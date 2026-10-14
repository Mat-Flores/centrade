"""Derived projections, never authoritative: replaced from the engine snapshot (SPEC §7).

Each row keeps the time of the observation it comes from (`observed_at`, I1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from centrade_core.audit import SYSTEM_WORKER, write_audit
from centrade_core.engine.types import EXIT_CAUSES, InstanceStatus, Snapshot
from centrade_core.models.trading import Alert, Instance, Order, Position, Trade
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

UNREACHABLE_RULE = "engine_unreachable"


def _currency(symbol: str) -> str:
    return symbol.rsplit("/", 1)[-1]  # quote currency; the snapshot carries no other


async def apply_observation(
    s: AsyncSession, instance_id: UUID, status: InstanceStatus, snap: Snapshot
) -> list[tuple[str, UUID]]:
    """Replace the projections with the snapshot. Returns what is to be announced on the stream:
    resolved alerts (already audited), written positions and orders."""
    notes: list[tuple[str, UUID]] = []
    await s.execute(
        update(Instance)
        .where(Instance.id == instance_id)
        .values(
            observed_state=status.state,
            observed_mode=status.mode,
            observed_at=status.observed_at,
        )
    )
    ids = [p.position_id for p in snap.positions]
    await s.execute(
        delete(Position).where(
            Position.instance_id == instance_id, Position.external_id.not_in(ids)
        )
    )
    for p in snap.positions:
        row = {
            "instrument": p.symbol,
            "side": "long" if p.side == "buy" else "short",
            "quantity": p.qty,
            "entry_price": p.entry_price,
            "currency": _currency(p.symbol),
            "observed_at": snap.observed_at,
        }
        written = await s.scalars(
            insert(Position)
            .values(instance_id=instance_id, external_id=p.position_id, **row)
            .on_conflict_do_update(
                index_elements=["instance_id", "external_id"],
                set_={**row, "updated_at": func.now()},
            )
            .returning(Position.id)
        )
        notes.extend(("position", i) for i in written)
    for c in snap.closed:
        # The closed trade comes from the snapshot (events only say to re-read). An already
        # written row is not announced again; a cause outside F10 becomes `unknown`.
        written = await s.scalars(
            insert(Trade)
            .values(
                instance_id=instance_id,
                external_id=c.position_id,
                instrument=c.symbol,
                quantity=c.qty,
                entry_price=c.entry_price,
                exit_price=c.exit_price,
                entry_cause=c.entry_cause or "unknown",
                exit_cause=c.exit_cause if c.exit_cause in EXIT_CAUSES else "unknown",
                pnl=c.pnl,
                fees=c.fees,
                currency=_currency(c.symbol),
                opened_at=c.opened_at,
                closed_at=c.closed_at,
                duration_s=max(0, int((c.closed_at - c.opened_at).total_seconds())),
            )
            .on_conflict_do_nothing(index_elements=["instance_id", "external_id"])
            .returning(Trade.id)
        )
        notes.extend(("trade", i) for i in written)
    open_ids = [o.order_id for o in snap.orders]
    # A local order still open that the engine no longer knows: outcome unknown, never invented.
    lost = await s.scalars(
        update(Order)
        .where(
            Order.instance_id == instance_id,
            Order.status == "open",
            Order.client_order_id.not_in(open_ids),
        )
        .values(status="unknown")
        .returning(Order.id)
    )
    notes.extend(("order", i) for i in lost)
    for o in snap.orders:
        row = {
            "instrument": o.symbol,
            "side": o.side,
            "intent": o.intent,
            "status": o.status,
            "quantity": o.qty,
            "price": o.price,
            "currency": _currency(o.symbol),
            "observed_at": snap.observed_at,
        }
        written = await s.scalars(
            insert(Order)
            .values(instance_id=instance_id, client_order_id=o.order_id, **row)
            .on_conflict_do_update(
                index_elements=["client_order_id"], set_={**row, "updated_at": func.now()}
            )
            .returning(Order.id)
        )
        notes.extend(("order", i) for i in written)
    resolved = (  # the engine answers again: the alert resolves
        await s.scalars(
            update(Alert)
            .where(
                Alert.rule == UNREACHABLE_RULE,
                Alert.target_id == instance_id,
                Alert.status != "resolved",
            )
            .values(status="resolved", resolved_at=func.now())
            .returning(Alert.id)
        )
    ).all()
    for alert_id in resolved:  # audit last: same lock order as the API
        await write_audit(
            s,
            actor=SYSTEM_WORKER,
            action="alert.resolved",
            target=f"alert:{alert_id}",
            before={"status": "open"},
            after={"status": "resolved"},
        )
    return [("alert", a) for a in resolved] + notes


@dataclass(frozen=True)
class Unknown:
    became_unknown: bool  # the instance was not already `unknown`
    alert_id: UUID | None  # alert created on this pass


async def mark_unknown(s: AsyncSession, instance_id: UUID, now: datetime) -> Unknown:
    """Engine unreachable: `unknown` state. Positions and orders keep their old observation
    (they will become stale); nothing is reset."""
    previous = await s.scalar(select(Instance.observed_state).where(Instance.id == instance_id))
    await s.execute(
        update(Instance)
        .where(Instance.id == instance_id)
        .values(observed_state="unknown", observed_mode=None, observed_at=now)
    )
    open_alert = await s.scalar(
        select(Alert.id).where(
            Alert.rule == UNREACHABLE_RULE,
            Alert.target_id == instance_id,
            Alert.status != "resolved",
        )
    )
    alert = None
    if open_alert is None:
        alert = Alert(
            rule=UNREACHABLE_RULE,
            severity="critical",
            target_kind="instance",
            target_id=instance_id,
            message="Moteur injoignable : état observé inconnu, relevés conservés mais périmés.",
            invariant="I1",
        )
        s.add(alert)
        await s.flush()
    became = previous is not None and previous != "unknown"
    if became:  # an automation changes a state: it is audited (I14)
        await write_audit(
            s,
            actor=SYSTEM_WORKER,
            action="instance.observed_unknown",
            target=f"instance:{instance_id}",
            before={"observed_state": previous},
            after={"observed_state": "unknown"},
        )
    if alert is not None:
        await write_audit(
            s,
            actor=SYSTEM_WORKER,
            action="alert.raised",
            target=f"alert:{alert.id}",
            after={"rule": alert.rule, "severity": alert.severity},
        )
    return Unknown(became, None if alert is None else alert.id)
