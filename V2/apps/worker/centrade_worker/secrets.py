"""Decryption of secrets and an instance's credentials file (SPEC F6, I3, I12).

The only place in the platform that decrypts a `secrets` row. Reserved to the worker: no
`apps/api/` module imports it (tests/invariants/test_i12_frontiere_dechiffrement.py).

Refuse by default: a secret is decrypted and written only for a specific instance, re-read
from the database. A trading key requires a live instance whose account holds that key; a
read or webhook key never goes to an engine.
"""

import json
import os
import secrets as stdlib_secrets
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from centrade_core.models.trading import Account, Instance, Secret
from centrade_core.secrets import KEY_VERSION, Usage, cipher, secret_aad
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

CREDENTIALS_FILE = "credentials.json"


class SecretRefusedError(Exception):
    """The secret is not intended for this instance. The message carries no value."""


def open_secret(
    master_key: bytes,
    *,
    secret_id: UUID,
    usage: Usage,
    owner: UUID,
    key_version: int,
    nonce: bytes,
    ciphertext: bytes,
) -> SecretStr:
    """Raises `InvalidTag` if the key, nonce, ciphertext, row, usage or owner do not
    match; never a partial value or a fallback."""
    aes = cipher(master_key)
    if key_version != KEY_VERSION:
        raise ValueError("version de clé maître inconnue")
    return SecretStr(aes.decrypt(nonce, ciphertext, secret_aad(secret_id, usage, owner)).decode())


def delivery_refusal(instance: Instance, account: Account | None, secret: Secret) -> str | None:
    """Reason for refusing to hand `secret` to `instance`'s engine, or None. `account` is the
    instance's account."""
    if secret.usage == "engine_api":
        return None  # bound to the instance by the AAD: another instance's secret does not decrypt
    if secret.usage != "trade":
        return "ce secret n'est jamais remis à un moteur"
    if instance.mode != "live":
        return "une instance qui n'est pas live ne reçoit aucune clé de trading"
    if (
        account is None
        or account.id != instance.account_id
        or account.type != "live"
        or account.secret_ref != secret.id
    ):
        return "cette clé n'est pas celle du compte de l'instance"
    return None


async def _load(
    session: AsyncSession, instance_id: UUID, secret_ids: Sequence[UUID]
) -> tuple[Instance, Account | None, list[Secret]]:
    """Re-reads everything from the database and applies the refusal: the caller passes only IDs."""
    instance = await session.get(Instance, instance_id)
    if instance is None:
        raise SecretRefusedError("instance inconnue")
    account = (
        None if instance.account_id is None else await session.get(Account, instance.account_id)
    )
    found = []
    for secret_id in secret_ids:
        secret = await session.get(Secret, secret_id)
        if secret is None:
            raise SecretRefusedError("secret inconnu")
        if (reason := delivery_refusal(instance, account, secret)) is not None:
            raise SecretRefusedError(reason)
        found.append(secret)
    return instance, account, found


async def reveal(
    session: AsyncSession, master_key: bytes, *, secret_id: UUID, instance_id: UUID, now: datetime
) -> SecretStr:
    """Plaintext value of a secret, for this instance's engine only. Records the last
    use (the caller commits)."""
    instance, account, (secret,) = await _load(session, instance_id, [secret_id])
    owner = instance.id if secret.usage == "engine_api" or account is None else account.id
    value = open_secret(
        master_key,
        secret_id=secret.id,
        usage=secret.usage,  # type: ignore[arg-type]
        owner=owner,
        key_version=secret.key_version,
        nonce=secret.nonce,
        ciphertext=secret.ciphertext,
    )
    secret.last_used_at = now
    return value


async def write_instance_file(
    session: AsyncSession,
    runtime_dir: Path,
    *,
    instance_id: UUID,
    secret_ids: Sequence[UUID],
    content: Mapping[str, Any],
    uid: int | None = None,
    gid: int | None = None,
) -> Path:
    """Writes `<runtime_dir>/<instance_id>/credentials.json` (JSON of `content`), readable only
    by its owner. `secret_ids`: all the secrets whose value `content` carries.

    `uid`/`gid`: the container user, if it is not the worker's.
    """
    await _load(session, instance_id, secret_ids)
    directory = runtime_dir / str(instance_id)
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink():
        raise SecretRefusedError("le dossier de l'instance est un lien")
    data = json.dumps(dict(content)).encode()
    tmp = directory / f".{CREDENTIALS_FILE}.{stdlib_secrets.token_hex(8)}"
    # Permissions are set at creation, never after: the content is never readable by
    # another account. Then atomic rename: no half-written file.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    try:
        with os.fdopen(fd, "wb") as f:
            if uid is not None or gid is not None:
                os.fchown(f.fileno(), -1 if uid is None else uid, -1 if gid is None else gid)
            f.write(data)
        os.replace(tmp, directory / CREDENTIALS_FILE)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return directory / CREDENTIALS_FILE


def remove_instance_file(runtime_dir: Path, instance_id: UUID) -> None:
    """On instance stop. No effect if the file does not exist."""
    (runtime_dir / str(instance_id) / CREDENTIALS_FILE).unlink(missing_ok=True)
