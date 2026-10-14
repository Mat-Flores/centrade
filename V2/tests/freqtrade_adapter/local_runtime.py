"""Parts shared by the real trial and the capacity measurement: TEST strategy and local runtime."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import SecretStr

STRATEGY = '''\
from control_plane import ControlPlaneStrategy


class EnterEveryCandle(ControlPlaneStrategy):
    """TEST strategy: an entry signal on every candle. Never in strategies/."""

    timeframe = "1m"
    startup_candle_count = 2

    def populate_indicators(self, dataframe, metadata):
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe["enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe["exit_long"] = 0
        return dataframe
'''


class LocalRuntime:
    """InstanceRuntime without a database: real 0400 files owned by the test user."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def container_user(self) -> str:
        return f"{os.getuid()}:{os.getgid()}"

    async def issue_credentials(
        self, instance_id: UUID, names: tuple[str, ...]
    ) -> dict[str, SecretStr]:
        return {n: SecretStr(secrets.token_urlsafe(32)) for n in names}

    async def credentials(self, instance_id: UUID) -> dict[str, SecretStr]:
        raise LookupError

    async def write_files(self, instance_id: UUID, files: Any, credentials: Any) -> Path:
        d = self.root / str(instance_id)
        d.mkdir(mode=0o700, exist_ok=True)
        for name, text in {**files, "credentials.json": json.dumps(credentials)}.items():
            (d / name).unlink(missing_ok=True)
            fd = os.open(d / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
        return d

    async def cleanup(self, instance_id: UUID) -> None:
        (self.root / str(instance_id) / "credentials.json").unlink(missing_ok=True)
