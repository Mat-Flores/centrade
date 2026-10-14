"""I1: every displayed state is observed and dated; stale beyond the threshold; unknown is displayed
as unknown; the wanted state is never presented as real (SPEC §1.2, §9)."""

from decimal import Decimal
from uuid import UUID

from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.engine.types import ClosedTrade, InstanceStatus, Position, Snapshot
from centrade_fake.engine import SYMBOL, Failure
from centrade_worker.projection import apply_observation
from centrade_worker.testing import T0


async def test_i01_displayed_state_carries_observation_timestamp(stack: Stack) -> None:
    c = await stack.client("operator")
    created = await create_instance(c)
    await stack.world.worker.run_once()  # deployment, then first snapshot

    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["state"]["value"] == "exits_only"
    assert inst["state"]["observed_at"] == T0.isoformat().replace("+00:00", "Z")
    assert inst["observed_mode"]["value"] == "paper" and inst["observed_mode"]["observed_at"]
    assert inst["server_time"] and inst["state"]["stale"] is False
    page = await get(c, "/api/v1/instances")
    assert page["server_time"] and any(i["id"] == created["id"] for i in page["items"])


async def test_i01_state_is_stale_beyond_threshold(stack: Stack) -> None:
    c = await stack.client("operator")
    created = await create_instance(c)
    await stack.world.worker.run_once()
    stack.world.clock.advance(stack.settings.observed_stale_after_s - 1)
    assert (await get(c, f"/api/v1/instances/{created['id']}"))["state"]["stale"] is False

    stack.world.clock.advance(2)  # the worker no longer runs: the value ages
    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["state"]["stale"] is True and inst["observed_mode"]["stale"] is True
    assert inst["state"]["value"] == "exits_only"  # the value keeps its date, never "current"
    assert inst["state"]["observed_at"] and inst["server_time"] > inst["state"]["observed_at"]


async def test_i01_unknown_state_is_displayed_as_unknown(stack: Stack) -> None:
    c = await stack.client("operator")
    created = await create_instance(c, failures=["silent"])
    await stack.world.worker.run_once()

    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["state"]["value"] == "unknown" and inst["observed_mode"]["value"] == "unknown"

    # A healthy instance, then silent: no last known value any more.
    healthy = await create_instance(c)
    await stack.world.worker.run_once()
    stack.world.fake.set_failure(ref_of(healthy["id"]), Failure.SILENT)
    await stack.world.worker.run_once()
    after = await get(c, f"/api/v1/instances/{healthy['id']}")
    assert after["state"]["value"] == "unknown" and after["observed_mode"]["value"] == "unknown"


async def test_i01_desired_state_is_never_shown_as_observed(stack: Stack) -> None:
    c = await stack.client("operator")
    created = await create_instance(c)  # never observed: the worker did not run
    assert created["desired_state"] == "exits_only"
    assert created["state"] == {"value": "unknown", "observed_at": None, "stale": False}

    await stack.world.worker.run_once()
    r = await act(c, created["id"], "resume-entries")
    assert r.status_code == 202
    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["desired_state"] == "running"  # wanted state changed immediately...
    assert inst["state"]["value"] == "exits_only"  # ...observed unchanged until seen
    assert inst["active_command"]["status"] == "requested"

    await stack.world.worker.run_once()
    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["state"]["value"] == "running" and inst["active_command"] is None


UNKNOWN = {"value": None, "observed_at": None, "stale": False}
AGGREGATES = ("realized_pnl", "closed_trades", "open_positions")


async def test_i01_aggregates_are_unknown_when_engine_never_observed(stack: Stack) -> None:
    c = await stack.client("operator")
    created = await create_instance(c)  # the worker has not run: never observed
    assert all(created[k] == UNKNOWN for k in AGGREGATES)
    listed = next(
        i for i in (await get(c, "/api/v1/instances"))["items"] if i["id"] == created["id"]
    )
    assert all(listed[k] == UNKNOWN for k in AGGREGATES)

    # Unreachable from the start: the instance row gets a fresh date with an `unknown` state,
    # which must not date the aggregates (no zero presented as observed).
    silent = await create_instance(c, failures=["silent"])
    await stack.world.worker.run_once()
    inst = await get(c, f"/api/v1/instances/{silent['id']}")
    assert inst["state"]["value"] == "unknown" and inst["state"]["observed_at"] is not None
    assert all(inst[k]["value"] is None and inst[k]["observed_at"] is None for k in AGGREGATES)


