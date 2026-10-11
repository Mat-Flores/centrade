"""Durées de session, rôles, ré-authentification TOTP, CSRF (SPEC §9, §13)."""

import httpx
import pytest

from .conftest import ORIGIN, PROBE, FakeClock, MakeAccount, MakeClient, SignIn

ME = "/api/v1/auth/me"


def _is_problem(response: httpx.Response, status: int) -> None:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == status
    assert {"type", "title", "detail", "instance"} <= set(body)


async def test_expiration_par_inactivite_de_30_minutes(
    client: httpx.AsyncClient, make_account: MakeAccount, sign_in: SignIn, clock: FakeClock
) -> None:
    await sign_in(client, await make_account())

    clock.advance(minutes=29)
    assert (await client.get(ME)).status_code == 200  # l'activité repousse l'échéance
    clock.advance(minutes=29)
    assert (await client.get(ME)).status_code == 200
    clock.advance(minutes=30)
    _is_problem(await client.get(ME), 401)


async def test_expiration_absolue_de_12_heures_malgre_l_activite(
    client: httpx.AsyncClient, make_account: MakeAccount, sign_in: SignIn, clock: FakeClock
) -> None:
    await sign_in(client, await make_account())

    for _ in range(28):  # 28 x 25 min = 11 h 40, toujours active
        clock.advance(minutes=25)
        assert (await client.get(ME)).status_code == 200
    clock.advance(minutes=20)

    _is_problem(await client.get(ME), 401)


async def test_absence_de_session_401_en_rfc_7807(client: httpx.AsyncClient) -> None:
    for path in (ME, f"{PROBE}/viewer"):
        response = await client.get(path)
        _is_problem(response, 401)
        assert "www-authenticate" in response.headers
    client.cookies.set("__Host-centrade_session", "SENTINELLE-jeton-invente")
    _is_problem(await client.get(ME), 401)


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        ("viewer", {"viewer"}),
        ("operator", {"viewer", "operator"}),
        ("admin", {"viewer", "operator", "admin"}),
    ],
)
async def test_role_insuffisant_403_en_rfc_7807(
    client: httpx.AsyncClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    role: str,
    allowed: set[str],
) -> None:
    account = await make_account(role)
    await sign_in(client, account)

    for needed in ("viewer", "operator", "admin"):
        response = await client.get(f"{PROBE}/{needed}")
        if needed in allowed:
            assert response.status_code == 200
            assert response.json() == {"actor": f"user:{account.id}"}
        else:
            _is_problem(response, 403)


async def test_reauthentification_totp_exigee_pour_une_action_dangereuse(
    client: httpx.AsyncClient, make_account: MakeAccount, sign_in: SignIn, clock: FakeClock
) -> None:
    await sign_in(client, await make_account())

    assert (await client.post(f"{PROBE}/dangerous")).status_code == 200
    clock.advance(minutes=4, seconds=59)
    assert (await client.post(f"{PROBE}/dangerous")).status_code == 200
    clock.advance(seconds=2)
    _is_problem(await client.post(f"{PROBE}/dangerous"), 403)
    assert (await client.get(ME)).status_code == 200  # la session, elle, reste valable


async def test_action_dangereuse_sans_session_401(client: httpx.AsyncClient) -> None:
    _is_problem(await client.post(f"{PROBE}/dangerous"), 401)


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://pirate.example"},
        {"Origin": "http://centrade.test"},  # même hôte, autre schéma
        {"Origin": "https://centrade.test.pirate.example"},
        {"Origin": "https://centrade.test:444"},
        {"Origin": "null"},
        {"Origin": ""},
        {},  # ni Origin ni Referer : refus par défaut
        {"Referer": "https://pirate.example/page"},
        {"Referer": "https://centrade.test.pirate.example/"},
        {"Referer": "https://centrade.test@pirate.example/"},
        {"Referer": "https://[illisible"},
        {"Origin": "https://pirate.example", "Referer": f"{ORIGIN}/"},  # Origin prime
    ],
)
async def test_origine_etrangere_refusee_sur_une_requete_qui_change_un_etat(
    make_client: MakeClient,
    make_account: MakeAccount,
    sign_in: SignIn,
    headers: dict[str, str],
) -> None:
    account = await make_account()
    legit = make_client()
    await sign_in(legit, account)
    # Le navigateur de la victime : ses cookies partent, l'origine est celle de l'attaquant.
    forged = make_client(origin=None)
    forged.cookies.update(legit.cookies)

    _is_problem(await forged.post(f"{PROBE}/write", headers=headers), 403)
    _is_problem(await forged.post("/api/v1/auth/logout", headers=headers), 403)
    login = await forged.post(
        "/api/v1/auth/login",
        json={"username": account.email, "password": account.password},
        headers=headers,
    )
    _is_problem(login, 403)  # CSRF de connexion
    assert (await legit.get(ME)).status_code == 200  # la session n'a pas été fermée


async def test_origine_attendue_acceptee_par_origin_ou_a_defaut_referer(
    make_client: MakeClient, make_account: MakeAccount, sign_in: SignIn
) -> None:
    legit = make_client()
    await sign_in(legit, await make_account())
    bare = make_client(origin=None)
    bare.cookies.update(legit.cookies)

    assert (await bare.post(f"{PROBE}/write", headers={"Origin": ORIGIN})).status_code == 200
    by_referer = await bare.post(f"{PROBE}/write", headers={"Referer": f"{ORIGIN}/cockpit?x=1"})
    assert by_referer.status_code == 200
    assert (await bare.get(ME)).status_code == 200  # une lecture n'exige pas d'origine
