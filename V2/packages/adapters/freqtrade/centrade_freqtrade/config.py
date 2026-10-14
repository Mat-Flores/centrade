"""Freqtrade configuration owned by the platform (SPEC §7, annex C, ADR 0008).

Everything is pure: same input, same output. The native API credentials come from a second
configuration file (deep merge, the last one wins), written by the worker.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from centrade_core.engine.types import EngineConfig, InstanceSpec, Mode

# Owned keys (annex C), in dotted notation. EngineConfig values: canonical strings.
# Every key written in the generated file is one of them (I10): a test checks it leaf by
# leaf, and that changing any one changes the configuration hash.
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
    "exchange.pair_blacklist",
    "pairlists",
    "stoploss",
    "trailing_stop",
    "trailing_stop_positive",
    "trailing_stop_positive_offset",
    "trailing_only_offset_is_reached",
    "minimal_roi",
    "order_types",
    "cancel_open_orders_on_exit",
    # Runtime settings decided by the platform (ADR 0008), not by the strategy.
    "entry_pricing",
    "exit_pricing",
    "unfilledtimeout",
    "dry_run_wallet",
    "centrade_params",
    "api_server.enabled",
    "api_server.listen_ip_address",
    "api_server.listen_port",
    "api_server.verbosity",
    "api_server.CORS_origins",
    "webhook.enabled",
    "webhook.allow_custom_messages",
    "telegram.enabled",
)
# Never written for paper or backtest (I3); in live they come from the credentials file.
VENUE_CREDENTIAL_KEYS: tuple[str, ...] = (
    "exchange.key",
    "exchange.secret",
    "exchange.password",
    "exchange.uid",
)

# Owned key -> GET /show_config key. `exchange.pair_whitelist` is not in it: the execution
# adapter adds it under `pair_whitelist` from GET /whitelist. Keys absent from this
# table are not rendered by the engine's API: they are declared `unreadable`, each with
# its justification in ADR 0008.
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
    "entry_pricing": "entry_pricing",
    "exit_pricing": "exit_pricing",
    "unfilledtimeout": "unfilledtimeout",
}
OBSERVABLE_KEYS: tuple[str, ...] = tuple(k for k in OWNED_KEYS if k in _SHOW_CONFIG_SOURCE)
# The engine may add default values to these dictionaries: only our keys count.
_SUBSET_KEYS = frozenset({"order_types", "entry_pricing", "exit_pricing", "unfilledtimeout"})

# Mode- or instance-specific: outside the configuration hash (I10).
MODE_KEYS = frozenset({"dry_run", "db_url", "bot_name"})

API_PORT = 8080
# Subfolder of /data created by the runner under the container user's name: the volume root
# belongs to root, the engine writes nothing there.
USER_DATA = "/data/engine"


@dataclass(frozen=True, slots=True)
class Drift:
    key: str
    expected: str | None
    observed: str | None


def _num(d: Decimal) -> str:
    return str(d).lower() if not d.is_finite() else format(d.normalize(), "f")


def _norm(v: Any) -> Any:
    """Comparable canonical form: normalized decimal numbers (50, 50.0 and "50" are equal)."""
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
    """`params["pairs"]`: normalized symbols `crypto:venue:BASE/QUOTE`, a single venue and a
    single quote currency. Supplied by the platform, not by the strategy author."""
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
    """Nested configuration, money as Decimal. Single source of render_config and of the file."""
    m = spec.manifest
    if m.trading_mode != "spot":
        raise ValueError("seul le mode spot est admis en V1")
    venue, pairs, quote = _pairs(spec.params)
    ex = m.exits
    trailing_on = bool(ex.trailing.get("enabled", False))
    stake = m.sizing.stake_amount
    doc: dict[str, Any] = {
        # Derived from the mode enumeration: a paper or backtest instance stays in dry-run.
        "dry_run": spec.mode != "live",
        "db_url": f"sqlite:///{USER_DATA}/trades-{spec.mode}.sqlite",
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
        or {"0": Decimal(100)},  # 10000 %: no declared profit target
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
            "listen_ip_address": "0.0.0.0",  # noqa: S104  engine network only (Compose)
            "listen_port": API_PORT,
            "verbosity": "error",
            "CORS_origins": [],
        },
        "webhook": {"enabled": False, "allow_custom_messages": False},
        "telegram": {"enabled": False},
        "pairlists": [{"method": "StaticPairList"}],
        # Platform runtime setting, the same for every strategy (ADR 0008). The
        # engine requires these blocks (KeyError at startup without them). `other`: the limit order
        # crosses the book, so it fills; with `same` an order could stay posted until the
        # timeout (observed), including on exit, which delays an exit (I4).
        "entry_pricing": {
            "price_side": "other",
            "use_order_book": True,
            "order_book_top": 1,
            "price_last_balance": Decimal(0),
            "check_depth_of_market": {"enabled": False, "bids_to_ask_delta": Decimal(1)},
        },
        "exit_pricing": {"price_side": "other", "use_order_book": True, "order_book_top": 1},
        "unfilledtimeout": {"entry": 10, "exit": 10, "unit": "minutes"},
        "dry_run_wallet": stake * m.sizing.max_open_positions,
        "centrade_params": {k: v for k, v in spec.params.items() if k != "pairs"},
    }
    if trailing_on:
        doc["trailing_stop_positive"] = Decimal(str(ex.trailing["positive"]))
    return doc


def render_config(spec: InstanceSpec) -> EngineConfig:
    """Owned keys only, as canonical strings (exact comparison with drift)."""
    doc = _document(spec)
    values = {k: _canon(_get(doc, k), k) for k in OWNED_KEYS if _get(doc, k) is not None}
    return EngineConfig(
        values=values,
        mode_keys=frozenset(MODE_KEYS & values.keys()),
        unreadable=frozenset(values.keys() - set(OBSERVABLE_KEYS)),
    )


def observed_values(show_config: Mapping[str, Any], whitelist: Any) -> dict[str, str]:
    """Re-read brought back to the owned key names and render_config's canonical strings.
    This is the only place where a re-read value is canonicalized."""
    seen = {**show_config, "pair_whitelist": whitelist}
    out: dict[str, str] = {}
    for key in OBSERVABLE_KEYS:
        raw = seen.get(_SHOW_CONFIG_SOURCE[key])
        if raw is not None:
            out[key] = _canon(raw, key)
    return out


def _within(want: Any, got: Any) -> bool:
    """Our inputs are in the re-read, at any depth; the engine's defaults in addition."""
    if isinstance(want, dict):
        return isinstance(got, dict) and all(
            k in got and _within(v, got[k]) for k, v in want.items()
        )
    return bool(want == got)


