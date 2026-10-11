"""I4, côté commandes : ce qui réduit le risque part toujours vers le moteur, quelle que soit la
panne de la plateforme (worker longtemps absent, bus en panne, autre instance en erreur)."""

from datetime import datetime
from typing import Any

import httpx
import pytest
from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.bus import Bus
from centrade_fake.engine import Failure
from centrade_worker.worker import Worker
from redis.exceptions import ConnectionError as RedisConnectionError

REDUCTIONS = {"pause-entries": "exits_only", "flatten": "running", "stop": "stopped"}


async def _running(stack: Stack, **params: object) -> tuple[httpx.AsyncClient, str]:
    c = await stack.client("operator")
    inst = await create_instance(c, **params)
    await stack.world.worker.run_once()
    assert (await act(c, inst["id"], "resume-entries")).status_code == 202
    await stack.world.worker.run_once()
    assert (await get(c, f"/api/v1/instances/{inst['id']}"))["state"]["value"] == "running"
    return c, str(inst["id"])


class _RedisEnPanne:
    """Tout appel échoue comme un Redis injoignable."""

    def __getattr__(self, name: str) -> Any:
        async def boom(*_: object, **__: object) -> None:
            raise RedisConnectionError("bus en panne")

        return boom


@pytest.mark.parametrize("action", sorted(REDUCTIONS))
async def test_i04_commande_de_reduction_n_expire_jamais_avant_l_envoi(
    stack: Stack, action: str
) -> None:
    c, iid = await _running(stack)
    cid = (await act(c, iid, action)).json()["command_id"]

    stack.world.clock.advance(600)  # worker absent bien au-delà de toute échéance
    await stack.world.worker.run_once()

    cmd = await get(c, f"/api/v1/commands/{cid}")
    assert cmd["dispatched_at"] is not None and cmd["status"] == "verified", cmd
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == REDUCTIONS[action]
    # L'échéance mesure l'effet, à compter de l'envoi.
    assert datetime.fromisoformat(cmd["deadline_at"]) > datetime.fromisoformat(cmd["dispatched_at"])


async def test_i04_echeance_de_la_pause_court_depuis_l_envoi(stack: Stack) -> None:
    c, iid = await _running(stack, failures=["ignore_pause"])
    cid = (await act(c, iid, "pause-entries")).json()["command_id"]
    w = stack.world

    w.clock.advance(600)
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "acknowledged"  # envoyée

    w.clock.advance(stack.settings.deadline_pause_entries_s + 1)  # sans effet : expire, et se voit
    await w.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{cid}")
    assert cmd["status"] == "timed_out" and cmd["dispatched_at"] is not None


async def test_i04_panne_du_bus_n_empeche_ni_l_envoi_ni_le_releve(stack: Stack) -> None:
    c, iid = await _running(stack)
    w = stack.world
    broken: Any = _RedisEnPanne()
    w.worker = Worker(
        adapters={"fake": w.fake},
        sessions=w.sessions,
        redis=broken,
        bus=Bus(broken, "worker", "w1"),
        clock=w.clock,
    )
    w.worker.register(ref_of(iid))
    cid = (await act(c, iid, "pause-entries")).json()["command_id"]
    w.clock.advance(1)

    with pytest.raises(RedisConnectionError):  # la panne reste visible : pas de battement
        await w.worker.run_once()

    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "verified"
    inst = await get(c, f"/api/v1/instances/{iid}")
    assert inst["state"]["value"] == "exits_only"
    assert datetime.fromisoformat(inst["state"]["observed_at"]) == w.clock.now  # relevé du tour


async def test_i04_erreur_sur_une_instance_n_empeche_pas_les_autres(stack: Stack) -> None:
    c, broken_id = await _running(stack)
    healthy = (await create_instance(c))["id"]
    w = stack.world
    await w.worker.run_once()
    assert (await act(c, healthy, "resume-entries")).status_code == 202
    await w.worker.run_once()

    real = w.fake.status

    async def status(ref: Any) -> Any:
        if str(ref.instance_id) == broken_id:
            raise RuntimeError("adaptateur en erreur")
        return await real(ref)

    w.fake.status = status  # type: ignore[method-assign]
    cid = (await act(c, healthy, "pause-entries")).json()["command_id"]
    w.clock.advance(1)
    with pytest.raises(RuntimeError, match="adaptateur en erreur"):
        await w.worker.run_once()

    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "verified"
    inst = await get(c, f"/api/v1/instances/{healthy}")
    assert inst["state"]["value"] == "exits_only"
    assert datetime.fromisoformat(inst["state"]["observed_at"]) == w.clock.now


async def test_i04_echec_d_ecriture_pour_une_commande_n_empeche_pas_d_envoyer_les_autres(
    stack: Stack,
) -> None:
    c, first = await _running(stack)
    second = (await create_instance(c))["id"]
    w = stack.world
    await w.worker.run_once()
    assert (await act(c, second, "resume-entries")).status_code == 202
    await w.worker.run_once()
    for iid in (first, second):
        assert (await act(c, iid, "pause-entries")).status_code == 202

    commands = w.worker._commands
    real, calls = commands._finish, 0

    async def finish(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("écriture impossible")
        await real(*args, **kwargs)

    commands._finish = finish  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="écriture impossible"):
        await w.worker.run_once()

    for iid in (first, second):  # les deux moteurs ont reçu la pause
        assert (await w.fake.status(ref_of(iid))).state == "exits_only"


async def test_i04_pause_envoyee_meme_si_le_moteur_etait_muet_au_tour_precedent(
    stack: Stack,
) -> None:
    c, iid = await _running(stack)
    w = stack.world
    w.fake.set_failure(ref_of(iid), Failure.SILENT)
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == "unknown"
    w.fake.set_failure(ref_of(iid), Failure.SILENT, on=False)

    r = await act(c, iid, "pause-entries")  # état inconnu : la pause reste acceptée
    assert r.status_code == 202
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{r.json()['command_id']}"))["status"] == "verified"
