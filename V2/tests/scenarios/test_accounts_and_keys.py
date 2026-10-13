"""Comptes et clés (SPEC F6, §8) : RBAC, TOTP récent, test de permissions, rotation, audit.

Valeurs sentinelles uniquement : aucune vraie clé.
"""

import asyncio
from typing import Any, get_args
from uuid import UUID, uuid4

import httpx
import pytest
from centrade_api.accounts.permissions import (
    KeyPermissions,
    KeyUsage,
    get_permission_probe,
    verdict,
)
from centrade_api.testing import Stack
from centrade_core.models import AuditLog
from centrade_core.models.trading import Account, Secret
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import func, select

A = "/api/v1/accounts"
KEY = {"usage": "trade", "key": "TEST-SECRET-DO-NOT-USE-cle", "secret": "TEST-SECRET-DO-NOT-USE-s"}
LIVE = {
    "venue": "venue-test",
    "type": "live",
    "environment": "sandbox",
    "label": "Compte de test",
    "currency": "USDT",
    "capital_cap": "1500.50",
}


class Probe:
    """Sonde de test : aucune venue réelle. Rend le résultat donné, ou lève s'il en est un."""

    def __init__(self, outcome: KeyPermissions | Exception | float) -> None:
        self.outcome = outcome
        self.seen: list[UUID] = []

    async def permissions(self, secret_id: UUID) -> KeyPermissions:
        self.seen.append(secret_id)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        if isinstance(self.outcome, float):
            await asyncio.sleep(self.outcome)
            return KeyPermissions(trading=True, withdrawal=False, ip_restricted=True)
        return self.outcome


OK = KeyPermissions(trading=True, withdrawal=False, ip_restricted=True)


async def _account(c: httpx.AsyncClient, **over: Any) -> dict[str, Any]:
    r = await c.post(A, json={**LIVE, **over})
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _row(stack: Stack, account_id: str) -> Account:
    async with stack.world.sessions() as s:
        row = await s.get(Account, UUID(account_id))
    assert row is not None
    return row


async def _secret_count(stack: Stack) -> int:
    async with stack.world.sessions() as s:
        return int(await s.scalar(select(func.count()).select_from(Secret)) or 0)


async def test_account_creation_and_list_return_money_as_decimal_strings(stack: Stack) -> None:
    admin = await stack.client("admin")
    created = await _account(admin)
    assert created["capital_cap"] == "1500.5" and created["type"] == "live"
    assert created["trade_key"] is None and created["read_key"] is None
    assert created["permissions_verified_at"] is None and created["ip_restricted"] is None
    paper = await _account(admin, type="paper", capital_cap=None, label="Papier")
    assert paper["capital_cap"] is None

    viewer = await stack.client("viewer")
    ids = [a["id"] for a in (await viewer.get(A, params={"limit": 200})).json()["items"]]
    assert ids.index(paper["id"]) < ids.index(created["id"])  # plus récent d'abord
    page = (await viewer.get(A, params={"limit": 1})).json()
    nxt = (await viewer.get(A, params={"limit": 1, "cursor": page["next_cursor"]})).json()
    assert [a["id"] for a in page["items"] + nxt["items"]] == ids[:2]
    assert "engine" not in created  # aucun nom de moteur dans le schéma

    for bad in (
        {"capital_cap": 1500.5},  # float refusé : chaîne décimale exigée
        {"capital_cap": 1500},
        {"capital_cap": "NaN"},
        {"capital_cap": "-1"},
        {"capital_cap": "0"},
        {"capital_cap": "1e400"},
        {"type": "backtest"},
        {"environment": "prod"},
        {"currency": "usdt"},
        {"venue": "Venue Test"},
        {"label": ""},
        {"inconnu": 1},
    ):
        assert (await admin.post(A, json={**LIVE, **bad})).status_code == 422, bad


