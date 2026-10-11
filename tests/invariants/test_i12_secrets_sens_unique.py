"""I12 / K2 : les secrets n'atteignent jamais les logs (SPEC §13, journalisation)."""

import io
import logging
from collections.abc import Iterator

import pytest
import structlog
from centrade_core.logging import MASK, configure_logging

S = "SENTINELLE-{}-0xDEADBEEF"


@pytest.fixture
def sortie() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    configure_logging(stream=buf)
    yield buf
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


def test_i12_logs_masquent_les_valeurs_sentinelles(sortie: io.StringIO) -> None:
    sentinelles = [S.format(i) for i in range(1, 21)]
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

    sortie_texte = sortie.getvalue()
    for sentinelle in sentinelles[: 20 - len(list(s))]:
        assert sentinelle not in sortie_texte, sentinelle
    assert MASK in sortie_texte
    assert "visible-001" in sortie_texte  # on masque les secrets, pas tout le reste
