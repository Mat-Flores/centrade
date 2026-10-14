"""Mapping of database rows onto the output schemas: orders, positions, trades."""

from __future__ import annotations

from datetime import datetime
from decimal import Context, Decimal
from typing import Any, cast
from uuid import UUID

from centrade_core.engine.types import EXIT_CAUSES
from centrade_core.models.trading import Account, Instance, Order, Position, Trade
from centrade_core.settings import Settings
from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_api.core.observed import ObservedMode, observe
from centrade_api.trading.schemas import OrderOut, PositionOut, TradeOut

ENTRY_INTENTS = frozenset({"entry"})  # only cancellable order: reinforcements are disabled in V1


def _dec(d: Decimal) -> str:
    # normalize() rounds to the context precision (28 digits): give it every digit of `d`.
    return format(d.normalize(Context(prec=max(1, len(d.as_tuple().digits)))), "f")


def _opt(d: Decimal | None) -> str | None:
    return None if d is None else _dec(d)


def _stale(at: datetime, now: datetime, cfg: Settings) -> bool:
    return (now - at).total_seconds() > cfg.observed_stale_after_s


Owner = dict[str, Any]  # mode, account_id, account_label of a row (see `_owner`)


def owner_of(row: Any, now: datetime, cfg: Settings) -> Owner:
    seen = row[4] if row[4] and row[5] else "unknown"
    return {
        "mode": row[1],
        "desired_mode": row[1],
        "observed_mode": observe(cast(ObservedMode, seen), row[5], now, cfg.observed_stale_after_s),
        "account_id": row[2],
        "account_label": row[3],
    }


def order_of(o: Order, own: Owner, now: datetime, cfg: Settings) -> OrderOut:
    return OrderOut(
        id=o.id,
        instance_id=o.instance_id,
        **own,
        client_order_id=o.client_order_id,
        instrument=o.instrument,
        side=o.side,
        intent=o.intent,
        status=o.status,
        quantity=_dec(o.quantity),
        price=_opt(o.price),
        currency=o.currency,
        decision_id=o.decision_id,
        observed_at=o.observed_at,
        stale=_stale(o.observed_at, now, cfg),
        cancelable=o.intent in ENTRY_INTENTS and o.status == "open",
        created_at=o.created_at,
    )


def stop_distance_pct(p: Position) -> Decimal | None:
    if p.stop_price is None or not p.entry_price:
        return None
    gap = p.entry_price - p.stop_price if p.side == "long" else p.stop_price - p.entry_price
    return (gap / p.entry_price * 100).quantize(Decimal("0.0001"))


def position_of(p: Position, own: Owner, now: datetime, cfg: Settings) -> PositionOut:
    return PositionOut(
        id=p.id,
        instance_id=p.instance_id,
        **own,
        instrument=p.instrument,
        side=p.side,
        quantity=_dec(p.quantity),
        entry_price=_opt(p.entry_price),
        currency=p.currency,
        observed_at=p.observed_at,
        stale=_stale(p.observed_at, now, cfg),
        stop_price=_opt(p.stop_price),
        stop_venue=p.stop_venue,
        stop_type=p.stop_type,
        stop_distance_pct=_opt(stop_distance_pct(p)),
        protection_state=p.protection_state,
        protection_verified_at=p.protection_verified_at,
    )


def trade_of(t: Trade, own: Owner, now: datetime, cfg: Settings) -> TradeOut:
    cause = t.exit_cause if t.exit_cause in EXIT_CAUSES else "unknown"
    return TradeOut(
        id=t.id,
        instance_id=t.instance_id,
        **own,
        instrument=t.instrument,
        quantity=_dec(t.quantity),
        entry_price=_dec(t.entry_price),
        exit_price=_dec(t.exit_price),
        entry_cause=t.entry_cause,
        exit_cause=cause,
        pnl=_dec(t.pnl),
        fees=_dec(t.fees),
        currency=t.currency,
        opened_at=t.opened_at,
        closed_at=t.closed_at,
        duration_s=t.duration_s,
    )


# Model -> (constructor, sort column). Identifiers are UUID v7: their order follows
# creation, which gives positions (with no creation date) a stable cursor.
KINDS: dict[str, tuple[Any, Any, Any]] = {
    "order": (Order, order_of, Order.created_at),
    "position": (Position, position_of, Position.id),
    "trade": (Trade, trade_of, Trade.closed_at),
}


def select_kind(kind: str) -> Select[Any]:
    model = KINDS[kind][0]
    return (
        select(
            model,
            Instance.mode,
            Instance.account_id,
            Account.label,
            Instance.observed_mode,
            Instance.observed_at,
        )
        .join(Instance, Instance.id == model.instance_id)
        .outerjoin(Account, Account.id == Instance.account_id)
    )


async def trading_out(
    db: AsyncSession, kind: str, ident: UUID, now: datetime, cfg: Settings
) -> BaseModel | None:
    model, build, _ = KINDS[kind]
    row = (await db.execute(select_kind(kind).where(model.id == ident))).one_or_none()
    return None if row is None else build(row[0], owner_of(row, now, cfg), now, cfg)