async def test_rbac_viewer_and_operator_are_rejected_on_writes(stack: Stack) -> None:
    admin = await stack.client("admin")
    aid = (await _account(admin))["id"]
    before = await _secret_count(stack)
    for role in ("viewer", "operator"):
        c = await stack.client(role)
        assert (await c.post(A, json=LIVE)).status_code == 403
        assert (await c.put(f"{A}/{aid}/secret", json=KEY)).status_code == 403
        assert (await c.post(f"{A}/{aid}/test")).status_code == 403
        assert (await c.post(f"{A}/{aid}/rotate", json=KEY)).status_code == 403
        assert (await c.get(A)).status_code == 200
    anonymous = await stack.client(signed_in=False)
    assert (await anonymous.get(A)).status_code == 401
    assert (await anonymous.put(f"{A}/{aid}/secret", json=KEY)).status_code == 401
    assert await _secret_count(stack) == before


async def test_old_totp_is_rejected_for_adding_or_replacing_a_key(stack: Stack) -> None:
    admin = await stack.client("admin")
    aid = (await _account(admin))["id"]
    assert (await admin.put(f"{A}/{aid}/secret", json=KEY)).status_code == 200
    stack.world.clock.advance(5 * 60 + 1)
    before = await _row(stack, aid)
    assert (await admin.put(f"{A}/{aid}/secret", json=KEY)).status_code == 403
    assert (await admin.post(f"{A}/{aid}/rotate", json=KEY)).status_code == 403
    assert (await admin.get(A)).status_code == 200  # la session, elle, reste valide
    assert (await _row(stack, aid)).secret_ref == before.secret_ref


async def test_request_from_another_origin_is_rejected(stack: Stack) -> None:
    admin = await stack.client("admin")
    aid = (await _account(admin))["id"]
    r = await admin.put(
        f"{A}/{aid}/secret", json=KEY, headers={"Origin": "https://ailleurs.example"}
    )
    assert r.status_code == 403 and (await _row(stack, aid)).secret_ref is None


async def test_put_is_write_only_and_response_has_no_value_or_derivative(stack: Stack) -> None:
    admin = await stack.client("admin")
    aid = (await _account(admin))["id"]
    r = await admin.put(f"{A}/{aid}/secret", json=KEY)
    assert r.status_code == 200
    assert set(r.json()) == {"usage", "key_version", "stored_at", "rotated_at", "last_used_at"}
    assert r.json()["usage"] == "trade" and r.json()["key_version"] == 1
    read = await admin.put(f"{A}/{aid}/secret", json={**KEY, "usage": "read"})
    assert read.status_code == 200
    row = await _row(stack, aid)
    assert row.secret_ref and row.read_secret_ref and row.secret_ref != row.read_secret_ref
    listed = next(a for a in (await admin.get(A)).json()["items"] if a["id"] == aid)
    assert listed["trade_key"]["usage"] == "trade" and listed["read_key"]["usage"] == "read"

    # Remplacer une clé : l'ancienne ligne disparaît, la vérification repart de zéro.
    stack.app.dependency_overrides[get_permission_probe] = lambda: Probe(OK)
    assert (await admin.post(f"{A}/{aid}/test")).json()["result"] == "verified"
    assert (await admin.put(f"{A}/{aid}/secret", json=KEY)).status_code == 200
    after = await _row(stack, aid)
    assert after.secret_ref != row.secret_ref
    assert after.permissions_verified_at is None and after.ip_restricted is None
    async with stack.world.sessions() as s:
        assert await s.get(Secret, row.secret_ref) is None

    for bad in (
        {**KEY, "usage": "engine_api"},  # réservé au worker
        {**KEY, "usage": "webhook"},
        {**KEY, "key": ""},
        {**KEY, "secret": "x" * 2000},
        {"usage": "trade", "key": "k"},
        {**KEY, "extra": "x"},
    ):
        assert (await admin.put(f"{A}/{aid}/secret", json=bad)).status_code == 422, bad
    assert (await admin.put(f"{A}/{uuid4()}/secret", json=KEY)).status_code == 404


async def test_a_paper_account_receives_no_key(stack: Stack) -> None:
    admin = await stack.client("admin")
    aid = (await _account(admin, type="paper"))["id"]
    before = await _secret_count(stack)
    assert (await admin.put(f"{A}/{aid}/secret", json=KEY)).status_code == 409
    assert (await admin.post(f"{A}/{aid}/rotate", json=KEY)).status_code == 409
    assert await _secret_count(stack) == before


