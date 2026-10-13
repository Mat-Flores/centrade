"""S5 (SPEC §14, I9, F11) : plateforme arrêtée 5 minutes puis relancée. Aucune instance
redémarrée ; les sorties passées pendant la panne apparaissent après resynchronisation ; aucun
doublon.

« Aucune entrée pendant la panne » tient au contrôle d'entrée du moteur, qui refuse quand le
Risk service ne répond pas : il arrive à M3 (S11, `test_i09_aucune_entree_pendant_la_panne`).
Ici, la plateforme prouve sa part : elle n'envoie rien, et n'ouvre aucune entrée en revenant."""

from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.models.trading import Event, Order
from centrade_worker.worker import Worker
from sqlalchemy import select
from worker_support import RunnerDouble, alerts, commands, container, instance, spy


async def test_s05_platform_outage_of_5_minutes_then_restart(stack: Stack) -> None:
    w = stack.world
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    ref = ref_of(iid)
    await w.worker.run_once()
    assert (await act(c, iid, "resume-entries")).status_code == 202
    await w.worker.run_once()
    for _ in range(200):  # jusqu'à tenir une position : sinon le scénario ne prouverait rien
        if (await w.fake.snapshot(ref)).positions:
            break
        w.step(ref, 1)
    await w.worker.run_once()
    held = (await w.projection(ref)).positions
    assert held
    row = await instance(w, iid)
    n_commands = len(await commands(w, iid))
    engine = w.fake._insts[ref.instance_id]  # le « conteneur » : le même objet après la panne
    calls = spy(w.fake)

    # --- la plateforme s'arrête : plus aucun tour de worker pendant 5 minutes ---
    del w.worker
    await w.fake.flatten(ref)  # le moteur, seul, sort de ses positions
    calls.clear()  # cette sortie vient du moteur, pas de la plateforme
    w.clock.advance(300)
    stale = await get(c, f"/api/v1/instances/{iid}")
    assert stale["state"]["stale"] is True  # l'API ne présente pas l'ancien état comme actuel

    # --- elle redémarre : rattachement, puis resynchronisation par instantané ---
    assert row.deployment_fingerprint
    runner = RunnerDouble([container(row.id, row.deployment_fingerprint)])
    worker = Worker(
        adapters={"fake": w.fake},
        sessions=w.sessions,
        redis=w.redis,
        bus=w.bus,
        clock=w.clock,
        runner=runner,
    )
    await worker.load_instances()
    await worker.run_once()
    await worker.run_once()

    # Aucune instance redémarrée, aucune commande envoyée, Docker seulement lu.
    assert calls == [] and runner.calls == ["adopt"]
    assert w.fake._insts[ref.instance_id] is engine
    assert len(await commands(w, iid)) == n_commands
    assert (await w.fake.status(ref)).state == "running"
    # Les sorties de la panne apparaissent ; les projections sont celles du moteur.
    got, want = await w.projection(ref), await w.expected(ref)
    assert got.positions == want.positions == frozenset()
    assert got.open_orders == want.open_orders
    shown = await get(c, f"/api/v1/instances/{iid}")
    assert shown["state"] == {**shown["state"], "value": "running", "stale": False}
    # Aucun doublon : chaque événement une fois, chaque ordre une fois.
    async with w.sessions() as s:
        events = (
            await s.execute(
                select(Event.seq, Event.type).where(Event.instance_id == ref.instance_id)
            )
        ).all()
        orders = (
            await s.scalars(
                select(Order.client_order_id).where(Order.instance_id == ref.instance_id)
            )
        ).all()
    seqs = [e.seq for e in events]
    assert sorted(seqs) == list(range(1, engine.seq + 1))  # tout, sans trou ni répétition
    assert sum(e.type == "position.closed" for e in events) == len(held)
    assert len(orders) == len(set(orders))
    assert await alerts(w, iid) == []
