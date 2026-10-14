from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, MetaData, Numeric, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from centrade_core.ids import uuid7


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    # Dates in UTC, exact amounts: never float (SPEC §6).
    type_annotation_map = {  # noqa: RUF012
        datetime: DateTime(timezone=True),
        Decimal: Numeric(38, 18),
        UUID: PG_UUID(as_uuid=True),
    }


def uuid_pk() -> Mapped[UUID]:
    return mapped_column(primary_key=True, default=uuid7)


def now_col() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


def updated_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), onupdate=func.now())
