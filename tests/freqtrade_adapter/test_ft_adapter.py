"""Adaptateur d'exécution contre la doublure de l'API REST (sans Docker)."""

from __future__ import annotations

import itertools
import json
from decimal import Decimal

import pytest
from centrade_core.engine.contract import CommandRejected, EngineUnreachable, observe_status
from centrade_core.engine.types import EXIT_CAUSES, BacktestSpec, InstanceRef, InstanceSpec
from centrade_freqtrade.adapter import EXIT_CAUSE
from hypothesis import given, settings
from hypothesis import strategies as st

from .double import NOW, STRATEGY_CODE, Rig
from .support import make_spec


async def deployed(rig: Rig) -> tuple[InstanceSpec, InstanceRef]:
    spec = rig.prepare(make_spec())
    return spec, await rig.adapter.deploy(spec)


async def events(rig: Rig, ref: InstanceRef, adapter=None):  # type: ignore[no-untyped-def]
    return [e async for e in (adapter or rig.adapter).events(ref)]


def run_to_position(rig: Rig) -> None:
    rig.server.state = "running"
    for _ in range(2):
        rig.server.step()


async def test_deploy_hands_files_to_the_engine_and_never_env() -> None:
    rig = Rig()
    spec, ref = await deployed(rig)
    c = rig.runner.created[spec.instance_id]
    assert c.command[:4] == ("trade", "--config", "/run/centrade/config.json", "--config")
    assert c.command[4] == "/run/centrade/credentials.json"  # fusionné en dernier
    assert c.env == {} and c.user == "1000:1000"
    assert c.image == "freqtradeorg/freqtrade:2026.9" and c.digest.startswith("sha256:")
    files = rig.runtime.files[spec.instance_id]
    assert set(files) == {"config.json", "control_plane.py", "SmaCross.py"}
    assert files["SmaCross.py"] == STRATEGY_CODE
    cfg = json.loads(files["config.json"])
    assert cfg["initial_state"] == "paused" and cfg["force_entry_enable"] is False
    secrets = rig.runtime.credentials_file[spec.instance_id]["api_server"]
    assert set(secrets) == {"username", "password", "jwt_secret_key", "ws_token"}
    assert not any(v in files["config.json"] for v in secrets.values())
    assert (await rig.adapter.status(ref)).state == "exits_only"


async def test_deploy_is_idempotent_and_refuses_without_deployment() -> None:
    rig = Rig()
    spec, ref = await deployed(rig)
    again = await rig.adapter.deploy(spec)
    assert again == ref and rig.runner.log.count("create") == 1
    with pytest.raises(CommandRejected):
        await rig.adapter.deploy(spec.model_copy(update={"deployment": None}))


async def test_wrong_credentials_give_unknown_never_running() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    rig.server.auth_source = lambda: ("autre", "jeton")
    assert (await observe_status(rig.adapter, ref)).state == "unknown"


async def test_no_command_ever_calls_forceenter() -> None:
    rig = Rig()
    _spec, ref = await deployed(rig)
    a = rig.adapter
    await a.resume_entries(ref)
    run_to_position(rig)
    await a.pause_entries(ref)
    await a.close_position(ref, "1")
    await a.flatten(ref)
    await a.stop(ref)
    await a.start(ref)
    assert rig.server.calls and not [c for c in rig.server.calls if "forceenter" in c[1]]


async def test_stop_pauses_cancels_entries_then_stops_container_and_cleans_up() -> None:
    rig = Rig()
    spec, ref = await deployed(rig)
    await rig.adapter.resume_entries(ref)
    rig.server.step()  # un ordre d'entrée ouvert
    assert (await rig.adapter.snapshot(ref)).orders
    rig.server.calls.clear()
    await rig.adapter.stop(ref)
    paths = [p for m, p in rig.server.calls]
    assert paths.index("pause") < paths.index("trades/1/open-order")
    assert "stop" not in paths  # jamais un simple POST /stop
    assert rig.runner.status[spec.instance_id] == "exited"
    assert rig.runtime.cleaned == [spec.instance_id]
    assert not rig.server.trades[0]["orders"][0]["is_open"]


async def test_start_after_stop_renews_credentials_and_boots_exits_only() -> None:
    rig = Rig()
    spec, ref = await deployed(rig)
    before = dict(rig.runtime.issued[spec.instance_id])
    await rig.adapter.resume_entries(ref)
    await rig.adapter.stop(ref)
    await rig.adapter.start(ref)
    assert rig.runtime.issued[spec.instance_id] != before
    assert rig.runtime.credentials_file[spec.instance_id]
    assert (await rig.adapter.status(ref)).state == "exits_only"


