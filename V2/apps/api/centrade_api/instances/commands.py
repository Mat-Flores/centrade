"""Demande d'une commande (SPEC F9, I5, I8).

Demander une commande n'appelle jamais un moteur : on écrit une commande `requested`, on met à jour
l'état voulu, on audite. Le worker la relève et ne la déclare `verified` que lorsque l'effet est
observé. Une même clé d'idempotence rejouée rend la même commande, sans second effet.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from centrade_core.audit import write_audit
from centrade_core.bus import notify
from centrade_core.commands import (
    ACTIVE,
    DESIRED_AFTER,
    PRIORITY,
    RISK_INCREASING,
    risk_increase_refusal,
)
from centrade_core.ids import uuid7
from centrade_core.models.trading import (
    Command,
    Instance,
)
from centrade_core.settings import Settings
from fastapi import HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_api.auth import Principal
from centrade_api.core.deps import (
    client_ip,
)

log = structlog.get_logger()


def _request_hash(instance_id: UUID, command_type: str, args: dict[str, Any] | None = None) -> str:
    tail = "" if not args else ":" + json.dumps(args, sort_keys=True)
    return hashlib.sha256(f"{instance_id}:{command_type}{tail}".encode()).hexdigest()


def new_command(
    inst: Instance,
    type_: str,
    user: Principal,
    key: str,
    now: datetime,
    cfg: Settings,
    args: dict[str, Any] | None = None,
) -> Command:
    return Command(
        id=uuid7(),
        instance_id=inst.id,
        type=type_,
        actor=user.actor,
        idempotency_key=key,
        args=args,
        request_hash=_request_hash(inst.id, type_, args),
        status="requested",
        correlation_id=uuid7(),
        requested_at=now,
        deadline_at=now + timedelta(seconds=cfg.command_deadline_s(type_)),
        updated_at=now,
    )


async def find_replay(
    db: AsyncSession, user: Principal, key: str, request_hash: str
) -> Command | None:
    existing = await db.scalar(
        select(Command).where(Command.actor == user.actor, Command.idempotency_key == key)
    )
    if existing is not None and existing.request_hash != request_hash:
        raise HTTPException(422, "Clé d'idempotence déjà utilisée pour une autre requête.")
    return existing


async def announce(redis: Redis | None, *items: tuple[str, UUID]) -> None:
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
    args: dict[str, Any] | None = None,
) -> tuple[Command, bool]:
    """Enregistre la commande (jamais d'appel au moteur). Rend (commande, rejeu)."""
    # Verrou de ligne : les demandes d'une même instance sont sérialisées.
    inst = await db.scalar(select(Instance).where(Instance.id == instance_id).with_for_update())
    if inst is None:
        raise HTTPException(404, "Instance inconnue.")
    # SPEC §13 : `operator` n'augmente le risque qu'en paper ; tout autre mode exige `admin`.
    if type_ in RISK_INCREASING and inst.mode != "paper" and user.role != "admin":
        raise HTTPException(403, "Droits insuffisants pour cette action hors mode paper.")
    replay = await find_replay(db, user, key, _request_hash(instance_id, type_, args))
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

    cmd = new_command(inst, type_, user, key, now, cfg, args)
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
        again = await find_replay(db, user, key, _request_hash(instance_id, type_, args))
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
        after={
            "desired_state": inst.desired_state,
            "command_id": str(cmd.id),
            **({"args": args} if args else {}),
        },
        ip=ip,
    )
    await db.commit()
    await announce(
        redis, ("command", cmd.id), ("instance", inst.id), *(("command", s) for s in superseded)
    )
    return cmd, False
