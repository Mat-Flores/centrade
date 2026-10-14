"""Brakes on login attempts (SPEC §13).

Rate per address, then progressive account lockout after repeated failures.
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
    """Progressive lockout: 1, 2, 4, 8 then 15 min from the 5th consecutive failure."""
    if failed_attempts < LOCK_THRESHOLD:
        return None
    # Bounded exponent: a very large counter must neither overflow nor lock forever.
    return min(LOCK_BASE * (1 << min(failed_attempts - LOCK_THRESHOLD, 4)), LOCK_MAX)


class RateLimiter:
    """Fixed window per key, in memory."""

    # shortcut: counters are local to this process and lost on restart; move them to
    # Redis as soon as the API runs in several processes.
    MAX_KEYS = 10_000

    def __init__(self, limit: int, window: timedelta) -> None:
        self._limit, self._window = limit, window
        self._hits: dict[str, tuple[datetime, int]] = {}

    def retry_after(self, key: str, now: datetime) -> int | None:
        """Counts an attempt. Returns None if it passes, otherwise the seconds to wait."""
        start, count = self._hits.get(key, (now, 0))
        if now - start >= self._window:
            start, count = now, 0
        if count >= self._limit:
            return math.ceil((start + self._window - now).total_seconds())
        if key not in self._hits and len(self._hits) >= self.MAX_KEYS:
            self._hits = {k: v for k, v in self._hits.items() if now - v[0] < self._window}
            if len(self._hits) >= self.MAX_KEYS:  # full of active keys: refuse, do not forget
                return math.ceil(self._window.total_seconds())
        self._hits[key] = (start, count + 1)
        return None

    def size(self) -> int:
        return len(self._hits)

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter(limit=10, window=timedelta(minutes=1))


def throttle(request: Request, now: Annotated[datetime, Depends(utcnow)]) -> None:
    """Rate per address, before any read of the body, the database or hash computation."""
    ip = client_ip(request)
    if (wait := limiter.retry_after(ip or "unknown", now)) is not None:
        log.warning("auth_rate_limited", ip=ip)
        raise HTTPException(
            429, "Trop de tentatives. Réessayez plus tard.", headers={"Retry-After": str(wait)}
        )
