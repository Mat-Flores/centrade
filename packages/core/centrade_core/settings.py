"""Configuration. Aucun secret n'a de valeur par défaut : un fichier absent arrête le démarrage."""

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
    engine_silent_after_s: float = 30.0  # moteur muet au-delà : état observé `unknown`
    worker_heartbeat_ttl_s: int = 15
    # Fraîcheur d'une valeur de moteur (SPEC §13) : au-delà, l'API la marque `stale`.
    observed_stale_after_s: float = 30.0
    stream_heartbeat_s: float = 2.0  # battement du flux SSE ; le front attend 5 s au plus
    stream_session_check_s: float = 5.0  # revérification de la session pendant le flux
    # Échéance de chaque type de commande (F9) : sans effet observé avant, `timed_out`.
    deadline_pause_entries_s: float = 10.0
    deadline_resume_entries_s: float = 30.0
    deadline_flatten_s: float = 60.0
    deadline_stop_s: float = 60.0
    deadline_start_s: float = 60.0
    deadline_deploy_s: float = 60.0
    deadline_close_position_s: float = 60.0
    deadline_cancel_entry_order_s: float = 30.0
    # Injection de pannes dans un moteur simulé par les paramètres d'une instance : jamais hors
    # des tests et de la pile e2e jetable.
    engine_failure_injection: bool = False
    # Seule origine admise pour les requêtes qui changent un état (CSRF). Défaut : celui de Caddy.
    public_origin: str = Field(default="https://localhost:8443", pattern=r"^https://[^/\s]+$")
    # Chemins de Docker secrets (/run/secrets/…), jamais les valeurs.
    postgres_password_file: Path
    # Seule l'API la reçoit (moindre privilège) : sans elle, `master_key()` échoue.
    master_key_file: Path | None = None
    # Fichier de configuration Redis du secret (`requirepass <valeur>`) : si présent, son mot de
    # passe est inséré dans `redis_url` en mémoire seulement (jamais en variable d'environnement).
    redis_conf_file: Path | None = None
    # Répertoire en mémoire (tmpfs) des fichiers remis aux moteurs, un sous-dossier par instance.
    # Même nom de variable que le runner : `ENGINE_RUNTIME_DIR`, sans préfixe.
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
        """Clé maître AES-256 : 32 octets encodés en base64 dans le fichier."""
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
