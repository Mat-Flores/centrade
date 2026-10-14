"""Schemas of the read-only logs: events, alerts, audit."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from centrade_core.models.trading import Alert, Event
from pydantic import AwareDatetime, BaseModel


class EventOut(BaseModel):
    id: UUID
    ts: AwareDatetime  # engine time
    ts_ingest: AwareDatetime  # reception time
    type: str
    instance_id: UUID
    seq: int
    correlation_id: UUID | None
    payload: dict[str, Any]  # decimals as strings (canonical envelope)

    @classmethod
    def of(cls, e: Event) -> EventOut:
        return cls(
            id=e.id,
            ts=e.ts,
            ts_ingest=e.ts_ingest,
            type=e.type,
            instance_id=e.instance_id,
            seq=e.seq,
            correlation_id=e.correlation_id,
            payload=e.payload,
        )


class AlertOut(BaseModel):
    id: UUID
    rule: str
    severity: str
    target_kind: str
    target_id: UUID | None
    status: str
    message: str
    correlation_id: UUID | None
    invariant: str | None
    created_at: AwareDatetime
    acknowledged_at: AwareDatetime | None
    resolved_at: AwareDatetime | None

    @classmethod
    def of(cls, a: Alert) -> AlertOut:
        return cls.model_validate(a, from_attributes=True)


class AuditOut(BaseModel):
    seq: int
    ts: AwareDatetime
    actor: str
    action: str
    target: str
    before_hash: str | None
    after_hash: str | None
    ip: str | None
