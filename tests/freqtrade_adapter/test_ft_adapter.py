"""Adaptateur d'exécution contre la doublure de l'API REST (sans Docker)."""

from __future__ import annotations

import itertools
import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from centrade_core.engine.contract import CommandRejected, EngineUnreachable, observe_status
from centrade_core.engine.types import EXIT_CAUSES, BacktestSpec, InstanceRef, InstanceSpec
from centrade_freqtrade import adapter as ft
from centrade_freqtrade import client
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


def close_many(rig: Rig, n: int) -> None:
    for _ in range(n):
        rig.server.close_trade(rig.server.open_entry(), "roi")
        rig.clock.now += timedelta(seconds=1)


def trade_pages(rig: Rig) -> list[tuple[int, int]]:
    """(offset, limit) de chaque appel à GET /trades."""
    return [
        (int(q["offset"][0]), int(q["limit"][0]))
        for (_, path), q in zip(rig.server.calls, rig.server.queries, strict=True)
        if path == "trades"
    ]


async def test_first_read_of_a_process_returns_the_whole_closed_history() -> None:
    """I9, S5 : après un arrêt du worker, aucun trade clos n'est perdu, quel qu'en soit le rang."""
    rig = Rig()
    _, ref = await deployed(rig)
    close_many(rig, 60)
    closed = (await rig.adapter.snapshot(ref)).closed
    assert [c.position_id for c in closed] == [str(i) for i in range(1, 61)]  # ancien -> récent


async def test_closed_history_is_read_by_pages_then_only_recent_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ft, "HISTORY_PAGE", 7)
    monkeypatch.setattr(ft, "RECENT_PAGE", 3)
    rig = Rig()
    _, ref = await deployed(rig)
    close_many(rig, 20)
    assert len((await rig.adapter.snapshot(ref)).closed) == 20
    assert trade_pages(rig) == [(0, 7), (7, 7), (14, 7)]  # jusqu'à la page incomplète
    rig.server.calls.clear()
    rig.server.queries.clear()
    close_many(rig, 1)
    recent = (await rig.adapter.snapshot(ref)).closed
    assert trade_pages(rig) == [(0, 3)]  # régime courant : une page récente suffit
    assert "21" in {c.position_id for c in recent}
    # Plus de clôtures qu'une page entre deux relevés : on pagine jusqu'à recouper le déjà-lu.
    rig.server.calls.clear()
    rig.server.queries.clear()
    close_many(rig, 8)
    recent = (await rig.adapter.snapshot(ref)).closed
    assert {str(i) for i in range(22, 30)} <= {c.position_id for c in recent}
    assert trade_pages(rig) == [(0, 3), (3, 3), (6, 3)]
    # Un autre processus (worker redémarré) relit tout.
    assert len((await rig.new_adapter().snapshot(ref)).closed) == 29


async def test_events_replay_the_whole_history_after_a_worker_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ft, "HISTORY_PAGE", 7)
    monkeypatch.setattr(ft, "RECENT_PAGE", 3)
    rig = Rig()
    _, ref = await deployed(rig)
    close_many(rig, 20)
    await rig.adapter.snapshot(ref)  # le relevé ne doit pas priver les événements de l'historique
    out = await events(rig, ref, rig.new_adapter())
    closed = {e.payload.position_id for e in out if e.type.value == "position.closed"}
    assert closed == {str(i) for i in range(1, 21)}
    close_many(rig, 5)
    more = await events(rig, ref)  # premier relevé de cet adaptateur-ci : tout, sans doublon
    assert len({e.id for e in more}) == len(more)
    assert sum(e.type.value == "position.closed" for e in more) == 25
    close_many(rig, 5)
    last = await events(rig, ref)
    assert {e.payload.position_id for e in last if e.type.value == "position.closed"} == {
        str(i) for i in range(26, 31)
    }


async def test_closed_history_beyond_the_cap_raises_instead_of_losing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ft, "HISTORY_PAGE", 7)
    monkeypatch.setattr(ft, "HISTORY_CAP", 14)
    rig = Rig()
    _, ref = await deployed(rig)
    close_many(rig, 14)
    with pytest.raises(ft.ClosedHistoryOverflow, match="14"):
        await rig.adapter.snapshot(ref)
    with pytest.raises(EngineUnreachable):  # ce que le worker attrape
        await events(rig, ref)
    assert (await rig.adapter.status(ref)).state == "exits_only"  # l'état, lui, reste lisible
    await rig.adapter.flatten(ref)  # et une sortie n'en dépend pas (I4)


