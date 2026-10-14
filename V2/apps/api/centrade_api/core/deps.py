"""Common route dependencies: database session, time, client address, bus, settings.

The `Annotated` aliases at the bottom of the file are how to request them in a route. No import
of `auth` here: `auth` depends on this module, not the other way round.
"""

import ipaddress
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from centrade_core.settings import Settings, get_settings
from fastapi import Depends, Header, Query, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request; each unit of work commits (`commit`) itself."""
    async with request.app.state.session_factory() as session:
        yield session


def utcnow() -> datetime:
    """Request time, injected so that expiry tests do not have to wait."""
    return datetime.now(UTC)


def client_ip(request: Request) -> str | None:
    """Client address as the ASGI server reports it, or None if it is not one.

    Behind Caddy, this is the proxy address as long as uvicorn does not trust it
    (`--forwarded-allow-ips`): we never read `X-Forwarded-For` ourselves, a client forges it.
    """
    if request.client is None:
        return None
    try:
        return str(ipaddress.ip_address(request.client.host))
    except ValueError:
        return None


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession] | None:
    """Process-wide session factory (None if the lifespan did not run)."""
    return getattr(request.app.state, "session_factory", None)


def get_redis(request: Request) -> Redis | None:
    return getattr(request.app.state, "redis", None)


Db = Annotated[AsyncSession, Depends(get_db)]
Now = Annotated[datetime, Depends(utcnow)]
Cfg = Annotated[Settings, Depends(get_settings)]
Bus = Annotated[Redis | None, Depends(get_redis)]
Limit = Annotated[int, Query(ge=1, le=200)]  # out of bounds or not an integer: 422
_KEY = Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
IdempotencyKey = Annotated[str, _KEY]
OptionalKey = Annotated[str | None, _KEY]  # creation: the key is optional (M1 compatibility)
