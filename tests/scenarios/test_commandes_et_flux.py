"""Instances, commandes et flux : idempotence, préemption, asymétrie (F9), RBAC, pagination,
rechargement du worker, fermeture du flux à l'expiration de la session."""

import json
from datetime import timedelta
from uuid import uuid4

import httpx
from centrade_api.testing import Stack, act, create_instance, get
from centrade_core.ids import uuid7
from centrade_core.models import Session
from centrade_core.models.trading import Command
from centrade_fake.engine import FakeEngine
from sqlalchemy import func, select

ACTIONS = ("start", "stop", "pause-entries", "resume-entries", "flatten")


async def _ready(stack: Stack, **params: object) -> tuple[httpx.AsyncClient, str]:
    c = await stack.client("operator")
    inst = await create_instance(c, **params)
    await stack.world.worker.run_once()
    return c, str(inst["id"])


async def test_idempotence_meme_cle_meme_commande_autre_contenu_refuse(stack: Stack) -> None:
    c, iid = await _ready(stack)
    other = (await create_instance(c))["id"]
    r1 = await act(c, iid, "pause-entries", key="cle-idempotence-1")
    r2 = await act(c, iid, "pause-entries", key="cle-idempotence-1")
    assert r1.status_code == r2.status_code == 202
    assert r1.json()["command_id"] == r2.json()["command_id"]
    assert r2.headers["Idempotency-Replayed"] == "true" and "Idempotency-Replayed" not in r1.headers
    async with stack.world.sessions() as s:
        n = await s.scalar(
            select(func.count()).where(Command.idempotency_key == "cle-idempotence-1")
        )
    assert n == 1
    assert (await act(c, iid, "flatten", key="cle-idempotence-1")).status_code == 422  # autre type
    assert (await act(c, other, "pause-entries", key="cle-idempotence-1")).status_code == 422
    missing = await c.post(f"/api/v1/instances/{iid}/stop")  # sans Idempotency-Key
    assert missing.status_code == 422


async def test_une_action_n_appelle_jamais_le_moteur(stack: Stack) -> None:
    c, iid = await _ready(stack)
    calls: list[str] = []
    real = stack.world.fake.resume_entries

    async def spy(ref: object) -> None:
        calls.append("resume")
        await real(ref)  # type: ignore[arg-type]

    stack.world.fake.resume_entries = spy  # type: ignore[method-assign]
    r = await act(c, iid, "resume-entries")
    assert r.status_code == 202 and calls == []  # seul le worker appelle l'adaptateur
    assert r.json()["command"]["status"] == "requested"
    await stack.world.worker.run_once()
    assert calls == ["resume"]


async def test_pause_passe_devant_et_remplace_la_reprise_en_attente(stack: Stack) -> None:
    c, iid = await _ready(stack)
    resume = (await act(c, iid, "resume-entries")).json()["command_id"]
    pause = (await act(c, iid, "pause-entries")).json()["command_id"]
    assert (await get(c, f"/api/v1/commands/{resume}"))["status"] == "superseded"
    await stack.world.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{pause}"))["status"] == "verified"
    inst = await get(c, f"/api/v1/instances/{iid}")
    assert inst["state"]["value"] == "exits_only" and inst["desired_state"] == "exits_only"
    assert (await get(c, f"/api/v1/commands/{resume}"))["superseded_at"]


async def test_une_commande_a_la_fois_par_instance(stack: Stack) -> None:
    c, iid = await _ready(stack)
    first = (await act(c, iid, "resume-entries")).json()["command_id"]
    second = (await act(c, iid, "stop")).json()["command_id"]
    await stack.world.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{first}"))["status"] == "verified"
    assert (await get(c, f"/api/v1/commands/{second}"))["status"] == "requested"  # attend
    await stack.world.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{second}"))["status"] == "verified"
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == "stopped"


