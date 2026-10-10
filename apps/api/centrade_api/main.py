from datetime import UTC, datetime

import structlog
from fastapi import FastAPI
from pydantic import AwareDatetime, BaseModel

from centrade_api.errors import install_error_handlers
from centrade_api.logging import configure_logging

configure_logging()
log = structlog.get_logger()


class Health(BaseModel):
    status: str
    ts: AwareDatetime


# Pas de Swagger ni de ReDoc : ils chargent des scripts tiers, interdits par la CSP (SPEC §9).
app = FastAPI(
    title="Centrade API",
    version="0.0.0",
    openapi_url="/api/v1/openapi.json",
    docs_url=None,
    redoc_url=None,
)
install_error_handlers(app)


@app.get("/api/v1/system/health")
async def health() -> Health:
    """Vivacité du processus API uniquement (ni Postgres ni Redis, I1)."""
    log.debug("health_checked")  # sondé toutes les 5 s : pas au niveau INFO
    return Health(status="ok", ts=datetime.now(UTC))
