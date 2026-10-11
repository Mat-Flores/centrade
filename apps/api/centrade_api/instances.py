"""Instances et commandes (SPEC F9, §8).

Une route d'action n'appelle jamais un moteur : elle écrit une commande `requested`, met à jour
l'état voulu, audite, et répond 202. Le worker relève la commande et ne la déclare `verified`
que lorsque l'effet est observé (I8). Aucune route ne crée d'ordre (SPEC §8).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

import structlog
from centrade_core.audit import write_audit
from centrade_core.bus import notify
from centrade_core.commands import (
    ACTIVE,
    DESIRED_AFTER,
    PRIORITY,
    RISK_INCREASING,
    Status,
    risk_increase_refusal,
)
from centrade_core.ids import uuid7
from centrade_core.models.trading import Command, Engine, Instance
from centrade_core.settings import Settings, get_settings
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from redis.asyncio import Redis
from sqlalchemy import select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_api.auth import Principal, require_role
from centrade_api.deps import client_ip, get_db, get_redis, utcnow
from centrade_api.schemas import (
    CommandAccepted,
    CommandOut,
    InstanceCreate,
    InstanceOut,
    Page,
    decode_cursor,
    encode_cursor,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["instances"])

Viewer = Annotated[Principal, Depends(require_role("viewer"))]
Operator = Annotated[Principal, Depends(require_role("operator"))]
Db = Annotated[AsyncSession, Depends(get_db)]
Now = Annotated[datetime, Depends(utcnow)]
Cfg = Annotated[Settings, Depends(get_settings)]
Bus = Annotated[Redis | None, Depends(get_redis)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$"),
]
Limit = Annotated[int, Query(ge=1, le=200)]  # hors bornes ou non entier : 422
ActionType = Literal["start", "stop", "pause_entries", "resume_entries", "flatten"]


async def instances_out(
    db: AsyncSession, rows: list[tuple[Instance, str]], now: datetime, cfg: Settings
) -> list[InstanceOut]:
    ids = [i.id for i, _ in rows]
    active: dict[UUID, Command] = {}
    if ids:
        cmds = await db.scalars(
            select(Command)
            .where(Command.instance_id.in_(ids), Command.status.in_(ACTIVE))
            .order_by(Command.requested_at, Command.id)
        )
        active = {c.instance_id: c for c in cmds}  # la plus récente l'emporte
    return [
        InstanceOut.of(i, kind, active.get(i.id), now, cfg.observed_stale_after_s)
        for i, kind in rows
    ]


async def instance_out(
    db: AsyncSession, instance_id: UUID, now: datetime, cfg: Settings
) -> InstanceOut | None:
    row = (
        await db.execute(
            select(Instance, Engine.kind)
            .join(Engine, Engine.id == Instance.engine_id)
            .where(Instance.id == instance_id)
        )
    ).one_or_none()
    return (await instances_out(db, [(row[0], row[1])], now, cfg))[0] if row else None


def _page_args(cursor: str | None) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    head, ident = decode_cursor(cursor)
    try:
        return datetime.fromisoformat(head), UUID(ident)
    except ValueError:
        raise HTTPException(422, "Curseur invalide.") from None


@router.get("/instances")
async def list_instances(
    _: Viewer, db: Db, now: Now, cfg: Cfg, cursor: str | None = None, limit: Limit = 50
) -> Page[InstanceOut]:
    stmt = select(Instance, Engine.kind).join(Engine, Engine.id == Instance.engine_id)
    if (at := _page_args(cursor)) is not None:
        stmt = stmt.where(tuple_(Instance.created_at, Instance.id) < tuple_(*at))
    rows = (
        await db.execute(
            stmt.order_by(Instance.created_at.desc(), Instance.id.desc()).limit(limit + 1)
        )
    ).all()
    more = len(rows) > limit
    page = [(r[0], r[1]) for r in rows[:limit]]
    nxt = encode_cursor(page[-1][0].created_at, page[-1][0].id) if more else None
    return Page(items=await instances_out(db, page, now, cfg), next_cursor=nxt, server_time=now)


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: UUID, _: Viewer, db: Db, now: Now, cfg: Cfg) -> InstanceOut:
    out = await instance_out(db, instance_id, now, cfg)
    if out is None:
        raise HTTPException(404, "Instance inconnue.")
    return out


def _request_hash(instance_id: UUID, command_type: str) -> str:
    return hashlib.sha256(f"{instance_id}:{command_type}".encode()).hexdigest()


def _new_command(
    inst: Instance, type_: str, user: Principal, key: str, now: datetime, cfg: Settings
) -> Command:
    return Command(
        id=uuid7(),
        instance_id=inst.id,
        type=type_,
        actor=user.actor,
        idempotency_key=key,
        request_hash=_request_hash(inst.id, type_),
        status="requested",
        correlation_id=uuid7(),
        requested_at=now,
        deadline_at=now + timedelta(seconds=cfg.command_deadline_s(type_)),
        updated_at=now,
    )


async def _replay(db: AsyncSession, user: Principal, key: str, request_hash: str) -> Command | None:
    existing = await db.scalar(
        select(Command).where(Command.actor == user.actor, Command.idempotency_key == key)
    )
    if existing is not None and existing.request_hash != request_hash:
        raise HTTPException(422, "Clé d'idempotence déjà utilisée pour une autre requête.")
    return existing


async def _announce(redis: Redis | None, *items: tuple[str, UUID]) -> None:
    if redis is not None:
        for kind, ident in items:
            await notify(redis, kind, ident)


async def request_command(
    db: AsyncSession,
    redis: Redis | None,
    request: Request,
    user: Principal,
    instance_id: UUID,
    type_: str,
    key: str,
    now: datetime,
    cfg: Settings,
) -> tuple[Command, bool]:
    """Enregistre la commande (jamais d'appel au moteur). Rend (commande, rejeu)."""
    # Verrou de ligne : les demandes d'une même instance sont sérialisées.
    inst = await db.scalar(select(Instance).where(Instance.id == instance_id).with_for_update())
    if inst is None:
        raise HTTPException(404, "Instance inconnue.")
    # SPEC §13 : `operator` n'augmente le risque qu'en paper ; tout autre mode exige `admin`.
    if type_ in RISK_INCREASING and inst.mode != "paper" and user.role != "admin":
        raise HTTPException(403, "Droits insuffisants pour cette action hors mode paper.")
    replay = await _replay(db, user, key, _request_hash(instance_id, type_))
    if replay is not None:
        return replay, True
    # I5 : refus au moindre doute. Le worker rejoue la même règle juste avant l'envoi.
    reason = risk_increase_refusal(
        type_,
        mode=inst.mode,
        observed_state=inst.observed_state,
        observed_mode=inst.observed_mode,
        observed_at=inst.observed_at,
        now=now,
        stale_after_s=cfg.observed_stale_after_s,
    )
    if reason is not None:
        raise HTTPException(409, reason)

    cmd = _new_command(inst, type_, user, key, now, cfg)
    db.add(cmd)
    superseded: list[UUID] = []
    if type_ in PRIORITY:  # passe devant : remplace ce qui augmenterait le risque
        rows = await db.scalars(
            update(Command)
            .where(
                Command.instance_id == inst.id,
                Command.type.in_(RISK_INCREASING),
                Command.status.in_(ACTIVE),
            )
            .values(status="superseded", superseded_at=now, updated_at=now)
            .returning(Command.id)
        )
        superseded = list(rows)
    before = inst.desired_state
    wanted = DESIRED_AFTER[type_]
    # Une pause ne « démarre » jamais une instance voulue arrêtée.
    if wanted is not None and not (type_ == "pause_entries" and before != "running"):
        inst.desired_state = wanted
        inst.updated_at = now
    try:
        await db.flush()
    except IntegrityError:  # même clé, demande concurrente d'une autre instance
        await db.rollback()
        again = await _replay(db, user, key, _request_hash(instance_id, type_))
        if again is None:
            raise
        return again, True
    ip = client_ip(request)
    for sid in superseded:
        await write_audit(
            db,
            actor=user.actor,
            action="command.superseded",
            target=f"command:{sid}",
            after={"status": "superseded", "by": str(cmd.id)},
            ip=ip,
        )
    await write_audit(  # en dernier : même ordre de verrous que le worker
        db,
        actor=user.actor,
        action=f"command.{type_}",
        target=f"instance:{inst.id}",
        before={"desired_state": before},
        after={"desired_state": inst.desired_state, "command_id": str(cmd.id)},
        ip=ip,
    )
    await db.commit()
    await _announce(
        redis, ("command", cmd.id), ("instance", inst.id), *(("command", s) for s in superseded)
    )
    return cmd, False


@router.post("/instances", status_code=201)
async def create_instance(
    body: InstanceCreate,
    request: Request,
    response: Response,
    user: Operator,
    db: Db,
    now: Now,
    cfg: Cfg,
    redis: Bus,
) -> InstanceOut:
    kind = body.engine
    if kind is None:  # le serveur ne choisit que s'il n'y a rien à choisir
        kinds = (await db.scalars(select(Engine.kind).distinct().limit(2))).all()
        if len(kinds) != 1:
            raise HTTPException(422, "Moteur à préciser : aucun ou plusieurs sont enregistrés.")
        kind = kinds[0]
    engine = await db.scalar(
        select(Engine).where(Engine.kind == kind).order_by(Engine.created_at, Engine.id).limit(1)
    )
    if engine is None:
        raise HTTPException(422, "Type de moteur inconnu.")
    inst = Instance(
        id=uuid7(),
        engine_id=engine.id,
        name=body.name,
        mode=body.mode,
        desired_state="exits_only",  # une instance créée démarre en sorties seules (F9)
        observed_state="unknown",
        params=body.params,
        created_at=now,
        updated_at=now,
    )
    db.add(inst)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, "Une instance porte déjà ce nom.") from None
    cmd = _new_command(inst, "deploy", user, f"deploy:{inst.id}", now, cfg)
    db.add(cmd)
    await db.flush()
    ip = client_ip(request)
    await write_audit(
        db,
        actor=user.actor,
        action="instance.create",
        target=f"instance:{inst.id}",
        after={"name": inst.name, "engine": kind, "mode": inst.mode, "params": inst.params},
        ip=ip,
    )
    await write_audit(
        db,
        actor=user.actor,
        action="command.deploy",
        target=f"instance:{inst.id}",
        after={"desired_state": inst.desired_state, "command_id": str(cmd.id)},
        ip=ip,
    )
    await db.commit()
    await _announce(redis, ("instance", inst.id), ("command", cmd.id))
    response.headers["Location"] = f"/api/v1/instances/{inst.id}"
    return InstanceOut.of(inst, engine.kind, cmd, now, cfg.observed_stale_after_s)


