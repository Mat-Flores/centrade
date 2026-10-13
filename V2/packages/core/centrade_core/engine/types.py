"""Types du contrat moteur (SPEC §7). Rien ici ne nomme un moteur précis."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints


def _decimal_only(v: Any) -> Any:
    """Argent : jamais de float (règle 5). Chaînes et entiers acceptés, valeur finie exigée."""
    if isinstance(v, float):
        raise ValueError("float interdit : fournir une chaîne décimale ou un Decimal")
    if isinstance(v, (str, int, Decimal)):
        d = Decimal(v) if not isinstance(v, Decimal) else v
        if not d.is_finite():
            raise ValueError("décimal non fini")
    return v


# Sérialisé en chaîne décimale en JSON (comportement natif de Pydantic pour Decimal).
Dec = Annotated[Decimal, BeforeValidator(_decimal_only)]
# `asset_class:venue:symbol`, ex. crypto:binance:BTC/USDT
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
    stop_on_venue: dict[str, bool]  # par venue
    native_limits: tuple[str, ...]
    supports_sandbox: bool


class Sizing(Model):
    stake_amount: Dec
    max_open_positions: int = Field(ge=1)


class Exits(Model):
    stoploss: Dec
    stop_on_venue: bool
    trailing: dict[str, Any] = Field(default_factory=dict)
    take_profit: dict[str, Dec] = Field(default_factory=dict)  # minutes écoulées -> gain visé


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
    """Ce que le worker fixe au déploiement, depuis le registre et la table `engines` (I10)."""

    fingerprint: str = Field(min_length=1)  # à porter sur ce qui tourne (étiquette du conteneur)
    config_hash: str
    code: str  # source de la version de stratégie ; vide pour une instance simulée
    image: str
    digest: str
    engine_version: str
    memory_mb: int | None = None  # réservations de `engines` ; None : défaut de l'adaptateur
    cpus: Dec | None = None


class InstanceSpec(Model):
    instance_id: UUID
    engine: str
    mode: Mode
    account_id: str
    manifest: Manifest
    params: dict[str, Any] = Field(default_factory=dict)
    # Toujours renseigné par le worker ; None (tests de contrat) : la vérification de F9 refuse.
    deployment: Deployment | None = None


class InstanceRef(Model):
    engine: str
    instance_id: UUID


class EngineConfig(Model):
    """Clés possédées par la plateforme, valeurs en chaînes (comparaison exacte)."""

    values: dict[str, str]
    # Clés propres au mode ou à l'instance : hors du hash de configuration (I10).
    mode_keys: frozenset[str] = frozenset()
    # Clés que le moteur ne sait pas faire relire. Déclarées ici, jamais ignorées en silence :
    # une clé possédée absente de la relecture et absente de cette liste est une dérive (F9).
    unreadable: frozenset[str] = frozenset()


class EffectiveConfig(Model):
    """Ce qui tourne réellement, relu dans le moteur (F9). `values` porte les mêmes noms de clés
    que `EngineConfig.values` ; leur forme reste celle du moteur (`config_drift` la compare)."""

    values: dict[str, str]
    observed_at: AwareDatetime
    fingerprint: str | None = None  # empreinte portée par ce qui tourne ; None : illisible
    engine_version: str | None = None  # version que le moteur déclare ; None : illisible


class Drift(Model):
    key: str
    expected: str | None  # None : clé non générée
    observed: str | None  # None : absente de la relecture


class InstanceStatus(Model):
    state: ObservedState
    mode: Mode | None  # mode observé ; None si inconnu
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
    price: Dec | None  # None : stop absent
    held_by: Literal["engine", "venue"]


# Énumération canonique des causes de sortie (SPEC F10). Toute autre valeur est lue `unknown`.
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
    """Position close, relue dans le moteur. `position_id` identifie le trade (unique par instance).
    Cause absente ou hors de `EXIT_CAUSES` : le worker écrit `unknown`, il ne devine rien."""

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
    closed: tuple[ClosedTrade, ...] = ()  # trades clos que le moteur relit encore


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
