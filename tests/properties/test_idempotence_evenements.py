"""Critère C3 : rejouer, dupliquer ou permuter les événements ne change ni les projections
ni le nombre de lignes d'`events`, une fois la resynchronisation faite."""

import asyncio
from collections.abc import Callable

from centrade_core.events import CanonicalEvent
from centrade_worker.testing import Projection, World
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


async def _run(
    migrated_url: str,
    redis_url: str,
    seed: int,
    steps: int,
    pick: Callable[[list[CanonicalEvent]], list[CanonicalEvent]],
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance(seed=seed)
        w.step(ref, steps)
        events = await w.drain_engine(ref)
        want = await w.expected(ref)

        await w.publish(events)  # passage unique, dans l'ordre
        await w.worker.run_once()
        single = await w.projection(ref)
        await w.wipe(ref)

        variant = pick(events)
        await w.publish(variant)
        await w.worker.run_once()
        again = await w.projection(ref)

        assert single == again
        assert again.n_events == len({e.id for e in events}) == len(events)
        assert (again.positions, again.open_orders) == (want.positions, want.open_orders)
        assert isinstance(again, Projection)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(0, 1000),
    steps=st.integers(1, 40),
    data=st.data(),
)
def test_rejouer_dupliquer_permuter_laisse_les_projections_inchangees(
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
            out += events  # tout le flux rejoué
        perm.shuffle(out)
        return out

    asyncio.run(_run(migrated_url, redis_url, seed, steps, pick))
