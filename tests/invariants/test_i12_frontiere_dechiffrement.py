"""I12 : une clé saisie n'est jamais relue, affichée ni journalisée, et n'est remise qu'au moteur
de l'instance live à laquelle elle est affectée. Valeurs sentinelles uniquement."""

import ast
import io
import json
import logging
import os
import stat
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import structlog
from centrade_api.accounts import KeyPermissions, get_permission_probe
from centrade_api.testing import Stack
from centrade_core.audit import fingerprint
from centrade_core.ids import uuid7
from centrade_core.logging import configure_logging
from centrade_core.models import AuditLog
from centrade_core.models.trading import Account, Instance, Secret
from centrade_core.secrets import AesGcmSecretStore
from centrade_worker import secrets as worker
from cryptography.exceptions import InvalidTag
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

API = Path(__file__).resolve().parents[2] / "apps" / "api" / "centrade_api"
# Seuls noms de `centrade_core.secrets` que l'API peut importer : aucun ne déchiffre une ligne
# de `secrets` (le TOTP a son propre AAD, qui n'en ouvre aucune).
ALLOWED = {"SecretStore", "AesGcmSecretStore", "encrypt_totp_secret", "decrypt_totp_secret"}
FORBIDDEN = {"open_secret", "reveal", "secret_aad", "cipher", "AESGCM"}
SENTINEL = "TEST-SECRET-DO-NOT-USE-{}-0xC0FFEE"
A = "/api/v1/accounts"
KEY = bytes(range(32))
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _violations(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names: list[tuple[str, str | None]] = [(a.name, None) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "", a.name) for a in node.names]
        else:
            # Par un autre chemin que l'import (attribut d'un module déjà chargé, importlib).
            ident = getattr(node, "attr", None) or getattr(node, "id", None)
            text = node.value if isinstance(node, ast.Constant) else None
            text = text if isinstance(text, str) else ""
            if ident in FORBIDDEN or "centrade_worker.secrets" in text:
                found.append(f"accès au déchiffrement : {ident or text}")
            continue
        for module, name in names:
            full = f"{module}.{name}" if name else module
            if full.startswith("centrade_worker.secrets") or module == "centrade_worker.secrets":
                found.append(f"déchiffrement du worker : {full}")
            elif "cryptography.hazmat.primitives.ciphers" in full:
                found.append(f"primitive de chiffrement : {full}")
            elif full == "centrade_core.secrets" or (
                module == "centrade_core.secrets" and name not in ALLOWED
            ):
                found.append(f"nom non admis de centrade_core.secrets : {full}")
    return found


def test_i12_aucun_module_de_l_api_n_importe_le_dechiffrement() -> None:
    modules = sorted(API.rglob("*.py"))
    assert len(modules) > 10
    for path in modules:
        assert _violations(path.read_text(encoding="utf-8")) == [], path
    # Le contrôle mord : chacune de ces lignes, dans l'API, ferait échouer le test.
    for bad in (
        "from centrade_worker.secrets import reveal",
        "from centrade_worker import secrets",
        "import centrade_worker.secrets as s",
        "from centrade_core.secrets import cipher",
        "from centrade_core.secrets import secret_aad",
        "from centrade_core import secrets",
        "import centrade_core.secrets",
        "from cryptography.hazmat.primitives.ciphers.aead import AESGCM",
        "import cryptography.hazmat.primitives.ciphers.aead",
        "import centrade_core\ncentrade_core.secrets.cipher(k)",
        "import importlib\nimportlib.import_module('centrade_worker.secrets')",
        "import sys\nsys.modules['centrade_core.secrets'].secret_aad",
    ):
        assert _violations(bad), bad


