"""Routes d'authentification : mot de passe, puis TOTP ou code de récupération (SPEC §8, §13).

Une session ouverte re-confirme son TOTP avant une action dangereuse (SPEC §9).

Chaque route tient en une transaction : l'état, la session et la ligne d'audit sont validés
ensemble, ou pas du tout. La réponse n'est décidée qu'après le `commit`.
"""

import math
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

import structlog
from anyio import to_thread
from centrade_core.audit import write_audit
from centrade_core.ids import uuid7
from centrade_core.models import Session, User
from centrade_core.settings import Settings, get_settings
from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_api.auth import security
from centrade_api.auth.deps import (
    PRE_SESSION_COOKIE,
    PRE_SESSION_TTL,
    SESSION_ABSOLUTE,
    SESSION_COOKIE,
    Principal,
    clear_cookie,
    current_user,
    pre_session_token,
    set_cookie,
    unauthorized,
)
from centrade_api.deps import client_ip, get_db, utcnow

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

ANONYMOUS = "anonymous"  # auteur d'une tentative dont l'identité n'est pas prouvée
LOCK_THRESHOLD = 5
LOCK_BASE = timedelta(minutes=1)
LOCK_MAX = timedelta(minutes=15)
# Clé maître absente ou fausse, ligne altérée : panne de notre côté, pas un échec de l'utilisateur.
_SECRET_UNREADABLE = (InvalidTag, ValueError, OSError)
# Échecs dont l'auteur est prouvé (pré-session ou session) ; tout autre échec reste anonyme.
_ATTRIBUTED_FAILURES = ("auth.totp.failed", "auth.totp_confirm.failed")


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


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)  # borne le coût d'argon2


class TotpIn(BaseModel):
    code: SecretStr = Field(min_length=1, max_length=64)  # 6 chiffres, ou code de récupération


class LoginOut(BaseModel):
    totp_required: bool


class Me(BaseModel):
    id: UUID
    email: str
    role: str


def throttle(request: Request, now: Annotated[datetime, Depends(utcnow)]) -> None:
    """Débit par adresse, avant toute lecture du corps, de la base ou calcul d'empreinte."""
    ip = client_ip(request)
    if (wait := limiter.retry_after(ip or "inconnue", now)) is not None:
        log.warning("auth_rate_limited", ip=ip)
        raise HTTPException(
            429, "Trop de tentatives. Réessayez plus tard.", headers={"Retry-After": str(wait)}
        )


async def _record_failure(
    db: AsyncSession, user: User, now: datetime, ip: str | None, action: str, reason: str
) -> bool:
    """Compte l'échec, verrouille au besoin, audite. Renvoie True si le compte vient de l'être.

    La ligne `users` est verrouillée par l'appelant (`FOR UPDATE`) : le compteur ne se perd pas.
    Auteur : `anonymous` tant que rien n'est prouvé (mot de passe), l'utilisateur ensuite (TOTP).
    """
    target = f"user:{user.id}"
    actor = target if action in _ATTRIBUTED_FAILURES else ANONYMOUS
    user.failed_attempts += 1
    log.warning(action.replace(".", "_"), reason=reason, user_id=str(user.id), ip=ip)
    await write_audit(db, actor=actor, action=action, target=target, ip=ip)
    lock = lock_duration(user.failed_attempts)
    if lock is None:
        return False
    user.locked_until = now + lock
    # Un compte verrouillé ne garde aucune pré-session en attente.
    await db.execute(delete(Session).where(Session.user_id == user.id, Session.stage == "pre_totp"))
    log.warning(
        "auth_account_locked", user_id=str(user.id), ip=ip, locked_s=int(lock.total_seconds())
    )
    await write_audit(
        db,
        actor="system:auth",  # verrou posé par la plateforme, pas par une personne
        action="auth.account.locked",
        target=target,
        after={"failed_attempts": user.failed_attempts, "locked_until": user.locked_until},
        ip=ip,
    )
    return True


