"""Banc d'essai de bout en bout (hors production) : API + worker + FakeEngine, une seule horloge.

L'API et le worker partagent la base, Redis et l'horloge injectée de `World` : un test fait
avancer le temps à la main, appelle l'API, lance un tour de worker, et lit le résultat.
Valeurs sentinelles uniquement.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pyotp
import pytest_asyncio
from centrade_core.engine.types import InstanceRef
from centrade_core.ids import uuid7
from centrade_core.models import User
from centrade_core.settings import Settings, get_settings
from centrade_worker.testing import World
from fastapi import FastAPI

from centrade_api.auth import routes, security
from centrade_api.deps import get_db, get_redis, get_session_factory, utcnow
from centrade_api.main import create_app

ORIGIN = "https://centrade.test"
PASSWORD = "SENTINELLE-mot-de-passe-0xDEADBEEF"  # noqa: S105  # sentinelle de test
_PASSWORD_HASH = security.hash_password(PASSWORD)  # argon2 est lent : une fois par processus


@dataclass
class Account:
    id: object
    email: str
    totp_secret: str


@dataclass
class Stack:
    app: FastAPI
    world: World
    settings: Settings
    _clients: list[httpx.AsyncClient]
    last_account: Account | None = None

    async def account(self, role: str) -> Account:
        uid = uuid7()
        email = f"sentinelle-{uuid4().hex[:12]}@example.test"
        totp = pyotp.random_base32()
        user = User(
            id=uid,
            username=email,
            role=role,
            password_hash=_PASSWORD_HASH,
            recovery_code_hashes=[
                security.recovery_code_hash(c) for c in security.new_recovery_codes()
            ],
        )
        user.totp_nonce, user.totp_secret_enc = security.encrypt_totp_secret(
            master_key=self.settings.master_key(), user_id=uid, secret=totp
        )
        async with self.world.sessions.begin() as s:
            s.add(user)
        return Account(uid, email, totp)

    async def client(self, role: str = "operator", *, signed_in: bool = True) -> httpx.AsyncClient:
        """Client HTTP (origine admise). Connecté par mot de passe puis TOTP si `signed_in`."""
        c = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, client=("203.0.113.10", 4242)),
            base_url=ORIGIN,
            headers={"Origin": ORIGIN},
        )
        self._clients.append(c)
        routes.limiter.reset()  # compteur de connexions global au processus
        if signed_in:
            acc = self.last_account = await self.account(role)
            r = await c.post(
                "/api/v1/auth/login", json={"username": acc.email, "password": PASSWORD}
            )
            assert r.status_code == 200, r.text  # noqa: S101
            code = pyotp.TOTP(acc.totp_secret).at(self.world.clock.now)
            r = await c.post("/api/v1/auth/totp", json={"code": code})
            assert r.status_code == 200, r.text  # noqa: S101
        return c


@pytest_asyncio.fixture
async def stack(migrated_url: str, redis_url: str, tmp_path: Path) -> AsyncIterator[Stack]:
    key = tmp_path / "master_key"
    key.write_text(base64.b64encode(bytes(range(32))).decode())
    settings = Settings(
        redis_url=redis_url,
        postgres_password_file=tmp_path / "absent",
        master_key_file=key,
        public_origin=ORIGIN,
        stream_heartbeat_s=0.05,  # flux : réveils rapides, aucun sommeil dans les tests
        stream_session_check_s=0.0,
    )
    async with World(migrated_url, redis_url) as w:
        app = create_app()

        async def _db() -> AsyncIterator[object]:
            async with w.sessions() as s:
                yield s

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[utcnow] = w.clock
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_redis] = lambda: w.redis
        app.dependency_overrides[get_session_factory] = lambda: w.sessions
        st = Stack(app, w, settings, [])
        yield st
        for c in st._clients:
            await c.aclose()


async def create_instance(c: httpx.AsyncClient, **params: object) -> dict[str, Any]:
    body = {"name": f"i-{uuid4().hex[:10]}", "engine": "fake", "mode": "paper", "params": params}
    r = await c.post("/api/v1/instances", json=body)
    assert r.status_code == 201, r.text  # noqa: S101
    return dict(r.json())


async def act(
    c: httpx.AsyncClient, instance_id: str, action: str, key: str | None = None
) -> httpx.Response:
    return await c.post(
        f"/api/v1/instances/{instance_id}/{action}",
        headers={"Idempotency-Key": key or uuid4().hex},
    )


async def get(c: httpx.AsyncClient, path: str) -> dict[str, Any]:
    r = await c.get(path)
    assert r.status_code == 200, r.text  # noqa: S101
    return dict(r.json())


def ref_of(instance_id: str) -> InstanceRef:
    return InstanceRef(engine="fake", instance_id=UUID(instance_id))