# --- I4 : rien ne retient une sortie ni un arrêt ------------------------------------------------
CANCEL = ("DELETE", "trades/1/open-order")
REFUSED = (502, {"detail": "Order cancel failed"})


@pytest.mark.parametrize("failure", [REFUSED, None, (500, {}), (200, "pas du JSON attendu")])
@pytest.mark.parametrize("broken", [CANCEL, ("POST", "pause"), ("GET", "status")])
async def test_flatten_sends_forceexit_whatever_happens_to_pause_and_cancel(
    broken: tuple[str, str], failure: tuple[int, object] | None
) -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    run_to_position(rig)  # trade 1 : position ouverte
    rig.server.open_entry()  # trade 2 : ordre d'entrée ouvert
    rig.server.trades[0]["trade_id"], rig.server.trades[1]["trade_id"] = 2, 1
    rig.server.fail[broken] = failure
    try:
        await rig.adapter.flatten(ref)
    except (EngineUnreachable, CommandRejected):
        pass  # l'échec de la pause ou de l'annulation remonte, mais après la sortie
    assert ("POST", "forceexit") in rig.server.calls
    assert rig.server.open_trades() == []


async def test_flatten_reports_the_failed_cancel_after_the_exit() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    rig.server.open_entry()
    rig.server.fail[CANCEL] = REFUSED
    with pytest.raises(CommandRejected, match="Order cancel failed"):
        await rig.adapter.flatten(ref)
    assert rig.server.calls.index(CANCEL) < rig.server.calls.index(("POST", "forceexit"))


@pytest.mark.parametrize("broken", [CANCEL, ("POST", "pause"), ("GET", "status")])
@pytest.mark.parametrize("failure", [REFUSED, None])
async def test_stop_always_stops_the_container(
    broken: tuple[str, str], failure: tuple[int, object] | None
) -> None:
    rig = Rig()
    spec, ref = await deployed(rig)
    await rig.adapter.resume_entries(ref)
    rig.server.step()  # un ordre d'entrée ouvert
    rig.server.fail[broken] = failure
    with pytest.raises((EngineUnreachable, CommandRejected)):
        await rig.adapter.stop(ref)  # l'échec remonte, après l'arrêt
    assert rig.runner.status[spec.instance_id] == "exited"
    assert rig.runtime.cleaned == [spec.instance_id]
    assert ("POST", "stop") not in rig.server.calls
    if broken != ("POST", "pause"):
        assert ("POST", "pause") in rig.server.calls  # ce qui pouvait être tenté l'a été
    await rig.adapter.stop(ref)  # idempotent : conteneur déjà arrêté, plus rien à signaler


async def test_stop_does_not_wait_for_a_silent_engine_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ft, "STOP_GRACE_S", 0.05)
    rig = Rig()
    spec, ref = await deployed(rig)
    rig.server.delay_s = 0.4  # l'API répond trop tard
    with pytest.raises(EngineUnreachable):
        await rig.adapter.stop(ref)
    assert rig.runner.status[spec.instance_id] == "exited"


async def test_stop_with_an_unreachable_api_still_stops() -> None:
    rig = Rig()
    spec, ref = await deployed(rig)
    rig.server.unreachable = True
    with pytest.raises(EngineUnreachable):
        await rig.adapter.stop(ref)
    assert rig.runner.status[spec.instance_id] == "exited"


async def test_pause_never_cancels_an_exit_order() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    run_to_position(rig)
    rig.server.open_exit_order(rig.server.trades[0])  # trade 1 : sortie ouverte
    both = rig.server.open_entry()  # trade 2 : entrée ET sortie ouvertes (la route annule tout)
    rig.server.open_exit_order(both)
    await rig.adapter.pause_entries(ref)
    assert not [c for c in rig.server.calls if c[0] == "DELETE"]
    assert (
        all(o["is_open"] for o in both["orders"]) and rig.server.trades[0]["orders"][-1]["is_open"]
    )
    only = rig.server.open_entry()  # trade 3 : entrée seule
    await rig.adapter.pause_entries(ref)
    assert [c for c in rig.server.calls if c[0] == "DELETE"] == [("DELETE", "trades/3/open-order")]
    assert not only["orders"][0]["is_open"]


