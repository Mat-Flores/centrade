"""Worker test helpers (non-production): FakeEngine, manually driven clock."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any

from centrade_core.bus import EVENTS_STREAM, Bus
from centrade_core.db import make_engine, make_session_factory
from centrade_core.engine.types import InstanceRef
from centrade_core.events import CanonicalEvent
from centrade_core.ids import uuid7
from centrade_fake.engine import FakeEngine
from redis.asyncio import Redis
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from centrade_worker.worker import Worker, WorkerConfig

T0 = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass(frozen=True)
class Projection:
    positions: frozenset[tuple[Any, ...]]
    open_orders: frozenset[tuple[Any, ...]]
    n_events: int
    orders: frozenset[tuple[str, str]] = frozenset()  # (client_order_id, status), all statuses
    trades: frozenset[tuple[Any, ...]] = frozenset()  # (external_id, exit_cause, pnl)


class World:
    def __init__(self, pg_url: str, redis_url: str, consumer: str = "w1") -> None:
        self._pg_url = pg_url
        self._redis_url = redis_url
        self._consumer = consumer

    async def __aenter__(self) -> World:
        self.db: AsyncEngine = make_engine(self._pg_url)
        self.sessions: async_sessionmaker[AsyncSession] = make_session_factory(self.db)
        self.redis: Redis = Redis.from_url(self._redis_url, decode_responses=True)
        await self.redis.flushdb()
        # The database is shared by the whole test session: a worker picks up all
        # commands and all instances. Each world therefore starts without the others'.
        async with self.sessions.begin() as s:
            await s.execute(text("TRUNCATE instances CASCADE"))
            await s.execute(text("TRUNCATE alerts"))
        self.clock = Clock()
        self.fake = FakeEngine(clock=self.clock, seed=3, new_id=uuid7, allow_failure_injection=True)
        self.bus = Bus(self.redis, "worker", self._consumer)
        self.worker = self.make_worker(self._consumer)
        return self

    async def __aexit__(
        self, et: type[BaseException] | None, e: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.redis.aclose()
        await self.db.dispose()

    def make_worker(self, consumer: str) -> Worker:
        return Worker(
            adapters={"fake": self.fake},
            sessions=self.sessions,
            redis=self.redis,
            bus=Bus(self.redis, "worker", consumer),
            clock=self.clock,
            config=WorkerConfig(),
            simulated=frozenset({"fake"}),
        )

    async def new_instance(self, seed: int | None = None) -> InstanceRef:
        """Deploys an instance, starts it, creates its rows and registers it with the worker."""
        if seed is not None:
            self.fake = FakeEngine(
                clock=self.clock, seed=seed, new_id=uuid7, allow_failure_injection=True
            )
            self.worker = self.make_worker(self._consumer)
        instance_id = uuid7()
        engine_id = uuid7()
        async with self.sessions.begin() as s:
            await s.execute(
                text(
                    "INSERT INTO engines (id, kind, image, version) VALUES (:i, 'fake', 'x', '1')"
                ),
                {"i": engine_id},
            )
            await s.execute(
                text(
                    "INSERT INTO instances (id, engine_id, name, mode, desired_state) "
                    "VALUES (:i, :e, :n, 'paper', 'running')"
                ),
                {"i": instance_id, "e": engine_id, "n": str(instance_id)},
            )
        # Same path as a `deploy` command: fingerprint recorded, then entries opened.
        ref = await self.fake.deploy(await self.worker.guard.deployment(instance_id))
        await self.fake.resume_entries(ref)
        self.worker.register(ref)
        return ref

    def step(self, ref: InstanceRef, n: int) -> None:
        for _ in range(n):
            self.fake.step(ref)

    async def drain_engine(self, ref: InstanceRef) -> list[CanonicalEvent]:
        return [ev async for ev in self.fake.events(ref)]

    async def publish(self, events: list[CanonicalEvent]) -> None:
        for ev in events:
            await self.bus.publish(EVENTS_STREAM, ev.model_dump_json())

    async def wipe(self, ref: InstanceRef) -> None:
        """Resets the instance's derived rows to zero (between two runs of a property)."""
        from centrade_core.models.trading import Alert, Event, Order, Position, Trade

        async with self.sessions.begin() as s:
            for model in (Event, Position, Order, Trade):
                await s.execute(delete(model).where(model.instance_id == ref.instance_id))
            await s.execute(delete(Alert).where(Alert.target_id == ref.instance_id))
        await self.redis.flushdb()

    async def projection(self, ref: InstanceRef) -> Projection:
        from centrade_core.models.trading import Event, Order, Position, Trade

        async with self.sessions() as s:
            pos = (
                await s.scalars(select(Position).where(Position.instance_id == ref.instance_id))
            ).all()
            every = (
                await s.scalars(select(Order).where(Order.instance_id == ref.instance_id))
            ).all()
            ords = [o for o in every if o.status == "open"]
            trades = (
                await s.scalars(select(Trade).where(Trade.instance_id == ref.instance_id))
            ).all()
            n = len(
                (
                    await s.scalars(select(Event.id).where(Event.instance_id == ref.instance_id))
                ).all()
            )
        return Projection(
            frozenset(
                (p.external_id, p.instrument, p.side, p.quantity, p.entry_price) for p in pos
            ),
            frozenset(
                (o.client_order_id, o.instrument, o.side, o.intent, o.quantity, o.price)
                for o in ords
            ),
            n,
            frozenset((o.client_order_id, o.status) for o in every),
            frozenset((t.external_id, t.exit_cause, t.pnl) for t in trades),
        )

    async def expected(self, ref: InstanceRef) -> Projection:
        """The engine snapshot, put into the projections' form."""
        snap = await self.fake.snapshot(ref)
        return Projection(
            frozenset(
                (
                    p.position_id,
                    p.symbol,
                    "long" if p.side == "buy" else "short",
                    p.qty,
                    p.entry_price,
                )
                for p in snap.positions
            ),
            frozenset(
                (o.order_id, o.symbol, o.side, o.intent, o.qty, o.price)
                for o in snap.orders
                if o.status == "open"
            ),
            0,
            trades=frozenset((c.position_id, c.exit_cause, c.pnl) for c in snap.closed),
        )
