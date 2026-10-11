import json
from decimal import Decimal
from typing import get_args

import pytest
from centrade_core.engine.types import Mode
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
def test_render_config_est_pure_et_deterministe(spec) -> None:  # type: ignore[no-untyped-def]
    before = spec.model_dump_json()
    assert render_config(spec) == render_config(spec)
    assert config_file(spec) == config_file(spec)
    assert spec.model_dump_json() == before


@given(specs())
def test_dry_run_derive_du_mode(spec) -> None:  # type: ignore[no-untyped-def]
    expected = "false" if spec.mode == "live" else "true"
    assert render_config(spec).values["dry_run"] == expected
    assert json.loads(config_file(spec))["dry_run"] is (spec.mode != "live")


@given(modes)
def test_toutes_les_cles_possedees_sont_presentes(mode: Mode) -> None:
    assert set(render_config(make_trailing_spec(mode)).values) == set(OWNED_KEYS)


def test_cles_possedees_aux_valeurs_imposees() -> None:
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
def test_aucun_identifiant_de_venue_hors_live(mode: Mode) -> None:
    doc = json.loads(config_file(make_spec(mode)))
    for dotted in VENUE_CREDENTIAL_KEYS:
        _, key = dotted.split(".")
        assert key not in doc["exchange"]
    assert not {"username", "password", "jwt_secret_key", "ws_token"} & set(doc["api_server"])
    assert set(render_config(make_spec(mode)).values).isdisjoint(VENUE_CREDENTIAL_KEYS)


def test_argent_non_representable_sans_perte_est_refuse() -> None:
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
def test_paires_invalides_refusees(pairs: list[str]) -> None:
    with pytest.raises(ValueError):
        render_config(make_spec(pairs=pairs))
