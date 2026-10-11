"""Ingestion idempotente : un événement déjà vu (même `id` ou `(instance_id, seq)`) est sans effet.

Un événement n'est qu'un indice (SPEC §7) : on le conserve, on met à jour l'historique des ordres,
mais les positions et l'état observé ne viennent que des relevés (voir projection.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from centrade_core.events import CanonicalEvent, EventType, OrderPayload
from centrade_core.models.trading import Event, Order
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

Anomaly = Literal["gap", "out_of_order", "duplicate"]

_ORDER_STATUS = {
    EventType.ORDER_SUBMITTED: "open",
    EventType.ORDER_FILLED: "filled",
    EventType.ORDER_CANCELED: "canceled",
    EventType.ORDER_REJECTED: "rejected",
}
# Un événement tardif ne fait jamais reculer un ordre ; seul un relevé peut le corriger.
_RANK = {"open": 0, "unknown": 1, "filled": 2, "canceled": 2, "rejected": 2}


@dataclass(frozen=True)
class Ingested:
    new: bool
    anomaly: Anomaly | None


async def ingest(
    sessions: async_sessionmaker[AsyncSession], ev: CanonicalEvent, now: datetime
) -> Ingested:
    async with sessions.begin() as s:
        seen = await s.scalar(
            select(Event.id).where(
                or_(
                    Event.id == ev.id, (Event.instance_id == ev.instance_id) & (Event.seq == ev.seq)
                )
            )
        )
        if seen is not None:
            return Ingested(new=False, anomaly="duplicate")
        top = await s.scalar(select(func.max(Event.seq)).where(Event.instance_id == ev.instance_id))
        anomaly: Anomaly | None = None
        if ev.seq <= (top or 0):
            anomaly = "out_of_order"
        elif ev.seq > (top or 0) + 1:
            anomaly = "gap"
        await s.execute(
            insert(Event)
            .values(
                id=ev.id,
                ts=ev.ts,
                ts_ingest=now,
                type=ev.type.value,
                instance_id=ev.instance_id,
                seq=ev.seq,
                correlation_id=ev.correlation_id,
                schema_version=ev.schema_version,
                payload=ev.payload.model_dump(mode="json"),
            )
            .on_conflict_do_nothing()
        )
        if ev.type in _ORDER_STATUS:
            await _track_order(s, ev)
    return Ingested(new=True, anomaly=anomaly)


async def _track_order(s: AsyncSession, ev: CanonicalEvent) -> None:
    p = ev.payload
    if not isinstance(p, OrderPayload):  # PAYLOAD_MODELS l'exclut pour ces quatre types
        return
    status = _ORDER_STATUS[ev.type]
    order = await s.scalar(select(Order).where(Order.client_order_id == str(p.client_order_id)))
    if order is None:
        s.add(
            Order(
                instance_id=ev.instance_id,
                client_order_id=str(p.client_order_id),
                instrument=p.symbol,
                side=p.side,
                intent=p.intent,
                status=status,
                quantity=p.qty,
                price=p.price,
                currency=p.currency,
                decision_id=p.decision_id,
                observed_at=ev.ts,
            )
        )
    elif _RANK[status] > _RANK[order.status]:
        order.status = status
        order.observed_at = ev.ts
