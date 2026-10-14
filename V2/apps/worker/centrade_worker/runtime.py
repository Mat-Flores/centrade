"""Worker `InstanceRuntime` (SPEC F6, I12): an instance's files in the in-memory runtime
directory, native API credentials stored by the SecretStore (`engine_api`).

Instance -> secret link: `instances.engine_secret_ref`. The secret is a JSON object
{name: random token}, encrypted with the instance as owner: another instance's secret
does not decrypt. No venue key goes through here.
"""

from __future__ import annotations

import json
import os
import re
import secrets as stdlib_secrets
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from centrade_core.models.trading import Instance
from centrade_core.secrets import AesGcmSecretStore
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from centrade_worker.secrets import (
    CREDENTIALS_FILE,
    remove_instance_file,
    reveal,
    write_instance_file,
)

# Plain name only: a file name derives from the manifest, hence from user input.
_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,39}")


class WorkerRuntime:
    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        master_key: bytes,
        runtime_dir: Path,
        clock: Callable[[], datetime],
    ) -> None:
        self._sessions = sessions
        self._store = AesGcmSecretStore(master_key)  # validates the key length
        self._key = master_key
        self._dir = runtime_dir
        self._clock = clock

    def container_user(self) -> str:
        # Files are 0400 owned by the worker: the engine container runs under this same uid,
        # with no privilege or ownership change. The group is never used for reading: it is
        # always explicit and never 0 (root group), even if the worker has gid 0.
        return f"{os.getuid()}:{os.getgid() or os.getuid()}"

    async def issue_credentials(
        self, instance_id: UUID, names: tuple[str, ...]
    ) -> dict[str, SecretStr]:
        if not names or len(set(names)) != len(names) or not all(map(_NAME.fullmatch, names)):
            raise ValueError("noms d'identifiants invalides")
        values = {n: stdlib_secrets.token_urlsafe(32) for n in names}
        async with self._sessions.begin() as s:
            inst = await s.get_one(Instance, instance_id, with_for_update=True)
            old = inst.engine_secret_ref
            inst.engine_secret_ref = await self._store.put(
                s,
                usage="engine_api",
                kind="engine_api",
                owner=instance_id,
                value=SecretStr(json.dumps(values)),
                now=self._clock(),
            )
            if old is not None:  # renewed on every deployment: the old ciphertext is destroyed
                await s.flush()
                await self._store.revoke(s, old)
        return {k: SecretStr(v) for k, v in values.items()}

    async def _ref(self, s: AsyncSession, instance_id: UUID) -> UUID:
        ref = await s.scalar(select(Instance.engine_secret_ref).where(Instance.id == instance_id))
        if ref is None:
            raise LookupError("aucun identifiant de moteur pour cette instance")
        return ref

    async def credentials(self, instance_id: UUID) -> dict[str, SecretStr]:
        async with self._sessions.begin() as s:
            value = await reveal(
                s,
                self._key,
                secret_id=await self._ref(s, instance_id),
                instance_id=instance_id,
                now=self._clock(),
            )
        return {k: SecretStr(v) for k, v in json.loads(value.get_secret_value()).items()}

    async def write_files(
        self, instance_id: UUID, files: Mapping[str, str], credentials: Mapping[str, Any]
    ) -> Path:
        if any(not _FILE.fullmatch(n) or n == CREDENTIALS_FILE for n in files):
            raise ValueError("nom de fichier d'instance invalide")
        async with self._sessions() as s:
            path = await write_instance_file(
                s,
                self._dir,
                instance_id=instance_id,
                secret_ids=[await self._ref(s, instance_id)],
                content=credentials,
            )
        directory = path.parent
        for name, text in files.items():
            tmp = directory / f".{name}.{stdlib_secrets.token_hex(8)}"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(text)
                os.replace(tmp, directory / name)
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
        return directory

    async def cleanup(self, instance_id: UUID) -> None:
        remove_instance_file(self._dir, instance_id)
