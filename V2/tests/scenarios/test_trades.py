"""Closed trades projection (SPEC §6, §7, F10): from the engine to `GET /trades`."""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.engine.types import EXIT_CAUSES, ClosedTrade, InstanceStatus, Snapshot
from centrade_core.models.trading import Trade
from centrade_fake.engine import SYMBOL
from centrade_worker.projection import apply_observation
from sqlalchemy import select, text

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
        "entry_cause": "signal",
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


async def test_closed_position_becomes_a_row_with_its_cause(stack: Stack) -> None:
    iid = str((await create_instance(await stack.client("operator")))["id"])
    notes = await _apply(stack, iid, _closed())
    (t,) = await _rows(stack, iid)
    assert (t.instance_id, t.external_id, t.instrument) == (UUID(iid), "p1", SYMBOL)
    assert (t.quantity, t.entry_price, t.exit_price) == (
        Decimal("0.5"),
        Decimal("100"),
        Decimal("110"),
    )
    assert (t.entry_cause, t.exit_cause, t.pnl, t.fees, t.currency) == (
        "signal",
        "take_profit",
        Decimal("5"),
        Decimal("0.1"),
        "USDT",
    )
    assert (t.opened_at, t.closed_at, t.duration_s) == (T0, T0 + timedelta(seconds=90), 90)
    assert notes == [("trade", t.id)]
    assert await _apply(stack, iid, _closed()) == []  # seen again: one row, nothing to announce
    assert len(await _rows(stack, iid)) == 1


async def test_unknown_or_missing_cause_is_unknown(stack: Stack) -> None:
    iid = str((await create_instance(await stack.client("operator")))["id"])
    await _apply(
        stack,
        iid,
        _closed(position_id="a", exit_cause="inventee", entry_cause=None),
        _closed(position_id="b", exit_cause=None, entry_cause=None),
    )
    rows = await _rows(stack, iid)
    assert {t.exit_cause for t in rows} == {"unknown"}
    assert {t.entry_cause for t in rows} == {"unknown"}


async def test_engine_closed_trade_is_visible_in_get_trades_with_cause_and_mode(
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
    by_id = {x.position_id: x for x in closed}
    rows = {t.external_id: t for t in await _rows(stack, iid)}
    assert rows.keys() == by_id.keys()
    for pid, x in by_id.items():
        t = rows[pid]
        assert (t.instrument, t.quantity, t.entry_price, t.exit_price) == (
            x.symbol,
            x.qty,
            x.entry_price,
            x.exit_price,
        )
        assert (t.pnl, t.fees, t.opened_at, t.closed_at) == (
            x.pnl,
            x.fees,
            x.opened_at,
            x.closed_at,
        )
        assert x.exit_price != x.entry_price and x.pnl != 0 and x.fees > 0
        assert t.pnl == (t.exit_price - t.entry_price) * t.quantity


async def test_exit_cause_db_constraint_equals_exit_causes(stack: Stack) -> None:
    async with stack.world.sessions() as s:
        defs = (
            await s.scalars(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = 'trades'::regclass AND contype = 'c'"
                )
            )
        ).all()
    (check,) = [d for d in defs if "exit_cause" in d]
    assert set(re.findall(r"'([a-z_]+)'", check)) == set(EXIT_CAUSES)


@pytest.mark.parametrize(
    ("query", "index"),
    [
        (
            "SELECT * FROM trades ORDER BY closed_at DESC, id DESC LIMIT 51",
            "ix_trades_closed_at_id",
        ),
        (
            "SELECT * FROM orders ORDER BY created_at DESC, id DESC LIMIT 51",
            "ix_orders_created_at_id",
        ),
    ],
)
async def test_paged_sort_uses_its_index(stack: Stack, query: str, index: str) -> None:
    async with stack.world.sessions.begin() as s:
        await s.execute(text("SET LOCAL enable_seqscan = off"))  # empty tables
        plan = "\n".join((await s.scalars(text("EXPLAIN " + query))).all())
    assert index in plan, plan