async def test_pause_still_cancels_entries_when_the_pause_call_fails() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    t = rig.server.open_entry()
    rig.server.fail[("POST", "pause")] = (500, {})
    with pytest.raises(EngineUnreachable):
        await rig.adapter.pause_entries(ref)
    assert not t["orders"][0]["is_open"]


async def test_close_position_is_sent_even_when_the_engine_state_is_unreadable() -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    run_to_position(rig)
    rig.server.override["show_config"] = ["illisible"]
    await rig.adapter.close_position(ref, "1")
    assert rig.server.open_trades() == []


# --- battement ----------------------------------------------------------------------------------
@pytest.mark.parametrize("beat", [None, "1760270400", 1.5, True, [], {}])
async def test_missing_or_non_integer_heartbeat_is_unknown(beat: object) -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    rig.server.override["health"] = {"last_process_ts": beat}
    assert (await observe_status(rig.adapter, ref)).state == "unknown"
    rig.server.override["health"] = {}
    assert (await observe_status(rig.adapter, ref)).state == "unknown"


async def test_halted_engine_does_not_beat_and_stays_halted() -> None:
    """Tag 2026.9 : `process_stopped` ne met pas `last_process` à jour. `halted` reste visible."""
    rig = Rig()
    _, ref = await deployed(rig)
    rig.server.state = "stopped"
    rig.server.override["health"] = {"last_process_ts": None}
    assert (await rig.adapter.status(ref)).state == "halted"


# --- réponses malformées --------------------------------------------------------------------------
json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-(10**30), max_value=10**30)
    | st.decimals(allow_nan=False, allow_infinity=False)
    | st.text(max_size=8),
    lambda inner: (
        st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=8), inner, max_size=4)
    ),
    max_leaves=12,
)
ROUTES = ("show_config", "health", "whitelist", "status", "trades", "balance")


@st.composite
def damaged(draw: st.DrawFn, body: Any) -> Any:
    """Une réponse plausible, abîmée : clés retirées, valeurs remplacées par n'importe quoi."""
    if isinstance(body, dict) and body:
        out = dict(body)
        for key in draw(st.lists(st.sampled_from(sorted(out)), max_size=3, unique=True)):
            if draw(st.booleans()):
                del out[key]
            elif draw(st.booleans()):
                out[key] = draw(json_values)
            else:
                out[key] = draw(damaged(out[key]))
        return out
    if isinstance(body, list) and body:
        return [draw(damaged(x)) for x in body]
    return draw(json_values)


@settings(max_examples=300, deadline=None)
@given(data=st.data(), route=st.sampled_from(ROUTES), wreck=st.booleans())
async def test_any_engine_answer_only_raises_contract_exceptions(
    data: st.DataObject, route: str, wreck: bool
) -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    run_to_position(rig)
    rig.server.close_trade(rig.server.open_entry(), "roi")
    rig.server.open_entry()
    good = rig.server._get(route, {"order_by_id": ["false"]})
    rig.server.override[route] = data.draw(json_values if wreck else damaged(good))
    a = rig.adapter
    for call in (a.status, a.snapshot, a.effective_config, lambda r: events(rig, r),
                 a.pause_entries, a.flatten):  # fmt: skip
        try:
            await call(ref)
        except (EngineUnreachable, CommandRejected):
            pass  # seules exceptions du contrat : l'instance devient `unknown`, pas le tour


@pytest.mark.parametrize(
    "raw",
    [b"[" * 100_000, b"{" + b'"a":' * 50_000, b"\xff\xfe", b"NaN", b'{"a": Infinity}',
     b"1e99999999", b""],
)  # fmt: skip
async def test_unreadable_bodies_are_unreachable(raw: bytes) -> None:
    rig = Rig()
    _, ref = await deployed(rig)
    rig.server.raw_body = raw
    for call in (rig.adapter.status, rig.adapter.snapshot, rig.adapter.effective_config):
        with pytest.raises(EngineUnreachable):
            await call(ref)


async def test_oversized_answer_is_refused_without_reading_it_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client, "MAX_RESPONSE_BYTES", 8192)
    rig = Rig()
    _, ref = await deployed(rig)
    assert (await rig.adapter.status(ref)).state == "exits_only"  # réponses courtes : lues
    rig.server.raw_body = b'{"a": "' + b"x" * 50_000 + b'"}'
    with pytest.raises(EngineUnreachable, match="volumineuse"):
        await rig.adapter.status(ref)


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
