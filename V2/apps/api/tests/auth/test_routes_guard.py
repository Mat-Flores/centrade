"""Refuse by default: every route of the application requires a session, bar an explicit allowlist.

This test walks the real routes: a route added by another batch without an authentication
dependency makes it fail. Opening it to the public is decided here, by adding it to `PUBLIC`.
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
    # Outside the brief, public since M0: description of the routes of a repo that is itself public.
    ("GET", "/api/v1/openapi.json"),
}
PRE_SESSION_ONLY = {("POST", "/api/v1/auth/totp")}
DUMMY_ID = "00000000-0000-7000-8000-000000000000"


def _routes(app: FastAPI) -> Iterator[tuple[str, str]]:
    # FastAPI 0.143 keeps an included router in lazy form in `app.routes`:
    # `iter_route_contexts` (that of the OpenAPI generator) gives the effective routes, prefix
    # included, including those that `include_in_schema=False` hides from the document.
    for context in iter_route_contexts(app.routes):
        # Anything that is not a simple route (mount, WebSocket) must be examined by hand.
        assert isinstance(context.original_route, Route), f"type inattendu : {context!r}"
        assert context.path, f"route sans chemin : {context!r}"
        for method in sorted((context.methods or set()) - {"HEAD", "OPTIONS"}):
            yield method, context.path


def _url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", DUMMY_ID, path)


def test_allowlist_contains_only_existing_routes() -> None:
    assert set(_routes(create_app())) >= PUBLIC | PRE_SESSION_ONLY


async def test_every_route_outside_the_allowlist_requires_a_session(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    checked = 0
    for method, path in _routes(app):
        if (method, path) in PUBLIC:
            continue
        response = await client.request(method, _url(path))
        assert response.status_code == 401, f"{method} {path} répond sans session"
        checked += 1
    assert checked >= 3  # logout, me, totp at least: the walk is not empty


async def test_pre_session_opens_no_protected_route(
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
