"""Docker local pour les tests du runner : vrai socket proxy (celui de engines.yml), réseau et
volumes jetables. Tout ce que ces tests créent est supprimé ; rien d'autre n'est touché."""

import os
import secrets
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import docker
import pytest
import yaml  # type: ignore[import-untyped]
from centrade_worker.runner import ContainerSpec, DockerRunner
from docker.errors import DockerException, NotFound

ROOT = Path(__file__).resolve().parents[2]
BUSYBOX = "busybox:1.37.0"
BUSYBOX_DIGEST = "sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e"

try:
    _probe = docker.from_env(timeout=5)
    _probe.ping()
    DOCKER_OK = True
except DockerException:
    DOCKER_OK = False

needs_docker = pytest.mark.skipif(not DOCKER_OK, reason="Docker local absent")


def engines_service() -> dict[str, Any]:
    doc = yaml.safe_load((ROOT / "deploy" / "compose" / "engines.yml").read_text(encoding="utf-8"))
    service: dict[str, Any] = doc["services"]["docker-socket-proxy"]
    return service


@dataclass
class Stack:
    raw: Any  # client Docker direct, pour préparer et nettoyer seulement
    proxy_url: str
    network: str
    runtime_dir: Path
    ids: list[str]

    def runner(self) -> DockerRunner:
        return DockerRunner(self.proxy_url, runtime_dir=self.runtime_dir, network=self.network)

    def spec(self, **over: Any) -> ContainerSpec:
        iid = uuid4()
        self.ids.append(str(iid))
        (self.runtime_dir / str(iid)).mkdir()
        base = {
            "instance_id": iid,
            "image": "busybox:1.37.0",
            "digest": BUSYBOX_DIGEST,
            "command": ("sleep", "300"),
            "files_dir": self.runtime_dir / str(iid),
            "mode": "paper",
            "fingerprint": "f" * 64,
            "memory_bytes": 64 * 1024 * 1024,
            "nano_cpus": 100_000_000,
            "user": "10001:10001",
        }
        return ContainerSpec(**{**base, **over})


@pytest.fixture(scope="session")
def docker_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    if not DOCKER_OK:
        pytest.skip("Docker local absent")
    raw = docker.from_env(timeout=60)
    tag = secrets.token_hex(4)
    try:
        raw.images.get(f"busybox@{BUSYBOX_DIGEST}")
    except DockerException:
        raw.images.pull(f"busybox@{BUSYBOX_DIGEST}")
    net = raw.networks.create(f"centrade-test-engines-{tag}", internal=True)
    svc = engines_service()
    image = svc["image"]
    try:
        raw.images.get(image)
    except DockerException:
        raw.images.pull(image)
    # Port hôte `None` : Docker en choisit un libre. Les stubs de types ne décrivent pas ce cas.
    proxy = raw.containers.run(  # type: ignore[call-overload]
        image,
        detach=True,
        name=f"centrade-test-proxy-{tag}",
        environment={k: str(v) for k, v in svc["environment"].items()},
        volumes={"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "ro"}},
        ports={"2375/tcp": ("127.0.0.1", None)},
        read_only=svc["read_only"],
        cap_drop=svc["cap_drop"],
        security_opt=svc["security_opt"],
        tmpfs={"/run": "", "/tmp": ""},  # noqa: S108
    )
    ids: list[str] = []
    try:
        for _ in range(50):
            proxy.reload()
            bound = proxy.attrs["NetworkSettings"]["Ports"].get("2375/tcp")
            if proxy.status == "running" and bound:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError(proxy.logs().decode(errors="replace")[-500:])
        port = bound[0]["HostPort"]
        time.sleep(1)
        runtime = tmp_path_factory.mktemp("run-centrade")
        os.chmod(runtime, 0o755)  # noqa: S103 (lu par le démon)
        assert net.name is not None
        yield Stack(raw, f"tcp://127.0.0.1:{port}", net.name, runtime, ids)
    finally:
        for iid in ids:
            for name in (f"centrade-engine-{iid}",):
                try:
                    raw.containers.get(name).remove(force=True)
                except NotFound:
                    pass
            try:
                raw.volumes.get(f"centrade-data-{iid}").remove()
            except NotFound:
                pass
        proxy.remove(force=True)
        net.remove()


@pytest.fixture
def make_stack(docker_stack: Stack) -> Callable[[], Stack]:
    return lambda: docker_stack
