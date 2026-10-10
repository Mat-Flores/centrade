import logging
import os

import structlog


def configure_logging() -> None:
    level = logging.getLevelNamesMapping().get(os.environ.get("CENTRADE_LOG_LEVEL", "INFO"), 20)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )
