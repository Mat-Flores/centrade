"""Adaptateur d'exécution de Freqtrade (SPEC §7, F9, F10, annexe C, ADR 0008).

La plateforme règle le moteur et lit ce qu'il fait ; elle n'émet aucun ordre : aucun appel à
`/forceenter` (I2, I11). Tout passe par l'API du moteur, joignable sur le réseau `engines` avec les
identifiants propres à l'instance. Moteur muet, lent ou incohérent : EngineUnreachable (donc
`unknown`), jamais un état supposé (I1).
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
FILES_DIR = "/run/centrade"  # point de montage fixé par le runner
CRED_NAMES = ("username", "password", "jwt_secret_key", "ws_token")
# Trades clos (`GET /trades`, `limit` et `offset`, tri par date de clôture décroissante : tag
# 2026.9). Premier relevé d'un processus : tout l'historique, par pages. Ensuite : les pages
# récentes, jusqu'à recouper un trade déjà relu.
HISTORY_PAGE = 200
RECENT_PAGE = 50
HISTORY_CAP = 50_000  # au-delà : ClosedHistoryOverflow, jamais une perte silencieuse
HEALTH_STALE_S = 120.0  # boucle du moteur muette plus longtemps : `error`
STOP_GRACE_S = 10.0  # pause et annulation des entrées avant l'arrêt : au mieux, pas plus
_NS = uuid5(NAMESPACE_URL, "https://centrade.invalid/freqtrade")

# Raison de sortie du moteur (ExitType, tag 2026.9) -> énumération de F10. Hors table : unknown.
EXIT_CAUSE = {
    "roi": "take_profit",
    "stop_loss": "stop_loss",
    "stoploss_on_exchange": "stop_loss",
    "trailing_stop_loss": "trailing_stop",
    "exit_signal": "signal",
    "custom_exit": "signal",
    "force_exit": "manual",  # indistinguable d'un flatten ou du kill switch côté moteur
    "emergency_exit": "engine_protection",
    "liquidation": "liquidation",
}
_STATES: dict[str, ObservedState] = {
    "running": "running",
    "paused": "exits_only",
    "stopped": "halted",  # processus vivant, moteur arrêté, positions non gérées (F9)
    "reload_config": "starting",
}


class EngineRunner(Protocol):
    """Ce que l'adaptateur demande au runner (`centrade_worker.runner.DockerRunner`)."""

    async def create(self, spec: Any) -> Any: ...
    async def start(self, instance_id: UUID) -> Any: ...
    async def stop(self, instance_id: UUID, timeout_s: int = 30) -> None: ...
    async def inspect(self, instance_id: UUID) -> Any: ...


class ClosedHistoryOverflow(EngineUnreachable):
    """L'historique des trades clos dépasse HISTORY_CAP : le relevé est refusé plutôt que rendu
    incomplet. Le worker le voit comme un moteur illisible, avec ce nom dans son journal."""


# Ce qu'une réponse du moteur mal formée fait lever en la lisant : clé absente, mauvais type,
# valeur non décimale, date hors bornes, modèle refusé par pydantic (ValueError).
_MALFORMED = (LookupError, TypeError, ValueError, ArithmeticError, AttributeError, OSError,
              RecursionError)  # fmt: skip


@contextmanager
def _engine_answers() -> Iterator[None]:
    """Seul endroit où une réponse illisible devient EngineUnreachable : l'état de cette instance
    est alors `unknown`, et le tour du worker continue pour les autres."""
    try:
        yield
    except _MALFORMED as exc:
        raise EngineUnreachable(f"réponse du moteur malformée : {type(exc).__name__}") from exc


