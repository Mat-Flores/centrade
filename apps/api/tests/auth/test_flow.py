"""Connexion en deux étapes, anti-rejeu, codes de récupération, verrouillage (SPEC §13)."""

import asyncio
import hashlib
from datetime import timedelta

import httpx
import pytest
from centrade_api.auth import security
from centrade_core.models import Session, User
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .conftest import Account, FakeClock, MakeAccount, MakeClient, SignIn

LOGIN, TOTP, ME, LOGOUT = (f"/api/v1/auth/{p}" for p in ("login", "totp", "me", "logout"))
PRE_COOKIE, SESSION_COOKIE = "__Host-centrade_pre", "__Host-centrade_session"
WRONG = "SENTINELLE-mauvais-mot-de-passe"

Factory = async_sessionmaker[AsyncSession]


def _creds(account: Account, password: str | None = None) -> dict[str, str]:
    return {"username": account.email, "password": password or account.password}


def _set_cookie(response: httpx.Response, name: str) -> str:
    found = [c for c in response.headers.get_list("set-cookie") if c.startswith(f"{name}=")]
    assert len(found) == 1, response.headers
    return found[0]


async def _stages(factory: Factory, account: Account) -> list[str]:
    async with factory() as s:
        return list(await s.scalars(select(Session.stage).where(Session.user_id == account.id)))


async def _user(factory: Factory, account: Account) -> User:
    async with factory() as s:
        return (await s.execute(select(User).where(User.id == account.id))).scalar_one()


async def test_mot_de_passe_puis_totp_ouvre_une_session_complete(
    client: httpx.AsyncClient, make_account: MakeAccount, clock: FakeClock
) -> None:
    account = await make_account("operator")

    r = await client.post(LOGIN, json=_creds(account))
    assert r.status_code == 200
    assert r.json() == {"totp_required": True}
    assert SESSION_COOKIE not in client.cookies
    assert (await client.get(ME)).status_code == 401  # la pré-session n'ouvre rien

    r = await client.post(TOTP, json={"code": account.code(clock.now)})
    assert r.status_code == 200
    cookie = _set_cookie(r, SESSION_COOKIE)
    for attribute in ("Secure", "HttpOnly", "SameSite=strict", "Path=/"):
        assert attribute in cookie
    assert "Domain" not in cookie  # exigé par le préfixe __Host-
    assert PRE_COOKIE not in client.cookies  # effacé

    me = await client.get(ME)
    assert me.status_code == 200
    assert me.json() == {"id": str(account.id), "email": account.email, "role": "operator"}
    assert me.headers["cache-control"] == "no-store"


async def test_cookie_de_pre_session_distinct_et_court(
    client: httpx.AsyncClient, make_account: MakeAccount
) -> None:
    r = await client.post(LOGIN, json=_creds(await make_account()))
    cookie = _set_cookie(r, PRE_COOKIE)
    for attribute in ("Secure", "HttpOnly", "SameSite=strict", "Path=/", "Max-Age=300"):
        assert attribute in cookie


async def test_identifiant_insensible_a_la_casse_et_aux_espaces(
    client: httpx.AsyncClient, make_account: MakeAccount
) -> None:
    account = await make_account()
    r = await client.post(
        LOGIN, json={"username": f"  {account.email.upper()} ", "password": account.password}
    )
    assert r.status_code == 200


async def test_pas_de_session_complete_sans_totp(
    client: httpx.AsyncClient, make_account: MakeAccount, session_factory: Factory
) -> None:
    account = await make_account()
    await client.post(LOGIN, json=_creds(account))

    assert await _stages(session_factory, account) == ["pre_totp"]
    assert (await client.get(ME)).status_code == 401
    # Sans pré-session, le second facteur seul n'ouvre rien non plus.
    client.cookies.clear()
    assert (await client.post(TOTP, json={"code": "000000"})).status_code == 401
    assert await _stages(session_factory, account) == ["pre_totp"]


