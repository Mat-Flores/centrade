"""Migration initiale : base vide -> head -> base, et propriétés du schéma."""

import asyncio
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from centrade_core.ids import uuid7
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


async def _rows(url: str, sql: str) -> list[Any]:
    engine = create_async_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as c:
            r = await c.execute(text(sql))
            return list(r.all()) if r.returns_rows else []
    finally:
        await engine.dispose()


def test_migration_head_hypertable_et_downgrade(
    pg_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    asyncio.run(_rows(pg_url, "CREATE DATABASE migtest"))
    url = make_url(pg_url).set(database="migtest").render_as_string(hide_password=False)
    cfg = make_alembic_config(url)
    tables = "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"

    command.upgrade(cfg, "head")
    hyper = asyncio.run(
        _rows(url, "SELECT hypertable_name FROM timescaledb_information.hypertables")
    )
    assert hyper == [("events",)]
    names = {r[0] for r in asyncio.run(_rows(url, tables))}
    assert {"users", "sessions", "engines", "instances", "commands", "events", "positions",
            "orders", "alerts", "audit_log"} <= names  # fmt: skip

    command.downgrade(cfg, "base")
    assert {r[0] for r in asyncio.run(_rows(url, tables))} == {"alembic_version"}
    command.upgrade(cfg, "head")  # re-montable après un downgrade


async def _instance(s: AsyncSession) -> Any:
    eid, iid = uuid7(), uuid7()
    await s.execute(
        text("INSERT INTO engines (id, kind, image, version) VALUES (:i, 'k', 'img', '1')"),
        {"i": eid},
    )
    await s.execute(
        text("INSERT INTO instances (id, engine_id, name, mode, desired_state) "
             "VALUES (:i, :e, :n, 'paper', 'stopped')"),
        {"i": iid, "e": eid, "n": f"i-{uuid4()}"},
    )  # fmt: skip
    return iid


async def test_instances_mode_immuable(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s, s.begin():
        iid = await _instance(s)
    async with session_factory() as s:
        with pytest.raises(DBAPIError, match="immuable"):
            await s.execute(text("UPDATE instances SET mode = 'live' WHERE id = :i"), {"i": iid})


async def test_events_unicite_instance_seq_ts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ins = (
        "INSERT INTO events (id, ts, type, instance_id, seq, schema_version, payload) "
        "VALUES (:id, '2026-01-01T00:00:00Z', 't', :i, 1, 1, '{}')"
    )
    async with session_factory() as s, s.begin():
        iid = await _instance(s)
        await s.execute(text(ins), {"id": uuid7(), "i": iid})
    async with session_factory() as s:
        with pytest.raises(IntegrityError):
            await s.execute(text(ins), {"id": uuid7(), "i": iid})
