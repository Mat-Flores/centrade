"""Types of the engine contract (SPEC §7). Nothing here names a specific engine."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints


def _decimal_only(v: Any) -> Any:
    """Money: never float (rule 5). Strings and integers accepted, finite value required."""
    if isinstance(v, float):
        raise ValueError("float interdit : fournir une chaîne décimale ou un Decimal")
    if isinstance(v, (str, int, Decimal)):
        d = Decimal(v) if not isinstance(v, Decimal) else v
        if not d.is_finite():
            raise ValueError("décimal non fini")
    return v


# Serialized as a decimal string in JSON (Pydantic's native behaviour for Decimal).
Dec = Annotated[Decimal, BeforeValidator(_decimal_only)]
# `asset_class:venue:symbol`, e.g. crypto:binance:BTC/USDT
Symbol = Annotated[str, StringConstraints(pattern=r"^[a-z_]+:[a-z0-9_-]+:[^\s:]+$")]

Mode = Literal["backtest", "paper", "live"]
ObservedState = Literal[
    "starting", "exits_only", "running", "halted", "stopped", "error", "unknown"
]
Side = Literal["buy", "sell"]
Intent = Literal["entry", "increase", "exit", "stop"]


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Capabilities(Model):
    asset_classes: tuple[str, ...]
    modes: tuple[Mode, ...]
    supports_flatten: bool
    supports_pause_entries: bool
    event_transport: Literal["push", "poll"]
    hot_reload: bool
    risk_enforcement: Literal["gateway", "hook", "exchange_only"]
    boots_exits_only: bool
    reports_effective_config: bool
    supports_reduce: bool
    supports_close_position: bool
    supports_cancel_entry_order: bool
    stop_on_venue: dict[str, bool]  # per venue
    native_limits: tuple[str, ...]
    supports_sandbox: bool


class Sizing(Model):
    stake_amount: Dec
    max_open_positions: int = Field(ge=1)


class Exits(Model):
    stoploss: Dec
    stop_on_venue: bool
    trailing: dict[str, Any] = Field(default_factory=dict)
    take_profit: dict[str, Dec] = Field(default_factory=dict)  # minutes elapsed -> target gain


class Manifest(Model):
    name: str
    engine: str
    version: int = Field(ge=1)
    entrypoint: str
    asset_classes: tuple[str, ...]
    trading_mode: Literal["spot"]
    timeframes: tuple[str, ...]
    modes: tuple[Mode, ...]
    params_schema: dict[str, Any] = Field(default_factory=dict)
    sizing: Sizing
    exits: Exits
    risk_defaults: dict[str, Dec] = Field(default_factory=dict)
    requires_data: tuple[str, ...] = ()


class ValidationResult(Model):
    ok: bool
    errors: tuple[str, ...] = ()


class Deployment(Model):
    """What the worker sets at deployment, from the registry and the `engines` table (I10)."""

    fingerprint: str = Field(min_length=1)  # to carry on what runs (container label)
    config_hash: str
    code: str  # source of the strategy version; empty for a simulated instance
    image: str
    digest: str
    engine_version: str
    memory_mb: int | None = None  # `engines` reservations; None: the adapter's default
    cpus: Dec | None = None


class InstanceSpec(Model):
    instance_id: UUID
    engine: str
    mode: Mode
    account_id: str
    manifest: Manifest
    params: dict[str, Any] = Field(default_factory=dict)
    # Always set by the worker; None (contract tests): the F9 verification refuses.
    deployment: Deployment | None = None


class InstanceRef(Model):
    engine: str
    instance_id: UUID


class EngineConfig(Model):
    """Keys owned by the platform, values as strings (exact comparison)."""

    values: dict[str, str]
    # Mode- or instance-specific keys: outside the configuration hash (I10).
    mode_keys: frozenset[str] = frozenset()
    # Keys the engine cannot have re-read. Declared here, never silently ignored:
    # an owned key absent from the re-read and absent from this list is a drift (F9).
    unreadable: frozenset[str] = frozenset()


class EffectiveConfig(Model):
    """What actually runs, re-read from the engine (F9). `values` carries the same key names
    as `EngineConfig.values`; their form stays the engine's (`config_drift` compares it)."""

    values: dict[str, str]
    observed_at: AwareDatetime
    fingerprint: str | None = None  # fingerprint carried by what runs; None: unreadable
    engine_version: str | None = None  # version the engine declares; None: unreadable


class Drift(Model):
    key: str
    expected: str | None  # None: key not generated
    observed: str | None  # None: absent from the re-read


class InstanceStatus(Model):
    state: ObservedState
    mode: Mode | None  # observed mode; None if unknown
    observed_at: AwareDatetime


class Position(Model):
    position_id: str
    symbol: Symbol
    side: Side
    qty: Dec
    entry_price: Dec
    opened_at: AwareDatetime


class Order(Model):
    order_id: str
    symbol: Symbol
    side: Side
    intent: Intent
    qty: Dec
    price: Dec
    status: Literal["open", "filled", "canceled", "rejected"]


class Balance(Model):
    currency: str
    free: Dec
    total: Dec


class Stop(Model):
    position_id: str
    price: Dec | None  # None: no stop
    held_by: Literal["engine", "venue"]


# Canonical enumeration of exit causes (SPEC F10). Any other value is read as `unknown`.
EXIT_CAUSES = (
    "stop_loss",
    "trailing_stop",
    "take_profit",
    "signal",
    "timeout",
    "manual",
    "kill_switch",
    "engine_protection",
    "liquidation",
    "unknown",
)


class ClosedTrade(Model):
    """Closed position, re-read from the engine. `position_id` identifies the trade (unique per
    instance). `pnl` is realized and net of fees; `fees` is reported beside it.
    Cause absent or outside `EXIT_CAUSES`: the worker writes `unknown`, it guesses nothing."""

    position_id: str
    symbol: Symbol
    side: Side
    qty: Dec
    entry_price: Dec
    exit_price: Dec
    pnl: Dec
    fees: Dec = Decimal(0)
    entry_cause: str | None = None
    exit_cause: str | None = None
    opened_at: AwareDatetime
    closed_at: AwareDatetime


class Snapshot(Model):
    positions: tuple[Position, ...]
    orders: tuple[Order, ...]
    balances: tuple[Balance, ...]
    stops: tuple[Stop, ...]
    observed_at: AwareDatetime
    closed: tuple[ClosedTrade, ...] = ()  # closed trades the engine still re-reads


class BacktestSpec(Model):
    manifest: Manifest
    params: dict[str, Any] = Field(default_factory=dict)
    start: datetime
    end: datetime
    timeframe: str


class BacktestResult(Model):
    ok: bool
    trades: int = Field(ge=0)
    metrics: dict[str, Dec] = Field(default_factory=dict)
