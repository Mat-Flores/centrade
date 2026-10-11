from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from centrade_core.db import make_engine, make_session_factory
from centrade_core.settings import get_settings
from fastapi import Depends, FastAPI
from pydantic import AwareDatetime, BaseModel
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from centrade_api.auth import require_same_origin
from centrade_api.auth import router as auth_router
from centrade_api.errors import install_error_handlers
from centrade_api.logging import configure_logging

configure_logging()
log = structlog.get_logger()


class Health(BaseModel):
    status: str
    ts: AwareDatetime


class NoStore:
    """`Cache-Control: no-store` sur toute réponse : ni session ni état observé dans un cache.

    Seul en-tête de sécurité posé ici ; HSTS, CSP, nosniff, Referrer-Policy et X-Frame-Options
    le sont par Caddy (deploy/caddy/Caddyfile). ASGI pur : compatible avec le SSE.
    Source : https://www.starlette.io/middleware/#pure-asgi-middleware
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.master_key()  # clé absente ou invalide : l'API ne démarre pas
    engine = make_engine(settings.database_url())
    app.state.session_factory = make_session_factory(engine)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    # Pas de Swagger ni de ReDoc : ils chargent des scripts tiers, interdits par la CSP (SPEC §9).
    app = FastAPI(
        title="Centrade API",
        version="0.0.0",
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        # CSRF sur toutes les routes, présentes et à venir (SPEC §13).
        dependencies=[Depends(require_same_origin)],
    )
    install_error_handlers(app)
    app.add_middleware(NoStore)
    app.include_router(auth_router)

    @app.get("/api/v1/system/health")
    async def health() -> Health:
        """Vivacité du processus API uniquement (ni Postgres ni Redis, I1)."""
        log.debug("health_checked")  # sondé toutes les 5 s : pas au niveau INFO
        return Health(status="ok", ts=datetime.now(UTC))

    return app


app = create_app()
