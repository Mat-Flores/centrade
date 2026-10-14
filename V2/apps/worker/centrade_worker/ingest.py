"""Idempotent ingestion: an already-seen event (same `id` or `(instance_id, seq)`) has no effect.

An event is only a hint (SPEC §7): it is kept and the order history is updated,
but positions and observed state come only from snapshots (see projection.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

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
# A late event never moves an order backwards; only a snapshot can correct it.
_RANK = {"open": 0, "unknown": 1, "filled": 2, "canceled": 2, "rejected": 2}


@dataclass(frozen=True)
class Ingested:
    new: bool
    anomaly: Anomaly | None
    order_id: UUID | None = None  # order row created or modified, to announce on the stream


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
        order_id = await _track_order(s, ev) if ev.type in _ORDER_STATUS else None
    return Ingested(new=True, anomaly=anomaly, order_id=order_id)


async def _track_order(s: AsyncSession, ev: CanonicalEvent) -> UUID | None:
    p = ev.payload
    if not isinstance(p, OrderPayload):  # PAYLOAD_MODELS excludes it for these four types
        return None
    status = _ORDER_STATUS[ev.type]
    order = await s.scalar(select(Order).where(Order.client_order_id == str(p.client_order_id)))
    if order is None:
        order = Order(
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
        s.add(order)
        await s.flush()  # the row identifier, for the announcement
    elif _RANK[status] > _RANK[order.status]:
        order.status = status
        order.observed_at = ev.ts
    else:
        return None
    return order.id
