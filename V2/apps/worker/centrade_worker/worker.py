"""Worker: carries the adapters, publishes their events, ingests them, maintains the projections.

One round (`run_once`): claims the commands, then launches ONE task per instance, in parallel:
sending its commands (what reduces risk first) -> its events (bus, ingestion) ->
its snapshot (state + snapshot) -> F9 verification -> sending its automatic pause. Then:
command verification, expiry, heartbeat. A slow, silent or failing instance delays no
other (I4, X14): the round waits for its tasks only `tick_wait_s`, the unfinished task
continues and its instance gets no other while it lasts (one command at a time per
instance, F9). The heartbeat depends on no engine. No sleep here: `run` sleeps between
rounds, tests call `run_once` with an injected clock.

Database: each write opens its own session, never shared between tasks nor held during
an engine call; the pool (5 + 10 connections) therefore queues beyond that itself.

Independence (I9): at startup, running containers are attached without being restarted
and without any command going to an engine; at shutdown, the worker touches nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol, TypeVar
from uuid import UUID

import structlog
from centrade_core.bus import EVENTS_STREAM, HEARTBEAT_KEY, Bus, notify
from centrade_core.engine.contract import CommandRejected, EngineAdapter, EngineUnreachable
from centrade_core.engine.types import InstanceRef
from centrade_core.events import CanonicalEvent
from centrade_core.ids import uuid7
from centrade_core.models.trading import Engine, Instance
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from centrade_worker.commands import Commands, Observation, _Claimed
from centrade_worker.guard import Guard, raise_alert
from centrade_worker.ingest import ingest
from centrade_worker.projection import apply_observation, mark_unknown
from centrade_worker.runner import RunnerContainer

log = structlog.get_logger("worker")
_T = TypeVar("_T")
_Log = structlog.stdlib.BoundLogger


class Containers(Protocol):
    """What the worker asks of the runner: read what runs. Nothing else (I9)."""

    async def adopt(self) -> list[RunnerContainer]: ...
    async def inspect(self, instance_id: UUID) -> RunnerContainer | None: ...


@dataclass(frozen=True)
class WorkerConfig:
    interval_s: float = 1.0
    # An engine that does not answer within this delay is silent: `unknown` state.
    engine_silent_after_s: float = 30.0
    heartbeat_ttl_s: int = 15
    batch: int = 100
    # An unchanged instance is still notified at this cadence: its observation date advances.
    refresh_notify_s: float = 10.0
    # Freshness required of the snapshot taken just before sending what increases risk (I5).
    stale_after_s: float = 30.0
    # Cadence of the F9 verification outside startup (§13: drift and mode mismatch detected
    # within 60 s; half leaves the margin of one round and one re-read).
    verify_every_s: float = 30.0
    # Deadline of the pause sent automatically after a drift (setting `deadline_pause_entries_s`).
    pause_deadline_s: float = 10.0
    # Wait for instance tasks per round. Beyond it, the round ends without them: heartbeat
    # (TTL above) and another instance's pause (10 s, §13) do not wait for a slow engine.
    tick_wait_s: float = 2.0
    # `running` engine whose configuration could not be re-read since this delay: critical
    # alert and pause (§13: drift detected within 60 s).
    unreadable_after_s: float = 60.0


class Worker:
    def __init__(
        self,
        *,
        adapters: Mapping[str, EngineAdapter],
        sessions: async_sessionmaker[AsyncSession],
        redis: Redis,
        bus: Bus,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        config: WorkerConfig = WorkerConfig(),  # noqa: B008 - frozen dataclass
        runner: Containers | None = None,
        simulated: frozenset[str] = frozenset(),
        pinned_digests: Mapping[str, str] | None = None,
        cleanup: Callable[[UUID], Awaitable[None]] | None = None,
    ) -> None:
        self._adapters = adapters
        self._sessions = sessions
        self._redis = redis
        self._bus = bus
        self._clock = clock
        self._cfg = config
        self._runner = runner
        # Engines held in memory by this process: only these are redeployed at startup.
        self._simulated = simulated
        self._refs: dict[UUID, InstanceRef] = {}
        self._anomalies: dict[UUID, str] = {}
        self._notes: list[tuple[str, UUID]] = []  # validated changes, notified at round end
        self._last_sig: dict[UUID, tuple[tuple[object, ...], datetime]] = {}
        # Removes an instance's credentials file (`InstanceRuntime.cleanup`).
        self._cleanup = cleanup
        self._cleaned: set[UUID] = set()  # observed stops already cleaned up
        self._tasks: dict[UUID, asyncio.Task[tuple[Observation | None, list[Exception]]]] = {}
        # Only one bus reader at a time: `read` resumes any unacknowledged message.
        self._ingest_lock = asyncio.Lock()
        self._ingest_error: Exception | None = None

        def note(kind: str, ident: UUID) -> None:
            self._notes.append((kind, ident))

        self.guard = Guard(
            sessions=sessions,
            adapters=adapters,
            clock=clock,
            call_timeout_s=config.engine_silent_after_s,
            stale_after_s=config.stale_after_s,
            every_s=config.verify_every_s,
            pause_deadline_s=config.pause_deadline_s,
            note=note,
            unreadable_after_s=config.unreadable_after_s,
            pinned_digests=pinned_digests,
        )
        self._commands = Commands(
            sessions=sessions,
            adapters=adapters,
            clock=clock,
            call_timeout_s=config.engine_silent_after_s,
            guard=self.guard,
            register=self.register,
            note=note,
        )

    def register(self, ref: InstanceRef) -> None:
        """The instance (already present in `instances`) is followed from the next round."""
        if ref.engine not in self._adapters:
            raise KeyError(f"aucun adaptateur pour le moteur {ref.engine!r}")
        self._refs[ref.instance_id] = ref

    async def load_instances(self) -> None:
        """At startup: follows the database's instances and attaches the running containers.
        No engine call, except for simulated engines, which do not survive the
        process and are redeployed in exits-only."""
        async with self._sessions() as s:
            rows = (
                await s.execute(
                    select(Instance, Engine.kind).join(Engine, Engine.id == Instance.engine_id)
                )
            ).all()
        for inst, kind in rows:
            try:
                ref = InstanceRef(engine=kind, instance_id=inst.id)
                if kind in self._simulated:
                    # Same path as a `deploy` command: the fingerprint is recorded (I10).
                    ref = await self._adapters[kind].deploy(await self.guard.deployment(inst.id))
                self.register(ref)
            except Exception:
                log.exception("instance_not_reloaded", instance_id=str(inst.id))
        if self._runner is not None:
            await self._adopt([inst for inst, _ in rows])

    async def _adopt(self, instances: list[Instance]) -> None:
        """Docker labels against the database (F9, §10 point 7). Read-only on the Docker side: a
        container is neither started, nor stopped, nor removed here, orphans included."""
        assert self._runner is not None  # noqa: S101
        try:
            running = {c.instance_id: c for c in await self._runner.adopt()}
        except EngineUnreachable:
            log.warning("adoption_failed")  # Docker unreachable: nothing is concluded
            return
        known = {i.id: i for i in instances}
        alerts: list[UUID | None] = []
        async with self._sessions.begin() as s:
            for iid, c in running.items():  # the instance row first, the audit after
                if iid in known and known[iid].container_ref != c.container_id:
                    await s.execute(
                        update(Instance)
                        .where(Instance.id == iid)
                        .values(container_ref=c.container_id)
                    )
            for iid, c in running.items():
                inst = known.get(iid)
                if inst is None:
                    alerts.append(
                        await raise_alert(
                            s,
                            rule="orphan_container",
                            severity="warning",
                            message=f"Conteneur orphelin {c.container_id[:12]} : étiqueté pour "
                            f"l'instance {iid}, inconnue de la base. Laissé tel quel.",
                            target_id=iid,
                            target_kind="global",
                        )
                    )
                elif c.fingerprint != (inst.deployment_fingerprint or ""):
                    alerts.append(
                        await raise_alert(
                            s,
                            rule="fingerprint_mismatch",
                            severity="warning",
                            message="L'empreinte portée par le conteneur n'est pas celle "
                            "enregistrée au déploiement (I10).",
                            target_id=iid,
                            invariant="I10",
                        )
                    )
            for inst in instances:
                if (
                    inst.container_ref is not None
                    and inst.desired_state != "stopped"
                    and inst.id not in running
                ):
                    alerts.append(
                        await raise_alert(
                            s,
                            rule="container_missing",
                            severity="critical",
                            message="Le conteneur de l'instance ne tourne plus alors qu'elle "
                            "n'est pas voulue arrêtée.",
                            target_id=inst.id,
                        )
                    )
        self._notes.extend(("alert", a) for a in alerts if a is not None)
        log.info(
            "adoption",
            running=len(running),
            attached=len(running.keys() & known.keys()),
            alerts=sum(a is not None for a in alerts),
        )

    async def run_once(self) -> None:
        tick_log = log.bind(correlation_id=str(uuid7()))
        errors: list[Exception] = []  # platform steps: without them, no heartbeat
        self._ingest_error = None

        async def step(name: str, do: Callable[[], Awaitable[_T]]) -> _T | None:
            try:
                return await do()
            except Exception as exc:  # the next step happens anyway
                tick_log.exception("step_failed", step=name)
                errors.append(exc)
                return None

        try:
            # Commands first: neither the bus nor an event batch delays a pause.
            # Only what increases risk can go stale before leaving.
            await step("expire_before_dispatch", lambda: self._commands.expire(("requested",)))
            claimed = await step("claim_commands", self._claim) or {}
            # Bus down: no engine outbox is drained this round.
            before = len(errors)
            await step("bus", lambda: self._bus.ensure_group(EVENTS_STREAM))
            bus_ok = len(errors) == before
            for iid in dict.fromkeys([*claimed, *self._refs]):
                if iid not in self._tasks:
                    self._tasks[iid] = asyncio.create_task(
                        self._instance(tick_log, iid, claimed.get(iid, ()), bus_ok)
                    )
            if self._tasks:
                await asyncio.wait(self._tasks.values(), timeout=self._cfg.tick_wait_s)
            observed: dict[UUID, Observation] = {}
            failed: list[Exception] = []  # specific to one instance: visible, no effect elsewhere
            for iid, task in list(self._tasks.items()):
                if not task.done():
                    tick_log.warning("instance_slow", instance_id=str(iid))
                    continue
                del self._tasks[iid]
                obs, errs = task.result()
                failed.extend(errs)
                if obs is not None:
                    observed[iid] = obs
            await self._ingest(tick_log)
            if self._ingest_error is not None:
                errors.append(self._ingest_error)
            await step("verification", lambda: self._commands.verify(observed))
            await step("expiration", self._commands.expire_all)
            if errors:
                raise errors[0]  # incomplete round: no heartbeat, the API sees a frozen worker
            await self._redis.set(
                HEARTBEAT_KEY, self._clock().isoformat(), ex=self._cfg.heartbeat_ttl_s
            )
            if failed:
                raise failed[0]
        finally:  # what is already committed is announced, even if the round end fails
            notes, self._notes = list(dict.fromkeys(self._notes)), []
            for kind, ident in notes:
                await notify(self._redis, kind, ident)

    async def _claim(self) -> dict[UUID, list[_Claimed]]:
        # An instance whose task is still running keeps its commands `requested`: a single
        # task sends for an instance, and no deadline runs before sending (I4).
        return await self._commands.claim(skip=tuple(self._tasks))

    async def _instance(
        self, tick_log: _Log, iid: UUID, claimed: Sequence[_Claimed], bus_ok: bool
    ) -> tuple[Observation | None, list[Exception]]:
        """ONE instance's round. Never raises: returns its snapshot and its errors."""
        instance_log = tick_log.bind(instance_id=str(iid))
        errors: list[Exception] = []

        async def step(name: str, do: Callable[[], Awaitable[_T]]) -> _T | None:
            try:
                return await do()
            except Exception as exc:  # the next step happens anyway
                instance_log.exception("step_failed", step=name)
                errors.append(exc)
                return None

        if claimed:  # before any read: nothing delays a pause (I4)
            await step("dispatch", lambda: self._commands.send(claimed))
        obs: Observation | None = None
        ref = self._refs.get(iid)  # a `deploy` may have just registered it
        if ref is not None:
            # A single delay for events and snapshot: silent => `unknown` in 30 s (§13).
            deadline = asyncio.get_running_loop().time() + self._cfg.engine_silent_after_s
            if bus_ok:
                await step("publication", lambda: self._publish_events(instance_log, ref, deadline))
                await self._ingest(instance_log)  # before the snapshot, which has the last word
            obs = await step("snapshot", lambda: self._resync(instance_log, ref, deadline))
            if obs is not None:
                status = obs.status
                if await step("f9_verification", lambda: self.guard.check(ref, status)) == ():
                    obs = replace(obs, conform=True)
                await step("cleanup", lambda: self._clean_stopped(instance_log, iid, status.state))
        if iid in self.guard.pause_requested:  # the automatic pause leaves in the same round
            self.guard.pause_requested.discard(iid)
            await step("dispatch_pauses", lambda: self._commands.dispatch(only=iid))
        return obs, errors

    async def aclose(self) -> None:
        """Abandons in-progress instance tasks. No engine is touched (I9)."""
        tasks, self._tasks = list(self._tasks.values()), {}
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.run_once()
            except Exception:
                log.exception("tick_failed")  # no heartbeat: the API sees a frozen worker
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self._cfg.interval_s)
        await self.aclose()
        log.info("clean_shutdown")

    # --- steps ----------------------------------------------------------------------------
    async def _publish_events(self, tick_log: _Log, ref: InstanceRef, deadline: float) -> None:
        try:
            async with asyncio.timeout_at(deadline):
                async for ev in self._adapters[ref.engine].events(ref):
                    await self._bus.publish(EVENTS_STREAM, ev.model_dump_json())
        except (EngineUnreachable, CommandRejected, TimeoutError):
            # Nothing is invented; the round's snapshot will say `unknown`.
            tick_log.warning("events_unavailable")

    async def _ingest(self, tick_log: _Log) -> None:
        """Ingestion, one task at a time. A failure stops ingestion until the next round
        (the unacknowledged message will be redelivered) and deprives this round of a heartbeat."""
        async with self._ingest_lock:
            if self._ingest_error is not None:
                return
            try:
                await self._consume(tick_log)
            except Exception as exc:
                tick_log.exception("step_failed", step="ingestion")
                self._ingest_error = exc

    async def _consume(self, tick_log: _Log) -> None:
        while msgs := await self._bus.read(EVENTS_STREAM, self._cfg.batch):
            for m in msgs:
                try:
                    ev = CanonicalEvent.model_validate_json(m.data)
                    res = await ingest(self._sessions, ev, self._clock())
                except (ValidationError, IntegrityError):
                    # Unusable message or unknown instance: redelivering it would not fix it.
                    tick_log.error("message_rejected", message_id=m.id)
                    await self._bus.ack(EVENTS_STREAM, m.id)
                    continue
                if res.anomaly:
                    self._anomalies[ev.instance_id] = res.anomaly
                if res.order_id is not None:
                    self._notes.append(("order", res.order_id))
                tick_log.info(
                    "event_ingested",
                    instance_id=str(ev.instance_id),
                    seq=ev.seq,
                    new=res.new,
                    anomaly=res.anomaly,
                )
                await self._bus.ack(EVENTS_STREAM, m.id)  # only after successful processing

    async def _resync(
        self, tick_log: _Log, ref: InstanceRef, deadline: float
    ) -> Observation | None:
        reason = self._anomalies.pop(ref.instance_id, "poll")
        adapter = self._adapters[ref.engine]
        try:
            async with asyncio.timeout_at(deadline):
                status = await adapter.status(ref)
                snap = await adapter.snapshot(ref)
        except Exception as exc:
            # No snapshot: the state is unknown, whatever the cause (I1). An engine that does
            # not know the instance, or whose adapter refuses the snapshot, says nothing either.
            async with self._sessions.begin() as s:
                unknown = await mark_unknown(s, ref.instance_id, self._clock())
            if unknown.alert_id is not None:
                self._notes.append(("alert", unknown.alert_id))
            self._note_instance(ref.instance_id, ("unknown",))
            tick_log.warning(
                "engine_unreachable",
                reason=reason,
                error=type(exc).__name__,
                alert_created=unknown.alert_id is not None,
            )
            if isinstance(exc, EngineUnreachable | CommandRejected | TimeoutError):
                return None
            raise  # unexpected adapter error: it stays visible
        async with self._sessions.begin() as s:
            written = await apply_observation(s, ref.instance_id, status, snap)
        self._notes.extend(n for n in written if n[0] == "alert")
        # Positions and orders: announced when the snapshot changes, then at the instance's
        # cadence (their observation date advances); never every round.
        sig = (
            status.state, status.mode, snap.positions, snap.orders, snap.stops, snap.closed,
            snap.balances,
        )  # fmt: skip
        if self._note_instance(ref.instance_id, sig):
            self._notes.extend(n for n in written if n[0] != "alert")
        tick_log.info("resync", reason=reason, state=status.state)
        return Observation(status, snap)

    async def _clean_stopped(self, tick_log: _Log, iid: UUID, state: str) -> None:
        """Observed stop without a commanded `stop` (crash): the credentials file does not stay
        on disk, it will be rewritten at the next start. Only if Docker confirms that no
        container is running or about to restart; at the slightest doubt, nothing is removed."""
        if state not in ("stopped", "error"):
            self._cleaned.discard(iid)
            return
        if self._cleanup is None or self._runner is None or iid in self._cleaned:
            return
        try:
            async with asyncio.timeout(self._cfg.engine_silent_after_s):
                c = await self._runner.inspect(iid)
        except (EngineUnreachable, TimeoutError):
            return
        if c is None or c.status in ("exited", "dead"):
            await self._cleanup(iid)
            self._cleaned.add(iid)
            tick_log.info("credentials_removed", observed_state=state)

    def _note_instance(self, iid: UUID, sig: tuple[object, ...]) -> bool:
        now = self._clock()
        last = self._last_sig.get(iid)
        age = None if last is None else (now - last[1]).total_seconds()
        if last is None or last[0] != sig or (age or 0) >= self._cfg.refresh_notify_s:
            self._notes.append(("instance", iid))
            self._last_sig[iid] = (sig, now)
            return True
        return False


def install_stop_signals(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
