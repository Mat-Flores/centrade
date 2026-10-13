import ast
import builtins
import textwrap
from decimal import Decimal

import pytest
from centrade_freqtrade.checks import (
    ALLOWED_BUILTINS,
    ALLOWED_IMPORTS,
    PLATFORM_HOOKS,
    PROTECTED_NAMES,
    check_strategy_source,
    validate,
)
from hypothesis import given, settings
from hypothesis import strategies as st

from .local_runtime import STRATEGY
from .support import SMA_DIR, sma_manifest

HEAD = "from control_plane import ControlPlaneStrategy\n"
BODY = HEAD + "class S(ControlPlaneStrategy):\n"


def check(src: str) -> list[str]:
    return check_strategy_source(src, "S")


def method(stmt: str) -> str:
    return BODY + "    def f(self, x):\n" + textwrap.indent(stmt, " " * 8) + "\n"


def test_real_strategies_are_accepted() -> None:
    assert check_strategy_source((SMA_DIR / "SmaCross.py").read_text(), "SmaCross") == []
    assert check_strategy_source(STRATEGY, "EnterEveryCandle") == []  # celle de l'essai réel


ORDINARY = (
    "import logging\nimport math\nfrom datetime import datetime, timedelta\n"
    "from functools import reduce\nfrom typing import Optional\n"
    "import numpy as np\nimport pandas as pd\nimport talib.abstract as ta\n"
    "from pandas import DataFrame\n"
    "from freqtrade.strategy import IntParameter, informative, merge_informative_pair\n"
    + HEAD
    + "logger = logging.getLogger(__name__)\n"
    "class S(ControlPlaneStrategy):\n"
    "    timeframe = '5m'\n    stoploss = -0.1\n    minimal_roi = {'0': 0.05}\n"
    "    period = IntParameter(5, 30, default=14, space='buy')\n"
    "    @informative('1h')\n"
    "    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:\n"
    "        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)\n        return dataframe\n"
    "    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:\n"
    "        stake = str(self.config['stake_currency'])\n"
    "        if self.config.get('dry_run') and self.dp.runmode.value == 'dry_run':\n"
    "            logger.info('paire %s en %s', metadata['pair'], stake)\n"
    "        dataframe['ema'] = ta.EMA(dataframe, timeperiod=int(self.period.value))\n"
    "        upper, middle, lower = ta.BBANDS(dataframe['close'], timeperiod=20)\n"
    "        dataframe['width'] = np.where(middle > 0, (upper - lower) / middle, np.nan)\n"
    "        dataframe['up'] = pd.Series(dataframe['close']).rolling(3).max()\n"
    "        self.last_seen = datetime.now() - timedelta(minutes=math.floor(2.5))\n"
    "        return dataframe\n"
    "    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:\n"
    "        conds = [dataframe['rsi_1h'] < 30, dataframe['close'] > dataframe['ema']]\n"
    "        dataframe.loc[reduce(lambda a, b: a & b, conds), 'enter_long'] = 1\n"
    "        return dataframe\n"
    "    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,\n"
    "                            min_stake, max_stake, leverage, entry_tag, side, **kwargs):\n"
    "        return min(proposed_stake, max_stake)\n"
)


def test_ordinary_indicator_strategy_is_accepted() -> None:
    assert check(ORDINARY) == []


