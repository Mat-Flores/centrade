"""S9 (SPEC §14) : événements dupliqués, désordonnés ou perdus -> projections exactes après
resynchronisation, sans doublon dans `events`."""

import pytest
from centrade_fake.engine import Failure
from centrade_worker.testing import World
from sqlalchemy import text


@pytest.mark.parametrize("mode", [Failure.DUPLICATE, Failure.OUT_OF_ORDER, Failure.DROP])
async def test_s09_projections_exactes_apres_resynchronisation(
    migrated_url: str, redis_url: str, mode: Failure
) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance(seed=11)
        w.fake.set_failure(ref, mode)
        w.step(ref, 60)  # le worker relève lui-même les événements dégradés
        await w.worker.run_once()

        got, want = await w.projection(ref), await w.expected(ref)
        assert got.positions == want.positions
        assert got.open_orders == want.open_orders
        assert want.positions or want.open_orders  # le scénario n'est pas vide
        async with w.sessions() as s:
            dup_ids = (
                await s.execute(text("SELECT id FROM events GROUP BY id HAVING count(*) > 1"))
            ).all()
            dup_seq = (
                await s.execute(
                    text(
                        "SELECT seq FROM events WHERE instance_id = :i "
                        "GROUP BY seq HAVING count(*) > 1"
                    ),
                    {"i": ref.instance_id},
                )
            ).all()
        assert dup_ids == [] and dup_seq == []
        if mode is Failure.DROP:
            assert got.n_events <= 1  # seul le changement d'état d'avant la panne a survécu
        else:
            assert got.n_events > 0


async def test_s09_modes_enchaines_sur_une_meme_instance(migrated_url: str, redis_url: str) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance(seed=5)
        for mode in (Failure.DUPLICATE, Failure.OUT_OF_ORDER, Failure.DROP):
            w.fake.set_failure(ref, mode)
            w.step(ref, 30)
            await w.worker.run_once()
            w.fake.set_failure(ref, mode, on=False)
            got, want = await w.projection(ref), await w.expected(ref)
            assert (got.positions, got.open_orders) == (want.positions, want.open_orders)
