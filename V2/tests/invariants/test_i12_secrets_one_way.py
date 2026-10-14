"""I12 / K2: secrets never reach the logs (SPEC §13, logging)."""

import io
import logging
from collections.abc import Iterator

import pytest
import structlog
from centrade_core.db import make_engine
from centrade_core.logging import MASK, configure_logging
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

S = "SENTINELLE-{}-0xDEADBEEF"


@pytest.fixture
def output() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    configure_logging(stream=buf)
    yield buf
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


def test_i12_logs_mask_sentinel_values(output: io.StringIO) -> None:
    sentinels = [S.format(i) for i in range(1, 36)]
    s = iter(sentinels)
    log = structlog.get_logger()

    # By key name, flat, in nested structures and in different cases.
    log.info(
        "connexion",
        password=next(s),
        TOTP_secret=next(s),
        api_key=next(s),
        master_key=next(s),
        session_token=next(s),
        headers={
            "Authorization": f"Bearer {next(s)}",
            "Cookie": f"__Host-sid={next(s)}",
            "X-Api-Key": next(s),
        },
        requete={
            "corps": [{"username": "ok", "passwd": next(s)}, ("a", {"refresh_token": next(s)})]
        },
        recovery_codes=[next(s), next(s)],
        raw=next(s).encode(),
        instance_id="visible-001",
    )
    # In free text: message, URL, trace.
    log.warning(f"échec token={next(s)} sur /x?password={next(s)}&k=v")
    log.info("entete", valeur=f"Authorization: Bearer {next(s)}")
    try:
        raise RuntimeError(f"api_key={next(s)}")
    except RuntimeError:
        log.exception("plantage")
    # Stdlib logs (uvicorn): message, arguments, `extra`.
    logging.getLogger("uvicorn.error").error("rejeté: secret=%s", next(s))
    logging.getLogger("uvicorn.access").info(
        '%s "GET /cb?token=%s HTTP/1.1" 401', "127.0.0.1", next(s)
    )
    logging.getLogger("uvicorn.error").error("x", extra={"password": next(s)})
    # Credentials in a URL, with or without a username.
    log.error("connexion refusée", url=f"redis://:{next(s)}@redis:6379/0")
    log.error(f"échec sur postgresql+asyncpg://centrade:{next(s)}@postgres:5432/centrade")
    # Value with spaces: masked entirely, not just its first word.
    a, b, c, d = next(s), next(s), next(s), next(s)
    log.warning(f'refus password="{a} {b}" puis suite')
    log.warning(f"refus passphrase={c} {d}")
    # `code` key (TOTP, recovery code), flat, nested and in text.
    log.info("totp", code=next(s), corps={"code": next(s), "status_code": 401})
    log.info(f"essai code={next(s)}")

    class _Corps(BaseModel):
        n: int

    for valeur in (next(s), {"jeton": next(s), "x": [next(s) + " " + next(s)]}):
        try:  # Pydantic copies the rejected value into its message: `input_value=...`
            _Corps.model_validate({"n": valeur})
        except ValidationError as exc:
            log.error("validation", error=str(exc))
            try:
                raise RuntimeError("requête rejetée") from exc
            except RuntimeError:
                log.exception("trace")

    leftover = len(list(s))
    assert leftover < 5  # almost all sentinels were used
    output_text = output.getvalue()
    for sentinel in sentinels[: len(sentinels) - leftover]:
        assert sentinel not in output_text, sentinel
    assert "401" in output_text and "status_code" in output_text  # `status_code` stays readable
    assert "@redis:6379/0" in output_text and "@postgres:5432/centrade" in output_text
    assert MASK in output_text
    assert "visible-001" in output_text  # secrets are masked, not everything else


async def test_i12_sql_error_omits_parameters(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    try:
        async with engine.connect() as c:
            with pytest.raises(DBAPIError) as err:
                await c.execute(text("SELECT 1 / 0 WHERE :v <> ''"), {"v": S.format("sql")})
    finally:
        await engine.dispose()
    assert "SENTINELLE" not in str(err.value)  # `hide_parameters`: no bound value
