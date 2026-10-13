"""Fixtures des tests de l'API : application câblée sur la base de test, horloge injectée.

Valeurs sentinelles uniquement : aucun vrai secret.
"""

import base64
import importlib.util
import io
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pyotp
import pytest
import pytest_asyncio
import structlog
from centrade_api.auth import (
    Principal,
    current_user,
    require_recent_totp,
    require_role,
    routes,
    security,
)
from centrade_api.deps import get_db, utcnow
from centrade_api.main import create_app
from centrade_core.ids import uuid7
from centrade_core.logging import configure_logging
from centrade_core.models import User
from centrade_core.settings import Settings, get_settings
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# pytest ne propage pas tests/conftest.py hors de tests/ : on réemploie ses fixtures telles quelles.
_spec = importlib.util.spec_from_file_location(
    "centrade_root_conftest", Path(__file__).resolve().parents[4] / "tests" / "conftest.py"
)
assert _spec and _spec.loader
_root = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_root)
pg_url = _root.pg_url
migrated_url = _root.migrated_url
engine = _root.engine
session_factory = _root.session_factory

ORIGIN = "https://centrade.test"
PASSWORD = "SENTINELLE-mot-de-passe-0xDEADBEEF"  # noqa: S105  # sentinelle de test
_PASSWORD_HASH = security.hash_password(PASSWORD)  # argon2 est lent : une fois pour tous
PROBE = "/api/v1/_probe"


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC).replace(microsecond=0)

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)

    def __call__(self) -> datetime:
        return self.now


@dataclass
class Account:
    id: UUID
    email: str
    password: str
    totp_secret: str
    recovery_codes: list[str]

    def code(self, at: datetime, offset: int = 0) -> str:
        return pyotp.TOTP(self.totp_secret).at(at, offset)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def logs(monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    monkeypatch.setenv("CENTRADE_LOG_LEVEL", "DEBUG")  # le niveau le plus bavard
    buffer = io.StringIO()
    configure_logging(stream=buffer)
    yield buffer
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    key = tmp_path / "master_key"
    key.write_text(base64.b64encode(bytes(range(32))).decode())
    return Settings(
        redis_url="redis://inutilise:6379/0",
        postgres_password_file=tmp_path / "absent",
        master_key_file=key,
        public_origin=ORIGIN,
    )


@pytest.fixture
def app(
    session_factory: async_sessionmaker[AsyncSession], clock: FakeClock, settings: Settings
) -> FastAPI:
    application = create_app()

    async def _db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as s:
            yield s

    application.dependency_overrides[get_db] = _db
    application.dependency_overrides[utcnow] = clock
    application.dependency_overrides[get_settings] = lambda: settings
    routes.limiter.reset()

    # Routes témoins : aucune route de M1 n'emploie encore les rôles ni la ré-authentification.
    for role in ("viewer", "operator", "admin"):

        @application.get(f"{PROBE}/{role}")
        async def _role(user: Principal = Depends(require_role(role))) -> dict[str, str]:  # noqa: B008
            return {"actor": user.actor}

    @application.post(f"{PROBE}/write")
    async def _write(user: Principal = Depends(current_user)) -> dict[str, str]:  # noqa: B008
        return {"actor": user.actor}

    @application.post(f"{PROBE}/dangerous")
    async def _dangerous(user: Principal = Depends(require_recent_totp)) -> dict[str, str]:  # noqa: B008
        return {"actor": user.actor}

    return application


MakeClient = Callable[..., httpx.AsyncClient]


@pytest_asyncio.fixture
async def make_client(app: FastAPI) -> AsyncIterator[MakeClient]:
    async with AsyncExitStack() as stack:

        def make(ip: str = "203.0.113.10", origin: str | None = ORIGIN) -> httpx.AsyncClient:
            client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, client=(ip, 4242)),
                base_url=ORIGIN,  # https : les cookies `Secure` ne partent que sur TLS
                headers={"Origin": origin} if origin else {},
            )
            stack.push_async_callback(client.aclose)
            return client

        yield make


@pytest.fixture
def client(make_client: MakeClient) -> httpx.AsyncClient:
    return make_client()


MakeAccount = Callable[..., Awaitable[Account]]


@pytest.fixture
def make_account(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> MakeAccount:
    async def make(role: str = "admin", *, with_totp: bool = True) -> Account:
        account = Account(
            id=uuid7(),
            email=f"sentinelle-{uuid4().hex[:12]}@example.test",
            password=PASSWORD,
            totp_secret=pyotp.random_base32(),
            recovery_codes=security.new_recovery_codes(),
        )
        user = User(
            id=account.id,
            username=account.email,
            role=role,
            password_hash=_PASSWORD_HASH,
            recovery_code_hashes=[security.recovery_code_hash(c) for c in account.recovery_codes],
        )
        if with_totp:
            user.totp_nonce, user.totp_secret_enc = security.encrypt_totp_secret(
                master_key=settings.master_key(), user_id=account.id, secret=account.totp_secret
            )
        async with session_factory() as s, s.begin():
            s.add(user)
        return account

    return make


SignIn = Callable[[httpx.AsyncClient, Account], Awaitable[None]]


@pytest.fixture
def sign_in(clock: FakeClock) -> SignIn:
    """Parcours complet : mot de passe puis code TOTP de l'instant de l'horloge."""

    async def run(client: httpx.AsyncClient, account: Account) -> None:
        r = await client.post(
            "/api/v1/auth/login", json={"username": account.email, "password": account.password}
        )
        assert r.status_code == 200, r.text
        r = await client.post("/api/v1/auth/totp", json={"code": account.code(clock.now)})
        assert r.status_code == 200, r.text

    return run
