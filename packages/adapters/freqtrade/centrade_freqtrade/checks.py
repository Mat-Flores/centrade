"""Contrôles statiques d'une version de stratégie (SPEC §7, F10, annexe C) : manifest, paramètres,
et analyse AST du code source.

Le contrôle du code refuse par défaut : imports, noms globaux et décorateurs passent par des listes
blanches ; toute liaison ou écriture qui vise la plateforme est refusée, quelle qu'en soit la forme
syntaxique. Il ne remplace ni la configuration possédée ni l'isolation du conteneur : du code
Python dans le processus du moteur ne se confine pas par analyse statique (limites : ADR 0008).
"""

from __future__ import annotations

import ast
import builtins
import math
import re
from collections import Counter
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

from centrade_core.engine.types import Manifest, ValidationResult

PLATFORM_HOOKS = frozenset(
    {
        "confirm_trade_entry",
        "confirm_trade_exit",
        "adjust_trade_position",
        "adjust_entry_price",
        "adjust_order_price",
        "adjust_exit_price",  # le moteur le refuse avec adjust_order_price (ADR 0008)
        "leverage",
    }
)


def _base_names() -> frozenset[str]:
    """Noms définis par ControlPlaneStrategy, lus dans son source (pas d'import : Freqtrade
    n'est pas installé côté plateforme) : méthodes et attributs de classe."""
    tree = ast.parse(Path(__file__).with_name("control_plane.py").read_text(encoding="utf-8"))
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ControlPlaneStrategy"
    )
    names: set[str] = set()
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for t in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return frozenset(names)


ENGINE = "freqtrade"
BASE_MODULE = "control_plane"
BASE_CLASS = "ControlPlaneStrategy"

# Noms qu'une stratégie ne peut ni lier ni écrire : tout ce que la base définit (dérivé de son
# source) plus les hooks de la plateforme.
PROTECTED_NAMES = _base_names() | PLATFORM_HOOKS

