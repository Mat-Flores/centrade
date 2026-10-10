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


app = FastAPI(title="Centrade API", version="0.0.0")
install_error_handlers(app)


@app.get("/api/v1/system/health")
async def health() -> Health:
    """Vivacité du processus API uniquement (ni Postgres ni Redis, I1)."""
    log.info("health_checked")
    return Health(status="ok", ts=datetime.now(UTC))
