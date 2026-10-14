"""I3: an instance's mode is fixed at creation (database trigger)."""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from centrade_core.ids import uuid7
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def test_i03_mode_is_immutable_after_creation(
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
    for mode in ("live", "paper"):  # even an identical value is a write to the mode
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


async def test_i03_paper_and_backtest_never_get_a_trading_key(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path, keyed_instance: Any
) -> None:
    """Even on a live account that holds a key: neither decrypted nor written for paper."""
    from centrade_worker import secrets as worker

    key, now = bytes(range(32)), datetime(2026, 1, 1, tzinfo=UTC)

    # A backtest is not an `instances` row (mode constraint): the property
    # below covers this mode and all the others.
    for mode in ("paper",):
        _, instance_id, trade, api = await keyed_instance(mode=mode)
        async with session_factory() as s:
            with pytest.raises(worker.SecretRefusedError, match="aucune clé de trading"):
                await worker.reveal(s, key, secret_id=trade, instance_id=instance_id, now=now)
            for ids in ([trade], [api, trade]):
                with pytest.raises(worker.SecretRefusedError, match="aucune clé de trading"):
                    await worker.write_instance_file(
                        s, tmp_path, instance_id=instance_id, secret_ids=ids, content={"k": "v"}
                    )
            # Only the engine's native API identifier is handed to it.
            api_value = await worker.reveal(s, key, secret_id=api, instance_id=instance_id, now=now)
            assert api_value.get_secret_value().startswith("TEST-SECRET-DO-NOT-USE-api")
            path = await worker.write_instance_file(
                s, tmp_path, instance_id=instance_id, secret_ids=[api], content={"k": "v"}
            )
        assert "TEST-SECRET" not in path.read_text()
        worker.remove_instance_file(tmp_path, instance_id)
    assert all(os.listdir(tmp_path / d) == [] for d in os.listdir(tmp_path))


@given(
    mode=st.sampled_from(("paper", "backtest", "live", "", "LIVE", "unknown")),
    account_type=st.sampled_from(("paper", "live")),
    same_account=st.booleans(),
    same_key=st.booleans(),
    has_account=st.booleans(),
)
def test_i03_trading_key_is_handed_only_if_everything_matches(
    mode: str, account_type: str, same_account: bool, same_key: bool, has_account: bool
) -> None:
    from centrade_core.models.trading import Account, Instance, Secret
    from centrade_worker.secrets import delivery_refusal

    account_id, secret_id = uuid7(), uuid7()
    secret = Secret(id=secret_id, usage="trade")
    instance = Instance(mode=mode, account_id=account_id if same_account else uuid7())
    account = Account(
        id=account_id, type=account_type, secret_ref=secret_id if same_key else uuid7()
    )
    refusal = delivery_refusal(instance, account if has_account else None, secret)
    allowed = (
        mode == "live" and account_type == "live" and same_account and same_key and has_account
    )
    assert (refusal is None) == allowed


async def _running(stack: Any) -> tuple[Any, str]:
    from centrade_api.testing import act, create_instance

    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    await stack.world.worker.run_once()
    assert (await act(c, iid, "resume-entries")).status_code == 202
    await stack.world.worker.run_once()
    return c, iid


async def test_i03_mode_mismatch_forbids_entries_and_raises_an_alert(stack: Any) -> None:
    from centrade_api.testing import act, get, ref_of
    from centrade_fake.engine import Failure
    from worker_support import alerts, commands, instance, spy

    c, iid = await _running(stack)
    w = stack.world
    assert (await w.fake.status(ref_of(iid))).state == "running"
    calls = spy(w.fake)

    w.fake.set_failure(ref_of(iid), Failure.LIE_MODE)  # the engine declares itself live
    await w.worker.run_once()

    (alert,) = await alerts(w, iid, "mode_mismatch")
    assert (alert.severity, alert.invariant, alert.status) == ("critical", "I3", "open")
    # The observed mode is recorded as is, never replaced by the wanted mode (I1).
    row = await instance(w, iid)
    assert (row.mode, row.observed_mode) == ("paper", "live")
    shown = await get(c, f"/api/v1/instances/{iid}")
    assert shown["mode_mismatch"] is True and shown["observed_mode"]["value"] == "live"
    # Entries open despite the mismatch: `pause_entries` was sent automatically, in the same cycle.
    (pause,) = await commands(w, iid, "pause_entries")
    assert pause.actor == "system:worker" and calls == ["pause_entries"]
    assert (await w.fake.status(ref_of(iid))).state == "exits_only"
    await w.worker.run_once()
    assert (await commands(w, iid, "pause_entries"))[0].status == "verified"

    # While the mismatch lasts, no resume: refused on request...
    r = await act(c, iid, "resume-entries")
    assert r.status_code == 409 and "mode" in r.json()["detail"]
    # ... and, if the lie starts after an accepted request, refused just before sending.
    w.fake.set_failure(ref_of(iid), Failure.LIE_MODE, on=False)
    await w.worker.run_once()
    assert (await alerts(w, iid, "mode_mismatch"))[0].status == "resolved"
    r = await act(c, iid, "resume-entries")
    assert r.status_code == 202
    w.fake.set_failure(ref_of(iid), Failure.LIE_MODE)
    await w.worker.run_once()
    cmd = await get(c, f"/api/v1/commands/{r.json()['command_id']}")
    assert cmd["status"] == "failed", cmd
    assert "mode" in {x["code"] for x in cmd["result"]["reasons"]}
    assert "resume_entries" not in calls
    assert (await w.fake.status(ref_of(iid))).state == "exits_only"
    assert [a.status for a in await alerts(w, iid, "mode_mismatch")] == ["resolved", "open"]


async def test_i03_mode_is_reread_at_every_start(stack: Any) -> None:
    """Stop then restart, and worker restart: each observed start re-reads the mode and
    the configuration, without waiting for the cadence."""
    from centrade_api.testing import act, ref_of
    from centrade_fake.engine import Failure
    from worker_support import alerts

    c, iid = await _running(stack)
    w = stack.world
    reads = 0
    real = w.fake.effective_config

    async def effective_config(ref: Any) -> Any:
        nonlocal reads
        reads += str(ref.instance_id) == iid  # the database is shared: this instance only
        return await real(ref)

    w.fake.effective_config = effective_config
    await w.worker.run_once()
    assert reads == 0  # already verified at this start, and the cadence is not due

    assert (await act(c, iid, "stop")).status_code == 202
    await w.worker.run_once()
    w.fake.set_failure(ref_of(iid), Failure.LIE_MODE)  # the engine changes during the stop
    await w.worker.run_once()
    assert (await act(c, iid, "start")).status_code == 202
    await w.worker.run_once()  # observed start: immediate verification
    assert reads == 1
    assert [a.severity for a in await alerts(w, iid, "mode_mismatch")] == ["critical"]

    w.worker = w.make_worker("apres")  # the worker restarts, the engine carries on
    await w.worker.load_instances()
    await w.worker.run_once()
    assert reads == 2
