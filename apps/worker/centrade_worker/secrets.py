"""Déchiffrement des secrets et fichier d'identifiants d'une instance (SPEC F6, I3, I12).

Seul endroit de la plateforme qui déchiffre une ligne de `secrets`. Réservé au worker : aucun
module de `apps/api/` ne l'importe (tests/invariants/test_i12_frontiere_dechiffrement.py).

Refus par défaut : un secret ne se déchiffre et ne s'écrit que pour une instance précise, relue
en base. Une clé de trading exige une instance live dont le compte porte cette clé ; une clé de
lecture ou de webhook ne va jamais à un moteur.
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
    """Le secret n'est pas destiné à cette instance. Le message ne porte aucune valeur."""


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
    """Lève `InvalidTag` si la clé, le nonce, le chiffré, la ligne, l'usage ou le propriétaire ne
    correspondent pas ; jamais de valeur partielle ni de repli."""
    aes = cipher(master_key)
    if key_version != KEY_VERSION:
        raise ValueError("version de clé maître inconnue")
    return SecretStr(aes.decrypt(nonce, ciphertext, secret_aad(secret_id, usage, owner)).decode())


def delivery_refusal(instance: Instance, account: Account | None, secret: Secret) -> str | None:
    """Motif de refus de remettre `secret` au moteur de `instance`, ou None. `account` est le
    compte de l'instance."""
    if secret.usage == "engine_api":
        return None  # lié à l'instance par l'AAD : celui d'une autre ne se déchiffre pas
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
    """Relit tout en base et applique le refus : l'appelant ne fournit que des identifiants."""
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
    """Valeur en clair d'un secret, pour le moteur de cette instance seulement. Note le dernier
    usage (l'appelant commit)."""
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
    """Écrit `<runtime_dir>/<instance_id>/credentials.json` (JSON de `content`), lisible par son
    seul propriétaire. `secret_ids` : tous les secrets dont `content` porte une valeur.

    `uid`/`gid` : l'utilisateur du conteneur, s'il n'est pas celui du worker.
    """
    await _load(session, instance_id, secret_ids)
    directory = runtime_dir / str(instance_id)
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink():
        raise SecretRefusedError("le dossier de l'instance est un lien")
    data = json.dumps(dict(content)).encode()
    tmp = directory / f".{CREDENTIALS_FILE}.{stdlib_secrets.token_hex(8)}"
    # Droits posés à la création, jamais après : le contenu n'est à aucun instant lisible
    # d'un autre compte. Puis renommage atomique : pas de fichier à moitié écrit.
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
    """À l'arrêt de l'instance. Sans effet si le fichier n'existe pas."""
    (runtime_dir / str(instance_id) / CREDENTIALS_FILE).unlink(missing_ok=True)
