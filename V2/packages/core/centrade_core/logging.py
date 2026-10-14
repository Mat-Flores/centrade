"""structlog logging with secret masking (K2, SPEC §13).

Everything goes through a single pipeline, including uvicorn and stdlib logs.
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
# Sensitive key name, as a substring, case-insensitive: `X-Api-Key`, `totp_secret`, `Set-Cookie`…
# `code` (TOTP, recovery) only as a whole name: `status_code` stays readable.
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
# Sensitive values in free text (message, URL, trace), in order of application.
_SENSITIVE_TEXT = (
    # Rejected value that Pydantic copies into its message: `input_value=…, input_type=…`.
    re.compile(r"(input_value=).*?(?=, input_type=|$)", re.M),
    # URL credentials: `scheme://user:secret@host`.
    re.compile(r"(://[^/\s:@]*:)[^/\s@]+(?=@)"),
    re.compile(r"(?i)((?:bearer|basic)\s+)[^\s&\"',;]+"),
    # `name=value`, `name: value`. Quoted: up to the closing quote. Otherwise up to
    # a separator or end of line, spaces included: we mask too much rather than too little.
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
        return MASK  # binary in a log is at best useless, at worst a key
    return value


def mask_secrets(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    return _mask(event_dict)  # type: ignore[no-any-return]  # a dict stays a dict


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
            # stdlib entries (uvicorn…) only: they get the same wrapping.
            foreign_pre_chain=[*shared, structlog.stdlib.ExtraAdder()],
            processors=[
                structlog.processors.format_exc_info,
                mask_secrets,  # after format_exc_info: a trace is text to mask too
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # uvicorn installs its own handlers at startup: we replace them with ours.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
