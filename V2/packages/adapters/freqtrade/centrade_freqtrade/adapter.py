"""Freqtrade execution adapter (SPEC §7, F9, F10, annex C, ADR 0008).

The platform configures the engine and reads what it does; it places no order: no call to
`/forceenter` (I2, I11). Everything goes through the engine's API, reachable on the `engines`
network with the instance's own credentials. Silent, slow or inconsistent engine:
EngineUnreachable (hence `unknown`), never an assumed state (I1).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

import requests
import structlog
from centrade_core.engine.contract import CommandRejected, EngineUnreachable, InstanceRuntime
from centrade_core.engine.types import (
    BacktestResult,
    BacktestSpec,
    Balance,
    Capabilities,
    ClosedTrade,
    Drift,
    EffectiveConfig,
    EngineConfig,
    InstanceRef,
    InstanceSpec,
    InstanceStatus,
    Intent,
    Manifest,
    ObservedState,
    Order,
    Position,
    Snapshot,
    Stop,
    ValidationResult,
)
from centrade_core.events import (
    CanonicalEvent,
    EventType,
    ExitCause,
    OrderPayload,
    Payload,
    PositionClosed,
    PositionUpdated,
    ProtectionUpdated,
    StatusChanged,
)

from centrade_freqtrade import checks, config
from centrade_freqtrade.capabilities import capabilities
from centrade_freqtrade.client import EXIT_TIMEOUT_S, EngineApi
from centrade_freqtrade.image import ENGINE_MEMORY_BYTES, ENGINE_NANO_CPUS

log = structlog.get_logger("centrade_freqtrade")

ENGINE = checks.ENGINE
CONFIG_FILE = "config.json"
BASE_FILE = "control_plane.py"
FILES_DIR = "/run/centrade"  # mount point set by the runner
CRED_NAMES = ("username", "password", "jwt_secret_key", "ws_token")
# Closed trades (`GET /trades`, `limit` and `offset`, sorted by descending close date: tag
# 2026.9). A process's first snapshot: the whole history, in pages. After that: the recent
# pages, until overlapping an already re-read trade.
HISTORY_PAGE = 200
RECENT_PAGE = 50
HISTORY_CAP = 50_000  # beyond: ClosedHistoryOverflow, never a silent loss
HEALTH_STALE_S = 120.0  # engine loop silent for longer: `error`
STOP_GRACE_S = 10.0  # pause and entry cancellation before stopping: best effort, no more
_NS = uuid5(NAMESPACE_URL, "https://centrade.invalid/freqtrade")

# Engine exit reason (ExitType, tag 2026.9) -> F10 enumeration. Outside the table: unknown.
EXIT_CAUSE = {
    "roi": "take_profit",
    "stop_loss": "stop_loss",
    "stoploss_on_exchange": "stop_loss",
    "trailing_stop_loss": "trailing_stop",
    "exit_signal": "signal",
    "custom_exit": "signal",
    "force_exit": "manual",  # engine cannot tell it from a flatten or the kill switch
    "emergency_exit": "engine_protection",
    "liquidation": "liquidation",
}
_STATES: dict[str, ObservedState] = {
    "running": "running",
    "paused": "exits_only",
    "stopped": "halted",  # process alive, engine stopped, positions unmanaged (F9)
    "reload_config": "starting",
}


class EngineRunner(Protocol):
    """What the adapter asks of the runner (`centrade_worker.runner.DockerRunner`)."""

    async def create(self, spec: Any) -> Any: ...
    async def start(self, instance_id: UUID) -> Any: ...
    async def stop(self, instance_id: UUID, timeout_s: int = 30) -> None: ...
    async def inspect(self, instance_id: UUID) -> Any: ...


class ClosedHistoryOverflow(EngineUnreachable):
    """The closed-trade history exceeds HISTORY_CAP: the snapshot is refused rather than returned
    incomplete. The worker sees it as an unreadable engine, with this name in its log."""


# What a malformed engine response raises when read: missing key, wrong type,
# non-decimal value, date out of bounds, model refused by pydantic (ValueError).
_MALFORMED = (LookupError, TypeError, ValueError, ArithmeticError, AttributeError, OSError,
              RecursionError)  # fmt: skip


@contextmanager
def _engine_answers() -> Iterator[None]:
    """The only place where an unreadable response becomes EngineUnreachable: this instance's state
    is then `unknown`, and the worker's round continues for the others."""
    try:
        yield
    except _MALFORMED as exc:
        raise EngineUnreachable(f"réponse du moteur malformée : {type(exc).__name__}") from exc


