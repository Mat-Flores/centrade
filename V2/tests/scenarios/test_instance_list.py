"""Instance list of the new interface: strategy, account and start time on each row (§8, §9).

`started_at` is the last verified `deploy` or `start` command, shown only while the observed state
says the instance runs. Sentinel values, FakeEngine only.
"""

from decimal import Decimal
from typing import Any
from uuid import uuid4

from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.ids import uuid7
from centrade_core.models.trading import (
    Account,
    Engine,
    Instance,
    Position,
    Strategy,
    StrategyVersion,
    Trade,
)
from centrade_fake.engine import Failure
from sqlalchemy import event, select

I = "/api/v1/instances"  # noqa: E741


async def _registry(stack: Stack) -> dict[str, str]:
    """An approved fake strategy version and a paper account: a registry creation body."""
    sid, vid, aid = uuid7(), uuid7(), uuid7()
    manifest = {
        "name": "s",
        "engine": "fake",
        "version": 1,
        "entrypoint": "s.py",
        "asset_classes": ["crypto"],
        "trading_mode": "spot",
        "timeframes": ["5m"],
        "modes": ["paper"],
        "params_schema": {"type": "object", "properties": {}},
        "sizing": {"stake_amount": "50", "max_open_positions": 3},
        "exits": {"stoploss": "-0.05", "stop_on_venue": True},
    }
    async with stack.world.sessions.begin() as s:
        s.add(Strategy(id=sid, name=f"s-{uuid4().hex[:8]}"))
        await s.flush()
        s.add(
            StrategyVersion(
                id=vid,
                strategy_id=sid,
                version=1,
                manifest=manifest,
                code="pass",
                code_hash="h" * 8,
                status="approved",
                author="user:test",
                exits={"stoploss": "-0.05"},
            )
        )
        s.add(
            Account(
                id=aid,
                venue="venue-test",
                type="paper",
                environment="sandbox",
                label="Compte de test",
                currency="USDT",
            )
        )
    return {
        "name": f"i-{uuid4().hex[:10]}",
        "strategy_version_id": str(vid),
        "account_id": str(aid),
    }


def _item(page: dict[str, Any], iid: str) -> dict[str, Any]:
    return next(i for i in page["items"] if i["id"] == iid)


async def test_list_rows_carry_the_strategy_and_account_of_a_registry_instance(
    stack: Stack,
) -> None:
    c = await stack.client("operator")
    body = await _registry(stack)
    r = await c.post(I, json=body, headers={"Idempotency-Key": uuid4().hex})
    assert r.status_code == 201, r.text
    simulated = await create_instance(c)

    page = await get(c, I)
    row = _item(page, r.json()["id"])
    assert row["strategy"]["version_id"] == body["strategy_version_id"]
    assert row["strategy"]["exits"] == {"stoploss": "-0.05"} and row["strategy"]["version"] == 1
    assert row["account"]["id"] == body["account_id"]
    assert row["account"]["label"] == "Compte de test" and "secret" not in str(row["account"])
    assert row["engine"] == "fake"
    plain = _item(page, simulated["id"])
    assert plain["strategy"] is None and plain["account"] is None

    only = await get(c, f"{I}?strategy_id={row['strategy']['strategy_id']}")
    assert [i["id"] for i in only["items"]] == [row["id"]]  # the filter drops the simulated one

    detail = await get(c, f"{I}/{row['id']}")
    assert (detail["strategy"], detail["account"]) == (row["strategy"], row["account"])


async def test_started_at_is_the_last_verified_start_while_the_instance_runs(
    stack: Stack,
) -> None:
    c = await stack.client("operator")
    created = await create_instance(c)
    assert created["started_at"] is None  # never observed
    assert _item(await get(c, I), created["id"])["started_at"] is None

    await stack.world.worker.run_once()  # deploy verified, observed exits_only
    verified = await get(c, f"/api/v1/commands?instance_id={created['id']}&status=verified")
    deploy = next(x for x in verified["items"] if x["type"] == "deploy")
    row = _item(await get(c, I), created["id"])
    assert row["state"]["value"] == "exits_only"
    assert row["started_at"] == deploy["verified_at"]

    assert (await act(c, created["id"], "stop")).status_code == 202
    await stack.world.worker.run_once()
    row = _item(await get(c, I), created["id"])
    assert row["state"]["value"] == "stopped" and row["started_at"] is None

    stack.world.clock.advance(60)
    await stack.world.worker.run_once()  # fresh observation: a start needs one (I5)
    assert (await act(c, created["id"], "start")).status_code == 202
    await stack.world.worker.run_once()
    verified = await get(c, f"/api/v1/commands?instance_id={created['id']}&status=verified")
    start = next(x for x in verified["items"] if x["type"] == "start")
    row = _item(await get(c, I), created["id"])
    assert row["state"]["value"] == "exits_only"
    assert row["started_at"] == start["verified_at"] != deploy["verified_at"]
    assert (await get(c, f"{I}/{created['id']}"))["started_at"] == row["started_at"]


