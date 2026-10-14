"""RFC 7807 errors (application/problem+json), SPEC §8.

Source: https://fastapi.tiangolo.com/tutorial/handling-errors/
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def _problem(
    request: Request, status: int, headers: Mapping[str, str] | None = None, **extra: Any
) -> JSONResponse:
    try:
        title = HTTPStatus(status).phrase
    except ValueError:  # status outside the registry (499…)
        title = "Error"
    body = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "instance": request.url.path,
        **extra,
    }
    return JSONResponse(
        body, status_code=status, headers=headers, media_type="application/problem+json"
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # The headers carry `Allow`, `WWW-Authenticate`, `Retry-After`.
        return _problem(request, exc.status_code, exc.headers, detail=exc.detail)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # No detail: an exception message may contain a secret.
        return _problem(request, 500)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Neither "input" nor "ctx": the received value may be a secret.
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _problem(request, 422, errors=errors)
