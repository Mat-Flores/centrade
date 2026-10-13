"""Flux temps réel (SSE) : battement, puis `instance`, `command`, `alert`, `order`, `position`
et `trade` relayés depuis Redis.

Le worker et l'API publient sur `notify` seulement l'identité de ce qui a changé ; ce flux relit
la base et envoie l'objet complet. La session est revérifiée en lecture seule (le flux ne repousse
pas l'inactivité) : session expirée ou fermée => le flux se ferme.

Source : https://fastapi.tiangolo.com/tutorial/server-sent-events
"""

import json
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

import structlog
from centrade_core.bus import NOTIFY_CHANNEL
from centrade_core.models import Session
from centrade_core.models.trading import Alert, Command
from centrade_core.settings import Settings, get_settings
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from centrade_api.auth import Principal, require_role
from centrade_api.auth.deps import SESSION_IDLE
from centrade_api.core.deps import (
    get_redis,
    get_session_factory,
    utcnow,
)
from centrade_api.feeds.schemas import AlertOut
from centrade_api.instances.schemas import CommandOut
from centrade_api.instances.service import instance_out
from centrade_api.trading.projections import trading_out

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["stream"])


async def _session_alive(
    factory: async_sessionmaker[AsyncSession], session_id: UUID, now: datetime
) -> bool:
    async with factory() as s:
        found = await s.scalar(
            select(Session.id).where(
                Session.id == session_id,
                Session.stage == "full",
                Session.expires_at > now,
                Session.last_activity_at > now - SESSION_IDLE,
            )
        )
    return found is not None


async def _message(
    factory: async_sessionmaker[AsyncSession], cfg: Settings, kind: str, ident: UUID, now: datetime
) -> ServerSentEvent | None:
    async with factory() as s:
        payload: dict[str, object]
        if kind == "instance":
            inst = await instance_out(s, ident, now, cfg)
            payload = {} if inst is None else {"instance": inst.model_dump(mode="json")}
        elif kind == "command":
            cmd = await s.get(Command, ident)
            payload = (
                {} if cmd is None else {"command": CommandOut.of(cmd, now).model_dump(mode="json")}
            )
        elif kind == "alert":
            alert = await s.get(Alert, ident)
            payload = {} if alert is None else {"alert": AlertOut.of(alert).model_dump(mode="json")}
        elif kind in ("order", "position", "trade"):
            out = await trading_out(s, kind, ident, now, cfg)
            payload = {} if out is None else {kind: out.model_dump(mode="json")}
        else:
            return None
    if not payload:
        return None
    return ServerSentEvent(data={"server_time": now.isoformat(), **payload}, event=kind)


async def stream_messages(
    *,
    factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    session_id: UUID,
    now: Callable[[], datetime],
    cfg: Settings,
) -> AsyncGenerator[ServerSentEvent]:
    pubsub = redis.pubsub()
    await pubsub.subscribe(NOTIFY_CHANNEL)
    try:
        last_beat = last_check = time.monotonic()
        yield ServerSentEvent(data={"server_time": now().isoformat()}, event="heartbeat")
        while True:
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=cfg.stream_heartbeat_s
            )
            mono = time.monotonic()
            if mono - last_check >= cfg.stream_session_check_s:
                last_check = mono
                if not await _session_alive(factory, session_id, now()):
                    return
            if msg is not None:
                try:
                    note = json.loads(msg["data"])
                    event = await _message(factory, cfg, note["kind"], UUID(note["id"]), now())
                except (ValueError, KeyError, TypeError):
                    log.warning("notification_unreadable")
                    event = None
                if event is not None:
                    yield event
            if mono - last_beat >= cfg.stream_heartbeat_s:
                last_beat = mono
                yield ServerSentEvent(data={"server_time": now().isoformat()}, event="heartbeat")
    finally:
        await pubsub.unsubscribe(NOTIFY_CHANNEL)
        await pubsub.aclose()  # type: ignore[no-untyped-call]


@router.get("/stream", response_class=EventSourceResponse)
async def stream(
    user: Annotated[Principal, Depends(require_role("viewer"))],
    factory: Annotated[async_sessionmaker[AsyncSession] | None, Depends(get_session_factory)],
    redis: Annotated[Redis | None, Depends(get_redis)],
    request: Request,
    cfg: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[ServerSentEvent]:
    if factory is None or redis is None:
        raise HTTPException(503, "Flux indisponible.")
    now: Callable[[], datetime] = request.app.dependency_overrides.get(utcnow, utcnow)
    async for ev in stream_messages(
        factory=factory, redis=redis, session_id=user.session_id, now=now, cfg=cfg
    ):
        yield ev
