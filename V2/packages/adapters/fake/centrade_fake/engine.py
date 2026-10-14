"""FakeEngine: implements the whole `centrade_core.engine` contract, in memory.

No strategy: arbitrary events, driven by `step()` (clock and seed injected).
Unreachable engine (`silent` and `crash` modes): `status()` and every command raise
`EngineUnreachable`; the caller uses `observe_status()`, which returns `unknown`, never `running`.
"""

from __future__ import annotations

import random
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from centrade_core.engine.contract import CommandRejected, EngineUnreachable
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
    PnlSnapshot,
    PositionClosed,
    PositionUpdated,
    ProtectionUpdated,
    StatusChanged,
)

ENGINE = "fake"
SYMBOL = "crypto:fake:BTC/USDT"
# Event causes -> F10 enumeration (emergency liquidation is a manual exit here).
_F10_CAUSE = {
    "manual": "manual",
    "flatten": "manual",
    "stop": "stop_loss",
    "take_profit": "take_profit",
    "signal": "signal",
}
SLOW_LAG = timedelta(seconds=60)  # `slow`: snapshots arrive aged, hence stale (I1)


class Failure(StrEnum):
    SLOW = "slow"
    SILENT = "silent"
    CRASH = "crash"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    DROP = "drop"
    ROGUE_ENTRY = "rogue_entry"
    IGNORE_PAUSE = "ignore_pause"
    LIE_MODE = "lie_mode"
    DRIFT = "drift"


@dataclass
class _Inst:
    spec: InstanceSpec
    config: dict[str, str]
    state: ObservedState = "exits_only"  # always starts in exits-only
    seq: int = 0
    realized: Decimal = Decimal(0)
    outbox: list[CanonicalEvent] = field(default_factory=list)
    positions: dict[str, Position] = field(default_factory=dict)
    orders: dict[str, Order] = field(default_factory=dict)  # open orders only
    decisions: dict[str, UUID | None] = field(default_factory=dict)
    stops: dict[str, Stop] = field(default_factory=dict)
    closed: list[ClosedTrade] = field(default_factory=list)
    failures: set[Failure] = field(default_factory=set)


