"""Worker : porte les adaptateurs, publie leurs événements, les ingère, tient les projections.

Un tour (`run_once`) : relève les événements -> bus -> ingestion -> relevé de chaque instance
(état + instantané) -> battement. Aucun sommeil ici : `run` dort entre deux tours, les tests
appellent `run_once` avec une horloge injectée.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog
from centrade_core.bus import EVENTS_STREAM, HEARTBEAT_KEY, Bus, notify
from centrade_core.engine.contract import EngineAdapter, EngineUnreachable
from centrade_core.engine.types import InstanceRef
from centrade_core.events import CanonicalEvent
from centrade_core.ids import uuid7
from centrade_core.models.trading import Engine, Instance
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from centrade_worker.commands import Commands, Observation, spec_for
from centrade_worker.ingest import ingest
from centrade_worker.projection import apply_observation, mark_unknown

log = structlog.get_logger("worker")


@dataclass(frozen=True)
class WorkerConfig:
    interval_s: float = 1.0
    # Un moteur qui ne répond pas dans ce délai est muet : état `unknown`.
    engine_silent_after_s: float = 30.0
    heartbeat_ttl_s: int = 15
    batch: int = 100
    # Une instance inchangée est quand même notifiée à cette cadence : sa date d'observation avance.
    refresh_notify_s: float = 10.0


class Worker:
    def __init__(
        self,
        *,
        adapters: Mapping[str, EngineAdapter],
        sessions: async_sessionmaker[AsyncSession],
        redis: Redis,
        bus: Bus,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        config: WorkerConfig = WorkerConfig(),  # noqa: B008 - dataclass figée
    ) -> None:
        self._adapters = adapters
        self._sessions = sessions
        self._redis = redis
        self._bus = bus
        self._clock = clock
        self._cfg = config
        self._refs: dict[UUID, InstanceRef] = {}
        self._anomalies: dict[UUID, str] = {}
        self._notes: list[tuple[str, UUID]] = []  # changements validés, notifiés en fin de tour
        self._last_sig: dict[UUID, tuple[tuple[object, ...], datetime]] = {}
        self._commands = Commands(
            sessions=sessions,
            adapters=adapters,
            clock=clock,
            call_timeout_s=config.engine_silent_after_s,
            register=self.register,
            note=lambda kind, ident: self._notes.append((kind, ident)),
        )

    def register(self, ref: InstanceRef) -> None:
        """L'instance (déjà présente dans `instances`) est suivie à partir du prochain tour."""
        if ref.engine not in self._adapters:
            raise KeyError(f"aucun adaptateur pour le moteur {ref.engine!r}")
        self._refs[ref.instance_id] = ref

    async def load_instances(self) -> None:
        """Au démarrage : recharge les instances de la base et les enregistre."""
        async with self._sessions() as s:
            rows = (
                await s.execute(
                    select(Instance, Engine.kind).join(Engine, Engine.id == Instance.engine_id)
                )
            ).all()
        for inst, kind in rows:
            try:
                # Le FakeEngine ne survit pas au processus : redéployé, en sorties seules.
                self.register(await self._adapters[kind].deploy(spec_for(inst, kind)))
            except Exception:
                log.exception("instance_non_rechargee", instance_id=str(inst.id))

    async def run_once(self) -> None:
        tour = log.bind(correlation_id=str(uuid7()))
        try:
            await self._bus.ensure_group(EVENTS_STREAM)
            await self._publish_events(tour)
            await self._consume(tour)
            await self._commands.expire(("requested",))  # une commande périmée ne part jamais
            await self._commands.dispatch()
            observed: dict[UUID, Observation] = {}
            for iid, ref in list(self._refs.items()):
                if (obs := await self._resync(tour.bind(instance_id=str(iid)), ref)) is not None:
                    observed[iid] = obs
            await self._commands.verify(observed)
            await self._commands.expire_all()
            # Seulement si le tour a abouti : clé absente = worker figé.
            await self._redis.set(
                HEARTBEAT_KEY, self._clock().isoformat(), ex=self._cfg.heartbeat_ttl_s
            )
        finally:  # ce qui est déjà validé en base est annoncé, même si la fin du tour échoue
            notes, self._notes = list(dict.fromkeys(self._notes)), []
            for kind, ident in notes:
                await notify(self._redis, kind, ident)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.run_once()
            except Exception:
                log.exception("tour_en_echec")  # pas de battement : l'API voit un worker figé
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self._cfg.interval_s)
        log.info("arret_propre")

    # --- étapes ---------------------------------------------------------------------------
    async def _publish_events(self, tour: structlog.stdlib.BoundLogger) -> None:
        for iid, ref in self._refs.items():
            try:
                async with asyncio.timeout(self._cfg.engine_silent_after_s):
                    async for ev in self._adapters[ref.engine].events(ref):
                        await self._bus.publish(EVENTS_STREAM, ev.model_dump_json())
            except (EngineUnreachable, TimeoutError):
                # Rien n'est inventé ; le relevé du tour dira `unknown`.
                tour.warning("evenements_indisponibles", instance_id=str(iid))

    async def _consume(self, tour: structlog.stdlib.BoundLogger) -> None:
        while msgs := await self._bus.read(EVENTS_STREAM, self._cfg.batch):
            for m in msgs:
                try:
                    ev = CanonicalEvent.model_validate_json(m.data)
                    res = await ingest(self._sessions, ev, self._clock())
                except (ValidationError, IntegrityError):
                    # Message inexploitable ou instance inconnue : le relivrer ne le réparerait pas.
                    tour.error("message_rejete", message_id=m.id)
                    await self._bus.ack(EVENTS_STREAM, m.id)
                    continue
                if res.anomaly:
                    self._anomalies[ev.instance_id] = res.anomaly
                tour.info(
                    "evenement_ingere",
                    instance_id=str(ev.instance_id),
                    seq=ev.seq,
                    new=res.new,
                    anomaly=res.anomaly,
                )
                await self._bus.ack(EVENTS_STREAM, m.id)  # après traitement réussi seulement

    async def _resync(
        self, tour: structlog.stdlib.BoundLogger, ref: InstanceRef
    ) -> Observation | None:
        reason = self._anomalies.pop(ref.instance_id, "poll")
        adapter = self._adapters[ref.engine]
        try:
            async with asyncio.timeout(self._cfg.engine_silent_after_s):
                status = await adapter.status(ref)
                snap = await adapter.snapshot(ref)
        except (EngineUnreachable, TimeoutError):
            async with self._sessions.begin() as s:
                unknown = await mark_unknown(s, ref.instance_id, self._clock())
            if unknown.alert_id is not None:
                self._notes.append(("alert", unknown.alert_id))
            self._note_instance(ref.instance_id, ("unknown",))
            tour.warning(
                "moteur_injoignable", reason=reason, alert_created=unknown.alert_id is not None
            )
            return None
        async with self._sessions.begin() as s:
            resolved = await apply_observation(s, ref.instance_id, status, snap)
        self._notes.extend(("alert", a) for a in resolved)
        self._note_instance(
            ref.instance_id, (status.state, status.mode, len(snap.positions), len(snap.orders))
        )
        tour.info("resynchronisation", reason=reason, state=status.state)
        return Observation(status, snap)

    def _note_instance(self, iid: UUID, sig: tuple[object, ...]) -> None:
        now = self._clock()
        last = self._last_sig.get(iid)
        age = None if last is None else (now - last[1]).total_seconds()
        if last is None or last[0] != sig or (age or 0) >= self._cfg.refresh_notify_s:
            self._notes.append(("instance", iid))
            self._last_sig[iid] = (sig, now)


def install_stop_signals(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
