"""I14 : le journal d'audit est inaltérable et sa chaîne est vérifiable (SPEC §6, §1.2)."""

import asyncio

import pytest
from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_core.audit import fingerprint, verify_chain, write_audit
from centrade_core.models import AuditLog
from centrade_fake.engine import Failure
from fastapi.routing import iter_route_contexts
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def _write(factory: async_sessionmaker[AsyncSession], n: int) -> None:
    async with factory() as s, s.begin():
        await write_audit(
            s,
            actor=f"user:{n}",
            action="instance.start",
            target="instance:1",
            before={"state": "stopped"},
            after={"state": "running"},
            ip="203.0.113.7",
        )


async def test_i14_audit_log_is_tamper_proof(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    for n in range(3):
        await _write(session_factory, n)
    async with session_factory() as s:
        assert await verify_chain(s) is None

    # UPDATE, DELETE et TRUNCATE sont refusés par le trigger.
    for sql in (
        "UPDATE audit_log SET actor = 'pirate'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
    ):
        async with session_factory() as s:
            with pytest.raises(DBAPIError, match="ajout seul"):
                await s.execute(text(sql))

    # Une ligne altérée hors trigger (accès direct aux fichiers, trigger désactivé) casse la chaîne.
    async with session_factory() as s, s.begin():
        victim, original = (
            await s.execute(text("SELECT seq, actor FROM audit_log ORDER BY seq OFFSET 1 LIMIT 1"))
        ).one()
        await s.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_change"))
        await s.execute(text("UPDATE audit_log SET actor = 'pirate' WHERE seq = :s"), {"s": victim})
        await s.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_change"))
    async with session_factory() as s:
        assert await verify_chain(s) == victim

    # Remise en état pour les autres tests.
    async with session_factory() as s, s.begin():
        await s.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_change"))
        await s.execute(
            text("UPDATE audit_log SET actor = :a WHERE seq = :s"), {"s": victim, "a": original}
        )
        await s.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_change"))
    async with session_factory() as s:
        assert await verify_chain(s) is None


async def test_i14_concurrent_writes_do_not_fork_the_chain(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await asyncio.gather(*(_write(session_factory, n) for n in range(12)))
    async with session_factory() as s:
        assert await verify_chain(s) is None


def test_i14_fingerprint_is_deterministic_and_carries_no_value() -> None:
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    assert "secret-sentinelle" not in fingerprint({"k": "secret-sentinelle"})


async def _audit_for(stack: Stack, *targets: str) -> list[AuditLog]:
    async with stack.world.sessions() as s:
        rows = await s.scalars(select(AuditLog).where(AuditLog.target.in_(targets)))
        return list(rows)


async def test_i14_every_action_writes_an_audit_row_with_its_author(stack: Stack) -> None:
    changing = {
        (m, p)
        for ctx in iter_route_contexts(stack.app.routes)
        for m in (ctx.methods or set()) - {"GET", "HEAD", "OPTIONS"}
        if (p := ctx.path)
    }
    actions = ("start", "stop", "pause-entries", "resume-entries", "flatten")
    # Une route qui change un état et qui n'est pas parcourue ici fait échouer ce test.
    registre = {
        ("POST", "/api/v1/strategies"),
        ("POST", "/api/v1/strategies/{strategy_id}/versions"),
        ("PATCH", "/api/v1/strategies/{strategy_id}/versions/{version}"),
    }
    # Comptes et clés : auditées dans tests/scenarios/test_comptes_et_cles.py.
    comptes = {
        ("POST", "/api/v1/accounts"),
        ("PUT", "/api/v1/accounts/{account_id}/secret"),
        ("POST", "/api/v1/accounts/{account_id}/test"),
        ("POST", "/api/v1/accounts/{account_id}/rotate"),
    }
    # Fermeture et annulation d'entrée : auditées dans tests/scenarios/test_instances_trading.py.
    trading = {
        ("POST", "/api/v1/positions/{position_id}/close"),
        ("DELETE", "/api/v1/orders/{order_id}"),
    }
    # Authentification : auditée dans apps/api/tests/auth/ (test_logs_audit, test_totp_confirm).
    auth = {("POST", f"/api/v1/auth/{p}") for p in ("login", "totp", "totp/confirm", "logout")}
    assert changing >= registre | comptes | trading | auth
    assert changing - registre - comptes - trading - auth == {("POST", "/api/v1/instances")} | {
        ("POST", f"/api/v1/instances/{{instance_id}}/{a}") for a in actions
    }

    c = await stack.client("operator")
    me = (await c.get("/api/v1/auth/me")).json()
    created = await create_instance(c)
    target = f"instance:{created['id']}"
    assert {r.action for r in await _audit_for(stack, target)} >= {
        "instance.create",
        "command.deploy",
    }
    await stack.world.worker.run_once()
    # `resume-entries` n'est refusé que sur état douteux ; ici l'état observé est frais.
    # `start` n'a de sens que sur une instance arrêtée : il passe après l'effet de `stop`.
    for a in ("pause-entries", "resume-entries", "flatten", "stop", "start"):
        if a == "start":
            for _ in range(2):  # pause et flatten d'abord, puis stop
                await stack.world.worker.run_once()
        before = len(await _audit_for(stack, target))
        r = await act(c, created["id"], a)
        assert r.status_code == 202, (a, r.text)
        rows = await _audit_for(stack, target)
        assert len(rows) == before + 1
        assert any(x.action == f"command.{a.replace('-', '_')}" for x in rows)
    rows = await _audit_for(stack, target)
    humans = [r for r in rows if r.action.startswith(("instance.", "command."))]
    assert humans and all(r.actor == f"user:{me['id']}" for r in humans), me


async def test_i14_automation_action_is_attributed_to_its_author(stack: Stack) -> None:
    c = await stack.client("operator")
    created = await create_instance(c)
    iid = created["id"]
    w = stack.world
    await w.worker.run_once()
    r = await act(c, iid, "resume-entries")
    cid = r.json()["command_id"]
    await w.worker.run_once()  # verified par le worker

    w.fake.set_failure(ref_of(iid), Failure.SILENT)
    await w.worker.run_once()  # passage à unknown + alerte
    r2 = await act(c, iid, "flatten")
    cid2 = r2.json()["command_id"]
    await w.worker.run_once()  # envoyée, sans réponse : l'échéance court depuis l'envoi
    w.clock.advance(stack.settings.deadline_flatten_s + 1)
    await w.worker.run_once()  # timed_out
    w.fake.set_failure(ref_of(iid), Failure.SILENT, on=False)
    w.clock.advance(1)
    await w.worker.run_once()  # alerte résolue

    alerts = (await get(c, f"/api/v1/alerts?instance_id={iid}"))["items"]
    targets = [f"instance:{iid}", f"command:{cid}", f"command:{cid2}"]
    targets += [f"alert:{a['id']}" for a in alerts]
    by_action = {
        r.action: r for r in await _audit_for(stack, *targets) if r.actor == "system:worker"
    }
    assert {
        "command.verified",
        "instance.observed_unknown",
        "alert.raised",
        "command.timed_out",
        "alert.resolved",
    } <= set(by_action)
    assert all(r.actor == "system:worker" for r in by_action.values())
    async with w.sessions() as s:
        assert await verify_chain(s) is None
