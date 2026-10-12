"""Registre de stratégies (SPEC F1, §7, §8).

Une version déposée est immuable : aucune route ne change son manifest, son code ni sa politique
de sortie, seul son statut avance. Les contrôles (manifest, code source) sont ceux de l'adaptateur
du type de moteur du manifest ; ils sont purs et tournent ici, à l'écriture. Une version refusée
n'est pas enregistrée.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import centrade_freqtrade.checks as freqtrade_checks
from centrade_core.audit import fingerprint, write_audit
from centrade_core.engine.contract import StaticChecks
from centrade_core.engine.types import Manifest
from centrade_core.ids import uuid7
from centrade_core.models.trading import Strategy, StrategyVersion
from centrade_fake.engine import ENGINE as FAKE
from centrade_fake.engine import FakeEngine
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError

from centrade_api.deps import client_ip
from centrade_api.instances import Db, IdempotencyKey, Limit, Now, Operator, Viewer, _page_args
from centrade_api.schemas import Page, decode_cursor, encode_cursor

router = APIRouter(prefix="/api/v1", tags=["strategies"])

# Type de moteur -> contrôles de son adaptateur. Un moteur inconnu est refusé.
CHECKS: dict[str, StaticChecks] = {
    FAKE: FakeEngine(clock=lambda: datetime.now(UTC), seed=0, new_id=uuid7),
    freqtrade_checks.ENGINE: freqtrade_checks,
}
TRANSITIONS = {("draft", "approved"), ("approved", "retired")}
Status = Literal["draft", "approved", "retired"]


class StrategyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")


class StrategyOut(BaseModel):
    id: UUID
    name: str
    created_at: AwareDatetime


class VersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest: dict[str, Any]
    code: str = Field(min_length=1, max_length=60_000)


class StatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status


class VersionOut(BaseModel):
    id: UUID
    strategy_id: UUID
    version: int
    status: Status
    engine: str  # type de moteur, lu dans le manifest
    manifest: dict[str, Any]
    code_hash: str
    author: str
    static_checks: dict[str, Any]
    exits: dict[str, Any]  # politique de sortie (F10) : stoploss et ratios en chaînes décimales
    created_at: AwareDatetime

    @classmethod
    def of(cls, v: StrategyVersion) -> VersionOut:
        return cls(
            **{k: getattr(v, k) for k in cls.model_fields if k != "engine"},
            engine=v.manifest["engine"],
        )


class VersionDetail(VersionOut):
    code: str

    @classmethod
    def of(cls, v: StrategyVersion) -> VersionDetail:
        return cls(**VersionOut.of(v).model_dump(), code=v.code)


def _check(raw: dict[str, Any], code: str) -> tuple[dict[str, Any], list[str]]:
    """Manifest canonique (JSON) et motifs de refus ; liste vide = accepté."""
    try:
        manifest = Manifest.model_validate(raw)
    except ValueError as e:  # ValidationError : ni valeur reçue ni contexte dans les motifs
        problems: list[Any] = getattr(e, "errors", lambda: [])()
        return {}, [f"manifest.{'.'.join(map(str, x['loc']))} : {x['msg']}" for x in problems]
    checks = CHECKS.get(manifest.engine)
    if checks is None:
        return {}, [f"type de moteur inconnu : {manifest.engine}"]
    props = manifest.params_schema.get("properties", {})
    defaults = {k: p["default"] for k, p in props.items() if isinstance(p, dict) and "default" in p}
    errors: list[str] = [
        *checks.validate(manifest, defaults).errors,
        *checks.check_source(manifest, code).errors,
    ]
    return manifest.model_dump(mode="json"), errors


async def _strategy(db: Db, strategy_id: UUID, *, lock: bool = False) -> Strategy:
    stmt = select(Strategy).where(Strategy.id == strategy_id)
    strategy = await db.scalar(stmt.with_for_update() if lock else stmt)
    if strategy is None:
        raise HTTPException(404, "Stratégie inconnue.")
    return strategy


async def _version(
    db: Db, strategy_id: UUID, version: int, *, lock: bool = False
) -> StrategyVersion:
    stmt = select(StrategyVersion).where(
        StrategyVersion.strategy_id == strategy_id, StrategyVersion.version == version
    )
    found = await db.scalar(stmt.with_for_update() if lock else stmt)
    if found is None:
        raise HTTPException(404, "Version inconnue.")
    return found


@router.get("/strategies")
async def list_strategies(
    _: Viewer, db: Db, now: Now, cursor: str | None = None, limit: Limit = 50
) -> Page[StrategyOut]:
    stmt = select(Strategy)
    if (at := _page_args(cursor)) is not None:
        stmt = stmt.where(tuple_(Strategy.created_at, Strategy.id) < tuple_(*at))
    rows = (
        await db.scalars(
            stmt.order_by(Strategy.created_at.desc(), Strategy.id.desc()).limit(limit + 1)
        )
    ).all()
    page = rows[:limit]
    nxt = encode_cursor(page[-1].created_at, page[-1].id) if len(rows) > limit else None
    items = [StrategyOut(id=s.id, name=s.name, created_at=s.created_at) for s in page]
    return Page(items=items, next_cursor=nxt, server_time=now)


@router.post("/strategies", status_code=201)
async def create_strategy(
    body: StrategyCreate, request: Request, user: Operator, db: Db, now: Now
) -> StrategyOut:
    s = Strategy(id=uuid7(), name=body.name, created_at=now, updated_at=now)
    db.add(s)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, "Une stratégie porte déjà ce nom.") from None
    await write_audit(
        db,
        actor=user.actor,
        action="strategy.create",
        target=f"strategy:{s.id}",
        after={"name": s.name},
        ip=client_ip(request),
    )
    await db.commit()
    return StrategyOut(id=s.id, name=s.name, created_at=s.created_at)


@router.post("/strategies/{strategy_id}/versions", status_code=201)
async def create_version(
    strategy_id: UUID,
    body: VersionCreate,
    key: IdempotencyKey,
    request: Request,
    response: Response,
    user: Operator,
    db: Db,
    now: Now,
) -> VersionDetail:
    manifest, errors = _check(body.manifest, body.code)
    if errors:
        raise HTTPException(422, errors)  # rien n'est enregistré
    code_hash = fingerprint({"code": body.code, "manifest": manifest})
    # Verrou de ligne : les dépôts d'une même stratégie sont sérialisés, les numéros se suivent.
    await _strategy(db, strategy_id, lock=True)
    replay = await db.scalar(
        select(StrategyVersion).where(
            StrategyVersion.strategy_id == strategy_id, StrategyVersion.idempotency_key == key
        )
    )
    if replay is not None:
        if replay.code_hash != code_hash:
            raise HTTPException(422, "Clé d'idempotence déjà utilisée pour un autre dépôt.")
        response.status_code = 200
        return VersionDetail.of(replay)
    last = await db.scalar(
        select(StrategyVersion.version)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version.desc())
        .limit(1)
    )
    v = StrategyVersion(
        id=uuid7(),
        strategy_id=strategy_id,
        version=(last or 0) + 1,
        manifest=manifest,
        code=body.code,
        idempotency_key=key,
        code_hash=code_hash,
        status="draft",
        author=user.actor,
        static_checks={"ok": True, "errors": [], "checked_at": now.isoformat()},
        exits=manifest["exits"],
        created_at=now,
        updated_at=now,
    )
    db.add(v)
    await db.flush()
    await write_audit(
        db,
        actor=user.actor,
        action="strategy.version.create",
        target=f"strategy_version:{v.id}",
        after={"strategy_id": str(strategy_id), "version": v.version, "code_hash": code_hash},
        ip=client_ip(request),
    )
    await db.commit()
    return VersionDetail.of(v)


@router.get("/strategies/{strategy_id}/versions")
async def list_versions(
    strategy_id: UUID, _: Viewer, db: Db, now: Now, cursor: str | None = None, limit: Limit = 50
) -> Page[VersionOut]:
    await _strategy(db, strategy_id)
    stmt = select(StrategyVersion).where(StrategyVersion.strategy_id == strategy_id)
    if cursor is not None:
        head = decode_cursor(cursor)[0]
        if not head.isdigit():
            raise HTTPException(422, "Curseur invalide.")
        stmt = stmt.where(StrategyVersion.version < int(head))
    rows = (await db.scalars(stmt.order_by(StrategyVersion.version.desc()).limit(limit + 1))).all()
    page = rows[:limit]
    nxt = encode_cursor(page[-1].version) if len(rows) > limit else None
    return Page(items=[VersionOut.of(v) for v in page], next_cursor=nxt, server_time=now)


@router.get("/strategies/{strategy_id}/versions/{version}")
async def get_version(strategy_id: UUID, version: int, _: Viewer, db: Db) -> VersionDetail:
    return VersionDetail.of(await _version(db, strategy_id, version))


@router.patch("/strategies/{strategy_id}/versions/{version}")
async def change_status(
    strategy_id: UUID,
    version: int,
    body: StatusChange,
    request: Request,
    user: Operator,
    db: Db,
    now: Now,
) -> VersionOut:
    """draft -> approved -> retired ; le seul champ modifiable d'une version."""
    v = await _version(db, strategy_id, version, lock=True)
    if (v.status, body.status) not in TRANSITIONS:
        raise HTTPException(409, f"Transition interdite : {v.status} vers {body.status}.")
    before, v.status, v.updated_at = v.status, body.status, now
    await write_audit(
        db,
        actor=user.actor,
        action="strategy.version.status",
        target=f"strategy_version:{v.id}",
        before={"status": before},
        after={"status": v.status},
        ip=client_ip(request),
    )
    await db.commit()
    return VersionOut.of(v)
