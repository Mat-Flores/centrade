"""Configuration. No secret has a default value: a missing file stops startup."""

import base64
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CENTRADE_", frozen=True)

    db_host: str = "postgres"
    db_port: int = 5432
    db_user: str = "centrade"
    db_name: str = "centrade"
    redis_url: str = Field(repr=False, description="redis://hôte:port/db, sans mot de passe")
    worker_interval_s: float = 1.0
    engine_silent_after_s: float = 30.0  # engine silent beyond this: observed state `unknown`
    worker_heartbeat_ttl_s: int = 15
    # Freshness of an engine value (SPEC §13): beyond it, the API marks it `stale`.
    observed_stale_after_s: float = 30.0
    stream_heartbeat_s: float = 2.0  # SSE stream heartbeat; the front end waits 5 s at most
    stream_session_check_s: float = 5.0  # session re-check during the stream
    # Deadline of each command type (F9): without an observed effect before it, `timed_out`.
    deadline_pause_entries_s: float = 10.0
    deadline_resume_entries_s: float = 30.0
    deadline_flatten_s: float = 60.0
    deadline_stop_s: float = 60.0
    deadline_start_s: float = 60.0
    deadline_deploy_s: float = 60.0
    deadline_close_position_s: float = 60.0
    deadline_cancel_entry_order_s: float = 30.0
    # Fault injection into an engine simulated by an instance's parameters: never outside
    # tests and the disposable e2e stack.
    engine_failure_injection: bool = False
    # Only origin allowed for state-changing requests (CSRF). Default: Caddy's.
    public_origin: str = Field(default="https://localhost:8443", pattern=r"^https://[^/\s]+$")
    # Docker secrets paths (/run/secrets/…), never the values.
    postgres_password_file: Path
    # The API always receives it; the worker only with the engines profile (engines' native
    # API credentials). Without it, `master_key()` fails.
    master_key_file: Path | None = None
    # Redis configuration file from the secret (`requirepass <value>`): if present, its
    # password is inserted into `redis_url` in memory only (never in an environment variable).
    redis_conf_file: Path | None = None
    # In-memory (tmpfs) directory of the files handed to engines, one subfolder per instance.
    # Same variable name as the runner: `ENGINE_RUNTIME_DIR`, no prefix.
    engine_runtime_dir: Path = Field(
        default=Path("/run/centrade"), validation_alias="ENGINE_RUNTIME_DIR"
    )

    @model_validator(mode="before")
    @classmethod
    def _redis_password(cls, data: dict[str, object]) -> dict[str, object]:
        conf, url = data.get("redis_conf_file"), data.get("redis_url")
        if conf is None or not isinstance(url, str):
            return data
        lines = Path(str(conf)).read_text(encoding="utf-8").splitlines()
        password = next(
            (x.split(None, 1)[1].strip() for x in lines if x.startswith("requirepass ")), ""
        )
        if not password or "@" in url:
            raise ValueError("redis_conf_file sans `requirepass`, ou redis_url déjà authentifiée")
        scheme, rest = url.split("://", 1)
        return {**data, "redis_url": f"{scheme}://:{quote(password, safe='')}@{rest}"}

    def command_deadline_s(self, command_type: str) -> float:
        return float(getattr(self, f"deadline_{command_type}_s"))

    def database_url(self) -> str:
        password = self.postgres_password_file.read_text(encoding="utf-8").strip()
        if not password:
            raise ValueError("fichier du mot de passe Postgres vide")
        return (
            f"postgresql+asyncpg://{quote(self.db_user)}:{quote(password, safe='')}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    def master_key(self) -> bytes:
        """AES-256 master key: 32 bytes base64-encoded in the file."""
        if self.master_key_file is None:
            raise ValueError("clé maître non fournie à ce processus (CENTRADE_MASTER_KEY_FILE)")
        key = base64.b64decode(
            self.master_key_file.read_text(encoding="utf-8").strip(), validate=True
        )
        if len(key) != 32:
            raise ValueError("la clé maître doit faire 32 octets (base64)")
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
