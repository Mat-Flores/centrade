"""Dépendances communes des routes : session de base, heure, adresse du client, bus, réglages.

Les alias `Annotated` en bas de fichier sont la façon de les demander dans une route. Aucun import
de `auth` ici : c'est `auth` qui dépend de ce module, pas l'inverse.
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
    """Une session par requête ; chaque unité de travail valide (`commit`) elle-même."""
    async with request.app.state.session_factory() as session:
        yield session


def utcnow() -> datetime:
    """Heure de la requête, injectée pour que les tests d'expiration n'attendent pas."""
    return datetime.now(UTC)


def client_ip(request: Request) -> str | None:
    """Adresse du client telle que le serveur ASGI la rapporte, ou None si ce n'en est pas une.

    Derrière Caddy, c'est l'adresse du proxy tant qu'uvicorn ne lui fait pas confiance
    (`--forwarded-allow-ips`) : on ne lit jamais `X-Forwarded-For` soi-même, un client le forge.
    """
    if request.client is None:
        return None
    try:
        return str(ipaddress.ip_address(request.client.host))
    except ValueError:
        return None


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession] | None:
    """Fabrique de sessions du processus (None si le cycle de vie n'a pas tourné)."""
    return getattr(request.app.state, "session_factory", None)


def get_redis(request: Request) -> Redis | None:
    return getattr(request.app.state, "redis", None)


Db = Annotated[AsyncSession, Depends(get_db)]
Now = Annotated[datetime, Depends(utcnow)]
Cfg = Annotated[Settings, Depends(get_settings)]
Bus = Annotated[Redis | None, Depends(get_redis)]
Limit = Annotated[int, Query(ge=1, le=200)]  # hors bornes ou non entier : 422
_KEY = Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
IdempotencyKey = Annotated[str, _KEY]
OptionalKey = Annotated[str | None, _KEY]  # création : la clé est facultative (compatibilité M1)
