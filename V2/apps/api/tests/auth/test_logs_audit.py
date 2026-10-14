"""Nothing sensitive in the logs; each auth event has its audit row (I12, I14)."""

import base64
import io
import json
import re

from centrade_core.audit import verify_chain
from centrade_core.models import AuditLog
from centrade_core.settings import Settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .conftest import Account, FakeClock, MakeAccount, MakeClient

LOGIN, TOTP, ME, LOGOUT = (f"/api/v1/auth/{p}" for p in ("login", "totp", "me", "logout"))
WRONG = "SENTINELLE-mauvais-mot-de-passe"
WRONG_UNKNOWN = "SENTINELLE-essai-sur-compte-inconnu"
IP = "203.0.113.77"


async def _journey(make_client: MakeClient, account: Account, clock: FakeClock) -> list[str]:
    """Failures, login, read, logout, recovery code. Returns the secrets seen."""
    client = make_client(ip=IP)
    creds = {"username": account.email, "password": account.password}
    bad_code = "000000" if account.code(clock.now) != "000000" else "111111"
    good_code = account.code(clock.now)

    assert (await client.post(LOGIN, json={**creds, "password": WRONG})).status_code == 401
    nobody = {"username": "personne@example.test", "password": WRONG_UNKNOWN}
    assert (await client.post(LOGIN, json=nobody)).status_code == 401
    assert (await client.post(LOGIN, json=creds)).status_code == 200
    pre_token = client.cookies["__Host-centrade_pre"]
    assert (await client.post(TOTP, json={"code": bad_code})).status_code == 401
    assert (await client.post(TOTP, json={"code": good_code})).status_code == 200
    token = client.cookies["__Host-centrade_session"]
    assert (await client.get(ME)).status_code == 200
    assert (await client.post(LOGOUT)).status_code == 204

    assert (await client.post(LOGIN, json=creds)).status_code == 200
    second_pre = client.cookies["__Host-centrade_pre"]
    recovery = account.recovery_codes[0]
    assert (await client.post(TOTP, json={"code": recovery})).status_code == 200
    second_token = client.cookies["__Host-centrade_session"]

    return [
        account.password,
        WRONG,
        WRONG_UNKNOWN,
        account.totp_secret,
        recovery,
        recovery.replace("-", ""),
        pre_token,
        token,
        second_pre,
        second_token,
        f"(?<![0-9]){good_code}(?![0-9])",
        f"(?<![0-9]){bad_code}(?![0-9])",
    ]


async def test_i12_no_sensitive_value_in_logs_of_a_full_journey(
    logs: io.StringIO,
    make_client: MakeClient,
    make_account: MakeAccount,
    clock: FakeClock,
    settings: Settings,
) -> None:
    account = await make_account()

    secrets = await _journey(make_client, account, clock)

    output = logs.getvalue()
    secrets.append(base64.b64encode(settings.master_key()).decode())
    for secret in secrets[:10] + secrets[-1:]:
        assert secret not in output
    for pattern in secrets[10:12]:  # 6-digit codes: not buried in another number
        assert not re.search(pattern, output)
    assert account.email not in output  # nor the full identifier
    # The flow was indeed logged, as JSON, with enough to investigate.
    events = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    names = [e["event"] for e in events]
    for expected in (
        "auth_login_failed",
        "auth_totp_failed",
        "auth_login_succeeded",
        "auth_logout",
        "auth_recovery_code_used",
    ):
        assert expected in names, names
    failed = next(e for e in events if e["event"] == "auth_login_failed")
    assert (failed["reason"], failed["ip"], failed["user_id"]) == (
        "bad_password",
        IP,
        str(account.id),
    )


async def test_i14_auth_events_leave_an_audit_row_with_author_and_ip(
    make_client: MakeClient,
    make_account: MakeAccount,
    clock: FakeClock,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    account = await make_account()

    await _journey(make_client, account, clock)

    async with session_factory() as s:
        rows = (
            await s.execute(
                select(AuditLog.action, AuditLog.actor, AuditLog.ip)
                .where(AuditLog.target == f"user:{account.id}")
                .order_by(AuditLog.seq)
            )
        ).all()
        assert await verify_chain(s) is None
    author = f"user:{account.id}"
    assert [tuple(r) for r in rows] == [
        ("auth.login.failed", "anonymous", IP),  # wrong password: identity not proven
        ("auth.password.accepted", author, IP),
        ("auth.totp.failed", author, IP),
        ("auth.login.succeeded", author, IP),
        ("auth.logout", author, IP),
        ("auth.password.accepted", author, IP),
        ("auth.recovery_code.used", author, IP),
        ("auth.login.succeeded", author, IP),
    ]


async def test_i14_correct_password_without_totp_leaves_a_trace(
    make_client: MakeClient,
    make_account: MakeAccount,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    account = await make_account()
    client = make_client(ip=IP)
    creds = {"username": account.email, "password": account.password}

    assert (await client.post(LOGIN, json=creds)).status_code == 200  # then nothing more

    async with session_factory() as s:
        rows = (
            await s.execute(
                select(AuditLog.action, AuditLog.actor, AuditLog.ip).where(
                    AuditLog.target == f"user:{account.id}"
                )
            )
        ).all()
    assert [tuple(r) for r in rows] == [("auth.password.accepted", f"user:{account.id}", IP)]


async def test_i14_lockout_and_failure_on_unknown_account_are_audited(
    make_client: MakeClient,
    make_account: MakeAccount,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    account = await make_account()
    client = make_client(ip=IP)
    async with session_factory() as s:
        before = (await s.execute(select(AuditLog.seq).order_by(AuditLog.seq.desc()))).scalar() or 0

    for _ in range(5):
        await client.post(LOGIN, json={"username": account.email, "password": WRONG})
    await client.post(LOGIN, json={"username": account.email, "password": account.password})
    await client.post(LOGIN, json={"username": "personne@example.test", "password": WRONG})

    async with session_factory() as s:
        rows = (
            await s.execute(
                select(AuditLog.action, AuditLog.actor, AuditLog.target, AuditLog.ip)
                .where(AuditLog.seq > before, AuditLog.ip == IP)
                .order_by(AuditLog.seq)
            )
        ).all()
    author = f"user:{account.id}"
    assert [tuple(r) for r in rows] == [
        *[("auth.login.failed", "anonymous", author, IP)] * 5,
        ("auth.account.locked", "system:auth", author, IP),
        ("auth.login.failed", "anonymous", author, IP),  # attempt during the lock
        ("auth.login.failed", "anonymous", "user:unknown", IP),
    ]