async def test_compte_sans_secret_totp_ne_peut_ouvrir_aucune_session(
    client: httpx.AsyncClient, make_account: MakeAccount, session_factory: Factory
) -> None:
    account = await make_account(with_totp=False)

    r = await client.post(LOGIN, json=_creds(account))

    assert r.status_code == 401
    assert "set-cookie" not in r.headers
    assert await _stages(session_factory, account) == []


async def test_pre_session_presentee_comme_session_est_refusee(
    client: httpx.AsyncClient, make_account: MakeAccount
) -> None:
    await client.post(LOGIN, json=_creds(await make_account()))
    pre_token = client.cookies[PRE_COOKIE]

    client.cookies.set(SESSION_COOKIE, pre_token)

    assert (await client.get(ME)).status_code == 401


async def test_pre_session_expire_apres_cinq_minutes(
    client: httpx.AsyncClient, make_account: MakeAccount, clock: FakeClock
) -> None:
    account = await make_account()
    await client.post(LOGIN, json=_creds(account))
    clock.advance(minutes=5, seconds=1)

    r = await client.post(TOTP, json={"code": account.code(clock.now)})

    assert r.status_code == 401


async def test_rotation_entre_pre_session_et_session(
    client: httpx.AsyncClient, make_account: MakeAccount, clock: FakeClock, session_factory: Factory
) -> None:
    account = await make_account()
    await client.post(LOGIN, json=_creds(account))
    pre_token = client.cookies[PRE_COOKIE]
    async with session_factory() as s:
        pre_id = (
            await s.execute(select(Session.id).where(Session.user_id == account.id))
        ).scalar_one()

    await client.post(TOTP, json={"code": account.code(clock.now)})

    token = client.cookies[SESSION_COOKIE]
    assert token != pre_token
    async with session_factory() as s:
        rows = (await s.execute(select(Session).where(Session.user_id == account.id))).scalars()
        (full,) = rows
    assert full.stage == "full"
    assert full.id != pre_id
    # L'ancien jeton ne vaut plus rien, ni comme pré-session ni comme session.
    client.cookies.clear()
    client.cookies.set(PRE_COOKIE, pre_token)
    clock.advance(seconds=30)
    assert (await client.post(TOTP, json={"code": account.code(clock.now)})).status_code == 401


async def test_jeton_de_session_en_clair_jamais_en_base(
    client: httpx.AsyncClient, make_account: MakeAccount, sign_in: SignIn, session_factory: Factory
) -> None:
    account = await make_account()
    await client.post(LOGIN, json=_creds(account))
    pre_token = client.cookies[PRE_COOKIE]
    async with session_factory() as s:
        pre_dump = (await s.execute(text("SELECT row_to_json(s)::text FROM sessions s"))).scalars()
        assert not any(pre_token in row for row in pre_dump)
    client.cookies.clear()

    await sign_in(client, account)

    token = client.cookies[SESSION_COOKIE]
    assert len(token) >= 43  # 256 bits d'aléa en base64url
    async with session_factory() as s:
        dump = "\n".join(
            (await s.execute(text("SELECT row_to_json(s)::text FROM sessions s"))).scalars()
        )
        stored = (
            await s.execute(select(Session.token_hash).where(Session.user_id == account.id))
        ).scalar_one()
    assert token not in dump
    assert stored == hashlib.sha256(token.encode()).hexdigest()


async def test_code_totp_rejoue_refuse(
    make_client: MakeClient, make_account: MakeAccount, clock: FakeClock
) -> None:
    account = await make_account()
    code = account.code(clock.now)
    first, second = make_client(), make_client(ip="203.0.113.11")
    await first.post(LOGIN, json=_creds(account))
    assert (await first.post(TOTP, json={"code": code})).status_code == 200

    # Le même code, encore valide dans sa fenêtre, intercepté et rejoué.
    await second.post(LOGIN, json=_creds(account))
    replay = await second.post(TOTP, json={"code": code})

    assert replay.status_code == 401
    assert SESSION_COOKIE not in second.cookies
    # Un code d'un pas antérieur au dernier accepté est refusé lui aussi.
    assert (await second.post(TOTP, json={"code": account.code(clock.now, -1)})).status_code == 401
    clock.advance(seconds=30)
    assert (await second.post(TOTP, json={"code": account.code(clock.now)})).status_code == 200


