"""I1 : tout état affiché est observé et daté ; périmé au-delà du seuil ; inconnu s'affiche
inconnu ; l'état voulu n'est jamais présenté comme réel (SPEC §1.2, §9)."""

from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_fake.engine import Failure
from centrade_worker.testing import T0


async def test_i01_displayed_state_carries_observation_timestamp(stack: Stack) -> None:
    c = await stack.client("operator")
    created = await create_instance(c)
    await stack.world.worker.run_once()  # déploiement, puis premier relevé

    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["state"]["value"] == "exits_only"
    assert inst["state"]["observed_at"] == T0.isoformat().replace("+00:00", "Z")
    assert inst["observed_mode"]["value"] == "paper" and inst["observed_mode"]["observed_at"]
    assert inst["server_time"] and inst["state"]["stale"] is False
    page = await get(c, "/api/v1/instances")
    assert page["server_time"] and any(i["id"] == created["id"] for i in page["items"])


async def test_i01_state_is_stale_beyond_threshold(stack: Stack) -> None:
    c = await stack.client("operator")
    created = await create_instance(c)
    await stack.world.worker.run_once()
    stack.world.clock.advance(stack.settings.observed_stale_after_s - 1)
    assert (await get(c, f"/api/v1/instances/{created['id']}"))["state"]["stale"] is False

    stack.world.clock.advance(2)  # le worker ne tourne plus : la valeur vieillit
    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["state"]["stale"] is True and inst["observed_mode"]["stale"] is True
    assert inst["state"]["value"] == "exits_only"  # la valeur garde sa date, jamais « actuelle »
    assert inst["state"]["observed_at"] and inst["server_time"] > inst["state"]["observed_at"]


async def test_i01_unknown_state_is_displayed_as_unknown(stack: Stack) -> None:
    c = await stack.client("operator")
    created = await create_instance(c, failures=["silent"])
    await stack.world.worker.run_once()

    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["state"]["value"] == "unknown" and inst["observed_mode"]["value"] == "unknown"

    # Une instance saine, puis muette : plus de dernière valeur connue.
    healthy = await create_instance(c)
    await stack.world.worker.run_once()
    stack.world.fake.set_failure(ref_of(healthy["id"]), Failure.SILENT)
    await stack.world.worker.run_once()
    after = await get(c, f"/api/v1/instances/{healthy['id']}")
    assert after["state"]["value"] == "unknown" and after["observed_mode"]["value"] == "unknown"


async def test_i01_desired_state_is_never_shown_as_observed(stack: Stack) -> None:
    c = await stack.client("operator")
    created = await create_instance(c)  # jamais observé : le worker n'a pas tourné
    assert created["desired_state"] == "exits_only"
    assert created["state"] == {"value": "unknown", "observed_at": None, "stale": False}

    await stack.world.worker.run_once()
    r = await act(c, created["id"], "resume-entries")
    assert r.status_code == 202
    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["desired_state"] == "running"  # voulu changé tout de suite…
    assert inst["state"]["value"] == "exits_only"  # …observé inchangé tant que rien n'est vu
    assert inst["active_command"]["status"] == "requested"

    await stack.world.worker.run_once()
    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["state"]["value"] == "running" and inst["active_command"] is None
