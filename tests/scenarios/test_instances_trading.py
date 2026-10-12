"""Lot G : création depuis le registre, détail d'instance, lectures de trading, fermeture et
annulation d'un ordre d'entrée (F9, F10, §8, §9). Valeurs sentinelles, aucun moteur réel."""

from datetime import timedelta
from decimal import Decimal
from typing import Any, get_args
from uuid import UUID, uuid4

import httpx
import pytest
from centrade_api.stream import _message
from centrade_api.testing import Stack, get
from centrade_core.engine.types import Intent
from centrade_core.ids import uuid7
from centrade_core.models import AuditLog
from centrade_core.models.trading import (
    Account,
    Command,
    Engine,
    Instance,
    Order,
    Position,
    Strategy,
    StrategyVersion,
    Trade,
)
from sqlalchemy import func, select

I = "/api/v1/instances"  # noqa: E741


def _manifest(engine: str = "fake", **over: Any) -> dict[str, Any]:
    return {
        "name": "s",
        "engine": engine,
        "version": 1,
        "entrypoint": "s.py",
        "asset_classes": ["crypto"],
        "trading_mode": "spot",
        "timeframes": ["5m"],
        "modes": ["paper", "live"],
        "params_schema": {"type": "object", "properties": {"fast": {"type": "integer"}}},
        "sizing": {"stake_amount": "50", "max_open_positions": 3},
        "exits": {"stoploss": "-0.05", "stop_on_venue": True},
        **over,
    }


async def _seed(
    stack: Stack, *, engine: str = "fake", status: str = "approved", acct: str = "paper"
) -> tuple[UUID, UUID]:
    sid, vid, aid = uuid7(), uuid7(), uuid7()
    async with stack.world.sessions.begin() as s:
        s.add(Strategy(id=sid, name=f"s-{uuid4().hex[:8]}"))
        await s.flush()
        s.add(
            StrategyVersion(
                id=vid,
                strategy_id=sid,
                version=1,
                manifest=_manifest(engine),
                code="pass",
                code_hash="h" * 8,
                status=status,
                author="user:test",
                exits={"stoploss": "-0.05"},
            )
        )
        s.add(
            Account(
                id=aid,
                venue="venue-test",
                type=acct,
                environment="sandbox",
                label="Compte de test",
                currency="USDT",
            )
        )
    return vid, aid


def _body(vid: UUID, aid: UUID, **over: Any) -> dict[str, Any]:
    return {
        "name": f"i-{uuid4().hex[:10]}",
        "strategy_version_id": str(vid),
        "account_id": str(aid),
        **over,
    }


def _key() -> dict[str, str]:
    return {"Idempotency-Key": uuid4().hex}


async def _instance(stack: Stack, **over: Any) -> Instance:
    async with stack.world.sessions.begin() as s:
        eng = await s.scalar(select(Engine).where(Engine.kind == "fake"))
        assert eng is not None
        inst = Instance(
            id=uuid7(),
            engine_id=eng.id,
            name=f"i-{uuid4().hex[:10]}",
            mode="paper",
            desired_state="exits_only",
            observed_state="unknown",
            **over,
        )
        s.add(inst)
    return inst


async def _row(stack: Stack, row: Any) -> Any:
    async with stack.world.sessions.begin() as s:
        s.add(row)
    return row


def _position(inst: Instance, **over: Any) -> Position:
    return Position(
        id=uuid7(),
        instance_id=inst.id,
        external_id=f"ext-{uuid4().hex[:6]}",
        instrument="BTC/USDT",
        side="long",
        quantity=Decimal("0.5"),
        entry_price=Decimal("100"),
        currency="USDT",
        observed_at=over.pop("observed_at", None) or inst.created_at,
        **over,
    )


def _order(inst: Instance, intent: str, **over: Any) -> Order:
    return Order(
        id=uuid7(),
        instance_id=inst.id,
        client_order_id=str(uuid4()),
        instrument="BTC/USDT",
        side="buy",
        intent=intent,
        status=over.pop("status", "open"),
        quantity=Decimal("1"),
        price=Decimal("99.5"),
        currency="USDT",
        observed_at=inst.created_at,
        **over,
    )


async def _commands(stack: Stack, iid: UUID, type_: str) -> list[Command]:
    async with stack.world.sessions() as s:
        return list(
            await s.scalars(
                select(Command).where(Command.instance_id == iid, Command.type == type_)
            )
        )


# --- création -----------------------------------------------------------------------------


