"""Strategy registry (SPEC F1, §7, §8).

A deposited version is immutable: no route changes its manifest, its code or its exit policy,
only its status advances. The checks (manifest, source code) are those of the adapter of the
manifest's engine type; they are pure and run here, at write time. A refused version is not
recorded.
"""

from __future__ import annotations

from uuid import UUID

from centrade_core.audit import fingerprint, write_audit
from centrade_core.ids import uuid7
from centrade_core.models.trading import Strategy, StrategyVersion
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError

from centrade_api.auth import Operator, Viewer
from centrade_api.core.deps import (
    Db,
    IdempotencyKey,
    Limit,
    Now,
    client_ip,
)
from centrade_api.core.pagination import Page, decode_cursor, encode_cursor, page_args
from centrade_api.strategies.checks import check_version
from centrade_api.strategies.schemas import (
    StatusChange,
    StrategyCreate,
    StrategyOut,
    VersionCreate,
    VersionDetail,
    VersionOut,
)

router = APIRouter(prefix="/api/v1", tags=["strategies"])

TRANSITIONS = {("draft", "approved"), ("approved", "retired")}


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
    if (at := page_args(cursor)) is not None:
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
    manifest, errors = check_version(body.manifest, body.code)
    if errors:
        raise HTTPException(422, errors)  # nothing is recorded
    code_hash = fingerprint({"code": body.code, "manifest": manifest})
    # Row lock: deposits for the same strategy are serialized, numbers follow each other.
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
    """draft -> approved -> retired; the only editable field of a version."""
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