async def test_started_at_is_none_when_the_observed_state_is_unknown(stack: Stack) -> None:
    c = await stack.client("operator")
    created = await create_instance(c)
    await stack.world.worker.run_once()
    assert _item(await get(c, I), created["id"])["started_at"] is not None

    stack.world.fake.set_failure(ref_of(created["id"]), Failure.SILENT)
    await stack.world.worker.run_once()
    row = _item(await get(c, I), created["id"])
    assert row["state"]["value"] == "unknown" and row["started_at"] is None


async def _bulk(stack: Stack, n: int) -> None:
    """`n` observed instances, each with a closed trade in two currencies and an open position."""
    now = stack.world.clock.now
    async with stack.world.sessions.begin() as s:
        engine = await s.scalar(select(Engine).where(Engine.kind == "fake"))
        assert engine is not None
        for k in range(n):
            iid = uuid7()
            s.add(
                Instance(
                    id=iid, engine_id=engine.id, name=f"bulk-{k}-{uuid4().hex[:6]}", mode="paper",
                    desired_state="running", observed_state="running", observed_mode="paper",
                    observed_at=now,
                )
            )  # fmt: skip
            await s.flush()
            for cur in ("USDT", "EUR"):
                s.add(
                    Trade(
                        id=uuid7(), instance_id=iid, external_id=f"t-{cur}", instrument=f"X/{cur}",
                        quantity=Decimal("1"), entry_price=Decimal("1"), exit_price=Decimal("2"),
                        entry_cause="signal", exit_cause="signal", pnl=Decimal("0.9"),
                        fees=Decimal("0.1"), currency=cur, opened_at=now, closed_at=now,
                        duration_s=0,
                    )
                )  # fmt: skip
            s.add(
                Position(
                    id=uuid7(), instance_id=iid, external_id="p", instrument="X/USDT", side="long",
                    quantity=Decimal("1"), entry_price=Decimal("1"), currency="USDT",
                    observed_at=now,
                )
            )  # fmt: skip


async def test_listing_200_instances_takes_a_fixed_number_of_queries(stack: Stack) -> None:
    c = await stack.client("viewer")
    await _bulk(stack, 200)
    seen: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        seen.append(statement)

    TABLES = ("instances", "commands", "trades", "positions", "strategy_versions", "accounts")

    async def count(path: str) -> tuple[int, int, dict[str, Any]]:
        seen.clear()
        page = await get(c, path)
        listing = [q for q in seen if any(f"FROM {t}" in q for t in TABLES)]
        return len(seen), len(listing), page

    event.listen(stack.world.db.sync_engine, "before_cursor_execute", record)
    try:
        total_one, listing_one, _ = await count(f"{I}?limit=1")
        total_all, listing_all, page = await count(f"{I}?limit=200")
    finally:
        event.remove(stack.world.db.sync_engine, "before_cursor_execute", record)
    assert len(page["items"]) == 200
    assert listing_all <= 5 and total_all == total_one and listing_all == listing_one
    row = page["items"][0]
    assert row["realized_pnl"]["value"] == [
        {"currency": "EUR", "amount": "0.9", "fees": "0.1"},
        {"currency": "USDT", "amount": "0.9", "fees": "0.1"},
    ]
    assert (row["closed_trades"]["value"], row["open_positions"]["value"]) == (2, 1)


async def test_instance_detail_keeps_its_fields_and_matches_the_list_row(stack: Stack) -> None:
    c = await stack.client("operator")
    body = await _registry(stack)
    r = await c.post(I, json=body, headers={"Idempotency-Key": uuid4().hex})
    assert r.status_code == 201, r.text
    await stack.world.worker.run_once()

    row = _item(await get(c, I), r.json()["id"])
    detail = await get(c, f"{I}/{row['id']}")
    extra = {"deployment_fingerprint", "config_hash", "engine_version", "effective_config", "drift"}
    assert set(detail) == set(row) | extra
    assert {k: detail[k] for k in row} == row
