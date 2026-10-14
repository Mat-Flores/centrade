# The pipeline lives in centrade_core so that the worker shares it.
from centrade_core.logging import configure_logging

__all__ = ["configure_logging"]
