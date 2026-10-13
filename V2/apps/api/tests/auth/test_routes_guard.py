"""Refus par défaut : toute route de l'application exige une session, sauf liste blanche explicite.

Ce test parcourt les routes réelles : une route ajoutée par un autre lot sans dépendance
d'authentification le fait échouer. L'ouvrir au public se décide ici, en l'ajoutant à `PUBLIC`.
"""

import re
from collections.abc import Iterator

import httpx
from centrade_api.main import create_app
from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from starlette.routing import Route

from .conftest import MakeAccount

PUBLIC = {
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/system/health"),
    # Hors brief, public depuis M0 : description des routes d'un dépôt lui-même public.
    ("GET", "/api/v1/openapi.json"),
}
PRE_SESSION_ONLY = {("POST", "/api/v1/auth/totp")}
DUMMY_ID = "00000000-0000-7000-8000-000000000000"


def _routes(app: FastAPI) -> Iterator[tuple[str, str]]:
    # FastAPI 0.143 garde un routeur inclus sous forme paresseuse dans `app.routes` :
    # `iter_route_contexts` (celui du générateur OpenAPI) donne les routes effectives, préfixe
    # compris, y compris celles que `include_in_schema=False` cache du document.
    for context in iter_route_contexts(app.routes):
        # Tout ce qui n'est pas une route simple (montage, WebSocket) doit être examiné à la main.
        assert isinstance(context.original_route, Route), f"type inattendu : {context!r}"
        assert context.path, f"route sans chemin : {context!r}"
        for method in sorted((context.methods or set()) - {"HEAD", "OPTIONS"}):
            yield method, context.path


def _url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", DUMMY_ID, path)


def test_la_liste_blanche_ne_contient_que_des_routes_existantes() -> None:
    assert set(_routes(create_app())) >= PUBLIC | PRE_SESSION_ONLY


async def test_toute_route_hors_liste_blanche_exige_une_session(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    checked = 0
    for method, path in _routes(app):
        if (method, path) in PUBLIC:
            continue
        response = await client.request(method, _url(path))
        assert response.status_code == 401, f"{method} {path} répond sans session"
        checked += 1
    assert checked >= 3  # logout, me, totp au moins : le parcours n'est pas vide


async def test_la_pre_session_n_ouvre_aucune_route_protegee(
    app: FastAPI, client: httpx.AsyncClient, make_account: MakeAccount
) -> None:
    account = await make_account()
    login = await client.post(
        "/api/v1/auth/login", json={"username": account.email, "password": account.password}
    )
    assert login.status_code == 200

    for method, path in _routes(app):
        if (method, path) in PUBLIC | PRE_SESSION_ONLY:
            continue
        response = await client.request(method, _url(path))
        assert response.status_code == 401, f"{method} {path} s'ouvre avec une pré-session"
