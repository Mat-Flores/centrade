"""S7 (SPEC §14): an engine that declares itself live for a paper instance. Entries never opened,
critical alert, and the observed mode stays displayed as is ("MODE INCOHÉRENT" badge)."""

from centrade_api.testing import Stack, act, create_instance, get, ref_of
from worker_support import alerts, commands, instance, spy


async def test_s07_mode_mismatch_never_opens_entries(stack: Stack) -> None:
    w = stack.world
    c = await stack.client("operator")
    calls = spy(w.fake)
    iid = str((await create_instance(c, failures=["lie_mode"]))["id"])

    await w.worker.run_once()  # first observed start: the effective mode is re-read

    shown = await get(c, f"/api/v1/instances/{iid}")
    assert shown["desired_mode"] == "paper" and shown["observed_mode"]["value"] == "live"
    assert shown["mode_mismatch"] is True and shown["state"]["value"] == "exits_only"
    assert (await instance(w, iid)).observed_mode == "live"  # never replaced by the wanted mode
    (alert,) = await alerts(w, iid, "mode_mismatch")
    assert (alert.severity, alert.status, alert.invariant) == ("critical", "open", "I3")
    # The deployment is not confirmed: what is running is not compliant.
    assert (await commands(w, iid, "deploy"))[0].status == "acknowledged"

    r = await act(c, iid, "resume-entries")
    assert r.status_code == 409 and "mode" in r.json()["detail"]
    for _ in range(3):
        w.clock.advance(20)
        await w.worker.run_once()
    assert calls == ["deploy"]  # no resume reached the engine
    assert (await w.fake.status(ref_of(iid))).state == "exits_only"
    assert w.fake._insts[ref_of(iid).instance_id].orders == {}
    assert len(await alerts(w, iid, "mode_mismatch")) == 1  # one alert, not one per check
    assert (await commands(w, iid, "deploy"))[0].status == "timed_out"
