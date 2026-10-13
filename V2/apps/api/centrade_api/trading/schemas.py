"""Schémas des ordres, positions et trades (SPEC §8, §9).

Argent et quantités en chaînes décimales, avec la devise. Chaque ligne porte le mode voulu et le
mode observé (daté) de son instance : l'interface ne mélange jamais paper et live.
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
    mode: Mode  # = desired_mode, gardé pour les clients existants
    desired_mode: Mode  # voulu
    observed_mode: Observed[ObservedMode]  # observé, daté ; « unknown » si jamais observé
    account_id: UUID | None
    account_label: str | None


class OrderOut(_Owned):
    id: UUID
    client_order_id: str  # identifiant côté moteur
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
    cancelable: bool  # ordre d'entrée encore ouvert : seul cas où l'annulation est proposée
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
    # Écart entre le stop et le prix d'entrée, en % du prix d'entrée (pas de cours courant en
    # base) : positif = le stop limite une perte, négatif = il garantit déjà un gain.
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
    exit_cause: str  # une valeur de EXIT_CAUSES
    pnl: str
    fees: str
    currency: str
    opened_at: AwareDatetime
    closed_at: AwareDatetime
    duration_s: int
