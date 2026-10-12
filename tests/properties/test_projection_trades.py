"""Les trades clos viennent du relevé : rejouer, dupliquer, permuter ou perdre des événements, ou
redémarrer le worker, laisse une ligne `trades` par position close, avec sa cause (F10)."""

import asyncio
from collections.abc import Callable

from centrade_core.engine.types import InstanceRef
from centrade_core.events import CanonicalEvent
from centrade_core.models.trading import Trade
from centrade_worker.testing import World
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select


async def _lignes(w: World, ref: InstanceRef) -> frozenset[tuple[object, ...]]:
    """Toutes les colonnes d'une ligne `trades`, hors identifiants propres à la base."""
    async with w.sessions() as s:
        rows = (await s.scalars(select(Trade).where(Trade.instance_id == ref.instance_id))).all()
    return frozenset(
        (
            t.external_id, t.instrument, t.quantity, t.entry_price, t.exit_price, t.entry_cause,
            t.exit_cause, t.pnl, t.fees, t.currency, t.opened_at, t.closed_at, t.duration_s,
        )
        for t in rows
    )  # fmt: skip


async def _attendu(w: World, ref: InstanceRef) -> frozenset[tuple[object, ...]]:
    return frozenset(
        (
            c.position_id, c.symbol, c.qty, c.entry_price, c.exit_price, c.entry_cause or "unknown",
            c.exit_cause, c.pnl, c.fees, c.symbol.rsplit("/", 1)[-1],
            c.opened_at, c.closed_at, int((c.closed_at - c.opened_at).total_seconds()),
        )
        for c in (await w.fake.snapshot(ref)).closed
    )  # fmt: skip


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
        want = await _attendu(w, ref)

        await w.publish(events)
        await w.worker.run_once()
        assert await _lignes(w, ref) == want

        await w.publish(pick(events))  # le même flux, abîmé, repassé après le premier tour
        await w.worker.run_once()
        again = w.make_worker("w2")  # redémarrage : un autre worker reprend l'instance
        again.register(ref)
        await again.run_once()
        got = await _lignes(w, ref)
        assert got == want
        await w.wipe(ref)  # ligne perdue : le relevé la restitue
        await again.run_once()
        assert await _lignes(w, ref) == want


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
