from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from centrade_core.models.base import Base, now_col, updated_at, uuid_pk


class Engine(Base):
    __tablename__ = "engines"

    id: Mapped[UUID] = uuid_pk()
    kind: Mapped[str]
    image: Mapped[str]
    version: Mapped[str]
    digest: Mapped[str | None]
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = updated_at()


class Instance(Base):
    __tablename__ = "instances"

    id: Mapped[UUID] = uuid_pk()
    engine_id: Mapped[UUID] = mapped_column(ForeignKey("engines.id"), index=True)
    name: Mapped[str] = mapped_column(unique=True)
    mode: Mapped[str]  # paper | live ; immuable (trigger)
    desired_state: Mapped[str]  # running | exits_only | stopped
    observed_state: Mapped[str] = mapped_column(server_default="unknown")
    observed_at: Mapped[datetime | None]
    observed_mode: Mapped[str | None]
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = updated_at()


class Command(Base):
    __tablename__ = "commands"

    id: Mapped[UUID] = uuid_pk()
    instance_id: Mapped[UUID] = mapped_column(ForeignKey("instances.id"), index=True)
    type: Mapped[str]
    actor: Mapped[str]
    idempotency_key: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(server_default="requested")
    correlation_id: Mapped[UUID]
    deadline_at: Mapped[datetime]
    requested_at: Mapped[datetime] = now_col()
    dispatched_at: Mapped[datetime | None]
    acknowledged_at: Mapped[datetime | None]
    verified_at: Mapped[datetime | None]
    failed_at: Mapped[datetime | None]
    timed_out_at: Mapped[datetime | None]
    superseded_at: Mapped[datetime | None]
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = updated_at()


class Event(Base):
    """Hypertable sur `ts` : l'unicité doit contenir `ts`."""

    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(primary_key=True)  # heure du moteur
    ts_ingest: Mapped[datetime] = mapped_column(server_default=func.now())
    type: Mapped[str]
    instance_id: Mapped[UUID] = mapped_column(ForeignKey("instances.id"))
    seq: Mapped[int] = mapped_column(BigInteger)  # par instance
    correlation_id: Mapped[UUID | None]
    schema_version: Mapped[int]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[UUID] = uuid_pk()
    instance_id: Mapped[UUID] = mapped_column(ForeignKey("instances.id"), index=True)
    instrument: Mapped[str]
    side: Mapped[str]  # long | short
    quantity: Mapped[Decimal]
    entry_price: Mapped[Decimal | None]
    currency: Mapped[str]
    observed_at: Mapped[datetime]
    updated_at: Mapped[datetime] = updated_at()


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[UUID] = uuid_pk()
    instance_id: Mapped[UUID] = mapped_column(ForeignKey("instances.id"), index=True)
    client_order_id: Mapped[str] = mapped_column(unique=True)
    instrument: Mapped[str]
    side: Mapped[str]  # buy | sell
    intent: Mapped[str]  # entry | increase | exit | stop
    status: Mapped[str]
    quantity: Mapped[Decimal]
    price: Mapped[Decimal | None]
    currency: Mapped[str]
    decision_id: Mapped[UUID | None]
    observed_at: Mapped[datetime]
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = updated_at()


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[UUID] = uuid_pk()
    rule: Mapped[str]
    severity: Mapped[str]  # info | warning | critical
    target_kind: Mapped[str]  # instance | account | global
    target_id: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(server_default="open")
    message: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[UUID | None]
    invariant: Mapped[str | None]
    created_at: Mapped[datetime] = now_col()
    acknowledged_at: Mapped[datetime | None]
    resolved_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = updated_at()
