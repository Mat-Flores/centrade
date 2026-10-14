"""Engine REST client: one short call, bounded in time and size, outside the asynchronous
loop.

`freqtrade-client` is not used: it reads numbers as floats, ignores the HTTP code and
swallows connection errors. This deviates from SPEC §5 and §7, to be validated (ADR 0007). The
routes called are its own (ADR 0008).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import requests
from centrade_core.engine.contract import CommandRejected, EngineUnreachable

CONNECT_TIMEOUT_S = 2.0
READ_TIMEOUT_S = 5.0
EXIT_TIMEOUT_S = 20.0  # a forced exit goes through the venue: longer than a read
# Cap on a response read. A page of 200 closed trades weighs about a megabyte.
MAX_RESPONSE_BYTES = 16 * 1024**2


def _no_constant(name: str) -> Any:
    raise ValueError(f"constante JSON refusée : {name}")


def _decode(text: str) -> Any:
    # Money: decimal numbers in the response become Decimal, never float.
    return json.loads(text, parse_float=Decimal, parse_constant=_no_constant)


class EngineApi:
    def __init__(
        self,
        http: Callable[[], requests.Session],
        base_url: str,
        username: str,
        password: str,
    ) -> None:
        self._http = http
        self._base = f"{base_url}/api/v1/"
        self._auth = (username, password)

    def _request(
        self, method: str, path: str, body: Any, params: dict[str, Any] | None, read_s: float
    ) -> Any:
        try:
            with self._http() as session:
                resp = session.request(
                    method,
                    self._base + path,
                    auth=self._auth,
                    params=params,
                    data=None if body is None else json.dumps(body),
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                    timeout=(CONNECT_TIMEOUT_S, read_s),
                    allow_redirects=False,
                    stream=True,  # read in chunks: never more than the cap in memory
                )
                status, raw = resp.status_code, bytearray()
                for chunk in resp.iter_content(64 * 1024):
                    raw += chunk
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise EngineUnreachable("réponse du moteur trop volumineuse")
        except requests.RequestException as exc:
            raise EngineUnreachable(f"API du moteur injoignable : {type(exc).__name__}") from exc
        try:
            data = _decode(raw.decode("utf-8")) if raw else None
        except (ValueError, RecursionError) as exc:  # invalid JSON, too deep, badly encoded
            raise EngineUnreachable("réponse du moteur illisible") from exc
        if status == 502 and isinstance(data, dict):  # engine RPCException: business refusal
            raise CommandRejected(str(data.get("detail") or data.get("error") or "refus du moteur"))
        if status in (401, 403) or status >= 500:
            raise EngineUnreachable(f"API du moteur : code {status}")
        if status >= 400:
            raise CommandRejected(f"API du moteur : code {status}")
        if status != 200 or data is None:
            raise EngineUnreachable(f"réponse inattendue du moteur : code {status}")
        return data

    async def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        params: dict[str, Any] | None = None,
        read_s: float = READ_TIMEOUT_S,
    ) -> Any:
        return await asyncio.to_thread(self._request, method, path, body, params, read_s)

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self.call("GET", path, params=params)
