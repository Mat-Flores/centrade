"""Trading : ordres, positions et trades en lecture ; fermeture et annulation d'entrée en commande.

Aucune route ne crée d'ordre ni n'annule une sortie ou un stop (SPEC §8) : annuler une sortie
augmente le risque, la plateforme ne le propose pas. Fermer et annuler une entrée réduisent le
risque : commandes sans 2FA, jamais refusées pour un état observé inconnu ou périmé (I4).
Argent et quantités en chaînes décimales, avec la devise ; chaque ligne porte le mode voulu et le
mode observé (daté) de son instance pour que l'interface ne mélange jamais paper et live (§9).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID

from centrade_core.engine.types import EXIT_CAUSES
from centrade_core.models.trading import Account, Instance, Order, Position, Trade
from centrade_core.settings import Settings
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import Select, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_api.instances import (
    Bus,
    Cfg,
    Db,
    IdempotencyKey,
    Limit,
    Now,
    Operator,
    Viewer,
    _page_args,
    request_command,
)
from centrade_api.schemas import (
    CommandAccepted,
    CommandOut,
    Observed,
    ObservedMode,
    Page,
    encode_cursor,
    observe,
)

router = APIRouter(prefix="/api/v1", tags=["trading"])

ENTRY_INTENTS = frozenset({"entry"})  # seul ordre annulable : les renforts sont désactivés en V1
Mode = Literal["paper", "live"]


def _dec(d: Decimal) -> str:
    return format(d.normalize(), "f")


def _opt(d: Decimal | None) -> str | None:
    return None if d is None else _dec(d)


def _stale(at: datetime, now: datetime, cfg: Settings) -> bool:
    return (now - at).total_seconds() > cfg.observed_stale_after_s


class _Owned(BaseModel):
    """Ce que toute ligne dit de son instance : modes et compte (None : instance sans compte)."""

    instance_id: UUID
    mode: Mode  # = desired_mode, gardé pour les clients existants
    desired_mode: Mode  # voulu
    observed_mode: Observed[ObservedMode]  # observé, daté ; « unknown » si jamais observé
    account_id: UUID | None
    account_label: str | None


class OrderOut(_Owned):
    id: UUID
    client_order_id: str  # identifiant côté moteur
    instrument: str
    side: str
    intent: str  # entry | increase | exit | stop
    status: str
    quantity: str
    price: str | None
    currency: str
    decision_id: UUID | None
    observed_at: AwareDatetime
    stale: bool
    cancelable: bool  # ordre d'entrée encore ouvert : seul cas où l'annulation est proposée
    created_at: AwareDatetime


class PositionOut(_Owned):
    id: UUID
    instrument: str
    side: str
    quantity: str
    entry_price: str | None
    currency: str
    observed_at: AwareDatetime
    stale: bool
    stop_price: str | None
    stop_venue: str | None  # venue | engine
    stop_type: str | None  # fixed | trailing | dynamic
    # Écart entre le stop et le prix d'entrée, en % du prix d'entrée (pas de cours courant en
    # base) : positif = le stop limite une perte, négatif = il garantit déjà un gain.
    stop_distance_pct: str | None
    protection_state: str  # protected | engine_only | unprotected | unknown
    protection_verified_at: AwareDatetime | None


class TradeOut(_Owned):
    id: UUID
    instrument: str
    quantity: str
    entry_price: str
    exit_price: str
    entry_cause: str
    exit_cause: str  # une valeur de EXIT_CAUSES
    pnl: str
    fees: str
    currency: str
    opened_at: AwareDatetime
    closed_at: AwareDatetime
    duration_s: int


Owner = dict[str, Any]  # mode, account_id, account_label d'une ligne (voir `_owner`)


def _owner(row: Any, now: datetime, cfg: Settings) -> Owner:
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


# Modèle -> (constructeur, colonne de tri). Les identifiants sont des UUID v7 : leur ordre suit
# la création, ce qui donne aux positions (sans date de création) un curseur stable.
_KINDS: dict[str, tuple[Any, Any, Any]] = {
    "order": (Order, order_of, Order.created_at),
    "position": (Position, position_of, Position.id),
    "trade": (Trade, trade_of, Trade.closed_at),
}


def _select(kind: str) -> Select[Any]:
    model = _KINDS[kind][0]
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
    model, build, _ = _KINDS[kind]
    row = (await db.execute(_select(kind).where(model.id == ident))).one_or_none()
    return None if row is None else build(row[0], _owner(row, now, cfg), now, cfg)


async def _page(
    db: AsyncSession,
    kind: str,
    now: datetime,
    cfg: Settings,
    instance_id: UUID | None,
    account_id: UUID | None,
    cursor: str | None,
    limit: int,
) -> Page[Any]:
    model, build, order = _KINDS[kind]
    stmt = _select(kind)
    if instance_id is not None:
        stmt = stmt.where(model.instance_id == instance_id)
    if account_id is not None:
        stmt = stmt.where(Instance.account_id == account_id)
    if (at := _page_args(cursor)) is not None:
        key = tuple_(order, model.id) if kind != "position" else model.id
        stmt = stmt.where(key < (tuple_(*at) if kind != "position" else at[1]))
    rows = (await db.execute(stmt.order_by(order.desc(), model.id.desc()).limit(limit + 1))).all()
    page = rows[:limit]
    nxt = None
    if len(rows) > limit:
        last = page[-1][0]
        head = now if kind == "position" else getattr(last, order.key)
        nxt = encode_cursor(head, last.id)
    return Page(
        items=[build(r[0], _owner(r, now, cfg), now, cfg) for r in page],
        next_cursor=nxt,
        server_time=now,
    )


@router.get("/orders")
async def list_orders(
    _: Viewer,
    db: Db,
    now: Now,
    cfg: Cfg,
    instance_id: UUID | None = None,
    account_id: UUID | None = None,
    cursor: str | None = None,
    limit: Limit = 50,
) -> Page[OrderOut]:
    return await _page(db, "order", now, cfg, instance_id, account_id, cursor, limit)


@router.get("/positions")
async def list_positions(
    _: Viewer,
    db: Db,
    now: Now,
    cfg: Cfg,
    instance_id: UUID | None = None,
    account_id: UUID | None = None,
    cursor: str | None = None,
    limit: Limit = 50,
) -> Page[PositionOut]:
    return await _page(db, "position", now, cfg, instance_id, account_id, cursor, limit)


@router.get("/trades")
async def list_trades(
    _: Viewer,
    db: Db,
    now: Now,
    cfg: Cfg,
    instance_id: UUID | None = None,
    account_id: UUID | None = None,
    cursor: str | None = None,
    limit: Limit = 50,
) -> Page[TradeOut]:
    return await _page(db, "trade", now, cfg, instance_id, account_id, cursor, limit)


async def _accepted(
    db: Db,
    redis: Bus,
    request: Request,
    response: Response,
    user: Operator,
    instance_id: UUID,
    type_: str,
    key: str,
    now: datetime,
    cfg: Settings,
    args: dict[str, Any],
) -> CommandAccepted:
    cmd, replayed = await request_command(
        db, redis, request, user, instance_id, type_, key, now, cfg, args
    )
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    response.headers["Location"] = f"/api/v1/commands/{cmd.id}"
    return CommandAccepted(command_id=cmd.id, command=CommandOut.of(cmd, now))


@router.post("/positions/{position_id}/close", status_code=202)
async def close_position(
    position_id: UUID,
    request: Request,
    response: Response,
    user: Operator,
    db: Db,
    now: Now,
    cfg: Cfg,
    redis: Bus,
    idempotency_key: IdempotencyKey,
) -> CommandAccepted:
    pos = await db.get(Position, position_id)
    if pos is None:
        raise HTTPException(404, "Position inconnue.")
    return await _accepted(
        db, redis, request, response, user, pos.instance_id, "close_position",
        idempotency_key, now, cfg, {"position_id": pos.external_id},
    )  # fmt: skip


@router.delete("/orders/{order_id}", status_code=202)
async def cancel_order(
    order_id: UUID,
    request: Request,
    response: Response,
    user: Operator,
    db: Db,
    now: Now,
    cfg: Cfg,
    redis: Bus,
    idempotency_key: IdempotencyKey,
) -> CommandAccepted:
    order = await db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Ordre inconnu.")
    if order.intent not in ENTRY_INTENTS:
        raise HTTPException(
            409,
            "Seul un ordre d'entrée s'annule : annuler une sortie ou un stop augmente le risque.",
        )
    if order.status != "open":
        raise HTTPException(409, "Cet ordre n'est plus ouvert.")
    return await _accepted(
        db, redis, request, response, user, order.instance_id, "cancel_entry_order",
        idempotency_key, now, cfg, {"order_id": order.client_order_id},
    )  # fmt: skip