async def test_flatten_closes_everything_and_never_stops_the_container() -> None:
    rig = Rig()
    spec, ref = await deployed(rig)
    run_to_position(rig)
    rig.server.open_exit_order(rig.server.trades[0])
    await rig.adapter.flatten(ref)
    snap = await rig.adapter.snapshot(ref)
    assert snap.positions == () and snap.orders == () and snap.stops == ()
    assert rig.runner.status[spec.instance_id] == "running"
    assert snap.closed[0].exit_cause == "manual"


async def test_close_position_is_idempotent() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    run_to_position(rig)
    await rig.adapter.close_position(ref, "1")
    await rig.adapter.close_position(ref, "1")
    assert (await rig.adapter.snapshot(ref)).positions == ()


async def test_cancel_entry_order_refused_when_an_exit_order_is_open() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    t = rig.server.open_entry()
    rig.server.open_exit_order(t)  # entrée encore ouverte et ordre de sortie ouvert
    snap = await rig.adapter.snapshot(ref)
    entry = next(o for o in snap.orders if o.intent == "entry")
    with pytest.raises(CommandRejected):
        await rig.adapter.cancel_entry_order(ref, entry.order_id)
    assert all(o["is_open"] for o in t["orders"])  # rien n'a été annulé


async def test_cancel_entry_order_cancels_an_entry_only_trade() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    t = rig.server.open_entry()
    entry = (await rig.adapter.snapshot(ref)).orders[0]
    await rig.adapter.cancel_entry_order(ref, entry.order_id)
    assert not t["orders"][0]["is_open"]
    await rig.adapter.cancel_entry_order(ref, entry.order_id)  # idempotent


async def test_halted_engine_is_halted_and_cannot_resume() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    rig.server.state = "stopped"  # processus vivant, moteur arrêté
    assert (await rig.adapter.status(ref)).state == "halted"
    with pytest.raises(CommandRejected):
        await rig.adapter.resume_entries(ref)
    await rig.adapter.start(ref)  # conteneur en marche : remet le moteur en sorties seules
    assert (await rig.adapter.status(ref)).state == "exits_only"


async def test_flatten_works_on_a_halted_engine() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    run_to_position(rig)
    rig.server.state = "stopped"
    await rig.adapter.flatten(ref)
    assert (await rig.adapter.snapshot(ref)).positions == ()


async def test_mode_is_read_from_the_engine_not_from_the_request() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    rig.server.cfg.update(dry_run=False, runmode="live")
    assert (await rig.adapter.status(ref)).mode == "live"


async def test_stale_heartbeat_is_error() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    rig.clock.now = NOW.replace(hour=14)  # le moteur n'a rien traité depuis des heures
    rig.server.clock = lambda: NOW  # type: ignore[assignment]
    assert (await rig.adapter.status(ref)).state == "error"


async def test_effective_config_carries_fingerprint_version_and_drift() -> None:
    rig = Rig()
    spec, ref = await deployed(rig)
    eff = await rig.adapter.effective_config(ref)
    assert eff.fingerprint == "f" * 64 and eff.engine_version == "2026.9"
    gen = rig.adapter.render_config(spec)
    assert rig.adapter.config_drift(gen, eff) == ()
    assert not (set(gen.values) - eff.values.keys() - gen.unreadable)
    rig.server.cfg["stoploss"] = -0.5
    rig.server.pairs = ["ETH/USDT"]
    keys = {d.key for d in rig.adapter.config_drift(gen, await rig.adapter.effective_config(ref))}
    assert keys == {"stoploss", "exchange.pair_whitelist"}


async def test_snapshot_keeps_decimals_exact_and_normalises_symbols() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    t = rig.server.open_entry()
    t["orders"][0]["safe_price"] = Decimal("0.1000000000000000055511151231257827")
    snap = await rig.adapter.snapshot(ref)
    assert snap.orders[0].price == Decimal("0.1000000000000000055511151231257827")
    assert snap.orders[0].symbol == "crypto:binance:BTC/USDT" and snap.orders[0].intent == "entry"
    assert snap.balances[0].currency == "USDT" and snap.balances[0].free == Decimal("150.0")
    rig.server.step()
    snap = await rig.adapter.snapshot(ref)
    assert snap.positions[0].position_id == "1" and snap.stops[0].held_by == "engine"
    assert snap.stops[0].price == Decimal("95.5")


