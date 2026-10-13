"""Worker : porte les adaptateurs, publie leurs événements, les ingère, tient les projections.

Un tour (`run_once`) : relève les commandes, puis lance UNE tâche par instance, en parallèle :
envoi de ses commandes (ce qui réduit le risque d'abord) -> ses événements (bus, ingestion) ->
son relevé (état + instantané) -> vérification de F9 -> envoi de sa pause d'office. Puis :
vérification des commandes, expiration, battement. Une instance lente, muette ou en erreur ne
retarde aucune autre (I4, X14) : le tour n'attend ses tâches que `tick_wait_s`, la tâche
inachevée continue et son instance n'en reçoit pas d'autre tant qu'elle dure (une commande à la
fois par instance, F9). Le battement ne dépend d'aucun moteur. Aucun sommeil ici : `run` dort
entre deux tours, les tests appellent `run_once` avec une horloge injectée.

Base : chaque écriture ouvre sa propre session, jamais partagée entre tâches ni tenue pendant
un appel à un moteur ; le pool (5 + 10 connexions) fait donc lui-même la file au-delà.

Indépendance (I9) : au démarrage, les conteneurs en marche sont rattachés sans être redémarrés
et sans qu'aucune commande parte vers un moteur ; à l'arrêt, le worker ne touche à rien.
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
    """Ce que le worker demande au runner : lire ce qui tourne. Rien d'autre (I9)."""

    async def adopt(self) -> list[RunnerContainer]: ...
    async def inspect(self, instance_id: UUID) -> RunnerContainer | None: ...


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
    # Attente des tâches d'instance par tour. Au-delà, le tour se termine sans elles : battement
    # (TTL ci-dessus) et pause d'une autre instance (10 s, §13) n'attendent pas un moteur lent.
    tick_wait_s: float = 2.0
    # Moteur `running` dont la configuration n'a pas pu être relue depuis ce délai : alerte
    # critique et pause (§13 : dérive détectée en 60 s).
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
        config: WorkerConfig = WorkerConfig(),  # noqa: B008 - dataclass figée
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
        # Moteurs tenus en mémoire par ce processus : seuls redéployés au démarrage.
        self._simulated = simulated
        self._refs: dict[UUID, InstanceRef] = {}
        self._anomalies: dict[UUID, str] = {}
        self._notes: list[tuple[str, UUID]] = []  # changements validés, notifiés en fin de tour
        self._last_sig: dict[UUID, tuple[tuple[object, ...], datetime]] = {}
        # Retire le fichier d'identifiants d'une instance (`InstanceRuntime.cleanup`).
        self._cleanup = cleanup
        self._cleaned: set[UUID] = set()  # arrêts observés déjà nettoyés
        self._tasks: dict[UUID, asyncio.Task[tuple[Observation | None, list[Exception]]]] = {}
        # Un seul lecteur du bus à la fois : `read` reprend tout message non acquitté.
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
                    # Même chemin qu'une commande `deploy` : l'empreinte est enregistrée (I10).
                    ref = await self._adapters[kind].deploy(await self.guard.deployment(inst.id))
                self.register(ref)
            except Exception:
                log.exception("instance_not_reloaded", instance_id=str(inst.id))
        if self._runner is not None:
            await self._adopt([inst for inst, _ in rows])

    async def _adopt(self, instances: list[Instance]) -> None:
        """Étiquettes Docker contre la base (F9, §10 point 7). Lecture seule côté Docker : un
        conteneur n'est ni démarré, ni arrêté, ni supprimé ici, orphelin compris."""
        assert self._runner is not None  # noqa: S101
        try:
            running = {c.instance_id: c for c in await self._runner.adopt()}
        except EngineUnreachable:
            log.warning("adoption_failed")  # Docker injoignable : rien n'est conclu
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
        tick_log = log.bind(correlation_id=str(uuid7()))
        errors: list[Exception] = []  # étapes de la plateforme : sans elles, pas de battement
        self._ingest_error = None

        async def step(name: str, do: Callable[[], Awaitable[_T]]) -> _T | None:
            try:
                return await do()
            except Exception as exc:  # l'étape suivante a lieu quand même
                tick_log.exception("step_failed", step=name)
                errors.append(exc)
                return None

        try:
            # Les commandes d'abord : ni le bus ni un lot d'événements ne retardent une pause.
            # Seul ce qui augmente le risque peut périmer avant de partir.
            await step("expire_before_dispatch", lambda: self._commands.expire(("requested",)))
            claimed = await step("claim_commands", self._claim) or {}
            # Bus en panne : aucune boîte d'envoi de moteur n'est vidée à ce tour.
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
            failed: list[Exception] = []  # propres à une instance : visibles, sans effet ailleurs
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
                raise errors[0]  # tour incomplet : pas de battement, l'API voit un worker figé
            await self._redis.set(
                HEARTBEAT_KEY, self._clock().isoformat(), ex=self._cfg.heartbeat_ttl_s
            )
            if failed:
                raise failed[0]
        finally:  # ce qui est déjà validé en base est annoncé, même si la fin du tour échoue
            notes, self._notes = list(dict.fromkeys(self._notes)), []
            for kind, ident in notes:
                await notify(self._redis, kind, ident)

    async def _claim(self) -> dict[UUID, list[_Claimed]]:
        # Une instance dont la tâche dure encore garde ses commandes `requested` : une seule
        # tâche envoie pour une instance, et aucune échéance ne court avant l'envoi (I4).
        return await self._commands.claim(skip=tuple(self._tasks))

    async def _instance(
        self, tick_log: _Log, iid: UUID, claimed: Sequence[_Claimed], bus_ok: bool
    ) -> tuple[Observation | None, list[Exception]]:
        """Le tour d'UNE instance. Ne lève jamais : rend son relevé et ses erreurs."""
        instance_log = tick_log.bind(instance_id=str(iid))
        errors: list[Exception] = []

        async def step(name: str, do: Callable[[], Awaitable[_T]]) -> _T | None:
            try:
                return await do()
            except Exception as exc:  # l'étape suivante a lieu quand même
                instance_log.exception("step_failed", step=name)
                errors.append(exc)
                return None

        if claimed:  # avant toute lecture : rien ne retarde une pause (I4)
            await step("dispatch", lambda: self._commands.send(claimed))
        obs: Observation | None = None
        ref = self._refs.get(iid)  # un `deploy` vient peut-être de l'enregistrer
        if ref is not None:
            # Un seul délai pour les événements et le relevé : muet => `unknown` en 30 s (§13).
            deadline = asyncio.get_running_loop().time() + self._cfg.engine_silent_after_s
            if bus_ok:
                await step("publication", lambda: self._publish_events(instance_log, ref, deadline))
                await self._ingest(instance_log)  # avant le relevé, qui a le dernier mot
            obs = await step("snapshot", lambda: self._resync(instance_log, ref, deadline))
            if obs is not None:
                status = obs.status
                if await step("f9_verification", lambda: self.guard.check(ref, status)) == ():
                    obs = replace(obs, conform=True)
                await step("cleanup", lambda: self._clean_stopped(instance_log, iid, status.state))
        if iid in self.guard.pause_requested:  # la pause d'office part dans le même tour
            self.guard.pause_requested.discard(iid)
            await step("dispatch_pauses", lambda: self._commands.dispatch(only=iid))
        return obs, errors

    async def aclose(self) -> None:
        """Abandonne les tâches d'instance en cours. Aucun moteur n'est touché (I9)."""
        tasks, self._tasks = list(self._tasks.values()), {}
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.run_once()
            except Exception:
                log.exception("tick_failed")  # pas de battement : l'API voit un worker figé
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self._cfg.interval_s)
        await self.aclose()
        log.info("clean_shutdown")

    # --- étapes ---------------------------------------------------------------------------
    async def _publish_events(self, tick_log: _Log, ref: InstanceRef, deadline: float) -> None:
        try:
            async with asyncio.timeout_at(deadline):
                async for ev in self._adapters[ref.engine].events(ref):
                    await self._bus.publish(EVENTS_STREAM, ev.model_dump_json())
        except (EngineUnreachable, CommandRejected, TimeoutError):
            # Rien n'est inventé ; le relevé du tour dira `unknown`.
            tick_log.warning("events_unavailable")

    async def _ingest(self, tick_log: _Log) -> None:
        """Ingestion, par une tâche à la fois. Un échec arrête l'ingestion jusqu'au tour
        suivant (le message non acquitté sera relivré) et prive ce tour de battement."""
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
                    # Message inexploitable ou instance inconnue : le relivrer ne le réparerait pas.
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
                await self._bus.ack(EVENTS_STREAM, m.id)  # après traitement réussi seulement

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
            # Aucun relevé : l'état est inconnu, quelle que soit la cause (I1). Un moteur qui ne
            # connaît pas l'instance, ou dont l'adaptateur refuse le relevé, ne dit rien non plus.
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
            raise  # erreur imprévue de l'adaptateur : elle reste visible
        async with self._sessions.begin() as s:
            written = await apply_observation(s, ref.instance_id, status, snap)
        self._notes.extend(n for n in written if n[0] == "alert")
        # Positions et ordres : annoncés quand le relevé change, puis à la cadence de l'instance
        # (leur date d'observation avance) ; jamais à chaque tour.
        sig = (status.state, status.mode, snap.positions, snap.orders, snap.stops, snap.closed)
        if self._note_instance(ref.instance_id, sig):
            self._notes.extend(n for n in written if n[0] != "alert")
        tick_log.info("resync", reason=reason, state=status.state)
        return Observation(status, snap)

    async def _clean_stopped(self, tick_log: _Log, iid: UUID, state: str) -> None:
        """Arrêt observé sans `stop` commandé (plantage) : le fichier d'identifiants ne reste pas
        sur le disque, il sera réécrit au prochain démarrage. Seulement si Docker confirme
        qu'aucun conteneur ne tourne ni ne va être relancé ; au moindre doute, rien n'est retiré."""
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
