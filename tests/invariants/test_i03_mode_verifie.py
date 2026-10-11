"""I3 : le mode d'une instance est fixé à la création (trigger en base)."""

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


async def test_i03_paper_et_backtest_sans_cle_de_trading(
    session_factory: async_sessionmaker[AsyncSession], tmp_path: Path, keyed_instance: Any
) -> None:
    """Même sur un compte live qui porte une clé : ni déchiffrée, ni écrite pour du paper."""
    from centrade_worker import secrets as worker

    key, now = bytes(range(32)), datetime(2026, 1, 1, tzinfo=UTC)

    # Un backtest n'est pas une ligne d'`instances` (contrainte de mode) : la propriété
    # ci-dessous couvre ce mode et tous les autres.
    for mode in ("paper",):
        _, instance_id, trade, api = await keyed_instance(mode=mode)
        async with session_factory() as s:
            with pytest.raises(worker.SecretRefusedError, match="I3"):
                await worker.reveal(s, key, secret_id=trade, instance_id=instance_id, now=now)
            for ids in ([trade], [api, trade]):
                with pytest.raises(worker.SecretRefusedError, match="I3"):
                    await worker.write_instance_file(
                        s, tmp_path, instance_id=instance_id, secret_ids=ids, content={"k": "v"}
                    )
            # Seul l'identifiant de l'API native du moteur lui est remis.
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
def test_i03_cle_de_trading_remise_seulement_si_tout_concorde(
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
