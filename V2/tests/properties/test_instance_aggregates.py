"""Aggregates of the instance list reconcile with `GET /trades` (I1, §9): per currency, the net
realized PnL and the fees are the exact Decimal sums of the instance's trade rows, and the count is
the number of rows. Never a float, never an addition across currencies."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, localcontext
from uuid import UUID

from centrade_api.testing import Stack, create_instance, get
from centrade_core.engine.types import ClosedTrade, InstanceStatus, Snapshot
from centrade_worker.projection import apply_observation
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

CURRENCIES = ("USDT", "EUR", "BTC")
# NUMERIC(38, 18): 18 places, and room left for a sum of a few rows.
MONEY = st.decimals(
    min_value=Decimal("-1e12"), max_value=Decimal("1e12"), places=18, allow_nan=False
)
TRADE = st.tuples(st.sampled_from(CURRENCIES), MONEY, MONEY.map(abs))


def _canonical(s: str) -> bool:
    """Plain decimal notation, no exponent, no trailing zero after the point."""
    whole, _, frac = s.removeprefix("-").partition(".")
    no_padding = (whole == "0" or not whole.startswith("0")) and not frac.endswith("0")
    return "E" not in s.upper() and s != "-0" and whole.isdigit() and no_padding and s[-1] != "."


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(trades=st.lists(TRADE, max_size=12))
async def test_list_aggregates_equal_the_decimal_sums_of_the_instance_trades(
    stack: Stack, trades: list[tuple[str, Decimal, Decimal]]
) -> None:
    c = await stack.client("operator")
    iid = (await create_instance(c))["id"]
    now = stack.world.clock.now
    closed = tuple(
        ClosedTrade(
            position_id=f"p{n}", symbol=f"crypto:fake:X/{cur}", side="buy", qty=Decimal("1"),
            entry_price=Decimal("1"), exit_price=Decimal("1"), pnl=pnl, fees=fees,
            opened_at=now - timedelta(minutes=1), closed_at=now,
        )
        for n, (cur, pnl, fees) in enumerate(trades)
    )  # fmt: skip
    snap = Snapshot(positions=(), orders=(), balances=(), stops=(), observed_at=now, closed=closed)
    status = InstanceStatus(state="running", mode="paper", observed_at=now)
    async with stack.world.sessions.begin() as s:
        await apply_observation(s, UUID(iid), status, snap)

    rows = (await get(c, f"/api/v1/trades?instance_id={iid}&limit=200"))["items"]
    page = await get(c, "/api/v1/instances?limit=200")
    item = next(i for i in page["items"] if i["id"] == iid)

    from_rows: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    from_input: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    with localcontext(prec=60):  # the default 28 digits would round these sums
        for t in rows:
            from_rows[t["currency"]][0] += Decimal(t["pnl"])
            from_rows[t["currency"]][1] += Decimal(t["fees"])
        for cur, pnl, fees in trades:
            from_input[cur][0] += pnl
            from_input[cur][1] += fees

    money = item["realized_pnl"]["value"]
    assert (
        item["realized_pnl"]["observed_at"] is not None and item["realized_pnl"]["stale"] is False
    )
    got = {m["currency"]: [Decimal(m["amount"]), Decimal(m["fees"])] for m in money}
    assert got == from_rows == from_input  # exact: no rounding, no float
    assert [m["currency"] for m in money] == sorted(got)  # one entry per currency, stable order
    assert all(_canonical(m["amount"]) and _canonical(m["fees"]) for m in money), money
    assert item["closed_trades"]["value"] == len(rows) == len(trades)
    assert item["open_positions"]["value"] == 0
    detail = await get(c, f"/api/v1/instances/{iid}")
    assert detail["realized_pnl"] == item["realized_pnl"]
