"""I8: a command is "done" only once its effect is observed (SPEC §1.2, F9)."""

import asyncio
from typing import get_args

import httpx
from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.audit import fingerprint
from centrade_core.commands import Status, transition
from centrade_core.db import make_engine, make_session_factory
from centrade_core.ids import uuid7
from centrade_core.models import AuditLog
from centrade_core.models.trading import Command
from centrade_fake.engine import Failure
from centrade_worker.testing import T0
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select, text

STATUSES: tuple[Status, ...] = get_args(Status)
RANK = {"requested": 0, "dispatched": 1, "acknowledged": 2}


async def _running(stack: Stack, **params: object) -> tuple[httpx.AsyncClient, str]:
    c = await stack.client("operator")
    inst = await create_instance(c, **params)
    w = stack.world
    await w.worker.run_once()
    r = await act(c, inst["id"], "resume-entries")
    assert r.status_code == 202
    await w.worker.run_once()
    return c, inst["id"]


async def test_i08_command_is_not_done_without_an_observed_effect(stack: Stack) -> None:
    c, iid = await _running(stack, failures=["ignore_pause"])
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == "running"
    r = await act(c, iid, "pause-entries")
    cid = r.json()["command_id"]

    for _ in range(3):  # the engine acknowledges but does nothing
        stack.world.clock.advance(2)
        await stack.world.worker.run_once()
        cmd = await get(c, f"/api/v1/commands/{cid}")
        assert cmd["status"] == "acknowledged" and cmd["verified_at"] is None
    inst = await get(c, f"/api/v1/instances/{iid}")
    assert inst["state"]["value"] == "running" and inst["desired_state"] == "exits_only"

    stack.world.clock.advance(stack.settings.deadline_pause_entries_s)
    await stack.world.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "timed_out"


async def test_i08_command_without_response_becomes_timed_out(stack: Stack) -> None:
    c, iid = await _running(stack)
    stack.world.fake.set_failure(ref_of(iid), Failure.SILENT)
    r = await act(c, iid, "flatten")
    cid = r.json()["command_id"]
    await stack.world.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{cid}")
    assert cmd["status"] == "dispatched" and cmd["acknowledged_at"] is None  # unacked, not replayed

    stack.world.clock.advance(stack.settings.deadline_flatten_s + 1)
    await stack.world.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{cid}")
    assert cmd["status"] == "timed_out" and cmd["timed_out_at"] and cmd["verified_at"] is None
    alerts = await get(c, f"/api/v1/alerts?instance_id={iid}")
    assert any(a["rule"] == "command_timed_out" for a in alerts["items"])

    stack.world.fake.set_failure(ref_of(iid), Failure.SILENT, on=False)
    stack.world.clock.advance(1)
    await stack.world.worker.run_once()  # no automatic retry
    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "timed_out"


async def test_i08_no_verification_on_snapshot_older_than_the_ack(stack: Stack) -> None:
    c, iid = await _running(stack)
    w = stack.world
    w.fake.set_failure(ref_of(iid), Failure.SLOW)  # the engine obeys, but its snapshots are stale
    cid = (await act(c, iid, "pause-entries")).json()["command_id"]
    await w.worker.run_once()
    assert (await w.fake.status(ref_of(iid))).state == "exits_only"  # the effect is real...
    cmd = await get(c, f"/api/v1/commands/{cid}")
    assert cmd["status"] == "acknowledged" and cmd["verified_at"] is None  # ...but not observed

    w.fake.set_failure(ref_of(iid), Failure.SLOW, on=False)
    w.clock.advance(1)
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "verified"


async def test_i08_pause_and_flatten_go_through_a_busy_instance(stack: Stack) -> None:
    c, iid = await _running(stack)
    w = stack.world
    w.fake.set_failure(ref_of(iid), Failure.SILENT)
    stop = (await act(c, iid, "stop")).json()["command_id"]
    await w.worker.run_once()  # `stop` stays sent, unanswered: the instance is busy
    assert (await get(c, f"/api/v1/commands/{stop}"))["status"] == "dispatched"
    w.fake.set_failure(ref_of(iid), Failure.SILENT, on=False)

    pause = (await act(c, iid, "pause-entries")).json()["command_id"]
    flatten = (await act(c, iid, "flatten")).json()["command_id"]
    await w.worker.run_once()

    assert (await get(c, f"/api/v1/commands/{stop}"))["status"] == "dispatched"
    for cid in (pause, flatten):
        assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "verified"


async def test_i08_expiry_audit_fingerprint_carries_the_previous_status(
    stack: Stack,
) -> None:
    c, iid = await _running(stack)
    w = stack.world
    w.fake.set_failure(ref_of(iid), Failure.SILENT)
    cid = (await act(c, iid, "flatten")).json()["command_id"]
    await w.worker.run_once()
    w.clock.advance(stack.settings.deadline_flatten_s + 1)
    await w.worker.run_once()
    async with w.sessions() as s:
        row = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.action == "command.timed_out", AuditLog.target == f"command:{cid}"
                )
            )
        ).scalar_one()
    assert row.before_hash == fingerprint({"status": "dispatched"})
    assert row.after_hash == fingerprint({"status": "timed_out"})


async def _lifecycle(pg_url: str, path: list[Status]) -> None:
    """Tries each transition in the database, then compares with what the F9 cycle allows."""
    engine = make_engine(pg_url)
    try:
        sessions = make_session_factory(engine)
        cid, iid = uuid7(), uuid7()
        async with sessions.begin() as s:
            eid = await s.scalar(text("SELECT id FROM engines LIMIT 1"))
            await s.execute(
                text(
                    "INSERT INTO instances (id, engine_id, name, mode, desired_state) "
                    "VALUES (:i, :e, :n, 'paper', 'exits_only')"
                ),
                {"i": iid, "e": eid, "n": str(iid)},
            )
            s.add(
                Command(
                    id=cid,
                    instance_id=iid,
                    type="pause_entries",
                    actor="user:test",
                    idempotency_key=str(cid),
                    correlation_id=cid,
                    deadline_at=T0,
                    requested_at=T0,
                )
            )
        state: str = "requested"
        for target in path:
            async with sessions.begin() as s:
                done = await transition(s, cid, target, T0)
            async with sessions() as s:
                row = await s.get(Command, cid)
            assert row is not None
            allowed = (state, target) in LEGAL
            assert done is allowed, (state, target)
            assert row.status == (target if allowed else state)  # a refusal changes nothing
            if allowed:
                assert getattr(row, f"{target}_at") == T0
                state = target
            if state == "verified":  # effect observed only after send then acknowledgement
                assert row.dispatched_at is not None and row.acknowledged_at is not None
    finally:
        await engine.dispose()


# The F9 cycle, written here independently of the code: any other transition is refused.
LEGAL = {
    ("requested", "dispatched"),
    ("dispatched", "acknowledged"),
    ("acknowledged", "verified"),
    ("dispatched", "failed"),
    *((src, end) for src in RANK for end in ("timed_out", "superseded")),
}


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(path=st.lists(st.sampled_from(STATUSES), max_size=8))
def test_i08_command_lifecycle_is_ordered(migrated_url: str, path: list[Status]) -> None:
    """Whatever sequence of transitions is attempted on the real table: never backwards,
    never skipping a step, and a terminal state no longer changes."""
    asyncio.run(_lifecycle(migrated_url, path))
