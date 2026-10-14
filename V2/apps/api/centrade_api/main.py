import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Annotated, Literal

import structlog
from centrade_core.bus import HEARTBEAT_KEY
from centrade_core.db import make_engine, make_session_factory
from centrade_core.settings import Settings, get_settings
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import AwareDatetime, BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from centrade_api.accounts.routes import router as accounts_router
from centrade_api.auth import require_same_origin
from centrade_api.auth import router as auth_router
from centrade_api.core.deps import get_redis, get_session_factory, utcnow
from centrade_api.core.errors import install_error_handlers
from centrade_api.core.logging import configure_logging
from centrade_api.feeds.routes import router as feeds_router
from centrade_api.instances.routes import router as instances_router
from centrade_api.strategies.routes import router as strategies_router
from centrade_api.stream.routes import router as stream_router
from centrade_api.trading.routes import router as trading_router

configure_logging()
log = structlog.get_logger()


class Check(BaseModel):
    status: Literal["ok", "down"]
    observed_at: AwareDatetime  # every announced state is observed and dated (I1)
    detail: str | None = None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    ts: AwareDatetime
    checks: dict[str, Check]


class NoStore:
    """`Cache-Control: no-store` on every response: neither session nor observed state in a cache.

    Only security header set here; HSTS, CSP, nosniff, Referrer-Policy and X-Frame-Options
    are set by Caddy (deploy/caddy/Caddyfile). Pure ASGI: compatible with SSE.
    Source: https://www.starlette.io/middleware/#pure-asgi-middleware
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_no_store)


MAX_BODY_BYTES = 64 * 1024  # all routes receive small JSON bodies


class BodyLimit:
    """Bounds the request body: beyond it, 413, without reading it whole or parsing it.

    Counts what actually arrives (a `Content-Length` is declared, a chunked upload has none).
    The exception bubbles up from the body read to the error handler.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        seen = 0

        async def bounded() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > MAX_BODY_BYTES:
                    raise HTTPException(413, "Corps de requête trop volumineux.")
            return message

        await self.app(scope, bounded if scope["type"] == "http" else receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.master_key()  # missing or invalid key: the API does not start
    engine = make_engine(settings.database_url())
    app.state.session_factory = make_session_factory(engine)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    # No Swagger or ReDoc: they load third-party scripts, forbidden by the CSP (SPEC §9).
    app = FastAPI(
        title="Centrade API",
        version="0.0.0",
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        # CSRF on all routes, present and future (SPEC §13).
        dependencies=[Depends(require_same_origin)],
    )
    install_error_handlers(app)
    app.add_middleware(NoStore)
    app.add_middleware(BodyLimit)
    app.include_router(auth_router)
    app.include_router(instances_router)
    app.include_router(accounts_router)
    app.include_router(feeds_router)
    app.include_router(stream_router)
    app.include_router(strategies_router)
    app.include_router(trading_router)

    @app.get("/api/v1/system/health")
    async def health(
        now: Annotated[datetime, Depends(utcnow)],
        factory: Annotated[async_sessionmaker[AsyncSession] | None, Depends(get_session_factory)],
        redis: Annotated[Redis | None, Depends(get_redis)],
        request: Request,
    ) -> Health:
        """No session. Database, bus and worker heartbeat: each observed and dated (I1).
        Always 200: a failed component yields `degraded`, it does not restart the API."""

        async def probe(name: str, check: Callable[[], Awaitable[str | None]]) -> Check:
            try:
                async with asyncio.timeout(2):
                    detail = await check()
                return Check(status="ok", observed_at=now, detail=detail)
            except Exception as exc:  # failure of any kind: component "down"
                log.warning("health_component_down", component=name, error=type(exc).__name__)
                return Check(status="down", observed_at=now)

        async def database() -> str | None:
            if factory is None:
                raise RuntimeError("database not configured")
            async with factory() as s:
                await s.execute(text("SELECT 1"))
            return None

        async def bus() -> str | None:
            if redis is None:
                raise RuntimeError("bus not configured")
            await redis.ping()
            return None

        async def worker() -> str | None:
            if redis is None:
                raise RuntimeError("bus not configured")
            raw = await redis.get(HEARTBEAT_KEY)  # the key expires if the worker goes quiet
            if raw is None:
                raise RuntimeError("heartbeat missing")
            beat = str(raw)
            cfg: Settings = request.app.dependency_overrides.get(get_settings, get_settings)()
            age = now - datetime.fromisoformat(beat)
            if age > timedelta(seconds=cfg.worker_heartbeat_ttl_s):
                raise RuntimeError("heartbeat too old")
            return beat

        checks = {
            "database": await probe("database", database),
            "bus": await probe("bus", bus),
            "worker": await probe("worker", worker),
        }
        ok = all(c.status == "ok" for c in checks.values())
        return Health(status="ok" if ok else "degraded", ts=now, checks=checks)

    return app


app = create_app()
