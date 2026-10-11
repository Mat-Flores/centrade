"""Commandes côté worker (SPEC F9, I8) : relever, appeler l'adaptateur, vérifier l'effet, expirer.

La table `commands` sert de file (`FOR UPDATE SKIP LOCKED`) : pas de double écriture base + bus.
Une commande n'est `verified` que si un relevé postérieur à l'accusé montre l'effet du §7.
Un moteur qui ne répond pas laisse la commande `dispatched` : elle n'est jamais rejouée, elle
expire (`timed_out`, alerte). Les actions du worker sont auditées sous `system:worker` (I14).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from centrade_core.audit import SYSTEM_WORKER, write_audit
from centrade_core.commands import ACTIVE, PRIORITY, Status, transition
from centrade_core.engine.contract import EngineAdapter, EngineUnreachable
from centrade_core.engine.types import (
    Exits,
    InstanceRef,
    InstanceSpec,
    InstanceStatus,
    Manifest,
    Sizing,
    Snapshot,
)
from centrade_core.models.trading import Alert, Command, Engine, Instance
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

log = structlog.get_logger("commands")

Note = Callable[[str, UUID], None]


@dataclass(frozen=True)
class Observation:
    status: InstanceStatus
    snapshot: Snapshot


# Effet attendu de chaque commande (SPEC §7, « Confirmée quand »).
EFFECT: dict[str, Callable[[InstanceStatus, Snapshot], bool]] = {
    "deploy": lambda st, sn: st.state == "exits_only",
    "start": lambda st, sn: st.state == "exits_only",
    "stop": lambda st, sn: st.state == "stopped",
    "pause_entries": lambda st, sn: st.state == "exits_only",
    "resume_entries": lambda st, sn: st.state == "running",
    "flatten": lambda st, sn: not sn.positions,
}
# Liste blanche des méthodes d'adaptateur appelables par une commande (`deploy` à part).
_METHOD = {k: k for k in ("start", "stop", "pause_entries", "resume_entries", "flatten")}


def spec_for(inst: Instance, kind: str) -> InstanceSpec:
    """Spécification d'une instance simulée ; le manifest vient avec les stratégies (M2)."""
    manifest = Manifest(
        name=inst.name,
        engine=kind,
        version=1,
        entrypoint="-",
        asset_classes=("crypto",),
        trading_mode="spot",
        timeframes=("5m",),
        modes=("paper",),
        sizing=Sizing(stake_amount=Decimal("50"), max_open_positions=3),
        exits=Exits(stoploss=Decimal("-0.05"), stop_on_venue=True),
    )
    return InstanceSpec(
        instance_id=inst.id,
        engine=kind,
        mode="live" if inst.mode == "live" else "paper",
        account_id="paper-sim",
        manifest=manifest,
        params=inst.params,
    )


@dataclass(frozen=True)
class _Claimed:
    id: UUID
    type: str
    kind: str
    instance_id: UUID
    spec: InstanceSpec


