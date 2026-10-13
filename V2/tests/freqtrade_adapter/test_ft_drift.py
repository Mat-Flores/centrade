import json
from typing import Any

from centrade_core.engine.types import InstanceSpec
from centrade_freqtrade.config import (
    OBSERVABLE_KEYS,
    OWNED_KEYS,
    config_file,
    drift,
    effective_mode,
    render_config,
)
from hypothesis import given
from hypothesis import strategies as st

from .support import make_spec, make_trailing_spec


def show_config(spec: InstanceSpec) -> dict[str, Any]:
    """Réponse de GET /show_config telle que le tag la forme (flottants, `exchange` en chaîne,
    infini en -1, `state` à la place de initial_state), plus `pair_whitelist` de GET /whitelist."""
    d = json.loads(config_file(spec))
    return {
        **{
            k: d.get(k)
            for k in (
                "dry_run",
                "trading_mode",
                "stake_currency",
                "stoploss",
                "bot_name",
                "strategy",
                "minimal_roi",
                "order_types",
                "trailing_stop",
                "trailing_stop_positive",
                "trailing_stop_positive_offset",
                "trailing_only_offset_is_reached",
                "max_open_trades",
                "available_capital",
                "force_entry_enable",
                "position_adjustment_enable",
                "unfilledtimeout",
                "entry_pricing",
                "exit_pricing",
            )
        },
        "stake_amount": str(d["stake_amount"]),
        "exchange": d["exchange"]["name"],
        "pair_whitelist": d["exchange"]["pair_whitelist"],
        "stoploss_on_exchange": d["order_types"]["stoploss_on_exchange"],
        "state": "paused",
        "runmode": "live" if spec.mode == "live" else "dry_run",
        "version": "2026.9",
    }


def _mutate(key: str, v: Any) -> Any:
    if isinstance(v, bool):
        return not v
    if isinstance(v, (int, float)):
        return v + 1
    if isinstance(v, str):
        return v + "x"
    if isinstance(v, list):
        return [*v, "SOL/USDT"]
    if key == "minimal_roi":
        return {**v, "999": 1.0}
    first = next(iter(v))  # comparées par sous-ensemble : on change une de nos entrées
    return {**v, first: _mutate(first, v[first])}


def test_no_drift_on_a_conforming_config() -> None:
    for spec in (make_spec(), make_trailing_spec(), make_spec("live")):
        assert drift(render_config(spec), show_config(spec)) == []


@given(st.sampled_from(OBSERVABLE_KEYS))
def test_drift_is_reported_for_every_modified_owned_key(key: str) -> None:
    spec = make_trailing_spec()
    eff = show_config(spec)
    src = {"exchange.name": "exchange", "exchange.pair_whitelist": "pair_whitelist"}.get(key, key)
    eff[src] = _mutate(key, eff[src])
    assert [d.key for d in drift(render_config(spec), eff)] == [key]


@given(st.sampled_from(OBSERVABLE_KEYS))
def test_missing_observable_key_is_a_drift(key: str) -> None:
    spec = make_trailing_spec()
    eff = show_config(spec)
    eff.pop(
        {"exchange.name": "exchange", "exchange.pair_whitelist": "pair_whitelist"}.get(key, key)
    )
    assert [d.key for d in drift(render_config(spec), eff)] == [key]


def test_unowned_key_is_ignored_and_engine_defaults_are_tolerated() -> None:
    spec = make_spec()
    eff = show_config(spec)
    eff.update(state="running", timeframe="1h", version="9999", use_custom_stoploss=None)
    eff["order_types"] = {**eff["order_types"], "entry_extra": "limit"}
    eff["unfilledtimeout"] = {**eff["unfilledtimeout"], "exit_timeout_count": 0}
    eff["entry_pricing"] = {**eff["entry_pricing"], "price_last_balance": 0.0, "extra": 1}
    depth = {**eff["entry_pricing"]["check_depth_of_market"], "extra": True}
    eff["entry_pricing"]["check_depth_of_market"] = depth
    assert drift(render_config(spec), eff) == []


def test_equivalent_forms_are_not_drifts() -> None:
    spec = make_spec()
    eff = show_config(spec)
    eff.update(stake_amount="50.0", available_capital=150, stoploss=-0.050)
    assert drift(render_config(spec), eff) == []


def test_unobservable_keys_are_documented() -> None:
    assert set(OWNED_KEYS) - set(OBSERVABLE_KEYS) == {
        "db_url", "initial_state", "tradable_balance_ratio", "cancel_open_orders_on_exit",
        "api_server.enabled", "api_server.listen_ip_address", "api_server.listen_port",
        "webhook.enabled", "webhook.allow_custom_messages", "telegram.enabled",
        "exchange.pair_blacklist", "api_server.verbosity", "api_server.CORS_origins",
        "pairlists", "dry_run_wallet", "centrade_params",
    }  # fmt: skip


def test_drift_on_a_nested_execution_setting() -> None:
    spec = make_spec()
    eff = show_config(spec)
    eff["entry_pricing"] = {**eff["entry_pricing"], "price_side": "same"}
    eff["exit_pricing"] = {"use_order_book": True, "order_book_top": 1}  # price_side retiré
    depth = {**eff["entry_pricing"]["check_depth_of_market"], "enabled": True}
    assert [d.key for d in drift(render_config(spec), eff)] == ["entry_pricing", "exit_pricing"]
    eff = show_config(spec)
    eff["entry_pricing"] = {**eff["entry_pricing"], "check_depth_of_market": depth}
    assert [d.key for d in drift(render_config(spec), eff)] == ["entry_pricing"]


def test_reread_value_of_an_unexpected_shape_is_a_drift_not_an_error() -> None:
    spec = make_spec()
    for odd in ("pas un dictionnaire", 3, [1], {"entry": {"imbriqué": 1}}):
        eff = show_config(spec)
        eff["unfilledtimeout"] = odd
        assert [d.key for d in drift(render_config(spec), eff)] == ["unfilledtimeout"]


def test_effective_mode() -> None:
    assert effective_mode({"dry_run": True, "runmode": "dry_run"}) == "paper"
    assert effective_mode({"dry_run": True, "runmode": "backtest"}) == "backtest"
    assert effective_mode({"dry_run": False, "runmode": "live"}) == "live"
    assert effective_mode({"dry_run": False, "runmode": "dry_run"}) is None
    assert effective_mode({"dry_run": True, "runmode": "live"}) is None
    assert effective_mode({"runmode": "live"}) is None
    assert effective_mode({}) is None