async def test_creation_paper_depuis_le_registre_ecrit_une_commande_de_deploiement(
    stack: Stack,
) -> None:
    vid, aid = await _seed(stack)
    c = await stack.client("operator")
    r = await c.post(I, json=_body(vid, aid, params={"fast": 5}), headers=_key())
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["desired_mode"] == "paper"
    assert out["desired_state"] == "exits_only"
    assert out["state"]["value"] == "unknown"
    assert out["active_command"]["type"] == "deploy"
    detail = await get(c, f"{I}/{out['id']}")
    assert detail["strategy"]["version_id"] == str(vid)
    assert detail["account"]["label"] == "Compte de test"
    assert "secret" not in str(detail["account"])


@pytest.mark.parametrize(
    ("over", "status"),
    [
        ({"mode": "live"}, 422),
        ({"params": {"inconnu": 1}}, 422),
        ({"engine": "autre"}, 422),
        ({"account_id": None, "strategy_version_id": None}, 201),  # création simulée de M1
    ],
)
async def test_creation_refus_et_compatibilite(
    stack: Stack, over: dict[str, Any], status: int
) -> None:
    vid, aid = await _seed(stack)
    c = await stack.client("operator")
    body = {**_body(vid, aid), **over}
    if status == 201:
        body = {"name": body["name"], "engine": "fake"}
    r = await c.post(I, json=body, headers=_key())
    assert r.status_code == status, r.text


async def test_creation_refuse_compte_live_version_retiree_moteur_inconnu(stack: Stack) -> None:
    c = await stack.client("operator")
    vid, aid = await _seed(stack, acct="live")
    assert (await c.post(I, json=_body(vid, aid), headers=_key())).status_code == 409
    vid, aid = await _seed(stack, status="retired")
    assert (await c.post(I, json=_body(vid, aid), headers=_key())).status_code == 409
    vid, aid = await _seed(stack, engine="inconnu")
    assert (await c.post(I, json=_body(vid, aid), headers=_key())).status_code == 422
    vid, aid = await _seed(stack)
    ghost = _body(uuid4(), aid)
    assert (await c.post(I, json=ghost, headers=_key())).status_code == 422
    half = {"name": "x1", "account_id": str(aid)}  # un seul des deux
    assert (await c.post(I, json=half, headers=_key())).status_code == 422


async def test_creation_idempotente_et_cle_reutilisee_avec_un_autre_corps(stack: Stack) -> None:
    vid, aid = await _seed(stack)
    c = await stack.client("operator")
    body, h = _body(vid, aid), _key()
    first = await c.post(I, json=body, headers=h)
    again = await c.post(I, json=body, headers=h)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.headers["Idempotency-Replayed"] == "true"
    assert again.json()["id"] == first.json()["id"]
    other = await c.post(I, json={**body, "name": "autre-nom"}, headers=h)
    assert other.status_code == 422
    async with stack.world.sessions() as s:
        assert (
            await s.scalar(
                select(func.count())
                .select_from(Instance)
                .where(Instance.name.in_([body["name"], "autre-nom"]))
            )
            == 1
        )


def test_aucune_route_ne_modifie_le_mode(stack: Stack) -> None:
    from fastapi.routing import iter_route_contexts

    for ctx in iter_route_contexts(stack.app.routes):
        if ctx.path and ctx.path.startswith(I):
            assert not (ctx.methods or set()) & {"PUT", "PATCH", "DELETE"}, ctx.path


# --- détail -------------------------------------------------------------------------------


async def test_detail_derive_et_configuration_effective_datees_ou_inconnues(stack: Stack) -> None:
    c = await stack.client("operator")
    inst = await _instance(stack)
    d = await get(c, f"{I}/{inst.id}")
    assert d["effective_config"] == {"value": None, "observed_at": None, "stale": False}
    assert d["drift"]["value"] is None and d["drift"]["observed_at"] is None
    assert d["strategy"] is None and d["account"] is None

    at = stack.world.clock.now - timedelta(seconds=5)
    async with stack.world.sessions.begin() as s:
        row = await s.get(Instance, inst.id)
        assert row is not None
        row.effective_config, row.effective_config_at = {"stoploss": "-0.05"}, at
        row.drift = [{"key": "stoploss", "expected": "-0.05", "observed": "-0.5"}]
        row.deployment_fingerprint, row.config_hash = "fp", "ch"
    d = await get(c, f"{I}/{inst.id}")
    assert d["effective_config"]["value"] == {"stoploss": "-0.05"}
    assert d["effective_config"]["observed_at"] is not None
    assert d["drift"]["value"] == [{"key": "stoploss", "expected": "-0.05", "observed": "-0.5"}]
    assert (d["deployment_fingerprint"], d["config_hash"]) == ("fp", "ch")
    assert d["desired_state"] == "exits_only" and d["state"]["value"] == "unknown"


