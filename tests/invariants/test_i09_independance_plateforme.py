"""I9 : arrêter ou redémarrer la plateforme ne touche à aucun conteneur de moteur.
Côté runner : l'arrêt du runner (et donc du worker) laisse les conteneurs en marche, et une
nouvelle instance du runner les adopte sans les redémarrer. Docker local requis."""

import pytest
from runner.support import Stack, docker_stack, needs_docker  # noqa: F401

pytestmark = [pytest.mark.docker, needs_docker]


async def test_i09_arret_du_worker_ne_touche_aucun_conteneur(docker_stack: Stack) -> None:  # noqa: F811
    runner = docker_stack.runner()
    spec = docker_stack.spec()
    await runner.create(spec)
    started = await runner.start(spec.instance_id)

    # Arrêt du worker : son client Docker est fermé, il ne reste rien qui pilote le conteneur.
    runner._cli().close()
    del runner

    live = docker_stack.raw.containers.get(f"centrade-engine-{spec.instance_id}")
    live.reload()
    assert live.status == "running"
    assert live.attrs["State"]["StartedAt"] == started.started_at

    await docker_stack.runner().stop(spec.instance_id, timeout_s=2)
    await docker_stack.runner().remove(spec.instance_id)


async def test_i09_adoption_sans_redemarrage(docker_stack: Stack) -> None:  # noqa: F811
    spec = docker_stack.spec()
    old = docker_stack.runner()
    await old.create(spec)
    started = await old.start(spec.instance_id)

    adopted = [c for c in await docker_stack.runner().adopt() if c.instance_id == spec.instance_id]
    assert [(c.status, c.started_at) for c in adopted] == [("running", started.started_at)]
    live = docker_stack.raw.containers.get(f"centrade-engine-{spec.instance_id}")
    assert live.attrs["RestartCount"] == 0

    await old.stop(spec.instance_id, timeout_s=2)
    await old.remove(spec.instance_id)