async def test_reprise_refusee_si_etat_inconnu_perime_ou_mode_different(stack: Stack) -> None:
    w = stack.world
    c, iid = await _ready(stack)

    w.clock.advance(stack.settings.observed_stale_after_s + 1)  # périmé : le worker ne tourne pas
    r = await act(c, iid, "resume-entries")
    assert r.status_code == 409 and "périmé" in r.json()["detail"]
    assert (await act(c, iid, "pause-entries")).status_code == 202  # réduit le risque : accepté
    assert (await act(c, iid, "flatten")).status_code == 202
    assert (await act(c, iid, "stop")).status_code == 202

    unknown = (await create_instance(c, failures=["silent"]))["id"]
    await w.worker.run_once()
    r = await act(c, unknown, "resume-entries")
    assert r.status_code == 409 and "inconnu" in r.json()["detail"]
    for a in ("pause-entries", "flatten", "stop"):
        assert (await act(c, unknown, a)).status_code == 202, a

    liar = (await create_instance(c, failures=["lie_mode"]))["id"]
    await w.worker.run_once()
    r = await act(c, liar, "resume-entries")
    assert r.status_code == 409 and "mode" in r.json()["detail"]
    inst = await get(c, f"/api/v1/instances/{liar}")
    assert inst["mode_mismatch"] is True and inst["desired_mode"] == "paper"
    assert (await act(c, liar, "pause-entries")).status_code == 202


async def test_commande_rejetee_par_l_adaptateur_passe_failed_avec_raison(stack: Stack) -> None:
    c = await stack.client("operator")
    inst = await create_instance(c, failures=["panne-inconnue"])
    await stack.world.worker.run_once()
    deploy = (await get(c, "/api/v1/commands?instance_id=" + inst["id"]))["items"][0]
    assert deploy["type"] == "deploy" and deploy["status"] == "failed"
    assert deploy["failed_at"] and "panne-inconnue" in deploy["result"]["reason"]


async def test_creation_validations_et_listes(stack: Stack) -> None:
    c = await stack.client("operator")
    body = {"name": f"n-{uuid4().hex[:8]}", "engine": "fake", "mode": "paper", "params": {}}
    assert (await c.post("/api/v1/instances", json=body)).status_code == 201
    assert (await c.post("/api/v1/instances", json=body)).status_code == 409  # nom pris
    assert (await c.post("/api/v1/instances", json={**body, "mode": "live"})).status_code == 422
    assert (
        await c.post("/api/v1/instances", json={**body, "engine": "inconnu"})
    ).status_code == 422

    for _ in range(2):
        await create_instance(c)
    first = await get(c, "/api/v1/instances?limit=2")
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = await get(c, f"/api/v1/instances?limit=2&cursor={first['next_cursor']}")
    ids = {i["id"] for i in first["items"]}
    assert second["items"] and not ids & {i["id"] for i in second["items"]}
    assert (await c.get("/api/v1/instances?cursor=n-importe-quoi")).status_code == 422
    await stack.world.worker.run_once()
    events = await get(c, "/api/v1/events?limit=5")
    assert "server_time" in events and "items" in events
    assert (await c.get("/api/v1/commands/" + str(uuid4()))).status_code == 404


async def test_rbac_viewer_ne_peut_rien_commander_et_audit_reserve_a_l_admin(stack: Stack) -> None:
    op = await stack.client("operator")
    iid = (await create_instance(op))["id"]
    viewer = await stack.client("viewer")
    assert (await viewer.get("/api/v1/instances")).status_code == 200
    assert (await viewer.get(f"/api/v1/instances/{iid}")).status_code == 200
    for path in ("/commands", "/events", "/alerts"):
        assert (await viewer.get("/api/v1" + path)).status_code == 200
    body = {"name": "x-viewer", "engine": "fake", "mode": "paper", "params": {}}
    assert (await viewer.post("/api/v1/instances", json=body)).status_code == 403
    for a in ACTIONS:
        assert (await act(viewer, iid, a)).status_code == 403, a
    assert (await viewer.get("/api/v1/audit")).status_code == 403
    assert (await op.get("/api/v1/audit")).status_code == 403
    admin = await stack.client("admin")
    audit = await get(admin, "/api/v1/audit?limit=3")
    assert len(audit["items"]) == 3 and audit["next_cursor"]


