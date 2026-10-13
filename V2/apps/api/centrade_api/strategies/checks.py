"""Contrôles d'une version de stratégie, par type de moteur (SPEC §7).

Les contrôles (manifest, code source) sont ceux de l'adaptateur du moteur déclaré par le manifest.
Ils sont purs et tournent à l'écriture : une version refusée n'est pas enregistrée.
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

# Type de moteur -> contrôles de son adaptateur. Un moteur inconnu est refusé.
CHECKS: dict[str, StaticChecks] = {
    FAKE: FakeEngine(clock=lambda: datetime.now(UTC), seed=0, new_id=uuid7),
    freqtrade_checks.ENGINE: freqtrade_checks,
}


def check_version(raw: dict[str, Any], code: str) -> tuple[dict[str, Any], list[str]]:
    """Manifest canonique (JSON) et motifs de refus ; liste vide = accepté."""
    try:
        manifest = Manifest.model_validate(raw)
    except ValueError as e:  # ValidationError : ni valeur reçue ni contexte dans les motifs
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
