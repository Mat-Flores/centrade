"""Worker : porte les adaptateurs, publie leurs événements, les ingère, tient les projections.

Un tour (`run_once`) : envoi des commandes -> événements (bus, ingestion) -> relevé de chaque
instance (état + instantané) -> vérification de F9 (démarrage observé, puis cadence) ->
vérification des commandes -> battement. Chaque étape est isolée :
une panne (bus, base, un moteur) n'empêche ni l'envoi d'une commande ni le relevé des autres
instances (I4). Aucun sommeil ici : `run` dort entre deux tours, les tests appellent `run_once`
avec une horloge injectée.

Indépendance (I9) : au démarrage, les conteneurs en marche sont rattachés sans être redémarrés
et sans qu'aucune commande parte vers un moteur ; à l'arrêt, le worker ne touche à rien.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from typing import Protocol
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

from centrade_worker.commands import Commands, Observation
from centrade_worker.guard import Guard, raise_alert
from centrade_worker.ingest import ingest
from centrade_worker.projection import apply_observation, mark_unknown
from centrade_worker.runner import RunnerContainer

log = structlog.get_logger("worker")


class Containers(Protocol):
    """Ce que le worker demande au runner : lister ce qui tourne. Rien d'autre (I9)."""

    async def adopt(self) -> list[RunnerContainer]: ...


