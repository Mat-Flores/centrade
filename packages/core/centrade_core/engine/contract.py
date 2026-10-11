"""Protocol EngineAdapter (SPEC §7), asynchrone ; les commandes sont idempotentes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from centrade_core.engine.types import (
    BacktestResult,
    BacktestSpec,
    Capabilities,
    EffectiveConfig,
    EngineConfig,
    InstanceRef,
    InstanceSpec,
    InstanceStatus,
    Manifest,
    Snapshot,
    ValidationResult,
)

if TYPE_CHECKING:  # events importe engine.types : évite le cycle
    from centrade_core.events import CanonicalEvent


class EngineUnreachable(Exception):
    """Le moteur ne répond pas (silence, plantage, délai). L'appelant en déduit `unknown`."""


class CommandRejected(Exception):
    """Commande impossible dans l'état actuel (ex. reprendre les entrées d'une instance arrêtée)."""


class EngineAdapter(Protocol):
    def capabilities(self) -> Capabilities: ...
    def validate(self, manifest: Manifest, params: dict[str, Any]) -> ValidationResult: ...
    def render_config(self, spec: InstanceSpec) -> EngineConfig: ...  # pure
    async def deploy(self, spec: InstanceSpec) -> InstanceRef: ...  # sorties seules
    async def start(self, ref: InstanceRef) -> None: ...  # relance, sorties seules
    async def stop(self, ref: InstanceRef) -> None: ...
    async def pause_entries(self, ref: InstanceRef) -> None: ...
    async def resume_entries(self, ref: InstanceRef) -> None: ...
    async def flatten(self, ref: InstanceRef) -> None: ...
    async def close_position(self, ref: InstanceRef, position_id: str) -> None: ...
    async def cancel_entry_order(self, ref: InstanceRef, order_id: str) -> None: ...
    async def status(self, ref: InstanceRef) -> InstanceStatus: ...
    async def effective_config(self, ref: InstanceRef) -> EffectiveConfig: ...
    async def snapshot(self, ref: InstanceRef) -> Snapshot: ...
    def events(self, ref: InstanceRef) -> AsyncIterator[CanonicalEvent]: ...
    async def backtest(self, spec: BacktestSpec) -> BacktestResult: ...


async def observe_status(
    adapter: EngineAdapter,
    ref: InstanceRef,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    timeout_s: float | None = None,
) -> InstanceStatus:
    """Moteur injoignable -> `unknown`, jamais `running` (I1, I5). Un moteur muet lève
    EngineUnreachable, ou ne répond pas dans le délai ; les deux donnent un statut inconnu."""
    try:
        async with asyncio.timeout(timeout_s):
            return await adapter.status(ref)
    except (EngineUnreachable, TimeoutError):
        return InstanceStatus(state="unknown", mode=None, observed_at=clock())