async def test_i01_aggregates_are_stale_beyond_threshold(stack: Stack) -> None:
    w, c = stack.world, await stack.client("operator")
    created = await create_instance(c)
    await w.worker.run_once()
    fresh = await get(c, f"/api/v1/instances/{created['id']}")
    at = fresh["state"]["observed_at"]
    assert fresh["realized_pnl"] == {"value": [], "observed_at": at, "stale": False}
    assert fresh["closed_trades"] == {"value": 0, "observed_at": at, "stale": False}
    assert fresh["open_positions"] == {"value": 0, "observed_at": at, "stale": False}

    seen = w.clock.now
    snap = Snapshot(
        positions=(
            Position(
                position_id="open-1", symbol=SYMBOL, side="buy", qty=Decimal("1"),
                entry_price=Decimal("100"), opened_at=seen,
            ),
        ),
        orders=(), balances=(), stops=(), observed_at=seen,
        closed=(
            ClosedTrade(
                position_id="closed-1", symbol=SYMBOL, side="buy", qty=Decimal("1"),
                entry_price=Decimal("100"), exit_price=Decimal("90"), pnl=Decimal("-10.1"),
                fees=Decimal("0.1"), exit_cause="stop_loss", opened_at=seen, closed_at=seen,
            ),
        ),
    )  # fmt: skip
    async with w.sessions.begin() as s:
        await apply_observation(
            s,
            UUID(created["id"]),
            InstanceStatus(state="exits_only", mode="paper", observed_at=seen),
            snap,
        )
    w.fake.set_failure(ref_of(created["id"]), Failure.SILENT)  # the engine stops answering
    w.clock.advance(stack.settings.observed_stale_after_s + 1)

    inst = await get(c, f"/api/v1/instances/{created['id']}")
    money = [{"currency": "USDT", "amount": "-10.1", "fees": "0.1"}]
    assert inst["realized_pnl"]["value"] == money and inst["realized_pnl"]["stale"] is True
    assert inst["closed_trades"]["value"] == 1 and inst["open_positions"]["value"] == 1
    assert all(inst[k]["stale"] is True for k in AGGREGATES)

    await w.worker.run_once()  # unreachable: `unknown` state with a fresh date on the instance
    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["state"]["value"] == "unknown"
    stale_at = inst["open_positions"]["observed_at"]
    assert stale_at is not None and stale_at < inst["state"]["observed_at"]  # last value, its date
    assert inst["realized_pnl"]["value"] == money and inst["open_positions"]["value"] == 1
    assert all(inst[k]["stale"] is True and inst[k]["observed_at"] == stale_at for k in AGGREGATES)


async def test_i01_balance_never_observed_is_unknown_not_zero(stack: Stack) -> None:
    w, c = stack.world, await stack.client("operator")
    created = await create_instance(c)  # the worker has not run: never observed
    assert created["balances"] == UNKNOWN
    listed = next(
        i for i in (await get(c, "/api/v1/instances"))["items"] if i["id"] == created["id"]
    )
    assert listed["balances"] == UNKNOWN

    silent = await create_instance(c, failures=["silent"])  # unreachable from the start
    await w.worker.run_once()
    assert (await get(c, f"/api/v1/instances/{silent['id']}"))["balances"] == UNKNOWN

    # A snapshot without any balance is indistinguishable from "never observed": unknown, not 0.
    async with w.sessions.begin() as s:
        await apply_observation(
            s,
            UUID(created["id"]),
            InstanceStatus(state="exits_only", mode="paper", observed_at=w.clock.now),
            Snapshot(positions=(), orders=(), balances=(), stops=(), observed_at=w.clock.now),
        )
    assert (await get(c, f"/api/v1/instances/{created['id']}"))["balances"] == UNKNOWN


async def test_i01_balance_is_stale_beyond_threshold(stack: Stack) -> None:
    w, c = stack.world, await stack.client("operator")
    created = await create_instance(c)
    await w.worker.run_once()
    fresh = await get(c, f"/api/v1/instances/{created['id']}")
    usdt = [{"currency": "USDT", "free": "1000", "total": "1000"}]  # FakeEngine balance
    assert fresh["balances"] == {
        "value": usdt, "observed_at": fresh["state"]["observed_at"], "stale": False
    }  # fmt: skip

    w.fake.set_failure(ref_of(created["id"]), Failure.SILENT)  # the engine stops answering
    w.clock.advance(stack.settings.observed_stale_after_s + 1)
    await w.worker.run_once()  # unreachable: state unknown, the balance rows stay

    inst = await get(c, f"/api/v1/instances/{created['id']}")
    assert inst["state"]["value"] == "unknown"
    # Last value, with its own (old) date, marked stale: never presented as current.
    assert inst["balances"] == {
        "value": usdt, "observed_at": fresh["balances"]["observed_at"], "stale": True
    }  # fmt: skip