# --- héritage ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "src",
    [
        HEAD + "class S(ControlPlaneStrategy): pass",
        "import control_plane\nclass S(control_plane.ControlPlaneStrategy): pass",
        "import control_plane as cp\nclass S(cp.ControlPlaneStrategy): pass",
        "from control_plane import ControlPlaneStrategy as B\nclass S(B): pass",
        HEAD + "class M(ControlPlaneStrategy): pass\nclass S(M): pass",
        HEAD + "class M(ControlPlaneStrategy): pass\nclass S(M, object): pass",
    ],
)
def test_direct_indirect_and_aliased_inheritance_are_accepted(src: str) -> None:
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
        HEAD + "A = ControlPlaneStrategy\nclass S(A): pass",  # alias par affectation : refusé
        HEAD + "class S(ControlPlaneStrategy, metaclass=type): pass",
        HEAD + "@dec\nclass S(ControlPlaneStrategy): pass",
        "from . import control_plane\nclass S(control_plane.ControlPlaneStrategy): pass",
        "def (",
        "\x00",
        # A2 : second import qui remplace la base
        HEAD + "from freqtrade.strategy import IStrategy as ControlPlaneStrategy\n"
        "class S(ControlPlaneStrategy): pass",
        HEAD + "from pandas import DataFrame as ControlPlaneStrategy\n"
        "class S(ControlPlaneStrategy): pass",
        HEAD + "import numpy as ControlPlaneStrategy\nclass S(ControlPlaneStrategy): pass",
        HEAD + "class S(ControlPlaneStrategy): pass\n" + HEAD,  # liée deux fois
        "import control_plane as cp\nimport numpy as cp\nclass S(cp.ControlPlaneStrategy): pass",
        # A3 : la base ou la classe redéfinie ailleurs qu'au niveau du module
        HEAD
        + "if True:\n    class ControlPlaneStrategy: pass\nclass S(ControlPlaneStrategy): pass",
        HEAD + "class S(ControlPlaneStrategy): pass\nif True:\n    class S: pass",
        HEAD + "class S(ControlPlaneStrategy): pass\ndef f():\n    global S\n    S = object",
        HEAD + "class S(ControlPlaneStrategy): pass\ntry:\n    S = object\nexcept Exception: pass",
        HEAD + "class S(ControlPlaneStrategy): pass\ndel S",
        HEAD + "if True:\n    class S(ControlPlaneStrategy): pass",
        HEAD + "class M(ControlPlaneStrategy): pass\nM = object\nclass S(M): pass",
        HEAD + "class S(ControlPlaneStrategy):\n    class Interne: pass",
    ],
)
def test_missing_or_misleading_inheritance_is_rejected(src: str) -> None:
    assert check(src)


@pytest.mark.parametrize("hook", sorted(PLATFORM_HOOKS))
def test_every_overridden_hook_is_rejected(hook: str) -> None:
    for body in (f"def {hook}(self, *a, **k): return True", f"async def {hook}(self): pass",
                 f"{hook} = lambda *a, **k: True", f"{hook}: object = None"):  # fmt: skip
        assert any(hook in e for e in check(BODY + f"    {body}"))
    assert check(HEAD + f"class S(ControlPlaneStrategy): pass\nS.{hook} = print")


def test_hook_overridden_in_an_intermediate_class_is_rejected() -> None:
    src = (
        HEAD + "class M(ControlPlaneStrategy):\n    def leverage(self): return 5\nclass S(M): pass"
    )
    assert any("leverage" in e for e in check(src))


# --- A1, A3 : toute forme de liaison ou d'écriture d'un nom protégé ----------------------------
PRELUDE = HEAD + "def ctx():\n    return None\nv = [1]\n"

# Formes dont la cible est un nom nu.
NAME_FORMS = (
    "{T} = v",
    "{T}: object = v",
    "{T} += v",
    "del {T}",
    "for {T} in v:\n    pass",
    "for {T}, autre in [v]:\n    pass",
    "with ctx() as {T}:\n    pass",
    "with ctx() as ({T}, autre):\n    pass",
    "[0 for {T} in v]",
    "{{0: 0 for {T} in v}}",
    "({T}, autre) = v, v",
    "[{T}, *autre] = v",
    "*{T}, autre = v",
    "({T} := v)",
    "import numpy as {T}",
    "from pandas import DataFrame as {T}",
    "def {T}():\n    pass",
    "async def {T}():\n    pass",
    "try:\n    pass\nexcept Exception as {T}:\n    pass",
    "match v:\n    case {T}:\n        pass",
    "match v:\n    case [*{T}]:\n        pass",
    "match v:\n    case {{**{T}}}:\n        pass",
    "match v:\n    case int() as {T}:\n        pass",
    "type {T} = int",
)
# Formes dont la cible est une expression (attribut ou indice).
TARGET_FORMS = (
    "{T} = v",
    "{T}: object = v",
    "{T} += v",
    "del {T}",
    "for {T} in v:\n    pass",
    "with ctx() as {T}:\n    pass",
    "[0 for {T} in v]",
    "({T}, autre) = v, v",
    "[{T}, *autre] = v",
)
WRAPPERS = (
    "{S}",
    "if v:\n{I}",
    "if v:\n    pass\nelse:\n{I}",
    "try:\n{I}\nexcept Exception:\n    pass",
    "try:\n    pass\nfinally:\n{I}",
    "with ctx():\n{I}",
    "for autre2 in v:\n{I}",
    "while v:\n{I}",
    "match v:\n    case _:\n{II}",
    "def g():\n{I}",
    "async def g():\n{I}",
    "def g():\n    def h():\n{II}",
    "class S2(ControlPlaneStrategy):\n{I}",
    "class S2(ControlPlaneStrategy):\n    def m(self):\n{II}",
)


