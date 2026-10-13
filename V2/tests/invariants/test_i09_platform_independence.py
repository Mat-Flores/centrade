"""I9 : arrêter ou redémarrer la plateforme ne touche à aucun conteneur de moteur.
Côté runner (Docker local requis) : l'arrêt du runner (et donc du worker) laisse les conteneurs en
marche, et une nouvelle instance du runner les adopte sans les redémarrer.
Côté worker (FakeEngine, runner doublé) : son arrêt n'envoie rien à aucun moteur ; à la reprise,
il rattache ce qui tourne sans rien commander et resynchronise sans doublon."""

import asyncio
import os
import signal

import pytest
from centrade_api.testing import Stack as ApiStack
from centrade_api.testing import act, create_instance, ref_of
from centrade_core.models.trading import Event, Order
from centrade_worker.testing import World
from centrade_worker.worker import Worker, install_stop_signals
from runner.support import Stack, docker_stack, needs_docker  # noqa: F401
from sqlalchemy import func, select
from worker_support import RunnerDouble, alerts, commands, container, instance, spy


@pytest.mark.docker
@needs_docker
async def test_i09_worker_shutdown_touches_no_container(docker_stack: Stack) -> None:  # noqa: F811
    runner = docker_stack.runner()
    spec = docker_stack.spec()
    await runner.create(spec)
    started = await runner.start(spec.instance_id)

    # Arrêt du worker : son client Docker est fermé, il ne reste rien qui pilote le conteneur.
    runner._cli().close()
    del runner

    live = docker_stack.raw.containers.get(f"centrade-engine-{spec.instance_id}")
    live.reload()
    assert live.status == "running"
    assert live.attrs["State"]["StartedAt"] == started.started_at

    await docker_stack.runner().stop(spec.instance_id, timeout_s=2)
    await docker_stack.runner().remove(spec.instance_id)


@pytest.mark.docker
@needs_docker
async def test_i09_adoption_does_not_restart_the_container(docker_stack: Stack) -> None:  # noqa: F811
    spec = docker_stack.spec()
    old = docker_stack.runner()
    await old.create(spec)
    started = await old.start(spec.instance_id)

    adopted = [c for c in await docker_stack.runner().adopt() if c.instance_id == spec.instance_id]
    assert [(c.status, c.started_at) for c in adopted] == [("running", started.started_at)]
    live = docker_stack.raw.containers.get(f"centrade-engine-{spec.instance_id}")
    assert live.attrs["RestartCount"] == 0

    await old.stop(spec.instance_id, timeout_s=2)
    await old.remove(spec.instance_id)


async def _running(stack: ApiStack) -> str:
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    await stack.world.worker.run_once()
    assert (await act(c, iid, "resume-entries")).status_code == 202
    await stack.world.worker.run_once()
    return iid


def _restarted(w: World, runner: RunnerDouble | None = None) -> Worker:
    """Nouveau processus de worker devant un moteur qui, lui, a continué de tourner."""
    return Worker(
        adapters={"fake": w.fake},
        sessions=w.sessions,
        redis=w.redis,
        bus=w.bus,
        clock=w.clock,
        runner=runner,
    )


async def test_i09_worker_shutdown_has_no_effect_on_instances(stack: ApiStack) -> None:
    iid = await _running(stack)
    w = stack.world
    runner = RunnerDouble([container(ref_of(iid).instance_id, "x")])
    worker = _restarted(w, runner)
    worker.register(ref_of(iid))
    await worker.run_once()
    before = (await w.fake.status(ref_of(iid)), await w.fake.snapshot(ref_of(iid)))
    row = await instance(w, iid)
    n_commands = len(await commands(w, iid))
    calls = spy(w.fake)

    stop = asyncio.Event()
    install_stop_signals(stop)
    try:
        os.kill(os.getpid(), signal.SIGTERM)  # le signal d'arrêt de Docker
        await asyncio.wait_for(worker.run(stop), timeout=5)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            asyncio.get_running_loop().remove_signal_handler(sig)

    assert stop.is_set() and calls == [] and runner.calls == []  # rien vers le moteur ni Docker
    after = (await w.fake.status(ref_of(iid)), await w.fake.snapshot(ref_of(iid)))
    assert after[0].state == "running" and after[1].positions == before[1].positions
    now = await instance(w, iid)
    assert (now.desired_state, now.observed_state) == (row.desired_state, row.observed_state)
    assert len(await commands(w, iid)) == n_commands


