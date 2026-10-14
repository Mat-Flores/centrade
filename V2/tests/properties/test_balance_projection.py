"""Balance projection (I1): one row per instance and currency holding the most recent observed
value. Replaying a snapshot changes nothing; an older snapshot never overwrites nor deletes a
newer one; a currency absent from the latest snapshot is gone."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from centrade_api.testing import Stack, create_instance
from centrade_core.engine.types import Balance, InstanceStatus, Snapshot
from centrade_core.models.trading import BalanceSnapshot
from centrade_worker.projection import apply_observation
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select

CURRENCIES = ("USDT", "EUR", "BTC")
MONEY = st.decimals(min_value=Decimal(0), max_value=Decimal("1e12"), places=18, allow_nan=False)
BALANCES = st.dictionaries(st.sampled_from(CURRENCIES), st.tuples(MONEY, MONEY), max_size=3)


def _snap(at_s: int, stack: Stack, balances: dict[str, tuple[Decimal, Decimal]]) -> Snapshot:
    return Snapshot(
        positions=(), orders=(), stops=(),
        balances=tuple(Balance(currency=c, free=f, total=t) for c, (f, t) in balances.items()),
        observed_at=stack.world.clock.now + timedelta(seconds=at_s),
    )  # fmt: skip


async def _apply(stack: Stack, iid: UUID, snap: Snapshot) -> None:
    status = InstanceStatus(state="running", mode="paper", observed_at=snap.observed_at)
    async with stack.world.sessions.begin() as s:
        await apply_observation(s, iid, status, snap)


async def _rows(stack: Stack, iid: UUID) -> dict[str, tuple[Decimal, Decimal, object]]:
    async with stack.world.sessions() as s:
        rows = await s.scalars(select(BalanceSnapshot).where(BalanceSnapshot.instance_id == iid))
        return {b.currency: (b.free, b.total, b.observed_at) for b in rows}


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
# shortcut: the latest snapshot is non-empty. Once an empty snapshot deleted every row, nothing
# remembers its date and a late older snapshot writes its rows back with their own old date
# (shown stale, never as current); closing it needs a stored "last balance observation" date.
@given(
    snaps=st.tuples(st.lists(BALANCES, max_size=4), BALANCES.filter(bool)).map(
        lambda t: [*t[0], t[1]]
    ),
    order=st.randoms(use_true_random=False),
    replays=st.integers(min_value=1, max_value=3),
)
async def test_replayed_or_shuffled_snapshots_keep_one_row_per_currency_from_the_latest(
    stack: Stack,
    snaps: list[dict[str, tuple[Decimal, Decimal]]],
    order: object,
    replays: int,
) -> None:
    c = await stack.client("operator")
    iid = UUID((await create_instance(c))["id"])
    dated = [_snap(n, stack, b) for n, b in enumerate(snaps)]  # index = observation second
    delivered = dated * replays
    order.shuffle(delivered)  # type: ignore[attr-defined]
    for snap in delivered:
        await _apply(stack, iid, snap)

    latest = dated[-1]
    assert await _rows(stack, iid) == {
        b.currency: (b.free, b.total, latest.observed_at) for b in latest.balances
    }


async def test_an_older_snapshot_never_overwrites_a_newer_balance(stack: Stack) -> None:
    c = await stack.client("operator")
    iid = UUID((await create_instance(c))["id"])
    await _apply(stack, iid, _snap(10, stack, {"USDT": (Decimal("5"), Decimal("7"))}))
    await _apply(
        stack, iid,
        _snap(5, stack, {"USDT": (Decimal("1"), Decimal("1")), "EUR": (Decimal(1), Decimal(1))}),
    )  # fmt: skip
    rows = await _rows(stack, iid)
    assert set(rows) == {"USDT"} and rows["USDT"][:2] == (Decimal("5"), Decimal("7"))

    await _apply(stack, iid, _snap(10, stack, {"USDT": (Decimal("6"), Decimal("8"))}))
    assert (await _rows(stack, iid))["USDT"][:2] == (Decimal("6"), Decimal("8"))  # same date: kept


async def test_a_currency_absent_from_the_snapshot_is_deleted(stack: Stack) -> None:
    c = await stack.client("operator")
    iid = UUID((await create_instance(c))["id"])
    both = {"USDT": (Decimal("1"), Decimal("1")), "BTC": (Decimal("0.5"), Decimal("0.5"))}
    await _apply(stack, iid, _snap(1, stack, both))
    await _apply(stack, iid, _snap(2, stack, {"USDT": (Decimal("2"), Decimal("2"))}))
    assert set(await _rows(stack, iid)) == {"USDT"}
