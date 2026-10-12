"""Vérification de F9 avant d'ouvrir les entrées (SPEC F9, I3, I5, I10). Pure : ni horloge, ni
réseau, ni base. Tout ce qui manque, date ou diverge est un motif de refus ; une liste vide est la
seule façon d'ouvrir les entrées. Ce qui réduit le risque ne passe jamais par ici (I4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from centrade_core.commands import RISK_INCREASING, risk_increase_refusal
from centrade_core.engine.types import Drift, EffectiveConfig, InstanceSpec, InstanceStatus

# Motifs : `mode`, `drift` et `fingerprint` sont des écarts constatés ; les autres, un doute.
MODE: Final = "mode"
DRIFT: Final = "drift"
FINGERPRINT: Final = "fingerprint"
UNKNOWN: Final = "unknown"
STALE: Final = "stale"
STATE: Final = "state"
LIVE: Final = "live"
ERROR: Final = "error"
# Écart constaté : alerte, et pause des entrées si le moteur est observé `running`.
FOUND: Final = frozenset({MODE, DRIFT, FINGERPRINT})
CRITICAL: Final = frozenset({MODE, DRIFT})  # F9 : écart de mode, dérive de configuration
# Seules commandes soumises à un contrôle avant l'envoi ; toutes les autres partent sans lui.
GATED: Final = RISK_INCREASING | {"deploy"}


@dataclass(frozen=True)
class Refusal:
    code: str
    message: str


def _fresh(at: datetime, now: datetime, stale_after_s: float) -> bool:
    # Trop vieux ou daté du futur (dérive d'horloge) : dans les deux cas, on ne sait pas.
    return abs(now - at) <= timedelta(seconds=stale_after_s)


def entry_refusals(
    *,
    spec: InstanceSpec,
    status: InstanceStatus | None,
    effective: EffectiveConfig | None,
    drifts: tuple[Drift, ...] | None,
    recorded_fingerprint: str | None,
    now: datetime,
    stale_after_s: float,
) -> tuple[Refusal, ...]:
    """Motifs de refus d'ouvrir les entrées. `spec` vient du registre à l'instant du contrôle,
    `recorded_fingerprint` de l'enregistrement fait au déploiement, le reste du moteur.
    `drifts` : résultat de `owned_drifts` ; None si la comparaison n'a pas pu se faire."""
    out: list[Refusal] = []
    if spec.mode != "paper":
        # F9 point 5 (permissions, IP, solde, politique de sortie) : avec la promotion, M7.
        out.append(Refusal(LIVE, "Aucune promotion en live n'existe encore : entrées refusées."))
    # F9 point 4 (kill switch inactif, état de risque à jour) : avec le Risk service, M3.
    if status is None or status.state == "unknown":
        out.append(Refusal(UNKNOWN, "L'état observé est inconnu."))
    else:
        if not _fresh(status.observed_at, now, stale_after_s):
            out.append(Refusal(STALE, "L'état observé est périmé."))
        if status.mode is None:
            out.append(Refusal(UNKNOWN, "Le mode effectif du moteur est inconnu."))
        elif status.mode != spec.mode:
            out.append(
                Refusal(
                    MODE,
                    f"Le mode effectif du moteur ({status.mode}) n'est pas celui de l'instance "
                    f"({spec.mode}).",
                )
            )
    if effective is None or drifts is None:
        out.append(Refusal(UNKNOWN, "La configuration effective n'a pas pu être relue : inconnu."))
        return tuple(out)
    if not _fresh(effective.observed_at, now, stale_after_s):
        out.append(Refusal(STALE, "La configuration relue est périmée."))
    if drifts:
        keys = ", ".join(sorted(d.key for d in drifts))
        out.append(Refusal(DRIFT, f"Dérive de configuration sur les clés possédées : {keys}."))
    dep = spec.deployment
    if dep is None or not recorded_fingerprint or dep.fingerprint != recorded_fingerprint:
        out.append(
            Refusal(
                FINGERPRINT,
                "Le registre ne décrit plus ce qui a été déployé (code, paramètres, sorties, "
                "image ou configuration) : empreinte différente (I10).",
            )
        )
    elif effective.fingerprint != recorded_fingerprint:
        out.append(
            Refusal(FINGERPRINT, "Ce qui tourne ne porte pas l'empreinte du déploiement (I10).")
        )
    elif effective.engine_version != dep.engine_version:
        out.append(
            Refusal(FINGERPRINT, "La version du moteur n'est pas celle de l'empreinte (I10).")
        )
    return tuple(out)


def command_refusals(
    command_type: str,
    *,
    mode: str,
    status: InstanceStatus | None,
    entries: tuple[Refusal, ...] | None,
    now: datetime,
    stale_after_s: float,
) -> tuple[Refusal, ...]:
    """Motifs de refus d'envoyer une commande. Vide pour tout ce qui n'augmente pas le risque,
    quelles que soient les autres entrées (I4). `entries` : `entry_refusals`, exigé pour
    `resume_entries` (None : vérification non faite, donc refus)."""
    if command_type not in GATED:
        return ()
    if mode != "paper":
        return (Refusal(LIVE, "Aucune promotion en live n'existe encore : commande refusée."),)
    if command_type == "deploy":
        return ()
    if command_type == "resume_entries":
        if entries is None:
            return (Refusal(UNKNOWN, "La vérification de F9 n'a pas eu lieu : inconnu."),)
        if entries:
            return entries
    base = risk_increase_refusal(
        command_type,
        mode=mode,
        observed_state="unknown" if status is None else status.state,
        observed_mode=None if status is None else status.mode,
        observed_at=None if status is None else status.observed_at,
        now=now,
        stale_after_s=stale_after_s,
    )
    return () if base is None else (Refusal(STATE, base),)
