"""Tour du worker : une tâche par instance, en parallèle (SPEC F9, I4, §13 ; menace X14).

Un moteur lent, muet ou en erreur ne retarde ni la pause d'une autre instance, ni le battement du
worker. Horloge injectée et moteur doublé : le moteur « lent » attend un signal du test, jamais un
vrai délai."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from centrade_core.bus import HEARTBEAT_KEY
from centrade_core.engine.contract import CommandRejected
from centrade_core.engine.types import InstanceRef
from centrade_core.ids import uuid7
from centrade_core.models.trading import Command, Instance
from centrade_fake.engine import Failure
from centrade_worker.runner import RunnerContainer
from centrade_worker.testing import World
from centrade_worker.worker import Worker, WorkerConfig
from sqlalchemy import text, update
from worker_support import alerts, commands, container, instance, spy


async def request(w: World, ref: InstanceRef, type_: str, **args: str) -> UUID:
    """Commande `requested`, comme l'API l'écrit."""
    now = w.clock.now
    cmd = Command(
        id=uuid7(),
        instance_id=ref.instance_id,
        type=type_,
        actor="user:test",
        idempotency_key=uuid4().hex,
        args=args or None,
        status="requested",
        correlation_id=uuid7(),
        requested_at=now,
        deadline_at=now + timedelta(seconds=60),
        updated_at=now,
    )
    async with w.sessions.begin() as s:
        s.add(cmd)
    return cmd.id


async def status_of(w: World, command_id: UUID) -> str:
    async with w.sessions() as s:
        return (await s.get_one(Command, command_id)).status


def hang(w: World, ref: InstanceRef, method: str) -> asyncio.Event:
    """`method` du moteur ne répond plus pour cette instance, jusqu'au signal rendu."""
    release = asyncio.Event()
    real = getattr(w.fake, method)

    async def slow(r: InstanceRef, *args: Any) -> Any:
        if r.instance_id == ref.instance_id:
            await release.wait()
        return await real(r, *args)

    setattr(w.fake, method, slow)
    return release


def quick(w: World, **kw: Any) -> Worker:
    """Même worker, qui n'attend qu'un court instant les instances lentes."""
    old = w.worker
    w.worker = Worker(
        adapters={"fake": w.fake},
        sessions=w.sessions,
        redis=w.redis,
        bus=w.bus,
        clock=w.clock,
        config=replace(WorkerConfig(), tick_wait_s=0.3),
        simulated=frozenset({"fake"}),
        **kw,
    )
    for ref in old._refs.values():
        w.worker.register(ref)
    return w.worker


