"""Initial migration: empty database -> head -> base, and schema properties."""

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


def test_migration_head_hypertable_and_downgrade(
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
    command.upgrade(cfg, "head")  # can be upgraded again after a downgrade


async def _instance(s: AsyncSession) -> Any:
    eid, iid = uuid7(), uuid7()
    await s.execute(
        text("INSERT INTO engines (id, kind, image, version) VALUES (:i, 'fake', 'img', '1')"),
        {"i": eid},
    )
    await s.execute(
        text("INSERT INTO instances (id, engine_id, name, mode, desired_state) "
             "VALUES (:i, :e, :n, 'paper', 'stopped')"),
        {"i": iid, "e": eid, "n": f"i-{uuid4()}"},
    )  # fmt: skip
    return iid


async def test_instances_mode_is_immutable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s, s.begin():
        iid = await _instance(s)
    async with session_factory() as s:
        with pytest.raises(DBAPIError, match="immuable"):
            await s.execute(text("UPDATE instances SET mode = 'live' WHERE id = :i"), {"i": iid})


async def test_events_are_unique_per_instance_seq_ts(
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


def test_downgrade_0003_with_two_positions_on_the_same_instrument(
    pg_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    asyncio.run(_rows(pg_url, "CREATE DATABASE migdown"))
    url = make_url(pg_url).set(database="migdown").render_as_string(hide_password=False)
    cfg = make_alembic_config(url)
    command.upgrade(cfg, "head")
    for sql in (
        "INSERT INTO instances (id, engine_id, name, mode, desired_state) "
        "SELECT gen_random_uuid(), id, 'i-down', 'paper', 'stopped' FROM engines LIMIT 1",
        "INSERT INTO positions (id, instance_id, external_id, instrument, side, quantity, "
        "currency, observed_at) SELECT gen_random_uuid(), i.id, v.ext, 'crypto:fake:BTC/USDT', "
        "'long', 1, 'USDT', now() FROM instances i, (VALUES ('p1'), ('p2')) AS v(ext)",
    ):
        asyncio.run(_rows(url, sql))

    command.downgrade(cfg, "0002")  # projections are derived: emptied, then rebuilt

    assert asyncio.run(_rows(url, "SELECT count(*) FROM positions")) == [(0,)]
    constraints = {
        r[0]
        for r in asyncio.run(
            _rows(url, "SELECT conname FROM pg_constraint WHERE conrelid = 'positions'::regclass")
        )
    }
    assert "uq_positions_instance_instrument_side" in constraints
    command.upgrade(cfg, "head")


def test_migration_0005_upgrade_downgrade_and_m1_data(
    pg_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    asyncio.run(_rows(pg_url, "CREATE DATABASE mig0005"))
    url = make_url(pg_url).set(database="mig0005").render_as_string(hide_password=False)
    cfg = make_alembic_config(url)
    command.upgrade(cfg, "0004")
    asyncio.run(_rows(url, "INSERT INTO instances (id, engine_id, name, mode, desired_state) "
                           "SELECT gen_random_uuid(), id, 'i-m1', 'paper', 'stopped' "
                           "FROM engines LIMIT 1"))  # fmt: skip

    command.upgrade(cfg, "0005")  # M1 data survives
    assert asyncio.run(_rows(url, "SELECT name FROM instances")) == [("i-m1",)]
    tables = "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    assert {"accounts", "secrets", "strategies", "strategy_versions", "trades",
            "service_accounts"} <= {r[0] for r in asyncio.run(_rows(url, tables))}  # fmt: skip

    command.downgrade(cfg, "0004")
    names = {r[0] for r in asyncio.run(_rows(url, tables))}
    assert not {"accounts", "secrets", "strategies", "strategy_versions", "trades"} & names
    cols = "SELECT column_name FROM information_schema.columns WHERE table_name = 'instances'"
    assert "deployment_fingerprint" not in {r[0] for r in asyncio.run(_rows(url, cols))}
    command.upgrade(cfg, "head")


async def _version(s: AsyncSession) -> Any:
    sid, vid = uuid7(), uuid7()
    await s.execute(
        text("INSERT INTO strategies (id, name) VALUES (:i, :n)"), {"i": sid, "n": f"s-{uuid4()}"}
    )
    await s.execute(
        text("INSERT INTO strategy_versions (id, strategy_id, version, manifest, code_hash, "
             "author, exits, code) VALUES (:v, :s, 1, '{}', 'h', 'op', '{}', 'c')"),
        {"v": vid, "s": sid},
    )  # fmt: skip
    return sid, vid


async def test_strategy_versions_are_immutable_except_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s, s.begin():
        _, vid = await _version(s)
    updates = (
        "UPDATE strategy_versions SET manifest = '{\"b\": 2}' WHERE id = :i",
        "UPDATE strategy_versions SET code_hash = 'x' WHERE id = :i",
        "UPDATE strategy_versions SET code = 'x' WHERE id = :i",
        'UPDATE strategy_versions SET exits = \'{"stoploss": "-0.5"}\' WHERE id = :i',
    )
    for sql in updates:
        async with session_factory() as s:
            with pytest.raises(DBAPIError, match="immuables"):
                await s.execute(text(sql), {"i": vid})
    async with session_factory() as s, s.begin():  # the status remains modifiable
        await s.execute(
            text("UPDATE strategy_versions SET status = 'approved' WHERE id = :i"), {"i": vid}
        )


async def test_strategy_versions_are_unique_per_strategy_number(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s, s.begin():
        sid, _ = await _version(s)
    async with session_factory() as s:
        with pytest.raises(IntegrityError):
            await s.execute(
                text("INSERT INTO strategy_versions (id, strategy_id, version, manifest, "
                     "code_hash, author, exits, code) "
                     "VALUES (:v, :s, 1, '{}', 'h', 'op', '{}', 'c')"),
                {"v": uuid7(), "s": sid},
            )  # fmt: skip


async def test_orders_client_order_id_is_unique(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ins = (
        "INSERT INTO orders (id, instance_id, client_order_id, instrument, side, intent, "
        "status, quantity, currency, observed_at) "
        "VALUES (:id, :i, 'dup-1', 'crypto:fake:BTC/USDT', 'buy', 'entry', 'open', 1, 'USDT', "
        "now())"
    )
    async with session_factory() as s, s.begin():
        iid = await _instance(s)
        await s.execute(text(ins), {"id": uuid7(), "i": iid})
    async with session_factory() as s:
        with pytest.raises(IntegrityError):
            await s.execute(text(ins), {"id": uuid7(), "i": iid})
