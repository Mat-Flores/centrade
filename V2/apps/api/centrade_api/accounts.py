"""Comptes et clés (SPEC F6, §8, I12).

Une clé est en écriture seule : aucune route ne la renvoie, ni en entier ni en partie, et ce
module ne sait pas la déchiffrer (le déchiffrement vit dans le worker). Le test de permissions
passe par une sonde injectée qui reçoit une référence, jamais une valeur, et n'expose aucune
fonction d'ordre (I11). Refus par défaut : une clé nouvelle ou dont le test n'aboutit pas n'est
pas vérifiée, ce qui bloque le live (I5).

Source : https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

import structlog
from centrade_core.audit import write_audit
from centrade_core.ids import uuid7
from centrade_core.models.trading import Account, Secret
from centrade_core.secrets import AesGcmSecretStore, SecretStore
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_api.auth import Principal, require_recent_totp, require_role
from centrade_api.deps import client_ip
from centrade_api.instances import Cfg, Db, Limit, Now, Viewer, _page_args
from centrade_api.schemas import Page, encode_cursor

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["comptes"])

Admin = Annotated[Principal, Depends(require_role("admin"))]
# Ajouter ou remplacer une clé est une action dangereuse (SPEC §9) : TOTP de moins de 5 min.
RecentTotp = Depends(require_recent_totp)
KeyUsage = Literal["trade", "read"]  # `engine_api` et `webhook` ne se saisissent pas ici
Verdict = Literal["verified", "refused", "unverified"]
PROBE_TIMEOUT_S = 10.0
_KIND = "venue_api_key"
_REF = {"trade": "secret_ref", "read": "read_secret_ref"}


@dataclass(frozen=True, slots=True)
class KeyPermissions:
    """Ce que la venue dit d'une clé. None : la venue ne l'a pas dit."""

    trading: bool | None
    withdrawal: bool | None
    ip_restricted: bool | None


class PermissionProbe(Protocol):
    """Lecture des permissions d'une clé stockée. Aucune fonction d'ordre (I11)."""

    async def permissions(self, secret_id: UUID) -> KeyPermissions: ...


class UnverifiedProbe:
    """Aucune venue réelle dans cet environnement (SPEC §0.10) : rien n'est constaté."""

    async def permissions(self, secret_id: UUID) -> KeyPermissions:
        return KeyPermissions(trading=None, withdrawal=None, ip_restricted=None)


def get_permission_probe() -> PermissionProbe:
    return UnverifiedProbe()


def get_secret_store(cfg: Cfg) -> SecretStore:
    return AesGcmSecretStore(cfg.master_key())


Probe = Annotated[PermissionProbe, Depends(get_permission_probe)]
Store = Annotated[SecretStore, Depends(get_secret_store)]


def verdict(perms: KeyPermissions, usage: KeyUsage) -> Verdict:
    """Clé de trading : trading autorisé et retrait interdit. Clé de lecture : ni l'un ni
    l'autre. Retrait possible : refus. Réponse incomplète : non vérifié."""
    if not isinstance(perms, KeyPermissions):
        return "unverified"
    if perms.withdrawal is True:
        return "refused"
    if not isinstance(perms.trading, bool) or perms.withdrawal is not False:
        return "unverified"
    return "verified" if perms.trading is (usage == "trade") else "refused"


async def _probe(
    probe: PermissionProbe, secret_id: UUID, usage: KeyUsage
) -> tuple[Verdict, bool | None]:
    """Rend (verdict, restriction d'IP constatée). Erreur ou délai dépassé : non vérifié."""
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_S):
            perms = await probe.permissions(secret_id)
    except Exception as exc:  # le message d'une erreur de venue peut porter une clé : type seul
        log.warning("account_probe_failed", error=type(exc).__name__)
        return "unverified", None
    result = verdict(perms, usage)
    ip = perms.ip_restricted if result == "verified" else None
    return result, ip if isinstance(ip, bool) else None


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue: str = Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_-]*$")
    type: Literal["paper", "live"]
    environment: Literal["production", "sandbox"]
    label: str = Field(min_length=1, max_length=80)
    currency: str = Field(pattern=r"^[A-Z0-9]{2,10}$")
    # Chaîne décimale, dans `currency`. Bornes de NUMERIC(38, 18).
    capital_cap: Decimal | None = Field(
        default=None, gt=0, lt=Decimal("1e20"), max_digits=38, decimal_places=18
    )

    @field_validator("capital_cap", mode="before")
    @classmethod
    def _decimal_string(cls, v: object) -> object:
        if v is not None and not isinstance(v, str):
            raise ValueError("chaîne décimale attendue")  # jamais de float pour de l'argent
        return v


class SecretIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usage: KeyUsage
    key: SecretStr = Field(min_length=1, max_length=512)
    secret: SecretStr = Field(min_length=1, max_length=1024)

    def value(self) -> SecretStr:
        return SecretStr(
            json.dumps(
                {"key": self.key.get_secret_value(), "secret": self.secret.get_secret_value()}
            )
        )


class KeyOut(BaseModel):
    """Tout ce qu'on dit d'une clé : jamais sa valeur, ni un préfixe, ni une empreinte."""

    usage: str
    key_version: int
    stored_at: AwareDatetime
    rotated_at: AwareDatetime | None
    last_used_at: AwareDatetime | None

    @classmethod
    def of(cls, s: Secret) -> KeyOut:
        return cls(
            usage=s.usage,
            key_version=s.key_version,
            stored_at=s.created_at,
            rotated_at=s.rotated_at,
            last_used_at=s.last_used_at,
        )


class AccountOut(BaseModel):
    id: UUID
    venue: str
    type: str
    environment: str
    label: str
    currency: str
    capital_cap: str | None  # chaîne décimale
    trade_key: KeyOut | None
    read_key: KeyOut | None
    permissions_verified_at: AwareDatetime | None  # None : non vérifié, live bloqué
    ip_restricted: bool | None  # None : inconnu
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @classmethod
    def of(cls, a: Account, secrets: dict[UUID, Secret]) -> AccountOut:
        def key(ref: UUID | None) -> KeyOut | None:
            return KeyOut.of(secrets[ref]) if ref in secrets else None

        return cls(
            id=a.id,
            venue=a.venue,
            type=a.type,
            environment=a.environment,
            label=a.label,
            currency=a.currency,
            capital_cap=None if a.capital_cap is None else _money(a.capital_cap),
            trade_key=key(a.secret_ref),
            read_key=key(a.read_secret_ref),
            permissions_verified_at=a.permissions_verified_at,
            ip_restricted=a.ip_restricted,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )


class PermissionTestOut(BaseModel):
    result: Verdict
    account: AccountOut


def _money(value: Decimal) -> str:
    return format(value.normalize(), "f")


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
    if (at := _page_args(cursor)) is not None:
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
    result, ip_restricted = await _probe(probe, account.secret_ref, "trade")
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
    result, ip_restricted = await _probe(probe, new, body.usage)
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
