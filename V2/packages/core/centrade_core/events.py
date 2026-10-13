"""Événements canoniques (SPEC §7, annexe B). Décimaux en chaînes une fois sérialisés."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from centrade_core.engine.types import Dec, Intent, Mode, ObservedState, Side, Symbol


class EventType(StrEnum):
    INSTANCE_STATUS_CHANGED = "instance.status_changed"
    SIGNAL_CREATED = "signal.created"
    ORDER_SUBMITTED = "order.submitted"
    ORDER_FILLED = "order.filled"
    ORDER_CANCELED = "order.canceled"
    ORDER_REJECTED = "order.rejected"
    POSITION_UPDATED = "position.updated"
    POSITION_CLOSED = "position.closed"
    PROTECTION_UPDATED = "protection.updated"
    PNL_SNAPSHOT = "pnl.snapshot"
    ENGINE_ERROR = "engine.error"


ExitCause = Literal["manual", "flatten", "stop", "take_profit", "signal", "unknown"]


class _Payload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StatusChanged(_Payload):
    state: ObservedState
    mode: Mode | None


class SignalCreated(_Payload):
    symbol: Symbol
    side: Side


class OrderPayload(_Payload):
    """Commun à order.submitted, filled, canceled et rejected."""

    client_order_id: UUID
    intent: Intent
    decision_id: UUID | None = None  # pour une entrée
    symbol: Symbol
    side: Side
    qty: Dec
    price: Dec
    fee: Dec | None = None
    currency: str


class PositionUpdated(_Payload):
    position_id: str
    symbol: Symbol
    side: Side
    qty: Dec
    entry_price: Dec


class PositionClosed(_Payload):
    position_id: str
    symbol: Symbol
    exit_cause: ExitCause
    qty: Dec
    exit_price: Dec


class ProtectionUpdated(_Payload):
    position_id: str
    state: Literal["set", "moved", "absent"]
    stop_price: Dec | None = None
    held_by: Literal["engine", "venue"] = "engine"


class PnlSnapshot(_Payload):
    currency: str
    realized: Dec
    unrealized: Dec


class EngineError(_Payload):
    code: str
    message: str


Payload = (
    StatusChanged
    | SignalCreated
    | OrderPayload
    | PositionUpdated
    | PositionClosed
    | ProtectionUpdated
    | PnlSnapshot
    | EngineError
)

PAYLOAD_MODELS: dict[EventType, type[_Payload]] = {
    EventType.INSTANCE_STATUS_CHANGED: StatusChanged,
    EventType.SIGNAL_CREATED: SignalCreated,
    EventType.ORDER_SUBMITTED: OrderPayload,
    EventType.ORDER_FILLED: OrderPayload,
    EventType.ORDER_CANCELED: OrderPayload,
    EventType.ORDER_REJECTED: OrderPayload,
    EventType.POSITION_UPDATED: PositionUpdated,
    EventType.POSITION_CLOSED: PositionClosed,
    EventType.PROTECTION_UPDATED: ProtectionUpdated,
    EventType.PNL_SNAPSHOT: PnlSnapshot,
    EventType.ENGINE_ERROR: EngineError,
}


class CanonicalEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    id: UUID
    ts: AwareDatetime  # heure du moteur
    ts_ingest: AwareDatetime | None = None  # heure de réception, posée à l'ingestion
    seq: Annotated[int, Field(ge=1)]  # séquence par instance
    type: EventType
    engine: str
    instance_id: UUID
    strategy_version: str | None = None
    account_id: str | None = None
    correlation_id: UUID | None = None
    payload: Payload  # déclaré après `type` : le validateur s'en sert

    @field_validator("payload", mode="before")
    @classmethod
    def _typed_payload(cls, v: Any, info: ValidationInfo) -> Any:
        t = info.data.get("type")
        if t is None:
            return v
        model = PAYLOAD_MODELS[t]
        if isinstance(v, model):
            return v
        if isinstance(v, _Payload):
            raise ValueError(f"charge utile {type(v).__name__} incompatible avec {t.value}")
        return model.model_validate(v)
