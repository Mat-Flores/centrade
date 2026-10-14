"""Checks of a strategy version, per engine type (SPEC §7).

The checks (manifest, source code) are those of the adapter of the engine declared by the
manifest. They are pure and run at write time: a refused version is not recorded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import centrade_freqtrade.checks as freqtrade_checks
from centrade_core.engine.contract import StaticChecks
from centrade_core.engine.types import Manifest
from centrade_core.ids import uuid7
from centrade_fake.engine import ENGINE as FAKE
from centrade_fake.engine import FakeEngine

# Engine type -> checks of its adapter. An unknown engine is refused.
CHECKS: dict[str, StaticChecks] = {
    FAKE: FakeEngine(clock=lambda: datetime.now(UTC), seed=0, new_id=uuid7),
    freqtrade_checks.ENGINE: freqtrade_checks,
}


def check_version(raw: dict[str, Any], code: str) -> tuple[dict[str, Any], list[str]]:
    """Canonical manifest (JSON) and refusal reasons; empty list = accepted."""
    try:
        manifest = Manifest.model_validate(raw)
    except ValueError as e:  # ValidationError: neither received value nor context in the reasons
        problems: list[Any] = getattr(e, "errors", lambda: [])()
        return {}, [f"manifest.{'.'.join(map(str, x['loc']))} : {x['msg']}" for x in problems]
    checks = CHECKS.get(manifest.engine)
    if checks is None:
        return {}, [f"type de moteur inconnu : {manifest.engine}"]
    props = manifest.params_schema.get("properties", {})
    defaults = {k: p["default"] for k, p in props.items() if isinstance(p, dict) and "default" in p}
    errors: list[str] = [
        *checks.validate(manifest, defaults).errors,
        *checks.check_source(manifest, code).errors,
    ]
    return manifest.model_dump(mode="json"), errors