def _locked(user: User, now: datetime) -> bool:
    return user.locked_until is not None and user.locked_until > now


@router.post("/login", dependencies=[Depends(throttle)])
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    now: Annotated[datetime, Depends(utcnow)],
) -> LoginOut:
    """Étape 1. Ouvre une pré-session, qui ne donne accès qu'à `/auth/totp`.

    Compte inconnu, mot de passe faux, compte verrouillé ou sans TOTP : même réponse, même coût.
    """
    ip = client_ip(request)
    username = body.username.strip().lower()
    token: str | None = None
    async with db.begin():
        user = (
            await db.execute(select(User).where(User.username == username).with_for_update())
        ).scalar_one_or_none()
        checkable = user is not None and not _locked(user, now)
        # Hors de la boucle d'événements : argon2 occupe un cœur pendant des dizaines de ms.
        password_ok = await to_thread.run_sync(
            security.verify_password,
            user.password_hash if user is not None and checkable else None,
            body.password.get_secret_value(),
        )
        if user is None:
            log.warning("auth_login_failed", reason="unknown_account", user_id=None, ip=ip)
            await write_audit(
                db, actor=ANONYMOUS, action="auth.login.failed", target="user:unknown", ip=ip
            )
        elif not checkable:
            # Ni compté ni évalué : un verrou ne se prolonge pas, et ne dit rien du mot de passe.
            log.warning("auth_login_failed", reason="locked", user_id=str(user.id), ip=ip)
            await write_audit(
                db, actor=ANONYMOUS, action="auth.login.failed", target=f"user:{user.id}", ip=ip
            )
        elif not password_ok:
            await _record_failure(db, user, now, ip, "auth.login.failed", "bad_password")
        elif user.totp_secret_enc is None or user.totp_nonce is None:
            # TOTP obligatoire : sans second facteur enrôlé, aucune session, même partielle.
            await _record_failure(db, user, now, ip, "auth.login.failed", "totp_not_enrolled")
        else:
            await db.execute(
                delete(Session).where(
                    Session.user_id == user.id,
                    or_(Session.stage == "pre_totp", Session.expires_at <= now),
                )
            )
            # Tracé même si le TOTP ne suit jamais : un mot de passe connu d'un tiers se voit.
            actor = f"user:{user.id}"
            await write_audit(db, actor=actor, action="auth.password.accepted", target=actor, ip=ip)
            token = security.new_token()
            db.add(
                Session(
                    id=uuid7(),
                    user_id=user.id,
                    token_hash=security.token_hash(token),
                    stage="pre_totp",
                    created_at=now,
                    last_activity_at=now,
                    expires_at=now + PRE_SESSION_TTL,
                )
            )
    if token is None:
        raise unauthorized("Identifiants refusés, ou compte temporairement verrouillé.")
    set_cookie(response, PRE_SESSION_COOKIE, token, PRE_SESSION_TTL)
    return LoginOut(totp_required=True)


def _totp_accepted(user: User, code: str, now: datetime, master_key: bytes) -> bool:
    """Vérifie un code TOTP et consomme son pas. Le seul chemin de vérification du TOTP.

    Ne lit ni ne consomme les codes de récupération. Lève `InvalidTag` si le secret TOTP est
    illisible (clé maître ou ligne altérée).
    """
    if user.totp_secret_enc is None or user.totp_nonce is None:
        return False
    step = security.totp_step(
        security.decrypt_totp_secret(
            master_key=master_key,
            user_id=user.id,
            nonce=user.totp_nonce,
            ciphertext=user.totp_secret_enc,
        ),
        code,
        now,
    )
    # Pas déjà accepté, ou plus ancien que le dernier accepté : rejeu.
    if step is None or (user.totp_last_step is not None and step <= user.totp_last_step):
        return False
    user.totp_last_step = step
    return True