async def test_code_totp_accepte_a_un_pas_pres_seulement(
    client: httpx.AsyncClient, make_account: MakeAccount, clock: FakeClock
) -> None:
    account = await make_account()
    await client.post(LOGIN, json=_creds(account))

    assert (await client.post(TOTP, json={"code": account.code(clock.now, -2)})).status_code == 401
    assert (await client.post(TOTP, json={"code": account.code(clock.now, 2)})).status_code == 401
    assert (await client.post(TOTP, json={"code": account.code(clock.now, -1)})).status_code == 200


async def test_code_de_recuperation_utilisable_une_seule_fois(
    make_client: MakeClient, make_account: MakeAccount, session_factory: Factory
) -> None:
    account = await make_account()
    code = account.recovery_codes[0]
    first, second = make_client(), make_client(ip="203.0.113.11")

    await first.post(LOGIN, json=_creds(account))
    # Saisie tolérante : casse et tirets ne comptent pas.
    used = await first.post(TOTP, json={"code": code.lower().replace("-", " ")})
    assert used.status_code == 200
    assert (await first.get(ME)).status_code == 200

    await second.post(LOGIN, json=_creds(account))
    again = await second.post(TOTP, json={"code": code})
    assert again.status_code == 401
    assert SESSION_COOKIE not in second.cookies

    user = await _user(session_factory, account)
    assert len(user.recovery_code_hashes) == len(account.recovery_codes) - 1
    assert security.recovery_code_hash(code) not in user.recovery_code_hashes
    # Les autres codes restent valables.
    other = await second.post(TOTP, json={"code": account.recovery_codes[1]})
    assert other.status_code == 200


async def test_code_de_recuperation_en_clair_jamais_en_base(
    make_account: MakeAccount, session_factory: Factory
) -> None:
    account = await make_account()
    async with session_factory() as s:
        dump = (
            await s.execute(
                text("SELECT row_to_json(u)::text FROM users u WHERE id = :i"), {"i": account.id}
            )
        ).scalar_one()
    for secret in (*account.recovery_codes, account.totp_secret, account.password):
        assert secret not in dump
        assert secret.replace("-", "") not in dump


async def test_verrouillage_progressif_apres_echecs_repetes(
    client: httpx.AsyncClient, make_account: MakeAccount, clock: FakeClock, session_factory: Factory
) -> None:
    account = await make_account()
    for _ in range(4):
        assert (await client.post(LOGIN, json=_creds(account, WRONG))).status_code == 401
    assert (await _user(session_factory, account)).locked_until is None

    assert (await client.post(LOGIN, json=_creds(account, WRONG))).status_code == 401
    assert (await _user(session_factory, account)).locked_until == clock.now + timedelta(minutes=1)

    # Verrouillé : même le bon mot de passe est refusé, avec la même réponse qu'un échec.
    locked = await client.post(LOGIN, json=_creds(account))
    assert locked.status_code == 401
    assert "set-cookie" not in locked.headers
    assert (await _user(session_factory, account)).failed_attempts == 5  # pas de surenchère

    # Le verrou levé, un nouvel échec verrouille deux fois plus longtemps.
    clock.advance(minutes=1, seconds=1)
    assert (await client.post(LOGIN, json=_creds(account, WRONG))).status_code == 401
    assert (await _user(session_factory, account)).locked_until == clock.now + timedelta(minutes=2)

    clock.advance(minutes=2, seconds=1)
    assert (await client.post(LOGIN, json=_creds(account))).status_code == 200
    assert (await client.post(TOTP, json={"code": account.code(clock.now)})).status_code == 200
    user = await _user(session_factory, account)
    assert (user.failed_attempts, user.locked_until) == (0, None)