def program(wrapper: str, stmt: str) -> str:
    wrapped = wrapper.format(
        S=stmt, I=textwrap.indent(stmt, " " * 4), II=textwrap.indent(stmt, " " * 8)
    )
    src = PRELUDE + wrapped + "\nclass S(ControlPlaneStrategy):\n    pass\n"
    ast.parse(src)  # un programme mal formé serait refusé pour une mauvaise raison
    return src


def test_template_is_accepted_with_a_harmless_name() -> None:
    """Garde-fou de la propriété : seul le nom visé fait refuser le programme."""
    for wrapper in WRAPPERS:
        for form in NAME_FORMS:
            assert check(program(wrapper, form.format(T="inoffensif"))) == [], (wrapper, form)


@pytest.mark.parametrize("form", NAME_FORMS)
@pytest.mark.parametrize("name", ["confirm_trade_entry", "ControlPlaneStrategy", "_entry_allowed"])
def test_every_binding_form_of_a_protected_name_is_rejected(form: str, name: str) -> None:
    errors = check(program("{S}", form.format(T=name)))
    assert any(name in e for e in errors), errors


@pytest.mark.parametrize("form", TARGET_FORMS)
@pytest.mark.parametrize(
    "target",
    [
        "ControlPlaneStrategy.confirm_trade_entry",  # A1
        "S.confirm_trade_entry",
        "ctx().leverage",
        "v[0]._entry_allowed",
        "ControlPlaneStrategy.nouveau",  # écriture d'attribut hors de self
        "v[0].config",
        "v[0].config['dry_run']",
        "v[0].config['exchange']['name']",
        "v[0].config.get('exchange')['name']",
        "v[0].stoploss",  # valeur imposée par la configuration : pas de réécriture à chaud
    ],
)
def test_every_write_form_targeting_the_platform_is_rejected(form: str, target: str) -> None:
    assert check(program("{S}", form.format(T=target)))


protected = st.sampled_from(sorted(PROTECTED_NAMES | {"ControlPlaneStrategy"}))
owners = st.sampled_from(["ControlPlaneStrategy", "S", "self", "v[0]", "ctx()", "ctx().a"])


@st.composite
def offending_programs(draw: st.DrawFn) -> tuple[str, str]:
    name = draw(protected)
    if draw(st.booleans()):
        stmt = draw(st.sampled_from(NAME_FORMS)).format(T=name)
    else:
        stmt = draw(st.sampled_from(TARGET_FORMS)).format(T=f"{draw(owners)}.{name}")
    # Du code inoffensif autour ne doit rien y changer.
    before = draw(
        st.sampled_from(["", "autre3 = v\n", "import math\n", "def k():\n    return 1\n"])
    )
    return program(draw(st.sampled_from(WRAPPERS)), before + stmt), name


@settings(max_examples=400, deadline=None)
@given(offending_programs())
def test_any_binding_or_write_of_a_protected_name_is_rejected(case: tuple[str, str]) -> None:
    src, name = case
    assert any(name in e for e in check(src)), src


@pytest.mark.parametrize(
    "member",
    [
        "def _entry_allowed(self, **o): return True",
        "_entry_allowed = lambda self, **o: True",
        "can_short = True",
        "def __init__(self, config): pass",
        "def __init_subclass__(cls): pass",
        "def __getattribute__(self, n): return 1",
        "def __setattr__(self, n, v): pass",
        "def f(self):\n        self._entry_allowed = lambda **o: True",
        "def f(self):\n        self._boot_dry_run = True",
        "def f(self):\n        del self._boot_dry_run",
    ],
)
def test_internal_base_names_are_rejected(member: str) -> None:
    assert check(BODY + f"    {member}")