_TALIB = re.compile(r"[A-Z][A-Z0-9_]*")  # fonctions d'indicateurs : jamais un sous-module
# Liste blanche d'imports : module -> noms permis, par `from … import` comme en attribut du module
# importé. Aucun de ces noms n'est un module (relevé sur l'image du tag épinglé, ADR 0008).
ALLOWED_IMPORTS: dict[str, frozenset[str] | re.Pattern[str]] = {
    BASE_MODULE: frozenset({BASE_CLASS}),
    "__future__": frozenset({"annotations"}),
    # `freqtrade.strategy.__all__` du tag, sans IStrategy (la base est imposée) ni Trade, Order,
    # PairLocks (accès à la base de données du moteur).
    "freqtrade.strategy": frozenset(
        {
            "informative",
            "BooleanParameter",
            "CategoricalParameter",
            "DecimalParameter",
            "IntParameter",
            "RealParameter",
            "timeframe_to_minutes",
            "timeframe_to_next_date",
            "timeframe_to_prev_date",
            "merge_informative_pair",
            "stoploss_from_absolute",
            "stoploss_from_open",
        }
    ),
    "pandas": frozenset(
        {
            "DataFrame",
            "Series",
            "Timestamp",
            "Timedelta",
            "NA",
            "NaT",
            "concat",
            "isna",
            "notna",
            "to_datetime",
            "to_numeric",
        }
    ),
    "numpy": frozenset(
        {
            "abs",
            "absolute",
            "all",
            "any",
            "arange",
            "argmax",
            "argmin",
            "array",
            "asarray",
            "bool_",
            "ceil",
            "clip",
            "concatenate",
            "cumprod",
            "cumsum",
            "diff",
            "e",
            "exp",
            "float64",
            "floor",
            "full",
            "inf",
            "int64",
            "isfinite",
            "isin",
            "isnan",
            "linspace",
            "log",
            "log10",
            "log2",
            "logical_and",
            "logical_not",
            "logical_or",
            "max",
            "maximum",
            "mean",
            "median",
            "min",
            "minimum",
            "nan",
            "nanmax",
            "nanmean",
            "nanmin",
            "nanstd",
            "nansum",
            "ndarray",
            "ones",
            "percentile",
            "pi",
            "power",
            "quantile",
            "roll",
            "round",
            "select",
            "sign",
            "sqrt",
            "std",
            "sum",
            "var",
            "where",
            "zeros",
        }
    ),
    "talib": _TALIB,
    "talib.abstract": _TALIB,
    "math": frozenset(n for n in dir(math) if not n.startswith("_")),  # ni sous-module ni E/S
    "datetime": frozenset({"datetime", "timedelta", "timezone", "date", "time", "UTC"}),
    "decimal": frozenset({"Decimal"}),
    "typing": frozenset(
        {
            "Any",
            "Callable",
            "ClassVar",
            "Dict",
            "Final",
            "Iterable",
            "List",
            "Literal",
            "Mapping",
            "Optional",
            "Sequence",
            "Tuple",
            "Union",
        }
    ),
    "functools": frozenset({"reduce", "lru_cache", "cache"}),
    "logging": frozenset({"getLogger", "Logger", "DEBUG", "INFO", "WARNING", "ERROR"}),
}
# Noms globaux utilisables sans les définir. Aucun accès par chaîne (getattr, vars…), aucune E/S,
# aucune fabrique de classe (type), aucun décorateur qui délie une méthode de son instance.
ALLOWED_BUILTINS = frozenset(
    {"abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float", "frozenset",
     "int", "isinstance", "len", "list", "map", "max", "min", "object", "pow", "print", "property",
     "range", "repr", "reversed", "round", "set", "slice", "sorted", "str", "sum", "super",
     "tuple", "zip", "ArithmeticError", "Exception", "IndexError", "KeyError",
     "NotImplementedError", "RuntimeError", "TypeError", "ValueError", "ZeroDivisionError"}
)  # fmt: skip
_BUILTIN_NAMES = frozenset(dir(builtins))
_DECORATORS = frozenset(
    {("freqtrade.strategy", "informative"), ("functools", "lru_cache"), ("functools", "cache")}
)
# Attributs que le moteur relit sur la stratégie à chaque tour et que la configuration générée
# impose au chargement (`StrategyResolver`, tag 2026.9) : les réécrire à chaud contournerait F10.
CONFIG_IMPOSED_ATTRS = frozenset(
    {"stoploss", "trailing_stop", "trailing_stop_positive", "trailing_stop_positive_offset",
     "trailing_only_offset_is_reached", "minimal_roi", "order_types", "stake_currency",
     "stake_amount", "max_open_trades", "position_adjustment_enable", "unfilledtimeout"}
)  # fmt: skip
# Chemins connus, sur des objets quelconques, vers l'exécution de chaînes (pandas), la lecture
# d'attributs par chaîne (str.format) ou les builtins (cadres d'exécution). Liste noire, donc
# incomplète par nature : un complément, pas la garantie.
_GADGET_ATTRS = frozenset({"eval", "query", "format", "format_map"})
_FRAME_ATTR = re.compile(r"(gi|cr|ag|tb|f|co)_[a-z_]+")
# Seules fonctions qui reçoivent une valeur de configuration : elles en rendent une copie scalaire.
_CONFIG_CONVERTERS = frozenset({"int", "float", "str", "bool", "len"})

_CONFIG_RULE = (
    "configuration : lecture seule, par .get() ou [...], convertie par int, float, str, bool "
    "ou len ; ni alias, ni passage à une fonction, ni modification"
)

_Def = (ast.FunctionDef, ast.AsyncFunctionDef)


def _allowed(module: str, name: str) -> bool:
    spec = ALLOWED_IMPORTS.get(module)
    if spec is None:
        return False
    return name in spec if isinstance(spec, frozenset) else spec.fullmatch(name) is not None


def _bound_names(node: ast.AST) -> Iterator[str]:
    """Noms que `node` lie, toutes formes de la grammaire confondues (affectation, boucle, `with`,
    `except`, compréhension, `:=`, `del`, import, définition, paramètre, motif, alias de type)."""
    if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
        yield node.id
    elif isinstance(node, (*_Def, ast.ClassDef, ast.TypeVar, ast.ParamSpec, ast.TypeVarTuple)):
        yield node.name
    elif isinstance(node, ast.arg):
        yield node.arg
    elif isinstance(node, ast.alias):
        yield node.asname or node.name.split(".")[0]
    elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name:
        yield node.name
    elif isinstance(node, ast.MatchMapping) and node.rest:
        yield node.rest
    elif isinstance(node, (ast.Global, ast.Nonlocal)):
        yield from node.names


