import base64
from pathlib import Path

import pytest
from centrade_core.settings import Settings
from pydantic import ValidationError


def test_aucun_secret_par_defaut(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("REDIS_URL", "POSTGRES_PASSWORD_FILE", "MASTER_KEY_FILE"):
        monkeypatch.delenv(f"CENTRADE_{var}", raising=False)
    with pytest.raises(ValidationError) as err:
        Settings()
    manquants = {e["loc"][0] for e in err.value.errors()}
    assert {"postgres_password_file", "master_key_file", "redis_url"} <= manquants


def test_url_et_cle_lues_dans_les_fichiers(tmp_path: Path) -> None:
    pw, key = tmp_path / "pw", tmp_path / "key"
    pw.write_text("p@ss/w:rd\n")
    key.write_text(base64.b64encode(bytes(32)).decode())
    s = Settings(redis_url="redis://r:6379/0", postgres_password_file=pw, master_key_file=key)
    assert (
        s.database_url() == "postgresql+asyncpg://centrade:p%40ss%2Fw%3Ard@postgres:5432/centrade"
    )
    assert s.master_key() == bytes(32)
    key.write_text(base64.b64encode(bytes(16)).decode())
    with pytest.raises(ValueError, match="32 octets"):
        s.master_key()
