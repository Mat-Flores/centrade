"""S8 (SPEC §14, §13): owned key modified outside the platform. Detected within 60 s (injected
clock), exits only, critical alert; the drift and the re-read configuration are recorded
and dated."""

from datetime import timedelta

from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_fake.engine import Failure
from worker_support import alerts, commands, instance, spy


async def test_s08_drift_detected_within_60_s_exits_only_critical_alert(stack: Stack) -> None:
    w = stack.world
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    await w.worker.run_once()
    assert (await act(c, iid, "resume-entries")).status_code == 202
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == "running"
    calls = spy(w.fake)

    w.fake.set_failure(ref_of(iid), Failure.DRIFT)  # modified in the engine, outside the platform
    drifted_at = w.clock.now
    detected_at = None
    for _ in range(12):  # the worker runs; the clock advances 5 s per cycle
        w.clock.advance(5)
        await w.worker.run_once()
        if await alerts(w, iid, "config_drift"):
            detected_at = w.clock.now
            break
    assert detected_at is not None and detected_at - drifted_at <= timedelta(seconds=60)

    (alert,) = await alerts(w, iid, "config_drift")
    assert (alert.severity, alert.status) == ("critical", "open")
    assert "max_open_positions" in alert.message
    # Exits only: the pause was sent automatically, without waiting for the next cycle.
    assert calls == ["pause_entries"]
    assert (await w.fake.status(ref_of(iid))).state == "exits_only"
    (pause,) = await commands(w, iid, "pause_entries")
    assert pause.actor == "system:worker"
    row = await instance(w, iid)
    assert row.drift == [{"key": "max_open_positions", "expected": "3", "observed": "999"}]
    assert row.effective_config is not None and row.effective_config["max_open_positions"] == "999"
    assert row.effective_config_at == detected_at
    detail = await get(c, f"/api/v1/instances/{iid}")
    assert detail["drift"]["value"] == row.drift and detail["drift"]["observed_at"] is not None

    await w.worker.run_once()
    assert (await commands(w, iid, "pause_entries"))[0].status == "verified"
    shown = await get(c, f"/api/v1/instances/{iid}")
    assert shown["state"]["value"] == "exits_only" and shown["desired_state"] == "running"

    # While the drift lasts, entries do not reopen.
    r = await act(c, iid, "resume-entries")
    assert r.status_code == 202
    await w.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{r.json()['command_id']}")
    assert cmd["status"] == "failed" and "max_open_positions" in cmd["result"]["reason"]
    assert {x["code"] for x in cmd["result"]["reasons"]} == {"drift"}
    assert calls == ["pause_entries"]

    # The configuration is compliant again: the alert resolves, the recorded drift is cleared.
    w.fake.set_failure(ref_of(iid), Failure.DRIFT, on=False)
    w.clock.advance(30)
    await w.worker.run_once()
    assert (await alerts(w, iid, "config_drift"))[0].status == "resolved"
    assert (await instance(w, iid)).drift == []


async def test_s08_owned_key_missing_from_the_reread_is_drift(stack: Stack) -> None:
    """Never silent ignorance: a key the adapter does not re-read, without declaring it."""
    w = stack.world
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    real = w.fake.effective_config

    async def partial(ref: object) -> object:
        eff = await real(ref)  # type: ignore[arg-type]
        return eff.model_copy(
            update={"values": {k: v for k, v in eff.values.items() if k != "stoploss"}}
        )

    w.fake.effective_config = partial  # type: ignore[method-assign,assignment]
    await w.worker.run_once()
    assert (await instance(w, iid)).drift == [
        {"key": "stoploss", "expected": "-0.05", "observed": None}
    ]
    assert [a.severity for a in await alerts(w, iid, "config_drift")] == ["critical"]

    # Declared not re-readable by the adapter: it is no longer a drift.
    render = w.fake.render_config
    w.fake.render_config = lambda spec: render(spec).model_copy(  # type: ignore[method-assign]
        update={"unreadable": frozenset({"stoploss"})}
    )
    w.clock.advance(30)
    await w.worker.run_once()
    assert (await instance(w, iid)).drift == []
    assert (await alerts(w, iid, "config_drift"))[0].status == "resolved"