# --- lectures de trading ------------------------------------------------------------------


async def test_lectures_positions_ordres_trades(stack: Stack) -> None:
    c = await stack.client("viewer")
    acct = await _seed(stack)
    inst = await _instance(stack, account_id=acct[1])
    other = await _instance(stack)
    await _row(
        stack,
        _position(
            inst,
            stop_price=Decimal("95"),
            stop_venue="venue",
            stop_type="fixed",
            protection_state="protected",
        ),
    )
    await _row(stack, _position(other))
    await _row(stack, _order(inst, "entry", decision_id=uuid4()))
    await _row(
        stack,
        Trade(
            id=uuid7(),
            instance_id=inst.id,
            external_id="t1",
            instrument="BTC/USDT",
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            exit_price=Decimal("95"),
            entry_cause="signal",
            exit_cause="stop_loss",
            pnl=Decimal("-5"),
            fees=Decimal("0.1"),
            currency="USDT",
            opened_at=inst.created_at,
            closed_at=inst.created_at,
            duration_s=60,
        ),
    )
    p = (await get(c, f"/api/v1/positions?instance_id={inst.id}"))["items"]
    assert len(p) == 1
    assert p[0]["stop_distance_pct"] == "5" and p[0]["mode"] == "paper"
    assert (p[0]["stop_venue"], p[0]["protection_state"]) == ("venue", "protected")
    assert p[0]["quantity"] == "0.5" and p[0]["currency"] == "USDT"
    assert len((await get(c, "/api/v1/positions"))["items"]) == 2
    nostop = (await get(c, f"/api/v1/positions?instance_id={other.id}"))["items"][0]
    assert nostop["stop_distance_pct"] is None and nostop["protection_state"] == "unknown"
    by_account = (await get(c, f"/api/v1/orders?account_id={acct[1]}"))["items"]
    assert [o["intent"] for o in by_account] == ["entry"] and by_account[0]["decision_id"]
    assert by_account[0]["cancelable"] is True
    assert by_account[0]["desired_mode"] == by_account[0]["mode"] == "paper"
    assert by_account[0]["observed_mode"] == {
        "value": "unknown",
        "observed_at": None,
        "stale": False,
    }
    t = (await get(c, "/api/v1/trades"))["items"][0]
    assert (t["exit_cause"], t["pnl"], t["mode"]) == ("stop_loss", "-5", "paper")
    page = await get(c, "/api/v1/positions?limit=1")
    assert page["next_cursor"]
    rest = await get(c, f"/api/v1/positions?limit=1&cursor={page['next_cursor']}")
    assert rest["items"][0]["id"] != page["items"][0]["id"]


async def test_flux_relaie_ordres_positions_trades(stack: Stack) -> None:
    inst = await _instance(stack)
    pos, order = _position(inst), _order(inst, "exit")
    await _row(stack, pos)
    await _row(stack, order)
    now = stack.world.clock.now
    for kind, row in (("position", pos), ("order", order)):
        ev = await _message(stack.world.sessions, stack.settings, kind, row.id, now)
        assert ev is not None and ev.event == kind and kind in ev.data
    assert await _message(stack.world.sessions, stack.settings, "trade", uuid4(), now) is None


# --- fermeture et annulation --------------------------------------------------------------


@pytest.mark.parametrize("intent", get_args(Intent))
async def test_annuler_un_ordre_seulement_si_c_est_une_entree(stack: Stack, intent: str) -> None:
    c = await stack.client("operator")
    inst = await _instance(stack)
    order = await _row(stack, _order(inst, intent))
    r = await c.delete(f"/api/v1/orders/{order.id}", headers=_key())
    cmds = await _commands(stack, inst.id, "cancel_entry_order")
    if intent == "entry":  # les renforts sont désactivés en V1 : le worker les refuse aussi
        assert r.status_code == 202, r.text
        assert [x.args for x in cmds] == [{"order_id": order.client_order_id}]
        assert r.json()["command_id"] == str(cmds[0].id)
    else:
        assert r.status_code == 409 and "Seul un ordre d'entrée" in r.json()["detail"]
        assert cmds == []


