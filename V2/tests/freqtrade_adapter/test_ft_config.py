import copy
import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any, get_args

import pytest
from centrade_core.deployment import config_hash
from centrade_core.engine.types import Mode
from centrade_freqtrade import config as ftconfig
from centrade_freqtrade.config import (
    OWNED_KEYS,
    VENUE_CREDENTIAL_KEYS,
    config_file,
    render_config,
)
from hypothesis import given
from hypothesis import strategies as st

from .support import make_spec, make_trailing_spec, sma_manifest

modes = st.sampled_from(get_args(Mode))
stakes = st.decimals(min_value="0.01", max_value="100000", places=2)
stoplosses = st.decimals(min_value="-0.99", max_value="-0.01", places=2)


@st.composite
def specs(draw: st.DrawFn):  # type: ignore[no-untyped-def]
    m = sma_manifest(stoploss=draw(stoplosses))
    m = m.model_copy(update={"sizing": m.sizing.model_copy(update={"stake_amount": draw(stakes)})})
    return make_spec(draw(modes), m)


@given(specs())
def test_render_config_is_pure_and_deterministic(spec) -> None:  # type: ignore[no-untyped-def]
    before = spec.model_dump_json()
    assert render_config(spec) == render_config(spec)
    assert config_file(spec) == config_file(spec)
    assert spec.model_dump_json() == before


@given(specs())
def test_dry_run_is_derived_from_the_mode(spec) -> None:  # type: ignore[no-untyped-def]
    expected = "false" if spec.mode == "live" else "true"
    assert render_config(spec).values["dry_run"] == expected
    assert json.loads(config_file(spec))["dry_run"] is (spec.mode != "live")


@given(modes)
def test_all_owned_keys_are_present(mode: Mode) -> None:
    assert set(render_config(make_trailing_spec(mode)).values) == set(OWNED_KEYS)


def test_owned_keys_have_the_imposed_values() -> None:
    v = render_config(make_spec()).values
    assert v["initial_state"] == "paused"
    assert v["force_entry_enable"] == v["position_adjustment_enable"] == "false"
    assert v["trading_mode"] == "spot"
    assert v["stake_amount"] == "50"
    assert v["available_capital"] == "150"
    assert v["max_open_trades"] == "3"
    assert v["stake_currency"] == "USDT"
    assert v["exchange.name"] == "binance"
    assert json.loads(v["exchange.pair_whitelist"]) == ["BTC/USDT", "ETH/USDT"]
    assert v["stoploss"] == "-0.05"
    assert json.loads(v["order_types"])["emergency_exit"] == "market"
    assert json.loads(v["order_types"])["force_exit"] == "market"
    assert json.loads(v["order_types"])["stoploss_on_exchange"] is True
    assert json.loads(v["minimal_roi"]) == {"0": "0.04", "60": "0.02"}
    assert v["strategy"] == "SmaCross"


@given(st.sampled_from(["backtest", "paper"]))
def test_no_venue_credentials_outside_live(mode: Mode) -> None:
    doc = json.loads(config_file(make_spec(mode)))
    for dotted in VENUE_CREDENTIAL_KEYS:
        _, key = dotted.split(".")
        assert key not in doc["exchange"]
    assert not {"username", "password", "jwt_secret_key", "ws_token"} & set(doc["api_server"])
    assert set(render_config(make_spec(mode)).values).isdisjoint(VENUE_CREDENTIAL_KEYS)


def test_money_not_representable_without_loss_is_rejected() -> None:
    m = sma_manifest()
    m = m.model_copy(
        update={"sizing": m.sizing.model_copy(update={"stake_amount": Decimal("0.1") / 3})}
    )
    with pytest.raises(ValueError, match="sans perte"):
        config_file(make_spec(manifest=m))


@pytest.mark.parametrize(
    "pairs",
    [
        [],
        ["crypto:binance:BTC/USDT", "crypto:kraken:ETH/USDT"],
        ["crypto:binance:BTC/EUR", "crypto:binance:ETH/USDT"],
        ["BTC/USDT"],
    ],
)
def test_invalid_pairs_are_rejected(pairs: list[str]) -> None:
    with pytest.raises(ValueError):
        render_config(make_spec(pairs=pairs))


@given(st.decimals(allow_nan=True, allow_infinity=True))
def test_a_decimal_is_written_without_loss_or_rejected(d: Decimal) -> None:
    """The only `float()` of the package: the text written round-trips to the exact decimal."""
    try:
        text = ftconfig._to_json({"v": d})
    except ValueError:
        return
    assert json.loads(text, parse_float=Decimal, parse_int=Decimal)["v"] == d


@pytest.mark.parametrize("gain", ["Infinity", "NaN", "1e400", "0.1000000000000000055511151231"])
def test_non_finite_or_inexact_profit_target_is_rejected(gain: str) -> None:
    m = sma_manifest()
    exits = m.exits.model_copy(update={"take_profit": {"0": Decimal(gain)}})
    with pytest.raises(ValueError):
        config_file(make_spec(manifest=m.model_copy(update={"exits": exits})))


def leaves(doc: Any, prefix: str = "") -> Iterator[str]:
    if isinstance(doc, dict) and doc:
        for k, v in doc.items():
            yield from leaves(v, f"{prefix}.{k}" if prefix else k)
    else:
        yield prefix


def owner(cfg_keys: Any, leaf: str) -> str | None:
    return next((k for k in cfg_keys if leaf == k or leaf.startswith(k + ".")), None)


@given(specs())
def test_every_key_written_to_the_file_is_owned(spec) -> None:  # type: ignore[no-untyped-def]
    """I10 : nothing is written to the engine configuration outside the fingerprint."""
    cfg = render_config(spec)
    for leaf in leaves(json.loads(config_file(spec))):
        assert owner(cfg.values, leaf), f"clé écrite mais non possédée : {leaf}"
    assert cfg.mode_keys <= cfg.values.keys() and cfg.unreadable <= cfg.values.keys()


def _other(v: Any) -> Any:
    if isinstance(v, bool):
        return not v
    if isinstance(v, (int, Decimal)):
        return v + 1
    if isinstance(v, str):
        return v + "x"
    return [*v, "X"] if isinstance(v, list) else {"x": 1}


@given(spec=specs(), data=st.data())
def test_changing_a_written_key_changes_the_hash(  # type: ignore[no-untyped-def]
    spec, data: st.DataObject
) -> None:
    doc = ftconfig._document(spec)
    leaf = data.draw(st.sampled_from(sorted(leaves(doc))))
    changed = copy.deepcopy(doc)
    cur = changed
    *path, last = leaf.split(".")
    for part in path:
        cur = cur[part]
    cur[last] = _other(cur[last])
    before = render_config(spec)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ftconfig, "_document", lambda _spec: changed)
        after = render_config(spec)
    key = owner(before.values, leaf)
    assert key is not None and before.values[key] != after.values[key], leaf
    same_hash = config_hash(before.values, exclude=before.mode_keys) == config_hash(
        after.values, exclude=after.mode_keys
    )
    assert same_hash is (key in before.mode_keys), leaf  # only the mode keys escape it


def test_platform_execution_setting_is_visible_and_in_the_fingerprint() -> None:
    v = render_config(make_spec()).values
    assert json.loads(v["entry_pricing"])["price_side"] == "other"
    assert json.loads(v["exit_pricing"])["price_side"] == "other"
    assert json.loads(v["unfilledtimeout"]) == {"entry": "10", "exit": "10", "unit": "minutes"}
    assert v["dry_run_wallet"] == "150" and json.loads(v["pairlists"])[0]["method"]