def _same(key: str, want: str | None, got: str | None) -> bool:
    """Compares two canonical strings of the same key."""
    if key in _SUBSET_KEYS and want is not None and got is not None:
        try:
            return _within(json.loads(want), json.loads(got))
        except ValueError:  # the re-read does not have the expected shape: that is a drift
            return False
    return want == got


def observed_drift(generated: EngineConfig, observed: Mapping[str, str]) -> list[Drift]:
    """Drifts on the re-read keys, from the values of `observed_values`. A key absent from
    the re-read is not reported here: `owned_drifts` handles it."""
    gen = generated.values
    return [
        Drift(k, gen.get(k), observed[k])
        for k in OBSERVABLE_KEYS
        if k in observed and not _same(k, gen.get(k), observed[k])
    ]


def drift(generated: EngineConfig, effective: Mapping[str, Any]) -> list[Drift]:
    """Drifts on the observable owned keys. `effective`: response of GET /show_config,
    plus `pair_whitelist` (GET /whitelist). An absent observable key is a drift."""
    gen = generated.values
    seen = observed_values(effective, effective.get("pair_whitelist"))
    return [
        Drift(k, gen.get(k), seen.get(k))
        for k in OBSERVABLE_KEYS
        if not _same(k, gen.get(k), seen.get(k))
    ]


def _json_number(o: Any) -> Any:
    # Format imposed by the engine: JSON numbers read as floats. Refused if conversion loses data.
    if isinstance(o, Decimal):
        f = float(o)
        if Decimal(repr(f)) != o:
            raise ValueError(f"valeur non représentable sans perte dans la configuration : {o}")
        return f
    raise TypeError(type(o).__name__)


def _to_json(doc: Any) -> str:
    # allow_nan=False: an infinite or undefined number is refused (ValueError), never written.
    return json.dumps(doc, default=_json_number, sort_keys=True, indent=2, allow_nan=False)


def config_file(spec: InstanceSpec) -> str:
    """JSON text of the instance's first configuration file (without credentials)."""
    doc = _document(spec)
    # The engine's schema requires token and chat_id as soon as the block exists, even disabled: we
    # omit it (absent = disabled). `render_config` keeps `telegram.enabled=false`.
    doc.pop("telegram")
    return _to_json(doc)


def effective_mode(effective: Mapping[str, Any]) -> Mode | None:
    """Mode re-read from the engine (I3). Missing or inconsistent combination: None (unknown)."""
    dry, run = _norm(effective.get("dry_run")), effective.get("runmode")
    if dry is True and run == "dry_run":
        return "paper"
    if dry is True and run == "backtest":
        return "backtest"
    if dry is False and run == "live":
        return "live"
    return None
