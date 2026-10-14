"""Criterion C3: replaying, duplicating or reordering events changes neither the projections
nor the number of `events` rows, once resynchronization is done. Losing some of them does not
skew the projections either: the snapshot is authoritative."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from centrade_core.events import CanonicalEvent
from centrade_worker.testing import Projection, World
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


@dataclass(frozen=True)
class Outcome:
    events: list[CanonicalEvent]
    variant: list[CanonicalEvent]
    want: Projection  # the engine's snapshot
    single: Projection  # after a single pass, in order
    again: Projection  # after the variant's pass


async def _run(
    migrated_url: str,
    redis_url: str,
    seed: int,
    steps: int,
    pick: Callable[[list[CanonicalEvent]], list[CanonicalEvent]],
) -> Outcome:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance(seed=seed)
        w.step(ref, steps)
        events = await w.drain_engine(ref)
        want = await w.expected(ref)

        await w.publish(events)  # single pass, in order
        await w.worker.run_once()
        single = await w.projection(ref)
        await w.wipe(ref)

        variant = pick(events)
        await w.publish(variant)
        await w.worker.run_once()
        return Outcome(events, variant, want, single, await w.projection(ref))


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(0, 1000),
    steps=st.integers(1, 40),
    data=st.data(),
)
def test_replaying_duplicating_or_permuting_events_leaves_projections_unchanged(
    migrated_url: str, redis_url: str, seed: int, steps: int, data: st.DataObject
) -> None:
    perm = data.draw(st.randoms(use_true_random=False))
    n_dup = data.draw(st.integers(0, 10))
    replay = data.draw(st.booleans())

    def pick(events: list[CanonicalEvent]) -> list[CanonicalEvent]:
        out = list(events)
        perm.shuffle(out)
        out += [perm.choice(events) for _ in range(n_dup if events else 0)]
        if replay:
            out += events  # the whole stream replayed
        perm.shuffle(out)
        return out

    o = asyncio.run(_run(migrated_url, redis_url, seed, steps, pick))
    assert o.single == o.again  # positions, open orders, status of each order, events
    assert o.again.n_events == len({e.id for e in o.events}) == len(o.events)
    assert (o.again.positions, o.again.open_orders) == (o.want.positions, o.want.open_orders)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(0, 1000),
    steps=st.integers(1, 40),
    lost=st.lists(st.booleans(), min_size=130, max_size=130),
    order=st.randoms(use_true_random=False),
)
def test_losing_some_events_does_not_corrupt_projections(
    migrated_url: str, redis_url: str, seed: int, steps: int, lost: list[bool], order: object
) -> None:
    def pick(events: list[CanonicalEvent]) -> list[CanonicalEvent]:
        kept = [e for i, e in enumerate(events) if not lost[i % len(lost)]]
        order.shuffle(kept)  # type: ignore[attr-defined]
        return kept

    o = asyncio.run(_run(migrated_url, redis_url, seed, steps, pick))
    assert o.again.n_events == len(o.variant)  # nothing invented to fill a gap
    # Positions and open orders come from the snapshot: identical to the engine's truth.
    assert (o.again.positions, o.again.open_orders) == (o.want.positions, o.want.open_orders)
    # Order status: that of the full stream, or `unknown` if its outcome was lost.
    full = dict(o.single.orders)
    for order_id, status in o.again.orders:
        assert status in (full[order_id], "unknown"), (order_id, status)