def default_address(instance_id: UUID) -> str:
    # Container DNS name on the `engines` network (the runner names it `centrade-engine-<id>`).
    return f"http://centrade-engine-{instance_id}:{config.API_PORT}"


def _dec(v: Any) -> Decimal | None:
    return None if v is None else Decimal(v)


def _when(ms: Any) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, UTC)


def _cid(instance_id: UUID, engine_order_id: str) -> UUID:
    return uuid5(_NS, f"{instance_id}:order:{engine_order_id}")


def _eid(instance_id: UUID, *parts: object) -> UUID:
    return uuid5(_NS, f"{instance_id}:" + ":".join(map(str, parts)))


def _intent(order: Mapping[str, Any]) -> Intent:
    side = order["ft_order_side"]
    return "entry" if side == "buy" else "stop" if side == "stoploss" else "exit"


def _stage(order: Mapping[str, Any]) -> str:
    if order["is_open"]:
        return "open"
    if order["status"] == "closed":
        return "filled"
    return "rejected" if order["status"] == "rejected" else "canceled"


def _open_orders(trade: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [o for o in trade["orders"] if o["is_open"]]


@dataclass
class _Track:
    """What the adapter has already announced about an instance (the snapshot stays the truth)."""

    seq: int | None = None
    state: tuple[str, str | None] | None = None
    orders: dict[str, str] = field(default_factory=dict)
    positions: dict[str, tuple[Decimal, Decimal]] = field(default_factory=dict)
    stops: dict[str, Decimal | None] = field(default_factory=dict)
    closed: set[str] = field(default_factory=set)
    history: bool = False  # the whole closed-trade history was announced by this process


class FreqtradeAdapter:
    def __init__(
        self,
        runner: EngineRunner,
        runtime: InstanceRuntime,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        http: Callable[[], requests.Session] = requests.Session,
        address: Callable[[UUID], str] = default_address,
    ) -> None:
        self._runner = runner
        self._runtime = runtime
        self._clock = clock
        self._http = http
        self._address = address
        self._creds: dict[UUID, tuple[str, str]] = {}
        self._tracks: dict[UUID, _Track] = {}
        self._snap_closed: dict[UUID, set[str]] = {}  # closed trades already returned by `snapshot`
        self._overflow: set[UUID] = set()

    # --- pure checks ------------------------------------------------------------------------
    def capabilities(self) -> Capabilities:
        return capabilities()

    def validate(self, manifest: Manifest, params: dict[str, Any]) -> ValidationResult:
        return checks.validate(manifest, params)

    def check_source(self, manifest: Manifest, source: str) -> ValidationResult:
        return checks.check_source(manifest, source)

    def render_config(self, spec: InstanceSpec) -> EngineConfig:
        return config.render_config(spec)

    def config_drift(
        self, generated: EngineConfig, effective: EffectiveConfig
    ) -> tuple[Drift, ...]:
        found = config.observed_drift(generated, effective.values)
        return tuple(Drift(key=d.key, expected=d.expected, observed=d.observed) for d in found)

    # --- lifecycle --------------------------------------------------------------------------
    async def deploy(self, spec: InstanceSpec) -> InstanceRef:
        iid = spec.instance_id
        ref = InstanceRef(engine=ENGINE, instance_id=iid)
        dep = spec.deployment
        if dep is None:
            raise CommandRejected("déploiement sans empreinte ni image : refusé")
        if await self._runner.inspect(iid) is not None:  # idempotent
            return ref
        strategy_file = spec.manifest.entrypoint.rsplit("/", 1)[-1]
        if strategy_file in (CONFIG_FILE, BASE_FILE, "credentials.json"):
            raise CommandRejected("nom de fichier de stratégie réservé")
        creds = await self._issue(iid)
        files = {
            CONFIG_FILE: config.config_file(spec),
            BASE_FILE: Path(__file__).with_name("control_plane.py").read_text(encoding="utf-8"),
            strategy_file: dep.code,
        }
        directory = await self._runtime.write_files(iid, files, creds)
        try:
            await self._runner.create(self._container(spec, strategy_file, directory))
            await self._runner.start(iid)
        except BaseException:
            await self._runtime.cleanup(iid)
            raise
        log.info("engine_deployed", instance_id=str(iid), mode=spec.mode, image=dep.image)
        return ref

    def _container(self, spec: InstanceSpec, strategy_file: str, directory: Path) -> Any:
        from centrade_worker.runner import ContainerSpec  # the runner belongs to the worker

        dep = spec.deployment
        assert dep is not None  # noqa: S101 (checked by the caller)
        return ContainerSpec(
            instance_id=spec.instance_id,
            image=dep.image,
            digest=dep.digest,
            command=(
                "trade",
                "--config",
                f"{FILES_DIR}/{CONFIG_FILE}",
                "--config",
                f"{FILES_DIR}/credentials.json",  # merged last
                "--strategy-path",
                FILES_DIR,
                "--strategy",
                strategy_file.removesuffix(".py"),
                "--userdir",
                config.USER_DATA,
            ),
            files_dir=directory,
            mode=spec.mode,
            fingerprint=dep.fingerprint,
            memory_bytes=ENGINE_MEMORY_BYTES if dep.memory_mb is None else dep.memory_mb * 1024**2,
            nano_cpus=ENGINE_NANO_CPUS if dep.cpus is None else int(dep.cpus * 1_000_000_000),
            user=self._runtime.container_user(),
        )

    async def _issue(self, iid: UUID) -> dict[str, Any]:
        issued = await self._runtime.issue_credentials(iid, CRED_NAMES)
        values = {k: v.get_secret_value() for k, v in issued.items()}
        self._creds[iid] = (values["username"], values["password"])
        return {"api_server": values}

    async def start(self, ref: InstanceRef) -> None:
        c = await self._runner.inspect(ref.instance_id)
        if c is None:
            raise CommandRejected("conteneur absent : déployer d'abord")
        if c.status == "running":
            if await self._engine_state(ref) == "stopped":
                await self._post(ref, "pause")  # engine stopped, process alive: exits-only
            return
        # The instance folder kept configuration and strategy; the stop removed the
        # credentials, renewed here. The engine restarts in `paused` (generated configuration).
        await self._runtime.write_files(ref.instance_id, {}, await self._issue(ref.instance_id))
        await self._runner.start(ref.instance_id)

    async def stop(self, ref: InstanceRef) -> None:
        """F9: pause, entry order cancellation, container stop. The first two
        are attempted best effort, within a short delay; the container is stopped in every case,
        and their failure is raised afterwards."""
        iid = ref.instance_id
        failed: Exception | None = None
        c = await self._runner.inspect(iid)
        if c is not None and c.status == "running":
            try:
                async with asyncio.timeout(STOP_GRACE_S):
                    failed = await self._reduce_entries(ref)
            except TimeoutError:
                failed = EngineUnreachable("API du moteur muette avant l'arrêt")
                log.warning("stop_without_confirmed_pause", instance_id=str(iid))
            await self._runner.stop(iid)
        await self._runtime.cleanup(iid)
        self._creds.pop(iid, None)
        log.info("engine_stopped", instance_id=str(iid))
        if failed is not None:
            raise failed

    async def pause_entries(self, ref: InstanceRef) -> None:
        failed = await self._reduce_entries(ref)
        if failed is not None:
            raise failed

    async def _reduce_entries(self, ref: InstanceRef) -> Exception | None:
        """Pause, then cancellation of open entry orders: each is attempted even if the
        other fails. The first error is returned, not raised: the caller first lets through
        what must never wait (an exit, the container stop)."""
        first: Exception | None = None
        for step in (self._pause, self._cancel_entries):
            try:
                with _engine_answers():
                    await step(ref)
            except (EngineUnreachable, CommandRejected) as exc:
                log.warning(
                    "entry_reduction_incomplete",
                    instance_id=str(ref.instance_id),
                    step=step.__name__,
                    error=str(exc),
                )
                first = first or exc
        return first

    async def _pause(self, ref: InstanceRef) -> None:
        await self._post(ref, "pause")  # from `stopped`, starts the engine paused

    async def _cancel_entries(self, ref: InstanceRef) -> None:
        api = await self._api(ref)
        for trade in await self._open_trades(api):
            orders = _open_orders(trade)
            # The route cancels all the trade's open orders (ADR 0008): as soon as an exit
            # or stop order is open, nothing is cancelled.
            if orders and all(_intent(o) == "entry" for o in orders):
                await _cancel_open(api, trade["trade_id"])

    async def resume_entries(self, ref: InstanceRef) -> None:
        state = await self._engine_state(ref)
        if state == "paused":
            await self._post(ref, "start")
        elif state != "running":
            raise CommandRejected(f"reprise des entrées impossible depuis l'état {state}")

    async def flatten(self, ref: InstanceRef) -> None:
        """I4: the exit of everything goes out whatever happens to the pause and the cancellation
        of entries; their failure is logged and raised afterwards. The pause also wakes a stopped
        engine, which `forceexit` would refuse. With no open trade, `forceexit` does nothing."""
        failed = await self._reduce_entries(ref)
        api = await self._api(ref)
        await api.call("POST", "forceexit", {"tradeid": "all"}, read_s=EXIT_TIMEOUT_S)
        if failed is not None:
            raise failed

    async def close_position(self, ref: InstanceRef, position_id: str) -> None:
        api = await self._api(ref)
        try:  # best-effort prior reads: unreadable, they do not hold back the exit (I4)
            with _engine_answers():
                if not any(str(t["trade_id"]) == position_id for t in await self._open_trades(api)):
                    return  # already closed
                if await self._engine_state(ref) == "stopped":
                    await self._post(ref, "pause")  # forceexit refuses a stopped engine
        except (EngineUnreachable, CommandRejected) as exc:
            log.warning("read_before_exit_failed", instance_id=str(ref.instance_id),
                        error=str(exc))  # fmt: skip
        await api.call("POST", "forceexit", {"tradeid": position_id}, read_s=EXIT_TIMEOUT_S)

    async def cancel_entry_order(self, ref: InstanceRef, order_id: str) -> None:
        api = await self._api(ref)
        iid = ref.instance_id
        with _engine_answers():
            for trade in await self._open_trades(api):
                orders = _open_orders(trade)
                if not any(str(_cid(iid, o["order_id"])) == order_id for o in orders):
                    continue
                # The route cancels all the trade's open orders (ADR 0008): exit or stop,
                # never. Between this read and the call, an exit order may appear: a limit
                # of the engine's route, recorded in ADR 0008, to lift before live.
                if any(_intent(o) != "entry" for o in orders):
                    raise CommandRejected("le trade a un ordre de sortie ou de stop ouvert")
                await _cancel_open(api, trade["trade_id"])
                return

    # --- observation ------------------------------------------------------------------------
    async def status(self, ref: InstanceRef) -> InstanceStatus:
        now = self._clock()
        c = await self._runner.inspect(ref.instance_id)
        if c is None:
            raise EngineUnreachable("conteneur absent")
        if c.status in ("exited", "created"):
            return InstanceStatus(state="stopped", mode=None, observed_at=now)
        if c.status != "running":
            return InstanceStatus(state="error", mode=None, observed_at=now)
        api = await self._api(ref)
        cfg = await api.get("show_config")
        health = await api.get("health")
        if not isinstance(cfg, dict) or not isinstance(health, dict):
            raise EngineUnreachable("réponse inattendue du moteur")
        state = _STATES.get(str(cfg.get("state")))
        if state is None:
            raise EngineUnreachable("état du moteur inconnu")
        # The heartbeat only matters for a loop that is supposed to run: stopped or reloading, the
        # engine does not update `last_process` (`process_stopped`, tag 2026.9).
        if state in ("running", "exits_only"):
            beat = health.get("last_process_ts")
            if isinstance(beat, bool) or not isinstance(beat, int):
                raise EngineUnreachable("battement du moteur absent ou illisible")
            if now.timestamp() - beat > HEALTH_STALE_S:
                state = "error"  # the process answers, its loop no longer runs
        with _engine_answers():
            return InstanceStatus(state=state, mode=config.effective_mode(cfg), observed_at=now)

    async def effective_config(self, ref: InstanceRef) -> EffectiveConfig:
        c = await self._runner.inspect(ref.instance_id)
        if c is None:
            raise EngineUnreachable("conteneur absent")
        api = await self._api(ref)
        cfg = await api.get("show_config")
        wl = await api.get("whitelist")
        if not isinstance(cfg, dict) or not isinstance(wl, dict):
            raise EngineUnreachable("réponse inattendue du moteur")
        pairs = wl.get("whitelist")
        if not isinstance(pairs, list):
            raise EngineUnreachable("liste blanche illisible")
        version = cfg.get("version")
        with _engine_answers():
            return EffectiveConfig(
                values=config.observed_values(cfg, pairs),
                observed_at=self._clock(),
                fingerprint=c.fingerprint or None,
                engine_version=version if isinstance(version, str) else None,
            )

    async def snapshot(self, ref: InstanceRef) -> Snapshot:
        iid = ref.instance_id
        with _engine_answers():
            raw = await self._read(ref, self._snap_closed.get(iid))
            snap = self._snapshot(iid, raw)
        self._snap_closed.setdefault(iid, set()).update(c.position_id for c in snap.closed)
        return snap

    def _snapshot(self, iid: UUID, raw: Mapping[str, Any]) -> Snapshot:
        venue, dry = raw["venue"], raw["dry_run"]
        positions: list[Position] = []
        orders: list[Order] = []
        stops: list[Stop] = []
        for t in raw["open"]:
            sym = _symbol(venue, t["pair"])
            for o in t["orders"]:
                if o["is_open"]:
                    orders.append(
                        Order(
                            order_id=str(_cid(iid, o["order_id"])),
                            symbol=sym,
                            side="buy" if o["ft_order_side"] == "buy" else "sell",
                            intent=_intent(o),
                            qty=Decimal(o["amount"]),
                            price=Decimal(o["safe_price"]),
                            status="open",
                        )
                    )
            if t["nr_of_successful_entries"] > 0:
                pid = str(t["trade_id"])
                positions.append(
                    Position(
                        position_id=pid,
                        symbol=sym,
                        side="buy",
                        qty=Decimal(t["amount"]),
                        entry_price=Decimal(t["open_rate"]),
                        opened_at=_when(t["open_fill_timestamp"] or t["open_timestamp"]),
                    )
                )
                # in dry-run the stop is always held by the engine (ADR 0008, fact 6)
                on_venue = not dry and any(
                    o["is_open"] and o["ft_order_side"] == "stoploss" for o in t["orders"]
                )
                stops.append(
                    Stop(
                        position_id=pid,
                        price=_dec(t.get("stop_loss_abs")),
                        held_by="venue" if on_venue else "engine",
                    )
                )
        return Snapshot(
            positions=tuple(positions),
            orders=tuple(orders),
            balances=raw["balances"],
            stops=tuple(stops),
            observed_at=self._clock(),
            closed=tuple(_closed(venue, t) for t in raw["closed"]),
        )

    async def events(self, ref: InstanceRef) -> AsyncIterator[CanonicalEvent]:
        """Events born from the difference between two snapshots. An interrupted round replays the
        same (deterministic) identifiers: never a duplicate on the ingestion side."""
        iid = ref.instance_id
        tr = self._tracks.setdefault(iid, _Track())
        if tr.seq is None:  # start after a previous worker's sequences (excluding a repeated gap)
            tr.seq = int(self._clock().timestamp())
        c = await self._runner.inspect(iid)
        with _engine_answers():
            if c is None or c.status != "running":
                # Stopped container: no API to read, but the stop itself is announced once.
                raw: dict[str, Any] = {"state": ("stopped", None), "open": [], "closed": []}
                whole = tr.history
            else:
                raw = await self._read(ref, tr.closed if tr.history else None)
                whole = True
            out: list[CanonicalEvent] = []
            seq = tr.seq
            for when, key, kind, payload in _diff(iid, raw, tr, self._clock()):
                seq += 1
                out.append(
                    CanonicalEvent(
                        id=_eid(iid, *key),
                        ts=when or self._clock(),
                        seq=seq,
                        type=kind,
                        engine=ENGINE,
                        instance_id=iid,
                        payload=payload,
                    )
                )
        for ev in out:
            tr.seq = ev.seq
            yield ev
        _commit(raw, tr)
        tr.history = whole

    async def backtest(self, spec: BacktestSpec) -> BacktestResult:
        raise CommandRejected("backtest : non disponible à ce jalon")

    # --- internal ---------------------------------------------------------------------------
    async def _api(self, ref: InstanceRef) -> EngineApi:
        iid = ref.instance_id
        if iid not in self._creds:
            try:
                got = await self._runtime.credentials(iid)
            except LookupError as exc:
                raise EngineUnreachable("aucun identifiant pour ce moteur") from exc
            self._creds[iid] = (
                got["username"].get_secret_value(),
                got["password"].get_secret_value(),
            )
        user, password = self._creds[iid]
        return EngineApi(self._http, self._address(iid), user, password)

    async def _post(self, ref: InstanceRef, path: str) -> None:
        await (await self._api(ref)).call("POST", path)

    async def _engine_state(self, ref: InstanceRef) -> str:
        cfg = await (await self._api(ref)).get("show_config")
        if not isinstance(cfg, dict) or not isinstance(cfg.get("state"), str):
            raise EngineUnreachable("réponse inattendue du moteur")
        return str(cfg["state"])

    async def _open_trades(self, api: EngineApi) -> list[dict[str, Any]]:
        trades = await api.get("status")
        if not isinstance(trades, list):
            raise EngineUnreachable("réponse inattendue du moteur sur /status")
        return trades

    async def _closed_trades(
        self, iid: UUID, api: EngineApi, seen: set[str] | None
    ) -> list[dict[str, Any]]:
        """Closed trades, oldest to newest. `seen` is None at a process's first snapshot:
        the whole history is re-read (I9, S5). Otherwise: the recent pages, up to the one
        that overlaps `seen`; everything older has already been returned."""
        if iid in self._overflow:
            raise ClosedHistoryOverflow(f"plus de {HISTORY_CAP} trades clos : relevé refusé")
        size = HISTORY_PAGE if seen is None else RECENT_PAGE
        found: dict[str, dict[str, Any]] = {}  # a close between two pages shifts them: duplicates
        offset = 0
        while True:
            page = await api.get(
                "trades", {"limit": size, "offset": offset, "order_by_id": "false"}
            )
            trades = page["trades"]
            if not isinstance(trades, list):
                raise EngineUnreachable("réponse inattendue du moteur sur /trades")
            for t in trades:
                found.setdefault(str(t["trade_id"]), t)
            offset += len(trades)
            if len(trades) < size or (seen is not None and not seen.isdisjoint(found)):
                return list(reversed(found.values()))
            if offset >= HISTORY_CAP:
                self._overflow.add(iid)
                log.error("closed_trades_history_too_long", instance_id=str(iid))
                raise ClosedHistoryOverflow(f"plus de {HISTORY_CAP} trades clos : relevé refusé")

    async def _read(self, ref: InstanceRef, seen: set[str] | None) -> dict[str, Any]:
        api = await self._api(ref)
        cfg = await api.get("show_config")
        open_ = await self._open_trades(api)
        closed = await self._closed_trades(ref.instance_id, api, seen)
        bal = await api.get("balance")
        if not (isinstance(cfg, dict) and isinstance(bal, dict)):
            raise EngineUnreachable("réponse inattendue du moteur")
        return {
            "venue": cfg["exchange"],
            "dry_run": cfg["dry_run"] is True,
            "state": (_STATES.get(str(cfg.get("state"))), config.effective_mode(cfg)),
            "open": open_,
            "closed": closed,
            "balances": tuple(
                Balance(
                    currency=b["currency"], free=Decimal(b["free"]), total=Decimal(b["balance"])
                )
                for b in bal["currencies"]
            ),
        }


async def _cancel_open(api: EngineApi, trade_id: int) -> None:
    try:
        await api.call("DELETE", f"trades/{trade_id}/open-order")
    except CommandRejected as exc:
        # Order filled, canceled or trade removed between read and call: effect achieved.
        if not any(m in str(exc) for m in ("No open order", "no active trade", "Invalid trade_id")):
            raise


def _symbol(venue: str, pair: str) -> str:
    return f"crypto:{venue}:{pair}"


def _closed(venue: str, t: Mapping[str, Any]) -> ClosedTrade:
    fees = (_dec(t.get("fee_open_cost")) or Decimal(0)) + (_dec(t.get("fee_close_cost")) or 0)
    pnl = t.get("close_profit_abs")
    return ClosedTrade(
        position_id=str(t["trade_id"]),
        symbol=_symbol(venue, t["pair"]),
        side="buy",
        qty=Decimal(t["amount"]),
        entry_price=Decimal(t["open_rate"]),
        exit_price=Decimal(t["close_rate"]),
        pnl=Decimal(pnl if pnl is not None else t["realized_profit"]),
        fees=Decimal(fees),
        entry_cause=t.get("enter_tag") or "signal",  # force_entry_enable is false: the signal
        exit_cause=EXIT_CAUSE.get(t.get("exit_reason") or "", "unknown"),
        opened_at=_when(t["open_fill_timestamp"] or t["open_timestamp"]),
        closed_at=_when(t["close_timestamp"]),
    )


def _event_cause(cause: str | None) -> ExitCause:
    if cause in ("manual", "take_profit", "signal"):
        return cause  # type: ignore[return-value]
    return "stop" if cause in ("stop_loss", "trailing_stop") else "unknown"


Pending = tuple[datetime | None, tuple[object, ...], EventType, Payload]

_STAGE_EVENT = {
    "open": EventType.ORDER_SUBMITTED,
    "filled": EventType.ORDER_FILLED,
    "canceled": EventType.ORDER_CANCELED,
    "rejected": EventType.ORDER_REJECTED,
}


def _diff(iid: UUID, raw: Mapping[str, Any], tr: _Track, now: datetime) -> list[Pending]:
    assert tr.seq is not None  # noqa: S101
    out: list[Pending] = []
    venue: str = raw.get("venue", "")
    dry_run: bool = raw.get("dry_run", True)
    state, mode = raw["state"]
    if state is not None and (state, mode) != tr.state:
        key = ("state", state, mode, tr.seq + 1 + len(out))  # distinct even if the state comes back
        out.append(
            (now, key, EventType.INSTANCE_STATUS_CHANGED, StatusChanged(state=state, mode=mode))
        )
    trades = sorted([*raw["closed"], *raw["open"]], key=lambda t: t["trade_id"])
    for t in trades:
        sym = _symbol(venue, t["pair"])
        for o in sorted(t["orders"], key=lambda o: o.get("order_timestamp") or 0):
            stage, seen = _stage(o), tr.orders.get(o["order_id"])
            when = _when(o["order_timestamp"]) if o.get("order_timestamp") else None
            body = OrderPayload(
                client_order_id=_cid(iid, o["order_id"]),
                intent=_intent(o),
                symbol=sym,
                side="buy" if o["ft_order_side"] == "buy" else "sell",
                qty=Decimal(o["amount"]),
                price=Decimal(o["safe_price"]),
                currency=t["quote_currency"],
            )
            if seen is None:
                out.append(
                    (when, ("order", o["order_id"], "open"), EventType.ORDER_SUBMITTED, body)
                )
            if stage != "open" and seen != stage:
                done = (
                    _when(o["order_filled_timestamp"]) if o.get("order_filled_timestamp") else when
                )
                out.append((done, ("order", o["order_id"], stage), _STAGE_EVENT[stage], body))
    for t in raw["open"]:
        if t["nr_of_successful_entries"] <= 0:
            continue
        pid, sym = str(t["trade_id"]), _symbol(venue, t["pair"])
        qty, price = Decimal(t["amount"]), Decimal(t["open_rate"])
        if tr.positions.get(pid) != (qty, price):
            out.append((None, ("position", pid, qty, price), EventType.POSITION_UPDATED,
                        PositionUpdated(position_id=pid, symbol=sym, side="buy", qty=qty,
                                        entry_price=price)))  # fmt: skip
        stop = _dec(t.get("stop_loss_abs"))
        if pid not in tr.stops or tr.stops[pid] != stop:
            held = "venue" if not dry_run and any(
                o["is_open"] and o["ft_order_side"] == "stoploss" for o in t["orders"]
            ) else "engine"  # fmt: skip
            out.append((None, ("protection", pid, stop), EventType.PROTECTION_UPDATED,
                        ProtectionUpdated(position_id=pid, state="set" if pid not in tr.stops
                                          else "moved" if stop is not None else "absent",
                                          stop_price=stop, held_by=held)))  # fmt: skip
    for t in raw["closed"]:
        pid = str(t["trade_id"])
        if pid in tr.closed:
            continue
        ct = _closed(venue, t)
        cause = _event_cause(ct.exit_cause)
        out.append((ct.closed_at, ("closed", pid), EventType.POSITION_CLOSED,
                    PositionClosed(position_id=pid, symbol=ct.symbol, exit_cause=cause,
                                   qty=ct.qty, exit_price=ct.exit_price)))  # fmt: skip
        if pid in tr.stops:
            out.append((ct.closed_at, ("protection", pid, "absent"), EventType.PROTECTION_UPDATED,
                        ProtectionUpdated(position_id=pid, state="absent")))  # fmt: skip
    return out


def _commit(raw: Mapping[str, Any], tr: _Track) -> None:
    state, mode = raw["state"]
    if state is not None:
        tr.state = (state, mode)
    for t in [*raw["closed"], *raw["open"]]:
        for o in t["orders"]:
            tr.orders[o["order_id"]] = _stage(o)
    for t in raw["open"]:
        if t["nr_of_successful_entries"] > 0:
            pid = str(t["trade_id"])
            tr.positions[pid] = (Decimal(t["amount"]), Decimal(t["open_rate"]))
            tr.stops[pid] = _dec(t.get("stop_loss_abs"))
    for t in raw["closed"]:
        pid = str(t["trade_id"])
        tr.closed.add(pid)
        tr.positions.pop(pid, None)
        tr.stops.pop(pid, None)