def _second_factor(user: User, code: str, now: datetime, master_key: bytes) -> str | None:
    """Vérifie et consomme le second facteur. Renvoie `totp`, `recovery`, ou None s'il est refusé.

    Lève `InvalidTag` si le secret TOTP est illisible (clé maître ou ligne altérée).
    """
    if user.totp_secret_enc is None or user.totp_nonce is None:
        return None
    if _totp_accepted(user, code, now, master_key):
        return "totp"
    if security.is_totp_code(code):
        return None  # six chiffres refusés (faux ou rejoués) : jamais un code de récupération
    used = security.matching_hash(user.recovery_code_hashes, security.recovery_code_hash(code))
    if used is None:
        return None
    user.recovery_code_hashes = [h for h in user.recovery_code_hashes if h != used]
    return "recovery"


@router.post("/totp", dependencies=[Depends(throttle)])
async def totp(
    body: TotpIn,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    now: Annotated[datetime, Depends(utcnow)],
    settings: Annotated[Settings, Depends(get_settings)],
    pre_token: Annotated[str, Depends(pre_session_token)],
) -> Me:
    """Étape 2. Code TOTP ou code de récupération : ferme la pré-session, ouvre la session."""
    ip = client_ip(request)
    opened: tuple[str, Me, str] | None = None
    failure = unauthorized("Code refusé.")
    async with db.begin():
        pre = (
            await db.execute(
                select(Session).where(
                    Session.token_hash == security.token_hash(pre_token),
                    Session.stage == "pre_totp",
                    Session.expires_at > now,
                )
            )
        ).scalar_one_or_none()
        user = (
            None
            if pre is None
            else (
                await db.execute(select(User).where(User.id == pre.user_id).with_for_update())
            ).scalar_one_or_none()
        )
        if pre is None or user is None:
            failure = unauthorized()
        elif _locked(user, now):
            await db.execute(delete(Session).where(Session.id == pre.id))
            failure = HTTPException(423, "Compte temporairement verrouillé.")
        else:
            try:
                factor = _second_factor(
                    user, body.code.get_secret_value().strip(), now, settings.master_key()
                )
            except _SECRET_UNREADABLE:
                # Aucune session, et le compteur d'échecs ne bouge pas.
                log.error("auth_totp_secret_unreadable", user_id=str(user.id), ip=ip)
                failure = HTTPException(503, "Service d'authentification indisponible.")
            else:
                # La pré-session ne sert qu'une fois : deux envois simultanés, chacun avec un
                # facteur valide, n'ouvrent pas deux sessions.
                if (
                    factor is not None
                    and not (
                        await db.execute(
                            delete(Session).where(Session.id == pre.id).returning(Session.id)
                        )
                    ).first()
                ):
                    factor = None
                if factor is None:
                    if await _record_failure(db, user, now, ip, "auth.totp.failed", "bad_code"):
                        failure = HTTPException(423, "Compte temporairement verrouillé.")
                else:
                    opened = (*await _open_session(db, user, now, ip, factor), factor)
    if opened is None:
        raise failure
    token, me_out, factor = opened
    # Après le commit : on n'annonce une session que lorsqu'elle existe.
    if factor == "recovery":
        log.warning("auth_recovery_code_used", user_id=str(me_out.id), ip=ip)
    log.info("auth_login_succeeded", user_id=str(me_out.id), ip=ip, factor=factor)
    set_cookie(response, SESSION_COOKIE, token, SESSION_ABSOLUTE)
    clear_cookie(response, PRE_SESSION_COOKIE)
    return me_out