class Commands:
    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        adapters: Mapping[str, EngineAdapter],
        clock: Callable[[], datetime],
        call_timeout_s: float,
        register: Callable[[InstanceRef], None],
        note: Note,
    ) -> None:
        self._sessions = sessions
        self._adapters = adapters
        self._clock = clock
        self._call_timeout_s = call_timeout_s
        self._register = register
        self._note = note

    async def expire(self, statuses: tuple[str, ...]) -> None:
        """Échéance dépassée sans effet observé : `timed_out`, alerte, aucune relance."""
        now = self._clock()
        async with self._sessions.begin() as s:
            due = await s.scalars(
                select(Command)
                .where(Command.status.in_(statuses), Command.deadline_at <= now)
                .with_for_update(skip_locked=True)
            )
            for cmd in due.all():
                reason = {"reason": "échéance dépassée sans effet observé"}
                if not await transition(s, cmd.id, "timed_out", now, result=reason):
                    continue
                alert = Alert(
                    rule="command_timed_out",
                    severity="critical" if cmd.type in PRIORITY else "warning",
                    target_kind="instance",
                    target_id=cmd.instance_id,
                    message=f"Commande {cmd.type} sans effet observé avant son échéance.",
                    correlation_id=cmd.correlation_id,
                    invariant="I8",
                )
                s.add(alert)
                await s.flush()
                await self._audit(s, "command.timed_out", cmd.id, cmd.status, "timed_out")
                await write_audit(
                    s,
                    actor=SYSTEM_WORKER,
                    action="alert.raised",
                    target=f"alert:{alert.id}",
                    after={"rule": alert.rule, "severity": alert.severity},
                )
                self._note("command", cmd.id)
                self._note("alert", alert.id)
                log.warning("commande_expiree", command_id=str(cmd.id), type=cmd.type)

    async def dispatch(self) -> None:
        """Relève les commandes `requested` (une à la fois par instance, sauf celles qui
        réduisent le risque), les marque `dispatched` AVANT d'appeler le moteur, puis appelle."""
        now = self._clock()
        claimed: list[_Claimed] = []
        async with self._sessions.begin() as s:
            busy = set(
                await s.scalars(
                    select(Command.instance_id).where(
                        Command.status.in_(("dispatched", "acknowledged"))
                    )
                )
            )
            rows = (
                await s.execute(
                    select(Command, Instance, Engine.kind)
                    .join(Instance, Instance.id == Command.instance_id)
                    .join(Engine, Engine.id == Instance.engine_id)
                    .where(Command.status == "requested")
                    .with_for_update(of=Command, skip_locked=True)
                )
            ).all()
            rows = sorted(
                rows, key=lambda r: (r[0].type not in PRIORITY, r[0].requested_at, r[0].id)
            )
            for cmd, inst, kind in rows:
                if cmd.type not in PRIORITY and cmd.instance_id in busy:
                    continue
                if await transition(s, cmd.id, "dispatched", now):
                    busy.add(cmd.instance_id)
                    claimed.append(_Claimed(cmd.id, cmd.type, kind, inst.id, spec_for(inst, kind)))
        for c in claimed:
            await self._call(c)

    async def _call(self, c: _Claimed) -> None:
        try:
            async with asyncio.timeout(self._call_timeout_s):
                adapter = self._adapters[c.kind]
                if c.type == "deploy":
                    self._register(await adapter.deploy(c.spec))
                else:
                    ref = InstanceRef(engine=c.kind, instance_id=c.instance_id)
                    await getattr(adapter, _METHOD[c.type])(ref)
        except (EngineUnreachable, TimeoutError):
            # Ni accusé ni échec : on ignore si le moteur a reçu l'ordre. Pas de rejeu.
            log.warning("commande_sans_reponse", command_id=str(c.id), type=c.type)
            return
        except Exception as exc:
            await self._finish(c.id, "failed", {"reason": f"{type(exc).__name__}: {exc}"[:200]})
            return
        await self._finish(c.id, "acknowledged")

    async def _finish(
        self, command_id: UUID, dst: Status, result: dict[str, Any] | None = None
    ) -> None:
        async with self._sessions.begin() as s:
            if await transition(s, command_id, dst, self._clock(), result=result):
                if dst == "failed":
                    await self._audit(s, "command.failed", command_id, "dispatched", dst, result)
                    log.warning("commande_en_echec", command_id=str(command_id), **(result or {}))
                self._note("command", command_id)

    async def verify(self, observed: Mapping[UUID, Observation]) -> None:
        """`verified` seulement si un relevé postérieur à l'accusé montre l'effet attendu."""
        now = self._clock()
        async with self._sessions.begin() as s:
            acked = await s.scalars(
                select(Command)
                .where(Command.status == "acknowledged")
                .with_for_update(skip_locked=True)
            )
            for cmd in acked.all():
                obs = observed.get(cmd.instance_id)
                effect = EFFECT.get(cmd.type)
                if obs is None or effect is None or cmd.acknowledged_at is None:
                    continue
                if obs.status.observed_at < cmd.acknowledged_at or not effect(
                    obs.status, obs.snapshot
                ):
                    continue
                if await transition(s, cmd.id, "verified", now):
                    await self._audit(s, "command.verified", cmd.id, "acknowledged", "verified")
                    self._note("command", cmd.id)

    async def expire_all(self) -> None:
        await self.expire(ACTIVE)

    @staticmethod
    async def _audit(
        s: AsyncSession,
        action: str,
        command_id: UUID,
        before: str,
        after: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        await write_audit(
            s,
            actor=SYSTEM_WORKER,
            action=action,
            target=f"command:{command_id}",
            before={"status": before},
            after={"status": after, **(detail or {})},
        )
