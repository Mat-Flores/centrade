"""Valeur observée et datée (I1).

Toute valeur issue d'un moteur sort en `Observed` : la valeur, la date de son observation et
`stale`. L'état voulu et l'état observé restent des champs distincts ; rien ne copie l'un dans
l'autre.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel

ObservedState = Literal[
    "starting", "exits_only", "running", "halted", "stopped", "error", "unknown"
]
ObservedMode = Literal["paper", "live", "unknown"]


class Observed[T](BaseModel):
    value: T
    observed_at: AwareDatetime | None  # None : jamais observé
    stale: bool  # plus ancien que le seuil de fraîcheur


def observe[T](
    value: T, observed_at: datetime | None, now: datetime, stale_after_s: float
) -> Observed[T]:
    stale = observed_at is not None and now - observed_at > timedelta(seconds=stale_after_s)
    return Observed(value=value, observed_at=observed_at, stale=stale)
