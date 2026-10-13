"""S7 (SPEC §14) : un moteur qui se déclare live pour une instance paper. Entrées jamais ouvertes,
alerte critique, et le mode observé reste affiché tel quel (badge « MODE INCOHÉRENT »)."""

from centrade_api.testing import Stack, act, create_instance, get, ref_of
from worker_support import alerts, commands, instance, spy


async def test_s07_mode_mismatch_never_opens_entries(stack: Stack) -> None:
    w = stack.world
    c = await stack.client("operator")
    calls = spy(w.fake)
    iid = str((await create_instance(c, failures=["lie_mode"]))["id"])

    await w.worker.run_once()  # premier démarrage observé : le mode effectif est relu

    shown = await get(c, f"/api/v1/instances/{iid}")
    assert shown["desired_mode"] == "paper" and shown["observed_mode"]["value"] == "live"
    assert shown["mode_mismatch"] is True and shown["state"]["value"] == "exits_only"
    assert (await instance(w, iid)).observed_mode == "live"  # jamais remplacé par le mode voulu
    (alert,) = await alerts(w, iid, "mode_mismatch")
    assert (alert.severity, alert.status, alert.invariant) == ("critical", "open", "I3")
    # Le déploiement n'est pas confirmé : ce qui tourne n'est pas conforme.
    assert (await commands(w, iid, "deploy"))[0].status == "acknowledged"

    r = await act(c, iid, "resume-entries")
    assert r.status_code == 409 and "mode" in r.json()["detail"]
    for _ in range(3):
        w.clock.advance(20)
        await w.worker.run_once()
    assert calls == ["deploy"]  # aucune reprise n'a atteint le moteur
    assert (await w.fake.status(ref_of(iid))).state == "exits_only"
    assert w.fake._insts[ref_of(iid).instance_id].orders == {}
    assert len(await alerts(w, iid, "mode_mismatch")) == 1  # une alerte, pas une par contrôle
    assert (await commands(w, iid, "deploy"))[0].status == "timed_out"