async def test_probe_defaults_to_unverified(stack: Stack) -> None:
    """Sans venue réelle : `permissions_verified_at` reste vide, `ip_restricted` inconnu."""
    admin = await stack.client("admin")
    aid = (await _account(admin))["id"]
    assert (await admin.post(f"{A}/{aid}/test")).status_code == 409  # aucune clé à tester
    await admin.put(f"{A}/{aid}/secret", json=KEY)
    r = await admin.post(f"{A}/{aid}/test")
    assert r.status_code == 200 and r.json()["result"] == "unverified"
    assert r.json()["account"]["permissions_verified_at"] is None
    assert r.json()["account"]["ip_restricted"] is None


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (OK, "verified"),
        (KeyPermissions(trading=True, withdrawal=True, ip_restricted=True), "refused"),
        (KeyPermissions(trading=False, withdrawal=False, ip_restricted=True), "refused"),
        (KeyPermissions(trading=None, withdrawal=True, ip_restricted=None), "refused"),
        (KeyPermissions(trading=True, withdrawal=None, ip_restricted=True), "unverified"),
        (KeyPermissions(trading=None, withdrawal=False, ip_restricted=True), "unverified"),
        (RuntimeError("TEST-SECRET-DO-NOT-USE-erreur"), "unverified"),
        (TimeoutError(), "unverified"),
        (60.0, "unverified"),  # sonde muette : délai dépassé
        (None, "unverified"),  # réponse qui n'est pas du type attendu
        ({"trading": True, "withdrawal": False}, "unverified"),
    ],
)
async def test_permissions_check_decision(
    stack: Stack, monkeypatch: pytest.MonkeyPatch, outcome: Any, expected: str
) -> None:
    from centrade_api.accounts import permissions

    monkeypatch.setattr(permissions, "PROBE_TIMEOUT_S", 0.05)
    admin = await stack.client("admin")
    aid = (await _account(admin))["id"]
    await admin.put(f"{A}/{aid}/secret", json=KEY)
    # Un compte d'abord vérifié : un test qui n'aboutit plus retire la vérification (I5).
    stack.app.dependency_overrides[get_permission_probe] = lambda: Probe(OK)
    assert (await admin.post(f"{A}/{aid}/test")).json()["result"] == "verified"
    probe = Probe(outcome)
    stack.app.dependency_overrides[get_permission_probe] = lambda: probe

    r = await admin.post(f"{A}/{aid}/test")

    assert r.status_code == 200 and r.json()["result"] == expected
    assert "TEST-SECRET" not in r.text
    row = await _row(stack, aid)
    assert probe.seen == [row.secret_ref]  # la sonde reçoit une référence, jamais une valeur
    if expected == "verified":
        assert row.permissions_verified_at == stack.world.clock() and row.ip_restricted is True
    else:
        assert row.permissions_verified_at is None and row.ip_restricted is None


perm = st.one_of(st.none(), st.booleans())


@given(trading=perm, withdrawal=perm, ip=perm, usage=st.sampled_from(get_args(KeyUsage)))
def test_verdict_is_rejected_by_default(
    trading: bool | None, withdrawal: bool | None, ip: bool | None, usage: KeyUsage
) -> None:
    result = verdict(
        KeyPermissions(trading=trading, withdrawal=withdrawal, ip_restricted=ip), usage
    )
    wanted_trading = usage == "trade"
    # Vérifié seulement si tout est connu et conforme ; jamais avec un retrait possible.
    assert (result == "verified") == (trading is wanted_trading and withdrawal is False)
    if withdrawal is True:
        assert result == "refused"


def test_verdict_of_an_incomplete_response_is_unverified() -> None:
    for junk in (None, {}, "ok", True, object()):
        assert verdict(junk, "trade") == "unverified"  # type: ignore[arg-type]
    # Des valeurs « vraies » qui ne sont pas des booléens ne valent pas permission constatée.
    assert (
        verdict(KeyPermissions(trading=1, withdrawal=0, ip_restricted=None), "trade")  # type: ignore[arg-type]
        != "verified"
    )