async def test_echecs_totp_repetes_verrouillent_le_compte(
    client: httpx.AsyncClient, make_account: MakeAccount, clock: FakeClock, session_factory: Factory
) -> None:
    account = await make_account()
    await client.post(LOGIN, json=_creds(account))
    bad = "000000" if account.code(clock.now) != "000000" else "111111"

    statuses = [(await client.post(TOTP, json={"code": bad})).status_code for _ in range(5)]

    assert statuses == [401, 401, 401, 401, 423]
    assert await _stages(session_factory, account) == []  # la pré-session est détruite
    # Le bon code ne sert plus : ni cette pré-session, ni une nouvelle tant que le verrou tient.
    assert (await client.post(TOTP, json={"code": account.code(clock.now)})).status_code == 401
    assert (await client.post(LOGIN, json=_creds(account))).status_code == 401


async def test_compte_verrouille_avec_pre_session_vivante_n_ouvre_rien(
    client: httpx.AsyncClient, make_account: MakeAccount, clock: FakeClock, session_factory: Factory
) -> None:
    # État que le code ne produit pas lui-même (verrou posé à la main) : refus quand même.
    account = await make_account()
    await client.post(LOGIN, json=_creds(account))
    async with session_factory() as s, s.begin():
        user = (await s.execute(select(User).where(User.id == account.id))).scalar_one()
        user.locked_until = clock.now + timedelta(minutes=10)

    r = await client.post(TOTP, json={"code": account.code(clock.now)})

    assert r.status_code == 423
    assert SESSION_COOKIE not in client.cookies
    assert await _stages(session_factory, account) == []


async def test_envois_simultanes_du_meme_facteur_n_ouvrent_qu_une_session(
    make_client: MakeClient, make_account: MakeAccount, clock: FakeClock, session_factory: Factory
) -> None:
    account = await make_account()
    for code in (account.code(clock.now), account.recovery_codes[0]):
        first, second = make_client(), make_client(ip="203.0.113.11")
        await first.post(LOGIN, json=_creds(account))
        second.cookies.set(PRE_COOKIE, first.cookies[PRE_COOKIE])  # la même pré-session, deux fois

        responses = await asyncio.gather(
            first.post(TOTP, json={"code": code}), second.post(TOTP, json={"code": code})
        )

        assert sorted(r.status_code for r in responses) == [200, 401]
        assert await _stages(session_factory, account) == ["full"]
        async with session_factory() as s, s.begin():
            await s.execute(delete(Session).where(Session.user_id == account.id))


async def test_echecs_simultanes_sont_tous_comptes(
    make_client: MakeClient, make_account: MakeAccount, session_factory: Factory
) -> None:
    account = await make_account()
    clients = [make_client(ip=f"203.0.113.{n}") for n in range(20, 28)]

    responses = await asyncio.gather(*(c.post(LOGIN, json=_creds(account, WRONG)) for c in clients))

    assert {r.status_code for r in responses} == {401}
    user = await _user(session_factory, account)
    # Huit essais en parallèle : cinq comptés, puis le verrou. Aucun compteur perdu.
    assert user.failed_attempts == 5
    assert user.locked_until is not None


async def test_mauvais_codes_simultanes_sont_tous_comptes(
    make_client: MakeClient, make_account: MakeAccount, clock: FakeClock, session_factory: Factory
) -> None:
    account = await make_account()
    first = make_client()
    await first.post(LOGIN, json=_creds(account))
    bad = "000000" if account.code(clock.now) != "000000" else "111111"
    clients = [first, *(make_client(ip=f"203.0.113.{n}") for n in range(30, 37))]
    for other in clients[1:]:
        other.cookies.set(PRE_COOKIE, first.cookies[PRE_COOKIE])

    responses = await asyncio.gather(*(c.post(TOTP, json={"code": bad}) for c in clients))

    # Cinq essais comptés, le cinquième verrouille ; les suivants trouvent le compte verrouillé
    # (423) ou la pré-session détruite (401), selon l'ordre d'arrivée. Aucun n'est compté en trop.
    statuses = [r.status_code for r in responses]
    assert set(statuses) == {401, 423}
    assert statuses.count(401) >= 4
    assert (await _user(session_factory, account)).failed_attempts == 5
    assert await _stages(session_factory, account) == []