# --- A4 : configuration ------------------------------------------------------------------------
@pytest.mark.parametrize(
    "stmt",
    [
        "self.config['dry_run'] = True",
        "self.config = {'dry_run': True}",
        "self.config['dry_run'] |= True",
        "self.config |= {'dry_run': True}",
        "del self.config['dry_run']",
        "self.config.update(dry_run=True)",
        "self.config.setdefault('dry_run', True)",
        "self.config.pop('dry_run')",
        "self.config['exchange']['name'] = 'x'",
        "self.config.get('exchange')['name'] = 'x'",
        "self.config['exchange'].update(name='x')",
        "self.config.items()",
        # alias (A4) : la configuration ne se lie à aucun nom, ne se passe ni ne se renvoie
        "c = self.config\nc['dry_run'] = True",
        "c = self.config['exchange']",
        "c = self.config.get('exchange', {})",
        "c: dict = self.config",
        "for c in [self.config]:\n    c['dry_run'] = True",
        "(c := self.config)",
        "c, d = self.config, 1",
        "with ctx(self.config) as c:\n    pass",
        "[c.update(dry_run=True) for c in [self.config]]",
        "(lambda c: c.update(dry_run=True))(self.config)",
        "g = lambda c=self.config: c",
        "x.attr = self.config",
        "return self.config",
        "yield self.config",
        "c = self.config or {}",
        "(self.config or {})['dry_run'] = True",
        "(self.config or x).update(dry_run=True)",
        "x(self.config or {})",
        "c = self.config if x else None",
        "c = dict(self.config)",
        "c = [self.config]",
        "c = {'k': self.config}",
        "g = self.config.get",
        "self.config.get('a', self.config)",
        "x(self.config)",
        "x(k=self.config)",
        "x(*[self.config])",
        "int(*self.config)",
        "s = self\ns.config['dry_run'] = True",
        "config = x\nconfig['dry_run'] = True",
        "x.config['dry_run'] = True",
    ],
)
def test_config_modification_or_alias_is_rejected(stmt: str) -> None:
    assert check(method(stmt))


@pytest.mark.parametrize(
    "stmt",
    [
        "return self.config.get('x', 1) == 1",
        "return int(self.config.get('centrade_params', {}).get('fast', 10))",
        "y = float(self.config['stake_amount'])",
        "y = str(self.config['exchange']['name'])",
        "if self.config.get('dry_run'):\n    pass",
        "if not self.config['dry_run']:\n    pass",
        "y = 1 if self.config.get('a') else 2",
        "y = 'a' in self.config",
        "y = f\"{self.config['stake_currency']}\"",
        "y = bool(self.config.get('a')) and x",
        "y = int(self.config.get('a') or 0)",
        "if self.config.get('a') and (x or self.config['b']):\n    pass",
    ],
)
def test_reading_the_config_remains_allowed(stmt: str) -> None:
    assert check(method(stmt)) == []


# --- A5 : imports en liste blanche et attributs de module --------------------------------------
@pytest.mark.parametrize(
    "module",
    ["socket", "ssl", "asyncio", "http.client", "urllib.request", "requests", "httpx", "aiohttp",
     "subprocess", "os", "os.path", "posix", "pty", "multiprocessing", "ctypes", "importlib",
     "runpy", "sys", "builtins", "ccxt", "freqtrade", "freqtrade.exchange", "freqtrade.rpc",
     "freqtrade.persistence", "freqtrade.freqtradebot", "operator", "inspect", "gc", "pickle",
     "shutil", "pathlib", "io", "threading", "types", "numpy.ctypeslib", "pandas.io.common",
     "un_module_inconnu"],
)  # fmt: skip
def test_any_module_outside_the_allowlist_is_rejected_even_under_an_alias(module: str) -> None:
    base = HEAD + "class S(ControlPlaneStrategy): pass\n"
    parent, _, leaf = module.rpartition(".")
    lines = [f"import {module}", f"import {module} as x", f"def f():\n    import {module}",
             f"from {module} import quelquechose as z", f"from {module} import *",
             f"if v:\n    import {module} as x"]  # fmt: skip
    if parent:
        lines.append(f"from {parent} import {leaf} as y")
    for line in lines:
        assert any("import" in e for e in check(base + line)), line


modnames = st.from_regex(r"[a-z_][a-z0-9_]{0,8}(\.[a-z_][a-z0-9_]{0,8}){0,2}", fullmatch=True)


@given(modnames, st.sampled_from(["import {m}", "import {m} as x", "from {m} import y"]))
def test_every_import_is_rejected_by_default(module: str, form: str) -> None:
    src = HEAD + "class S(ControlPlaneStrategy): pass\n" + form.format(m=module)
    try:
        ast.parse(src)
    except SyntaxError:
        return  # mot-clé tiré au hasard
    allowed = module in ALLOWED_IMPORTS and ("." not in module or " as " in form)
    allowed = allowed and not module.startswith("__")  # un nom à double soulignement ne se lie pas
    if form.startswith("from"):
        allowed = False  # `y` n'est dans aucune liste
    assert bool(check(src)) is not allowed, src


