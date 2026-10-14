"""Worker-side commands (SPEC F9, I8): claim, call the adapter, verify the effect, expire.

The `commands` table serves as the queue (`FOR UPDATE SKIP LOCKED`): no database + bus double write.
A command is `verified` only if a snapshot later than the acknowledgement shows the §7 effect.
An engine that does not answer leaves the command `dispatched`: it is never replayed, it
expires (`timed_out`, alert). Worker actions are audited under `system:worker` (I14).

Asymmetry (I4, I5): what reduces risk never expires before being sent, and its deadline
runs from sending; what increases it goes through the F9 verification (`guard`) on a fresh
snapshot just before sending, and is not sent at the slightest doubt.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from centrade_core.audit import SYSTEM_WORKER, write_audit
from centrade_core.commands import (
    ACTIVE,
    PRIORITY,
    RISK_REDUCING,
    Status,
    transition,
)
from centrade_core.engine.contract import CommandRejected, EngineAdapter, EngineUnreachable
from centrade_core.engine.types import InstanceRef, InstanceStatus, Snapshot
from centrade_core.models.trading import Alert, Command, Engine, Instance
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from centrade_worker.guard import Guard

log = structlog.get_logger("commands")

Note = Callable[[str, UUID], None]


@dataclass(frozen=True)
class Observation:
    status: InstanceStatus
    snapshot: Snapshot
    # F9 verification passed on this snapshot. False until it has happened.
    conform: bool = False


_Args = Mapping[str, Any]
# Expected effect of each command (SPEC §7, "Confirmed when").
EFFECT: dict[str, Callable[[Observation, _Args], bool]] = {
    "deploy": lambda o, a: o.status.state == "exits_only" and o.conform,
    "start": lambda o, a: o.status.state == "exits_only",
    "stop": lambda o, a: o.status.state == "stopped",
    "pause_entries": lambda o, a: o.status.state == "exits_only",
    "resume_entries": lambda o, a: o.status.state == "running",
    "flatten": lambda o, a: not o.snapshot.positions,
    "close_position": lambda o, a: (
        a.get("position_id") not in {p.position_id for p in o.snapshot.positions}
    ),
    "cancel_entry_order": lambda o, a: (
        a.get("order_id") not in {x.order_id for x in o.snapshot.orders}
    ),
}
# Whitelist of adapter methods callable without arguments (`deploy` and the two
# commands with an argument are handled separately).
_METHOD = {k: k for k in ("start", "stop", "pause_entries", "resume_entries", "flatten")}
# Never held behind another command of the same instance (F9, "Asymmetry").
_IMMEDIATE = PRIORITY | {"close_position", "cancel_entry_order"}


@dataclass(frozen=True)
class _Claimed:
    id: UUID
    type: str
    kind: str
    instance_id: UUID
    mode: str
    args: _Args
    correlation_id: UUID


def _arg(c: _Claimed, name: str) -> str:
    value = c.args.get(name)
    if not isinstance(value, str) or not value:
        raise CommandRejected(f"argument {name} manquant")
    return value


class Commands:
    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        adapters: Mapping[str, EngineAdapter],
        clock: Callable[[], datetime],
        call_timeout_s: float,
        guard: Guard,
        register: Callable[[InstanceRef], None],
        note: Note,
    ) -> None:
        self._sessions = sessions
        self._adapters = adapters
        self._clock = clock
        self._call_timeout_s = call_timeout_s
        self._guard = guard
        self._register = register
        self._note = note

    async def expire(self, statuses: tuple[str, ...]) -> None:
        """Deadline passed with no observed effect: `timed_out`, alert, no retry.
        A command that reduces risk does not expire until it has been sent (I4)."""
        now = self._clock()
        async with self._sessions.begin() as s:
            due = await s.scalars(
                select(Command)
                .where(
                    Command.status.in_(statuses),
                    Command.deadline_at <= now,
                    or_(Command.status != "requested", Command.type.not_in(RISK_REDUCING)),
                )
                .with_for_update(skip_locked=True)
            )
            for cmd in due.all():
                reason = {"reason": "échéance dépassée sans effet observé"}
                before = cmd.status  # read beforehand: the transition updates the object
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
                await self._audit(s, "command.timed_out", cmd.id, before, "timed_out")
                await write_audit(
                    s,
                    actor=SYSTEM_WORKER,
                    action="alert.raised",
                    target=f"alert:{alert.id}",
                    after={"rule": alert.rule, "severity": alert.severity},
                )
                self._note("command", cmd.id)
                self._note("alert", alert.id)
                log.warning("command_expired", command_id=str(cmd.id), type=cmd.type)

    async def claim(
        self, only: UUID | None = None, skip: Collection[UUID] = ()
    ) -> dict[UUID, list[_Claimed]]:
        """Claims the `requested` commands (one at a time per instance, except those that
        reduce risk) and marks them `dispatched` BEFORE any engine call. Returns, per
        instance, the queue to send in order: what is never held comes first (I4).
        `only`: this instance only; `skip`: instances with a send still in progress,
        their commands stay `requested` (no deadline runs without a send)."""
        now = self._clock()
        claimed: dict[UUID, list[_Claimed]] = {}
        async with self._sessions.begin() as s:
            busy = set(
                await s.scalars(
                    select(Command.instance_id).where(
                        Command.status.in_(("dispatched", "acknowledged"))
                    )
                )
            )
            stmt = (
                select(Command, Instance, Engine.kind)
                .join(Instance, Instance.id == Command.instance_id)
                .join(Engine, Engine.id == Instance.engine_id)
                .where(Command.status == "requested")
                .with_for_update(of=Command, skip_locked=True)
            )
            if only is not None:
                stmt = stmt.where(Command.instance_id == only)
            if skip:
                stmt = stmt.where(Command.instance_id.not_in(skip))
            rows = sorted(
                (await s.execute(stmt)).all(),
                key=lambda r: (
                    r[0].type not in PRIORITY,
                    # Close and entry cancellation: never behind a resume's verification.
                    # `stop` keeps its arrival rank (one command at a time, F9).
                    r[0].type not in _IMMEDIATE,
                    r[0].requested_at,
                    r[0].id,
                ),
            )
            for cmd, inst, kind in rows:
                if cmd.type not in _IMMEDIATE and cmd.instance_id in busy:
                    continue
                if cmd.type not in RISK_REDUCING and cmd.deadline_at <= now:
                    continue  # stale: it is never sent (I5); `expire` closes it
                # Reduces risk: the deadline measures the effect, from sending (I4).
                deadline = (
                    now + (cmd.deadline_at - cmd.requested_at)
                    if cmd.type in RISK_REDUCING
                    else None
                )
                if await transition(s, cmd.id, "dispatched", now, deadline_at=deadline):
                    busy.add(cmd.instance_id)
                    claimed.setdefault(inst.id, []).append(
                        _Claimed(
                            cmd.id,
                            cmd.type,
                            kind,
                            inst.id,
                            inst.mode,
                            cmd.args or {},
                            cmd.correlation_id,
                        )
                    )
        return claimed

    async def send(self, claimed: Sequence[_Claimed]) -> None:
        """Sends ONE instance's queue, in order, one command at a time (F9). A failure
        for one command does not prevent sending the following ones."""
        failures: list[Exception] = []
        for c in claimed:
            try:
                await self._call(c)
            except Exception as exc:
                log.exception("command_untracked", command_id=str(c.id), type=c.type)
                failures.append(exc)
        if failures:
            raise failures[0]

    async def dispatch(self, only: UUID | None = None) -> None:
        """Claims then sends, instance after instance. The worker's round sends in parallel
        (`claim` then one task per instance); this serves a single instance."""
        failures: list[Exception] = []
        for batch in (await self.claim(only)).values():
            try:
                await self.send(batch)
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise failures[0]

    async def _send(self, c: _Claimed, adapter: EngineAdapter, ref: InstanceRef) -> None:
        if c.type == "deploy":
            self._register(await adapter.deploy(await self._guard.deployment(c.instance_id)))
        elif c.type == "close_position":
            await adapter.close_position(ref, _arg(c, "position_id"))
        elif c.type == "cancel_entry_order":
            order_id = _arg(c, "order_id")
            orders = (await adapter.snapshot(ref)).orders
            order = next((o for o in orders if o.order_id == order_id), None)
            if order is None:
                raise CommandRejected("ordre introuvable parmi les ordres ouverts")
            if order.intent != "entry":  # cancelling an exit or a stop increases risk (F9)
                raise CommandRejected("cet ordre n'est pas un ordre d'entrée : jamais annulé")
            await adapter.cancel_entry_order(ref, order_id)
        else:
            await getattr(adapter, _METHOD[c.type])(ref)

    async def _call(self, c: _Claimed) -> None:
        try:
            adapter = self._adapters[c.kind]
            ref = InstanceRef(engine=c.kind, instance_id=c.instance_id)
            # Empty, reading nothing, for everything that does not increase risk (I4).
            refusals = await self._guard.gate(c.type, ref, c.mode, c.correlation_id)
            if not refusals:
                async with asyncio.timeout(self._call_timeout_s):
                    await self._send(c, adapter, ref)
        except (EngineUnreachable, TimeoutError):
            # Neither ack nor failure: unknown whether the engine got the order. No replay.
            log.warning("command_unanswered", command_id=str(c.id), type=c.type)
            return
        except Exception as exc:
            await self._finish(c.id, "failed", {"reason": f"{type(exc).__name__}: {exc}"[:200]})
            return
        if refusals:  # nothing was sent to the engine
            result = {
                "reason": " ".join(r.message for r in refusals),
                "reasons": [{"code": r.code, "message": r.message} for r in refusals],
            }
            await self._finish(c.id, "failed", result)
            return
        await self._finish(c.id, "acknowledged")

    async def _finish(
        self, command_id: UUID, dst: Status, result: dict[str, Any] | None = None
    ) -> None:
        async with self._sessions.begin() as s:
            if await transition(s, command_id, dst, self._clock(), result=result):
                if dst == "failed":
                    await self._audit(s, "command.failed", command_id, "dispatched", dst, result)
                    log.warning(
                        "command_failed",
                        command_id=str(command_id),
                        reason=(result or {}).get("reason"),
                    )
                self._note("command", command_id)

    async def verify(self, observed: Mapping[UUID, Observation]) -> None:
        """`verified` only if a snapshot later than the acknowledgement shows the effect."""
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
                if obs.status.observed_at < cmd.acknowledged_at or not effect(obs, cmd.args or {}):
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
