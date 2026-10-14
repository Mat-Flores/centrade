"""I4, commands side: what reduces risk is always sent to the engine, whatever the
platform outage (worker absent for a long time, bus down, another instance in error)."""

from datetime import datetime
from typing import Any

import httpx
import pytest
from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.bus import Bus
from centrade_fake.engine import Failure
from centrade_worker.worker import Worker
from redis.exceptions import ConnectionError as RedisConnectionError

REDUCTIONS = {"pause-entries": "exits_only", "flatten": "running", "stop": "stopped"}


async def _running(stack: Stack, **params: object) -> tuple[httpx.AsyncClient, str]:
    c = await stack.client("operator")
    inst = await create_instance(c, **params)
    await stack.world.worker.run_once()
    assert (await act(c, inst["id"], "resume-entries")).status_code == 202
    await stack.world.worker.run_once()
    assert (await get(c, f"/api/v1/instances/{inst['id']}"))["state"]["value"] == "running"
    return c, str(inst["id"])


class _BrokenRedis:
    """Every call fails like an unreachable Redis."""

    def __getattr__(self, name: str) -> Any:
        async def boom(*_: object, **__: object) -> None:
            raise RedisConnectionError("bus en panne")

        return boom


@pytest.mark.parametrize("action", sorted(REDUCTIONS))
async def test_i04_risk_reducing_command_never_expires_before_dispatch(
    stack: Stack, action: str
) -> None:
    c, iid = await _running(stack)
    cid = (await act(c, iid, action)).json()["command_id"]

    stack.world.clock.advance(600)  # worker absent well beyond any deadline
    await stack.world.worker.run_once()

    cmd = await get(c, f"/api/v1/commands/{cid}")
    assert cmd["dispatched_at"] is not None and cmd["status"] == "verified", cmd
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == REDUCTIONS[action]
    # The deadline measures the effect, counted from the send.
    assert datetime.fromisoformat(cmd["deadline_at"]) > datetime.fromisoformat(cmd["dispatched_at"])


async def test_i04_pause_deadline_runs_from_dispatch(stack: Stack) -> None:
    c, iid = await _running(stack, failures=["ignore_pause"])
    cid = (await act(c, iid, "pause-entries")).json()["command_id"]
    w = stack.world

    w.clock.advance(600)
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "acknowledged"  # sent

    w.clock.advance(stack.settings.deadline_pause_entries_s + 1)  # no effect: expires, visible
    await w.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{cid}")
    assert cmd["status"] == "timed_out" and cmd["dispatched_at"] is not None


async def test_i04_bus_outage_blocks_neither_dispatch_nor_snapshot(stack: Stack) -> None:
    c, iid = await _running(stack)
    w = stack.world
    broken: Any = _BrokenRedis()
    w.worker = Worker(
        adapters={"fake": w.fake},
        sessions=w.sessions,
        redis=broken,
        bus=Bus(broken, "worker", "w1"),
        clock=w.clock,
    )
    w.worker.register(ref_of(iid))
    cid = (await act(c, iid, "pause-entries")).json()["command_id"]
    w.clock.advance(1)

    with pytest.raises(RedisConnectionError):  # the outage stays visible: no heartbeat
        await w.worker.run_once()

    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "verified"
    inst = await get(c, f"/api/v1/instances/{iid}")
    assert inst["state"]["value"] == "exits_only"
    assert datetime.fromisoformat(inst["state"]["observed_at"]) == w.clock.now  # cycle snapshot


async def test_i04_error_on_one_instance_does_not_block_the_others(stack: Stack) -> None:
    c, broken_id = await _running(stack)
    healthy = (await create_instance(c))["id"]
    w = stack.world
    await w.worker.run_once()
    assert (await act(c, healthy, "resume-entries")).status_code == 202
    await w.worker.run_once()

    real = w.fake.status

    async def status(ref: Any) -> Any:
        if str(ref.instance_id) == broken_id:
            raise RuntimeError("adaptateur en erreur")
        return await real(ref)

    w.fake.status = status  # type: ignore[method-assign]
    cid = (await act(c, healthy, "pause-entries")).json()["command_id"]
    w.clock.advance(1)
    with pytest.raises(RuntimeError, match="adaptateur en erreur"):
        await w.worker.run_once()

    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "verified"
    inst = await get(c, f"/api/v1/instances/{healthy}")
    assert inst["state"]["value"] == "exits_only"
    assert datetime.fromisoformat(inst["state"]["observed_at"]) == w.clock.now


async def test_i04_write_failure_for_one_command_does_not_block_dispatching_the_others(
    stack: Stack,
) -> None:
    c, first = await _running(stack)
    second = (await create_instance(c))["id"]
    w = stack.world
    await w.worker.run_once()
    assert (await act(c, second, "resume-entries")).status_code == 202
    await w.worker.run_once()
    for iid in (first, second):
        assert (await act(c, iid, "pause-entries")).status_code == 202

    commands = w.worker._commands
    real, calls = commands._finish, 0

    async def finish(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("écriture impossible")
        await real(*args, **kwargs)

    commands._finish = finish  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="écriture impossible"):
        await w.worker.run_once()

    for iid in (first, second):  # both engines received the pause
        assert (await w.fake.status(ref_of(iid))).state == "exits_only"


async def test_i04_pause_is_dispatched_even_if_engine_was_silent_on_previous_tick(
    stack: Stack,
) -> None:
    c, iid = await _running(stack)
    w = stack.world
    w.fake.set_failure(ref_of(iid), Failure.SILENT)
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == "unknown"
    w.fake.set_failure(ref_of(iid), Failure.SILENT, on=False)

    r = await act(c, iid, "pause-entries")  # unknown state: the pause is still accepted
    assert r.status_code == 202
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{r.json()['command_id']}"))["status"] == "verified"
