"""Schémas de l'API de pilotage (SPEC §8, §9).

I1 : toute valeur issue d'un moteur sort en `Observed` (valeur + date d'observation + `stale`).
Les réponses qui en portent ont `server_time`, l'horloge du serveur au moment de la réponse :
le client calcule l'âge sans se fier à la sienne. L'état voulu et l'état observé sont des champs
distincts ; rien ici ne copie l'un dans l'autre. Aucun schéma ne nomme un moteur précis.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timedelta
from typing import Any, Literal, Self, cast
from uuid import UUID

from centrade_core.models.trading import Alert, Command, Event, Instance
from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

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


class CommandOut(BaseModel):
    id: UUID
    instance_id: UUID
    type: str
    actor: str
    status: str
    correlation_id: UUID
    requested_at: AwareDatetime
    deadline_at: AwareDatetime
    dispatched_at: AwareDatetime | None
    acknowledged_at: AwareDatetime | None
    verified_at: AwareDatetime | None
    failed_at: AwareDatetime | None
    timed_out_at: AwareDatetime | None
    superseded_at: AwareDatetime | None
    result: dict[str, Any] | None
    server_time: AwareDatetime

    @classmethod
    def of(cls, c: Command, now: datetime) -> CommandOut:
        return cls(
            id=c.id,
            instance_id=c.instance_id,
            type=c.type,
            actor=c.actor,
            status=c.status,
            correlation_id=c.correlation_id,
            requested_at=c.requested_at,
            deadline_at=c.deadline_at,
            dispatched_at=c.dispatched_at,
            acknowledged_at=c.acknowledged_at,
            verified_at=c.verified_at,
            failed_at=c.failed_at,
            timed_out_at=c.timed_out_at,
            superseded_at=c.superseded_at,
            result=c.result,
            server_time=now,
        )


class InstanceOut(BaseModel):
    id: UUID
    name: str
    engine: str  # type de moteur (table `engines`)
    desired_mode: Literal["paper", "live"]  # voulu, fixé à la création (I3)
    desired_state: Literal["running", "exits_only", "stopped"]  # voulu
    state: Observed[ObservedState]  # observé
    observed_mode: Observed[ObservedMode]  # observé
    mode_mismatch: bool  # mode observé connu et différent du mode voulu (I3)
    active_command: CommandOut | None  # commande non terminale la plus récente
    created_at: AwareDatetime
    server_time: AwareDatetime

    @classmethod
    def of(
        cls,
        i: Instance,
        kind: str,
        active: Command | None,
        now: datetime,
        stale_after_s: float,
    ) -> InstanceOut:
        # `unknown` : jamais la dernière valeur connue présentée comme actuelle.
        state = cast(ObservedState, i.observed_state if i.observed_at is not None else "unknown")
        mode = cast(
            ObservedMode, i.observed_mode if i.observed_mode and i.observed_at else "unknown"
        )
        return cls(
            id=i.id,
            name=i.name,
            engine=kind,
            desired_mode=i.mode,
            desired_state=i.desired_state,
            state=observe(state, i.observed_at, now, stale_after_s),
            observed_mode=observe(mode, i.observed_at, now, stale_after_s),
            mode_mismatch=mode != "unknown" and mode != i.mode,
            active_command=None if active is None else CommandOut.of(active, now),
            created_at=i.created_at,
            server_time=now,
        )


MAX_PARAMS_CHARS = 4096  # JSON des paramètres d'une instance : stocké, audité, rendu au moteur


class InstanceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    # Absent : le serveur prend l'unique moteur enregistré (aucun écran ne nomme un moteur, §7).
    engine: str | None = Field(
        default=None, min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_-]*$"
    )
    mode: Literal["paper"] = "paper"  # le passage en live suit la procédure de promotion (F1)
    params: dict[str, Any] = Field(default_factory=dict, max_length=32)  # transmis à l'adaptateur
    # Création depuis le registre : les deux ensemble, ou aucun (création simulée de M1).
    strategy_version_id: UUID | None = None
    account_id: UUID | None = None

    @model_validator(mode="after")
    def _registry_pair(self) -> Self:
        if (self.strategy_version_id is None) != (self.account_id is None):
            raise ValueError("strategy_version_id et account_id vont ensemble")
        return self

    @field_validator("params")
    @classmethod
    def _bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        # `max_length` ne compte que les clés : on borne aussi ce qu'elles contiennent.
        if len(json.dumps(value)) > MAX_PARAMS_CHARS:
            raise ValueError("paramètres trop volumineux")
        return value


class StrategyRef(BaseModel):
    version_id: UUID
    strategy_id: UUID
    name: str
    version: int
    status: str
    code_hash: str
    exits: dict[str, Any]  # politique de sortie de la version (F10)


class AccountRef(BaseModel):
    """Jamais de référence de secret (I12)."""

    id: UUID
    venue: str
    type: str
    environment: str
    label: str
    currency: str


class DriftItem(BaseModel):
    key: str
    expected: Any
    observed: Any


class InstanceDetail(InstanceOut):
    strategy: StrategyRef | None  # None : instance sans version de registre (création simulée)
    account: AccountRef | None
    deployment_fingerprint: str | None  # calculé par la plateforme (I10)
    config_hash: str | None
    # Version que le moteur déclare, relue (F9) : value None = jamais observée, donc « inconnue ».
    engine_version: Observed[str | None]
    # Relues dans le moteur : value None = jamais observé, donc « inconnu » (I1).
    effective_config: Observed[dict[str, Any] | None]
    drift: Observed[list[DriftItem] | None]  # liste vide : aucune dérive constatée


class CommandAccepted(BaseModel):
    command_id: UUID
    command: CommandOut


class EventOut(BaseModel):
    id: UUID
    ts: AwareDatetime  # heure du moteur
    ts_ingest: AwareDatetime  # heure de réception
    type: str
    instance_id: UUID
    seq: int
    correlation_id: UUID | None
    payload: dict[str, Any]  # décimaux en chaînes (enveloppe canonique)

    @classmethod
    def of(cls, e: Event) -> EventOut:
        return cls(
            id=e.id,
            ts=e.ts,
            ts_ingest=e.ts_ingest,
            type=e.type,
            instance_id=e.instance_id,
            seq=e.seq,
            correlation_id=e.correlation_id,
            payload=e.payload,
        )


class AlertOut(BaseModel):
    id: UUID
    rule: str
    severity: str
    target_kind: str
    target_id: UUID | None
    status: str
    message: str
    correlation_id: UUID | None
    invariant: str | None
    created_at: AwareDatetime
    acknowledged_at: AwareDatetime | None
    resolved_at: AwareDatetime | None

    @classmethod
    def of(cls, a: Alert) -> AlertOut:
        return cls.model_validate(a, from_attributes=True)


class AuditOut(BaseModel):
    seq: int
    ts: AwareDatetime
    actor: str
    action: str
    target: str
    before_hash: str | None
    after_hash: str | None
    ip: str | None


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None  # à repasser tel quel ; None : fin de la liste
    server_time: AwareDatetime


def encode_cursor(ts: datetime | int, ident: UUID | None = None) -> str:
    raw = f"{ts.isoformat() if isinstance(ts, datetime) else ts}|{ident or ''}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        head, ident = raw.split("|", 1)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Curseur invalide.") from None
    return head, ident