async def test_annuler_un_ordre_deja_clos_ou_inconnu_est_refuse(stack: Stack) -> None:
    c = await stack.client("operator")
    inst = await _instance(stack)
    done = await _row(stack, _order(inst, "entry", status="filled"))
    assert (await c.delete(f"/api/v1/orders/{done.id}", headers=_key())).status_code == 409
    assert (await c.delete(f"/api/v1/orders/{uuid4()}", headers=_key())).status_code == 404


@pytest.mark.parametrize("stale", [False, True])
async def test_fermeture_acceptee_meme_si_l_etat_observe_est_inconnu_ou_perime(
    stack: Stack, stale: bool
) -> None:
    c = await stack.client("operator")
    inst = await _instance(stack)
    if stale:
        async with stack.world.sessions.begin() as s:
            row = await s.get(Instance, inst.id)
            assert row is not None
            row.observed_state = "running"
            row.observed_at = stack.world.clock.now - timedelta(hours=1)
    pos = await _row(stack, _position(inst))
    h = _key()
    r = await c.post(f"/api/v1/positions/{pos.id}/close", headers=h)
    assert r.status_code == 202, r.text
    cmds = await _commands(stack, inst.id, "close_position")
    assert [x.args for x in cmds] == [{"position_id": pos.external_id}]
    again = await c.post(f"/api/v1/positions/{pos.id}/close", headers=h)
    assert again.headers["Idempotency-Replayed"] == "true"
    assert len(await _commands(stack, inst.id, "close_position")) == 1
    assert (await c.post(f"/api/v1/positions/{uuid4()}/close", headers=_key())).status_code == 404


async def test_rbac_viewer_refuse_et_audit_avec_auteur(stack: Stack) -> None:
    inst = await _instance(stack)
    pos = await _row(stack, _position(inst))
    order = await _row(stack, _order(inst, "entry"))
    v = await stack.client("viewer")
    assert (await v.post(f"/api/v1/positions/{pos.id}/close", headers=_key())).status_code == 403
    assert (await v.delete(f"/api/v1/orders/{order.id}", headers=_key())).status_code == 403
    assert (await v.post(I, json=_body(uuid4(), uuid4()), headers=_key())).status_code == 403
    o = await stack.client("operator")
    me = (await o.get("/api/v1/auth/me")).json()
    assert (await o.post(f"/api/v1/positions/{pos.id}/close", headers=_key())).status_code == 202
    assert (await o.delete(f"/api/v1/orders/{order.id}", headers=_key())).status_code == 202
    async with stack.world.sessions() as s:
        rows = list(
            await s.scalars(select(AuditLog).where(AuditLog.target == f"instance:{inst.id}"))
        )
    assert {r.action for r in rows} == {"command.close_position", "command.cancel_entry_order"}
    assert all(r.actor == f"user:{me['id']}" for r in rows)


async def test_openapi_sans_nom_de_moteur_ni_creation_d_ordre(stack: Stack) -> None:
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=stack.app), base_url="http://t")
    spec = (await c.get("/api/v1/openapi.json")).json()
    await c.aclose()
    assert "freqtrade" not in str(spec).lower()
    assert "post" not in spec["paths"]["/api/v1/orders"]
    assert set(spec["paths"]["/api/v1/orders/{order_id}"]) == {"delete"}
    assert not [
        p for p in spec["paths"] if p.startswith("/api/v1/orders/") and "post" in spec["paths"][p]
    ]


async def test_lignes_portent_le_mode_voulu_et_le_mode_observe_distincts(stack: Stack) -> None:
    c = await stack.client("viewer")
    seen = stack.world.clock.now
    inst = await _instance(stack, observed_mode="live", observed_at=seen)
    await _row(stack, _position(inst, observed_at=seen))
    await _row(stack, _order(inst, "entry"))
    for path in ("positions", "orders"):
        (row,) = (await get(c, f"/api/v1/{path}?instance_id={inst.id}"))["items"]
        assert row["desired_mode"] == row["mode"] == "paper"
        assert row["observed_mode"]["value"] == "live"
        assert (
            row["observed_mode"]["observed_at"] is not None
            and row["observed_mode"]["stale"] is False
        )


async def test_cancelable_seulement_pour_une_entree_ouverte(stack: Stack) -> None:
    c = await stack.client("viewer")
    inst = await _instance(stack)
    for intent in get_args(Intent):
        await _row(stack, _order(inst, intent))
    rows = (await get(c, f"/api/v1/orders?instance_id={inst.id}"))["items"]
    assert {r["intent"] for r in rows if r["cancelable"]} == {"entry"}
