"""`WorkerRuntime` (SPEC F6, I12) : fichiers d'une instance et identifiants de l'API native du
moteur. Jetons propres à l'instance, renouvelés à chaque déploiement, jamais lisibles d'un autre
compte ni d'une autre instance."""

import json
import logging
import os
import stat
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from centrade_core.engine.contract import InstanceRuntime
from centrade_core.ids import uuid7
from centrade_core.models.trading import Engine, Instance, Secret
from centrade_worker.runtime import WorkerRuntime
from centrade_worker.secrets import CREDENTIALS_FILE
from centrade_worker.testing import T0
from cryptography.exceptions import InvalidTag
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

KEY = bytes(range(32))
NAMES = ("username", "password", "jwt_secret_key")
Sessions = async_sessionmaker[AsyncSession]


async def _instance(sessions: Sessions) -> UUID:
    engine_id, instance_id = uuid7(), uuid7()
    async with sessions.begin() as s:
        s.add(Engine(id=engine_id, kind="fake", image="img", version="1"))
        await s.flush()
        s.add(
            Instance(
                id=instance_id,
                engine_id=engine_id,
                name=f"i-{uuid4()}",
                mode="paper",
                desired_state="stopped",
            )
        )
    return instance_id


def _runtime(sessions: Sessions, tmp_path: Path, key: bytes = KEY) -> WorkerRuntime:
    return WorkerRuntime(sessions=sessions, master_key=key, runtime_dir=tmp_path, clock=lambda: T0)


async def _secret_ref(sessions: Sessions, instance_id: UUID) -> UUID | None:
    async with sessions() as s:
        return await s.scalar(select(Instance.engine_secret_ref).where(Instance.id == instance_id))


