"""Cycle de vie d'une commande (SPEC F9, I8) : transitions ordonnées, états terminaux figés.

`requested -> dispatched -> acknowledged -> verified`, ou `failed`, `timed_out`, `superseded`.
La transition est une seule instruction conditionnelle : deux écrivains concurrents (API et
worker) ne peuvent ni sauter une étape ni modifier un état terminal.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_core.models.trading import Command

Status = Literal[
    "requested", "dispatched", "acknowledged", "verified", "failed", "timed_out", "superseded"
]
CommandType = Literal[
    "deploy",
    "start",
    "stop",
    "pause_entries",
    "resume_entries",
    "flatten",
    "close_position",
    "cancel_entry_order",
]

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
# Réduit le risque : jamais expirée avant l'envoi, l'échéance court à compter de l'envoi (I4).
RISK_REDUCING: Final = PRIORITY | {"stop", "close_position", "cancel_entry_order"}
RISK_INCREASING: Final = frozenset({"resume_entries", "start"})
# États observés depuis lesquels une commande qui augmente le risque a un sens, et son libellé.
_READY: Final[dict[str, tuple[tuple[str, ...], str]]] = {
    "resume_entries": (("exits_only", "running"), "reprise des entrées"),
    "start": (("stopped", "error"), "démarrage"),
}
DESIRED_AFTER: Final[dict[str, str | None]] = {  # None : l'état voulu ne change pas
    "deploy": "exits_only",
    "start": "exits_only",
    "stop": "stopped",
    "pause_entries": "exits_only",
    "resume_entries": "running",
    "flatten": None,
    "close_position": None,
    "cancel_entry_order": None,
}


def risk_increase_refusal(
    command_type: str,
    *,
    mode: str,
    observed_state: str,
    observed_mode: str | None,
    observed_at: datetime | None,
    now: datetime,
    stale_after_s: float,
) -> str | None:
    """Raison du refus d'une commande qui augmente le risque, ou None (I5 : refus au moindre
    doute). Pure : la même règle sert à la demande (API) et juste avant l'envoi (worker)."""
    if command_type not in RISK_INCREASING:
        return None
    ready, label = _READY[command_type]
    if observed_at is None or observed_state == "unknown":
        return f"L'état observé est inconnu : {label} refusé."
    # Trop vieux, ou daté du futur (dérive d'horloge) : dans les deux cas, on ne sait pas.
    if abs(now - observed_at) > timedelta(seconds=stale_after_s):
        return f"L'état observé est périmé : {label} refusé."
    if observed_state not in ready:
        return f"État observé « {observed_state} » : {label} impossible."
    if command_type == "resume_entries" and observed_mode != mode:
        return f"Le mode observé diffère du mode de l'instance (I3) : {label} refusé."
    return None


async def transition(
    s: AsyncSession,
    command_id: UUID,
    dst: Status,
    now: datetime,
    *,
    result: dict[str, Any] | None = None,
    deadline_at: datetime | None = None,
) -> bool:
    """Passe la commande à `dst` si, et seulement si, son état actuel le permet. Vrai si fait."""
    sources = [src for src, targets in NEXT.items() if dst in targets]
    if not sources:  # `requested` : état initial, on n'y revient jamais
        return False
    values: dict[str, Any] = {"status": dst, STEP_COLUMN[dst]: now, "updated_at": now}
    if result is not None:
        values["result"] = result
    if deadline_at is not None:
        values["deadline_at"] = deadline_at
    done = await s.execute(
        update(Command)
        .where(Command.id == command_id, Command.status.in_(sources))
        .values(**values)
        .returning(Command.id)
    )
    return done.first() is not None
