"""I8 : une commande n'est « faite » que lorsque son effet est observé (SPEC §1.2, F9)."""

from typing import get_args

import httpx
from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.commands import NEXT, TERMINAL, Status, can_transition
from centrade_fake.engine import Failure
from hypothesis import given
from hypothesis import strategies as st

STATUSES: tuple[str, ...] = get_args(Status)
RANK = {"requested": 0, "dispatched": 1, "acknowledged": 2}


async def _running(stack: Stack, **params: object) -> tuple[httpx.AsyncClient, str]:
    c = await stack.client("operator")
    inst = await create_instance(c, **params)
    w = stack.world
    await w.worker.run_once()
    r = await act(c, inst["id"], "resume-entries")
    assert r.status_code == 202
    await w.worker.run_once()
    return c, inst["id"]


async def test_i08_commande_non_faite_sans_effet_observe(stack: Stack) -> None:
    c, iid = await _running(stack, failures=["ignore_pause"])
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == "running"
    r = await act(c, iid, "pause-entries")
    cid = r.json()["command_id"]

    for _ in range(3):  # le moteur accuse réception mais ne fait rien
        stack.world.clock.advance(2)
        await stack.world.worker.run_once()
        cmd = await get(c, f"/api/v1/commands/{cid}")
        assert cmd["status"] == "acknowledged" and cmd["verified_at"] is None
    inst = await get(c, f"/api/v1/instances/{iid}")
    assert inst["state"]["value"] == "running" and inst["desired_state"] == "exits_only"

    stack.world.clock.advance(stack.settings.deadline_pause_entries_s)
    await stack.world.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "timed_out"


async def test_i08_commande_sans_reponse_passe_timed_out(stack: Stack) -> None:
    c, iid = await _running(stack)
    stack.world.fake.set_failure(ref_of(iid), Failure.SILENT)
    r = await act(c, iid, "flatten")
    cid = r.json()["command_id"]
    await stack.world.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{cid}")
    assert cmd["status"] == "dispatched" and cmd["acknowledged_at"] is None  # ni accusé, ni rejoué

    stack.world.clock.advance(stack.settings.deadline_flatten_s + 1)
    await stack.world.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{cid}")
    assert cmd["status"] == "timed_out" and cmd["timed_out_at"] and cmd["verified_at"] is None
    alerts = await get(c, f"/api/v1/alerts?instance_id={iid}")
    assert any(a["rule"] == "command_timed_out" for a in alerts["items"])

    stack.world.fake.set_failure(ref_of(iid), Failure.SILENT, on=False)
    stack.world.clock.advance(1)
    await stack.world.worker.run_once()  # aucune relance automatique
    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "timed_out"


@given(path=st.lists(st.sampled_from(STATUSES), max_size=12))
def test_i08_cycle_de_vie_de_la_commande_est_ordonne(path: list[str]) -> None:
    """Quelle que soit la suite de transitions tentées : jamais en arrière, jamais de saut
    d'étape vers `verified`, et un état terminal ne change plus."""
    state, visited = "requested", ["requested"]
    for target in path:
        before = state
        if can_transition(state, target):
            state = target
            visited.append(target)
        else:
            assert state == before
        if before in TERMINAL:
            assert state == before
    if "verified" in visited:  # effet observé seulement après dispatch puis accusé
        assert visited[: visited.index("verified")][-2:] == ["dispatched", "acknowledged"]
    ranks = [RANK[s] for s in visited if s in RANK]
    assert ranks == sorted(ranks) and len(set(ranks)) == len(ranks)
    assert all(src in RANK for src in NEXT)