@pytest.mark.parametrize(
    "line",
    [
        "import logging\nlogging.os.system('x')",  # A5
        "import logging\nx = logging.os",
        "import logging as lg\nlg.sys.exit()",
        "import numpy as np\nnp.ctypeslib.load_library('x', '.')",
        "import numpy as np\nnp.load('f', allow_pickle=True)",
        "import numpy as np\nnp.random.seed(1)",
        "import pandas as pd\npd.read_csv('http://x')",
        "import pandas as pd\npd.io.common.os.system('x')",
        "import pandas as pd\npd.eval('1')",
        "import talib.abstract as ta\nta.Function('SMA')",
        "import talib\ntalib.abstract.SMA",
        "import math\nm = math",  # un module ne se lie pas à un autre nom
        "import math\nprint(math)",
        "import math\n[math][0].os",
        "import math\ndef f(m=math): pass",
        "import typing\ntyping.sys.exit()",
        "import control_plane\ncontrol_plane.logger.info('x')",
        "import control_plane\ncontrol_plane.IStrategy",
        "from typing import sys",
        "from logging import os",
        "from numpy import ctypeslib",
        "from talib import abstract",
        "from freqtrade.strategy import Trade",
        "from freqtrade.strategy import IStrategy",
        "from control_plane import PROTECTED",
        "from control_plane import IStrategy",
        "import math as m\nimport logging as m",
    ],
)
def test_module_access_through_an_allowed_module_is_rejected(line: str) -> None:
    assert check(HEAD + f"class S(ControlPlaneStrategy): pass\n{line}")


# --- noms et attributs : liste blanche de builtins, soulignements ------------------------------
@pytest.mark.parametrize(
    "line",
    ["__import__('socket')", "exec('1')", "eval('1')", "compile('1', 'f', 'exec')",
     "setattr(S, 'x', 1)", "x = __builtins__", "S.__subclasses__()", "globals()",
     "open('/etc/passwd')", "input()", "x = __loader__", "x = __spec__", "memoryview(b'')",
     "x = nom_jamais_defini", "staticmethod(print)", "classmethod(print)", "help()", "dir()",
     # un nom de builtin ne se lie pas : sa liaison ailleurs légitimerait le vrai builtin ici
     "def f(getattr): pass\ngetattr(v, 'x')", "open = 1", "def type(): pass", "max = 3",
     "import math as eval", "for vars in []: pass", "lambda open: 0",
     "global v", "def f():\n    nonlocal v"],
)  # fmt: skip
def test_names_outside_the_allowlist_are_rejected(line: str) -> None:
    assert check(HEAD + f"v = 1\nclass S(ControlPlaneStrategy): pass\n{line}")


def test_builtins_allowlist_contains_no_dynamic_access() -> None:
    assert ALLOWED_BUILTINS <= set(dir(builtins))
    assert not ALLOWED_BUILTINS & {
        "getattr", "setattr", "delattr", "eval", "exec", "compile", "open", "__import__", "vars",
        "globals", "locals", "type", "input", "breakpoint", "memoryview", "staticmethod",
        "classmethod", "dir", "help", "exit", "quit", "id",
    }  # fmt: skip


@pytest.mark.parametrize(
    "expr",
    ["getattr(self, 'x')", "type(self)", "vars(self)", "self.__dict__", "self.__class__",
     "S.__bases__", "S.__mro__", "object.__setattr__(self, 'a', 1)", "S.__base__",
     "self.__getattribute__('a')", "super().__init__(x)", "x.__globals__", "x.__anything__",
     "self.f.__func__", "x.__name__",
     # A6 : attributs privés d'un objet qui n'est pas self
     "self.dp._exchange", "self.dp._config", "self.wallets._exchange", "x._private",
     "self.dp._exchange.create_order('BTC/USDT', 'market', 'buy', 1)", "x()._y", "x[0]._y",
     # cadres d'exécution : chemin vers les builtins
     "(i for i in []).gi_frame.f_builtins", "x.gi_frame", "x.f_globals", "x.tb_frame",
     "x.cr_frame", "x.f_back", "x.co_consts",
     # exécution de chaînes par la bibliothèque
     "'{0.dp._exchange}'.format(self)", "'{s.dp._exchange}'.format_map({'s': self})",
     "x.eval('1')", "x.query('@pd.io.common.os.system(\"x\")')",
     # la classe ne se nomme que comme base : pas d'appel de méthode avec un autre `self`
     "S.f(self.dp)", "ControlPlaneStrategy.confirm_trade_entry", "S", "f"],
)  # fmt: skip
def test_private_or_diverted_dynamic_access_is_rejected(expr: str) -> None:
    assert check(method(f"return {expr}"))


