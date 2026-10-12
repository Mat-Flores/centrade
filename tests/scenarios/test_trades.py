"""Projection des trades clos (SPEC §6, §7, F10) : du moteur à `GET /trades`."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.engine.types import ClosedTrade, InstanceStatus, Snapshot
from centrade_core.models.trading import Trade
from centrade_fake.engine import SYMBOL
from centrade_worker.projection import apply_observation
from sqlalchemy import select

T0 = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _closed(**over: Any) -> ClosedTrade:
    base: dict[str, Any] = {
        "position_id": "p1",
        "symbol": SYMBOL,
        "side": "buy",
        "qty": Decimal("0.5"),
        "entry_price": Decimal("100"),
        "exit_price": Decimal("110"),
        "pnl": Decimal("5"),
        "fees": Decimal("0.1"),
        "exit_cause": "take_profit",
        "opened_at": T0,
        "closed_at": T0 + timedelta(seconds=90),
    }
    return ClosedTrade(**{**base, **over})


async def _apply(stack: Stack, iid: str, *closed: ClosedTrade) -> list[tuple[str, UUID]]:
    snap = Snapshot(positions=(), orders=(), balances=(), stops=(), observed_at=T0, closed=closed)
    status = InstanceStatus(state="running", mode="paper", observed_at=T0)
    async with stack.world.sessions.begin() as s:
        return await apply_observation(s, UUID(iid), status, snap)


async def _rows(stack: Stack, iid: str) -> list[Trade]:
    async with stack.world.sessions() as s:
        return list(await s.scalars(select(Trade).where(Trade.instance_id == UUID(iid))))


async def test_position_close_devient_une_ligne_avec_sa_cause(stack: Stack) -> None:
    iid = str((await create_instance(await stack.client("operator")))["id"])
    notes = await _apply(stack, iid, _closed())
    (t,) = await _rows(stack, iid)
    assert (t.exit_cause, t.pnl, t.fees, t.currency, t.duration_s) == (
        "take_profit",
        Decimal("5"),
        Decimal("0.1"),
        "USDT",
        90,
    )
    assert notes == [("trade", t.id)]
    assert await _apply(stack, iid, _closed()) == []  # revu : une ligne, rien à annoncer
    assert len(await _rows(stack, iid)) == 1


async def test_cause_inconnue_ou_absente_est_unknown(stack: Stack) -> None:
    iid = str((await create_instance(await stack.client("operator")))["id"])
    await _apply(
        stack,
        iid,
        _closed(position_id="a", exit_cause="inventee"),
        _closed(position_id="b", exit_cause=None),
    )
    rows = await _rows(stack, iid)
    assert {t.exit_cause for t in rows} == {"unknown"}
    assert {t.entry_cause for t in rows} == {"unknown"}


async def test_trade_clos_du_moteur_visible_dans_get_trades_avec_cause_et_mode(
    stack: Stack,
) -> None:
    w = stack.world
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    ref = ref_of(iid)
    await w.worker.run_once()
    assert (await act(c, iid, "resume-entries")).status_code == 202
    await w.worker.run_once()
    for _ in range(500):
        w.step(ref, 1)
        if (await w.fake.snapshot(ref)).closed:
            break
    else:
        raise AssertionError("aucune position close : le test ne prouverait rien")
    await w.worker.run_once()
    items = (await get(c, f"/api/v1/trades?instance_id={iid}"))["items"]
    closed = (await w.fake.snapshot(ref)).closed
    assert len(items) == len(closed) >= 1
    assert {i["mode"] for i in items} == {"paper"}
    assert {i["exit_cause"] for i in items} == {x.exit_cause for x in closed}
