"""Journalisation structlog avec masquage des secrets (K2, SPEC §13).

Tout passe par un seul pipeline, y compris les journaux d'uvicorn et de la stdlib.
"""

import logging
import os
import re
import sys
from collections.abc import Mapping
from typing import Any, TextIO

import structlog
from structlog.typing import EventDict, WrappedLogger

MASK = "***"
# Nom de clé sensible, en sous-chaîne, sans casse : `X-Api-Key`, `totp_secret`, `Set-Cookie`…
# `code` (TOTP, récupération) seulement en nom entier : `status_code` reste lisible.
_SENSITIVE_KEY = re.compile(
    r"pass(word|wd)?$|pwd|secret|token|authorization|cookie|api[-_]?key|private[-_]?key"
    r"|master[-_]?key|totp|(^|[-_])otp|recovery|credential|session|bearer|signature|passphrase"
    r"|^codes?$",
    re.I,
)
_NAMES = (
    r"(?:pass(?:word|wd|phrase)?|pwd|secret|token|api[-_]?key|totp|otp|authorization|cookie"
    r"|\bcodes?)"
)
# Valeurs sensibles dans du texte libre (message, URL, trace), dans l'ordre d'application.
_SENSITIVE_TEXT = (
    # Valeur refusée que Pydantic recopie dans son message : `input_value=…, input_type=…`.
    re.compile(r"(input_value=).*?(?=, input_type=|$)", re.M),
    # Identifiants d'une URL : `scheme://utilisateur:secret@hôte`.
    re.compile(r"(://[^/\s:@]*:)[^/\s@]+(?=@)"),
    re.compile(r"(?i)((?:bearer|basic)\s+)[^\s&\"',;]+"),
    # `nom=valeur`, `nom: valeur`. Entre guillemets : jusqu'au guillemet fermant. Sinon jusqu'à
    # un séparateur ou la fin de ligne, espaces compris : on masque trop plutôt que pas assez.
    re.compile(rf"(?i)({_NAMES}[\"']?\s*[=:]\s*)(?:\"[^\"\n]*\"?|'[^'\n]*'?|[^&\"',;\n]+)"),
)


def _mask(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            k: MASK if isinstance(k, str) and _SENSITIVE_KEY.search(k) else _mask(v)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        return [_mask(v) for v in value]
    if isinstance(value, str):
        for pattern in _SENSITIVE_TEXT:
            value = pattern.sub(lambda m: m.group(1) + MASK, value)
        return value
    if isinstance(value, bytes | bytearray):
        return MASK  # du binaire dans un log est au mieux inutile, au pire une clé
    return value


def mask_secrets(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    return _mask(event_dict)  # type: ignore[no-any-return]  # un dict reste un dict


def configure_logging(stream: TextIO | None = None) -> None:
    level = logging.getLevelNamesMapping().get(os.environ.get("CENTRADE_LOG_LEVEL", "INFO"), 20)
    shared: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=[
            *shared,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            # Entrées de la stdlib (uvicorn…) seulement : elles reçoivent le même habillage.
            foreign_pre_chain=[*shared, structlog.stdlib.ExtraAdder()],
            processors=[
                structlog.processors.format_exc_info,
                mask_secrets,  # après format_exc_info : une trace est du texte à masquer aussi
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # uvicorn installe ses propres gestionnaires au démarrage : on les remplace par le nôtre.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
