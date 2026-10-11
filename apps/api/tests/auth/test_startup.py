"""Démarrage réel de l'API : configuration lue dans l'environnement, refus sans clé maître."""

import base64
from pathlib import Path

import pytest
from centrade_api.main import create_app
from centrade_core.settings import get_settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

ORIGIN = "https://centrade.test"


@pytest.fixture
def env(migrated_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = make_url(migrated_url)
    (tmp_path / "pw").write_text(url.password or "")
    key = tmp_path / "key"
    key.write_text(base64.b64encode(bytes(range(32))).decode())
    for name, value in {
        "DB_HOST": url.host,
        "DB_PORT": url.port,
        "DB_USER": url.username,
        "DB_NAME": url.database,
        "REDIS_URL": "redis://inutilise:6379/0",
        "POSTGRES_PASSWORD_FILE": tmp_path / "pw",
        "MASTER_KEY_FILE": key,
        "PUBLIC_ORIGIN": ORIGIN,
    }.items():
        monkeypatch.setenv(f"CENTRADE_{name}", str(value))
    get_settings.cache_clear()
    return key


def test_api_demarree_sert_l_authentification_sur_la_base(env: Path) -> None:
    try:
        with TestClient(create_app(), base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "personne@example.test", "password": "SENTINELLE-x"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize(
    "content", [None, "", "pas-du-base64", base64.b64encode(b"k" * 16).decode()]
)
def test_api_ne_demarre_pas_sans_cle_maitre_valide(env: Path, content: str | None) -> None:
    if content is None:
        env.unlink()
    else:
        env.write_text(content)
    try:
        with pytest.raises((OSError, ValueError)), TestClient(create_app()):
            pass
    finally:
        get_settings.cache_clear()
