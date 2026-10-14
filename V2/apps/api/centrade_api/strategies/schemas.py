"""Schemas of the strategy registry (SPEC F1, §8)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from centrade_core.models.trading import StrategyVersion
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Status = Literal["draft", "approved", "retired"]


class StrategyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")


class StrategyOut(BaseModel):
    id: UUID
    name: str
    created_at: AwareDatetime


class VersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest: dict[str, Any]
    code: str = Field(min_length=1, max_length=60_000)


class StatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status


class VersionOut(BaseModel):
    id: UUID
    strategy_id: UUID
    version: int
    status: Status
    engine: str  # engine type, read from the manifest
    manifest: dict[str, Any]
    code_hash: str
    author: str
    static_checks: dict[str, Any]
    exits: dict[str, Any]  # exit policy (F10): stoploss and ratios as decimal strings
    created_at: AwareDatetime

    @classmethod
    def of(cls, v: StrategyVersion) -> VersionOut:
        return cls(
            **{k: getattr(v, k) for k in cls.model_fields if k != "engine"},
            engine=v.manifest["engine"],
        )


class VersionDetail(VersionOut):
    code: str

    @classmethod
    def of(cls, v: StrategyVersion) -> VersionDetail:
        return cls(**VersionOut.of(v).model_dump(), code=v.code)
