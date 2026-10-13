"""Ré-authentification TOTP d'une session ouverte : `POST /auth/totp/confirm` (SPEC §9, §13)."""

import asyncio
import io
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
import pyotp
from centrade_api.auth import Principal, current_user, routes, security
from centrade_api.core.deps import get_db, utcnow
from centrade_core.ids import uuid7
from centrade_core.models import AuditLog, Session, User
from fastapi import Cookie, Depends, FastAPI
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .conftest import PROBE, Account, FakeClock, MakeAccount, MakeClient, SignIn

CONFIRM, LOGIN, ME = (f"/api/v1/auth/{p}" for p in ("totp/confirm", "login", "me"))
DANGEROUS = f"{PROBE}/dangerous"
SESSION_COOKIE = "__Host-centrade_session"

Factory = async_sessionmaker[AsyncSession]


async def _sessions(factory: Factory, account: Account) -> list[Session]:
    async with factory() as s:
        rows = await s.scalars(
            select(Session).where(Session.user_id == account.id).order_by(Session.created_at)
        )
        return list(rows)


async def _user(factory: Factory, account: Account) -> User:
    async with factory() as s:
        return (await s.execute(select(User).where(User.id == account.id))).scalar_one()


async def _actions(factory: Factory, account: Account) -> list[tuple[str, str]]:
    async with factory() as s:
        rows = await s.execute(
            select(AuditLog.action, AuditLog.actor)
            .where(AuditLog.target == f"user:{account.id}")
            .order_by(AuditLog.seq)
        )
        return [(r.action, r.actor) for r in rows]


def _wrong(account: Account, clock: FakeClock) -> str:
    near = {account.code(clock.now, o) for o in (-1, 0, 1)}
    return next(c for c in ("000000", "111111", "222222", "333333") if c not in near)


def _refused(response: httpx.Response) -> dict[str, object]:
    assert response.status_code == 403, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body: dict[str, object] = response.json()
    assert body["detail"] == "Code refusé."
    assert "set-cookie" not in response.headers
    return body


