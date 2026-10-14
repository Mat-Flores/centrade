"""Session, roles and CSRF: the dependencies every protected route uses.

Refuse by default: missing cookie, unknown, expired or wrong-stage session, database
error => no access. The durations are constants: no configuration value disables them.

Sources: https://fastapi.tiangolo.com/tutorial/dependencies/ ,
https://fastapi.tiangolo.com/advanced/response-cookies/ ,
https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

import structlog
from centrade_core.models import Session, User
from centrade_core.settings import Settings, get_settings
from fastapi import Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_api.auth.security import token_hash
from centrade_api.core.deps import get_db, utcnow

log = structlog.get_logger()

# `__Host-`: the browser accepts the cookie only if `Secure`, `Path=/` and without `Domain`.
SESSION_COOKIE = "__Host-centrade_session"
PRE_SESSION_COOKIE = "__Host-centrade_pre"

SESSION_ABSOLUTE = timedelta(hours=12)
SESSION_IDLE = timedelta(minutes=30)
PRE_SESSION_TTL = timedelta(minutes=5)
RECENT_TOTP = timedelta(minutes=5)

Role = Literal["viewer", "operator", "admin"]
_RANK: dict[str, int] = {"viewer": 0, "operator": 1, "admin": 2}  # SPEC §13 "Roles"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True, slots=True)
class Principal:
    """The user of a full session. Carries no hash and no secret."""

    user_id: UUID
    email: str
    role: str
    session_id: UUID
    totp_verified_at: datetime | None

    @property
    def actor(self) -> str:
        """Author to record in the audit and the commands."""
        return f"user:{self.user_id}"


def unauthorized(detail: str = "Session absente ou expirée.") -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Session"})


def set_cookie(response: Response, name: str, token: str, ttl: timedelta) -> None:
    response.set_cookie(
        name,
        token,
        max_age=int(ttl.total_seconds()),
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )


def clear_cookie(response: Response, name: str) -> None:
    # Same attributes as when set: without `Secure`, clearing a `__Host-` cookie is ignored.
    response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="strict")


async def require_same_origin(request: Request) -> None:
    """CSRF, on top of `SameSite=Strict`: a state-changing request comes from our origin.

    Global dependency of the application. Neither `Origin` nor `Referer` => refuse.
    """
    if request.method in _SAFE_METHODS:
        return
    # Read here, not as a parameter: a read (health probe) does not depend on configuration.
    settings: Settings = request.app.dependency_overrides.get(get_settings, get_settings)()
    origin = request.headers.get("origin")
    if origin is None and (referer := request.headers.get("referer")):
        try:
            parts = urlsplit(referer)
            origin = f"{parts.scheme}://{parts.netloc}"
        except ValueError:  # unreadable Referer: treated as absent
            origin = None
    if origin != settings.public_origin:
        # Visible server-side: a misconfigured origin blocks all writes.
        log.warning(
            "csrf_origin_refused",
            origin=origin,
            expected=settings.public_origin,
            path=request.url.path,
        )
        raise HTTPException(403, "Origine de la requête refusée.")


def pre_session_token(
    token: Annotated[str | None, Cookie(alias=PRE_SESSION_COOKIE)] = None,
) -> str:
    """Pre-session token: opens only `/auth/totp`, which verifies it in the database."""
    if not token:
        raise unauthorized()
    return token


async def current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    now: Annotated[datetime, Depends(utcnow)],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Principal:
    """Full session, valid at this instant; pushes back the inactivity deadline."""
    if not token:
        raise unauthorized()
    # Check and extend in a single statement: no window between the two.
    row = (
        await db.execute(
            update(Session)
            .where(
                Session.token_hash == token_hash(token),
                Session.stage == "full",
                Session.expires_at > now,
                Session.last_activity_at > now - SESSION_IDLE,
            )
            .values(last_activity_at=now)
            .returning(Session.id, Session.user_id, Session.totp_verified_at)
        )
    ).one_or_none()
    user = None if row is None else await db.get(User, row.user_id)
    await db.commit()
    if row is None or user is None:
        raise unauthorized()
    return Principal(
        user_id=user.id,
        email=user.username,
        role=user.role,
        session_id=row.id,
        totp_verified_at=row.totp_verified_at,
    )


def require_role(minimum: Role) -> Callable[[Principal], Awaitable[Principal]]:
    """Dependency: full session and role at least `minimum` (viewer < operator < admin)."""
    needed = _RANK[minimum]  # a misspelled role fails at import, not on the first request

    async def dependency(user: Annotated[Principal, Depends(current_user)]) -> Principal:
        if _RANK.get(user.role, -1) < needed:  # unknown role in the database: no rights
            raise HTTPException(403, "Droits insuffisants pour cette action.")
        return user

    return dependency


async def require_recent_totp(
    user: Annotated[Principal, Depends(current_user)],
    now: Annotated[datetime, Depends(utcnow)],
) -> Principal:
    """Dangerous actions (SPEC §9): this session's TOTP is less than five minutes old."""
    verified = user.totp_verified_at
    if verified is None or not (verified <= now < verified + RECENT_TOTP):
        raise HTTPException(403, "Confirmation par code TOTP requise.")
    return user


# Roles requested by routes: `_: Viewer` is enough to require a session of the wanted level.
Viewer = Annotated[Principal, Depends(require_role("viewer"))]
Operator = Annotated[Principal, Depends(require_role("operator"))]
Admin = Annotated[Principal, Depends(require_role("admin"))]