@pytest.mark.parametrize(
    "src",
    [
        BODY + "    def f(self):\n        self = self.dp\n        return self._exchange",
        BODY + "    def f(self):\n        for self in [self.dp]:\n            pass",
        BODY
        + "    def f(self):\n        g = lambda self: self._exchange\n        return g(self.dp)",
        BODY
        + "    def f(self):\n        def g(self):\n            return self._x\n        return g",
        BODY + "    def f(this, self):\n        return self._exchange",
        BODY + "    def f(self): pass\ndef g(self):\n    return self._exchange",
        BODY + "    def f(self, *self2, **self):\n        pass",
        # méthode sortie de la classe pour être appelée avec un autre `self`
        BODY + "    def h(self):\n        return self._exchange\n    fs = [h]",
        BODY + "    def h(self):\n        return self._exchange\n    g = property(h)",
        HEAD + "def keep(f):\n    return f\nclass S(ControlPlaneStrategy):\n"
        "    @keep\n    def h(self):\n        return self._exchange",
        BODY + "    @staticmethod\n    def h(self):\n        return self._exchange",
    ],
)
def test_self_only_designates_the_instance(src: str) -> None:
    assert check(src)


def test_private_self_attributes_and_usual_decorators_are_allowed() -> None:
    src = (
        "from freqtrade.strategy import informative\n"
        + BODY
        + "    def _aide(self):\n        self._compteur = 1\n        return self._compteur\n"
        "    @property\n    def double(self):\n        return self._aide() * 2\n"
        "    @informative('1h')\n    def populate_indicators_1h(self, dataframe, metadata):\n"
        "        return dataframe\n"
    )
    assert check(src) == []


@pytest.mark.parametrize(
    "stmt",
    [
        "x.columns = []",  # écriture d'attribut hors de self
        "self.dp.attr = 1",
        "del x.attr",
        "self.stoploss = -0.99",  # valeurs imposées par la configuration générée (F10)
        "self.minimal_roi = {'0': 10}",
        "self.trailing_stop = False",
        "self.order_types = {}",
        "self.position_adjustment_enable = True",
        "self.max_open_trades = 100",
    ],
)
def test_attribute_writes_are_rejected(stmt: str) -> None:
    assert check(method(stmt))


def test_protected_names_are_derived_from_the_base() -> None:
    assert {"_entry_allowed", "confirm_trade_entry", "_boot_dry_run", "__init__"} <= PROTECTED_NAMES
    assert set(PLATFORM_HOOKS) <= PROTECTED_NAMES
    assert not {"timeframe", "stoploss", "minimal_roi", "populate_indicators"} & PROTECTED_NAMES


# --- manifest ----------------------------------------------------------------------------------
def test_validate_accepts_a_valid_manifest() -> None:
    assert validate(sma_manifest(), {"fast": 5, "slow": 20, "pairs": ["x"]}).ok


@pytest.mark.parametrize(
    "params",
    [{"fast": 1}, {"fast": "5"}, {"fast": True}, {"inconnu": 1}, {"fast": 5.5}],
)
def test_validate_rejects_non_conforming_parameters(params: dict[str, object]) -> None:
    assert not validate(sma_manifest(), params).ok


def test_validate_checks_exits_and_mode() -> None:
    assert not validate(sma_manifest(stoploss=Decimal(0)), {}).ok
    assert not validate(sma_manifest(stoploss=Decimal(-1)), {}).ok
    assert not validate(sma_manifest(trailing={"enabled": True}), {}).ok
    assert validate(sma_manifest(trailing={"enabled": True, "positive": "0.01"}), {}).ok
    assert not validate(sma_manifest(take_profit={"x": Decimal("0.1")}), {}).ok
    m = sma_manifest().model_copy(update={"trading_mode": "futures"})
    assert not validate(m, {}).ok
    m = sma_manifest().model_copy(update={"engine": "autre"})
    assert not validate(m, {}).ok