async def test_code_valide_rafraichit_le_totp_de_la_session(
    client: httpx.AsyncClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    await sign_in(client, account)
    (opened,) = await _sessions(session_factory, account)
    clock.advance(minutes=6)
    assert (await client.post(DANGEROUS)).status_code == 403

    r = await client.post(CONFIRM, json={"code": account.code(clock.now)})

    assert r.status_code == 204
    assert r.content == b""
    assert "set-cookie" not in r.headers  # ni nouveau jeton ni nouvelle échéance de cookie
    assert (await client.post(DANGEROUS)).status_code == 200
    (session,) = await _sessions(session_factory, account)
    assert session.totp_verified_at == clock.now
    # Même session, même échéance absolue : seule la date du TOTP a bougé.
    assert (session.id, session.expires_at) == (opened.id, opened.expires_at)
    author = f"user:{account.id}"
    assert (await _actions(session_factory, account))[-1] == ("auth.totp_confirm.succeeded", author)
    # La confirmation vaut cinq minutes, pas plus.
    clock.advance(minutes=5, seconds=1)
    assert (await client.post(DANGEROUS)).status_code == 403


async def test_code_faux_refuse_sans_rien_rafraichir_ni_fermer_la_session(
    client: httpx.AsyncClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    await sign_in(client, account)
    (opened,) = await _sessions(session_factory, account)
    clock.advance(minutes=6)

    _refused(await client.post(CONFIRM, json={"code": _wrong(account, clock)}))

    (session,) = await _sessions(session_factory, account)
    assert session.totp_verified_at == opened.totp_verified_at
    assert session.expires_at == opened.expires_at
    assert (await client.get(ME)).status_code == 200
    assert (await client.post(DANGEROUS)).status_code == 403
    assert (await _user(session_factory, account)).failed_attempts == 1
    author = f"user:{account.id}"
    assert (await _actions(session_factory, account))[-1] == ("auth.totp_confirm.failed", author)


async def test_code_rejoue_refuse_comme_un_code_faux(
    client: httpx.AsyncClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    await sign_in(client, account)
    (opened,) = await _sessions(session_factory, account)

    # Le code qui vient d'ouvrir la session, encore dans sa fenêtre.
    from_login = _refused(await client.post(CONFIRM, json={"code": account.code(clock.now)}))
    # Un pas plus ancien que le dernier accepté : refusé lui aussi.
    _refused(await client.post(CONFIRM, json={"code": account.code(clock.now, -1)}))
    (session,) = await _sessions(session_factory, account)
    assert session.totp_verified_at == opened.totp_verified_at

    clock.advance(minutes=6)
    code = account.code(clock.now)
    assert (await client.post(CONFIRM, json={"code": code})).status_code == 204
    clock.advance(seconds=1)
    replayed = _refused(await client.post(CONFIRM, json={"code": code}))
    (session,) = await _sessions(session_factory, account)
    assert session.totp_verified_at == clock.now - timedelta(seconds=1)

    # Aucun indice : rejeu et code faux donnent la même réponse.
    wrong = _refused(await client.post(CONFIRM, json={"code": _wrong(account, clock)}))
    assert from_login == replayed == wrong


async def test_code_de_recuperation_refuse_et_non_consomme(
    client: httpx.AsyncClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    await sign_in(client, account)
    clock.advance(minutes=6)
    wrong = _refused(await client.post(CONFIRM, json={"code": _wrong(account, clock)}))

    for code in (account.recovery_codes[0], account.recovery_codes[1].lower().replace("-", " ")):
        assert _refused(await client.post(CONFIRM, json={"code": code})) == wrong

    assert (await client.post(DANGEROUS)).status_code == 403
    user = await _user(session_factory, account)
    assert len(user.recovery_code_hashes) == len(account.recovery_codes)  # aucun n'est brûlé
    assert user.failed_attempts == 3  # compté comme tout autre refus


async def test_sans_session_complete_refuse(
    client: httpx.AsyncClient, make_account: MakeAccount, clock: FakeClock, session_factory: Factory
) -> None:
    account = await make_account()
    code = {"code": account.code(clock.now)}

    assert (await client.post(CONFIRM, json=code)).status_code == 401  # aucun cookie

    creds = {"username": account.email, "password": account.password}
    assert (await client.post(LOGIN, json=creds)).status_code == 200
    assert (await client.post(CONFIRM, json=code)).status_code == 401  # pré-session seule
    # La pré-session présentée comme session ne passe pas davantage.
    client.cookies.set(SESSION_COOKIE, client.cookies["__Host-centrade_pre"])
    assert (await client.post(CONFIRM, json=code)).status_code == 401

    (pre,) = await _sessions(session_factory, account)
    assert (pre.stage, pre.totp_verified_at) == ("pre_totp", None)
    user = await _user(session_factory, account)
    assert (user.failed_attempts, user.totp_last_step) == (0, None)  # le code n'a pas été lu


async def test_autre_origine_refusee(
    make_client: MakeClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    legit = make_client()
    await sign_in(legit, account)
    (opened,) = await _sessions(session_factory, account)
    clock.advance(minutes=6)
    forged = make_client(origin=None)
    forged.cookies.update(legit.cookies)
    code = {"code": account.code(clock.now)}

    for headers in ({"Origin": "https://pirate.example"}, {}):
        r = await forged.post(CONFIRM, json=code, headers=headers)
        assert r.status_code == 403
        assert r.json()["detail"] == "Origine de la requête refusée."

    (session,) = await _sessions(session_factory, account)
    assert session.totp_verified_at == opened.totp_verified_at
    assert (await legit.post(CONFIRM, json=code)).status_code == 204  # le code n'a pas été brûlé


async def test_echecs_repetes_verrouillent_puis_un_code_valide_est_refuse(
    client: httpx.AsyncClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    await sign_in(client, account)
    (opened,) = await _sessions(session_factory, account)
    clock.advance(minutes=6)
    bad = {"code": _wrong(account, clock)}

    statuses = [(await client.post(CONFIRM, json=bad)).status_code for _ in range(5)]

    assert statuses == [403, 403, 403, 403, 423]
    user = await _user(session_factory, account)
    assert user.locked_until == clock.now + timedelta(minutes=1)  # le même verrou que la connexion
    locked = await client.post(CONFIRM, json={"code": account.code(clock.now)})
    assert locked.status_code == 423
    assert locked.headers["content-type"].startswith("application/problem+json")
    user = await _user(session_factory, account)
    assert user.failed_attempts == 5  # un essai pendant le verrou ne le prolonge pas
    (session,) = await _sessions(session_factory, account)
    assert session.totp_verified_at == opened.totp_verified_at
    assert (await client.get(ME)).status_code == 200  # la session reste ouverte
    assert (await client.post(DANGEROUS)).status_code == 403
    author = f"user:{account.id}"
    assert (await _actions(session_factory, account))[-7:] == [
        *[("auth.totp_confirm.failed", author)] * 5,
        ("auth.account.locked", "system:auth"),
        ("auth.totp_confirm.failed", author),  # essai pendant le verrou : audité, pas compté
    ]

    # Le verrou levé, un code valide passe ; le compteur d'échecs ne repart pas de zéro.
    clock.advance(minutes=1, seconds=1)
    assert (await client.post(CONFIRM, json={"code": account.code(clock.now)})).status_code == 204
    assert (await _user(session_factory, account)).failed_attempts == 5


async def test_echecs_de_connexion_et_de_confirmation_partagent_le_meme_compteur(
    make_client: MakeClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    client, elsewhere = make_client(), make_client(ip="203.0.113.11")
    await sign_in(client, account)
    clock.advance(minutes=6)
    for _ in range(3):
        r = await elsewhere.post(LOGIN, json={"username": account.email, "password": "SENTINELLE"})
        assert r.status_code == 401

    bad = {"code": _wrong(account, clock)}
    statuses = [(await client.post(CONFIRM, json=bad)).status_code for _ in range(2)]

    assert statuses == [403, 423]
    assert (await _user(session_factory, account)).failed_attempts == 5


async def test_la_confirmation_ne_rafraichit_que_sa_session(
    make_client: MakeClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    first, second = make_client(), make_client(ip="203.0.113.11")
    await sign_in(first, account)
    clock.advance(seconds=30)  # un autre pas TOTP pour la seconde ouverture
    await sign_in(second, account)
    before = {s.id: s.totp_verified_at for s in await _sessions(session_factory, account)}
    assert len(before) == 2
    clock.advance(minutes=6)

    assert (await first.post(CONFIRM, json={"code": account.code(clock.now)})).status_code == 204

    after = {s.id: s.totp_verified_at for s in await _sessions(session_factory, account)}
    changed = [sid for sid in before if after[sid] != before[sid]]
    assert len(changed) == 1
    assert after[changed[0]] == clock.now
    assert (await first.post(DANGEROUS)).status_code == 200
    assert (await second.post(DANGEROUS)).status_code == 403


async def test_un_meme_code_envoye_par_deux_sessions_n_en_rafraichit_qu_une(
    make_client: MakeClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    first, second = make_client(), make_client(ip="203.0.113.11")
    await sign_in(first, account)
    clock.advance(seconds=30)
    await sign_in(second, account)
    clock.advance(minutes=6)
    code = {"code": account.code(clock.now)}

    responses = await asyncio.gather(
        first.post(CONFIRM, json=code), second.post(CONFIRM, json=code)
    )

    assert sorted(r.status_code for r in responses) == [204, 403]
    fresh = [
        s for s in await _sessions(session_factory, account) if s.totp_verified_at == clock.now
    ]
    assert len(fresh) == 1


async def test_le_dernier_pas_est_relu_sous_verrou_et_non_tel_que_charge_par_la_session(
    app: FastAPI,
    client: httpx.AsyncClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    # La course rendue déterministe : entre le contrôle de session (qui charge l'utilisateur)
    # et le `FOR UPDATE`, une autre requête consomme le même code. L'objet déjà chargé ne doit
    # pas masquer la ligne relue, que le ramasse-miettes l'ait libéré ou non.
    account = await make_account()
    await sign_in(client, account)
    (opened,) = await _sessions(session_factory, account)
    clock.advance(minutes=6)
    code = account.code(clock.now)
    step = security.totp_step(account.totp_secret, code, clock.now)
    loaded: list[User | None] = []

    async def overtaken(
        db: Annotated[AsyncSession, Depends(get_db)],
        now: Annotated[datetime, Depends(utcnow)],
        token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> Principal:
        principal = await current_user(db, now, token)
        # Tenu en vie : la session SQLAlchemy ne garde ses objets que par référence faible.
        loaded.append(await db.get(User, account.id))
        await db.commit()
        async with session_factory() as other, other.begin():
            await other.execute(
                update(User).where(User.id == account.id).values(totp_last_step=step)
            )
        return principal

    app.dependency_overrides[current_user] = overtaken

    _refused(await client.post(CONFIRM, json={"code": code}))

    (session,) = await _sessions(session_factory, account)
    assert session.totp_verified_at == opened.totp_verified_at


async def test_la_confirmation_ne_prolonge_pas_la_session(
    client: httpx.AsyncClient, make_account: MakeAccount, sign_in: SignIn, clock: FakeClock
) -> None:
    account = await make_account()
    await sign_in(client, account)

    for _ in range(28):  # 28 x 25 min = 11 h 40, une confirmation à chaque fois
        clock.advance(minutes=25)
        r = await client.post(CONFIRM, json={"code": account.code(clock.now)})
        assert r.status_code == 204
    clock.advance(minutes=20)  # 12 h : durée absolue atteinte malgré les confirmations

    assert (await client.post(CONFIRM, json={"code": account.code(clock.now)})).status_code == 401
    assert (await client.get(ME)).status_code == 401


async def test_session_inactive_depuis_30_minutes_ne_peut_pas_confirmer(
    client: httpx.AsyncClient, make_account: MakeAccount, sign_in: SignIn, clock: FakeClock
) -> None:
    account = await make_account()
    await sign_in(client, account)
    clock.advance(minutes=30)

    assert (await client.post(CONFIRM, json={"code": account.code(clock.now)})).status_code == 401


async def test_secret_totp_illisible_503_sans_compter_d_echec(
    client: httpx.AsyncClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    await sign_in(client, account)
    (opened,) = await _sessions(session_factory, account)
    clock.advance(minutes=6)
    async with session_factory() as s, s.begin():
        user = (await s.execute(select(User).where(User.id == account.id))).scalar_one()
        assert user.totp_secret_enc is not None
        user.totp_secret_enc = bytes(b ^ 1 for b in user.totp_secret_enc)

    r = await client.post(CONFIRM, json={"code": account.code(clock.now)})

    assert r.status_code == 503
    (session,) = await _sessions(session_factory, account)
    assert session.totp_verified_at == opened.totp_verified_at
    assert (await _user(session_factory, account)).failed_attempts == 0


async def test_corps_invalide_422_sans_renvoyer_la_valeur(
    client: httpx.AsyncClient, make_account: MakeAccount, sign_in: SignIn
) -> None:
    await sign_in(client, await make_account())

    for body in ({}, {"code": ""}, {"code": "9" * 65}, {"code": 123456}):
        r = await client.post(CONFIRM, json=body)
        assert r.status_code == 422, body
        assert "9" * 50 not in r.text


async def test_le_code_saisi_n_apparait_ni_dans_les_logs_ni_dans_l_audit(
    logs: io.StringIO,
    client: httpx.AsyncClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    await sign_in(client, account)
    clock.advance(minutes=6)
    good, bad = account.code(clock.now), _wrong(account, clock)
    sentinel = "SENTINELLE-code-0xC0FFEE"

    assert (await client.post(CONFIRM, json={"code": sentinel})).status_code == 403
    assert (await client.post(CONFIRM, json={"code": bad})).status_code == 403
    assert (await client.post(CONFIRM, json={"code": account.recovery_codes[0]})).status_code == 403
    assert (await client.post(CONFIRM, json={"code": good})).status_code == 204
    assert (await client.post(CONFIRM, json={"code": good})).status_code == 403  # rejeu

    async with session_factory() as s:
        audit = "\n".join(
            await s.scalars(
                text("SELECT row_to_json(a)::text FROM audit_log a WHERE target = :t"),
                {"t": f"user:{account.id}"},
            )
        )
    output = logs.getvalue()
    assert "auth_totp_confirm_failed" in output and "auth_totp_confirm_succeeded" in output
    assert "auth.totp_confirm.failed" in audit and "auth.totp_confirm.succeeded" in audit
    for haystack in (output, audit):
        assert sentinel not in haystack
        assert account.recovery_codes[0] not in haystack
        for code in (good, bad):  # six chiffres : pas noyés dans un autre nombre
            assert not re.search(f"(?<![0-9]){code}(?![0-9])", haystack)


_KEY = bytes(range(32))
_SECRET = "JBSWY3DPEHPK3PXP"  # noqa: S105  # secret de la documentation de pyotp, pas un vrai
_NOW = datetime(2026, 1, 1, 12, 0, 7, tzinfo=UTC)
_RECOVERY = security.new_recovery_codes()


def _enrolled(last_step: int | None) -> User:
    user = User(
        id=uuid7(),
        username="sentinelle@example.test",
        role="admin",
        password_hash="x",  # noqa: S106  # jamais vérifié ici
        recovery_code_hashes=[security.recovery_code_hash(c) for c in _RECOVERY],
        totp_last_step=last_step,
    )
    user.totp_nonce, user.totp_secret_enc = security.encrypt_totp_secret(
        master_key=_KEY, user_id=user.id, secret=_SECRET
    )
    return user


_CURRENT = security.totp_step(_SECRET, pyotp.TOTP(_SECRET).at(_NOW), _NOW)
assert _CURRENT is not None


@given(
    back=st.one_of(st.none(), st.integers(min_value=-3, max_value=3)),
    offset=st.integers(min_value=-3, max_value=3),
)
def test_propriete_un_pas_n_est_accepte_que_frais_et_proche(back: int | None, offset: int) -> None:
    """Accepté si et seulement si le pas est à un pas près de l'instant et après le dernier."""
    assert _CURRENT is not None
    last = None if back is None else _CURRENT + back
    user = _enrolled(last)
    hashes = list(user.recovery_code_hashes)

    accepted = routes._totp_accepted(user, pyotp.TOTP(_SECRET).at(_NOW, offset), _NOW, _KEY)

    step = _CURRENT + offset
    assert accepted == (abs(offset) <= 1 and (last is None or step > last))
    assert user.totp_last_step == (step if accepted else last)  # ne recule jamais
    assert user.recovery_code_hashes == hashes


@given(
    code=st.one_of(
        st.text(max_size=64),
        st.sampled_from(_RECOVERY),
        st.sampled_from(_RECOVERY).map(lambda c: c.lower().replace("-", " ")),
    )
)
def test_propriete_rien_d_autre_qu_un_code_totp_n_est_accepte(code: str) -> None:
    valid = {pyotp.TOTP(_SECRET).at(_NOW, o) for o in (-1, 0, 1)}
    user = _enrolled(None)
    hashes = list(user.recovery_code_hashes)

    accepted = routes._totp_accepted(user, code, _NOW, _KEY)

    assert accepted == (code in valid)
    assert user.recovery_code_hashes == hashes  # un code de récupération n'est jamais consommé
    if not accepted:
        assert user.totp_last_step is None
