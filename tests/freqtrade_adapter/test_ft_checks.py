import ast
from decimal import Decimal

import pytest
from centrade_freqtrade.checks import (
    FORBIDDEN_MODULES,
    PLATFORM_HOOKS,
    check_strategy_source,
    validate,
)

from .support import SMA_DIR, sma_manifest

HEAD = "from control_plane import ControlPlaneStrategy\n"


def check(src: str) -> list[str]:
    return check_strategy_source(src, "S")


def test_strategie_d_exemple_acceptee() -> None:
    assert check_strategy_source((SMA_DIR / "SmaCross.py").read_text(), "SmaCross") == []
    assert ast.parse((SMA_DIR / "SmaCross.py").read_text())


@pytest.mark.parametrize(
    "src",
    [
        HEAD + "class S(ControlPlaneStrategy): pass",
        "import control_plane\nclass S(control_plane.ControlPlaneStrategy): pass",
        "import control_plane as cp\nclass S(cp.ControlPlaneStrategy): pass",
        "from control_plane import ControlPlaneStrategy as B\nclass S(B): pass",
        HEAD + "class M(ControlPlaneStrategy): pass\nclass S(M): pass",
        HEAD + "A = ControlPlaneStrategy\nclass S(A): pass",
        HEAD + "class M(ControlPlaneStrategy): pass\nclass S(M, object): pass",
    ],
)
def test_heritage_direct_indirect_et_alias_acceptes(src: str) -> None:
    assert check(src) == []


@pytest.mark.parametrize(
    "src",
    [
        "from freqtrade.strategy import IStrategy\nclass S(IStrategy): pass",
        "class S: pass",
        "class Autre(object): pass",
        HEAD + "class S(object): pass",
        HEAD + "class S(Inconnu): pass",
        "from autre import ControlPlaneStrategy\nclass S(ControlPlaneStrategy): pass",
        HEAD + "class S(object, ControlPlaneStrategy): pass",
        HEAD + "class ControlPlaneStrategy(object): pass\nclass S(ControlPlaneStrategy): pass",
        HEAD + "ControlPlaneStrategy = object\nclass S(ControlPlaneStrategy): pass",
        HEAD + "class S(ControlPlaneStrategy, metaclass=type): pass",
        HEAD + "@dec\nclass S(ControlPlaneStrategy): pass",
        "from . import control_plane\nclass S(control_plane.ControlPlaneStrategy): pass",
        "def (",
    ],
)
def test_heritage_absent_ou_trompeur_refuse(src: str) -> None:
    assert check(src)


@pytest.mark.parametrize("hook", sorted(PLATFORM_HOOKS))
def test_chaque_hook_redefini_est_refuse(hook: str) -> None:
    for body in (f"def {hook}(self, *a, **k): return True", f"async def {hook}(self): pass",
                 f"{hook} = lambda *a, **k: True", f"{hook}: object = None"):  # fmt: skip
        assert any(hook in e for e in check(HEAD + f"class S(ControlPlaneStrategy):\n    {body}"))
    assert check(HEAD + f"class S(ControlPlaneStrategy): pass\nS.{hook} = print")


def test_hook_redefini_dans_une_classe_intermediaire_est_refuse() -> None:
    src = (
        HEAD + "class M(ControlPlaneStrategy):\n    def leverage(self): return 5\nclass S(M): pass"
    )
    assert any("leverage" in e for e in check(src))


@pytest.mark.parametrize("module", sorted(FORBIDDEN_MODULES))
def test_chaque_import_interdit_est_refuse_meme_sous_alias(module: str) -> None:
    base = HEAD + "class S(ControlPlaneStrategy): pass\n"
    leaf = module.rsplit(".", 1)[-1]
    parent = module.rsplit(".", 1)[0] if "." in module else None
    for line in (f"import {module}", f"import {module} as x"):
        assert any("interdit" in e for e in check(base + line)), line
    if parent:
        assert check(base + f"from {parent} import {leaf} as y")
    assert check(base + f"def f():\n    import {module}")
    assert check(base + f"from {module} import quelquechose as z")


