"""Read-only logs: events, alerts, audit. Cursor pagination, most recent first."""

from uuid import UUID

from centrade_core.models import AuditLog
from centrade_core.models.trading import Alert, Event
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, tuple_

from centrade_api.auth import Viewer, require_role
from centrade_api.core.deps import (
    Db,
    Limit,
    Now,
)
from centrade_api.core.pagination import Page, decode_cursor, encode_cursor, page_args
from centrade_api.feeds.schemas import AlertOut, AuditOut, EventOut

router = APIRouter(prefix="/api/v1", tags=["feeds"])


@router.get("/events")
async def list_events(
    _: Viewer,
    db: Db,
    now: Now,
    instance_id: UUID | None = None,
    type: str | None = None,
    cursor: str | None = None,
    limit: Limit = 50,
) -> Page[EventOut]:
    stmt = select(Event)
    if instance_id is not None:
        stmt = stmt.where(Event.instance_id == instance_id)
    if type is not None:
        stmt = stmt.where(Event.type == type)
    if (at := page_args(cursor)) is not None:
        stmt = stmt.where(tuple_(Event.ts, Event.id) < tuple_(*at))
    rows = (
        await db.scalars(stmt.order_by(Event.ts.desc(), Event.id.desc()).limit(limit + 1))
    ).all()
    page = rows[:limit]
    nxt = encode_cursor(page[-1].ts, page[-1].id) if len(rows) > limit else None
    return Page(items=[EventOut.of(e) for e in page], next_cursor=nxt, server_time=now)


@router.get("/alerts")
async def list_alerts(
    _: Viewer,
    db: Db,
    now: Now,
    instance_id: UUID | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: Limit = 50,
) -> Page[AlertOut]:
    stmt = select(Alert)
    if instance_id is not None:
        stmt = stmt.where(Alert.target_id == instance_id)
    if status is not None:
        stmt = stmt.where(Alert.status == status)
    if (at := page_args(cursor)) is not None:
        stmt = stmt.where(tuple_(Alert.created_at, Alert.id) < tuple_(*at))
    rows = (
        await db.scalars(stmt.order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit + 1))
    ).all()
    page = rows[:limit]
    nxt = encode_cursor(page[-1].created_at, page[-1].id) if len(rows) > limit else None
    return Page(items=[AlertOut.of(a) for a in page], next_cursor=nxt, server_time=now)


@router.get("/audit", dependencies=[Depends(require_role("admin"))])
async def list_audit(
    db: Db, now: Now, cursor: str | None = None, limit: Limit = 50
) -> Page[AuditOut]:
    stmt = select(AuditLog)
    if cursor is not None:
        head, _ = decode_cursor(cursor)
        try:
            stmt = stmt.where(AuditLog.seq < int(head))
        except ValueError:
            raise HTTPException(422, "Curseur invalide.") from None
    rows = (await db.scalars(stmt.order_by(AuditLog.seq.desc()).limit(limit + 1))).all()
    page = rows[:limit]
    nxt = encode_cursor(page[-1].seq) if len(rows) > limit else None
    items = [AuditOut.model_validate(r, from_attributes=True) for r in page]
    return Page(items=items, next_cursor=nxt, server_time=now)
