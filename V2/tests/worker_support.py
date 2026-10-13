"""Aides des tests du worker : lectures en base et doublures qui notent ce qu'elles reçoivent."""

from typing import Any
from uuid import UUID

from centrade_core.models.trading import Alert, Command, Instance
from centrade_worker.runner import RunnerContainer
from centrade_worker.testing import World
from sqlalchemy import select

# Tout ce qui agit sur un moteur. Les lectures (statut, instantané, configuration) n'y sont pas.
ACTIONS = (
    "deploy",
    "start",
    "stop",
    "pause_entries",
    "resume_entries",
    "flatten",
    "close_position",
    "cancel_entry_order",
)


def spy(engine: Any) -> list[str]:
    """Note chaque action reçue par le moteur, puis la laisse s'exécuter."""
    calls: list[str] = []

    def wrap(name: str) -> None:
        real = getattr(engine, name)

        async def call(*args: Any) -> Any:
            calls.append(name)
            return await real(*args)

        setattr(engine, name, call)

    for name in ACTIONS:
        wrap(name)
    return calls


class RunnerDouble:
    """Runner doublé : rend les conteneurs qu'on lui donne et note chaque appel."""

    def __init__(self, containers: list[RunnerContainer] | None = None) -> None:
        self.containers = containers or []
        self.calls: list[str] = []
        self.error: Exception | None = None

    async def adopt(self) -> list[RunnerContainer]:
        self.calls.append("adopt")
        if self.error is not None:
            raise self.error
        return list(self.containers)

    def __getattr__(self, name: str) -> Any:  # create, start, stop, remove… : jamais attendus
        async def unexpected(*_: Any, **__: Any) -> None:
            self.calls.append(name)

        return unexpected


def container(instance_id: UUID, fingerprint: str, ident: str = "c0ffee" * 4) -> RunnerContainer:
    return RunnerContainer(
        container_id=ident,
        instance_id=instance_id,
        status="running",
        started_at="2026-10-10T11:00:00Z",
        fingerprint=fingerprint,
        mode="paper",
    )


async def alerts(w: World, target_id: UUID | str, rule: str | None = None) -> list[Alert]:
    async with w.sessions() as s:
        stmt = select(Alert).where(Alert.target_id == UUID(str(target_id)))
        if rule is not None:
            stmt = stmt.where(Alert.rule == rule)
        return list(await s.scalars(stmt.order_by(Alert.created_at, Alert.id)))


async def commands(w: World, instance_id: UUID | str, type_: str | None = None) -> list[Command]:
    async with w.sessions() as s:
        stmt = select(Command).where(Command.instance_id == UUID(str(instance_id)))
        if type_ is not None:
            stmt = stmt.where(Command.type == type_)
        return list(await s.scalars(stmt.order_by(Command.requested_at, Command.id)))


async def instance(w: World, instance_id: UUID | str) -> Instance:
    async with w.sessions() as s:
        return await s.get_one(Instance, UUID(str(instance_id)))
