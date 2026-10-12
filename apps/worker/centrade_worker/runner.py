"""Runner Docker : seul code qui parle à Docker, par le socket proxy (SPEC §13, F9).

Il ne connaît aucun moteur : image, digest, commande, réservations. Tout conteneur naît du même
gabarit (`_template`), jamais d'un réglage de l'appelant. Aucun arrêt de la plateforme ne touche
un conteneur (I9) ; seul `remove`, demandé explicitement, en supprime un.
Sources : https://docker-py.readthedocs.io/en/stable/containers.html
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

import requests
from centrade_core.engine.contract import CommandRejected, EngineUnreachable
from docker.errors import (  # type: ignore[import-not-found]
    APIError,
    DockerException,
    ImageNotFound,
    NotFound,
)
from docker.types import Mount  # type: ignore[import-not-found]

import docker

LABEL_INSTANCE = "centrade.instance"
LABEL_FINGERPRINT = "centrade.fingerprint"
LABEL_MODE = "centrade.mode"

DATA_PATH = "/data"  # volume de données de l'instance, en écriture
# Un volume neuf appartient à root : le runner y crée ce sous-dossier au nom de l'utilisateur du
# conteneur, seul endroit où un moteur sans privilège peut écrire (racine du volume : rien).
DATA_SUBDIR = "engine"
FILES_PATH = "/run/centrade"  # configuration, stratégie, identifiants : lecture seule
ENV_ALLOWED = frozenset({"TZ", "PYTHONUNBUFFERED"})  # jamais de secret en variable (I12)
_ACTIVE = ("running", "created", "restarting", "paused")  # états qui occupent de la mémoire
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_IMAGE = re.compile(r"[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?")
_USER = re.compile(r"([1-9][0-9]*):([1-9][0-9]*)")  # ni uid 0 ni gid 0
_T = TypeVar("_T")


@dataclass(frozen=True)
class ContainerSpec:
    instance_id: UUID
    image: str  # `dépôt` ou `dépôt:tag`, sans digest
    digest: str  # sha256:… de la table `engines`
    command: tuple[str, ...]
    files_dir: Path  # doit être `<runtime_dir>/<instance_id>`
    mode: str
    fingerprint: str
    memory_bytes: int
    nano_cpus: int
    env: Mapping[str, str] = field(default_factory=dict)
    user: str = "1000:1000"  # uid:gid numériques, non nuls


@dataclass(frozen=True)
class RunnerContainer:
    container_id: str
    instance_id: UUID
    status: str
    started_at: str  # StartedAt de Docker, tel quel : il prouve l'absence de redémarrage
    fingerprint: str
    mode: str


_Views = list[RunnerContainer]  # `list` est aussi une méthode du runner


def _name(instance_id: UUID) -> str:
    return f"centrade-engine-{instance_id}"


def _own_data_subdir(container: Any, user: str) -> None:
    uid, gid = (int(x) for x in user.split(":"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(DATA_SUBDIR)
        info.type, info.mode, info.uid, info.gid = tarfile.DIRTYPE, 0o700, uid, gid
        tar.addfile(info)
    # Sans effet sur un dossier déjà là : le contenu d'une instance relancée reste intact.
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

    # --- accès Docker -------------------------------------------------------------------------

    def _cli(self) -> Any:
        if self._client is None:
            self._client = docker.DockerClient(  # type: ignore[attr-defined]
                base_url=self._base_url, timeout=15
            )
        return self._client

    async def _call(self, fn: Callable[[Any], _T]) -> _T:
        """Appel synchrone du SDK hors de la boucle ; erreurs traduites vers le contrat."""

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

    # --- gabarit ------------------------------------------------------------------------------

    def _template(self, spec: ContainerSpec) -> dict[str, Any]:
        """Seul gabarit de conteneur de moteur (§13). Valide l'entrée, refuse au moindre doute."""
        if not _DIGEST.fullmatch(spec.digest) or not _IMAGE.fullmatch(spec.image):
            raise CommandRejected(
                "image ou digest mal formé (attendu dépôt[:tag] et sha256:64 hex)"
            )
        if not _USER.fullmatch(spec.user):
            raise CommandRejected("utilisateur du conteneur : uid:gid numériques, non nuls")
        if spec.memory_bytes <= 0 or spec.nano_cpus <= 0:  # 0 = illimité pour Docker
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
            "image": f"{spec.image}@{spec.digest}",  # le démon refuse un digest qu'il n'a pas
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
            "tmpfs": {"/tmp": "rw,noexec,nosuid,size=64m"},  # noqa: S108 (tmpfs du conteneur)
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "privileged": False,
            "mem_limit": spec.memory_bytes,
            "memswap_limit": spec.memory_bytes,  # pas de swap
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
        """Refus si la mémoire réservée dépasserait celle de l'hôte, ou si on ne sait pas (I5)."""

        def reserved(cli: Any) -> tuple[int, int | None]:
            total: int | None = None
            try:
                total = int(cli.info()["MemTotal"])
            except (APIError, KeyError, ValueError):  # proxy sans `info` : paramètre
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

    # --- opérations ---------------------------------------------------------------------------

    async def create(self, spec: ContainerSpec) -> RunnerContainer:
        kwargs = self._template(spec)
        await self._admit(spec.memory_bytes)

        def go(cli: Any) -> RunnerContainer:
            image = kwargs.pop("image")
            c = cli.containers.create(image, **kwargs)  # `create` ne télécharge jamais
            try:
                _own_data_subdir(c, spec.user)
            except BaseException:
                c.remove(v=False)  # pas de conteneur à moitié préparé
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
            c.start()  # déjà en marche : Docker répond 304, sans erreur
            c.reload()
            return _view(c)

        return await self._call(go)

    async def stop(self, instance_id: UUID, timeout_s: int = 30) -> None:
        """Arrête un conteneur déjà arrêté ou absent sans erreur."""

        def go(cli: Any) -> None:
            try:
                cli.containers.get(_name(instance_id)).stop(timeout=timeout_s)
            except NotFound:
                pass

        await self._call(go)

    async def remove(self, instance_id: UUID) -> None:
        """Supprime le conteneur arrêté de l'instance ; jamais le volume de données."""

        def go(cli: Any) -> None:
            try:
                c = cli.containers.get(_name(instance_id))
            except NotFound:
                return
            if LABEL_INSTANCE not in c.attrs["Config"]["Labels"]:
                raise CommandRejected("conteneur non étiqueté : jamais supprimé")
            c.remove(v=False)  # sans force : un conteneur en marche reste

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
        """Conteneurs étiquetés en marche, rendus tels quels : ni redémarrés ni modifiés."""
        return [c for c in await self.list() if c.status == "running"]