def test_i12_l_api_demarree_ne_charge_pas_le_dechiffrement() -> None:
    """Y compris par un import indirect : le module du worker n'est pas chargé par l'API."""
    code = (
        "import sys, centrade_api.main\n"
        "assert 'centrade_api.accounts' in sys.modules\n"
        "print('centrade_worker.secrets' in sys.modules)"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    out = subprocess.run(  # noqa: S603  # interpréteur courant, code constant
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    )
    assert out.stdout.strip().splitlines()[-1] == "False"


@pytest.fixture
def logs() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    configure_logging(stream=buf)
    yield buf
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


class _Probe:
    def __init__(self, outcome: KeyPermissions | Exception) -> None:
        self.outcome = outcome

    async def permissions(self, secret_id: UUID) -> KeyPermissions:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


async def test_i12_la_valeur_saisie_ne_ressort_nulle_part(
    stack: Stack, logs: io.StringIO, caplog: pytest.LogCaptureFixture
) -> None:
    s = [SENTINEL.format(i) for i in range(12)]
    admin = await stack.client("admin")
    viewer = await stack.client("viewer")
    body = {
        "venue": "venue-test",
        "type": "live",
        "environment": "sandbox",
        "label": "Compte",
        "currency": "USDT",
    }
    aid = (await admin.post(A, json=body)).json()["id"]
    put = {"usage": "trade", "key": s[0], "secret": s[1]}
    responses = [
        await admin.put(f"{A}/{aid}/secret", json=put),
        await admin.put(f"{A}/{aid}/secret", json={"usage": "read", "key": s[2], "secret": s[3]}),
        await admin.get(A),
        await viewer.get(A),
        await admin.post(f"{A}/{aid}/test"),
        await admin.post(f"{A}/{aid}/rotate", json={**put, "key": s[4], "secret": s[5]}),  # 409
        # Refus de validation : Pydantic recopierait la valeur reçue dans son message.
        await admin.put(f"{A}/{aid}/secret", json={"usage": s[6], "key": s[6], "secret": s[6]}),
        await admin.put(f"{A}/{aid}/secret", json={**put, "key": s[6] * 100}),
        await admin.put(f"{A}/{aid}/secret", json={**put, "key": {"v": s[6]}, "secret": [s[6]]}),
        await admin.put(f"{A}/{aid}/secret", json={**put, "inconnu": s[6]}),
        await admin.put(
            f"{A}/{aid}/secret",
            content=f'{{"usage": "trade", "key": "{s[6]}", "secret": '.encode(),
            headers={"Content-Type": "application/json"},
        ),
        await admin.post(f"{A}/{aid}/rotate", json={"usage": "trade", "key": s[6]}),
        await admin.post(A, json={**body, "label": s[6] * 100, "capital_cap": s[6]}),
        await admin.put(f"{A}/{uuid4()}/secret", json={**put, "key": s[6]}),  # 404
        await viewer.put(f"{A}/{aid}/secret", json={**put, "key": s[6]}),  # 403
        await admin.get(A, params={"cursor": "invalide"}),
    ]
    # Sonde qui échoue avec la valeur dans son message, puis rotation réussie.
    stack.app.dependency_overrides[get_permission_probe] = lambda: _Probe(RuntimeError(s[7]))
    responses.append(await admin.post(f"{A}/{aid}/test"))
    responses.append(
        await admin.post(f"{A}/{aid}/rotate", json={**put, "key": s[8], "secret": s[9]})
    )
    ok = KeyPermissions(trading=True, withdrawal=False, ip_restricted=True)
    stack.app.dependency_overrides[get_permission_probe] = lambda: _Probe(ok)
    rotated = await admin.post(f"{A}/{aid}/rotate", json={**put, "key": s[10], "secret": s[11]})
    responses += [rotated, await admin.get(A)]

    statuses = [r.status_code for r in responses]
    assert statuses[:6] == [200, 200, 200, 200, 200, 409] and rotated.status_code == 200
    assert statuses[6:16] == [422, 422, 422, 422, 422, 422, 422, 404, 403, 422]
    for r in responses:
        assert "TEST-SECRET" not in r.text and "TEST-SECRET" not in str(r.headers), r.request.url
    assert "TEST-SECRET" not in logs.getvalue() and "TEST-SECRET" not in caplog.text
    assert "account_secret_stored" in logs.getvalue()  # les logs ont bien été capturés

    async with stack.world.sessions() as db:
        account = await db.get_one(Account, UUID(aid))
        rows = (
            await db.scalars(
                select(AuditLog).where(AuditLog.target == f"account:{aid}").order_by(AuditLog.seq)
            )
        ).all()
        secrets = (await db.scalars(select(Secret))).all()
    # Audit : l'empreinte « après » est celle de champs sans valeur de secret.
    last = rows[-1]
    assert last.action == "account.secret.rotate"
    assert last.after_hash == fingerprint(
        {"usage": "trade", "key_version": 1, "secret_id": str(account.secret_ref)}
    )
    assert "TEST-SECRET" not in repr([vars(r) for r in rows])
    # En base : chiffré seulement, et rien de lisible dans `repr`.
    for secret in secrets:
        assert b"TEST-SECRET" not in secret.ciphertext and "TEST-SECRET" not in repr(vars(secret))
    assert "TEST-SECRET" not in repr(vars(account))


async def test_i12_cle_remise_au_seul_moteur_de_l_instance_live_du_compte(
    keyed_instance: Any, session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    _, live, trade, api = await keyed_instance(mode="live")
    _, other_live, other_trade, other_api = await keyed_instance(mode="live")
    async with session_factory() as s:
        value = await worker.reveal(s, KEY, secret_id=trade, instance_id=live, now=NOW)
        assert value.get_secret_value() == SENTINEL.format("trade")
        assert "TEST-SECRET" not in repr(value) + str(value)
        assert (await s.get_one(Secret, trade)).last_used_at == NOW  # suivi du dernier usage
        # La clé d'un autre compte, même pour une instance live : refus, rien d'écrit.
        for secret_id, instance_id in ((other_trade, live), (trade, other_live)):
            with pytest.raises(worker.SecretRefusedError, match="I12"):
                await worker.reveal(s, KEY, secret_id=secret_id, instance_id=instance_id, now=NOW)
            with pytest.raises(worker.SecretRefusedError, match="I12"):
                await worker.write_instance_file(
                    s, tmp_path, instance_id=instance_id, secret_ids=[secret_id], content={}
                )
        # L'identifiant de moteur d'une autre instance ne se déchiffre pas (AAD).
        with pytest.raises(InvalidTag):
            await worker.reveal(s, KEY, secret_id=other_api, instance_id=live, now=NOW)
        for missing in (
            {"secret_id": uuid7(), "instance_id": live},
            {"secret_id": api, "instance_id": uuid7()},
        ):
            with pytest.raises(worker.SecretRefusedError):
                await worker.reveal(s, KEY, now=NOW, **missing)
        # Une référence détournée en base (clé d'un autre compte) ne se déchiffre pas non plus.
        account = await s.get_one(Account, (await s.get_one(Instance, live)).account_id)
        account.secret_ref = other_trade
        await s.flush()
        with pytest.raises(InvalidTag):
            await worker.reveal(s, KEY, secret_id=other_trade, instance_id=live, now=NOW)
        await s.rollback()
    assert os.listdir(tmp_path) == []


async def test_i12_cle_de_lecture_jamais_remise_a_un_moteur(
    keyed_instance: Any, session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    account_id, live, _, _ = await keyed_instance(mode="live")
    store = AesGcmSecretStore(KEY)
    async with session_factory() as s:
        for usage in ("read", "webhook"):
            ref = await store.put(
                s,
                usage=usage,
                kind="k",
                owner=account_id,
                value=SecretStr("x"),
                now=NOW,
            )
            with pytest.raises(worker.SecretRefusedError, match="jamais remis"):
                await worker.reveal(s, KEY, secret_id=ref, instance_id=live, now=NOW)
            with pytest.raises(worker.SecretRefusedError, match="jamais remis"):
                await worker.write_instance_file(
                    s, tmp_path, instance_id=live, secret_ids=[ref], content={}
                )
        await s.rollback()


async def test_i12_fichier_d_instance_droits_restreints_atomique_puis_supprime(
    keyed_instance: Any,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, instance_id, _, api = await keyed_instance(mode="paper")
    content = {"api_server": {"username": "centrade", "password": SENTINEL.format("api")}}
    opened: list[tuple[int, int]] = []
    real_open = os.open

    def spy(path: str, flags: int, mode: int = 0o777, **kw: object) -> int:
        opened.append((flags, mode))
        return real_open(path, flags, mode, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", spy)
    old_umask = os.umask(0)  # même sans umask protecteur
    try:
        async with session_factory() as s:
            path = await worker.write_instance_file(
                s, tmp_path, instance_id=instance_id, secret_ids=[api], content=content
            )
            # Réécriture (redéploiement) : remplace sans erreur.
            await worker.write_instance_file(
                s,
                tmp_path,
                instance_id=instance_id,
                secret_ids=[api],
                content=content,
                uid=os.getuid(),
                gid=os.getgid(),
            )
    finally:
        os.umask(old_umask)
    monkeypatch.undo()
    assert path == tmp_path / str(instance_id) / worker.CREDENTIALS_FILE
    assert json.loads(path.read_text()) == content
    assert stat.S_IMODE(path.stat().st_mode) == 0o400
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    # Droits posés à l'ouverture, création exclusive, sans suivre de lien.
    flags, mode = opened[0]
    assert mode == 0o400 and flags & os.O_EXCL and flags & os.O_CREAT and flags & os.O_NOFOLLOW
    assert [p.name for p in path.parent.iterdir()] == [worker.CREDENTIALS_FILE]  # aucun reste

    worker.remove_instance_file(tmp_path, instance_id)
    assert not path.exists()
    worker.remove_instance_file(tmp_path, instance_id)  # déjà supprimé : sans effet

    # Dossier d'instance détourné par un lien : refus, rien n'est écrit ailleurs.
    _, other, _, other_api = await keyed_instance(mode="paper")
    target = tmp_path / "ailleurs"
    target.mkdir()
    (tmp_path / str(other)).symlink_to(target, target_is_directory=True)
    async with session_factory() as s:
        with pytest.raises(worker.SecretRefusedError, match="lien"):
            await worker.write_instance_file(
                s, tmp_path, instance_id=other, secret_ids=[other_api], content=content
            )
    assert list(target.iterdir()) == []


async def test_i12_echec_d_ecriture_ne_laisse_aucun_fichier(
    keyed_instance: Any,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, instance_id, _, api = await keyed_instance(mode="paper")

    def boom(*_: object) -> None:
        raise OSError("disque plein")

    monkeypatch.setattr(os, "replace", boom)
    async with session_factory() as s:
        with pytest.raises(OSError, match="disque plein"):
            await worker.write_instance_file(
                s, tmp_path, instance_id=instance_id, secret_ids=[api], content={"k": "v"}
            )
        with pytest.raises(TypeError):  # contenu non sérialisable : refusé avant toute écriture
            await worker.write_instance_file(
                s,
                tmp_path,
                instance_id=instance_id,
                secret_ids=[api],
                content={"k": SecretStr("v")},
            )
    assert list((tmp_path / str(instance_id)).iterdir()) == []