async def _open_session(
    db: AsyncSession, user: User, now: datetime, ip: str | None, factor: str
) -> tuple[str, Me]:
    """Session complète : nouvelle ligne, nouvel identifiant, nouveau jeton (rotation)."""
    actor = f"user:{user.id}"
    user.failed_attempts, user.locked_until = 0, None
    token = security.new_token()
    db.add(
        Session(
            id=uuid7(),
            user_id=user.id,
            token_hash=security.token_hash(token),
            stage="full",
            created_at=now,
            last_activity_at=now,
            expires_at=now + SESSION_ABSOLUTE,
            totp_verified_at=now,
        )
    )
    if factor == "recovery":
        await write_audit(
            db,
            actor=actor,
            action="auth.recovery_code.used",
            target=actor,
            after={"left": len(user.recovery_code_hashes)},
            ip=ip,
        )
    await write_audit(db, actor=actor, action="auth.login.succeeded", target=actor, ip=ip)
    return token, Me(id=user.id, email=user.username, role=user.role)


@router.post("/totp/confirm", status_code=204, dependencies=[Depends(throttle)])
async def confirm_totp(
    body: TotpIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    now: Annotated[datetime, Depends(utcnow)],
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(current_user)],
) -> None:
    """Ré-authentification d'une session ouverte : rafraîchit le TOTP de cette session, lui seul.

    Code TOTP seul : un code de récupération rend un accès, il n'autorise pas une action
    dangereuse. Un refus ne ferme pas la session et ne dit pas si le code est faux ou rejoué.
    """
    ip = client_ip(request)
    actor = principal.actor
    failure: HTTPException | None = HTTPException(403, "Code refusé.")
    async with db.begin():
        user = (
            await db.execute(
                select(User)
                .where(User.id == principal.user_id)
                .with_for_update()
                # `current_user` a déjà chargé cette ligne : si l'objet vit encore, le dernier
                # pas accepté et le verrou dateraient d'avant le `FOR UPDATE` (rejeu simultané).
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if user is None:
            failure = unauthorized()
        elif _locked(user, now):
            # Ni compté ni évalué : un verrou ne se prolonge pas. Audité quand même (I14).
            log.warning("auth_totp_confirm_failed", reason="locked", user_id=str(user.id), ip=ip)
            await write_audit(
                db, actor=actor, action="auth.totp_confirm.failed", target=actor, ip=ip
            )
            failure = HTTPException(423, "Compte temporairement verrouillé.")
        else:
            try:
                accepted = _totp_accepted(
                    user, body.code.get_secret_value().strip(), now, settings.master_key()
                )
            except _SECRET_UNREADABLE:
                log.error("auth_totp_secret_unreadable", user_id=str(user.id), ip=ip)
                failure = HTTPException(503, "Service d'authentification indisponible.")
            else:
                if not accepted:
                    if await _record_failure(
                        db, user, now, ip, "auth.totp_confirm.failed", "bad_code"
                    ):
                        failure = HTTPException(423, "Compte temporairement verrouillé.")
                elif not (
                    await db.execute(
                        # Cette session seulement, et seulement sa date de TOTP : ni l'échéance
                        # absolue ni une autre session du même utilisateur ne bougent.
                        update(Session)
                        .where(Session.id == principal.session_id, Session.stage == "full")
                        .values(totp_verified_at=now)
                        .returning(Session.id)
                    )
                ).first():
                    failure = unauthorized()  # session fermée entre-temps : rien à rafraîchir
                else:
                    await write_audit(
                        db, actor=actor, action="auth.totp_confirm.succeeded", target=actor, ip=ip
                    )
                    failure = None
    if failure is not None:
        raise failure
    # Après le commit : on n'annonce une confirmation que lorsqu'elle est enregistrée.
    log.info("auth_totp_confirm_succeeded", user_id=str(principal.user_id), ip=ip)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    user: Annotated[Principal, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    ip = client_ip(request)
    async with db.begin():
        await db.execute(delete(Session).where(Session.id == user.session_id))
        await write_audit(db, actor=user.actor, action="auth.logout", target=user.actor, ip=ip)
    log.info("auth_logout", user_id=str(user.user_id), ip=ip)
    clear_cookie(response, SESSION_COOKIE)


@router.get("/me")
async def me(user: Annotated[Principal, Depends(current_user)]) -> Me:
    return Me(id=user.user_id, email=user.email, role=user.role)
