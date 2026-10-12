"""Le hook d'entrée de ControlPlaneStrategy. Freqtrade n'est pas installé ici : une doublure
minimale d'IStrategy est injectée dans sys.modules."""

import importlib
import sys
import types
from abc import ABC
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest


class FakeIStrategy(ABC):  # noqa: B024  # ABC comme le vrai IStrategy : ajoute `_abc_impl` aux sous-classes
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
    def boom(self: Any, **_: Any) -> bool:
        raise RuntimeError("panne")

    type.__setattr__(strategy_cls, "_entry_allowed", boom)  # la base elle-même, pour l'essai
    assert enter(strategy_cls({"dry_run": True})) is False


def test_reponse_non_booleenne_refusee(strategy_cls: Any) -> None:
    type.__setattr__(strategy_cls, "_entry_allowed", lambda self, **_: "oui")
    assert enter(strategy_cls({"dry_run": True})) is False


def test_config_illisible_refuse_sans_lever(strategy_cls: Any) -> None:
    class Broken(dict[str, Any]):
        def get(self, *a: Any) -> Any:
            raise RuntimeError("panne")

    s = strategy_cls({"dry_run": True})
    s.config = Broken()
    assert enter(s) is False


def test_sortie_jamais_bloquee_et_chemins_d_entree_fermes(strategy_cls: Any) -> None:
    s = strategy_cls({"dry_run": False})
    assert s.confirm_trade_exit(pair="BTC/USDT", exit_reason="stop_loss") is True
    assert s.adjust_trade_position(trade=None) is None
    assert s.adjust_order_price(current_order_rate=5.0, proposed_rate=9.0, is_entry=False) == 5.0
    assert s.leverage(pair="BTC/USDT", proposed_leverage=3.0) == 1.0


def test_mode_capture_a_la_construction(strategy_cls: Any) -> None:
    cfg = {"dry_run": False}
    s = strategy_cls(cfg)
    cfg["dry_run"] = True  # modifié après coup : sans effet
    assert enter(s) is False
    cfg2 = {"dry_run": True}
    s2 = strategy_cls(cfg2)
    cfg2["dry_run"] = False
    assert enter(s2) is False


def test_sous_classe_qui_redefinit_un_nom_protege_est_refusee(strategy_cls: Any) -> None:
    for name in ("_entry_allowed", "confirm_trade_entry", "leverage", "adjust_exit_price",
                 "_boot_dry_run", "__init__", "__setattr__", "_intact"):  # fmt: skip
        with pytest.raises(TypeError, match=name):
            type("S", (strategy_cls,), {name: lambda *a, **k: True})


HOOKS = ("_entry_allowed", "confirm_trade_entry", "confirm_trade_exit", "leverage", "_intact")


@pytest.mark.parametrize("name", HOOKS)
def test_nom_protege_non_reaffectable_sur_la_classe_ni_sur_l_instance(
    strategy_cls: Any, name: str
) -> None:
    sub = type("S", (strategy_cls,), {})
    s = sub({"dry_run": True})
    for target in (sub, strategy_cls, s):
        with pytest.raises(TypeError, match=name):
            setattr(target, name, lambda *a, **k: True)
        with pytest.raises(TypeError, match=name):
            delattr(target, name)
    assert enter(s) is True  # rien n'a changé


def test_mode_non_reaffectable_apres_la_construction(strategy_cls: Any) -> None:
    s = strategy_cls({"dry_run": False})
    with pytest.raises(TypeError):
        s._boot_dry_run = True
    s.config["dry_run"] = True
    assert enter(s) is False


def test_classe_placee_avant_la_base_ne_masque_aucun_nom_protege(strategy_cls: Any) -> None:
    for name in ("confirm_trade_entry", "_entry_allowed", "_intact"):
        mixin = type("Mixin", (), {name: lambda *a, **k: True})
        with pytest.raises(TypeError, match=name):
            type("S", (mixin, strategy_cls), {})


@pytest.mark.parametrize("name", ["_entry_allowed", "_boot_dry_run", "leverage"])
def test_hook_refuse_si_un_nom_protege_est_masque_malgre_tout(strategy_cls: Any, name: str) -> None:
    """Écritures qui évitent `__setattr__` (inaccessibles à une stratégie contrôlée) : le hook
    constate à l'appel que le type ne résout plus les noms de la base, et refuse."""
    sub = type("S", (strategy_cls,), {})
    s = sub({"dry_run": True})
    type.__setattr__(sub, name, lambda *a, **k: True)
    assert enter(s) is False
    sub2 = type("S2", (strategy_cls,), {})
    s2 = sub2({"dry_run": True})
    if name != "_boot_dry_run":  # celui-ci vit sur l'instance : c'est la valeur lue à l'amorçage
        object.__setattr__(s2, name, lambda *a, **k: True)
        assert enter(s2) is False


def test_les_ecritures_du_moteur_sur_la_strategie_restent_possibles(strategy_cls: Any) -> None:
    sub: Any = type("S", (strategy_cls,), {"stoploss": -0.1})
    s = sub({"dry_run": True})
    s.stoploss, s.dp, s.wallets = -0.05, object(), None  # StrategyResolver, FreqtradeBot
    sub.timeframe = "5m"
    assert enter(s) is True


def test_attributs_exiges_par_freqtrade_restent_redefinissables(strategy_cls: Any) -> None:
    sub = type(
        "S",
        (strategy_cls,),
        {"timeframe": "5m", "stoploss": -0.1, "minimal_roi": {"0": 1},
         "populate_indicators": lambda self, df, md: df},
    )  # fmt: skip
    assert sub({"dry_run": True}).timeframe == "5m"


def test_noms_proteges_statique_et_execution_concordent(strategy_cls: Any) -> None:
    import sys

    from centrade_freqtrade.checks import PROTECTED_NAMES

    runtime = sys.modules[strategy_cls.__module__].PROTECTED
    assert runtime == PROTECTED_NAMES