class FakeEngine:
    def __init__(
        self,
        clock: Callable[[], datetime],
        seed: int,
        new_id: Callable[[], UUID],
        allow_failure_injection: bool = False,
    ) -> None:
        # False by default: outside tests, an instance's parameters simulate no failure.
        self._allow_failure_injection = allow_failure_injection
        self._clock = clock
        self._rng = random.Random(seed)  # noqa: S311 - simulation, no cryptography
        self._new_id = new_id
        self._insts: dict[UUID, _Inst] = {}

    # --- test driving -----------------------------------------------------------------
    def set_failure(self, ref: InstanceRef, mode: Failure, on: bool = True) -> None:
        inst = self._get(ref)
        if on:
            inst.failures.add(mode)
            if mode is Failure.CRASH:
                inst.state = "error"
        else:
            inst.failures.discard(mode)  # after a crash: `start()` restarts in exits-only

    def step(self, ref: InstanceRef) -> None:
        """Advances by one deterministic step: a few events at most. No effect if unreachable."""
        inst = self._get(ref)
        if inst.failures & {Failure.SILENT, Failure.CRASH} or inst.state in ("stopped", "error"):
            return
        rogue = Failure.ROGUE_ENTRY in inst.failures
        open_entry = next(iter(inst.orders.values()), None)
        a = self._rng.randrange(3)
        if (
            a == 0
            and (inst.state == "running" or rogue)
            and open_entry is None
            and len(inst.positions) < inst.spec.manifest.sizing.max_open_positions
        ):
            self._submit_entry(inst, decision=None if rogue else self._new_id())
        elif a == 1 and open_entry is not None:
            self._fill_entry(inst, open_entry)
        elif a == 1 and inst.positions:
            self._close(inst, next(iter(inst.positions.values())), "signal")
        else:
            self._emit(
                inst,
                EventType.PNL_SNAPSHOT,
                PnlSnapshot(currency="USDT", realized=inst.realized, unrealized=Decimal(0)),
            )

    # --- contract ---------------------------------------------------------------------
    def capabilities(self) -> Capabilities:
        return Capabilities(
            asset_classes=("crypto",),
            modes=("backtest", "paper", "live"),
            supports_flatten=True,
            supports_pause_entries=True,
            event_transport="push",
            hot_reload=False,
            risk_enforcement="hook",
            boots_exits_only=True,
            reports_effective_config=True,
            supports_reduce=True,
            supports_close_position=True,
            supports_cancel_entry_order=True,
            stop_on_venue={"fake": True},
            native_limits=("stake_amount", "max_open_positions"),
            supports_sandbox=True,
        )

    def validate(self, manifest: Manifest, params: dict[str, Any]) -> ValidationResult:
        known = set(manifest.params_schema.get("properties", {}))
        errors = tuple(f"paramètre inconnu : {k}" for k in sorted(set(params) - known))
        return ValidationResult(ok=not errors, errors=errors)

    def check_source(self, manifest: Manifest, source: str) -> ValidationResult:
        return ValidationResult(ok=True)  # the fake engine runs no code

    def render_config(self, spec: InstanceSpec) -> EngineConfig:
        m = spec.manifest
        return EngineConfig(
            values={
                "mode": spec.mode,
                "account_id": spec.account_id,
                "stake_amount": str(m.sizing.stake_amount),
                "max_open_positions": str(m.sizing.max_open_positions),
                "stoploss": str(m.exits.stoploss),
                "stop_on_venue": str(m.exits.stop_on_venue).lower(),
                "command_interface": "disabled",
            },
            mode_keys=frozenset({"mode", "account_id"}),
        )

    async def deploy(self, spec: InstanceSpec) -> InstanceRef:
        ref = InstanceRef(engine=ENGINE, instance_id=spec.instance_id)
        if spec.instance_id not in self._insts:  # idempotent
            # `params["failures"]`: failure modes from deployment (simulation without a route).
            names = spec.params.get("failures", ())
            if names and not self._allow_failure_injection:
                raise CommandRejected("injection de pannes non autorisée sur ce déploiement")
            failures = {Failure(name) for name in names}
            self._insts[spec.instance_id] = _Inst(spec, dict(self.render_config(spec).values))
            for mode in failures:
                self.set_failure(ref, mode)
        return ref

    async def start(self, ref: InstanceRef) -> None:
        inst = self._live(ref)
        if inst.state in ("stopped", "error", "starting"):
            self._set_state(inst, "exits_only")

    async def stop(self, ref: InstanceRef) -> None:
        inst = self._live(ref)
        self._cancel_entries(inst)
        self._set_state(inst, "stopped")

    async def pause_entries(self, ref: InstanceRef) -> None:
        inst = self._live(ref)
        if inst.state == "running" and Failure.IGNORE_PAUSE not in inst.failures:
            self._cancel_entries(inst)
            self._set_state(inst, "exits_only")

    async def resume_entries(self, ref: InstanceRef) -> None:
        inst = self._live(ref)
        if inst.state == "exits_only":
            self._set_state(inst, "running")
        elif inst.state != "running":
            raise CommandRejected(f"reprise des entrées impossible depuis l'état {inst.state}")

    async def flatten(self, ref: InstanceRef) -> None:
        inst = self._live(ref)
        self._cancel_entries(inst)
        for pos in list(inst.positions.values()):
            self._close(inst, pos, "flatten")

    async def close_position(self, ref: InstanceRef, position_id: str) -> None:
        inst = self._live(ref)
        if position_id in inst.positions:
            self._close(inst, inst.positions[position_id], "manual")

    async def cancel_entry_order(self, ref: InstanceRef, order_id: str) -> None:
        inst = self._live(ref)
        order = inst.orders.get(order_id)
        if order is not None and order.intent == "entry":
            self._cancel(inst, order)

    async def status(self, ref: InstanceRef) -> InstanceStatus:
        inst = self._live(ref)
        mode = inst.spec.mode
        if Failure.LIE_MODE in inst.failures:
            mode = "live" if mode == "paper" else "paper"
        return InstanceStatus(state=inst.state, mode=mode, observed_at=self._observed_at(inst))

    async def effective_config(self, ref: InstanceRef) -> EffectiveConfig:
        inst = self._live(ref)
        values = dict(inst.config)
        if Failure.DRIFT in inst.failures:
            values["max_open_positions"] = "999"
        dep = inst.spec.deployment  # the simulator "runs" what was deployed to it
        return EffectiveConfig(
            values=values,
            observed_at=self._observed_at(inst),
            fingerprint=None if dep is None else dep.fingerprint,
            engine_version=None if dep is None else dep.engine_version,
        )

    def config_drift(
        self, generated: EngineConfig, effective: EffectiveConfig
    ) -> tuple[Drift, ...]:
        return tuple(
            Drift(key=k, expected=generated.values.get(k), observed=v)
            for k, v in sorted(effective.values.items())
            if generated.values.get(k) != v
        )

    async def snapshot(self, ref: InstanceRef) -> Snapshot:
        inst = self._live(ref)
        total = Decimal(1000) + inst.realized
        return Snapshot(
            positions=tuple(inst.positions.values()),
            orders=tuple(inst.orders.values()),
            balances=(Balance(currency="USDT", free=total, total=total),),
            stops=tuple(inst.stops.values()),
            observed_at=self._observed_at(inst),
            closed=tuple(inst.closed),
        )

    async def events(self, ref: InstanceRef) -> AsyncIterator[CanonicalEvent]:
        """Empties the instance's outbox (finite stream); call again after `step()`."""
        inst = self._live(ref)
        batch, inst.outbox = inst.outbox, []
        for ev in batch:
            yield ev

    async def backtest(self, spec: BacktestSpec) -> BacktestResult:
        return BacktestResult(ok=True, trades=0)

    # --- internal ---------------------------------------------------------------------
    def _get(self, ref: InstanceRef) -> _Inst:
        try:
            return self._insts[ref.instance_id]
        except KeyError:
            raise CommandRejected(f"instance inconnue : {ref.instance_id}") from None

    def _live(self, ref: InstanceRef) -> _Inst:
        inst = self._get(ref)
        if inst.failures & {Failure.SILENT, Failure.CRASH}:
            raise EngineUnreachable(str(ref.instance_id))
        return inst

    def _observed_at(self, inst: _Inst) -> datetime:
        now = self._clock()
        return now - SLOW_LAG if Failure.SLOW in inst.failures else now

    def _emit(self, inst: _Inst, type_: EventType, payload: Payload) -> None:
        inst.seq += 1  # the sequence is consumed even if the event is lost (gap)
        m = inst.spec.manifest
        ev = CanonicalEvent(
            id=self._new_id(),
            ts=self._clock(),
            seq=inst.seq,
            type=type_,
            engine=ENGINE,
            instance_id=inst.spec.instance_id,
            strategy_version=f"{m.name}@{m.version}",
            account_id=inst.spec.account_id,
            payload=payload,
        )
        f = inst.failures
        if Failure.DROP in f:
            return
        if Failure.OUT_OF_ORDER in f and inst.outbox:
            inst.outbox.insert(len(inst.outbox) - 1, ev)
        else:
            inst.outbox.append(ev)
        if Failure.DUPLICATE in f:
            inst.outbox.append(ev)

    def _set_state(self, inst: _Inst, state: ObservedState) -> None:
        if inst.state != state:
            inst.state = state
            self._emit(
                inst,
                EventType.INSTANCE_STATUS_CHANGED,
                StatusChanged(state=state, mode=inst.spec.mode),
            )

    def _order_payload(
        self, inst: _Inst, order: Order, decision: UUID | None, fee: Decimal | None = None
    ) -> OrderPayload:
        return OrderPayload(
            client_order_id=UUID(order.order_id),
            intent=order.intent,
            decision_id=decision,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=order.price,
            fee=fee,
            currency="USDT",
        )

    def _submit_entry(self, inst: _Inst, decision: UUID | None) -> None:
        oid = self._new_id()
        order = Order(
            order_id=str(oid),
            symbol=SYMBOL,
            side="buy",
            intent="entry",
            qty=Decimal(self._rng.randint(1, 100)) / 100,
            price=Decimal(self._rng.randint(1000, 100000)) / 10,
            status="open",
        )
        inst.orders[order.order_id] = order
        inst.decisions[order.order_id] = decision
        self._emit(inst, EventType.ORDER_SUBMITTED, self._order_payload(inst, order, decision))

    def _fill_entry(self, inst: _Inst, order: Order) -> None:
        del inst.orders[order.order_id]
        decision = inst.decisions.pop(order.order_id, None)
        fee = order.qty * order.price * Decimal("0.001")
        self._emit(
            inst,
            EventType.ORDER_FILLED,
            self._order_payload(inst, order.model_copy(update={"status": "filled"}), decision, fee),
        )
        pos = Position(
            position_id=str(self._new_id()),
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            entry_price=order.price,
            opened_at=self._clock(),
        )
        inst.positions[pos.position_id] = pos
        self._emit(
            inst,
            EventType.POSITION_UPDATED,
            PositionUpdated(
                position_id=pos.position_id,
                symbol=pos.symbol,
                side=pos.side,
                qty=pos.qty,
                entry_price=pos.entry_price,
            ),
        )
        ex = inst.spec.manifest.exits
        stop = Stop(
            position_id=pos.position_id,
            price=pos.entry_price * (1 + ex.stoploss),
            held_by="venue" if ex.stop_on_venue else "engine",
        )
        inst.stops[pos.position_id] = stop
        self._emit(
            inst,
            EventType.PROTECTION_UPDATED,
            ProtectionUpdated(
                position_id=pos.position_id,
                state="set",
                stop_price=stop.price,
                held_by=stop.held_by,
            ),
        )

    def _cancel(self, inst: _Inst, order: Order) -> None:
        del inst.orders[order.order_id]
        decision = inst.decisions.pop(order.order_id, None)
        self._emit(
            inst,
            EventType.ORDER_CANCELED,
            self._order_payload(inst, order.model_copy(update={"status": "canceled"}), decision),
        )

    def _cancel_entries(self, inst: _Inst) -> None:
        for order in [o for o in inst.orders.values() if o.intent == "entry"]:
            self._cancel(inst, order)

    def _close(self, inst: _Inst, pos: Position, cause: ExitCause) -> None:
        del inst.positions[pos.position_id]
        stop = inst.stops.pop(pos.position_id, None)
        # Exit at the stop price, otherwise one tick above the entry: pnl and fees never zero.
        exit_price = pos.entry_price * Decimal("1.01")
        if cause == "stop" and stop and stop.price is not None:
            exit_price = stop.price
        exit_order = Order(
            order_id=str(self._new_id()),
            symbol=pos.symbol,
            side="sell",
            intent="exit",
            qty=pos.qty,
            price=exit_price,
            status="filled",
        )
        self._emit(inst, EventType.ORDER_FILLED, self._order_payload(inst, exit_order, None))
        inst.closed.append(
            ClosedTrade(
                position_id=pos.position_id,
                symbol=pos.symbol,
                side=pos.side,
                qty=pos.qty,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                pnl=(exit_price - pos.entry_price) * pos.qty,
                fees=exit_price * pos.qty * Decimal("0.001"),
                entry_cause="signal",
                exit_cause=_F10_CAUSE[cause],
                opened_at=pos.opened_at,
                closed_at=self._clock(),
            )
        )
        self._emit(
            inst,
            EventType.POSITION_CLOSED,
            PositionClosed(
                position_id=pos.position_id,
                symbol=pos.symbol,
                exit_cause=cause,
                qty=pos.qty,
                exit_price=exit_price,
            ),
        )
        self._emit(
            inst,
            EventType.PROTECTION_UPDATED,
            ProtectionUpdated(position_id=pos.position_id, state="absent"),
        )
