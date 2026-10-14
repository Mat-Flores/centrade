import base64
import re
from pathlib import Path

import pytest
from centrade_core.settings import Settings
from pydantic import ValidationError


def test_no_secret_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("REDIS_URL", "POSTGRES_PASSWORD_FILE", "MASTER_KEY_FILE"):
        monkeypatch.delenv(f"CENTRADE_{var}", raising=False)
    with pytest.raises(ValidationError) as err:
        Settings()
    manquants = {e["loc"][0] for e in err.value.errors()}
    assert {"postgres_password_file", "redis_url"} <= manquants


def test_master_key_is_optional_but_never_defaulted(tmp_path: Path) -> None:
    """The worker and the migrations do not need it (least privilege); whoever asks for it
    without having received it fails."""
    s = Settings(redis_url="redis://r:6379/0", postgres_password_file=tmp_path / "pw")
    assert s.master_key_file is None and s.engine_failure_injection is False
    with pytest.raises(ValueError, match="clé maître"):
        s.master_key()


def test_url_and_key_are_read_from_files(tmp_path: Path) -> None:
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


def test_production_image_has_no_test_helper_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    lines = (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for helper in ("apps/api/centrade_api/testing.py", "apps/worker/centrade_worker/testing.py"):
        assert (root / helper).is_file()
        # Excluded after the line that admits its folder: in .dockerignore, the last one wins.
        assert lines.index(helper) > lines.index("!" + helper.rsplit("/", 1)[0]), helper
    for module in root.glob("apps/*/centrade_*/**/*.py"):
        if module.name != "testing.py":
            assert ".testing" not in module.read_text(encoding="utf-8"), module


def test_worker_does_not_receive_the_master_key() -> None:
    root = Path(__file__).resolve().parents[1]
    compose = (root / "deploy/compose/core.yml").read_text(encoding="utf-8")
    # `  name:` blocks of the `services:` section; pyyaml is not a project dependency.
    section = compose.split("\nservices:\n", 1)[1].split("\nnetworks:\n", 1)[0]
    services = dict(re.findall(r"^  (\w+):\n((?:(?:    .*)?\n)+)", section, re.M))
    assert {"api", "worker", "migrate"} <= set(services)
    assert "master_key" in services["api"] and "CENTRADE_MASTER_KEY_FILE" in services["api"]
    for name in ("worker", "migrate"):
        assert "master_key" not in services[name].lower(), name
    assert "MASTER_KEY" not in compose.split("\nservices:\n", 1)[0]  # not in the common anchor
