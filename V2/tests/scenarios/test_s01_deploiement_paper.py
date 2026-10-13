"""S1 (SPEC §14) : dépôt, instance, démarrage en sorties seules, vérification, entrées ouvertes ;
l'interface montre voulu et observé identiques."""

from uuid import uuid4

from centrade_api.testing import Stack, act, get, ref_of
from worker_support import alerts, commands, instance, spy

MANIFEST = {
    "name": "s1",
    "engine": "fake",
    "version": 1,
    "entrypoint": "s1.py",
    "asset_classes": ["crypto"],
    "trading_mode": "spot",
    "timeframes": ["5m"],
    "modes": ["paper"],
    "params_schema": {"type": "object", "properties": {"fast": {"type": "integer"}}},
    "sizing": {"stake_amount": "25", "max_open_positions": 2},
    "exits": {"stoploss": "-0.03", "stop_on_venue": True},
}


async def test_s01_deploiement_paper_de_bout_en_bout(stack: Stack) -> None:
    w = stack.world
    admin = await stack.client("admin")
    r = await admin.post(
        "/api/v1/accounts",
        json={
            "venue": "venue-test",
            "type": "paper",
            "environment": "sandbox",
            "label": "Compte S1",
            "currency": "USDT",
        },
    )
    assert r.status_code == 201, r.text
    account_id = r.json()["id"]

    # Dépôt d'une version, puis instance paper sur cette version et ce compte.
    c = await stack.client("operator")
    r = await c.post("/api/v1/strategies", json={"name": f"s1-{uuid4().hex[:8]}"})
    assert r.status_code == 201, r.text
    r = await c.post(
        f"/api/v1/strategies/{r.json()['id']}/versions",
        json={"manifest": MANIFEST, "code": "# stratégie simulée\n"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert r.status_code == 201, r.text
    version = r.json()
    r = await c.post(
        "/api/v1/instances",
        json={
            "name": f"s1-{uuid4().hex[:8]}",
            "strategy_version_id": version["id"],
            "account_id": account_id,
            "params": {"fast": 10},
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    assert r.json()["desired_state"] == "exits_only" and r.json()["state"]["value"] == "unknown"
    calls = spy(w.fake)

    # Démarrage en sorties seules : déployée depuis le registre, empreinte enregistrée, vérifiée.
    await w.worker.run_once()
    assert calls == ["deploy"]
    detail = await get(c, f"/api/v1/instances/{iid}")
    assert detail["state"]["value"] == "exits_only" and detail["observed_mode"]["value"] == "paper"
    assert detail["mode_mismatch"] is False and detail["drift"]["value"] == []
    assert detail["strategy"]["code_hash"] == version["code_hash"]
    row = await instance(w, iid)
    assert detail["deployment_fingerprint"] == row.deployment_fingerprint is not None
    running = await w.fake.effective_config(ref_of(iid))
    assert running.fingerprint == row.deployment_fingerprint
    # La configuration relue est celle du manifest déposé et du compte choisi, et elle est datée.
    assert detail["effective_config"]["value"]["stake_amount"] == "25"
    assert detail["effective_config"]["value"]["stoploss"] == "-0.03"
    assert detail["effective_config"]["value"]["account_id"] == account_id
    assert detail["effective_config"]["observed_at"] is not None
    assert (await commands(w, iid, "deploy"))[0].status == "verified"
    assert w.fake._insts[row.id].spec.manifest.sizing.max_open_positions == 2

    # Vérification de F9 passée : les entrées s'ouvrent, et l'effet est observé.
    r = await act(c, iid, "resume-entries")
    assert r.status_code == 202
    await w.worker.run_once()
    assert calls == ["deploy", "resume_entries"]
    assert (await get(c, f"/api/v1/commands/{r.json()['command_id']}"))["status"] == "verified"
    shown = await get(c, f"/api/v1/instances/{iid}")
    assert shown["desired_state"] == shown["state"]["value"] == "running"
    assert shown["state"]["stale"] is False and shown["active_command"] is None
    assert await alerts(w, iid) == []
