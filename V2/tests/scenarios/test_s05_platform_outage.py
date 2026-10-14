"""S5 (SPEC §14, I9, F11): platform stopped for 5 minutes then restarted. No instance
restarted; exits that happened during the outage appear after resynchronization; no
duplicates.

"No entry during the outage" rests on the engine's entry check, which refuses when the
Risk service does not answer: it arrives at M3 (S11, `test_i09_aucune_entree_pendant_la_panne`).
Here, the platform proves its part: it sends nothing, and opens no entry when it comes back."""

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
    for _ in range(200):  # until it holds a position: otherwise the scenario would prove nothing
        if (await w.fake.snapshot(ref)).positions:
            break
        w.step(ref, 1)
    await w.worker.run_once()
    held = (await w.projection(ref)).positions
    assert held
    row = await instance(w, iid)
    n_commands = len(await commands(w, iid))
    engine = w.fake._insts[ref.instance_id]  # the "container": the same object after the outage
    calls = spy(w.fake)

    # --- the platform stops: no worker cycle for 5 minutes ---
    del w.worker
    await w.fake.flatten(ref)  # the engine, alone, exits its positions
    calls.clear()  # this exit comes from the engine, not the platform
    w.clock.advance(300)
    stale = await get(c, f"/api/v1/instances/{iid}")
    assert stale["state"]["stale"] is True  # the API does not present the old state as current

    # --- it restarts: attachment, then resynchronization by snapshot ---
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

    # No instance restarted, no command sent, Docker only read.
    assert calls == [] and runner.calls == ["adopt"]
    assert w.fake._insts[ref.instance_id] is engine
    assert len(await commands(w, iid)) == n_commands
    assert (await w.fake.status(ref)).state == "running"
    # The outage's exits appear; the projections are the engine's.
    got, want = await w.projection(ref), await w.expected(ref)
    assert got.positions == want.positions == frozenset()
    assert got.open_orders == want.open_orders
    shown = await get(c, f"/api/v1/instances/{iid}")
    assert shown["state"] == {**shown["state"], "value": "running", "stale": False}
    # No duplicates: each event once, each order once.
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
    assert sorted(seqs) == list(range(1, engine.seq + 1))  # everything, with no gap or repetition
    assert sum(e.type == "position.closed" for e in events) == len(held)
    assert len(orders) == len(set(orders))
    assert await alerts(w, iid) == []
