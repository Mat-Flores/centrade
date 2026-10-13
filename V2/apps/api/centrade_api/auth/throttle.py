"""Freins aux tentatives de connexion (SPEC §13).

Débit par adresse, puis verrouillage progressif du compte après des échecs répétés.
"""

import math
from datetime import datetime, timedelta
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request

from centrade_api.core.deps import client_ip, utcnow

log = structlog.get_logger()

LOCK_THRESHOLD = 5
LOCK_BASE = timedelta(minutes=1)
LOCK_MAX = timedelta(minutes=15)


def lock_duration(failed_attempts: int) -> timedelta | None:
    """Verrouillage progressif : 1, 2, 4, 8 puis 15 min à partir du 5e échec consécutif."""
    if failed_attempts < LOCK_THRESHOLD:
        return None
    # Exposant borné : un compteur très grand ne doit ni déborder ni verrouiller sans fin.
    return min(LOCK_BASE * (1 << min(failed_attempts - LOCK_THRESHOLD, 4)), LOCK_MAX)


class RateLimiter:
    """Fenêtre fixe par clé, en mémoire."""

    # shortcut: compteurs propres à ce processus et perdus au redémarrage ; les passer dans
    # Redis dès que l'API tourne en plusieurs processus.
    MAX_KEYS = 10_000

    def __init__(self, limit: int, window: timedelta) -> None:
        self._limit, self._window = limit, window
        self._hits: dict[str, tuple[datetime, int]] = {}

    def retry_after(self, key: str, now: datetime) -> int | None:
        """Compte une tentative. Renvoie None si elle passe, sinon les secondes à attendre."""
        start, count = self._hits.get(key, (now, 0))
        if now - start >= self._window:
            start, count = now, 0
        if count >= self._limit:
            return math.ceil((start + self._window - now).total_seconds())
        if key not in self._hits and len(self._hits) >= self.MAX_KEYS:
            self._hits = {k: v for k, v in self._hits.items() if now - v[0] < self._window}
            if len(self._hits) >= self.MAX_KEYS:  # saturé de clés actives : refus plutôt qu'oubli
                return math.ceil(self._window.total_seconds())
        self._hits[key] = (start, count + 1)
        return None

    def size(self) -> int:
        return len(self._hits)

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter(limit=10, window=timedelta(minutes=1))


def throttle(request: Request, now: Annotated[datetime, Depends(utcnow)]) -> None:
    """Débit par adresse, avant toute lecture du corps, de la base ou calcul d'empreinte."""
    ip = client_ip(request)
    if (wait := limiter.retry_after(ip or "unknown", now)) is not None:
        log.warning("auth_rate_limited", ip=ip)
        raise HTTPException(
            429, "Trop de tentatives. Réessayez plus tard.", headers={"Retry-After": str(wait)}
        )
