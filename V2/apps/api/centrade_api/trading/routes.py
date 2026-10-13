"""Trading : ordres, positions et trades en lecture ; fermeture et annulation d'entrée en commande.

Aucune route ne crée d'ordre ni n'annule une sortie ou un stop (SPEC §8) : annuler une sortie
augmente le risque, la plateforme ne le propose pas. Fermer et annuler une entrée réduisent le
risque : commandes sans 2FA, jamais refusées pour un état observé inconnu ou périmé (I4).
Argent et quantités en chaînes décimales, avec la devise ; chaque ligne porte le mode voulu et le
mode observé (daté) de son instance pour que l'interface ne mélange jamais paper et live (§9).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from centrade_core.models.trading import Instance, Order, Position
from centrade_core.settings import Settings
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_api.auth import Operator, Viewer
from centrade_api.core.deps import (
    Bus,
    Cfg,
    Db,
    IdempotencyKey,
    Limit,
    Now,
)
from centrade_api.core.pagination import Page, encode_cursor, page_args
from centrade_api.instances.commands import request_command
from centrade_api.instances.schemas import (
    CommandAccepted,
    CommandOut,
)
from centrade_api.trading.projections import ENTRY_INTENTS, KINDS, owner_of, select_kind
from centrade_api.trading.schemas import OrderOut, PositionOut, TradeOut

router = APIRouter(prefix="/api/v1", tags=["trading"])


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
    model, build, order = KINDS[kind]
    stmt = select_kind(kind)
    if instance_id is not None:
        stmt = stmt.where(model.instance_id == instance_id)
    if account_id is not None:
        stmt = stmt.where(Instance.account_id == account_id)
    if (at := page_args(cursor)) is not None:
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
        items=[build(r[0], owner_of(r, now, cfg), now, cfg) for r in page],
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
