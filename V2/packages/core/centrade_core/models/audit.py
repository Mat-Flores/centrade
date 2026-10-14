from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from centrade_core.models.base import Base, uuid_pk


class AuditLog(Base):
    """Append-only (trigger); each row carries the previous row's fingerprint (I14)."""

    __tablename__ = "audit_log"

    id: Mapped[UUID] = uuid_pk()
    seq: Mapped[int] = mapped_column(BigInteger, unique=True)
    ts: Mapped[datetime]
    actor: Mapped[str]
    action: Mapped[str]
    target: Mapped[str]
    before_hash: Mapped[str | None]
    after_hash: Mapped[str | None]
    ip: Mapped[str | None]
    prev_hash: Mapped[str] = mapped_column(unique=True)
    row_hash: Mapped[str]
