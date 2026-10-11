"""I14 : le journal d'audit est inaltérable et sa chaîne est vérifiable (SPEC §6, §1.2)."""

import asyncio

import pytest
from centrade_core.audit import fingerprint, verify_chain, write_audit
from sqlalchemy import text
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


async def test_i14_journal_d_audit_inalterable(
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
        victim = (
            await s.execute(text("SELECT seq FROM audit_log ORDER BY seq OFFSET 1 LIMIT 1"))
        ).scalar_one()
        await s.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_change"))
        await s.execute(text("UPDATE audit_log SET actor = 'pirate' WHERE seq = :s"), {"s": victim})
        await s.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_change"))
    async with session_factory() as s:
        assert await verify_chain(s) == victim

    # Remise en état pour les autres tests.
    async with session_factory() as s, s.begin():
        await s.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_change"))
        await s.execute(text("UPDATE audit_log SET actor = 'user:1' WHERE seq = :s"), {"s": victim})
        await s.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_change"))
    async with session_factory() as s:
        assert await verify_chain(s) is None


async def test_i14_ecritures_concurrentes_sans_fourche(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await asyncio.gather(*(_write(session_factory, n) for n in range(12)))
    async with session_factory() as s:
        assert await verify_chain(s) is None


def test_i14_empreinte_deterministe_et_sans_valeur() -> None:
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    assert "secret-sentinelle" not in fingerprint({"k": "secret-sentinelle"})