def _action(slug: str, type_: ActionType) -> None:
    @router.post(f"/instances/{{instance_id}}/{slug}", status_code=202, name=type_)
    async def act(
        instance_id: UUID,
        request: Request,
        response: Response,
        user: Operator,
        db: Db,
        now: Now,
        cfg: Cfg,
        redis: Bus,
        idempotency_key: IdempotencyKey,
    ) -> CommandAccepted:
        cmd, replayed = await request_command(
            db, redis, request, user, instance_id, type_, idempotency_key, now, cfg
        )
        if replayed:
            response.headers["Idempotency-Replayed"] = "true"
        response.headers["Location"] = f"/api/v1/commands/{cmd.id}"
        return CommandAccepted(command_id=cmd.id, command=CommandOut.of(cmd, now))


for _slug, _type in (
    ("start", "start"),
    ("stop", "stop"),
    ("pause-entries", "pause_entries"),
    ("resume-entries", "resume_entries"),
    ("flatten", "flatten"),
):
    _action(_slug, _type)  # type: ignore[arg-type]


@router.get("/commands")
async def list_commands(
    _: Viewer,
    db: Db,
    now: Now,
    instance_id: UUID | None = None,
    status: Annotated[list[Status] | None, Query()] = None,  # répétable : ?status=a&status=b
    cursor: str | None = None,
    limit: Limit = 50,
) -> Page[CommandOut]:
    stmt = select(Command)
    if instance_id is not None:
        stmt = stmt.where(Command.instance_id == instance_id)
    if status:
        stmt = stmt.where(Command.status.in_(status))
    if (at := _page_args(cursor)) is not None:
        stmt = stmt.where(tuple_(Command.requested_at, Command.id) < tuple_(*at))
    rows = (
        await db.scalars(
            stmt.order_by(Command.requested_at.desc(), Command.id.desc()).limit(limit + 1)
        )
    ).all()
    page = rows[:limit]
    nxt = encode_cursor(page[-1].requested_at, page[-1].id) if len(rows) > limit else None
    return Page(items=[CommandOut.of(c, now) for c in page], next_cursor=nxt, server_time=now)


@router.get("/commands/{command_id}")
async def get_command(command_id: UUID, _: Viewer, db: Db, now: Now) -> CommandOut:
    cmd = await db.get(Command, command_id)
    if cmd is None:
        raise HTTPException(404, "Commande inconnue.")
    return CommandOut.of(cmd, now)