def default_address(instance_id: UUID) -> str:
    # Nom DNS du conteneur sur le réseau `engines` (le runner nomme `centrade-engine-<id>`).
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
    """Ce que l'adaptateur a déjà annoncé d'une instance (le relevé reste la source de vérité)."""

    seq: int | None = None
    state: tuple[str, str | None] | None = None
    orders: dict[str, str] = field(default_factory=dict)
    positions: dict[str, tuple[Decimal, Decimal]] = field(default_factory=dict)
    stops: dict[str, Decimal | None] = field(default_factory=dict)
    closed: set[str] = field(default_factory=set)
    history: bool = False  # l'historique entier des trades clos a été annoncé par ce processus


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
        self._snap_closed: dict[UUID, set[str]] = {}  # trades clos déjà rendus par `snapshot`
        self._overflow: set[UUID] = set()

    # --- contrôles purs ---------------------------------------------------------------------
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

    # --- cycle de vie -----------------------------------------------------------------------
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
        log.info("moteur_deploye", instance_id=str(iid), mode=spec.mode, image=dep.image)
        return ref

    def _container(self, spec: InstanceSpec, strategy_file: str, directory: Path) -> Any:
        from centrade_worker.runner import ContainerSpec  # le runner appartient au worker

        dep = spec.deployment
        assert dep is not None  # noqa: S101 (vérifié par l'appelant)
        return ContainerSpec(
            instance_id=spec.instance_id,
            image=dep.image,
            digest=dep.digest,
            command=(
                "trade",
                "--config",
                f"{FILES_DIR}/{CONFIG_FILE}",
                "--config",
                f"{FILES_DIR}/credentials.json",  # fusionné en dernier
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
                await self._post(ref, "pause")  # moteur arrêté, processus vivant : sorties seules
            return
        # Le dossier de l'instance a gardé configuration et stratégie ; l'arrêt a retiré les
        # identifiants, renouvelés ici. Le moteur redémarre en `paused` (configuration générée).
        await self._runtime.write_files(ref.instance_id, {}, await self._issue(ref.instance_id))
        await self._runner.start(ref.instance_id)

    async def stop(self, ref: InstanceRef) -> None:
        """F9 : pause, annulation des ordres d'entrée, arrêt du conteneur. Les deux premières
        sont tentées au mieux, dans un délai court ; le conteneur est arrêté dans tous les cas,
        et leur échec remonte ensuite."""
        iid = ref.instance_id
        failed: Exception | None = None
        c = await self._runner.inspect(iid)
        if c is not None and c.status == "running":
            try:
                async with asyncio.timeout(STOP_GRACE_S):
                    failed = await self._reduce_entries(ref)
            except TimeoutError:
                failed = EngineUnreachable("API du moteur muette avant l'arrêt")
                log.warning("arret_sans_pause_confirmee", instance_id=str(iid))
            await self._runner.stop(iid)
        await self._runtime.cleanup(iid)
        self._creds.pop(iid, None)
        log.info("moteur_arrete", instance_id=str(iid))
        if failed is not None:
            raise failed

    async def pause_entries(self, ref: InstanceRef) -> None:
        failed = await self._reduce_entries(ref)
        if failed is not None:
            raise failed

    async def _reduce_entries(self, ref: InstanceRef) -> Exception | None:
        """Pause, puis annulation des ordres d'entrée ouverts : chacune est tentée même si
        l'autre échoue. La première erreur est rendue, pas levée : l'appelant fait d'abord passer
        ce qui ne doit jamais attendre (une sortie, l'arrêt du conteneur)."""
        first: Exception | None = None
        for step in (self._pause, self._cancel_entries):
            try:
                with _engine_answers():
                    await step(ref)
            except (EngineUnreachable, CommandRejected) as exc:
                log.warning(
                    "reduction_des_entrees_incomplete",
                    instance_id=str(ref.instance_id),
                    step=step.__name__,
                    error=str(exc),
                )
                first = first or exc
        return first

    async def _pause(self, ref: InstanceRef) -> None:
        await self._post(ref, "pause")  # depuis `stopped`, démarre le moteur en pause

    async def _cancel_entries(self, ref: InstanceRef) -> None:
        api = await self._api(ref)
        for trade in await self._open_trades(api):
            orders = _open_orders(trade)
            # La route annule tous les ordres ouverts du trade (ADR 0008) : dès qu'un ordre de
            # sortie ou de stop est ouvert, rien n'est annulé.
            if orders and all(_intent(o) == "entry" for o in orders):
                await _cancel_open(api, trade["trade_id"])

    async def resume_entries(self, ref: InstanceRef) -> None:
        state = await self._engine_state(ref)
        if state == "paused":
            await self._post(ref, "start")
        elif state != "running":
            raise CommandRejected(f"reprise des entrées impossible depuis l'état {state}")

    async def flatten(self, ref: InstanceRef) -> None:
        """I4 : la sortie de tout part quoi qu'il arrive à la pause et à l'annulation des
        entrées ; leur échec est journalisé et remonte après. La pause réveille aussi un moteur
        arrêté, que `forceexit` refuserait. Sans trade ouvert, `forceexit` ne fait rien."""
        failed = await self._reduce_entries(ref)
        api = await self._api(ref)
        await api.call("POST", "forceexit", {"tradeid": "all"}, read_s=EXIT_TIMEOUT_S)
        if failed is not None:
            raise failed

    async def close_position(self, ref: InstanceRef, position_id: str) -> None:
        api = await self._api(ref)
        try:  # lectures préalables au mieux : illisibles, elles ne retiennent pas la sortie (I4)
            with _engine_answers():
                if not any(str(t["trade_id"]) == position_id for t in await self._open_trades(api)):
                    return  # déjà fermée
                if await self._engine_state(ref) == "stopped":
                    await self._post(ref, "pause")  # forceexit refuse un moteur arrêté
        except (EngineUnreachable, CommandRejected) as exc:
            log.warning("lecture_avant_sortie_en_echec", instance_id=str(ref.instance_id),
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
                # La route annule tous les ordres ouverts du trade (ADR 0008) : sortie ou stop,
                # jamais. Entre cette lecture et l'appel, un ordre de sortie peut naître : limite
                # de la route du moteur, consignée dans l'ADR 0008, à lever avant le live.
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
        # Le battement ne vaut que pour une boucle censée tourner : arrêté ou en rechargement, le
        # moteur ne met pas `last_process` à jour (`process_stopped`, tag 2026.9).
        if state in ("running", "exits_only"):
            beat = health.get("last_process_ts")
            if isinstance(beat, bool) or not isinstance(beat, int):
                raise EngineUnreachable("battement du moteur absent ou illisible")
            if now.timestamp() - beat > HEALTH_STALE_S:
                state = "error"  # le processus répond, sa boucle ne tourne plus
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
                # En dry-run le stop est toujours tenu par le moteur (ADR 0008, fait 6).
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
        """Événements nés de l'écart entre deux relevés. Un tour interrompu rejoue les mêmes
        identifiants (déterministes) : jamais de doublon côté ingestion."""
        iid = ref.instance_id
        tr = self._tracks.setdefault(iid, _Track())
        if tr.seq is None:  # départ après les séquences d'un worker précédent (hors trou répété)
            tr.seq = int(self._clock().timestamp())
        c = await self._runner.inspect(iid)
        with _engine_answers():
            if c is None or c.status != "running":
                # Conteneur arrêté : pas d'API à lire, mais l'arrêt lui-même s'annonce une fois.
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

    # --- interne ----------------------------------------------------------------------------
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
        """Trades clos, du plus ancien au plus récent. `seen` vaut None au premier relevé d'un
        processus : tout l'historique est relu (I9, S5). Sinon : les pages récentes, jusqu'à
        celle qui recoupe `seen` ; tout ce qui est plus ancien a déjà été rendu."""
        if iid in self._overflow:
            raise ClosedHistoryOverflow(f"plus de {HISTORY_CAP} trades clos : relevé refusé")
        size = HISTORY_PAGE if seen is None else RECENT_PAGE
        found: dict[str, dict[str, Any]] = {}  # une clôture entre deux pages décale : doublons
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
                log.error("historique_des_trades_clos_trop_long", instance_id=str(iid))
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
        # Ordre rempli, annulé ou trade retiré entre la lecture et l'appel : l'effet voulu est là.
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
        entry_cause=t.get("enter_tag") or "signal",  # force_entry_enable est faux : le signal
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
        key = ("state", state, mode, tr.seq + 1 + len(out))  # distinct même si l'état revient
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