async def test_successful_rotation_switches_then_revokes_the_old_key(stack: Stack) -> None:
    admin = await stack.client("admin")
    aid = (await _account(admin))["id"]
    assert (await admin.post(f"{A}/{aid}/rotate", json=KEY)).status_code == 409  # rien à remplacer
    await admin.put(f"{A}/{aid}/secret", json=KEY)
    old = (await _row(stack, aid)).secret_ref
    probe = Probe(OK)
    stack.app.dependency_overrides[get_permission_probe] = lambda: probe

    r = await admin.post(f"{A}/{aid}/rotate", json={**KEY, "key": "TEST-SECRET-DO-NOT-USE-n"})

    assert r.status_code == 200 and r.json()["rotated_at"] is not None
    assert "TEST-SECRET" not in r.text
    row = await _row(stack, aid)
    assert row.secret_ref not in (None, old) and probe.seen == [row.secret_ref]  # la nouvelle
    assert row.permissions_verified_at == stack.world.clock() and row.ip_restricted is True
    async with stack.world.sessions() as s:
        assert await s.get(Secret, old) is None  # révoquée après la bascule
        assert await s.get(Secret, row.secret_ref) is not None


@pytest.mark.parametrize(
    "outcome",
    [
        KeyPermissions(trading=True, withdrawal=True, ip_restricted=True),
        KeyPermissions(trading=True, withdrawal=None, ip_restricted=None),
        RuntimeError("venue injoignable"),
        60.0,
    ],
)
async def test_failed_rotation_leaves_the_old_key_intact(
    stack: Stack, monkeypatch: pytest.MonkeyPatch, outcome: Any
) -> None:
    from centrade_api.accounts import permissions

    monkeypatch.setattr(permissions, "PROBE_TIMEOUT_S", 0.05)
    admin = await stack.client("admin")
    aid = (await _account(admin))["id"]
    await admin.put(f"{A}/{aid}/secret", json=KEY)
    stack.app.dependency_overrides[get_permission_probe] = lambda: Probe(OK)
    await admin.post(f"{A}/{aid}/test")
    before = await _row(stack, aid)
    async with stack.world.sessions() as s:
        old = await s.get(Secret, before.secret_ref)
    assert old is not None
    count = await _secret_count(stack)
    stack.app.dependency_overrides[get_permission_probe] = lambda: Probe(outcome)

    r = await admin.post(f"{A}/{aid}/rotate", json={**KEY, "key": "TEST-SECRET-DO-NOT-USE-n"})

    assert r.status_code == 409 and "TEST-SECRET" not in r.text
    after = await _row(stack, aid)
    assert after.secret_ref == before.secret_ref
    assert after.permissions_verified_at == before.permissions_verified_at is not None
    assert await _secret_count(stack) == count  # la nouvelle n'est pas restée
    async with stack.world.sessions() as s:
        kept = await s.get(Secret, before.secret_ref)
        assert kept is not None
        assert (kept.ciphertext, kept.nonce) == (old.ciphertext, old.nonce)
        last = await s.scalar(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1))
    assert last is not None and last.action == "account.secret.rotate.refused"
    assert last.actor == f"user:{stack.last_account.id}"  # type: ignore[union-attr]


async def test_every_write_is_audited_with_its_author(stack: Stack) -> None:
    admin = await stack.client("admin")
    actor = f"user:{stack.last_account.id}"  # type: ignore[union-attr]
    aid = (await _account(admin))["id"]
    await admin.put(f"{A}/{aid}/secret", json=KEY)
    await admin.post(f"{A}/{aid}/test")
    stack.app.dependency_overrides[get_permission_probe] = lambda: Probe(OK)
    await admin.post(f"{A}/{aid}/rotate", json=KEY)
    async with stack.world.sessions() as s:
        rows = (
            await s.scalars(
                select(AuditLog).where(AuditLog.target == f"account:{aid}").order_by(AuditLog.seq)
            )
        ).all()
    assert [r.action for r in rows] == [
        "account.create",
        "account.secret.put",
        "account.test",
        "account.secret.rotate",
    ]
    assert {r.actor for r in rows} == {actor} and all(r.ip == "203.0.113.10" for r in rows)
