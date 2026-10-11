"""`python -m centrade_worker`."""

import asyncio
import socket
from datetime import UTC, datetime

from centrade_core.bus import Bus
from centrade_core.db import make_engine, make_session_factory
from centrade_core.engine.contract import EngineAdapter
from centrade_core.ids import uuid7
from centrade_core.logging import configure_logging
from centrade_core.settings import get_settings
from centrade_fake.engine import ENGINE as FAKE
from centrade_fake.engine import FakeEngine
from redis.asyncio import Redis

from centrade_worker.worker import Worker, WorkerConfig, install_stop_signals

GROUP = "worker"


async def main() -> None:
    configure_logging()
    cfg = get_settings()
    db = make_engine(cfg.database_url())
    redis = Redis.from_url(cfg.redis_url, decode_responses=True)
    # Registre moteur -> adaptateur : un nouveau moteur s'ajoute ici et nulle part ailleurs.
    adapters: dict[str, EngineAdapter] = {
        FAKE: FakeEngine(
            clock=lambda: datetime.now(UTC),
            seed=1,
            new_id=uuid7,
            allow_failure_injection=cfg.engine_failure_injection,
        )
    }
    worker = Worker(
        adapters=adapters,
        sessions=make_session_factory(db),
        redis=redis,
        bus=Bus(redis, GROUP, consumer=f"worker-{socket.gethostname()}"),
        config=WorkerConfig(
            interval_s=cfg.worker_interval_s,
            engine_silent_after_s=cfg.engine_silent_after_s,
            heartbeat_ttl_s=cfg.worker_heartbeat_ttl_s,
            stale_after_s=cfg.observed_stale_after_s,
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
