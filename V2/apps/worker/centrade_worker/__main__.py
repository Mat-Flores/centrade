"""`python -m centrade_worker`."""

import asyncio
import os
import socket
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from centrade_core.bus import Bus
from centrade_core.db import make_engine, make_session_factory
from centrade_core.engine.contract import EngineAdapter
from centrade_core.ids import uuid7
from centrade_core.logging import configure_logging
from centrade_core.models.trading import Engine
from centrade_core.settings import get_settings
from centrade_fake.engine import ENGINE as FAKE
from centrade_fake.engine import FakeEngine
from centrade_freqtrade.adapter import FreqtradeAdapter
from centrade_freqtrade.capabilities import capabilities
from centrade_freqtrade.checks import ENGINE as FREQTRADE
from centrade_freqtrade.image import (
    ENGINE_MEMORY_BYTES,
    ENGINE_NANO_CPUS,
    FREQTRADE_DIGEST,
    FREQTRADE_IMAGE,
    FREQTRADE_TAG,
)
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from centrade_worker.runner import DockerRunner
from centrade_worker.runtime import WorkerRuntime
from centrade_worker.worker import Worker, WorkerConfig, install_stop_signals

GROUP = "worker"
log = structlog.get_logger()


async def register_engine(sessions: async_sessionmaker[AsyncSession]) -> None:
    """Freqtrade `engines` row: image, digest and reservations from `image.py` (ADR 0008)."""
    async with sessions.begin() as s:
        row = await s.scalar(select(Engine).where(Engine.kind == FREQTRADE))
        row = row or Engine(kind=FREQTRADE)
        row.image = f"{FREQTRADE_IMAGE}:{FREQTRADE_TAG}"
        row.version = FREQTRADE_TAG
        row.digest = FREQTRADE_DIGEST
        row.memory_reservation_mb = ENGINE_MEMORY_BYTES // 1024**2
        row.cpu_reservation = Decimal(ENGINE_NANO_CPUS) / 1_000_000_000
        row.capabilities = capabilities().model_dump(mode="json")
        s.add(row)


async def main() -> None:
    configure_logging()
    cfg = get_settings()
    db = make_engine(cfg.database_url())
    redis = Redis.from_url(cfg.redis_url, decode_responses=True)
    # Engine -> adapter registry: a new engine is added here and nowhere else.
    adapters: dict[str, EngineAdapter] = {
        FAKE: FakeEngine(
            clock=lambda: datetime.now(UTC),
            seed=1,
            new_id=uuid7,
            allow_failure_injection=cfg.engine_failure_injection,
        )
    }
    # Engines profile only: without the socket proxy there is no container to attach to.
    sessions = make_session_factory(db)
    runner = DockerRunner() if os.environ.get("DOCKER_HOST") else None
    runtime: WorkerRuntime | None = None
    if runner is None:
        log.info("engines_with_missing_containers", reason="DOCKER_HOST unset, FakeEngine only")
    else:
        runtime = WorkerRuntime(
            sessions=sessions,
            master_key=cfg.master_key(),
            runtime_dir=cfg.engine_runtime_dir,
            clock=lambda: datetime.now(UTC),
        )
        adapters[FREQTRADE] = FreqtradeAdapter(runner, runtime)
        await register_engine(sessions)
    worker = Worker(
        adapters=adapters,
        runner=runner,
        simulated=frozenset({FAKE}),
        # Digest pinned by the adapter: an `engines` row modified in the database is refused.
        pinned_digests={FREQTRADE: FREQTRADE_DIGEST},
        cleanup=None if runtime is None else runtime.cleanup,
        sessions=sessions,
        redis=redis,
        bus=Bus(redis, GROUP, consumer=f"worker-{socket.gethostname()}"),
        config=WorkerConfig(
            interval_s=cfg.worker_interval_s,
            engine_silent_after_s=cfg.engine_silent_after_s,
            heartbeat_ttl_s=cfg.worker_heartbeat_ttl_s,
            stale_after_s=cfg.observed_stale_after_s,
            pause_deadline_s=cfg.deadline_pause_entries_s,
        ),
    )
    stop = asyncio.Event()
    install_stop_signals(stop)
    try:
        await worker.load_instances()
        await worker.run(stop)
    finally:
        await redis.aclose()
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
