"""Configuration. Aucun secret n'a de valeur par défaut : un fichier absent arrête le démarrage."""

import base64
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CENTRADE_", frozen=True)

    db_host: str = "postgres"
    db_port: int = 5432
    db_user: str = "centrade"
    db_name: str = "centrade"
    redis_url: str = Field(description="redis://hôte:port/db, sans mot de passe")
    # Chemins de Docker secrets (/run/secrets/…), jamais les valeurs.
    postgres_password_file: Path
    master_key_file: Path

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
        key = base64.b64decode(
            self.master_key_file.read_text(encoding="utf-8").strip(), validate=True
        )
        if len(key) != 32:
            raise ValueError("la clé maître doit faire 32 octets (base64)")
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
