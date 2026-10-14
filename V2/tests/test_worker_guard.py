"""F9 verification on the worker side: refusal branches and reactions (SPEC F9, I5, §13)."""

from datetime import timedelta
from typing import Any

from centrade_core.engine.contract import EngineUnreachable
from centrade_core.engine.types import InstanceRef
from centrade_worker.testing import World
from test_worker_parallel import request, status_of
from worker_support import alerts, commands, instance, spy


def failing_read(w: World, exc: Exception) -> tuple[list[int], Any]:
    """`effective_config` raises `exc`; returns the call counter and a way to restore it."""
    real, reads = w.fake.effective_config, [0]

    async def effective_config(ref: InstanceRef) -> Any:
        reads[0] += 1
        raise exc

    w.fake.effective_config = effective_config  # type: ignore[method-assign]

    def restore() -> None:
        w.fake.effective_config = real  # type: ignore[method-assign]

    return reads, restore


async def test_exception_in_the_check_rejects_the_resume_and_sends_nothing(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        await w.fake.pause_entries(ref)
        await w.worker.run_once()
        calls = spy(w.fake)
        failing_read(w, RuntimeError("relecture cassée"))

        resume = await request(w, ref, "resume_entries")
        await w.worker.run_once()

        (cmd,) = await commands(w, ref.instance_id, "resume_entries")
        assert cmd.id == resume and cmd.status == "failed"
        assert cmd.result is not None
        assert [r["code"] for r in cmd.result["reasons"]] == ["error"]
        assert "RuntimeError" in cmd.result["reason"]
        assert calls == []  # nothing was sent to the engine
        assert (await w.fake.status(ref)).state == "exits_only"
        (alert,) = await alerts(w, ref.instance_id, "entries_refused")
        assert (alert.status, alert.invariant) == ("open", "I5")


async def test_failed_reread_is_not_counted_as_a_completed_check(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        await w.worker.run_once()
        w.clock.advance(31)  # the cadence is due
        reads, restore = failing_read(w, EngineUnreachable("muet"))

        await w.worker.run_once()
        assert reads == [1]
        await w.worker.run_once()  # without waiting for the cadence: retried on the very next round
        assert reads == [2]

        restore()
        real = w.fake.effective_config

        async def counted(r: InstanceRef) -> Any:
            reads[0] += 1
            return await real(r)

        w.fake.effective_config = counted  # type: ignore[method-assign,assignment]
        await w.worker.run_once()
        await w.worker.run_once()
        assert reads == [3]  # succeeded: held until the next cadence
        assert (await instance(w, ref.instance_id)).effective_config_at == w.clock.now


async def test_unreadable_running_engine_raises_an_alert_and_pauses_within_60_s(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        await w.worker.run_once()  # last re-read succeeded
        read_at = w.clock.now
        calls = spy(w.fake)
        _, restore = failing_read(w, EngineUnreachable("configuration illisible"))

        detected_at = None
        for _ in range(20):
            w.clock.advance(5)
            await w.worker.run_once()
            if await alerts(w, ref.instance_id, "config_unreadable"):
                detected_at = w.clock.now
                break
            assert calls == []  # before the delay: no alert and no pause

        assert detected_at is not None and detected_at - read_at == timedelta(seconds=60)
        (alert,) = await alerts(w, ref.instance_id, "config_unreadable")
        assert (alert.severity, alert.status) == ("critical", "open")
        assert calls == ["pause_entries"]  # sent automatically, in the same round
        (pause,) = await commands(w, ref.instance_id, "pause_entries")
        assert pause.actor == "system:worker"
        assert (await w.fake.status(ref)).state == "exits_only"

        w.clock.advance(5)
        await w.worker.run_once()  # still unreadable, in exits-only: nothing more
        assert len(await alerts(w, ref.instance_id, "config_unreadable")) == 1
        assert calls == ["pause_entries"]
        assert await status_of(w, pause.id) == "verified"

        restore()
        await w.worker.run_once()
        assert (await alerts(w, ref.instance_id, "config_unreadable"))[0].status == "resolved"


async def test_observed_halted_state_raises_an_alert_and_returns_to_exits_only(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance()
        await w.worker.run_once()
        calls = spy(w.fake)
        w.fake._insts[ref.instance_id].state = "halted"  # never requested by the platform

        await w.worker.run_once()
        await w.worker.run_once()  # one alert and one command per episode, not one per round

        (alert,) = await alerts(w, ref.instance_id, "engine_halted")
        assert (alert.severity, alert.status) == ("critical", "open")
        (back,) = await commands(w, ref.instance_id, "pause_entries")
        assert back.actor == "system:worker" and back.dispatched_at is not None
        assert calls == ["pause_entries"]  # contract call that brings the engine back to exits-only

        w.fake._insts[ref.instance_id].state = "exits_only"
        await w.worker.run_once()
        assert (await alerts(w, ref.instance_id, "engine_halted"))[0].status == "resolved"
        assert await status_of(w, back.id) == "verified"
