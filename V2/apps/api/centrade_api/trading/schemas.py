"""Schemas of orders, positions and trades (SPEC §8, §9).

Money and quantities as decimal strings, with the currency. Each row carries the desired mode and
the observed (dated) mode of its instance: the interface never mixes paper and live.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel

from centrade_api.core.observed import Observed, ObservedMode

Mode = Literal["paper", "live"]


class _Owned(BaseModel):
    """Ce que toute ligne dit de son instance : modes et compte (None : instance sans compte)."""

    instance_id: UUID
    mode: Mode  # = desired_mode, kept for existing clients
    desired_mode: Mode  # desired
    observed_mode: Observed[ObservedMode]  # observed, dated; "unknown" if never observed
    account_id: UUID | None
    account_label: str | None


class OrderOut(_Owned):
    id: UUID
    client_order_id: str  # engine-side identifier
    instrument: str
    side: str
    intent: str  # entry | increase | exit | stop
    status: str
    quantity: str
    price: str | None
    currency: str
    decision_id: UUID | None
    observed_at: AwareDatetime
    stale: bool
    cancelable: bool  # still-open entry order: the only case where cancellation is offered
    created_at: AwareDatetime


class PositionOut(_Owned):
    id: UUID
    instrument: str
    side: str
    quantity: str
    entry_price: str | None
    currency: str
    observed_at: AwareDatetime
    stale: bool
    stop_price: str | None
    stop_venue: str | None  # venue | engine
    stop_type: str | None  # fixed | trailing | dynamic
    # Gap between the stop and the entry price, in % of the entry price (no current price in
    # the database): positive = the stop limits a loss, negative = it already guarantees a gain.
    stop_distance_pct: str | None
    protection_state: str  # protected | engine_only | unprotected | unknown
    protection_verified_at: AwareDatetime | None


class TradeOut(_Owned):
    id: UUID
    instrument: str
    quantity: str
    entry_price: str
    exit_price: str
    entry_cause: str
    exit_cause: str  # a value of EXIT_CAUSES
    pnl: str
    fees: str
    currency: str
    opened_at: AwareDatetime
    closed_at: AwareDatetime
    duration_s: int