async def test_i09_platform_restart_restarts_no_instance(stack: ApiStack) -> None:
    iid = await _running(stack)
    w = stack.world
    row = await instance(w, iid)
    assert row.deployment_fingerprint
    calls = spy(w.fake)
    runner = RunnerDouble([container(row.id, row.deployment_fingerprint)])

    worker = _restarted(w, runner)
    await worker.load_instances()
    await worker.run_once()

    assert calls == []  # ni redéploiement, ni relance, ni commande : le moteur est rattaché
    assert runner.calls == ["adopt"]  # Docker : une lecture, rien d'autre
    assert (await w.fake.status(ref_of(iid))).state == "running"
    row = await instance(w, iid)
    assert row.container_ref == runner.containers[0].container_id
    assert row.observed_state == "running" and row.observed_at == w.clock.now
    assert await alerts(w, iid) == []


async def test_i09_exits_made_during_outage_are_resynced_without_duplicates(
    stack: ApiStack,
) -> None:
    iid = await _running(stack)
    w, ref = stack.world, ref_of(iid)
    for _ in range(200):  # jusqu'à tenir une position : sinon le test ne prouverait rien
        if (await w.fake.snapshot(ref)).positions:
            break
        w.step(ref, 1)
    await w.worker.run_once()
    assert (await w.projection(ref)).positions

    # Panne : le worker a publié un lot qu'il n'a pas ingéré, puis le moteur continue seul.
    w.step(ref, 20)
    pending = await w.drain_engine(ref)
    await w.publish(pending)
    w.clock.advance(300)
    await w.fake.flatten(ref)  # des sorties passent pendant la panne
    emitted = len(pending) + len(w.fake._insts[ref.instance_id].outbox)

    async with w.sessions() as s:
        known = await s.scalar(
            select(func.count()).select_from(Event).where(Event.instance_id == ref.instance_id)
        )
    worker = _restarted(w)
    await worker.load_instances()
    await worker.run_once()
    await w.publish(pending)  # le bus relivre le lot : au moins une fois
    await worker.run_once()

    got = await w.projection(ref)
    assert got.n_events == (known or 0) + emitted  # tout est arrivé, une seule fois
    want = await w.expected(ref)
    assert (got.positions, got.open_orders) == (want.positions, want.open_orders)
    assert got.positions == frozenset()  # les sorties de la panne se voient
    async with w.sessions() as s:
        seqs = (
            await s.scalars(select(Event.seq).where(Event.instance_id == ref.instance_id))
        ).all()
        orders = (
            await s.scalars(
                select(Order.client_order_id).where(Order.instance_id == ref.instance_id)
            )
        ).all()
    assert len(seqs) == len(set(seqs)) and len(orders) == len(set(orders))


async def test_i09_orphan_container_is_reported_and_left_intact(stack: ApiStack) -> None:
    from centrade_core.ids import uuid7

    w = stack.world
    unknown = uuid7()
    runner = RunnerDouble([container(unknown, "f" * 64)])
    worker = _restarted(w, runner)
    calls = spy(w.fake)

    await worker.load_instances()
    await worker.load_instances()  # un second démarrage ne double pas l'alerte

    (alert,) = await alerts(w, unknown)
    assert (alert.rule, alert.target_kind, alert.status) == ("orphan_container", "global", "open")
    assert "orphelin" in alert.message
    assert runner.calls == ["adopt", "adopt"] and calls == []  # ni arrêté, ni supprimé


async def test_i09_different_label_fingerprint_and_missing_container_are_reported(
    stack: ApiStack,
) -> None:
    from centrade_core.engine.contract import EngineUnreachable
    from centrade_core.models.trading import Instance
    from sqlalchemy import update

    iid = await _running(stack)
    w = stack.world
    row = await instance(w, iid)
    runner = RunnerDouble([container(row.id, "pas-la-bonne-empreinte")])
    calls = spy(w.fake)

    await _restarted(w, runner).load_instances()
    (alert,) = await alerts(w, iid, "fingerprint_mismatch")
    assert alert.invariant == "I10" and alert.status == "open"

    runner.containers = []  # le conteneur rattaché ne tourne plus
    await _restarted(w, runner).load_instances()
    (missing,) = await alerts(w, iid, "container_missing")
    assert missing.severity == "critical"

    # Instance voulue arrêtée : son conteneur absent est normal. Docker muet : rien n'est conclu.
    async with w.sessions.begin() as s:
        await s.execute(update(Instance).where(Instance.id == row.id).values(container_ref="c2"))
    other = await _running(stack)
    calls.clear()
    async with w.sessions.begin() as s:
        await s.execute(
            update(Instance)
            .where(Instance.id == ref_of(other).instance_id)
            .values(container_ref="c3", desired_state="stopped")
        )
    runner.error = EngineUnreachable("Docker injoignable")
    await _restarted(w, runner).load_instances()
    runner.error = None
    await _restarted(w, runner).load_instances()
    assert await alerts(w, other, "container_missing") == []
    assert len(await alerts(w, iid, "container_missing")) == 1
    assert set(runner.calls) == {"adopt"} and calls == []
