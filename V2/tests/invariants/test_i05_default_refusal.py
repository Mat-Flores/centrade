"""I5, commands side: what increases risk (`resume_entries`, `start`) is refused at the slightest
doubt, on request (API) then again just before sending (worker). Nothing is then sent to
the engine. What reduces risk is never refused by this rule (I4)."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.commands import RISK_INCREASING, RISK_REDUCING, risk_increase_refusal
from centrade_fake.engine import Failure
from centrade_worker.testing import T0
from hypothesis import given
from hypothesis import strategies as st

STATES = ("starting", "exits_only", "running", "halted", "stopped", "error", "unknown")
READY = {"resume_entries": {"exits_only", "running"}, "start": {"stopped", "error"}}


@given(
    type_=st.sampled_from(sorted(RISK_INCREASING | RISK_REDUCING | {"deploy"})),
    mode=st.sampled_from(("paper", "live")),
    state=st.sampled_from(STATES),
    observed_mode=st.sampled_from((None, "paper", "live", "unknown")),
    age_s=st.none() | st.integers(-100_000, 100_000),  # negative: snapshot dated in the future
    stale_after_s=st.integers(1, 3600),
)
def test_i05_risk_increasing_actions_are_rejected_by_default(
    type_: str,
    mode: str,
    state: str,
    observed_mode: str | None,
    age_s: int | None,
    stale_after_s: int,
) -> None:
    def refusal(age: int | None) -> str | None:
        return risk_increase_refusal(
            type_,
            mode=mode,
            observed_state=state,
            observed_mode=observed_mode,
            observed_at=None if age is None else T0 - timedelta(seconds=age),
            now=T0,
            stale_after_s=stale_after_s,
        )

    reason = refusal(age_s)
    assert reason == refusal(age_s)  # same input, same decision
    if type_ not in RISK_INCREASING:
        assert reason is None  # the rule never holds back what reduces risk
        return
    doubt = age_s is None or state == "unknown" or abs(age_s) > stale_after_s
    if doubt:
        assert reason  # unknown, stale or future-dated: refusal, with a reason
    if reason is None:
        assert not doubt and state in READY[type_]
        assert type_ != "resume_entries" or observed_mode == mode
    elif age_s is not None and age_s >= 0:
        assert refusal(age_s + stale_after_s + 1)  # aging a snapshot never lifts a refusal


async def _ready(stack: Stack) -> tuple[httpx.AsyncClient, str, list[str]]:
    """Exits-only instance, and the `resume_entries` calls received by the engine."""
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    await stack.world.worker.run_once()
    calls: list[str] = []
    real = stack.world.fake.resume_entries

    async def spy(ref: Any) -> None:
        calls.append("resume_entries")
        await real(ref)

    stack.world.fake.resume_entries = spy  # type: ignore[method-assign]
    return c, iid, calls


@pytest.mark.parametrize(
    ("failure", "word"),
    [(Failure.LIE_MODE, "mode"), (Failure.SLOW, "périmé"), (Failure.SILENT, "inconnu")],
)
async def test_i05_resume_is_rechecked_just_before_dispatch(
    stack: Stack, failure: Failure, word: str
) -> None:
    c, iid, calls = await _ready(stack)
    r = await act(c, iid, "resume-entries")  # accepted: the last snapshot was good
    assert r.status_code == 202
    stack.world.fake.set_failure(ref_of(iid), failure)  # the engine changes in the meantime

    await stack.world.worker.run_once()

    cmd = await get(c, f"/api/v1/commands/{r.json()['command_id']}")
    assert cmd["status"] == "failed" and word in cmd["result"]["reason"], cmd
    assert calls == []  # nothing was sent to the engine
    stack.world.fake.set_failure(ref_of(iid), failure, on=False)
    assert (await stack.world.fake.status(ref_of(iid))).state == "exits_only"


async def test_i05_stale_resume_is_never_dispatched(stack: Stack) -> None:
    c, iid, calls = await _ready(stack)
    r = await act(c, iid, "resume-entries")
    stack.world.clock.advance(stack.settings.deadline_resume_entries_s + 1)  # worker frozen
    await stack.world.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{r.json()['command_id']}")
    assert cmd["status"] == "timed_out" and cmd["dispatched_at"] is None
    assert calls == []


async def test_i05_dispatch_itself_drops_a_stale_resume(stack: Stack) -> None:
    """Even if the cycle's expiry step failed, a stale resume is not sent."""
    c, iid, calls = await _ready(stack)
    r = await act(c, iid, "resume-entries")
    stack.world.clock.advance(stack.settings.deadline_resume_entries_s + 1)
    await stack.world.worker._commands.dispatch()
    cmd = await get(c, f"/api/v1/commands/{r.json()['command_id']}")
    assert cmd["status"] == "requested" and calls == []


async def test_i05_resume_is_accepted_and_verified_when_nothing_opposes_it(stack: Stack) -> None:
    c, iid, calls = await _ready(stack)
    r = await act(c, iid, "resume-entries")
    await stack.world.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{r.json()['command_id']}"))["status"] == "verified"
    assert calls == ["resume_entries"]


async def test_i05_start_is_rejected_unless_the_instance_is_stopped(stack: Stack) -> None:
    c, iid, _ = await _ready(stack)
    w = stack.world
    r = await act(c, iid, "start")  # already running: nothing to start
    assert r.status_code == 409 and "exits_only" in r.json()["detail"]

    assert (await act(c, iid, "stop")).status_code == 202
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == "stopped"
    r = await act(c, iid, "start")
    assert r.status_code == 202
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{r.json()['command_id']}"))["status"] == "verified"
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == "exits_only"

    w.clock.advance(stack.settings.observed_stale_after_s + 1)  # stale snapshot
    r = await act(c, iid, "start")
    assert r.status_code == 409 and "périmé" in r.json()["detail"]