@dataclass(frozen=True)
class WorkerConfig:
    interval_s: float = 1.0
    # Un moteur qui ne répond pas dans ce délai est muet : état `unknown`.
    engine_silent_after_s: float = 30.0
    heartbeat_ttl_s: int = 15
    batch: int = 100
    # Une instance inchangée est quand même notifiée à cette cadence : sa date d'observation avance.
    refresh_notify_s: float = 10.0
    # Fraîcheur exigée du relevé fait juste avant d'envoyer ce qui augmente le risque (I5).
    stale_after_s: float = 30.0
    # Cadence de la vérification de F9 hors démarrage (§13 : dérive et écart de mode détectés
    # en 60 s ; la moitié laisse la marge d'un tour et d'une relecture).
    verify_every_s: float = 30.0
    # Échéance de la pause envoyée d'office après un écart (réglage `deadline_pause_entries_s`).
    pause_deadline_s: float = 10.0


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
        runner: Containers | None = None,
        simulated: frozenset[str] = frozenset(),
    ) -> None:
        self._adapters = adapters
        self._sessions = sessions
        self._redis = redis
        self._bus = bus
        self._clock = clock
        self._cfg = config
        self._runner = runner
        # Moteurs tenus en mémoire par ce processus : seuls redéployés au démarrage.
        self._simulated = simulated
        self._refs: dict[UUID, InstanceRef] = {}
        self._anomalies: dict[UUID, str] = {}
        self._notes: list[tuple[str, UUID]] = []  # changements validés, notifiés en fin de tour
        self._last_sig: dict[UUID, tuple[tuple[object, ...], datetime]] = {}

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
        """L'instance (déjà présente dans `instances`) est suivie à partir du prochain tour."""
        if ref.engine not in self._adapters:
            raise KeyError(f"aucun adaptateur pour le moteur {ref.engine!r}")
        self._refs[ref.instance_id] = ref

    async def load_instances(self) -> None:
        """Au démarrage : suit les instances de la base et rattache les conteneurs en marche.
        Aucun appel à un moteur, sauf pour les moteurs simulés, qui ne survivent pas au
        processus et sont redéployés en sorties seules."""
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
                    spec = (await self.guard.target(inst.id)).spec
                    ref = await self._adapters[kind].deploy(spec)
                self.register(ref)
            except Exception:
                log.exception("instance_non_rechargee", instance_id=str(inst.id))
        if self._runner is not None:
            await self._adopt([inst for inst, _ in rows])

    async def _adopt(self, instances: list[Instance]) -> None:
        """Étiquettes Docker contre la base (F9, §10 point 7). Lecture seule côté Docker : un
        conteneur n'est ni démarré, ni arrêté, ni supprimé ici, orphelin compris."""
        assert self._runner is not None  # noqa: S101
        try:
            running = {c.instance_id: c for c in await self._runner.adopt()}
        except EngineUnreachable:
            log.warning("adoption_impossible")  # Docker injoignable : rien n'est conclu
            return
        known = {i.id: i for i in instances}
        alerts: list[UUID | None] = []
        async with self._sessions.begin() as s:
            for iid, c in running.items():  # la ligne d'instance d'abord, l'audit ensuite
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
        tour = log.bind(correlation_id=str(uuid7()))
        errors: list[Exception] = []
        observed: dict[UUID, Observation] = {}

        async def step(name: str, do: Callable[[], Awaitable[None]], **ctx: str) -> None:
            try:
                await do()
            except Exception as exc:  # l'étape suivante a lieu quand même
                tour.exception("etape_en_echec", step=name, **ctx)
                errors.append(exc)

        async def observe(ref: InstanceRef) -> None:
            obs = await self._resync(tour.bind(instance_id=str(ref.instance_id)), ref)
            if obs is not None:
                observed[ref.instance_id] = obs

        async def verify_f9(ref: InstanceRef) -> None:
            obs = observed[ref.instance_id]
            if await self.guard.check(ref, obs.status) == ():
                observed[ref.instance_id] = replace(obs, conform=True)

        try:
            # Les commandes d'abord : ni le bus ni un lot d'événements ne retardent une pause.
            # Seul ce qui augmente le risque peut périmer avant de partir.
            await step("expiration_avant_envoi", lambda: self._commands.expire(("requested",)))
            await step("envoi", self._commands.dispatch)
            await step("publication", lambda: self._publish_events(tour))
            await step("ingestion", lambda: self._consume(tour))
            for iid, ref in list(self._refs.items()):
                await step("releve", partial(observe, ref), instance_id=str(iid))
            for iid in list(observed):
                await step(
                    "verification_f9", partial(verify_f9, self._refs[iid]), instance_id=str(iid)
                )
            if self.guard.pause_requested:  # la pause d'office part dans le même tour
                self.guard.pause_requested = False
                await step("envoi_des_pauses", self._commands.dispatch)
            await step("verification", lambda: self._commands.verify(observed))
            await step("expiration", self._commands.expire_all)
            if errors:
                raise errors[0]  # tour incomplet : pas de battement, l'API voit un worker figé
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
        # Bus en panne : on échoue ici, avant de vider la boîte d'envoi d'un moteur.
        await self._bus.ensure_group(EVENTS_STREAM)
        for iid, ref in self._refs.items():
            try:
                async with asyncio.timeout(self._cfg.engine_silent_after_s):
                    async for ev in self._adapters[ref.engine].events(ref):
                        await self._bus.publish(EVENTS_STREAM, ev.model_dump_json())
            except (EngineUnreachable, CommandRejected, TimeoutError):
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
                if res.order_id is not None:
                    self._notes.append(("order", res.order_id))
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
        except (EngineUnreachable, CommandRejected, TimeoutError):
            # Un moteur qui ne connaît pas l'instance ne dit rien de son état : inconnu aussi.
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
            written = await apply_observation(s, ref.instance_id, status, snap)
        self._notes.extend(n for n in written if n[0] == "alert")
        # Positions et ordres : annoncés quand le relevé change, puis à la cadence de l'instance
        # (leur date d'observation avance) ; jamais à chaque tour.
        sig = (status.state, status.mode, snap.positions, snap.orders, snap.stops)
        if self._note_instance(ref.instance_id, sig):
            self._notes.extend(n for n in written if n[0] != "alert")
        tour.info("resynchronisation", reason=reason, state=status.state)
        return Observation(status, snap)

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
