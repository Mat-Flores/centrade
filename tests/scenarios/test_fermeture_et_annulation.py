"""`close_position` et `cancel_entry_order` (SPEC F9, §7, I4) dans le cycle des commandes : envoi,
effet vérifié par l'instantané, échéance. Elles réduisent le risque : immédiates, jamais retenues
par la vérification de F9 ni par une instance occupée. Un ordre qui n'est pas une entrée ne
s'annule jamais."""

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.engine.types import InstanceRef
from centrade_core.engine.types import Order as EngineOrder
from centrade_core.ids import uuid7
from centrade_core.models.trading import Command
from centrade_fake.engine import SYMBOL, Failure
from worker_support import commands, spy


def _key() -> dict[str, str]:
    return {"Idempotency-Key": uuid4().hex}


async def _trading(stack: Stack) -> tuple[httpx.AsyncClient, str, InstanceRef]:
    """Instance en marche qui tient au moins une position et un ordre d'entrée ouvert."""
    w = stack.world
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    ref = ref_of(iid)
    await w.worker.run_once()
    assert (await act(c, iid, "resume-entries")).status_code == 202
    await w.worker.run_once()
    for _ in range(500):
        snap = await w.fake.snapshot(ref)
        if snap.positions and snap.orders:
            break
        w.step(ref, 1)
    else:
        raise AssertionError("ni position ni ordre d'entrée : le test ne prouverait rien")
    await w.worker.run_once()
    return c, iid, ref


async def _command(stack: Stack, iid: str, type_: str, args: dict[str, Any] | None) -> UUID:
    """Commande écrite comme le fait l'API, pour les cas que ses routes refusent d'emblée."""
    now = stack.world.clock.now
    cmd = Command(
        id=uuid7(),
        instance_id=UUID(iid),
        type=type_,
        actor="user:test",
        idempotency_key=uuid4().hex,
        args=args,
        status="requested",
        correlation_id=uuid7(),
        requested_at=now,
        deadline_at=now + timedelta(seconds=30),
        updated_at=now,
    )
    async with stack.world.sessions.begin() as s:
        s.add(cmd)
    return cmd.id


async def test_fermeture_d_une_position_envoyee_et_verifiee_par_l_instantane(stack: Stack) -> None:
    c, iid, ref = await _trading(stack)
    w = stack.world
    target = (await get(c, f"/api/v1/positions?instance_id={iid}"))["items"][0]
    before = {p.position_id for p in (await w.fake.snapshot(ref)).positions}
    calls = spy(w.fake)

    r = await c.post(f"/api/v1/positions/{target['id']}/close", headers=_key())
    assert r.status_code == 202, r.text
    await w.worker.run_once()

    cmd = await get(c, f"/api/v1/commands/{r.json()['command_id']}")
    assert cmd["status"] == "verified", cmd
    assert calls == ["close_position"]
    left = {p.position_id for p in (await w.fake.snapshot(ref)).positions}
    assert left < before and len(before - left) == 1  # celle-là, et elle seule
    assert (await w.fake.status(ref)).state == "running"  # ni pause ni arrêt


async def test_annulation_d_un_ordre_d_entree_envoyee_et_verifiee(stack: Stack) -> None:
    c, iid, ref = await _trading(stack)
    w = stack.world
    (order,) = [
        o
        for o in (await get(c, f"/api/v1/orders?instance_id={iid}"))["items"]
        if o["status"] == "open"
    ]
    calls = spy(w.fake)

    r = await c.delete(f"/api/v1/orders/{order['id']}", headers=_key())
    assert r.status_code == 202, r.text
    await w.worker.run_once()

    assert (await get(c, f"/api/v1/commands/{r.json()['command_id']}"))["status"] == "verified"
    assert calls == ["cancel_entry_order"]
    assert (await w.fake.snapshot(ref)).orders == ()
    held = {p.position_id for p in (await w.fake.snapshot(ref)).positions}
    assert held  # les positions ne sont pas touchées


