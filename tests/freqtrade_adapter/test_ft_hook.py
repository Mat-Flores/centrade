"""Le hook d'entrée de ControlPlaneStrategy. Freqtrade n'est pas installé ici : une doublure
minimale d'IStrategy est injectée dans sys.modules."""

import importlib
import sys
import types
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest


class FakeIStrategy:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config


@pytest.fixture
def strategy_cls() -> Iterator[Any]:
    saved = {k: sys.modules.get(k) for k in ("freqtrade", "freqtrade.strategy")}
    ft, strat = types.ModuleType("freqtrade"), types.ModuleType("freqtrade.strategy")
    strat.IStrategy = FakeIStrategy  # type: ignore[attr-defined]
    sys.modules.update({"freqtrade": ft, "freqtrade.strategy": strat})
    sys.modules.pop("centrade_freqtrade.control_plane", None)
    yield importlib.import_module("centrade_freqtrade.control_plane").ControlPlaneStrategy
    sys.modules.pop("centrade_freqtrade.control_plane", None)
    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


def enter(s: Any) -> Any:
    return s.confirm_trade_entry(
        pair="BTC/USDT", order_type="limit", amount=1.0, rate=1.0, time_in_force="GTC",
        current_time=datetime.now(UTC), entry_tag=None, side="long",
    )  # fmt: skip


def test_dry_run_accepte(strategy_cls: Any) -> None:
    assert enter(strategy_cls({"dry_run": True})) is True


@pytest.mark.parametrize("cfg", [{"dry_run": False}, {}, {"dry_run": "true"}, {"dry_run": 1}])
def test_hors_dry_run_refuse(strategy_cls: Any, cfg: dict[str, Any]) -> None:
    assert enter(strategy_cls(cfg)) is False


def test_exception_interne_refuse_sans_lever(strategy_cls: Any) -> None:
    s = strategy_cls({"dry_run": True})

    def boom(**_: Any) -> bool:
        raise RuntimeError("panne")

    s._entry_allowed = boom
    assert enter(s) is False


def test_reponse_non_booleenne_refusee(strategy_cls: Any) -> None:
    s = strategy_cls({"dry_run": True})
    s._entry_allowed = lambda **_: "oui"
    assert enter(s) is False


def test_sortie_jamais_bloquee_et_chemins_d_entree_fermes(strategy_cls: Any) -> None:
    s = strategy_cls({"dry_run": False})
    assert s.confirm_trade_exit(pair="BTC/USDT", exit_reason="stop_loss") is True
    assert s.adjust_trade_position(trade=None) is None
    assert s.adjust_order_price(current_order_rate=5.0, proposed_rate=9.0, is_entry=False) == 5.0
    assert s.leverage(pair="BTC/USDT", proposed_leverage=3.0) == 1.0
