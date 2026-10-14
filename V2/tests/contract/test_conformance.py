"""Engine contract conformance suite (SPEC §7), run against each adapter."""

from __future__ import annotations

import pytest
from centrade_core.engine.contract import EngineUnreachable, observe_status, owned_drifts
from centrade_core.events import CanonicalEvent

from .conftest import Harness


async def _events(h: Harness, ref) -> list[CanonicalEvent]:  # type: ignore[no-untyped-def]
    return [ev async for ev in h.adapter.events(ref)]


async def _deploy(h: Harness):  # type: ignore[no-untyped-def]
    return await h.adapter.deploy(h.spec())


async def test_deploy_boots_exits_only_with_matching_config(harness: Harness) -> None:
    spec = harness.spec()
    ref = await harness.adapter.deploy(spec)
    assert (await harness.adapter.status(ref)).state == "exits_only"
    eff = await harness.adapter.effective_config(ref)
    gen = harness.adapter.render_config(spec)
    # A key the engine cannot have re-read is declared, not compared (F9).
    assert eff.values == {k: v for k, v in gen.values.items() if k not in gen.unreadable}


async def test_start_is_idempotent(harness: Harness) -> None:
    ref = await _deploy(harness)
    await harness.adapter.stop(ref)
    await harness.adapter.start(ref)
    await _events(harness, ref)
    await harness.adapter.start(ref)
    assert (await harness.adapter.status(ref)).state == "exits_only"
    assert await _events(harness, ref) == []


async def test_stop_is_idempotent(harness: Harness) -> None:
    ref = await _deploy(harness)
    await harness.adapter.stop(ref)
    await _events(harness, ref)
    await harness.adapter.stop(ref)
    assert (await harness.adapter.status(ref)).state == "stopped"
    assert await _events(harness, ref) == []


async def test_pause_entries_is_idempotent(harness: Harness) -> None:
    ref = await _deploy(harness)
    await harness.adapter.resume_entries(ref)
    await harness.adapter.pause_entries(ref)
    await _events(harness, ref)
    await harness.adapter.pause_entries(ref)
    assert (await harness.adapter.status(ref)).state == "exits_only"
    assert await _events(harness, ref) == []


async def test_no_entry_before_resume_entries(harness: Harness) -> None:
    ref = await _deploy(harness)
    harness.drive(ref, 100)
    evs = await _events(harness, ref)
    assert not [e for e in evs if e.type == "order.submitted" and e.payload.intent == "entry"]  # type: ignore[union-attr]
    snap = await harness.adapter.snapshot(ref)
    assert snap.positions == () and snap.orders == ()
    await harness.adapter.resume_entries(ref)
    assert (await harness.adapter.status(ref)).state == "running"
    harness.drive(ref, 100)
    evs = await _events(harness, ref)
    assert [e for e in evs if e.type == "order.submitted"]


async def test_flatten_leaves_no_position(harness: Harness) -> None:
    ref = await _deploy(harness)
    await harness.adapter.resume_entries(ref)
    for _ in range(300):
        harness.drive(ref, 1)
        if (await harness.adapter.snapshot(ref)).positions:
            break
    assert (await harness.adapter.snapshot(ref)).positions, "scénario sans position"
    await harness.adapter.pause_entries(ref)  # flatten remains possible in exits-only
    await harness.adapter.flatten(ref)
    snap = await harness.adapter.snapshot(ref)
    assert snap.positions == () and snap.orders == () and snap.stops == ()


async def test_unreachable_engine_is_unknown_never_running(harness: Harness) -> None:
    ref = await _deploy(harness)
    await harness.adapter.resume_entries(ref)
    harness.make_unreachable(ref)
    with pytest.raises(EngineUnreachable):
        await harness.adapter.status(ref)
    st = await observe_status(harness.adapter, ref)
    assert st.state == "unknown"


async def test_render_config_is_pure(harness: Harness) -> None:
    spec = harness.spec()
    before = spec.model_dump()
    assert harness.adapter.render_config(spec) == harness.adapter.render_config(spec)
    assert spec.model_dump() == before


async def test_effective_config_drift_is_detectable(harness: Harness) -> None:
    spec = harness.spec()
    ref = await harness.adapter.deploy(spec)
    harness.make_drift(ref)
    eff = await harness.adapter.effective_config(ref)
    assert eff.values != harness.adapter.render_config(spec).values


async def test_config_drift_is_empty_after_deploy_and_names_the_changed_key(
    harness: Harness,
) -> None:
    spec = harness.spec()
    generated = harness.adapter.render_config(spec)
    ref = await harness.adapter.deploy(spec)
    eff = await harness.adapter.effective_config(ref)
    assert harness.adapter.config_drift(generated, eff) == ()
    assert owned_drifts(generated, eff, ()) == ()  # each owned key is re-read or declared
    harness.make_drift(ref)
    eff = await harness.adapter.effective_config(ref)
    drifts = owned_drifts(generated, eff, harness.adapter.config_drift(generated, eff))
    assert drifts and {d.key for d in drifts} <= set(generated.values)
    assert all(d.expected != d.observed for d in drifts)


async def test_declared_keys_are_owned_keys(harness: Harness) -> None:
    generated = harness.adapter.render_config(harness.spec())
    assert generated.unreadable <= set(generated.values)
    assert generated.mode_keys <= set(generated.values)
    # The effective mode is re-read from the status, never from the request.
    ref = await harness.adapter.deploy(harness.spec())
    assert (await harness.adapter.status(ref)).mode == "paper"


async def test_clean_stream_has_unique_ids_and_seq(harness: Harness) -> None:
    ref = await _deploy(harness)
    await harness.adapter.resume_entries(ref)
    harness.drive(ref, 60)
    evs = await _events(harness, ref)
    assert evs
    assert len({e.id for e in evs}) == len(evs)
    assert [e.seq for e in evs] == sorted({e.seq for e in evs})