async def test_reponse_identique_que_le_compte_existe_ou_non(
    client: httpx.AsyncClient, make_account: MakeAccount, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = await make_account()
    verifications: list[str | None] = []
    real = security.verify_password

    def spy(password_hash: str | None, password: str) -> bool:
        verifications.append(password_hash)
        return real(password_hash, password)

    monkeypatch.setattr(security, "verify_password", spy)

    known = await client.post(LOGIN, json=_creds(account, WRONG))
    unknown = await client.post(
        LOGIN, json={"username": "personne@example.test", "password": WRONG}
    )

    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()
    assert "set-cookie" not in known.headers and "set-cookie" not in unknown.headers
    # Temps comparable : un calcul argon2 dans les deux cas (empreinte factice pour l'inconnu).
    assert len(verifications) == 2
    assert verifications[1] is None


async def test_logout_ferme_la_session(
    client: httpx.AsyncClient, make_account: MakeAccount, sign_in: SignIn, session_factory: Factory
) -> None:
    account = await make_account()
    await sign_in(client, account)
    token = client.cookies[SESSION_COOKIE]

    r = await client.post(LOGOUT)

    assert r.status_code == 204
    assert "Max-Age=0" in _set_cookie(r, SESSION_COOKIE)
    assert await _stages(session_factory, account) == []
    client.cookies.set(SESSION_COOKIE, token)  # un jeton volé avant la déconnexion
    assert (await client.get(ME)).status_code == 401


async def test_nouvelle_connexion_purge_les_sessions_expirees(
    client: httpx.AsyncClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    clock: FakeClock,
    session_factory: Factory,
) -> None:
    account = await make_account()
    await sign_in(client, account)
    clock.advance(hours=12, seconds=1)
    client.cookies.clear()

    await sign_in(client, account)

    async with session_factory() as s:
        count = await s.scalar(
            select(func.count()).select_from(Session).where(Session.user_id == account.id)
        )
    assert count == 1


async def test_limitation_de_debit_par_ip(
    make_client: MakeClient, make_account: MakeAccount, clock: FakeClock
) -> None:
    account = await make_account()
    noisy, quiet = make_client(ip="198.51.100.1"), make_client(ip="198.51.100.2")
    body = {"username": "personne@example.test", "password": WRONG}

    statuses = [(await noisy.post(LOGIN, json=body)).status_code for _ in range(11)]

    assert statuses == [401] * 10 + [429]
    limited = await noisy.post(LOGIN, json=_creds(account))  # même avec de bons identifiants
    assert limited.status_code == 429
    assert limited.headers["content-type"].startswith("application/problem+json")
    assert int(limited.headers["retry-after"]) == 60
    assert (await noisy.post(TOTP, json={"code": "000000"})).status_code == 429
    assert (await quiet.post(LOGIN, json=_creds(account))).status_code == 200  # autre adresse
    clock.advance(seconds=61)
    assert (await noisy.post(LOGIN, json=_creds(account))).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"username": "a@example.test"},
        {"username": "", "password": "x"},
        {"username": "a@example.test", "password": ""},
        {"username": "a@example.test", "password": "x" * 2000},
        {"username": "a" * 300, "password": "x"},
    ],
)
async def test_login_valide_strictement_ses_entrees(
    client: httpx.AsyncClient, body: dict[str, str]
) -> None:
    r = await client.post(LOGIN, json=body)

    assert r.status_code == 422
    assert "x" * 50 not in r.text  # la valeur reçue n'est jamais renvoyée