async def test_aucune_route_ni_schema_ne_nomme_un_moteur(stack: Stack) -> None:
    spec = json.dumps(stack.app.openapi()).lower()
    assert "fake" not in spec and "freqtrade" not in spec
    assert not [p for p in stack.app.openapi()["paths"] if "order" in p]  # aucune création d'ordre


async def test_le_worker_recharge_les_instances_en_sorties_seules(stack: Stack) -> None:
    w = stack.world
    c, iid = await _ready(stack)
    await act(c, iid, "resume-entries")
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == "running"

    w.fake = FakeEngine(clock=w.clock, seed=5, new_id=uuid7)  # le processus redémarre
    w.worker = w.make_worker("apres")
    await w.worker.load_instances()
    await w.worker.run_once()
    inst = await get(c, f"/api/v1/instances/{iid}")
    assert inst["state"]["value"] == "exits_only" and inst["desired_state"] == "running"


async def test_sante_etendue_sans_session(stack: Stack) -> None:
    anon = await stack.client(signed_in=False)
    down = (await anon.get("/api/v1/system/health")).json()
    assert down["status"] == "degraded" and down["checks"]["worker"]["status"] == "down"
    await stack.world.worker.run_once()
    ok = (await anon.get("/api/v1/system/health")).json()
    assert ok["status"] == "ok" and all(c["observed_at"] for c in ok["checks"].values())
    stack.world.clock.advance(60)  # battement trop ancien
    assert (await anon.get("/api/v1/system/health")).json()["checks"]["worker"]["status"] == "down"


class _JumpClock:
    """Horloge qui saute d'une heure après quelques lectures : la session expire en plein flux."""

    def __init__(self, base: object, after: int) -> None:
        self._base, self._after, self._n = base, after, 0

    def __call__(self):  # type: ignore[no-untyped-def]
        self._n += 1
        now = self._base()  # type: ignore[operator]
        return now + timedelta(hours=1) if self._n > self._after else now


async def test_le_flux_se_ferme_quand_la_session_expire(stack: Stack) -> None:
    from centrade_api.deps import utcnow

    c = await stack.client("viewer")
    stack.app.dependency_overrides[utcnow] = _JumpClock(stack.world.clock, after=3)
    async with c.stream("GET", "/api/v1/stream") as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        text = "".join([chunk async for chunk in r.aiter_text()])  # se termine : flux fermé
    assert "event: heartbeat" in text
    stack.app.dependency_overrides[utcnow] = stack.world.clock
    assert (await c.get("/api/v1/instances")).status_code == 200  # session non touchée côté flux


async def test_le_flux_exige_une_session_et_ne_repousse_pas_l_inactivite(stack: Stack) -> None:
    anon = await stack.client(signed_in=False)
    assert (await anon.get("/api/v1/stream")).status_code == 401
    await _ready(stack)
    assert stack.last_account is not None
    from centrade_api.stream import stream_messages

    async with stack.world.sessions() as s:
        row = (
            await s.execute(select(Session).where(Session.user_id == stack.last_account.id))
        ).scalar_one()
    before = row.last_activity_at
    gen = stream_messages(
        factory=stack.world.sessions,
        redis=stack.world.redis,
        session_id=row.id,
        now=stack.world.clock,
        cfg=stack.settings,
    )
    await gen.__anext__()
    stack.world.clock.advance(20)
    await gen.__anext__()
    await gen.aclose()
    async with stack.world.sessions() as s:
        after = await s.scalar(select(Session.last_activity_at).where(Session.id == row.id))
    assert after == before
    stack.world.clock.advance(31 * 60)  # inactivité dépassée : le flux se ferme
    gen2 = stream_messages(
        factory=stack.world.sessions,
        redis=stack.world.redis,
        session_id=row.id,
        now=stack.world.clock,
        cfg=stack.settings,
    )
    await gen2.__anext__()
    assert [ev async for ev in gen2] == []  # se termine sans rien envoyer
