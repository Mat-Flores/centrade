"""S8 (SPEC §14, §13) : clé possédée modifiée hors plateforme. Détectée en 60 s (horloge
injectée), sorties seules, alerte critique ; la dérive et la configuration relue sont enregistrées
et datées."""

from datetime import timedelta

from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_fake.engine import Failure
from worker_support import alerts, commands, instance, spy


async def test_s08_derive_detectee_en_60_s_sorties_seules_alerte_critique(stack: Stack) -> None:
    w = stack.world
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    await w.worker.run_once()
    assert (await act(c, iid, "resume-entries")).status_code == 202
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == "running"
    calls = spy(w.fake)

    w.fake.set_failure(ref_of(iid), Failure.DRIFT)  # modifiée dans le moteur, hors plateforme
    drifted_at = w.clock.now
    detected_at = None
    for _ in range(12):  # le worker tourne ; l'horloge avance de 5 s par tour
        w.clock.advance(5)
        await w.worker.run_once()
        if await alerts(w, iid, "config_drift"):
            detected_at = w.clock.now
            break
    assert detected_at is not None and detected_at - drifted_at <= timedelta(seconds=60)

    (alert,) = await alerts(w, iid, "config_drift")
    assert (alert.severity, alert.status) == ("critical", "open")
    assert "max_open_positions" in alert.message
    # Sorties seules : la pause est partie d'office, sans attendre le tour suivant.
    assert calls == ["pause_entries"]
    assert (await w.fake.status(ref_of(iid))).state == "exits_only"
    (pause,) = await commands(w, iid, "pause_entries")
    assert pause.actor == "system:worker"
    row = await instance(w, iid)
    assert row.drift == [{"key": "max_open_positions", "expected": "3", "observed": "999"}]
    assert row.effective_config is not None and row.effective_config["max_open_positions"] == "999"
    assert row.effective_config_at == detected_at
    detail = await get(c, f"/api/v1/instances/{iid}")
    assert detail["drift"]["value"] == row.drift and detail["drift"]["observed_at"] is not None

    await w.worker.run_once()
    assert (await commands(w, iid, "pause_entries"))[0].status == "verified"
    shown = await get(c, f"/api/v1/instances/{iid}")
    assert shown["state"]["value"] == "exits_only" and shown["desired_state"] == "running"

    # Tant que la dérive dure, les entrées ne se rouvrent pas.
    r = await act(c, iid, "resume-entries")
    assert r.status_code == 202
    await w.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{r.json()['command_id']}")
    assert cmd["status"] == "failed" and "max_open_positions" in cmd["result"]["reason"]
    assert {x["code"] for x in cmd["result"]["reasons"]} == {"drift"}
    assert calls == ["pause_entries"]

    # La configuration redevient conforme : l'alerte se résout, la dérive enregistrée s'efface.
    w.fake.set_failure(ref_of(iid), Failure.DRIFT, on=False)
    w.clock.advance(30)
    await w.worker.run_once()
    assert (await alerts(w, iid, "config_drift"))[0].status == "resolved"
    assert (await instance(w, iid)).drift == []


async def test_s08_cle_possedee_absente_de_la_relecture_est_une_derive(stack: Stack) -> None:
    """Jamais d'ignorance silencieuse : une clé que l'adaptateur ne relit pas, sans la déclarer."""
    w = stack.world
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    real = w.fake.effective_config

    async def partial(ref: object) -> object:
        eff = await real(ref)  # type: ignore[arg-type]
        return eff.model_copy(
            update={"values": {k: v for k, v in eff.values.items() if k != "stoploss"}}
        )

    w.fake.effective_config = partial  # type: ignore[method-assign,assignment]
    await w.worker.run_once()
    assert (await instance(w, iid)).drift == [
        {"key": "stoploss", "expected": "-0.05", "observed": None}
    ]
    assert [a.severity for a in await alerts(w, iid, "config_drift")] == ["critical"]

    # Déclarée non relisible par l'adaptateur : ce n'est plus une dérive.
    render = w.fake.render_config
    w.fake.render_config = lambda spec: render(spec).model_copy(  # type: ignore[method-assign]
        update={"unreadable": frozenset({"stoploss"})}
    )
    w.clock.advance(30)
    await w.worker.run_once()
    assert (await instance(w, iid)).drift == []
    assert (await alerts(w, iid, "config_drift"))[0].status == "resolved"
