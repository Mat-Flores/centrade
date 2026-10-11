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
from centrade_core.bus import EVENTS_STREAM, HEARTBEAT_KEY, Bus
from centrade_core.engine.contract import EngineAdapter, EngineUnreachable
from centrade_core.engine.types import InstanceRef
from centrade_core.events import CanonicalEvent
from centrade_core.ids import uuid7
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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

    def register(self, ref: InstanceRef) -> None:
        """L'instance (déjà présente dans `instances`) est suivie à partir du prochain tour."""
        if ref.engine not in self._adapters:
            raise KeyError(f"aucun adaptateur pour le moteur {ref.engine!r}")
        self._refs[ref.instance_id] = ref

    async def run_once(self) -> None:
        tour = log.bind(correlation_id=str(uuid7()))
        await self._bus.ensure_group(EVENTS_STREAM)
        await self._publish_events(tour)
        await self._consume(tour)
        for iid, ref in self._refs.items():
            await self._resync(tour.bind(instance_id=str(iid)), ref)
        # Seulement si le tour entier a abouti : une clé absente = un worker qui ne progresse plus.
        await self._redis.set(
            HEARTBEAT_KEY, self._clock().isoformat(), ex=self._cfg.heartbeat_ttl_s
        )

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

    async def _resync(self, tour: structlog.stdlib.BoundLogger, ref: InstanceRef) -> None:
        reason = self._anomalies.pop(ref.instance_id, "poll")
        adapter = self._adapters[ref.engine]
        try:
            async with asyncio.timeout(self._cfg.engine_silent_after_s):
                status = await adapter.status(ref)
                snap = await adapter.snapshot(ref)
        except (EngineUnreachable, TimeoutError):
            async with self._sessions.begin() as s:
                alerted = await mark_unknown(s, ref.instance_id, self._clock())
            tour.warning("moteur_injoignable", reason=reason, alert_created=alerted)
            return
        async with self._sessions.begin() as s:
            await apply_observation(s, ref.instance_id, status, snap)
        tour.info("resynchronisation", reason=reason, state=status.state)


def install_stop_signals(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
