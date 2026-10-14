"""Reading and preparing instances: output views, drifts, creation from the registry."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from centrade_core.commands import (
    ACTIVE,
)
from centrade_core.engine.types import Manifest
from centrade_core.models.trading import (
    Account,
    Command,
    Engine,
    Instance,
    StrategyVersion,
)
from centrade_core.settings import Settings
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_api.instances.schemas import (
    DriftItem,
    InstanceCreate,
    InstanceOut,
)
from centrade_api.strategies.checks import CHECKS


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
        active = {c.instance_id: c for c in cmds}  # the most recent wins
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


def drift_items(raw: Any) -> list[DriftItem]:
    """`instances.drift`: list of {key, expected, observed}."""
    if not raw:
        return []
    return [DriftItem.model_validate(x) for x in raw]


async def from_registry(
    db: AsyncSession, body: InstanceCreate
) -> tuple[Engine, StrategyVersion, Account]:
    """Version, account and engine of a creation from the registry; refuse on any doubt."""
    version = await db.get(StrategyVersion, body.strategy_version_id)
    account = await db.get(Account, body.account_id)
    if version is None or account is None:
        raise HTTPException(422, "Version de stratégie ou compte inconnu.")
    if version.status == "retired":
        raise HTTPException(409, "Cette version de stratégie est retirée.")
    if account.type != "paper":  # live goes through promotion (F1), never through here (I3)
        raise HTTPException(409, "Seul un compte paper peut recevoir une instance créée ici.")
    manifest = Manifest.model_validate(version.manifest)
    if "paper" not in manifest.modes:
        raise HTTPException(422, "Cette version ne déclare pas le mode paper.")
    if body.engine is not None and body.engine != manifest.engine:
        raise HTTPException(422, "Le moteur demandé n'est pas celui de la version.")
    checks = CHECKS.get(manifest.engine)
    engine = await db.scalar(
        select(Engine).where(Engine.kind == manifest.engine).order_by(Engine.created_at).limit(1)
    )
    if checks is None or engine is None:
        raise HTTPException(422, "Type de moteur inconnu.")
    result = checks.validate(manifest, body.params)
    if not result.ok:
        raise HTTPException(422, "Paramètres refusés : " + " ; ".join(result.errors))
    return engine, version, account
