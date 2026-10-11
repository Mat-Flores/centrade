"""Cycle de vie d'une commande (SPEC F9, I8) : transitions ordonnées, états terminaux figés.

`requested -> dispatched -> acknowledged -> verified`, ou `failed`, `timed_out`, `superseded`.
La transition est une seule instruction conditionnelle : deux écrivains concurrents (API et
worker) ne peuvent ni sauter une étape ni modifier un état terminal.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_core.models.trading import Command

Status = Literal[
    "requested", "dispatched", "acknowledged", "verified", "failed", "timed_out", "superseded"
]
CommandType = Literal["deploy", "start", "stop", "pause_entries", "resume_entries", "flatten"]

# Seules transitions permises. Un état absent des clés est terminal.
NEXT: Final[dict[str, frozenset[str]]] = {
    "requested": frozenset({"dispatched", "timed_out", "superseded"}),
    "dispatched": frozenset({"acknowledged", "failed", "timed_out", "superseded"}),
    "acknowledged": frozenset({"verified", "timed_out", "superseded"}),
}
TERMINAL: Final = frozenset({"verified", "failed", "timed_out", "superseded"})
ACTIVE: Final = tuple(NEXT)
STEP_COLUMN: Final[dict[str, str]] = {
    "dispatched": "dispatched_at",
    "acknowledged": "acknowledged_at",
    "verified": "verified_at",
    "failed": "failed_at",
    "timed_out": "timed_out_at",
    "superseded": "superseded_at",
}
# Ce qui réduit le risque passe devant (F9) ; ce qui l'augmente peut être remplacé.
PRIORITY: Final = frozenset({"pause_entries", "flatten"})
RISK_INCREASING: Final = frozenset({"resume_entries", "start"})
DESIRED_AFTER: Final[dict[str, str | None]] = {  # None : l'état voulu ne change pas
    "deploy": "exits_only",
    "start": "exits_only",
    "stop": "stopped",
    "pause_entries": "exits_only",
    "resume_entries": "running",
    "flatten": None,
}


def can_transition(src: str, dst: str) -> bool:
    return dst in NEXT.get(src, frozenset())


async def transition(
    s: AsyncSession,
    command_id: UUID,
    dst: Status,
    now: datetime,
    *,
    result: dict[str, Any] | None = None,
) -> bool:
    """Passe la commande à `dst` si, et seulement si, son état actuel le permet. Vrai si fait."""
    sources = [src for src, targets in NEXT.items() if dst in targets]
    values: dict[str, Any] = {"status": dst, STEP_COLUMN[dst]: now, "updated_at": now}
    if result is not None:
        values["result"] = result
    done = await s.execute(
        update(Command)
        .where(Command.id == command_id, Command.status.in_(sources))
        .values(**values)
        .returning(Command.id)
    )
    return done.first() is not None
