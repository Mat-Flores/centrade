"""Bus, ingestion idempotente, projections, moteur injoignable, battement, arrêt propre."""

import asyncio
from datetime import timedelta

from centrade_core.bus import EVENTS_STREAM, HEARTBEAT_KEY, Bus
from centrade_core.events import CanonicalEvent
from centrade_core.ids import uuid7
from centrade_fake.engine import Failure
from centrade_worker.ingest import ingest
from centrade_worker.testing import T0, World
from sqlalchemy import select


async def test_bus_non_acquitte_relivre_apres_redemarrage(redis_url: str) -> None:
    from redis.asyncio import Redis

    r = Redis.from_url(redis_url, decode_responses=True)
    await r.flushdb()
    a = Bus(r, "g", "a")
    for i in range(3):
        await a.publish("s", str(i))
    first = await a.read("s")
    assert [m.data for m in first] == ["0", "1", "2"]
    await a.ack("s", first[0].id)
    assert await a.pending("s") == 2
    again = await Bus(r, "g", "b").read("s")  # autre consommateur : reprise des non-acquittés
    assert [m.data for m in again] == ["1", "2"]
    await a.ack("s", *(m.id for m in again))
    assert await a.pending("s") == 0
    await r.aclose()


async def test_ingestion_idempotente_par_id_et_par_seq(migrated_url: str, redis_url: str) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance(seed=2)
        w.step(ref, 10)
        evs = await w.drain_engine(ref)
        ev = evs[0]
        r1 = await ingest(w.sessions, ev, T0)
        r2 = await ingest(w.sessions, ev, T0)  # même id
        twin = CanonicalEvent.model_validate({**ev.model_dump(), "id": uuid7()})
        r3 = await ingest(w.sessions, twin, T0)  # même (instance_id, seq), autre id
        assert (r1.new, r2.new, r3.new) == (True, False, False)
        assert r2.anomaly == r3.anomaly == "duplicate"
        p = await w.projection(ref)
        assert p.n_events == 1
        from centrade_core.models.trading import Event

        async with w.sessions() as s:
            assert (
                await s.scalar(select(Event.ts_ingest).where(Event.instance_id == ref.instance_id))
            ) == T0  # posé à la réception


async def test_trou_et_desordre_detectes(migrated_url: str, redis_url: str) -> None:
    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance(seed=2)
        w.step(ref, 10)
        evs = sorted(await w.drain_engine(ref), key=lambda e: e.seq)
        assert (await ingest(w.sessions, evs[0], T0)).anomaly is None
        assert (await ingest(w.sessions, evs[2], T0)).anomaly == "gap"
        assert (await ingest(w.sessions, evs[1], T0)).anomaly == "out_of_order"


async def test_redemarrage_au_milieu_d_un_lot_sans_perte_ni_doublon(
    migrated_url: str, redis_url: str
) -> None:
    async with World(migrated_url, redis_url, consumer="avant") as w:
        ref = await w.new_instance(seed=9)
        w.step(ref, 40)
        evs = await w.drain_engine(ref)
        assert len(evs) >= 8
        await w.publish(evs)
        # Le premier consommateur lit tout, traite 4 messages, puis « plante ».
        msgs = await w.bus.read(EVENTS_STREAM)
        for m in msgs[:4]:
            await ingest(w.sessions, CanonicalEvent.model_validate_json(m.data), T0)
            await w.bus.ack(EVENTS_STREAM, m.id)
        # Il avait ingéré un 5e message sans l'acquitter : il sera relivré, sans double effet.
        await ingest(w.sessions, CanonicalEvent.model_validate_json(msgs[4].data), T0)

        await w.make_worker("apres").run_once()

        assert (await w.projection(ref)).n_events == len(evs)
        assert await w.bus.pending(EVENTS_STREAM) == 0


async def test_moteur_injoignable_unknown_et_valeurs_non_rafraichies(
    migrated_url: str, redis_url: str
) -> None:
    from centrade_core.models.trading import Alert, Instance, Position

    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance(seed=4)
        w.step(ref, 60)
        await w.worker.run_once()
        before = await w.projection(ref)
        assert before.positions  # sinon le test ne prouve rien
        async with w.sessions() as s:
            inst = await s.get(Instance, ref.instance_id)
            assert inst is not None and inst.observed_state == "running"
            assert inst.observed_at == T0
            obs = {p.external_id: p.observed_at for p in await s.scalars(select(Position))}
        assert set(obs.values()) == {T0}

        w.fake.set_failure(ref, Failure.SILENT)
        w.clock.advance(120)
        await w.worker.run_once()
        await w.worker.run_once()  # une alerte, pas deux
        async with w.sessions() as s:
            inst = await s.get(Instance, ref.instance_id)
            assert inst is not None
            assert inst.observed_state == "unknown" and inst.observed_mode is None
            alerts = (
                await s.scalars(select(Alert).where(Alert.target_id == ref.instance_id))
            ).all()
            now_obs = {
                p.external_id: p.observed_at
                for p in await s.scalars(
                    select(Position).where(Position.instance_id == ref.instance_id)
                )
            }
        assert len(alerts) == 1 and alerts[0].severity == "critical" and alerts[0].status == "open"
        assert await w.projection(ref) == before  # rien inventé, rien remis à zéro
        assert now_obs == {k: v for k, v in obs.items() if k in now_obs} and len(now_obs) == len(
            before.positions
        )
        assert set(now_obs.values()) == {T0}  # l'ancienne heure d'observation, donc périmée

        w.fake.set_failure(ref, Failure.SILENT, on=False)
        w.clock.advance(5)
        await w.worker.run_once()
        async with w.sessions() as s:
            alert = await s.get(Alert, alerts[0].id)
            inst = await s.get(Instance, ref.instance_id)
        assert alert is not None and alert.status == "resolved"
        assert inst is not None and inst.observed_state == "running"
        assert inst.observed_at == T0 + timedelta(seconds=125)


async def test_releve_vieilli_garde_son_heure_d_observation(
    migrated_url: str, redis_url: str
) -> None:
    from centrade_core.models.trading import Instance, Position

    async with World(migrated_url, redis_url) as w:
        ref = await w.new_instance(seed=4)
        w.step(ref, 60)
        w.fake.set_failure(ref, Failure.SLOW)
        w.clock.advance(100)
        await w.worker.run_once()
        stale = T0 + timedelta(seconds=40)  # 60 s de retard sur l'horloge
        async with w.sessions() as s:
            inst = await s.get(Instance, ref.instance_id)
            rows = (
                await s.scalars(select(Position).where(Position.instance_id == ref.instance_id))
            ).all()
        assert inst is not None and inst.observed_at == stale
        assert rows and all(p.observed_at == stale for p in rows)


async def test_battement_expire_et_arret_propre(migrated_url: str, redis_url: str) -> None:
    async with World(migrated_url, redis_url) as w:
        assert await w.redis.get(HEARTBEAT_KEY) is None
        await w.worker.run_once()
        assert await w.redis.get(HEARTBEAT_KEY) == T0.isoformat()
        assert 0 < await w.redis.ttl(HEARTBEAT_KEY) <= 15

        stop = asyncio.Event()
        tours = 0

        async def un_tour() -> None:
            nonlocal tours
            tours += 1
            stop.set()  # équivalent d'un SIGTERM reçu pendant le tour

        w.worker.run_once = un_tour  # type: ignore[method-assign]
        await asyncio.wait_for(w.worker.run(stop), timeout=5)
        assert tours == 1
