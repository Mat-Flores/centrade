"""Protocol EngineAdapter (SPEC §7), asynchrone ; les commandes sont idempotentes."""

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

if TYPE_CHECKING:  # events importe engine.types : évite le cycle
    from centrade_core.events import CanonicalEvent


class EngineUnreachable(Exception):
    """Le moteur ne répond pas (silence, plantage, délai). L'appelant en déduit `unknown`."""


class CommandRejected(Exception):
    """Commande impossible dans l'état actuel (ex. reprendre les entrées d'une instance arrêtée)."""


class StaticChecks(Protocol):
    """Contrôles purs (ni réseau ni Docker) : le registre les exécute à l'écriture d'une version."""

    def validate(self, manifest: Manifest, params: dict[str, Any]) -> ValidationResult: ...
    def check_source(self, manifest: Manifest, source: str) -> ValidationResult: ...


class EngineAdapter(StaticChecks, Protocol):
    def capabilities(self) -> Capabilities: ...
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
    # Mode effectif (I3) : `status().mode`, relu dans le moteur, jamais recopié de la demande.
    async def effective_config(self, ref: InstanceRef) -> EffectiveConfig: ...

    def config_drift(  # pure
        self, generated: EngineConfig, effective: EffectiveConfig
    ) -> tuple[Drift, ...]:
        """Écarts entre la relecture et la configuration générée, sur les clés relues. Le worker
        ne compare rien lui-même : il ajoute seulement les clés manquantes (`owned_drifts`)."""
        ...

    async def snapshot(self, ref: InstanceRef) -> Snapshot: ...
    def events(self, ref: InstanceRef) -> AsyncIterator[CanonicalEvent]: ...
    async def backtest(self, spec: BacktestSpec) -> BacktestResult: ...


class InstanceRuntime(Protocol):
    """Ce qu'un adaptateur à conteneurs demande au worker : fichiers et identifiants de l'API
    native d'une instance. Les identifiants sont des jetons aléatoires propres à l'instance,
    stockés par le SecretStore (usage `engine_api`) ; aucune clé de venue ne passe par ici."""

    def container_user(self) -> str:
        """`uid:gid` sous lequel lancer le conteneur pour qu'il lise ses fichiers (0400)."""
        ...

    async def issue_credentials(
        self, instance_id: UUID, names: tuple[str, ...]
    ) -> dict[str, SecretStr]:
        """À chaque déploiement : un jeton neuf par nom ; les précédents sont détruits."""
        ...

    async def credentials(self, instance_id: UUID) -> dict[str, SecretStr]:
        """Ceux du dernier déploiement (après un redémarrage du worker). `LookupError` sinon."""
        ...

    async def write_files(
        self, instance_id: UUID, files: Mapping[str, str], credentials: Mapping[str, Any]
    ) -> Path:
        """Écrit `files` (nom simple -> texte) et le fichier d'identifiants (JSON de
        `credentials`, forme choisie par l'adaptateur) dans le sous-dossier de l'instance.
        Rend ce dossier, à monter en lecture seule."""
        ...

    async def cleanup(self, instance_id: UUID) -> None:
        """À l'arrêt : retire le fichier d'identifiants. Sans effet s'il n'existe pas."""
        ...


def owned_drifts(
    generated: EngineConfig, effective: EffectiveConfig, reported: tuple[Drift, ...]
) -> tuple[Drift, ...]:
    """Écarts de l'adaptateur, plus toute clé possédée ni relue ni déclarée non relisible."""
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
    """Moteur injoignable -> `unknown`, jamais `running` (I1, I5). Un moteur muet lève
    EngineUnreachable, ou ne répond pas dans le délai ; les deux donnent un statut inconnu."""
    try:
        async with asyncio.timeout(timeout_s):
            return await adapter.status(ref)
    except (EngineUnreachable, TimeoutError):
        return InstanceStatus(state="unknown", mode=None, observed_at=clock())
