"""Déploiement par le worker (SPEC F9, I5, I10) : refus lisibles, aucun live avant la promotion,
et annonce au flux des ordres et positions qui changent."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from centrade_api.testing import Stack, create_instance, get, ref_of
from centrade_core.engine.contract import CommandRejected
from centrade_core.engine.types import ValidationResult
from centrade_core.ids import uuid7
from centrade_core.models.trading import Engine, Instance, Order, Position
from centrade_worker.testing import World
from sqlalchemy import select
from worker_support import alerts, commands, instance, spy


async def test_refus_d_admission_du_runner_devient_un_echec_lisible(stack: Stack) -> None:
    w = stack.world
    c = await stack.client("operator")

    async def deploy(spec: Any) -> Any:  # ce que lève le runner quand la mémoire manque
        raise CommandRejected("mémoire réservée insuffisante : 2 Gio demandés pour 1 Gio")

    w.fake.deploy = deploy  # type: ignore[method-assign]
    iid = str((await create_instance(c))["id"])
    await w.worker.run_once()

    (cmd,) = await commands(w, iid, "deploy")
    assert cmd.status == "failed" and cmd.result is not None
    assert "mémoire réservée insuffisante" in cmd.result["reason"]
    shown = await get(c, f"/api/v1/instances/{iid}")
    assert shown["state"]["value"] == "unknown" and shown["active_command"] is None


async def test_code_refuse_par_l_adaptateur_n_est_jamais_deploye(stack: Stack) -> None:
    """Une instance sans version de stratégie ne tourne que sur un moteur qui accepte de n'avoir
    aucun code : c'est l'adaptateur qui le dit, pas le worker."""
    w = stack.world
    c = await stack.client("operator")
    calls = spy(w.fake)
    w.fake.check_source = lambda manifest, source: ValidationResult(  # type: ignore[method-assign]
        ok=False, errors=("aucune classe de stratégie",)
    )
    iid = str((await create_instance(c))["id"])
    await w.worker.run_once()

    (cmd,) = await commands(w, iid, "deploy")
    assert cmd.status == "failed" and cmd.result is not None
    assert "aucune classe de stratégie" in cmd.result["reason"]
    assert calls == [] and (await instance(w, iid)).deployment_fingerprint is None


@pytest.mark.parametrize("type_", ["deploy", "resume_entries", "start"])
async def test_instance_live_jamais_deployee_ni_reprise_avant_la_promotion(
    migrated_url: str, redis_url: str, type_: str
) -> None:
    from datetime import timedelta

    from centrade_core.models.trading import Command

    async with World(migrated_url, redis_url) as w:
        engine_id, iid = uuid7(), uuid7()
        async with w.sessions.begin() as s:
            s.add(Engine(id=engine_id, kind="fake", image="x", version="1"))
            await s.flush()
            s.add(
                Instance(
                    id=iid,
                    engine_id=engine_id,
                    name=f"live-{uuid4()}",
                    mode="live",
                    desired_state="exits_only",
                )
            )
            await s.flush()
            s.add(
                Command(
                    id=uuid7(),
                    instance_id=iid,
                    type=type_,
                    actor="user:test",
                    idempotency_key=uuid4().hex,
                    status="requested",
                    correlation_id=uuid7(),
                    requested_at=w.clock.now,
                    deadline_at=w.clock.now + timedelta(seconds=60),
                    updated_at=w.clock.now,
                )
            )
        calls = spy(w.fake)

        await w.worker.run_once()

        (cmd,) = await commands(w, iid)
        assert cmd.status == "failed" and cmd.result is not None
        assert [r["code"] for r in cmd.result["reasons"]] == ["live"]
        assert calls == []  # rien n'a atteint le moteur
        assert [a.rule for a in await alerts(w, iid)] == ["entries_refused"]


async def test_ordres_et_positions_annonces_au_flux_quand_ils_changent(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = stack.world
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    ref = ref_of(iid)
    await w.worker.run_once()
    await w.fake.resume_entries(ref)
    sent: list[tuple[str, UUID]] = []

    async def notify(redis: Any, kind: str, ident: UUID) -> None:
        sent.append((kind, ident))

    monkeypatch.setattr("centrade_worker.worker.notify", notify)
    for _ in range(500):
        snap = await w.fake.snapshot(ref)
        if snap.positions and snap.orders:
            break
        w.step(ref, 1)
    await w.worker.run_once()

    async with w.sessions() as s:
        positions = set(
            await s.scalars(select(Position.id).where(Position.instance_id == ref.instance_id))
        )
        orders = set(await s.scalars(select(Order.id).where(Order.instance_id == ref.instance_id)))
    assert positions and orders
    assert {i for k, i in sent if k == "position"} == positions
    assert {i for k, i in sent if k == "order"} == orders  # ouverts, exécutés, annulés
    assert len(sent) == len(set(sent))  # une annonce par ligne et par tour

    sent.clear()
    await w.worker.run_once()  # rien n'a changé : pas une annonce par tour
    assert not [k for k, _ in sent if k in ("position", "order")]
    w.clock.advance(10)  # cadence de rafraîchissement : la date d'observation avance
    await w.worker.run_once()
    assert {i for k, i in sent if k == "position"} == positions
