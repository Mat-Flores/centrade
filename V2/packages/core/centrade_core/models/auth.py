from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, LargeBinary, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from centrade_core.models.base import Base, now_col, updated_at, uuid_pk


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(unique=True)
    role: Mapped[str]  # viewer | operator | admin
    password_hash: Mapped[str]  # argon2id
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)  # AES-256-GCM
    totp_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)  # anti-replay
    recovery_code_hashes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    failed_attempts: Mapped[int] = mapped_column(server_default="0")
    locked_until: Mapped[datetime | None]
    created_at: Mapped[datetime] = now_col()
    updated_at: Mapped[datetime] = updated_at()


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(unique=True)  # SHA-256 of the token, never the token
    stage: Mapped[str]  # pre_totp | full
    created_at: Mapped[datetime] = now_col()
    last_activity_at: Mapped[datetime] = now_col()
    expires_at: Mapped[datetime]
    totp_verified_at: Mapped[datetime | None]  # re-authentication for dangerous actions
