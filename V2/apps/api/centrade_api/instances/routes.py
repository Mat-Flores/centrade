"""Routes of instances and commands (SPEC F9, §8).

An action route answers 202: the command is recorded, not yet executed (I8).
No route creates an order (SPEC §8).
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal
from uuid import UUID

from centrade_core.audit import write_audit
from centrade_core.commands import (
    Status,
)
from centrade_core.ids import uuid7
from centrade_core.models.trading import (
    Command,
    Engine,
    Instance,
    StrategyVersion,
)
from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError

from centrade_api.auth import Operator, Viewer
from centrade_api.core.deps import (
    Bus,
    Cfg,
    Db,
    IdempotencyKey,
    Limit,
    Now,
    OptionalKey,
    client_ip,
)
from centrade_api.core.observed import observe
from centrade_api.core.pagination import Page, encode_cursor, page_args
from centrade_api.instances.commands import announce, find_replay, new_command, request_command
from centrade_api.instances.schemas import (
    CommandAccepted,
    CommandOut,
    InstanceCreate,
    InstanceDetail,
    InstanceOut,
)
from centrade_api.instances.service import (
    drift_items,
    from_registry,
    instance_out,
    instances_out,
    listing,
)

router = APIRouter(prefix="/api/v1", tags=["instances"])

ActionType = Literal["start", "stop", "pause_entries", "resume_entries", "flatten"]


@router.get("/instances")
async def list_instances(
    _: Viewer,
    db: Db,
    now: Now,
    cfg: Cfg,
    strategy_id: UUID | None = None,
    cursor: str | None = None,
    limit: Limit = 50,
) -> Page[InstanceOut]:
    stmt = listing()
    if strategy_id is not None:  # on the outer join: instances without a version drop out
        stmt = stmt.where(StrategyVersion.strategy_id == strategy_id)
    if (at := page_args(cursor)) is not None:
        stmt = stmt.where(tuple_(Instance.created_at, Instance.id) < tuple_(*at))
    rows = (
        await db.execute(
            stmt.order_by(Instance.created_at.desc(), Instance.id.desc()).limit(limit + 1)
        )
    ).all()
    more = len(rows) > limit
    page = rows[:limit]
    nxt = encode_cursor(page[-1][0].created_at, page[-1][0].id) if more else None
    return Page(items=await instances_out(db, page, now, cfg), next_cursor=nxt, server_time=now)


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: UUID, _: Viewer, db: Db, now: Now, cfg: Cfg) -> InstanceDetail:
    out = await instance_out(db, instance_id, now, cfg)
    inst = await db.get(Instance, instance_id)
    if out is None or inst is None:
        raise HTTPException(404, "Instance inconnue.")
    at, stale = inst.effective_config_at, cfg.observed_stale_after_s
    seen = at is not None and inst.effective_config is not None
    version = (inst.effective_config or {}).get("engine_version") if seen else None
    return InstanceDetail(
        **out.model_dump(),
        engine_version=observe(version if isinstance(version, str) else None, at, now, stale),
        deployment_fingerprint=inst.deployment_fingerprint,
        config_hash=inst.config_hash,
        effective_config=observe(inst.effective_config if seen else None, at, now, stale),
        drift=observe(drift_items(inst.drift) if seen else None, at, now, stale),
    )


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
    idempotency_key: OptionalKey = None,
) -> InstanceOut:
    body_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()

    async def replayed() -> InstanceOut | None:
        if idempotency_key is None:
            return None
        prior = await find_replay(db, user, idempotency_key, body_hash)
        out = None if prior is None else await instance_out(db, prior.instance_id, now, cfg)
        if out is not None:
            response.status_code = 200
            response.headers["Idempotency-Replayed"] = "true"
            response.headers["Location"] = f"/api/v1/instances/{out.id}"
        return out

    if (again := await replayed()) is not None:
        return again
    version = account = None
    if body.strategy_version_id is not None:
        engine, version, account = await from_registry(db, body)
        kind = engine.kind
    else:
        wanted = body.engine
        if wanted is None:  # the server chooses only when there is nothing to choose
            kinds = (await db.scalars(select(Engine.kind).distinct().limit(2))).all()
            if len(kinds) != 1:
                raise HTTPException(422, "Moteur à préciser : aucun ou plusieurs sont enregistrés.")
            wanted = kinds[0]
        found = await db.scalar(
            select(Engine)
            .where(Engine.kind == wanted)
            .order_by(Engine.created_at, Engine.id)
            .limit(1)
        )
        if found is None:
            raise HTTPException(422, "Type de moteur inconnu.")
        engine, kind = found, wanted
    inst = Instance(
        id=uuid7(),
        engine_id=engine.id,
        name=body.name,
        mode=body.mode,
        desired_state="exits_only",  # a created instance starts in exits-only (F9)
        observed_state="unknown",
        params=body.params,
        strategy_version_id=version.id if version else None,
        account_id=account.id if account else None,
        created_at=now,
        updated_at=now,
    )
    db.add(inst)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, "Une instance porte déjà ce nom.") from None
    cmd = new_command(inst, "deploy", user, idempotency_key or f"deploy:{inst.id}", now, cfg)
    cmd.request_hash = body_hash
    db.add(cmd)
    try:
        await db.flush()
    except IntegrityError:  # same key, concurrent request
        await db.rollback()
        if (again := await replayed()) is not None:
            return again
        raise
    ip = client_ip(request)
    await write_audit(
        db,
        actor=user.actor,
        action="instance.create",
        target=f"instance:{inst.id}",
        after={
            "name": inst.name,
            "engine": kind,
            "mode": inst.mode,
            "params": inst.params,
            # creation from the registry only: the M1 fingerprint stays unchanged
            **(
                {"strategy_version_id": str(version.id), "account_id": str(account.id)}
                if version and account
                else {}
            ),
        },
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
    await announce(redis, ("instance", inst.id), ("command", cmd.id))
    response.headers["Location"] = f"/api/v1/instances/{inst.id}"
    out = await instance_out(db, inst.id, now, cfg)
    if out is None:  # deleted between the commit and this read
        raise HTTPException(404, "Instance inconnue.")
    return out


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
    status: Annotated[list[Status] | None, Query()] = None,  # repeatable: ?status=a&status=b
    cursor: str | None = None,
    limit: Limit = 50,
) -> Page[CommandOut]:
    stmt = select(Command)
    if instance_id is not None:
        stmt = stmt.where(Command.instance_id == instance_id)
    if status:
        stmt = stmt.where(Command.status.in_(status))
    if (at := page_args(cursor)) is not None:
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