@pytest.mark.parametrize(
    "line",
    ["__import__('socket')", "exec('1')", "eval('1')", "compile('1', 'f', 'exec')",
     "setattr(S, 'x', 1)", "x = __builtins__", "S.__subclasses__()", "globals()"],
)  # fmt: skip
def test_appels_dynamiques_refuses(line: str) -> None:
    assert check(HEAD + f"class S(ControlPlaneStrategy): pass\n{line}")


def test_imports_ordinaires_acceptes() -> None:
    src = HEAD + "import numpy as np\nfrom datetime import datetime\nimport talib.abstract as ta\n"
    assert check(src + "class S(ControlPlaneStrategy): pass") == []


def test_validate_manifest_valide() -> None:
    assert validate(sma_manifest(), {"fast": 5, "slow": 20, "pairs": ["x"]}).ok


@pytest.mark.parametrize(
    "params",
    [{"fast": 1}, {"fast": "5"}, {"fast": True}, {"inconnu": 1}, {"fast": 5.5}],
)
def test_validate_parametres_non_conformes(params: dict[str, object]) -> None:
    assert not validate(sma_manifest(), params).ok


def test_validate_exits_et_mode() -> None:
    assert not validate(sma_manifest(stoploss=Decimal(0)), {}).ok
    assert not validate(sma_manifest(stoploss=Decimal(-1)), {}).ok
    assert not validate(sma_manifest(trailing={"enabled": True}), {}).ok
    assert validate(sma_manifest(trailing={"enabled": True, "positive": "0.01"}), {}).ok
    assert not validate(sma_manifest(take_profit={"x": Decimal("0.1")}), {}).ok
    m = sma_manifest().model_copy(update={"trading_mode": "futures"})
    assert not validate(m, {}).ok
    m = sma_manifest().model_copy(update={"engine": "autre"})
    assert not validate(m, {}).ok


BODY = HEAD + "class S(ControlPlaneStrategy):\n"


@pytest.mark.parametrize(
    "member",
    [
        "def _entry_allowed(self, **o): return True",
        "_entry_allowed = lambda self, **o: True",
        "can_short = True",
        "def __init__(self, config): pass",
        "def __init_subclass__(cls): pass",
        "def f(self):\n        self._entry_allowed = lambda **o: True",
        "def f(self):\n        self._boot_dry_run = True",
        "def f(self):\n        del self._boot_dry_run",
    ],
)
def test_noms_internes_de_la_base_refuses(member: str) -> None:
    assert check(BODY + f"    {member}")


@pytest.mark.parametrize(
    "stmt",
    [
        "self.config['dry_run'] = True",
        "self.config = {'dry_run': True}",
        "self.config['dry_run'] |= True",
        "del self.config['dry_run']",
        "self.config.update(dry_run=True)",
        "self.config.setdefault('dry_run', True)",
        "self.config.pop('dry_run')",
    ],
)
def test_modification_de_la_config_refusee(stmt: str) -> None:
    assert check(BODY + f"    def f(self):\n        {stmt}")


@pytest.mark.parametrize(
    "expr",
    ["getattr(self, 'x')", "type(self)", "vars(self)", "self.__dict__", "self.__class__",
     "S.__bases__", "S.__mro__", "object.__setattr__(self, 'a', 1)", "S.__base__",
     "self.__getattribute__('a')"],
)  # fmt: skip
def test_acces_dynamique_aux_attributs_refuse(expr: str) -> None:
    assert check(BODY + f"    def f(self):\n        return {expr}")


def test_lecture_de_la_config_reste_permise() -> None:
    assert check(BODY + "    def f(self):\n        return self.config.get('x', 1)") == []


def test_noms_proteges_derives_de_la_base() -> None:
    from centrade_freqtrade.checks import PROTECTED_NAMES

    assert {"_entry_allowed", "confirm_trade_entry", "_boot_dry_run", "__init__"} <= PROTECTED_NAMES
    assert set(PLATFORM_HOOKS) <= PROTECTED_NAMES
    assert not {"timeframe", "stoploss", "minimal_roi", "populate_indicators"} & PROTECTED_NAMES
