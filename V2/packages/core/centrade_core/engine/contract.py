"""EngineAdapter Protocol (SPEC §7), asynchronous; commands are idempotent."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from pydantic import SecretStr

from centrade_core.engine.types import (
    BacktestResult,
    BacktestSpec,
    Capabilities,
    Drift,
    EffectiveConfig,
    EngineConfig,
    InstanceRef,
    InstanceSpec,
    InstanceStatus,
    Manifest,
    Snapshot,
    ValidationResult,
)

if TYPE_CHECKING:  # events imports engine.types: avoids the cycle
    from centrade_core.events import CanonicalEvent


class EngineUnreachable(Exception):
    """The engine does not answer (silence, crash, timeout). The caller infers `unknown`."""


class CommandRejected(Exception):
    """Command impossible in the current state (e.g. resume the entries of a stopped instance)."""


class StaticChecks(Protocol):
    """Pure checks (no network, no Docker): the registry runs them when a version is written."""

    def validate(self, manifest: Manifest, params: dict[str, Any]) -> ValidationResult: ...
    def check_source(self, manifest: Manifest, source: str) -> ValidationResult: ...


class EngineAdapter(StaticChecks, Protocol):
    def capabilities(self) -> Capabilities: ...
    def render_config(self, spec: InstanceSpec) -> EngineConfig: ...  # pure
    async def deploy(self, spec: InstanceSpec) -> InstanceRef: ...  # exits-only
    async def start(self, ref: InstanceRef) -> None: ...  # restart, exits-only
    async def stop(self, ref: InstanceRef) -> None: ...
    async def pause_entries(self, ref: InstanceRef) -> None: ...
    async def resume_entries(self, ref: InstanceRef) -> None: ...
    async def flatten(self, ref: InstanceRef) -> None: ...
    async def close_position(self, ref: InstanceRef, position_id: str) -> None: ...
    async def cancel_entry_order(self, ref: InstanceRef, order_id: str) -> None: ...
    async def status(self, ref: InstanceRef) -> InstanceStatus: ...
    # Effective mode (I3): `status().mode`, re-read from the engine, never copied from the request.
    async def effective_config(self, ref: InstanceRef) -> EffectiveConfig: ...

    def config_drift(  # pure
        self, generated: EngineConfig, effective: EffectiveConfig
    ) -> tuple[Drift, ...]:
        """Differences between the re-read and the generated configuration, on the re-read keys.
        The worker compares nothing itself: it only adds the missing keys (`owned_drifts`)."""
        ...

    async def snapshot(self, ref: InstanceRef) -> Snapshot: ...
    def events(self, ref: InstanceRef) -> AsyncIterator[CanonicalEvent]: ...
    async def backtest(self, spec: BacktestSpec) -> BacktestResult: ...


class InstanceRuntime(Protocol):
    """What a container-based adapter asks of the worker: files and native API credentials
    of an instance. The credentials are random tokens specific to the instance,
    stored by the SecretStore (usage `engine_api`); no venue key goes through here."""

    def container_user(self) -> str:
        """`uid:gid` to run the container under so that it reads its files (0400)."""
        ...

    async def issue_credentials(
        self, instance_id: UUID, names: tuple[str, ...]
    ) -> dict[str, SecretStr]:
        """At every deployment: a new token per name; the previous ones are destroyed."""
        ...

    async def credentials(self, instance_id: UUID) -> dict[str, SecretStr]:
        """Those of the last deployment (after a worker restart). `LookupError` otherwise."""
        ...

    async def write_files(
        self, instance_id: UUID, files: Mapping[str, str], credentials: Mapping[str, Any]
    ) -> Path:
        """Writes `files` (plain name -> text) and the credentials file (JSON of
        `credentials`, shape chosen by the adapter) into the instance's subfolder.
        Returns that folder, to be mounted read-only."""
        ...

    async def cleanup(self, instance_id: UUID) -> None:
        """On stop: removes the credentials file. No effect if it does not exist."""
        ...


def owned_drifts(
    generated: EngineConfig, effective: EffectiveConfig, reported: tuple[Drift, ...]
) -> tuple[Drift, ...]:
    """Adapter drifts, plus any owned key neither re-read nor declared non-re-readable."""
    seen = {d.key for d in reported}
    missing = tuple(
        Drift(key=k, expected=v, observed=None)
        for k, v in sorted(generated.values.items())
        if k not in effective.values and k not in generated.unreadable and k not in seen
    )
    return reported + missing


async def observe_status(
    adapter: EngineAdapter,
    ref: InstanceRef,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    timeout_s: float | None = None,
) -> InstanceStatus:
    """Engine unreachable -> `unknown`, never `running` (I1, I5). A silent engine raises
    EngineUnreachable, or does not answer within the delay; both give an unknown status."""
    try:
        async with asyncio.timeout(timeout_s):
            return await adapter.status(ref)
    except (EngineUnreachable, TimeoutError):
        return InstanceStatus(state="unknown", mode=None, observed_at=clock())
