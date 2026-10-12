from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from centrade_core.models.base import Base, now_col, updated_at, uuid_pk


class Engine(Base):
    __tablename__ = "engines"

    id: Mapped[UUID] = uuid_pk()
    kind: Mapped[str]
    image: Mapped[str]
    version: Mapped[str]
    digest: Mapped[str | None]
    memory_reservation_mb: Mapped[int | None]  # par instance, pour l'admission
    cpu_reservation: Mapped[Decimal | None]
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
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    strategy_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id"), index=True
    )
    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    container_ref: Mapped[str | None]
    # Identifiants de l'API native du moteur (usage `engine_api`), renouvelés à chaque déploiement.
    engine_secret_ref: Mapped[UUID | None] = mapped_column(ForeignKey("secrets.id"))
    deployment_fingerprint: Mapped[str | None]  # I10
    config_hash: Mapped[str | None]  # hash de la configuration générée
    effective_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # relue (F9)
    effective_config_at: Mapped[datetime | None]
    # Dérive constatée : liste de {key, expected, observed}, écrite par le worker (F9).
    drift: Mapped[list[dict[str, Any]] | dict[str, Any] | None] = mapped_column(JSONB)
    paper_origin_id: Mapped[UUID | None] = mapped_column(ForeignKey("instances.id"))
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = updated_at()


class Command(Base):
    __tablename__ = "commands"
    # La clé d'idempotence est propre à son auteur.
    __table_args__ = (UniqueConstraint("actor", "idempotency_key"),)

    id: Mapped[UUID] = uuid_pk()
    instance_id: Mapped[UUID] = mapped_column(ForeignKey("instances.id"), index=True)
    type: Mapped[str]
    actor: Mapped[str]
    idempotency_key: Mapped[str]
    args: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # position_id, order_id
    request_hash: Mapped[str] = mapped_column(server_default="")  # instance + type, anti-rejeu
    status: Mapped[str] = mapped_column(server_default="requested", index=True)
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
    external_id: Mapped[str]  # identifiant côté moteur ; unique par instance
    instrument: Mapped[str]
    side: Mapped[str]  # long | short
    quantity: Mapped[Decimal]
    entry_price: Mapped[Decimal | None]
    currency: Mapped[str]
    observed_at: Mapped[datetime]
    # Protection (F10, I7) : le stop est dans la devise de la position.
    stop_price: Mapped[Decimal | None]
    stop_venue: Mapped[str | None]  # venue | engine
    stop_type: Mapped[str | None]  # fixed | trailing | dynamic
    protection_state: Mapped[str] = mapped_column(server_default="unknown")
    protection_verified_at: Mapped[datetime | None]
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


class Secret(Base):
    """Jamais renvoyé par l'API (I12) : seul le worker déchiffre."""

    __tablename__ = "secrets"

    id: Mapped[UUID] = uuid_pk()
    kind: Mapped[str]
    usage: Mapped[str]  # trade | read | engine_api | webhook
    ciphertext: Mapped[bytes]
    nonce: Mapped[bytes]
    key_version: Mapped[int]
    last_used_at: Mapped[datetime | None]
    rotated_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = updated_at()


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[UUID] = uuid_pk()
    venue: Mapped[str]
    type: Mapped[str]  # paper | live
    environment: Mapped[str]  # production | sandbox
    label: Mapped[str]
    currency: Mapped[str]
    capital_cap: Mapped[Decimal | None]  # dans `currency`
    secret_ref: Mapped[UUID | None] = mapped_column(ForeignKey("secrets.id"))
    read_secret_ref: Mapped[UUID | None] = mapped_column(ForeignKey("secrets.id"))
    permissions_verified_at: Mapped[datetime | None]  # vide = non vérifié, live bloqué
    ip_restricted: Mapped[bool | None]  # constaté sur la venue ; None = inconnu
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = updated_at()


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = updated_at()


class StrategyVersion(Base):
    """Manifest, code et politique de sortie sont immuables (trigger) ; seul le statut change."""

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version"),
        UniqueConstraint("strategy_id", "idempotency_key"),
    )

    id: Mapped[UUID] = uuid_pk()
    strategy_id: Mapped[UUID] = mapped_column(ForeignKey("strategies.id"), index=True)
    version: Mapped[int]
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
    code: Mapped[str]  # source déposé, immuable comme le manifest
    idempotency_key: Mapped[str | None]  # rejeu d'un même dépôt
    code_hash: Mapped[str]
    status: Mapped[str] = mapped_column(server_default="draft")  # draft | approved | retired
    author: Mapped[str]
    static_checks: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    exits: Mapped[dict[str, Any]] = mapped_column(JSONB)  # politique de sortie (F10)
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = updated_at()


class Trade(Base):
    """Position close ; projection dérivée des événements."""

    __tablename__ = "trades"
    __table_args__ = (UniqueConstraint("instance_id", "external_id"),)

    id: Mapped[UUID] = uuid_pk()
    instance_id: Mapped[UUID] = mapped_column(ForeignKey("instances.id"), index=True)
    external_id: Mapped[str]  # identifiant côté moteur
    instrument: Mapped[str]
    quantity: Mapped[Decimal]
    entry_price: Mapped[Decimal]
    exit_price: Mapped[Decimal]
    entry_cause: Mapped[str]
    exit_cause: Mapped[str]  # énumération de F10
    pnl: Mapped[Decimal]
    fees: Mapped[Decimal]
    currency: Mapped[str]
    opened_at: Mapped[datetime]
    closed_at: Mapped[datetime]
    duration_s: Mapped[int]
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = updated_at()


class ServiceAccount(Base):
    __tablename__ = "service_accounts"

    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(unique=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    token_hash: Mapped[str] = mapped_column(unique=True)
    instance_id: Mapped[UUID | None] = mapped_column(ForeignKey("instances.id"), index=True)
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = updated_at()