def _is_self(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "self"


def _config_path(node: ast.AST) -> bool:
    """`node` désigne la configuration ou l'un de ses sous-objets : `X.config`, puis `[...]`,
    `.get` et `.get(...)` à volonté."""
    while True:
        if isinstance(node, ast.Attribute) and node.attr == "config":
            return True
        if isinstance(node, ast.Name):
            return node.id == "config"
        if isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Attribute) and node.attr == "get":
            node = node.value
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
        ):
            node = node.func.value
        else:
            return False


def _config_use_ok(node: ast.AST, up: dict[ast.AST, ast.AST]) -> bool:
    """La configuration se lit et se convertit ; elle ne se lie à aucun nom, ne se passe à
    aucune fonction, ne se renvoie pas et ne se modifie pas (aucun alias à suivre)."""
    parent = up.get(node)
    if isinstance(node, ast.Attribute) and node.attr == "get":
        return isinstance(parent, ast.Call) and parent.func is node
    if not isinstance(getattr(node, "ctx", None), (ast.Load, type(None))):
        return False
    if isinstance(parent, ast.Subscript):
        return parent.value is node
    if isinstance(parent, ast.Attribute):
        return parent.attr == "get"
    while isinstance(parent, ast.BoolOp):  # `a or b` rend l'un de ses opérandes : pas un chemin
        node, parent = parent, up.get(parent)
    if isinstance(parent, ast.Call):
        return (
            node in parent.args
            and isinstance(parent.func, ast.Name)
            and parent.func.id in _CONFIG_CONVERTERS
        )
    if isinstance(parent, (ast.If, ast.While, ast.IfExp, ast.Assert)):
        return parent.test is node
    if isinstance(parent, ast.UnaryOp):
        return isinstance(parent.op, ast.Not)
    return isinstance(parent, (ast.Compare, ast.FormattedValue))


