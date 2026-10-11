"""Dépendances communes des routes : session de base, heure, adresse du client."""

import ipaddress
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


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
