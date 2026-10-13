"""`make bootstrap-admin` : premier administrateur, sans identifiant par défaut (SPEC §13)."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from centrade_api.auth import bootstrap
from centrade_core.models import AuditLog, User
from centrade_core.settings import Settings
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .conftest import PASSWORD, Account, FakeClock, SignIn

EMAIL = "premier-admin@example.test"


@pytest.fixture
async def no_admin(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s, s.begin():
        await s.execute(delete(User).where(User.role == "admin"))


@pytest.mark.usefixtures("no_admin")
async def test_cree_le_premier_admin_qui_peut_se_connecter(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    client: httpx.AsyncClient,
    sign_in: SignIn,
    clock: FakeClock,
) -> None:
    created = await bootstrap.create_first_admin(
        session_factory, settings.master_key(), email=f"  {EMAIL.upper()} ", password=PASSWORD
    )

    uri = urlparse(created.totp_uri)
    secret = parse_qs(uri.query)["secret"][0]
    assert uri.scheme == "otpauth" and "Centrade" in created.totp_uri
    assert len(created.recovery_codes) == 10
    async with session_factory() as s:
        user = (await s.execute(select(User).where(User.username == EMAIL))).scalar_one()
        audit = (
            await s.execute(
                select(AuditLog.action, AuditLog.actor).where(AuditLog.target == f"user:{user.id}")
            )
        ).all()
        dump = (
            await s.execute(
                text("SELECT row_to_json(u)::text FROM users u WHERE id = :i"), {"i": user.id}
            )
        ).scalar_one()
    assert user.role == "admin"
    assert user.password_hash.startswith("$argon2id$")
    assert [tuple(a) for a in audit] == [("auth.admin.created", "host:bootstrap-admin")]
    for secret_value in (PASSWORD, secret, *created.recovery_codes):
        assert secret_value not in dump

    # Ce que la commande affiche suffit à ouvrir une session, et rien d'autre.
    account = Account(user.id, EMAIL, PASSWORD, secret, created.recovery_codes)
    await sign_in(client, account)
    me = await client.get("/api/v1/auth/me")
    assert me.json()["role"] == "admin"


@pytest.mark.usefixtures("no_admin")
async def test_refuse_s_il_existe_deja_un_admin(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    await bootstrap.create_first_admin(
        session_factory, settings.master_key(), email=EMAIL, password=PASSWORD
    )

    with pytest.raises(bootstrap.AdminExistsError):
        await bootstrap.create_first_admin(
            session_factory,
            settings.master_key(),
            email="second@example.test",
            password=PASSWORD,
        )

    async with session_factory() as s:
        admins = (await s.execute(select(User.username).where(User.role == "admin"))).scalars()
        assert list(admins) == [EMAIL]


@pytest.mark.usefixtures("no_admin")
@pytest.mark.parametrize(
    ("email", "password"),
    [("sans-arobase", PASSWORD), ("", PASSWORD), (EMAIL, "court"), (EMAIL, "x" * 11)],
)
async def test_refuse_un_identifiant_ou_un_mot_de_passe_faible(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    email: str,
    password: str,
) -> None:
    with pytest.raises(ValueError, match=r"invalide|au moins"):
        await bootstrap.create_first_admin(
            session_factory, settings.master_key(), email=email, password=password
        )

    async with session_factory() as s:
        assert (await s.execute(select(User.id).where(User.role == "admin"))).first() is None
