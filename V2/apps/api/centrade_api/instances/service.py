"""Reading and preparing instances: output views, drifts, creation from the registry."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from centrade_core.commands import (
    ACTIVE,
)
from centrade_core.engine.types import Manifest
from centrade_core.models.trading import (
    Account,
    BalanceSnapshot,
    Command,
    Engine,
    Instance,
    Position,
    Strategy,
    StrategyVersion,
    Trade,
)
from centrade_core.settings import Settings
from fastapi import HTTPException
from sqlalchemy import Row, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from centrade_api.instances.schemas import (
    AccountRef,
    BalanceOut,
    DriftItem,
    InstanceCreate,
    InstanceOut,
    Money,
    StrategyRef,
)
from centrade_api.strategies.checks import CHECKS
from centrade_api.trading.projections import _dec

# Outer joins: the last three columns may be None despite the declared types.
ListingRow = Row[Instance, str, StrategyVersion, str, Account]


def listing() -> Select[Instance, str, StrategyVersion, str, Account]:
    """Instance, engine type, strategy version, strategy name and account: outer joins, one
    query for a whole page. The version's code and manifest are never read here."""
    return (
        select(Instance, Engine.kind, StrategyVersion, Strategy.name, Account)
        .join(Engine, Engine.id == Instance.engine_id)
        .outerjoin(StrategyVersion, StrategyVersion.id == Instance.strategy_version_id)
        .outerjoin(Strategy, Strategy.id == StrategyVersion.strategy_id)
        .outerjoin(Account, Account.id == Instance.account_id)
        .options(
            defer(StrategyVersion.code, raiseload=True),
            defer(StrategyVersion.manifest, raiseload=True),
            defer(StrategyVersion.static_checks, raiseload=True),
        )
    )


def _strategy(v: StrategyVersion | None, name: str | None) -> StrategyRef | None:
    if v is None or name is None:
        return None
    return StrategyRef(
        version_id=v.id,
        strategy_id=v.strategy_id,
        name=name,
        version=v.version,
        status=v.status,
        code_hash=v.code_hash,
        exits=v.exits,
    )


async def instances_out(
    db: AsyncSession, rows: Sequence[ListingRow], now: datetime, cfg: Settings
) -> list[InstanceOut]:
    """Rows of `listing()`. A fixed number of queries, whatever the number of rows."""
    ids = [r[0].id for r in rows]
    active: dict[UUID, Command] = {}
    starts: dict[UUID, datetime] = {}
    money: dict[UUID, list[Money]] = defaultdict(list)
    closed: dict[UUID, int] = defaultdict(int)
    held_n: dict[UUID, int] = {}
    held_at: dict[UUID, datetime] = {}
    balances: dict[UUID, list[BalanceOut]] = defaultdict(list)
    balances_at: dict[UUID, datetime] = {}
    if ids:
        cmds = await db.scalars(
            select(Command)
            .where(Command.instance_id.in_(ids), Command.status.in_(ACTIVE))
            .order_by(Command.requested_at, Command.id)
        )
        active = {c.instance_id: c for c in cmds}  # the most recent wins
        verified = await db.execute(
            select(Command.instance_id, func.max(Command.verified_at))
            .where(
                Command.instance_id.in_(ids),
                Command.type.in_(("deploy", "start")),
                Command.status == "verified",
            )
            .group_by(Command.instance_id)
        )
        starts = {iid: at for iid, at in verified if at is not None}
        sums = await db.execute(
            select(
                Trade.instance_id, Trade.currency, func.sum(Trade.pnl), func.sum(Trade.fees),
                func.count(),
            )
            .where(Trade.instance_id.in_(ids))
            .group_by(Trade.instance_id, Trade.currency)
            .order_by(Trade.instance_id, Trade.currency)
        )  # fmt: skip
        for iid, currency, pnl, fees, n in sums:
            money[iid].append(Money(currency=currency, amount=_dec(pnl), fees=_dec(fees)))
            closed[iid] += n
        held = await db.execute(
            select(Position.instance_id, func.count(), func.max(Position.observed_at))
            .where(Position.instance_id.in_(ids))
            .group_by(Position.instance_id)
        )
        for iid, n, at in held:
            held_n[iid], held_at[iid] = n, at
        cash = await db.scalars(
            select(BalanceSnapshot)
            .where(BalanceSnapshot.instance_id.in_(ids))
            .order_by(BalanceSnapshot.instance_id, BalanceSnapshot.currency)
        )
        for b in cash:
            balances[b.instance_id].append(
                BalanceOut(currency=b.currency, free=_dec(b.free), total=_dec(b.total))
            )
            # The oldest row dates the whole list: the prudent side (I1).
            oldest = balances_at.get(b.instance_id, b.observed_at)
            balances_at[b.instance_id] = min(oldest, b.observed_at)
    return [
        InstanceOut.of(
            i,
            kind,
            active.get(i.id),
            now,
            cfg.observed_stale_after_s,
            strategy=_strategy(version, name),
            account=None if acc is None else AccountRef.model_validate(acc, from_attributes=True),
            last_start=starts.get(i.id),
            money=money.get(i.id, []),
            closed=closed.get(i.id, 0),
            positions=held_n.get(i.id, 0),
            positions_seen=held_at.get(i.id),
            balances=balances.get(i.id, []),
            balances_seen=balances_at.get(i.id),
        )
        for i, kind, version, name, acc in rows
    ]


async def instance_out(
    db: AsyncSession, instance_id: UUID, now: datetime, cfg: Settings
) -> InstanceOut | None:
    row = (await db.execute(listing().where(Instance.id == instance_id))).one_or_none()
    return (await instances_out(db, [row], now, cfg))[0] if row else None


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
