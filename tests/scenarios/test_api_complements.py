"""Compléments de lecture demandés par les écrans : filtre `strategy_id`, compte sur les lignes de
trading, version du moteur observée (datée) ou inconnue."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from centrade_api.testing import Stack, get
from centrade_core.ids import uuid7
from centrade_core.models.trading import (
    Account,
    Engine,
    Instance,
    Order,
    Position,
    Strategy,
    StrategyVersion,
    Trade,
)
from sqlalchemy import select

I = "/api/v1/instances"  # noqa: E741


async def _instance(stack: Stack, *, strategy: bool, account: bool, **over: object) -> Instance:
    async with stack.world.sessions.begin() as s:
        eng = await s.scalar(select(Engine).where(Engine.kind == "fake"))
        assert eng is not None
        extra: dict[str, object] = {}
        if strategy:
            sid, vid = uuid7(), uuid7()
            s.add(Strategy(id=sid, name=f"s-{uuid4().hex[:8]}"))
            await s.flush()
            s.add(
                StrategyVersion(
                    id=vid,
                    strategy_id=sid,
                    version=1,
                    manifest={},
                    code="pass",
                    code_hash="h",
                    status="approved",
                    author="user:test",
                    exits={},
                )
            )
            await s.flush()
            extra["strategy_version_id"] = vid
        if account:
            aid = uuid7()
            s.add(
                Account(
                    id=aid,
                    venue="venue-test",
                    type="paper",
                    environment="sandbox",
                    label="Compte A",
                    currency="USDT",
                )
            )
            await s.flush()
            extra["account_id"] = aid
        inst = Instance(
            id=uuid7(),
            engine_id=eng.id,
            name=f"i-{uuid4().hex[:10]}",
            mode="paper",
            desired_state="exits_only",
            observed_state="unknown",
            **extra,
            **over,
        )
        s.add(inst)
    return inst


async def _strategy_of(stack: Stack, inst: Instance) -> UUID:
    async with stack.world.sessions() as s:
        v = await s.get(StrategyVersion, inst.strategy_version_id)
        assert v is not None
        return v.strategy_id


async def test_filtre_strategy_id_ne_rend_que_les_instances_de_la_strategie(stack: Stack) -> None:
    await stack.world.worker.run_once()  # assure la ligne `engines` du moteur simulé
    a = await _instance(stack, strategy=True, account=False)
    await _instance(stack, strategy=True, account=False)
    await _instance(stack, strategy=False, account=False)
    c = await stack.client("viewer")
    sid = await _strategy_of(stack, a)
    items = (await get(c, f"{I}?strategy_id={sid}"))["items"]
    assert [i["id"] for i in items] == [str(a.id)]
    assert (await get(c, f"{I}?strategy_id={uuid4()}"))["items"] == []
    assert len((await get(c, I))["items"]) >= 3


async def test_lignes_de_trading_portent_le_compte(stack: Stack) -> None:
    await stack.world.worker.run_once()
    with_acc = await _instance(stack, strategy=False, account=True)
    without = await _instance(stack, strategy=False, account=False)
    now = stack.world.clock.now
    async with stack.world.sessions.begin() as s:
        for inst in (with_acc, without):
            s.add(
                Position(
                    id=uuid7(),
                    instance_id=inst.id,
                    external_id=uuid4().hex[:6],
                    instrument="BTC/USDT",
                    side="long",
                    quantity=Decimal(1),
                    entry_price=Decimal(1),
                    currency="USDT",
                    observed_at=now,
                )
            )
            s.add(
                Order(
                    id=uuid7(),
                    instance_id=inst.id,
                    client_order_id=str(uuid4()),
                    instrument="BTC/USDT",
                    side="buy",
                    intent="entry",
                    status="open",
                    quantity=Decimal(1),
                    price=Decimal(1),
                    currency="USDT",
                    observed_at=now,
                )
            )
            s.add(
                Trade(
                    id=uuid7(),
                    instance_id=inst.id,
                    external_id=uuid4().hex[:6],
                    instrument="BTC/USDT",
                    quantity=Decimal(1),
                    entry_price=Decimal(1),
                    exit_price=Decimal(1),
                    entry_cause="signal",
                    exit_cause="signal",
                    pnl=Decimal(0),
                    fees=Decimal(0),
                    currency="USDT",
                    opened_at=now,
                    closed_at=now + timedelta(seconds=1),
                    duration_s=1,
                )
            )
    c = await stack.client("viewer")
    for path in ("orders", "positions", "trades"):
        rows = {r["instance_id"]: r for r in (await get(c, f"/api/v1/{path}?limit=200"))["items"]}
        assert rows[str(with_acc.id)]["account_id"] == str(with_acc.account_id)
        assert rows[str(with_acc.id)]["account_label"] == "Compte A"
        assert rows[str(without.id)]["account_id"] is None
        assert rows[str(without.id)]["account_label"] is None


async def test_version_du_moteur_datee_ou_inconnue(stack: Stack) -> None:
    await stack.world.worker.run_once()
    at = stack.world.clock.now
    seen = await _instance(
        stack,
        strategy=False,
        account=False,
        effective_config={"engine_version": "2026.9", "max_open_positions": "3"},
        effective_config_at=at,
    )
    never = await _instance(stack, strategy=False, account=False)
    c = await stack.client("viewer")
    v = (await get(c, f"{I}/{seen.id}"))["engine_version"]
    assert v["value"] == "2026.9"
    assert v["observed_at"] is not None
    unknown = (await get(c, f"{I}/{never.id}"))["engine_version"]
    assert unknown == {"value": None, "observed_at": None, "stale": False}