async def test_client_order_id_is_deterministic_across_adapters() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    rig.server.open_entry()
    first = (await rig.adapter.snapshot(ref)).orders[0].order_id
    other = rig.new_adapter()
    assert (await other.snapshot(ref)).orders[0].order_id == first


async def test_closed_trade_is_read_with_translated_exit_cause() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    run_to_position(rig)
    rig.server.close_trade(rig.server.trades[0], "trailing_stop_loss")
    rig.server.open_entry()
    rig.server.close_trade(rig.server.trades[1], "reason_from_the_future")
    closed = (await rig.adapter.snapshot(ref)).closed
    assert [c.exit_cause for c in closed] == ["unknown", "trailing_stop"] or {
        c.exit_cause for c in closed
    } == {"trailing_stop", "unknown"}
    c = next(c for c in closed if c.position_id == "1")
    assert c.pnl == Decimal("0.25") and c.fees == Decimal("0.10") and c.entry_cause == "signal"
    assert c.position_id == "1"  # même identifiant que la position ouverte


async def test_closed_window_is_bounded() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    for _ in range(60):
        rig.server.close_trade(rig.server.open_entry(), "roi")
        rig.clock.now = rig.clock.now.replace(microsecond=0)
    assert len((await rig.adapter.snapshot(ref)).closed) == 50


async def test_events_cover_the_trade_lifecycle_and_replay_without_duplicates() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    await rig.adapter.resume_entries(ref)
    out = await events(rig, ref)
    assert [e.type.value for e in out] == ["instance.status_changed"]
    for _ in range(3):
        rig.server.step()
        out += await events(rig, ref)
    kinds = [e.type.value for e in out]
    for expected in ("order.submitted", "order.filled", "position.updated",
                     "protection.updated", "position.closed"):  # fmt: skip
        assert expected in kinds
    closed = next(e for e in out if e.type.value == "position.closed")
    assert closed.payload.exit_cause == "take_profit"
    assert await events(rig, ref) == []  # rien de nouveau : rien d'émis
    # Un worker redémarré rejoue tout, avec les mêmes identifiants : l'ingestion les écarte.
    replay = await events(rig, ref, rig.new_adapter())
    assert {e.id for e in replay if e.type.value != "instance.status_changed"} <= {
        e.id for e in out
    }
    assert len({e.id for e in out}) == len(out)
    assert [e.seq for e in out] == sorted({e.seq for e in out})


async def test_events_announce_the_stop_once() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    await events(rig, ref)
    await rig.adapter.stop(ref)
    out = await events(rig, ref)
    assert [e.payload.state for e in out] == ["stopped"]
    assert await events(rig, ref) == []


async def test_backtest_is_not_available() -> None:
    rig = Rig()
    spec = rig.prepare(make_spec())
    with pytest.raises(CommandRejected, match="non disponible"):
        await rig.adapter.backtest(
            BacktestSpec(manifest=spec.manifest, start=NOW, end=NOW, timeframe="5m")
        )


async def test_unreachable_engine_raises_not_invents() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    rig.server.unreachable = True
    for call in (rig.adapter.status, rig.adapter.snapshot, rig.adapter.effective_config,
                 rig.adapter.resume_entries):  # fmt: skip
        with pytest.raises(EngineUnreachable):
            await call(ref)


@given(reason=st.text())
def test_every_engine_reason_translates_into_the_f10_enumeration(reason: str) -> None:
    assert EXIT_CAUSE.get(reason, "unknown") in EXIT_CAUSES
    assert set(EXIT_CAUSE.values()) <= set(EXIT_CAUSES)


@settings(max_examples=60, deadline=None)
@given(plan=st.lists(st.sampled_from(["step", "drain", "pause", "resume", "flatten"]), max_size=40))
async def test_event_stream_never_duplicates_whatever_the_run(plan: list[str]) -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    out = []
    for action in plan:
        if action == "step":
            rig.server.step()
        elif action == "drain":
            out += await events(rig, ref)
        elif action == "pause":
            await rig.adapter.pause_entries(ref)
        elif action == "resume":
            await rig.adapter.resume_entries(ref)
        else:
            await rig.adapter.flatten(ref)
    out += await events(rig, ref)
    assert len({e.id for e in out}) == len(out)
    assert all(a.seq < b.seq for a, b in itertools.pairwise(out))
    assert await events(rig, ref) == []
