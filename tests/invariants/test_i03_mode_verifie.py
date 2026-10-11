"""I3 : le mode d'une instance est fixé à la création (trigger en base)."""

from uuid import uuid4

import pytest
from centrade_core.ids import uuid7
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def test_i03_mode_immuable_apres_creation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    eid, iid = uuid7(), uuid7()
    async with session_factory() as s, s.begin():
        await s.execute(
            text("INSERT INTO engines (id, kind, image, version) VALUES (:i, 'fake', 'img', '1')"),
            {"i": eid},
        )
        await s.execute(
            text(
                "INSERT INTO instances (id, engine_id, name, mode, desired_state) "
                "VALUES (:i, :e, :n, 'paper', 'stopped')"
            ),
            {"i": iid, "e": eid, "n": f"i-{uuid4()}"},
        )
    for mode in ("live", "paper"):  # même la valeur identique est une écriture sur le mode
        async with session_factory() as s:
            if mode == "paper":
                await s.execute(
                    text("UPDATE instances SET mode = 'paper' WHERE id = :i"), {"i": iid}
                )
                continue
            with pytest.raises(DBAPIError, match="immuable"):
                await s.execute(
                    text("UPDATE instances SET mode = 'live' WHERE id = :i"), {"i": iid}
                )