async def test_annulation_refuse_un_ordre_qui_n_est_pas_une_entree(stack: Stack) -> None:
    c, iid, ref = await _trading(stack)
    w = stack.world
    exit_order = EngineOrder(
        order_id=str(uuid7()),
        symbol=SYMBOL,
        side="sell",
        intent="exit",
        qty=Decimal("1"),
        price=Decimal("100"),
        status="open",
    )
    w.fake._insts[ref.instance_id].orders[exit_order.order_id] = exit_order  # sortie en attente
    calls = spy(w.fake)

    refused = await _command(stack, iid, "cancel_entry_order", {"order_id": exit_order.order_id})
    unknown = await _command(stack, iid, "cancel_entry_order", {"order_id": "inconnu"})
    empty = await _command(stack, iid, "cancel_entry_order", None)
    no_position = await _command(stack, iid, "close_position", {"position_id": 12})
    await w.worker.run_once()

    results = {
        cid: await get(c, f"/api/v1/commands/{cid}")
        for cid in (refused, unknown, empty, no_position)
    }
    assert {r["status"] for r in results.values()} == {"failed"}
    assert "pas un ordre d'entrée" in results[refused]["result"]["reason"]
    assert "introuvable" in results[unknown]["result"]["reason"]
    assert "order_id manquant" in results[empty]["result"]["reason"]
    assert "position_id manquant" in results[no_position]["result"]["reason"]
    assert calls == []  # rien n'a été envoyé au moteur
    assert exit_order.order_id in {o.order_id for o in (await w.fake.snapshot(ref)).orders}


async def test_i04_fermeture_et_annulation_jamais_retenues_par_la_verification_de_f9(
    stack: Stack,
) -> None:
    c, iid, ref = await _trading(stack)
    w = stack.world
    snap = await w.fake.snapshot(ref)
    position_id, order_id = snap.positions[0].position_id, snap.orders[0].order_id
    # Tout ce que la vérification refuse : mode faux, configuration dérivée, image changée,
    # relevés périmés, et une reprise des entrées restée sans effet (instance occupée).
    for failure in (Failure.LIE_MODE, Failure.DRIFT, Failure.SLOW, Failure.IGNORE_PAUSE):
        w.fake.set_failure(ref, failure)
    busy = await _command(stack, iid, "resume_entries", None)
    calls = spy(w.fake)

    close = await _command(stack, iid, "close_position", {"position_id": position_id})
    cancel = await _command(stack, iid, "cancel_entry_order", {"order_id": order_id})
    w.clock.advance(600)  # worker longtemps absent : elles n'expirent pas avant l'envoi
    await w.worker.run_once()

    assert {"close_position", "cancel_entry_order"} <= set(calls)
    assert "resume_entries" not in calls
    snap = await w.fake.snapshot(ref)
    assert position_id not in {p.position_id for p in snap.positions}
    assert order_id not in {o.order_id for o in snap.orders}
    for cid in (close, cancel):
        cmd = await get(c, f"/api/v1/commands/{cid}")
        assert cmd["dispatched_at"] is not None and cmd["status"] == "acknowledged", cmd
    assert (await get(c, f"/api/v1/commands/{busy}"))["status"] in ("failed", "timed_out")

    # Le relevé redevient frais : l'effet est observé, les deux commandes sont vérifiées.
    w.fake.set_failure(ref, Failure.SLOW, on=False)
    await w.worker.run_once()
    for cid in (close, cancel):
        assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "verified"


async def test_fermeture_sans_reponse_du_moteur_expire_et_se_voit(stack: Stack) -> None:
    c, iid, ref = await _trading(stack)
    w = stack.world
    position_id = (await w.fake.snapshot(ref)).positions[0].position_id
    w.fake.set_failure(ref, Failure.SILENT)
    cid = await _command(stack, iid, "close_position", {"position_id": position_id})

    await w.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "dispatched"  # jamais rejouée
    w.clock.advance(31)
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/commands/{cid}"))["status"] == "timed_out"
    assert len(await commands(w, iid, "close_position")) == 1
