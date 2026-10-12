"""Les trades clos viennent du relevé : rejouer, dupliquer, permuter ou perdre des événements, ou
redémarrer le worker, laisse une ligne `trades` par position close, avec sa cause (F10)."""

import asyncio
from collections.abc import Callable

from centrade_core.events import CanonicalEvent
from centrade_worker.testing import World
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
        want = (await w.expected(ref)).trades

        await w.publish(events)
        await w.worker.run_once()
        assert (await w.projection(ref)).trades == want

        await w.publish(pick(events))  # le même flux, abîmé, repassé après le premier tour
        await w.worker.run_once()
        again = w.make_worker("w2")  # redémarrage : un autre worker reprend l'instance
        again.register(ref)
        await again.run_once()
        got = (await w.projection(ref)).trades
        assert got == want
        await w.wipe(ref)  # ligne perdue : le relevé la restitue
        await again.run_once()
        assert (await w.projection(ref)).trades == want


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 1000), steps=st.integers(1, 60), data=st.data())
def test_trades_une_seule_ligne_par_position_close(
    migrated_url: str, redis_url: str, seed: int, steps: int, data: st.DataObject
) -> None:
    perm = data.draw(st.randoms(use_true_random=False))
    n_dup = data.draw(st.integers(0, 10))

    def pick(events: list[CanonicalEvent]) -> list[CanonicalEvent]:
        out = list(events) + [perm.choice(events) for _ in range(n_dup if events else 0)]
        perm.shuffle(out)
        return out

    asyncio.run(_run(migrated_url, redis_url, seed, steps, pick))
