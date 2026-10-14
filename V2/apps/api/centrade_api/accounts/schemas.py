"""Schemas of accounts and keys (SPEC F6, I12): no output carries a secret."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Literal
from uuid import UUID

from centrade_core.models.trading import Account, Secret
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, field_validator

from centrade_api.accounts.permissions import KeyUsage, Verdict


def _money(value: Decimal) -> str:
    return format(value.normalize(), "f")


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue: str = Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_-]*$")
    type: Literal["paper", "live"]
    environment: Literal["production", "sandbox"]
    label: str = Field(min_length=1, max_length=80)
    currency: str = Field(pattern=r"^[A-Z0-9]{2,10}$")
    # Decimal string, in `currency`. Bounds of NUMERIC(38, 18).
    capital_cap: Decimal | None = Field(
        default=None, gt=0, lt=Decimal("1e20"), max_digits=38, decimal_places=18
    )

    @field_validator("capital_cap", mode="before")
    @classmethod
    def _decimal_string(cls, v: object) -> object:
        if v is not None and not isinstance(v, str):
            raise ValueError("chaîne décimale attendue")  # never a float for money
        return v


class SecretIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usage: KeyUsage
    key: SecretStr = Field(min_length=1, max_length=512)
    secret: SecretStr = Field(min_length=1, max_length=1024)

    def value(self) -> SecretStr:
        return SecretStr(
            json.dumps(
                {"key": self.key.get_secret_value(), "secret": self.secret.get_secret_value()}
            )
        )


class KeyOut(BaseModel):
    """Everything said about a key: never its value, a prefix or a fingerprint."""

    usage: str
    key_version: int
    stored_at: AwareDatetime
    rotated_at: AwareDatetime | None
    last_used_at: AwareDatetime | None

    @classmethod
    def of(cls, s: Secret) -> KeyOut:
        return cls(
            usage=s.usage,
            key_version=s.key_version,
            stored_at=s.created_at,
            rotated_at=s.rotated_at,
            last_used_at=s.last_used_at,
        )


class AccountOut(BaseModel):
    id: UUID
    venue: str
    type: str
    environment: str
    label: str
    currency: str
    capital_cap: str | None  # decimal string
    trade_key: KeyOut | None
    read_key: KeyOut | None
    permissions_verified_at: AwareDatetime | None  # None: not verified, live blocked
    ip_restricted: bool | None  # None: unknown
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @classmethod
    def of(cls, a: Account, secrets: dict[UUID, Secret]) -> AccountOut:
        def key(ref: UUID | None) -> KeyOut | None:
            return KeyOut.of(secrets[ref]) if ref in secrets else None

        return cls(
            id=a.id,
            venue=a.venue,
            type=a.type,
            environment=a.environment,
            label=a.label,
            currency=a.currency,
            capital_cap=None if a.capital_cap is None else _money(a.capital_cap),
            trade_key=key(a.secret_ref),
            read_key=key(a.read_secret_ref),
            permissions_verified_at=a.permissions_verified_at,
            ip_restricted=a.ip_restricted,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )


class PermissionTestOut(BaseModel):
    result: Verdict
    account: AccountOut
