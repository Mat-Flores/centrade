"""Projections dérivées, jamais d'autorité : remplacées d'après le relevé du moteur (SPEC §7).

Chaque ligne garde l'heure de l'observation dont elle provient (`observed_at`, I1).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from centrade_core.engine.types import InstanceStatus, Snapshot
from centrade_core.models.trading import Alert, Instance, Order, Position
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

UNREACHABLE_RULE = "engine_unreachable"


def _currency(symbol: str) -> str:
    return symbol.rsplit("/", 1)[-1]  # devise de cotation ; le relevé n'en porte pas d'autre


async def apply_observation(
    s: AsyncSession, instance_id: UUID, status: InstanceStatus, snap: Snapshot
) -> None:
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
        await s.execute(
            insert(Position)
            .values(instance_id=instance_id, external_id=p.position_id, **row)
            .on_conflict_do_update(
                index_elements=["instance_id", "external_id"],
                set_={**row, "updated_at": func.now()},
            )
        )
    open_ids = [o.order_id for o in snap.orders]
    # Un ordre local encore ouvert que le moteur ne connaît plus : issue inconnue, jamais inventée.
    await s.execute(
        update(Order)
        .where(
            Order.instance_id == instance_id,
            Order.status == "open",
            Order.client_order_id.not_in(open_ids),
        )
        .values(status="unknown")
    )
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
        await s.execute(
            insert(Order)
            .values(instance_id=instance_id, client_order_id=o.order_id, **row)
            .on_conflict_do_update(
                index_elements=["client_order_id"], set_={**row, "updated_at": func.now()}
            )
        )
    await s.execute(  # le moteur répond de nouveau : l'alerte se résout
        update(Alert)
        .where(
            Alert.rule == UNREACHABLE_RULE,
            Alert.target_id == instance_id,
            Alert.status != "resolved",
        )
        .values(status="resolved", resolved_at=func.now())
    )


async def mark_unknown(s: AsyncSession, instance_id: UUID, now: datetime) -> bool:
    """Moteur injoignable : état `unknown`. Positions et ordres gardent leur ancienne observation
    (ils deviendront périmés) ; rien n'est remis à zéro. Rend True si une alerte a été créée."""
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
    if open_alert is not None:
        return False
    s.add(
        Alert(
            rule=UNREACHABLE_RULE,
            severity="critical",
            target_kind="instance",
            target_id=instance_id,
            message="Moteur injoignable : état observé inconnu, relevés conservés mais périmés.",
            invariant="I1",
        )
    )
    return True
