"""Runner contre le Docker local, derrière un vrai socket proxy configuré comme engines.yml."""
# ruff: noqa: ASYNC210 (sondes HTTP brèves vers le proxy local)

from uuid import uuid4

import pytest
import requests
from centrade_core.engine.contract import CommandRejected

from runner.support import BUSYBOX_DIGEST, Stack, docker_stack, needs_docker  # noqa: F401

pytestmark = [pytest.mark.docker, needs_docker]


async def test_full_lifecycle_through_the_container_template(docker_stack: Stack) -> None:  # noqa: F811
    runner = docker_stack.runner()
    spec = docker_stack.spec()
    created = await runner.create(spec)
    attrs = docker_stack.raw.containers.get(created.container_id).attrs
    host = attrs["HostConfig"]
    assert attrs["Config"]["User"] == "10001:10001"
    assert host["ReadonlyRootfs"] is True
    assert host["CapDrop"] == ["ALL"] and not host["CapAdd"]
    assert host["SecurityOpt"] == ["no-new-privileges:true"]
    assert host["Privileged"] is False
    assert host["Memory"] == spec.memory_bytes and host["NanoCpus"] == spec.nano_cpus
    assert host["PidsLimit"] == 256
    assert host["RestartPolicy"] == {"Name": "on-failure", "MaximumRetryCount": 3}
    assert host["NetworkMode"] == docker_stack.network
    assert not host["PortBindings"] and not attrs["NetworkSettings"]["Ports"]
    assert list(attrs["NetworkSettings"]["Networks"]) == [docker_stack.network]
    assert attrs["Config"]["Labels"]["centrade.instance"] == str(spec.instance_id)
    assert attrs["Config"]["Labels"]["centrade.mode"] == "paper"
    assert attrs["Config"]["Labels"]["centrade.fingerprint"] == "f" * 64
    by_dest = {m["Destination"]: m for m in attrs["Mounts"]}
    assert set(by_dest) == {"/data", "/run/centrade"}
    assert by_dest["/run/centrade"]["RW"] is False and by_dest["/data"]["RW"] is True

    started = await runner.start(spec.instance_id)
    assert started.status == "running"
    again = await runner.start(spec.instance_id)
    assert again.started_at == started.started_at  # démarrer un conteneur en marche : sans effet

    await runner.stop(spec.instance_id, timeout_s=2)
    await runner.stop(spec.instance_id, timeout_s=2)
    stopped = await runner.inspect(spec.instance_id)
    assert stopped is not None and stopped.status == "exited"
    await runner.remove(spec.instance_id)
    assert await runner.inspect(spec.instance_id) is None
    await runner.remove(spec.instance_id)


async def test_adoption_by_a_new_instance_leaves_containers_running(docker_stack: Stack) -> None:  # noqa: F811
    first = docker_stack.runner()
    spec = docker_stack.spec()
    await first.create(spec)
    before = await first.start(spec.instance_id)
    adopted = {c.instance_id: c for c in await docker_stack.runner().adopt()}
    assert adopted[spec.instance_id].started_at == before.started_at
    assert adopted[spec.instance_id].fingerprint == "f" * 64
    after = await docker_stack.runner().inspect(spec.instance_id)
    assert after is not None and after.started_at == before.started_at
    await first.stop(spec.instance_id, timeout_s=2)
    await first.remove(spec.instance_id)


async def test_different_digest_is_rejected_without_pulling(docker_stack: Stack) -> None:  # noqa: F811
    spec = docker_stack.spec(digest="sha256:" + "0" * 64)
    with pytest.raises(CommandRejected):
        await docker_stack.runner().create(spec)
    assert await docker_stack.runner().inspect(spec.instance_id) is None


async def test_admission_is_rejected_beyond_host_memory(docker_stack: Stack) -> None:  # noqa: F811
    host = docker_stack.raw.info()["MemTotal"]
    spec = docker_stack.spec(memory_bytes=host + 1)
    with pytest.raises(CommandRejected, match="insuffisante"):
        await docker_stack.runner().create(spec)


async def test_stopping_a_missing_container_does_not_fail(docker_stack: Stack) -> None:  # noqa: F811
    await docker_stack.runner().stop(uuid4())


async def test_socket_proxy_rejects_everything_but_containers(docker_stack: Stack) -> None:  # noqa: F811
    base = docker_stack.proxy_url.replace("tcp://", "http://")
    runner = docker_stack.runner()
    spec = docker_stack.spec()
    created = await runner.create(spec)
    await runner.start(spec.instance_id)
    cid = created.container_id
    allowed = [("GET", "/containers/json"), ("GET", "/info"), ("GET", f"/containers/{cid}/json")]
    for method, path in allowed:
        assert requests.request(method, base + path, timeout=10).status_code == 200, path
    denied = [
        ("GET", "/images/json"),
        ("POST", "/images/create?fromImage=busybox&tag=latest"),
        ("POST", "/build"),
        ("GET", "/volumes"),
        ("POST", "/volumes/create"),
        ("GET", "/secrets"),
        ("GET", "/swarm"),
        ("GET", "/networks"),
        ("GET", "/system/df"),
        ("POST", "/exec/abc/start"),
        ("GET", "/events"),
    ]
    # La création d'un exec relève de /containers (le proxy ne la distingue pas) ; son démarrage,
    # seul moment où une commande s'exécute, est refusé.
    made = requests.post(f"{base}/containers/{cid}/exec", json={"Cmd": ["id"]}, timeout=10)
    assert (
        requests.post(f"{base}/exec/{made.json()['Id']}/start", json={}, timeout=10).status_code
        == 403
    )
    for method, path in denied:
        assert requests.request(method, base + path, timeout=10).status_code == 403, path
    await runner.stop(spec.instance_id, timeout_s=2)
    await runner.remove(spec.instance_id)