async def test_slow_engine_delays_neither_another_instances_pause_nor_the_heartbeat(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        slow, healthy = await w.new_instance(), await w.new_instance()
        worker = quick(w)
        await worker.run_once()
        release = hang(w, slow, "status")  # « dort 30 s » : ne répond pas avant le signal
        pause = await request(w, healthy, "pause_entries")
        started = w.clock.now

        for _ in range(20):  # la tâche lente ne finit pas ; celle de l'autre instance, si
            await worker.run_once()
            if await status_of(w, pause) == "verified":
                break

        # Sans que l'horloge ait avancé ni que le moteur lent ait répondu : envoyée, effet observé.
        assert await status_of(w, pause) == "verified" and not release.is_set()
        assert (await instance(w, healthy.instance_id)).observed_state == "exits_only"
        assert w.clock.now == started
        assert await w.redis.get(HEARTBEAT_KEY) == started.isoformat()  # le worker bat

        # L'instance lente garde sa tâche : une seule à la fois, ses commandes attendent leur
        # tour sans être marquées envoyées (leur échéance ne court pas, I4).
        late = await request(w, slow, "pause_entries")
        await worker.run_once()
        assert await status_of(w, late) == "requested"

        release.set()
        await worker.run_once()  # la tâche lente se termine
        await worker.run_once()
        assert await status_of(w, late) == "verified"
        assert (await w.fake.status(slow)).state == "exits_only"
        await worker.aclose()


async def test_exception_in_one_instances_task_does_not_stop_the_others(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        broken, healthy = await w.new_instance(), await w.new_instance()
        await w.worker.run_once()
        real = w.fake.snapshot

        async def snapshot(ref: InstanceRef) -> Any:
            if ref.instance_id == broken.instance_id:
                raise RuntimeError("adaptateur en erreur")
            return await real(ref)

        w.fake.snapshot = snapshot  # type: ignore[method-assign]
        pause = await request(w, healthy, "pause_entries")
        w.clock.advance(1)

        with pytest.raises(RuntimeError, match="adaptateur en erreur"):  # l'erreur reste visible
            await w.worker.run_once()

        assert await status_of(w, pause) == "verified"
        assert (await instance(w, healthy.instance_id)).observed_at == w.clock.now
        # Le relevé a échoué : l'état affiché n'est pas laissé à son ancienne valeur (I1).
        assert (await instance(w, broken.instance_id)).observed_state == "unknown"
        assert [a.severity for a in await alerts(w, broken.instance_id, "engine_unreachable")] == [
            "critical"
        ]
        assert await w.redis.get(HEARTBEAT_KEY) == w.clock.now.isoformat()


async def test_contract_error_on_snapshot_leaves_the_instance_unknown_without_breaking_the_tick(
    migrated_url: str, redis_url: str
) -> None:
    """Constat 11 : historique des trades clos au-delà du plafond de relecture de l'adaptateur."""
    async with World(migrated_url, redis_url) as w:
        over, healthy = await w.new_instance(), await w.new_instance()
        real = w.fake.snapshot

        async def snapshot(ref: InstanceRef) -> Any:
            if ref.instance_id == over.instance_id:
                raise CommandRejected("historique des trades clos au-delà du plafond")
            return await real(ref)

        w.fake.snapshot = snapshot  # type: ignore[method-assign]

        await w.worker.run_once()  # ne lève pas

        assert (await instance(w, over.instance_id)).observed_state == "unknown"
        assert len(await alerts(w, over.instance_id, "engine_unreachable")) == 1
        assert (await instance(w, healthy.instance_id)).observed_state == "running"
        assert await w.redis.get(HEARTBEAT_KEY) is not None


async def test_events_of_a_failing_instance_do_not_interrupt_those_of_the_others(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        broken, healthy = await w.new_instance(seed=4), await w.new_instance()
        w.step(healthy, 40)
        real = w.fake.events

        def events(ref: InstanceRef) -> Any:
            if ref.instance_id == broken.instance_id:
                raise RuntimeError("flux d'événements en erreur")
            return real(ref)

        w.fake.events = events  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="flux d'événements en erreur"):
            await w.worker.run_once()

        assert (await w.projection(healthy)).n_events > 0  # publiés et ingérés quand même
        assert (await instance(w, broken.instance_id)).observed_state == "running"  # relevée
        assert await w.redis.get(HEARTBEAT_KEY) is not None  # le battement ne dépend d'aucun moteur


async def test_risk_reducing_actions_go_out_before_risk_increasing_ones(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance(seed=4)
        w.step(ref, 60)
        await w.fake.pause_entries(ref)
        snap = await w.fake.snapshot(ref)
        assert snap.positions  # sinon le test ne prouve rien
        await w.worker.run_once()
        calls = spy(w.fake)

        resume = await request(w, ref, "resume_entries")  # demandée la première
        w.clock.advance(1)
        close = await request(w, ref, "close_position", position_id=snap.positions[0].position_id)

        await w.worker.run_once()

        # La fermeture part seule ; la reprise attend son tour (une commande à la fois, F9).
        assert calls == ["close_position"]
        assert await status_of(w, close) == "verified"
        assert await status_of(w, resume) == "requested"
        await w.worker.run_once()
        assert calls == ["close_position", "resume_entries"]
        assert await status_of(w, resume) == "verified"


async def test_m1_instance_without_fingerprint_is_reloaded_through_the_deploy_path(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        async with w.sessions.begin() as s:  # telle que M1 l'a laissée
            await s.execute(
                update(Instance)
                .where(Instance.id == ref.instance_id)
                .values(deployment_fingerprint=None, config_hash=None)
            )
        w.worker = w.make_worker("apres")  # le moteur simulé repart avec le processus
        w.fake._insts.clear()

        await w.worker.load_instances()
        await w.worker.run_once()

        assert (await instance(w, ref.instance_id)).deployment_fingerprint
        assert await alerts(w, ref.instance_id, "fingerprint_mismatch") == []
        resume = await request(w, ref, "resume_entries")
        await w.worker.run_once()
        assert await status_of(w, resume) == "verified"


async def test_stored_digest_differing_from_the_adapters_rejects_the_deploy(
    migrated_url: str, redis_url: str
) -> None:
    pinned = "sha256:" + "a" * 64
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        worker = quick(w, pinned_digests={"fake": pinned})
        calls = spy(w.fake)
        async with w.sessions.begin() as s:  # ligne `engines` modifiée en base
            await s.execute(
                text(
                    "UPDATE engines SET digest = :d WHERE id = "
                    "(SELECT engine_id FROM instances WHERE id = :i)"
                ),
                {"d": "sha256:" + "b" * 64, "i": ref.instance_id},
            )
        refused = await request(w, ref, "deploy")
        await worker.run_once()
        (cmd,) = await commands(w, ref.instance_id, "deploy")
        assert cmd.id == refused and cmd.status == "failed"
        assert cmd.result is not None and "digest" in cmd.result["reason"]
        assert "deploy" not in calls

        async with w.sessions.begin() as s:
            await s.execute(
                text(
                    "UPDATE engines SET digest = :d WHERE id = "
                    "(SELECT engine_id FROM instances WHERE id = :i)"
                ),
                {"d": pinned, "i": ref.instance_id},
            )
        await worker.run_once()  # l'écart d'empreinte a mis l'instance en pause : confirmée ici
        accepted = await request(w, ref, "deploy")
        await worker.run_once()
        assert await status_of(w, accepted) != "failed" and "deploy" in calls


class _Runner:
    def __init__(self) -> None:
        self.seen: RunnerContainer | None = None

    async def adopt(self) -> list[RunnerContainer]:
        return []

    async def inspect(self, instance_id: UUID) -> RunnerContainer | None:
        return self.seen


@pytest.mark.parametrize(
    ("container_status", "removed"),
    [(None, True), ("exited", True), ("restarting", False), ("running", False)],
)
async def test_credentials_are_removed_when_the_instance_is_observed_stopped_without_container(
    migrated_url: str,
    redis_url: str,
    tmp_path: Path,
    container_status: str | None,
    removed: bool,
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        runner = _Runner()
        if container_status is not None:
            runner.seen = replace(container(ref.instance_id, "f"), status=container_status)
        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        cleaned: list[UUID] = []

        async def cleanup(instance_id: UUID) -> None:
            cleaned.append(instance_id)
            creds.unlink(missing_ok=True)

        worker = quick(w, runner=runner, cleanup=cleanup)
        await worker.run_once()
        assert creds.exists()  # en marche : rien n'est retiré

        await w.fake.stop(ref)  # arrêt hors plateforme (plantage) : aucun `stop` commandé
        await worker.run_once()
        await worker.run_once()

        assert creds.exists() is not removed
        assert cleaned == ([ref.instance_id] if removed else [])  # une fois par arrêt observé


async def test_crashed_silent_engine_keeps_its_credentials(
    migrated_url: str, redis_url: str
) -> None:
    """État inconnu : aucun nettoyage, le doute ne détruit rien."""
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        cleaned: list[UUID] = []

        async def cleanup(instance_id: UUID) -> None:
            cleaned.append(instance_id)

        worker = quick(w, runner=_Runner(), cleanup=cleanup)
        w.fake.set_failure(ref, Failure.SILENT)
        await worker.run_once()
        assert cleaned == []
