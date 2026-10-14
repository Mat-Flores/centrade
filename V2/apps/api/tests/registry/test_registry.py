"""Strategy registry (SPEC F1, §7, §8): deposit of a version, checks, immutability."""

import asyncio
import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from centrade_core.models import AuditLog
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .conftest import AsUser

Dep = tuple[dict[str, Any], str]
H = {"Idempotency-Key": "cle-de-test-0001"}


async def _strategy(c: httpx.AsyncClient, name: str | None = None) -> str:
    r = await c.post("/api/v1/strategies", json={"name": name or f"s-{uuid4().hex[:8]}"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _deposit(
    c: httpx.AsyncClient, sid: str, manifest: dict[str, Any], code: str, key: str | None = None
) -> httpx.Response:
    return await c.post(
        f"/api/v1/strategies/{sid}/versions",
        json={"manifest": manifest, "code": code},
        headers={"Idempotency-Key": key or f"cle-{uuid4().hex}"},
    )


async def test_example_strategy_is_accepted_end_to_end(as_user: AsUser, sma: Dep) -> None:
    c = await as_user("operator")
    sid = await _strategy(c)
    r = await _deposit(c, sid, *sma)

    assert r.status_code == 201, r.text
    v = r.json()
    assert (v["version"], v["status"], v["engine"]) == (1, "draft", sma[0]["engine"])
    assert len(v["code_hash"]) == 64
    assert v["exits"]["stoploss"] == "-0.05"  # decimal string, never a float
    assert v["manifest"]["sizing"]["stake_amount"] == "50"
    assert v["static_checks"]["ok"] is True
    assert v["author"].startswith("user:")
    got = (await c.get(f"/api/v1/strategies/{sid}/versions/1")).json()
    assert got["code"] == sma[1] and got["code_hash"] == v["code_hash"]
    listing = (await c.get(f"/api/v1/strategies/{sid}/versions")).json()
    assert [i["version"] for i in listing["items"]] == [1]
    assert "code" not in listing["items"][0]


def _no_stoploss(m: dict[str, Any], code: str) -> Dep:
    del m["exits"]["stoploss"]
    return m, code


def _mut(path: str, value: Any) -> Any:
    def go(m: dict[str, Any], code: str) -> Dep:
        node = m
        *head, last = path.split(".")
        for k in head:
            node = node[k]
        node[last] = value
        return m, code

    return go


REFUSALS = {
    "class without the base": lambda m, c: (m, c.replace("(ControlPlaneStrategy)", "(object)")),
    "overridden hook": lambda m, c: (
        m,
        c + "\n    def confirm_trade_entry(self, *a, **k):\n        return True\n",
    ),
    "forbidden import": lambda m, c: (m, "import socket\n" + c),
    "no stoploss": _no_stoploss,
    "trading_mode futures": _mut("trading_mode", "futures"),
    "unknown engine": _mut("engine", "inconnu"),
    "default outside schema": _mut("params_schema.properties.fast.default", 1),
    "float stoploss": _mut("exits.stoploss", -0.05),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
async def test_rejected_version_is_not_stored(
    case: str, as_user: AsUser, sma: Dep, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    c = await as_user("operator")
    sid = await _strategy(c)
    manifest, code = json.loads(json.dumps(sma[0])), sma[1]
    r = await _deposit(c, sid, *REFUSALS[case](manifest, code))

    assert r.status_code == 422, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["detail"], "la réponse liste les motifs"
    listing = (await c.get(f"/api/v1/strategies/{sid}/versions")).json()
    assert listing["items"] == []


async def test_rejection_reasons_are_listed(as_user: AsUser, sma: Dep) -> None:
    c = await as_user("operator")
    sid = await _strategy(c)
    code = "import socket\n" + sma[1].replace("(ControlPlaneStrategy)", "(object)")
    r = await _deposit(c, sid, sma[0], code)
    assert r.status_code == 422 and len(r.json()["detail"]) >= 2


async def test_no_route_modifies_a_version(as_user: AsUser, sma: Dep, app: FastAPI) -> None:
    c = await as_user("operator")
    sid = await _strategy(c)
    await _deposit(c, sid, *sma)
    url = f"/api/v1/strategies/{sid}/versions/1"
    for method in ("PUT", "DELETE"):
        assert (await c.request(method, url, json={})).status_code == 405
    # The only PATCH changes the status: any other field is refused.
    bodies: list[dict[str, Any]] = [
        {"manifest": sma[0]},
        {"code": "x"},
        {"exits": {}},
        {"status": "approved", "code": "x"},
    ]
    for body in bodies:
        assert (await c.patch(url, json=body)).status_code == 422
    got = (await c.get(url)).json()
    assert got["code"] == sma[1] and got["status"] == "draft"
    writes = {
        (m.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if path.startswith("/api/v1/strategies")
        for m in ops
        if m != "get"
    }
    assert writes == {
        ("POST", "/api/v1/strategies"),
        ("POST", "/api/v1/strategies/{strategy_id}/versions"),
        ("PATCH", "/api/v1/strategies/{strategy_id}/versions/{version}"),
    }


async def test_same_submission_with_same_key_creates_no_second_version(
    as_user: AsUser, sma: Dep
) -> None:
    c = await as_user("operator")
    sid = await _strategy(c)
    first = await _deposit(c, sid, *sma, key="rejeu-0001")
    again = await _deposit(c, sid, *sma, key="rejeu-0001")

    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert len((await c.get(f"/api/v1/strategies/{sid}/versions")).json()["items"]) == 1
    other = await _deposit(c, sid, sma[0], sma[1] + "\n# autre", key="rejeu-0001")
    assert other.status_code == 422  # same key, other content: loud failure


async def test_two_concurrent_submissions_get_two_numbers(as_user: AsUser, sma: Dep) -> None:
    c = await as_user("operator")
    sid = await _strategy(c)
    rs = await asyncio.gather(*(_deposit(c, sid, sma[0], sma[1] + f"\n# {i}") for i in range(4)))
    assert sorted(r.json()["version"] for r in rs) == [1, 2, 3, 4]


async def test_code_hash_depends_on_code_and_manifest_only(as_user: AsUser, sma: Dep) -> None:
    c = await as_user("operator")
    m, code = sma
    sid = await _strategy(c)
    base = (await _deposit(c, sid, m, code)).json()["code_hash"]
    same = (await _deposit(c, sid, dict(reversed(list(m.items()))), code)).json()
    assert same["code_hash"] == base and same["version"] == 2  # key order has no effect
    other_code = (await _deposit(c, sid, m, code + "\n# x")).json()["code_hash"]
    other_manifest = (await _deposit(c, sid, {**m, "timeframes": ["1h"]}, code)).json()["code_hash"]
    assert len({base, other_code, other_manifest}) == 3


async def test_statuses_rbac_and_audit(
    as_user: AsUser, sma: Dep, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op, viewer = await as_user("operator"), await as_user("viewer")
    assert (await viewer.post("/api/v1/strategies", json={"name": "x"})).status_code == 403
    sid = await _strategy(op)
    assert (await _deposit(viewer, sid, *sma)).status_code == 403
    v = (await _deposit(op, sid, *sma)).json()
    url = f"/api/v1/strategies/{sid}/versions/1"
    assert (await viewer.patch(url, json={"status": "approved"})).status_code == 403
    assert (await viewer.get(url)).status_code == 200  # read allowed
    assert (await op.patch(url, json={"status": "retired"})).status_code == 409  # draft -> approved
    ok = await op.patch(url, json={"status": "approved"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    assert ok.json()["code_hash"] == v["code_hash"]
    assert (await op.patch(url, json={"status": "retired"})).json()["status"] == "retired"
    assert (await op.patch(url, json={"status": "approved"})).status_code == 409

    async with session_factory() as s:
        rows = (
            await s.scalars(
                select(AuditLog).where(AuditLog.action.like("strategy%")).order_by(AuditLog.seq)
            )
        ).all()
    ours = [r for r in rows if r.target in {f"strategy:{sid}", f"strategy_version:{v['id']}"}]
    assert [r.action for r in ours] == [
        "strategy.create", "strategy.version.create", "strategy.version.status",
        "strategy.version.status",
    ]  # fmt: skip
    assert all(r.actor.startswith("user:") for r in ours)


async def test_strategies_are_paginated(as_user: AsUser) -> None:
    c = await as_user("operator")
    for _ in range(3):
        await _strategy(c)
    page = (await c.get("/api/v1/strategies", params={"limit": 2})).json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    nxt = (
        await c.get("/api/v1/strategies", params={"limit": 2, "cursor": page["next_cursor"]})
    ).json()
    assert {i["id"] for i in nxt["items"]}.isdisjoint(i["id"] for i in page["items"])


async def test_duplicate_name_and_unknown_strategy_are_rejected(as_user: AsUser, sma: Dep) -> None:
    c = await as_user("operator")
    await _strategy(c, "dup")
    assert (await c.post("/api/v1/strategies", json={"name": "dup"})).status_code == 409
    assert (await _deposit(c, str(uuid4()), *sma)).status_code == 404
    assert (await c.get(f"/api/v1/strategies/{uuid4()}/versions/1")).status_code == 404


def test_registry_api_names_no_engine(app: FastAPI) -> None:
    doc = app.openapi()
    paths = {p: v for p, v in doc["paths"].items() if p.startswith("/api/v1/strategies")}
    assert paths
    text = json.dumps({"paths": paths, "components": doc["components"]}).lower()
    for name in ("freqtrade", "fake"):
        assert name not in text
