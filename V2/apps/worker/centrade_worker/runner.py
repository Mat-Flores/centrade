"""Docker runner: the only code that talks to Docker, through the socket proxy (SPEC §13, F9).

It knows no engine: image, digest, command, reservations. Every container is born from the same
template (`_template`), never from a caller setting. No platform stop touches a container (I9);
only `remove`, explicitly requested, deletes one.
Sources: https://docker-py.readthedocs.io/en/stable/containers.html
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import tarfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

import docker
import requests
from centrade_core.engine.contract import CommandRejected, EngineUnreachable
from docker.errors import (
    APIError,
    DockerException,
    ImageNotFound,
    NotFound,
)
from docker.types import Mount

LABEL_INSTANCE = "centrade.instance"
LABEL_FINGERPRINT = "centrade.fingerprint"
LABEL_MODE = "centrade.mode"

DATA_PATH = "/data"  # instance data volume, writable
# A new volume belongs to root: the runner creates this subfolder there under the container
# user's name, the only place where an unprivileged engine can write (volume root: nothing).
DATA_SUBDIR = "engine"
FILES_PATH = "/run/centrade"  # configuration, strategy, credentials: read-only
ENV_ALLOWED = frozenset({"TZ", "PYTHONUNBUFFERED"})  # never a secret in a variable (I12)
_ACTIVE = ("running", "created", "restarting", "paused")  # states that occupy memory
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_IMAGE = re.compile(r"[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?")
_USER = re.compile(r"([1-9][0-9]*):([1-9][0-9]*)")  # neither uid 0 nor gid 0
_T = TypeVar("_T")


@dataclass(frozen=True)
class ContainerSpec:
    instance_id: UUID
    image: str  # `repo` or `repo:tag`, without digest
    digest: str  # sha256:… from the `engines` table
    command: tuple[str, ...]
    files_dir: Path  # must be `<runtime_dir>/<instance_id>`
    mode: str
    fingerprint: str
    memory_bytes: int
    nano_cpus: int
    env: Mapping[str, str] = field(default_factory=dict)
    user: str = "1000:1000"  # numeric uid:gid, non-zero


@dataclass(frozen=True)
class RunnerContainer:
    container_id: str
    instance_id: UUID
    status: str
    started_at: str  # Docker's StartedAt, as is: it proves there was no restart
    fingerprint: str
    mode: str


_Views = list[RunnerContainer]  # `list` is also a runner method


def _name(instance_id: UUID) -> str:
    return f"centrade-engine-{instance_id}"


def _own_data_subdir(container: Any, user: str) -> None:
    uid, gid = (int(x) for x in user.split(":"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(DATA_SUBDIR)
        info.type, info.mode, info.uid, info.gid = tarfile.DIRTYPE, 0o700, uid, gid
        tar.addfile(info)
    # No effect on an already existing folder: a restarted instance's content stays intact.
    if not container.put_archive(DATA_PATH, buf.getvalue()):
        raise CommandRejected("volume de données : dossier du moteur non créé")


def _view(c: Any) -> RunnerContainer:
    labels = c.attrs["Config"]["Labels"]
    return RunnerContainer(
        container_id=c.id,
        instance_id=UUID(labels[LABEL_INSTANCE]),
        status=c.attrs["State"]["Status"],
        started_at=c.attrs["State"]["StartedAt"],
        fingerprint=labels.get(LABEL_FINGERPRINT, ""),
        mode=labels.get(LABEL_MODE, ""),
    )


class DockerRunner:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        runtime_dir: Path | None = None,
        network: str | None = None,
        host_memory_mb: int | None = None,
        client: Any = None,
    ) -> None:
        self._base_url = base_url or os.environ.get("DOCKER_HOST", "")
        if client is None and not self._base_url.startswith("tcp://"):
            raise ValueError(
                "DOCKER_HOST doit viser le socket proxy (tcp://…), jamais le socket brut"
            )
        self._runtime_dir = runtime_dir or Path(
            os.environ.get("ENGINE_RUNTIME_DIR", "/run/centrade")
        )
        self._network = network or os.environ.get("ENGINE_NETWORK", "centrade_engines")
        mem = (
            host_memory_mb
            if host_memory_mb is not None
            else os.environ.get("ENGINE_HOST_MEMORY_MB")
        )
        self._host_memory_bytes = int(mem) * 1024 * 1024 if mem else None
        self._client = client

    # --- Docker access ------------------------------------------------------------------------

    def _cli(self) -> Any:
        if self._client is None:
            self._client = docker.DockerClient(base_url=self._base_url, timeout=15)
        return self._client

    async def _call(self, fn: Callable[[Any], _T]) -> _T:
        """Synchronous SDK call outside the loop; errors translated to the contract."""

        def run() -> _T:
            return fn(self._cli())

        try:
            return await asyncio.to_thread(run)
        except ImageNotFound as exc:
            raise CommandRejected(
                "image absente ou digest différent : aucun téléchargement"
            ) from exc
        except APIError as exc:
            if exc.status_code is not None and exc.status_code >= 500:
                raise EngineUnreachable(f"Docker : {exc.explanation or exc}") from exc
            raise CommandRejected(f"Docker a refusé : {exc.explanation or exc}") from exc
        except (DockerException, requests.RequestException, OSError) as exc:
            raise EngineUnreachable(f"Docker injoignable : {type(exc).__name__}") from exc

    # --- template -----------------------------------------------------------------------------

    def _template(self, spec: ContainerSpec) -> dict[str, Any]:
        """The only engine container template (§13). Validates input, refuses at any doubt."""
        if not _DIGEST.fullmatch(spec.digest) or not _IMAGE.fullmatch(spec.image):
            raise CommandRejected(
                "image ou digest mal formé (attendu dépôt[:tag] et sha256:64 hex)"
            )
        if not _USER.fullmatch(spec.user):
            raise CommandRejected("utilisateur du conteneur : uid:gid numériques, non nuls")
        if spec.memory_bytes <= 0 or spec.nano_cpus <= 0:  # 0 = unlimited for Docker
            raise CommandRejected("plafonds de mémoire et de CPU obligatoires")
        if not spec.command or not spec.mode or not spec.fingerprint:
            raise CommandRejected("commande, mode et empreinte obligatoires")
        if extra := set(spec.env) - ENV_ALLOWED:
            raise CommandRejected(f"variables d'environnement refusées : {sorted(extra)}")
        expected = self._runtime_dir / str(spec.instance_id)
        if spec.files_dir.resolve() != expected.resolve() or not expected.is_dir():
            raise CommandRejected(
                "seul le sous-dossier de l'instance du répertoire d'exécution se monte"
            )
        name = _name(spec.instance_id)
        return {
            "image": f"{spec.image}@{spec.digest}",  # the daemon refuses a digest it does not have
            "command": list(spec.command),
            "name": name,
            "user": spec.user,
            "environment": dict(spec.env),
            "labels": {
                LABEL_INSTANCE: str(spec.instance_id),
                LABEL_FINGERPRINT: spec.fingerprint,
                LABEL_MODE: spec.mode,
            },
            "read_only": True,
            "tmpfs": {"/tmp": "rw,noexec,nosuid,size=64m"},  # noqa: S108 (container tmpfs)
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "privileged": False,
            "mem_limit": spec.memory_bytes,
            "memswap_limit": spec.memory_bytes,  # no swap
            "nano_cpus": spec.nano_cpus,
            "pids_limit": 256,
            "restart_policy": {"Name": "on-failure", "MaximumRetryCount": 3},
            "network_mode": self._network,
            "mounts": [
                Mount(DATA_PATH, f"centrade-data-{spec.instance_id}", type="volume"),
                Mount(FILES_PATH, str(expected), type="bind", read_only=True),
            ],
        }

    async def _admit(self, new_bytes: int) -> None:
        """Refuse if reserved memory would exceed the host's, or if unknown (I5)."""

        def reserved(cli: Any) -> tuple[int, int | None]:
            total: int | None = None
            try:
                total = int(cli.info()["MemTotal"])
            except (APIError, KeyError, ValueError):  # proxy without `info`: a parameter
                pass
            used = 0
            for c in cli.containers.list(all=True, filters={"label": LABEL_INSTANCE}):
                c.reload()
                if c.attrs["State"]["Status"] in _ACTIVE:
                    used += int(c.attrs["HostConfig"]["Memory"])
            return used, total

        used, total = await self._call(reserved)
        total = total or self._host_memory_bytes
        if not total:
            raise CommandRejected("mémoire de l'hôte illisible : création refusée")
        if used + new_bytes > total:
            raise CommandRejected(
                f"mémoire réservée insuffisante : {used + new_bytes} octets demandés pour {total}"
            )

    # --- operations ---------------------------------------------------------------------------

    async def create(self, spec: ContainerSpec) -> RunnerContainer:
        kwargs = self._template(spec)
        await self._admit(spec.memory_bytes)

        def go(cli: Any) -> RunnerContainer:
            image = kwargs.pop("image")
            c = cli.containers.create(image, **kwargs)  # `create` never downloads
            try:
                _own_data_subdir(c, spec.user)
            except BaseException:
                c.remove(v=False)  # no half-prepared container
                raise
            c.reload()
            return _view(c)

        return await self._call(go)

    async def start(self, instance_id: UUID) -> RunnerContainer:
        def go(cli: Any) -> RunnerContainer:
            try:
                c = cli.containers.get(_name(instance_id))
            except NotFound as exc:
                raise CommandRejected("conteneur absent") from exc
            c.start()  # already running: Docker answers 304, no error
            c.reload()
            return _view(c)

        return await self._call(go)

    async def stop(self, instance_id: UUID, timeout_s: int = 30) -> None:
        """Stops an already stopped or absent container without error."""

        def go(cli: Any) -> None:
            try:
                cli.containers.get(_name(instance_id)).stop(timeout=timeout_s)
            except NotFound:
                pass

        await self._call(go)

    async def remove(self, instance_id: UUID) -> None:
        """Removes the instance's stopped container; never the data volume."""

        def go(cli: Any) -> None:
            try:
                c = cli.containers.get(_name(instance_id))
            except NotFound:
                return
            if LABEL_INSTANCE not in c.attrs["Config"]["Labels"]:
                raise CommandRejected("conteneur non étiqueté : jamais supprimé")
            c.remove(v=False)  # no force: a running container stays

        await self._call(go)

    async def inspect(self, instance_id: UUID) -> RunnerContainer | None:
        def go(cli: Any) -> RunnerContainer | None:
            try:
                return _view(cli.containers.get(_name(instance_id)))
            except NotFound:
                return None

        return await self._call(go)

    async def list(self) -> _Views:
        def go(cli: Any) -> _Views:
            found = cli.containers.list(all=True, filters={"label": LABEL_INSTANCE})
            out = []
            for c in found:
                c.reload()
                out.append(_view(c))
            return out

        return await self._call(go)

    async def adopt(self) -> _Views:
        """Labelled running containers, returned as is: neither restarted nor modified."""
        return [c for c in await self.list() if c.status == "running"]
