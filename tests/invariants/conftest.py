"""Fixtures des tests d'invariants. Valeurs sentinelles uniquement."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from centrade_api.testing import stack  # noqa: F401  (fixture partagée)
from centrade_core.ids import uuid7
from centrade_core.models.trading import Account, Engine, Instance
from centrade_core.secrets import AesGcmSecretStore
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SENTINEL = "TEST-SECRET-DO-NOT-USE-{}-0xC0FFEE"
KEY = bytes(range(32))
NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def keyed_instance(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    sessions = session_factory

    async def make(*, mode: str, account_type: str = "live") -> tuple[UUID, UUID, UUID, UUID]:
        """Compte avec sa clé de trading, instance sur ce compte, identifiant de moteur."""
        store = AesGcmSecretStore(KEY)
        engine_id, account_id, instance_id = uuid7(), uuid7(), uuid7()
        async with sessions() as s, s.begin():
            s.add(Engine(id=engine_id, kind="fake", image="img", version="1"))
            s.add(
                Account(
                    id=account_id,
                    venue="venue-test",
                    type=account_type,
                    environment="sandbox",
                    label="c",
                    currency="USDT",
                )
            )
            await s.flush()
            trade = await store.put(
                s,
                usage="trade",
                kind="venue_api_key",
                owner=account_id,
                value=SecretStr(SENTINEL.format("trade")),
                now=NOW,
            )
            (await s.get_one(Account, account_id)).secret_ref = trade
            s.add(
                Instance(
                    id=instance_id,
                    engine_id=engine_id,
                    name=f"i-{uuid4()}",
                    mode=mode,
                    desired_state="stopped",
                    account_id=account_id,
                )
            )
            await s.flush()
            api = await store.put(
                s,
                usage="engine_api",
                kind="engine_api",
                owner=instance_id,
                value=SecretStr(SENTINEL.format("api")),
                now=NOW,
            )
        return account_id, instance_id, trade, api

    return make
