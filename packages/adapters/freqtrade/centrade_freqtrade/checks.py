"""Contrôles statiques d'une version de stratégie (SPEC §7, F10, annexe C) : manifest, paramètres,
et analyse AST du code source. Ils ne remplacent pas la configuration possédée ni le test de
conformité : c'est une défense en profondeur, pas une isolation."""

from __future__ import annotations

import ast
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
    n'est pas installé côté plateforme) : méthodes, attributs de classe, `self.x = …`."""
    tree = ast.parse(Path(__file__).with_name("control_plane.py").read_text(encoding="utf-8"))
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ControlPlaneStrategy"
    )
    names: set[str] = set()
    for node in ast.walk(cls):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node in cls.body:
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for t in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(t, ast.Name) and node in cls.body:
                    names.add(t.id)
                elif isinstance(t, ast.Attribute):
                    names.add(t.attr)
    return frozenset(names)


ENGINE = "freqtrade"
BASE_MODULE = "control_plane"
BASE_CLASS = "ControlPlaneStrategy"

# Modules capables d'ouvrir une connexion réseau ou de lancer un processus (préfixes de noms).
FORBIDDEN_MODULES = frozenset(
    {
        "socket", "ssl", "select", "selectors", "asyncio", "http", "urllib", "urllib3",
        "requests", "httpx", "aiohttp", "websocket", "websockets", "ftplib", "smtplib",
        "imaplib", "poplib", "telnetlib", "xmlrpc", "socketserver", "ccxt", "paramiko",
        "subprocess", "os", "posix", "pty", "multiprocessing", "concurrent", "ctypes",
        "cffi", "importlib", "runpy", "code", "codeop", "pexpect", "sys", "builtins",
        "freqtrade.exchange", "freqtrade.rpc", "freqtrade.persistence",
    }
)  # fmt: skip
FORBIDDEN_NAMES = frozenset(
    {"__import__", "eval", "exec", "compile", "setattr", "delattr", "getattr", "type", "vars",
     "globals", "locals", "breakpoint", "__builtins__"}
)  # fmt: skip
FORBIDDEN_ATTRS = frozenset(
    {"__subclasses__", "__globals__", "__builtins__", "__import__", "__dict__", "__class__",
     "__bases__", "__base__", "__mro__", "__setattr__", "__delattr__", "__getattribute__"}
)  # fmt: skip
# Noms qu'une stratégie ne peut ni définir ni affecter : tout ce que la base définit (dérivé de
# son source) plus les hooks de la plateforme.
PROTECTED_NAMES = _base_names() | PLATFORM_HOOKS
_CONFIG_MUTATORS = frozenset({"update", "pop", "popitem", "setdefault", "clear"})


def _forbidden(module: str) -> bool:
    return any(module == m or module.startswith(m + ".") for m in FORBIDDEN_MODULES)


def check_strategy_source(source: str, class_name: str) -> list[str]:
    """Erreurs (liste vide = accepté) pour le code de la classe `class_name`."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"syntaxe invalide : {e.msg} (ligne {e.lineno})"]
    errors: list[str] = []

    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            errors += [f"ligne {line} : import interdit : {a.name}" for a in node.names
                       if _forbidden(a.name)]  # fmt: skip
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                errors.append(f"ligne {line} : import relatif interdit")
            names = [mod] + [f"{mod}.{a.name}" for a in node.names]
            errors += [f"ligne {line} : import interdit : {n}" for n in names if _forbidden(n)]
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            errors.append(f"ligne {line} : usage interdit : {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
            errors.append(f"ligne {line} : usage interdit : {node.attr}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in PROTECTED_NAMES:
                errors.append(
                    f"ligne {line} : redéfinition d'un nom de la plateforme : {node.name}"
                )
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.Delete):
                targets = node.targets
            else:
                targets = [node.target]
            for t in targets:
                for sub in ast.walk(t):
                    name = sub.id if isinstance(sub, ast.Name) else getattr(sub, "attr", "")
                    if name in PROTECTED_NAMES:
                        errors.append(
                            f"ligne {line} : redéfinition d'un nom de la plateforme : {name}"
                        )
                    elif name == "config":  # le mode d'une instance n'est pas celui de la stratégie
                        errors.append(f"ligne {line} : modification de la configuration interdite")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _CONFIG_MUTATORS
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "config"
        ):
            errors.append(f"ligne {line} : modification de la configuration interdite")

    errors += _check_inheritance(tree, class_name)
    return errors


def _check_inheritance(tree: ast.Module, class_name: str) -> list[str]:
    """Passe séquentielle sur le niveau module : suit les noms liés à la base de la plateforme
    (import sous alias, affectation d'alias, classes locales intermédiaires)."""
    base_names: set[str] = set()  # noms liés à ControlPlaneStrategy
    module_aliases: set[str] = set()  # noms liés au module control_plane
    descendants: set[str] = set()  # classes locales héritant de la base
    errors: list[str] = []

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
        elif isinstance(stmt, ast.Assign):
            ok = is_base(stmt.value)
            for t in stmt.targets:
                if isinstance(t, ast.Name):
                    base_names.discard(t.id)
                    descendants.discard(t.id)
                    if ok:
                        base_names.add(t.id)
        elif isinstance(stmt, ast.ClassDef):
            base_names.discard(stmt.name)
            descendants.discard(stmt.name)
            if stmt.keywords or stmt.decorator_list:
                errors.append(
                    f"ligne {stmt.lineno} : classe {stmt.name} : métaclasse ou décorateur"
                )
            if stmt.bases and is_base(stmt.bases[0]):
                descendants.add(stmt.name)
    if class_name not in descendants:
        errors.append(
            f"la classe {class_name} n'hérite pas de {BASE_CLASS} (importé de {BASE_MODULE})"
        )
    return errors


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
