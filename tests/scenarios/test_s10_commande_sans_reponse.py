"""S10 (SPEC §14) : commande sans réponse -> `timed_out`, visible par l'API et dans le flux,
jamais `verified` ; l'instance s'affiche `unknown`."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from centrade_api.stream import stream_messages
from centrade_api.testing import Stack, act, create_instance, get, ref_of
from centrade_fake.engine import Failure
from fastapi.sse import ServerSentEvent
from sqlalchemy import select


async def _next(gen: AsyncGenerator[ServerSentEvent]) -> ServerSentEvent:
    return await asyncio.wait_for(gen.__anext__(), 5)


async def test_s10_commande_sans_reponse_timed_out_visible_jamais_verified(stack: Stack) -> None:
    from centrade_core.models import Session

    w = stack.world
    c = await stack.client("operator")
    assert stack.last_account is not None
    async with w.sessions() as s:
        sid = await s.scalar(select(Session.id).where(Session.user_id == stack.last_account.id))
    assert sid is not None
    gen = stream_messages(
        factory=w.sessions, redis=w.redis, session_id=sid, now=w.clock, cfg=stack.settings
    )
    assert (await _next(gen)).event == "heartbeat"  # abonné avant que rien ne se passe

    inst = await create_instance(c)
    iid = inst["id"]
    await w.worker.run_once()
    r = await act(c, iid, "resume-entries")
    await w.worker.run_once()  # running, commande vérifiée
    w.fake.set_failure(ref_of(iid), Failure.SILENT)  # le moteur se tait
    cid = (await act(c, iid, "pause-entries")).json()["command_id"]

    await w.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{cid}")
    assert cmd["status"] == "dispatched" and cmd["verified_at"] is None
    assert (await get(c, f"/api/v1/instances/{iid}"))["state"]["value"] == "unknown"

    w.clock.advance(stack.settings.deadline_pause_entries_s + 1)
    await w.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{cid}")
    assert cmd["status"] == "timed_out" and cmd["verified_at"] is None
    inst_now = await get(c, f"/api/v1/instances/{iid}")
    assert inst_now["state"]["value"] == "unknown" and inst_now["desired_state"] == "exits_only"
    assert r.status_code == 202

    seen: list[tuple[str, dict[str, Any]]] = []
    for _ in range(60):  # le flux a relayé les changements, dans l'ordre
        ev = await _next(gen)
        if ev.event != "heartbeat":
            seen.append((str(ev.event), dict(ev.data or {})))
        if any(k == "alert" and d["alert"]["rule"] == "command_timed_out" for k, d in seen):
            break
    statuses = [
        d["command"]["status"] for k, d in seen if k == "command" and d["command"]["id"] == cid
    ]
    assert statuses[-1] == "timed_out" and "verified" not in statuses
    assert any(k == "instance" and d["instance"]["state"]["value"] == "unknown" for k, d in seen)
    assert any(k == "alert" and d["alert"]["rule"] == "command_timed_out" for k, d in seen)
    await gen.aclose()