def check_strategy_source(source: str, class_name: str) -> list[str]:
    """Erreurs (liste vide = accepté) pour le code de la classe `class_name`."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"syntaxe invalide : {e.msg} (ligne {e.lineno})"]
    except (ValueError, RecursionError, MemoryError):
        return ["source illisible"]
    nodes = list(ast.walk(tree))  # parcours itératif : tout l'arbre, à toute profondeur
    up: dict[ast.AST, ast.AST] = {c: n for n in nodes for c in ast.iter_child_nodes(n)}
    errors: list[str] = []

    def err(node: ast.AST, msg: str) -> None:
        errors.append(f"ligne {getattr(node, 'lineno', 0)} : {msg}")

    def first_param_of_method(node: ast.AST) -> bool:
        fn = up.get(up.get(node, node))
        return (
            isinstance(fn, _Def)
            and isinstance(up.get(fn), ast.ClassDef)
            and [*fn.args.posonlyargs, *fn.args.args][:1] == [node]
        )

    def base_import(node: ast.AST) -> bool:  # `from control_plane import ControlPlaneStrategy`
        imp = up.get(node)
        return (
            isinstance(node, ast.alias)
            and isinstance(imp, ast.ImportFrom)
            and imp.module == BASE_MODULE
            and not imp.level
            and node.name == BASE_CLASS
            and up.get(imp) is tree
        )

    # --- 1. liaisons : tout nom lié, où que ce soit et par quelque forme que ce soit ----------
    bound: Counter[str] = Counter()
    modules: dict[str, str] = {}  # nom lié par `import` -> module
    imported: dict[str, tuple[str, str]] = {}  # nom lié par `from … import` -> (module, nom)
    for node in nodes:
        for name in _bound_names(node):
            bound[name] += 1
            if name in PROTECTED_NAMES and not isinstance(node, ast.arg):
                # Un paramètre est une variable locale ; le moteur en nomme un `leverage`.
                err(node, f"redéfinition d'un nom de la plateforme : {name}")
            elif name == BASE_CLASS and not base_import(node):
                err(node, f"redéfinition d'un nom de la plateforme : {name}")
            elif name.startswith("__") or name in _BUILTIN_NAMES or name == "config":
                # Lier un builtin quelque part rendrait licite le vrai builtin ailleurs.
                err(node, f"nom réservé : {name}")
            elif name == "self" and not (isinstance(node, ast.arg) and first_param_of_method(node)):
                err(node, "self ne désigne que l'instance : premier paramètre d'une méthode")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            err(node, "global et nonlocal interdits")
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in ALLOWED_IMPORTS:
                    err(node, f"import interdit : {a.name}")
                elif "." in a.name and not a.asname:
                    err(node, f"import interdit sans alias : {a.name}")
                else:
                    modules[a.asname or a.name] = a.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                err(node, "import relatif interdit")
            for a in node.names:
                if node.level or not _allowed(node.module or "", a.name):
                    err(node, f"import interdit : {node.module}.{a.name}")
                else:
                    imported[a.asname or a.name] = (node.module or "", a.name)
    classes = {n.name for n in nodes if isinstance(n, ast.ClassDef)}
    methods = {n.name for n in nodes if isinstance(n, _Def) and isinstance(up[n], ast.ClassDef)}
    base_aliases = {n for n, origin in imported.items() if origin == (BASE_MODULE, BASE_CLASS)}
    for name in sorted({*modules, *imported, *classes}):
        if bound[name] != 1:  # ni second import, ni redéfinition sous if/try/with/match/def
            errors.append(f"nom lié plusieurs fois : {name}")

    # --- 2. usages ---------------------------------------------------------------------------
    for node in nodes:
        parent = up.get(node)
        if isinstance(node, ast.ClassDef):
            if parent is not tree:
                err(node, f"classe {node.name} : définie ailleurs qu'au niveau du module")
            if node.keywords or node.decorator_list:
                err(node, f"classe {node.name} : métaclasse ou décorateur")
        elif isinstance(node, _Def):
            for d in node.decorator_list:
                root = d.func if isinstance(d, ast.Call) else d
                if not isinstance(root, ast.Name) or not (
                    root.id == "property" or imported.get(root.id) in _DECORATORS
                ):
                    err(d, "décorateur interdit")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            as_object = isinstance(parent, ast.Attribute)
            if node.id in modules:
                if not (
                    isinstance(parent, ast.Attribute) and _allowed(modules[node.id], parent.attr)
                ):
                    err(node, f"usage interdit du module {modules[node.id]}")
            elif node.id in classes or node.id in base_aliases:
                if not (isinstance(parent, ast.ClassDef) and node in parent.bases):
                    err(node, f"usage interdit : {node.id} ne se nomme que comme classe de base")
            elif node.id in methods:
                err(node, f"usage interdit : la méthode {node.id} hors de self")
            elif not (node.id == "__name__" or node.id in ALLOWED_BUILTINS or node.id in bound) or (
                node.id == "__name__" and as_object
            ):
                err(node, f"usage interdit : {node.id}")
        elif isinstance(node, ast.Attribute):
            attr, on_self = node.attr, _is_self(node.value)
            if attr.startswith("__") or attr in _GADGET_ATTRS or _FRAME_ATTR.fullmatch(attr):
                err(node, f"usage interdit : {attr}")
            elif attr.startswith("_") and not on_self:
                err(node, f"attribut privé d'un objet autre que self : {attr}")
            if attr == BASE_CLASS and not (
                isinstance(parent, ast.ClassDef) and node in parent.bases
            ):
                err(node, f"redéfinition d'un nom de la plateforme : {attr}")
            elif not isinstance(node.ctx, ast.Load):
                if attr in PROTECTED_NAMES:
                    err(node, f"redéfinition d'un nom de la plateforme : {attr}")
                elif not on_self:
                    err(node, f"écriture d'attribut hors de self : {attr}")
                elif attr in CONFIG_IMPOSED_ATTRS:
                    err(node, f"valeur imposée par la configuration : {attr}")
        if _config_path(node) and not _config_use_ok(node, up):
            err(node, _CONFIG_RULE)

    errors += _check_inheritance(tree, class_name, bound)
    return errors


def _check_inheritance(tree: ast.Module, class_name: str, bound: Counter[str]) -> list[str]:
    """Passe séquentielle sur le niveau module : la base importée (sous son nom ou sous alias) et
    les classes locales intermédiaires. Chaque nom suivi n'est lié qu'une fois dans le fichier."""
    base_names: set[str] = set()  # noms liés à ControlPlaneStrategy
    module_aliases: set[str] = set()  # noms liés au module control_plane
    descendants: set[str] = set()  # classes locales héritant de la base

    def is_base(expr: ast.expr) -> bool:
        if isinstance(expr, ast.Name):
            return expr.id in base_names or expr.id in descendants
        return (
            isinstance(expr, ast.Attribute)
            and isinstance(expr.value, ast.Name)
            and expr.value.id in module_aliases
            and expr.attr == BASE_CLASS
        )

    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            module_aliases |= {a.asname or a.name for a in stmt.names if a.name == BASE_MODULE}
        elif isinstance(stmt, ast.ImportFrom) and stmt.module == BASE_MODULE and not stmt.level:
            base_names |= {a.asname or a.name for a in stmt.names if a.name == BASE_CLASS}
        elif isinstance(stmt, ast.ClassDef) and stmt.bases and is_base(stmt.bases[0]):
            descendants.add(stmt.name)
    if class_name not in descendants or bound[class_name] != 1:
        return [f"la classe {class_name} n'hérite pas de {BASE_CLASS} (importé de {BASE_MODULE})"]
    return []


def _check_params(schema: dict[str, Any], params: dict[str, Any]) -> list[str]:
    props: dict[str, Any] = schema.get("properties", {})
    errors = [f"paramètre inconnu : {k}" for k in sorted(set(params) - set(props) - {"pairs"})]
    errors += [f"paramètre requis : {k}" for k in schema.get("required", []) if k not in params]
    types: dict[str, Any] = {
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float, Decimal)) and not isinstance(v, bool),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
    }
    for k, v in params.items():
        spec = props.get(k)
        if spec is None:
            continue
        check = types.get(spec.get("type"))
        if check is None:
            errors.append(f"{k} : type de schéma non pris en charge : {spec.get('type')!r}")
        elif not check(v):
            errors.append(f"{k} : type {spec['type']} attendu")
        else:
            if "minimum" in spec and v < spec["minimum"]:
                errors.append(f"{k} : inférieur au minimum {spec['minimum']}")
            if "maximum" in spec and v > spec["maximum"]:
                errors.append(f"{k} : supérieur au maximum {spec['maximum']}")
            if "enum" in spec and v not in spec["enum"]:
                errors.append(f"{k} : hors de l'énumération")
    return errors


def validate(manifest: Manifest, params: dict[str, Any]) -> ValidationResult:
    """Manifest Freqtrade (spot seul, stop-loss obligatoire) et paramètres du `params_schema`.
    La clé `pairs` est fournie par la plateforme (config.render_config) : elle est ignorée ici."""
    errors: list[str] = []
    if manifest.engine != ENGINE:
        errors.append("engine doit valoir freqtrade")
    if manifest.trading_mode != "spot":
        errors.append("trading_mode : seul spot est admis en V1")
    stem = manifest.entrypoint.rsplit("/", 1)[-1].removesuffix(".py")
    if not manifest.entrypoint.endswith(".py") or not stem.isidentifier():
        errors.append("entrypoint : fichier .py dont le nom est le nom de la classe")
    ex = manifest.exits
    if not Decimal(-1) < ex.stoploss < Decimal(0):
        errors.append("exits.stoploss : obligatoire, strictement entre -1 et 0")
    if ex.trailing.get("enabled"):
        try:
            if Decimal(str(ex.trailing["positive"])) <= 0:
                errors.append("exits.trailing.positive : doit être positif")
        except (KeyError, ArithmeticError):
            errors.append("exits.trailing.positive : requis quand le suiveur est actif")
    for minutes, gain in ex.take_profit.items():
        if not minutes.isdigit() or gain <= 0:
            errors.append(f"exits.take_profit[{minutes}] : minutes entières et gain positif")
    if manifest.sizing.stake_amount <= 0:
        errors.append("sizing.stake_amount : doit être positif")
    errors += _check_params(manifest.params_schema, params)
    return ValidationResult(ok=not errors, errors=tuple(errors))


def check_source(manifest: Manifest, source: str) -> ValidationResult:
    """Contrôle AST du code ; la classe porte le nom du fichier d'entrée (voir `validate`)."""
    stem = manifest.entrypoint.rsplit("/", 1)[-1].removesuffix(".py")
    errors = tuple(check_strategy_source(source, stem))
    return ValidationResult(ok=not errors, errors=errors)
