"""Real Postgres/TimescaleDB and Redis (testcontainers), images from deploy/compose/core.yml."""

import re
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from centrade_core.db import make_engine, make_session_factory
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

ROOT = Path(__file__).resolve().parents[1]


def _compose_image(prefix: str) -> str:
    compose = (ROOT / "deploy" / "compose" / "core.yml").read_text(encoding="utf-8")
    found = re.search(rf"^\s*image:\s*({re.escape(prefix)}\S+)", compose, re.M)
    assert found, f"image {prefix} absente de core.yml"
    return found.group(1)


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "packages" / "core" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


@pytest.fixture
def make_alembic_config() -> Callable[[str], Config]:
    return alembic_config


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    image = _compose_image("timescale/timescaledb")
    with PostgresContainer(image, driver="asyncpg", username="centrade", dbname="centrade") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer(_compose_image("redis:")) as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(r.port)}/0"


@pytest.fixture(scope="session")
def migrated_url(pg_url: str) -> str:
    """Migration applied only once per test session."""
    command.upgrade(alembic_config(pg_url), "head")
    return pg_url


@pytest_asyncio.fixture(scope="session")
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(migrated_url)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(engine)


@pytest_asyncio.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s
