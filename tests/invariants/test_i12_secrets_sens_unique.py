"""I12 / K2 : les secrets n'atteignent jamais les logs (SPEC §13, journalisation)."""

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
def sortie() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    configure_logging(stream=buf)
    yield buf
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


def test_i12_logs_masquent_les_valeurs_sentinelles(sortie: io.StringIO) -> None:
    sentinelles = [S.format(i) for i in range(1, 36)]
    s = iter(sentinelles)
    log = structlog.get_logger()

    # Par nom de clé, à plat, dans des structures imbriquées et sous différentes casses.
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
    # Dans du texte libre : message, URL, trace.
    log.warning(f"échec token={next(s)} sur /x?password={next(s)}&k=v")
    log.info("entete", valeur=f"Authorization: Bearer {next(s)}")
    try:
        raise RuntimeError(f"api_key={next(s)}")
    except RuntimeError:
        log.exception("plantage")
    # Journaux de la stdlib (uvicorn) : message, arguments, `extra`.
    logging.getLogger("uvicorn.error").error("rejeté: secret=%s", next(s))
    logging.getLogger("uvicorn.access").info(
        '%s "GET /cb?token=%s HTTP/1.1" 401', "127.0.0.1", next(s)
    )
    logging.getLogger("uvicorn.error").error("x", extra={"password": next(s)})
    # Identifiants dans une URL, avec ou sans nom d'utilisateur.
    log.error("connexion refusée", url=f"redis://:{next(s)}@redis:6379/0")
    log.error(f"échec sur postgresql+asyncpg://centrade:{next(s)}@postgres:5432/centrade")
    # Valeur à espaces : masquée en entier, pas seulement son premier mot.
    a, b, c, d = next(s), next(s), next(s), next(s)
    log.warning(f'refus password="{a} {b}" puis suite')
    log.warning(f"refus passphrase={c} {d}")
    # Clé `code` (TOTP, code de récupération), à plat, imbriquée et dans du texte.
    log.info("totp", code=next(s), corps={"code": next(s), "status_code": 401})
    log.info(f"essai code={next(s)}")

    class _Corps(BaseModel):
        n: int

    for valeur in (next(s), {"jeton": next(s), "x": [next(s) + " " + next(s)]}):
        try:  # Pydantic recopie la valeur refusée dans son message : `input_value=…`
            _Corps.model_validate({"n": valeur})
        except ValidationError as exc:
            log.error("validation", error=str(exc))
            try:
                raise RuntimeError("requête rejetée") from exc
            except RuntimeError:
                log.exception("trace")

    reste = len(list(s))
    assert reste < 5  # presque toutes les sentinelles ont servi
    sortie_texte = sortie.getvalue()
    for sentinelle in sentinelles[: len(sentinelles) - reste]:
        assert sentinelle not in sortie_texte, sentinelle
    assert "401" in sortie_texte and "status_code" in sortie_texte  # `status_code` reste lisible
    assert "@redis:6379/0" in sortie_texte and "@postgres:5432/centrade" in sortie_texte
    assert MASK in sortie_texte
    assert "visible-001" in sortie_texte  # on masque les secrets, pas tout le reste


async def test_i12_erreur_sql_sans_les_parametres(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    try:
        async with engine.connect() as c:
            with pytest.raises(DBAPIError) as err:
                await c.execute(text("SELECT 1 / 0 WHERE :v <> ''"), {"v": S.format("sql")})
    finally:
        await engine.dispose()
    assert "SENTINELLE" not in str(err.value)  # `hide_parameters` : aucune valeur liée