async def test_identifiants_crees_au_deploiement_relus_et_renouveles(
    session_factory: Sessions, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    rt: InstanceRuntime = _runtime(session_factory, tmp_path)  # conforme au Protocol du contrat
    iid = await _instance(session_factory)
    with pytest.raises(LookupError):
        await rt.credentials(iid)  # rien avant le premier déploiement

    first = await rt.issue_credentials(iid, NAMES)
    assert set(first) == set(NAMES)
    values = [v.get_secret_value() for v in first.values()]
    assert len(set(values)) == len(NAMES) and all(len(v) >= 32 for v in values)
    old_ref = await _secret_ref(session_factory, iid)
    assert old_ref is not None
    # Après un redémarrage du worker : mêmes valeurs, relues depuis le SecretStore.
    again = await _runtime(session_factory, tmp_path).credentials(iid)
    assert {k: v.get_secret_value() for k, v in again.items()} == dict(
        zip(NAMES, values, strict=True)
    )

    second = await rt.issue_credentials(iid, NAMES)  # nouveau déploiement
    assert not {v.get_secret_value() for v in second.values()} & set(values)
    new_ref = await _secret_ref(session_factory, iid)
    async with session_factory() as s:
        assert await s.get(Secret, old_ref) is None  # l'ancien chiffré est détruit
        row = await s.get_one(Secret, new_ref)
    assert row.usage == "engine_api" and row.last_used_at is None
    for value in values + [v.get_secret_value() for v in second.values()]:
        assert value.encode() not in row.ciphertext
        assert value not in caplog.text and value not in repr(second)


async def test_identifiants_lies_a_l_instance_et_a_la_cle_maitre(
    session_factory: Sessions, tmp_path: Path
) -> None:
    rt = _runtime(session_factory, tmp_path)
    mine, other = await _instance(session_factory), await _instance(session_factory)
    await rt.issue_credentials(mine, NAMES)
    ref = await _secret_ref(session_factory, mine)
    # Le secret d'une instance, rattaché de force à une autre, ne se déchiffre pas (AAD).
    async with session_factory.begin() as s:
        await s.execute(update(Instance).where(Instance.id == mine).values(engine_secret_ref=None))
        await s.execute(update(Instance).where(Instance.id == other).values(engine_secret_ref=ref))
    with pytest.raises(InvalidTag):
        await rt.credentials(other)
    async with session_factory.begin() as s:
        await s.execute(update(Instance).where(Instance.id == other).values(engine_secret_ref=None))
        await s.execute(update(Instance).where(Instance.id == mine).values(engine_secret_ref=ref))
    with pytest.raises(InvalidTag):  # autre clé maître
        await _runtime(session_factory, tmp_path, bytes(32)).credentials(mine)
    with pytest.raises(ValueError, match="32 octets"):
        _runtime(session_factory, tmp_path, b"courte")
    for names in ((), ("a", "a"), ("../x",), ("A",), ("",)):
        with pytest.raises(ValueError, match="invalides"):
            await rt.issue_credentials(mine, names)


async def test_fichiers_d_instance_ecrits_en_0400_puis_identifiants_retires(
    session_factory: Sessions, tmp_path: Path
) -> None:
    rt = _runtime(session_factory, tmp_path)
    iid = await _instance(session_factory)
    with pytest.raises(LookupError):  # pas d'identifiants : aucun fichier
        await rt.write_files(iid, {"config.json": "{}"}, {})
    creds = await rt.issue_credentials(iid, NAMES)
    content: dict[str, Any] = {"api_server": {k: v.get_secret_value() for k, v in creds.items()}}

    directory = await rt.write_files(
        iid, {"config.json": '{"a": 1}', "strategie.py": "# é\n"}, content
    )

    assert directory == tmp_path / str(iid)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert sorted(os.listdir(directory)) == ["config.json", CREDENTIALS_FILE, "strategie.py"]
    for name in os.listdir(directory):
        st = (directory / name).stat()
        assert stat.S_IMODE(st.st_mode) == 0o400 and st.st_uid == os.getuid()
    assert json.loads((directory / CREDENTIALS_FILE).read_text()) == content
    assert (directory / "strategie.py").read_text(encoding="utf-8") == "# é\n"
    # Le conteneur du moteur tourne sous le compte du worker : il lit ses fichiers sans privilège.
    assert rt.container_user() == f"{os.getuid()}:{os.getgid()}"

    await rt.write_files(iid, {"config.json": '{"a": 2}'}, content)  # redéploiement : remplacés
    assert (directory / "config.json").read_text() == '{"a": 2}'
    assert not [n for n in os.listdir(directory) if n.startswith(".")]  # aucun temporaire

    await rt.cleanup(iid)
    await rt.cleanup(iid)  # sans effet la seconde fois
    assert sorted(os.listdir(directory)) == ["config.json", "strategie.py"]


@pytest.mark.parametrize(
    "name",
    ["../evasion.py", "sous/dossier.py", "/etc/passwd", ".cache", "", CREDENTIALS_FILE, "a\x00b"],
)
async def test_nom_de_fichier_hors_du_dossier_de_l_instance_refuse(
    session_factory: Sessions, tmp_path: Path, name: str
) -> None:
    rt = _runtime(session_factory, tmp_path)
    iid = await _instance(session_factory)
    await rt.issue_credentials(iid, NAMES)
    with pytest.raises(ValueError, match="invalide"):
        await rt.write_files(iid, {name: "x"}, {"k": "v"})
    assert not (tmp_path / str(iid)).exists() and os.listdir(tmp_path) == []


def test_utilisateur_du_conteneur_explicite_et_jamais_dans_le_groupe_root(
    session_factory: Sessions, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rt = _runtime(session_factory, tmp_path)
    monkeypatch.setattr(os, "getuid", lambda: 10001)
    monkeypatch.setattr(os, "getgid", lambda: 0)  # image dont l'utilisateur n'a pas de groupe
    assert rt.container_user() == "10001:10001"
    monkeypatch.setattr(os, "getgid", lambda: 10002)
    assert rt.container_user() == "10001:10002"
