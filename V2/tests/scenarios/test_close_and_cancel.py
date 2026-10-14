"""`close_position` and `cancel_entry_order` (SPEC F9, §7, I4) in the command cycle: send,
effect verified by the snapshot, deadline. They reduce risk: immediate, never held back
by the F9 verification nor by a busy instance. An order that is not an entry is
never cancelled."""

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.engine.types import InstanceRef
from centrade_core.engine.types import Order as EngineOrder
from centrade_core.ids import uuid7
from centrade_core.models.trading import Command
from centrade_fake.engine import SYMBOL, Failure
from worker_support import commands, spy


def _key() -> dict[str, str]:
    return {"Idempotency-Key": uuid4().hex}


async def _trading(stack: Stack) -> tuple[httpx.AsyncClient, str, InstanceRef]:
    """Running instance holding at least one position and one open entry order."""
    w = stack.world
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    ref = ref_of(iid)
    await w.worker.run_once()
    assert (await act(c, iid, "resume-entries")).status_code == 202
    await w.worker.run_once()
    for _ in range(500):
        snap = await w.fake.snapshot(ref)
        if snap.positions and snap.orders:
            break
        w.step(ref, 1)
    else:
        raise AssertionError("ni position ni ordre d'entrée : le test ne prouverait rien")
    await w.worker.run_once()
    return c, iid, ref


async def _command(stack: Stack, iid: str, type_: str, args: dict[str, Any] | None) -> UUID:
    """Command written the way the API does it, for cases its routes refuse outright."""
    now = stack.world.clock.now
    cmd = Command(
        id=uuid7(),
        instance_id=UUID(iid),
        type=type_,
        actor="user:test",
        idempotency_key=uuid4().hex,
        args=args,
        status="requested",
        correlation_id=uuid7(),
        requested_at=now,
        deadline_at=now + timedelta(seconds=30),
        updated_at=now,
    )
    async with stack.world.sessions.begin() as s:
        s.add(cmd)
    return cmd.id


async def test_position_close_is_sent_and_verified_by_the_snapshot(stack: Stack) -> None:
    c, iid, ref = await _trading(stack)
    w = stack.world
    target = (await get(c, f"/api/v1/positions?instance_id={iid}"))["items"][0]
    before = {p.position_id for p in (await w.fake.snapshot(ref)).positions}
    calls = spy(w.fake)

    r = await c.post(f"/api/v1/positions/{target['id']}/close", headers=_key())
    assert r.status_code == 202, r.text
    await w.worker.run_once()

    cmd = await get(c, f"/api/v1/commands/{r.json()['command_id']}")
    assert cmd["status"] == "verified", cmd
    assert calls == ["close_position"]
    left = {p.position_id for p in (await w.fake.snapshot(ref)).positions}
    assert left < before and len(before - left) == 1  # that one, and that one only
    assert (await w.fake.status(ref)).state == "running"  # neither pause nor stop


async def test_entry_order_cancel_is_sent_and_verified(stack: Stack) -> None:
    c, iid, ref = await _trading(stack)
    w = stack.world
    (order,) = [
        o
        for o in (await get(c, f"/api/v1/orders?instance_id={iid}"))["items"]
        if o["status"] == "open"
    ]
    calls = spy(w.fake)

    r = await c.delete(f"/api/v1/orders/{order['id']}", headers=_key())
    assert r.status_code == 202, r.text
    await w.worker.run_once()

    assert (await get(c, f"/api/v1/commands/{r.json()['command_id']}"))["status"] == "verified"
    assert calls == ["cancel_entry_order"]
    assert (await w.fake.snapshot(ref)).orders == ()
    held = {p.position_id for p in (await w.fake.snapshot(ref)).positions}
    assert held  # positions are not touched


async def test_cancel_rejects_an_order_that_is_not_an_entry(stack: Stack) -> None:
    c, iid, ref = await _trading(stack)
    w = stack.world
    exit_order = EngineOrder(
        order_id=str(uuid7()),
        symbol=SYMBOL,
        side="sell",
        intent="exit",
        qty=Decimal("1"),
        price=Decimal("100"),
        status="open",
    )
    w.fake._insts[ref.instance_id].orders[exit_order.order_id] = exit_order  # pending exit
    calls = spy(w.fake)

    refused = await _command(stack, iid, "cancel_entry_order", {"order_id": exit_order.order_id})
    unknown = await _command(stack, iid, "cancel_entry_order", {"order_id": "inconnu"})
    empty = await _command(stack, iid, "cancel_entry_order", None)
    no_position = await _command(stack, iid, "close_position", {"position_id": 12})
    await w.worker.run_once()

    results = {
        cid: await get(c, f"/api/v1/commands/{cid}")
        for cid in (refused, unknown, empty, no_position)
    }
    assert {r["status"] for r in results.values()} == {"failed"}
    assert "pas un ordre d'entrée" in results[refused]["result"]["reason"]
    assert "introuvable" in results[unknown]["result"]["reason"]
    assert "order_id manquant" in results[empty]["result"]["reason"]
    assert "position_id manquant" in results[no_position]["result"]["reason"]
    assert calls == []  # nothing was sent to the engine
    assert exit_order.order_id in {o.order_id for o in (await w.fake.snapshot(ref)).orders}


async def test_i04_close_and_cancel_are_never_held_back_by_the_f9_check(
    stack: Stack,
) -> None:
    c, iid, ref = await _trading(stack)
    w = stack.world
    snap = await w.fake.snapshot(ref)
    position_id, order_id = snap.positions[0].position_id, snap.orders[0].order_id
    # Everything the verification refuses: wrong mode, drifted configuration, changed image,
    # stale snapshots, and an entries resume left without effect (busy instance).
    for failure in (Failure.LIE_MODE, Failure.DRIFT, Failure.SLOW, Failure.IGNORE_PAUSE):
        w.fake.set_failure(ref, failure)
    busy = await _command(stack, iid, "resume_entries", None)
    calls = spy(w.fake)

    close = await _command(stack, iid, "close_position", {"position_id": position_id})
    cancel = await _command(stack, iid, "cancel_entry_order", {"order_id": order_id})
    w.clock.advance(600)  # worker absent for a long time: they do not expire before sending
    await w.worker.run_once()

    assert {"close_position", "cancel_entry_order"} <= set(calls)
    assert "resume_entries" not in calls
    snap = await w.fake.snapshot(ref)
    assert position_id not in {p.position_id for p in snap.positions}
    assert order_id not in {o.order_id for o in snap.orders}
    for cid in (close, cancel):
        cmd = await get(c, f"/api/v1/commands/{cid}")
        assert cmd["dispatched_at"] is not None and cmd["status"] == "acknowledged", cmd
    assert (await get(c, f"/api/v1/commands/{busy}"))["status"] in ("failed", "timed_out")

    # The snapshot is fresh again: the effect is observed, both commands are verified.
    w.fake.set_failure(ref, Failure.SLOW, on=False)
    await w.worker.run_once()
    for cid in (close, cancel):
        assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "verified"


async def test_close_without_engine_response_times_out_and_is_visible(stack: Stack) -> None:
    c, iid, ref = await _trading(stack)
    w = stack.world
    position_id = (await w.fake.snapshot(ref)).positions[0].position_id
    w.fake.set_failure(ref, Failure.SILENT)
    cid = await _command(stack, iid, "close_position", {"position_id": position_id})

    await w.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "dispatched"  # never replayed
    w.clock.advance(31)
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "timed_out"
    assert len(await commands(w, iid, "close_position")) == 1
