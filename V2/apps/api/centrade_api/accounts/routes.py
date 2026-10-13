"""Comptes et clés (SPEC F6, §8, I12).

Une clé est en écriture seule : aucune route ne la renvoie, ni en entier ni en partie, et ce
module ne sait pas la déchiffrer (le déchiffrement vit dans le worker). Le test de permissions
passe par une sonde injectée qui reçoit une référence, jamais une valeur, et n'expose aucune
fonction d'ordre (I11). Refus par défaut : une clé nouvelle ou dont le test n'aboutit pas n'est
pas vérifiée, ce qui bloque le live (I5).

Source : https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from centrade_core.audit import write_audit
from centrade_core.ids import uuid7
from centrade_core.models.trading import Account, Secret
from centrade_core.secrets import AesGcmSecretStore, SecretStore
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_api.accounts.permissions import (
    PermissionProbe,
    get_permission_probe,
    run_probe,
)
from centrade_api.accounts.schemas import (
    AccountCreate,
    AccountOut,
    KeyOut,
    PermissionTestOut,
    SecretIn,
)
from centrade_api.auth import Admin, Viewer, require_recent_totp
from centrade_api.core.deps import (
    Cfg,
    Db,
    Limit,
    Now,
    client_ip,
)
from centrade_api.core.pagination import Page, encode_cursor, page_args

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["accounts"])

# Ajouter ou remplacer une clé est une action dangereuse (SPEC §9) : TOTP de moins de 5 min.
RecentTotp = Depends(require_recent_totp)
_KIND = "venue_api_key"
_REF = {"trade": "secret_ref", "read": "read_secret_ref"}


def get_secret_store(cfg: Cfg) -> SecretStore:
    return AesGcmSecretStore(cfg.master_key())


Probe = Annotated[PermissionProbe, Depends(get_permission_probe)]
Store = Annotated[SecretStore, Depends(get_secret_store)]


async def _accounts_out(db: AsyncSession, accounts: list[Account]) -> list[AccountOut]:
    refs = [r for a in accounts for r in (a.secret_ref, a.read_secret_ref) if r is not None]
    secrets: dict[UUID, Secret] = {}
    if refs:
        secrets = {s.id: s for s in await db.scalars(select(Secret).where(Secret.id.in_(refs)))}
    return [AccountOut.of(a, secrets) for a in accounts]


async def _locked(db: AsyncSession, account_id: UUID) -> Account:
    account = await db.scalar(select(Account).where(Account.id == account_id).with_for_update())
    if account is None:
        raise HTTPException(404, "Compte inconnu.")
    return account


def _key_holder(account: Account) -> None:
    if account.type != "live":  # I3 : paper et backtest ne reçoivent aucune clé
        raise HTTPException(409, "Un compte paper ne reçoit aucune clé.")


def _unverify(account: Account, usage: str) -> None:
    if usage == "trade":
        account.permissions_verified_at = None
        account.ip_restricted = None


@router.get("/accounts")
async def list_accounts(
    _: Viewer, db: Db, now: Now, cursor: str | None = None, limit: Limit = 50
) -> Page[AccountOut]:
    stmt = select(Account)
    if (at := page_args(cursor)) is not None:
        stmt = stmt.where(tuple_(Account.created_at, Account.id) < tuple_(*at))
    rows = (
        await db.scalars(
            stmt.order_by(Account.created_at.desc(), Account.id.desc()).limit(limit + 1)
        )
    ).all()
    page = list(rows[:limit])
    nxt = encode_cursor(page[-1].created_at, page[-1].id) if len(rows) > limit else None
    return Page(items=await _accounts_out(db, page), next_cursor=nxt, server_time=now)


@router.post("/accounts", status_code=201)
async def create_account(
    body: AccountCreate, request: Request, response: Response, user: Admin, db: Db, now: Now
) -> AccountOut:
    account = Account(id=uuid7(), **body.model_dump(), created_at=now, updated_at=now)
    db.add(account)
    await db.flush()
    after: dict[str, Any] = body.model_dump(mode="json")
    await write_audit(
        db,
        actor=user.actor,
        action="account.create",
        target=f"account:{account.id}",
        after=after,
        ip=client_ip(request),
    )
    out = AccountOut.of(account, {})
    await db.commit()
    response.headers["Location"] = f"/api/v1/accounts/{account.id}"
    return out


@router.put("/accounts/{account_id}/secret", dependencies=[RecentTotp])
async def put_secret(
    account_id: UUID, body: SecretIn, request: Request, user: Admin, db: Db, now: Now, store: Store
) -> KeyOut:
    """Stocke ou remplace une clé, sans la tester : le compte redevient non vérifié."""
    account = await _locked(db, account_id)
    _key_holder(account)
    old: UUID | None = getattr(account, _REF[body.usage])
    new = await store.put(
        db, usage=body.usage, kind=_KIND, owner=account.id, value=body.value(), now=now
    )
    setattr(account, _REF[body.usage], new)
    _unverify(account, body.usage)
    account.updated_at = now
    await db.flush()
    if old is not None:  # après la bascule : la ligne n'est plus référencée
        await store.revoke(db, old)
    secret = await db.get_one(Secret, new)
    await write_audit(
        db,
        actor=user.actor,
        action="account.secret.put",
        target=f"account:{account.id}",
        before=None if old is None else {"secret_id": str(old)},
        after={"usage": body.usage, "key_version": secret.key_version, "secret_id": str(new)},
        ip=client_ip(request),
    )
    out = KeyOut.of(secret)
    await db.commit()
    log.info("account_secret_stored", account_id=str(account.id), usage=body.usage)
    return out


@router.post("/accounts/{account_id}/test")
async def check_permissions(
    account_id: UUID, request: Request, user: Admin, db: Db, now: Now, probe: Probe
) -> PermissionTestOut:
    """Teste la clé de trading. Le compte reflète le dernier test : seul `verified` le date."""
    account = await _locked(db, account_id)
    if account.secret_ref is None:
        raise HTTPException(409, "Aucune clé de trading à tester.")
    result, ip_restricted = await run_probe(probe, account.secret_ref, "trade")
    account.permissions_verified_at = now if result == "verified" else None
    account.ip_restricted = ip_restricted
    account.updated_at = now
    await db.flush()
    await write_audit(
        db,
        actor=user.actor,
        action="account.test",
        target=f"account:{account.id}",
        after={"result": result, "ip_restricted": ip_restricted},
        ip=client_ip(request),
    )
    await db.refresh(account)  # `updated_at` est recalculé en base : à relire avant de répondre
    out = PermissionTestOut(result=result, account=(await _accounts_out(db, [account]))[0])
    await db.commit()
    return out


@router.post("/accounts/{account_id}/rotate", dependencies=[RecentTotp])
async def rotate_secret(
    account_id: UUID,
    body: SecretIn,
    request: Request,
    user: Admin,
    db: Db,
    now: Now,
    store: Store,
    probe: Probe,
) -> KeyOut:
    """Nouvelle clé stockée, testée, puis bascule ; l'ancienne est révoquée après la bascule.

    Tout se fait dans une transaction : un test qui n'aboutit pas l'annule, l'ancienne clé et
    l'état du compte restent tels quels.
    """
    # shortcut: la sonde est appelée dans la transaction, avant tout commit ; une sonde qui lit la
    # nouvelle clé depuis un autre processus (M7) demandera un commit intermédiaire.
    account = await _locked(db, account_id)
    _key_holder(account)
    old: UUID | None = getattr(account, _REF[body.usage])
    if old is None:
        raise HTTPException(409, "Aucune clé à remplacer.")
    new = await store.rotate(db, old, owner=account.id, value=body.value(), now=now)
    result, ip_restricted = await run_probe(probe, new, body.usage)
    target, ip = f"account:{account_id}", client_ip(request)
    if result != "verified":
        await db.rollback()
        await write_audit(
            db,
            actor=user.actor,
            action="account.secret.rotate.refused",
            target=target,
            after={"usage": body.usage, "result": result},
            ip=ip,
        )
        await db.commit()
        raise HTTPException(409, "Nouvelle clé non vérifiée : l'ancienne reste en place.")
    setattr(account, _REF[body.usage], new)
    if body.usage == "trade":
        account.permissions_verified_at = now
        account.ip_restricted = ip_restricted
    account.updated_at = now
    await db.flush()
    await store.revoke(db, old)
    secret = await db.get_one(Secret, new)
    await write_audit(
        db,
        actor=user.actor,
        action="account.secret.rotate",
        target=target,
        before={"secret_id": str(old)},
        after={"usage": body.usage, "key_version": secret.key_version, "secret_id": str(new)},
        ip=ip,
    )
    out = KeyOut.of(secret)
    await db.commit()
    log.info("account_secret_rotated", account_id=str(account_id), usage=body.usage)
    return out
