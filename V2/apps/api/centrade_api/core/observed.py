"""Observed, dated value (I1).

Every value coming from an engine goes out as `Observed`: the value, the date of its observation
and `stale`. Desired state and observed state remain distinct fields; nothing copies one into
the other.
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
    observed_at: AwareDatetime | None  # None: never observed
    stale: bool  # older than the freshness threshold


def observe[T](
    value: T, observed_at: datetime | None, now: datetime, stale_after_s: float
) -> Observed[T]:
    stale = observed_at is not None and now - observed_at > timedelta(seconds=stale_after_s)
    return Observed(value=value, observed_at=observed_at, stale=stale)
