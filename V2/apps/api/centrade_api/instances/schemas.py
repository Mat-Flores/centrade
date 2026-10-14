"""Schemas of instances and commands (SPEC §8, §9).

Responses carrying an observed value have `server_time`, the server clock at the time of the
response: the client computes the age without relying on its own. No schema names a specific
engine.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal, Self, cast
from uuid import UUID

from centrade_core.models.trading import Command, Instance
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from centrade_api.core.observed import Observed, ObservedMode, ObservedState, observe


class CommandOut(BaseModel):
    id: UUID
    instance_id: UUID
    type: str
    actor: str
    status: str
    correlation_id: UUID
    requested_at: AwareDatetime
    deadline_at: AwareDatetime
    dispatched_at: AwareDatetime | None
    acknowledged_at: AwareDatetime | None
    verified_at: AwareDatetime | None
    failed_at: AwareDatetime | None
    timed_out_at: AwareDatetime | None
    superseded_at: AwareDatetime | None
    result: dict[str, Any] | None
    server_time: AwareDatetime

    @classmethod
    def of(cls, c: Command, now: datetime) -> CommandOut:
        return cls(
            id=c.id,
            instance_id=c.instance_id,
            type=c.type,
            actor=c.actor,
            status=c.status,
            correlation_id=c.correlation_id,
            requested_at=c.requested_at,
            deadline_at=c.deadline_at,
            dispatched_at=c.dispatched_at,
            acknowledged_at=c.acknowledged_at,
            verified_at=c.verified_at,
            failed_at=c.failed_at,
            timed_out_at=c.timed_out_at,
            superseded_at=c.superseded_at,
            result=c.result,
            server_time=now,
        )


class InstanceOut(BaseModel):
    id: UUID
    name: str
    engine: str  # engine type (`engines` table)
    desired_mode: Literal["paper", "live"]  # desired, set at creation (I3)
    desired_state: Literal["running", "exits_only", "stopped"]  # desired
    state: Observed[ObservedState]  # observed
    observed_mode: Observed[ObservedMode]  # observed
    mode_mismatch: bool  # observed mode known and different from the desired mode (I3)
    active_command: CommandOut | None  # most recent non-terminal command
    created_at: AwareDatetime
    server_time: AwareDatetime

    @classmethod
    def of(
        cls,
        i: Instance,
        kind: str,
        active: Command | None,
        now: datetime,
        stale_after_s: float,
    ) -> InstanceOut:
        # `unknown`: never the last known value presented as current.
        state = cast(ObservedState, i.observed_state if i.observed_at is not None else "unknown")
        mode = cast(
            ObservedMode, i.observed_mode if i.observed_mode and i.observed_at else "unknown"
        )
        return cls(
            id=i.id,
            name=i.name,
            engine=kind,
            desired_mode=i.mode,
            desired_state=i.desired_state,
            state=observe(state, i.observed_at, now, stale_after_s),
            observed_mode=observe(mode, i.observed_at, now, stale_after_s),
            mode_mismatch=mode != "unknown" and mode != i.mode,
            active_command=None if active is None else CommandOut.of(active, now),
            created_at=i.created_at,
            server_time=now,
        )


MAX_PARAMS_CHARS = 4096  # JSON of an instance's parameters: stored, audited, given to the engine


class InstanceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    # Absent: the server takes the only registered engine (no screen names an engine, §7).
    engine: str | None = Field(
        default=None, min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_-]*$"
    )
    mode: Literal["paper"] = "paper"  # going live follows the promotion procedure (F1)
    params: dict[str, Any] = Field(default_factory=dict, max_length=32)  # passed to the adapter
    # Creation from the registry: both together, or neither (simulated creation of M1).
    strategy_version_id: UUID | None = None
    account_id: UUID | None = None

    @model_validator(mode="after")
    def _registry_pair(self) -> Self:
        if (self.strategy_version_id is None) != (self.account_id is None):
            raise ValueError("strategy_version_id et account_id vont ensemble")
        return self

    @field_validator("params")
    @classmethod
    def _bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        # `max_length` counts only the keys: what they contain is bounded too.
        if len(json.dumps(value)) > MAX_PARAMS_CHARS:
            raise ValueError("paramètres trop volumineux")
        return value


class StrategyRef(BaseModel):
    version_id: UUID
    strategy_id: UUID
    name: str
    version: int
    status: str
    code_hash: str
    exits: dict[str, Any]  # exit policy of the version (F10)


class AccountRef(BaseModel):
    """Jamais de référence de secret (I12)."""

    id: UUID
    venue: str
    type: str
    environment: str
    label: str
    currency: str


class DriftItem(BaseModel):
    key: str
    expected: Any
    observed: Any


class InstanceDetail(InstanceOut):
    strategy: StrategyRef | None  # None: instance without a registry version (simulated creation)
    account: AccountRef | None
    deployment_fingerprint: str | None  # computed by the platform (I10)
    config_hash: str | None
    # Version the engine declares, re-read (F9): value None = never observed, hence "unknown".
    engine_version: Observed[str | None]
    # Re-read from the engine: value None = never observed, hence "unknown" (I1).
    effective_config: Observed[dict[str, Any] | None]
    drift: Observed[list[DriftItem] | None]  # empty list: no drift observed


class CommandAccepted(BaseModel):
    command_id: UUID
    command: CommandOut
