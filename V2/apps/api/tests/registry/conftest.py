"""Fixtures du registre : opérateur et lecteur connectés, stratégie d'exemple en entrée."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
import yaml  # type: ignore[import-untyped]

# Fixtures de la suite d'authentification (base, application, comptes), réemployées telles quelles.
from auth.conftest import (  # type: ignore[import-not-found]  # noqa: F401
    app,
    clock,
    engine,
    make_account,
    make_client,
    migrated_url,
    pg_url,
    session_factory,
    settings,
    sign_in,
)

SMA = Path(__file__).resolve().parents[4] / "strategies" / "sma-cross"


@pytest.fixture
def sma() -> tuple[dict[str, Any], str]:
    """Manifest (JSON) et code de la stratégie d'exemple."""
    manifest = yaml.safe_load((SMA / "strategy.yaml").read_text(encoding="utf-8"))
    return manifest, (SMA / "SmaCross.py").read_text(encoding="utf-8")


AsUser = Callable[[str], Awaitable[httpx.AsyncClient]]


@pytest_asyncio.fixture
async def as_user(make_client, make_account, sign_in) -> AsUser:  # type: ignore[no-untyped-def]  # noqa: F811
    async def make(role: str) -> httpx.AsyncClient:
        c: httpx.AsyncClient = make_client()
        await sign_in(c, await make_account(role))
        return c

    return make
