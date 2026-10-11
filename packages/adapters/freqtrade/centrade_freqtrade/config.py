"""Configuration Freqtrade possédée par la plateforme (SPEC §7, annexe C, ADR 0008).

Tout est pur : même entrée, même sortie. Les identifiants de l'API native viennent d'un second
fichier de configuration (fusion profonde, le dernier l'emporte), écrit par le worker.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from centrade_core.engine.types import EngineConfig, InstanceSpec, Mode

# Clés possédées (annexe C), en notation pointée. Valeurs de EngineConfig : chaînes canoniques.
OWNED_KEYS: tuple[str, ...] = (
    "dry_run",
    "db_url",
    "bot_name",
    "strategy",
    "trading_mode",
    "exchange.name",
    "initial_state",
    "force_entry_enable",
    "position_adjustment_enable",
    "stake_currency",
    "stake_amount",
    "max_open_trades",
    "available_capital",
    "tradable_balance_ratio",
    "exchange.pair_whitelist",
    "stoploss",
    "trailing_stop",
    "trailing_stop_positive",
    "trailing_stop_positive_offset",
    "trailing_only_offset_is_reached",
    "minimal_roi",
    "order_types",
    "cancel_open_orders_on_exit",
    "api_server.enabled",
    "api_server.listen_ip_address",
    "api_server.listen_port",
    "webhook.enabled",
    "webhook.allow_custom_messages",
    "telegram.enabled",
)
# Jamais écrits pour paper ni backtest (I3) ; en live ils viennent du fichier d'identifiants.
VENUE_CREDENTIAL_KEYS: tuple[str, ...] = (
    "exchange.key",
    "exchange.secret",
    "exchange.password",
    "exchange.uid",
)

# Clé possédée -> clé de GET /show_config. `exchange.pair_whitelist` n'y figure pas : l'adaptateur
# d'exécution l'ajoute sous `pair_whitelist` depuis GET /whitelist. Les clés absentes de cette
# table (db_url, initial_state, tradable_balance_ratio, cancel_open_orders_on_exit, api_server,
# webhook, telegram) ne sont pas observables par REST : voir l'ADR 0008.
_SHOW_CONFIG_SOURCE: dict[str, str] = {
    "dry_run": "dry_run",
    "bot_name": "bot_name",
    "strategy": "strategy",
    "trading_mode": "trading_mode",
    "exchange.name": "exchange",
    "force_entry_enable": "force_entry_enable",
    "position_adjustment_enable": "position_adjustment_enable",
    "stake_currency": "stake_currency",
    "stake_amount": "stake_amount",
    "max_open_trades": "max_open_trades",
    "available_capital": "available_capital",
    "exchange.pair_whitelist": "pair_whitelist",
    "stoploss": "stoploss",
    "trailing_stop": "trailing_stop",
    "trailing_stop_positive": "trailing_stop_positive",
    "trailing_stop_positive_offset": "trailing_stop_positive_offset",
    "trailing_only_offset_is_reached": "trailing_only_offset_is_reached",
    "minimal_roi": "minimal_roi",
    "order_types": "order_types",
}
OBSERVABLE_KEYS: tuple[str, ...] = tuple(k for k in OWNED_KEYS if k in _SHOW_CONFIG_SOURCE)
# Le moteur peut ajouter des valeurs par défaut à ces dictionnaires : seules nos clés comptent.
_SUBSET_KEYS = frozenset({"order_types"})

API_PORT = 8080
_USER_DATA = "/freqtrade/user_data"


@dataclass(frozen=True, slots=True)
class Drift:
    key: str
    expected: str | None
    observed: str | None


def _num(d: Decimal) -> str:
    return str(d).lower() if not d.is_finite() else format(d.normalize(), "f")


def _norm(v: Any) -> Any:
    """Forme canonique comparable : nombres décimaux normalisés (50, 50.0 et "50" s'égalent)."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, float):
        return _num(Decimal(repr(v)))
    if isinstance(v, (int, Decimal)):
        return _num(Decimal(v))
    if isinstance(v, Mapping):
        return {str(k): _norm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, str):
        if v in ("true", "false"):
            return v == "true"
        if v[:1] in "{[":
            try:
                return _norm(json.loads(v))
            except ValueError:
                return v
        try:
            return _num(Decimal(v))
        except InvalidOperation:
            return v
    return str(v)


def _canon(v: Any, key: str = "") -> str:
    n = _norm(v)
    if key == "exchange.pair_whitelist" and isinstance(n, list):
        n = sorted(n)
    if isinstance(n, bool):
        return "true" if n else "false"
    if isinstance(n, str):
        return n
    return json.dumps(n, sort_keys=True, separators=(",", ":"))


def _get(doc: Mapping[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for part in dotted.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _pairs(params: Mapping[str, Any]) -> tuple[str, list[str], str]:
    """`params["pairs"]` : symboles normalisés `crypto:venue:BASE/QUOTE`, une seule venue et une
    seule devise de cotation. Fournis par la plateforme, pas par l'auteur de la stratégie."""
    raw = params.get("pairs")
    if not isinstance(raw, list) or not raw:
        raise ValueError("params.pairs : liste non vide de symboles normalisés exigée")
    venues, pairs, quotes = set(), [], set()
    for s in raw:
        parts = str(s).split(":")
        if len(parts) != 3 or parts[0] != "crypto" or "/" not in parts[2]:
            raise ValueError(f"symbole invalide : {s!r}")
        venues.add(parts[1])
        pairs.append(parts[2])
        quotes.add(parts[2].split("/")[1].split(":")[0])
    if len(venues) != 1 or len(quotes) != 1:
        raise ValueError("une seule venue et une seule devise de cotation par instance")
    return venues.pop(), sorted(set(pairs)), quotes.pop()


def _document(spec: InstanceSpec) -> dict[str, Any]:
    """Configuration imbriquée, argent en Decimal. Source unique de render_config et du fichier."""
    m = spec.manifest
    if m.trading_mode != "spot":
        raise ValueError("seul le mode spot est admis en V1")
    venue, pairs, quote = _pairs(spec.params)
    ex = m.exits
    trailing_on = bool(ex.trailing.get("enabled", False))
    stake = m.sizing.stake_amount
    doc: dict[str, Any] = {
        # Dérivé de l'énumération du mode : une instance paper ou backtest reste en dry-run.
        "dry_run": spec.mode != "live",
        "db_url": f"sqlite:///{_USER_DATA}/trades-{spec.mode}.sqlite",
        "bot_name": f"centrade-{spec.instance_id}",
        "strategy": m.entrypoint.rsplit("/", 1)[-1].removesuffix(".py"),
        "trading_mode": "spot",
        "exchange": {"name": venue, "pair_whitelist": pairs, "pair_blacklist": []},
        "initial_state": "paused",
        "force_entry_enable": False,
        "position_adjustment_enable": False,
        "stake_currency": quote,
        "stake_amount": stake,
        "max_open_trades": m.sizing.max_open_positions,
        "available_capital": stake * m.sizing.max_open_positions,
        "tradable_balance_ratio": Decimal(1),
        "stoploss": ex.stoploss,
        "trailing_stop": trailing_on,
        "trailing_stop_positive_offset": Decimal(str(ex.trailing.get("offset", 0)))
        if trailing_on
        else Decimal(0),
        "trailing_only_offset_is_reached": bool(ex.trailing.get("only_offset_reached", False))
        if trailing_on
        else False,
        "minimal_roi": dict(sorted(ex.take_profit.items(), key=lambda kv: int(kv[0])))
        or {"0": Decimal(100)},  # 10000 % : pas d'objectif de gain déclaré
        "order_types": {
            "entry": "limit",
            "exit": "limit",
            "stoploss": "limit",
            "stoploss_on_exchange": ex.stop_on_venue,
            "stoploss_on_exchange_interval": 60,
            "emergency_exit": "market",
            "force_exit": "market",
        },
        "cancel_open_orders_on_exit": False,
        "api_server": {
            "enabled": True,
            "listen_ip_address": "0.0.0.0",  # noqa: S104  réseau des moteurs seulement (Compose)
            "listen_port": API_PORT,
            "verbosity": "error",
            "CORS_origins": [],
        },
        "webhook": {"enabled": False, "allow_custom_messages": False},
        "telegram": {"enabled": False},
        # Non possédés : requis par le moteur ou lus par la stratégie.
        "pairlists": [{"method": "StaticPairList"}],
        "dry_run_wallet": stake * m.sizing.max_open_positions,
        "centrade_params": {k: v for k, v in spec.params.items() if k != "pairs"},
    }
    if trailing_on:
        doc["trailing_stop_positive"] = Decimal(str(ex.trailing["positive"]))
    return doc


def render_config(spec: InstanceSpec) -> EngineConfig:
    """Clés possédées uniquement, en chaînes canoniques (comparaison exacte avec drift)."""
    doc = _document(spec)
    values = {k: _canon(_get(doc, k), k) for k in OWNED_KEYS if _get(doc, k) is not None}
    return EngineConfig(values=values)


def _json_number(o: Any) -> Any:
    # Format imposé par le moteur : nombres JSON lus en flottants. Refus si la conversion perd.
    if isinstance(o, Decimal):
        f = float(o)
        if Decimal(repr(f)) != o:
            raise ValueError(f"valeur non représentable sans perte dans la configuration : {o}")
        return f
    raise TypeError(type(o).__name__)


def config_file(spec: InstanceSpec) -> str:
    """Texte JSON du premier fichier de configuration de l'instance (sans identifiants)."""
    return json.dumps(_document(spec), default=_json_number, sort_keys=True, indent=2)


def drift(generated: EngineConfig | Mapping[str, str], effective: Mapping[str, Any]) -> list[Drift]:
    """Écarts sur les clés possédées observables. `effective` : réponse de GET /show_config,
    plus `pair_whitelist` (GET /whitelist). Une clé observable absente est un écart."""
    gen = generated.values if isinstance(generated, EngineConfig) else generated
    out: list[Drift] = []
    for key in OBSERVABLE_KEYS:
        want = _canon(gen[key], key) if key in gen else None
        raw = effective.get(_SHOW_CONFIG_SOURCE[key])
        got = _canon(raw, key) if raw is not None else None
        if key in _SUBSET_KEYS and want is not None and got is not None:
            w, g = json.loads(want), json.loads(got)
            same = isinstance(g, dict) and all(g.get(k) == v for k, v in w.items())
        else:
            same = want == got
        if not same:
            out.append(Drift(key, want, got))
    return out


def effective_mode(effective: Mapping[str, Any]) -> Mode | None:
    """Mode relu dans le moteur (I3). Combinaison absente ou incohérente : None (inconnu)."""
    dry, run = _norm(effective.get("dry_run")), effective.get("runmode")
    if dry is True and run == "dry_run":
        return "paper"
    if dry is True and run == "backtest":
        return "backtest"
    if dry is False and run == "live":
        return "live"
    return None
