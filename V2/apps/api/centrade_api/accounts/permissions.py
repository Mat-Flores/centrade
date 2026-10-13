"""Droits d'une clé d'exchange (SPEC F6, I5, I11).

La sonde reçoit une référence de secret, jamais sa valeur, et n'expose aucune fonction d'ordre.
Refus par défaut : une clé dont le test n'aboutit pas n'est pas vérifiée, ce qui bloque le live.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

import structlog

log = structlog.get_logger()

KeyUsage = Literal["trade", "read"]  # `engine_api` et `webhook` ne se saisissent pas ici
Verdict = Literal["verified", "refused", "unverified"]
PROBE_TIMEOUT_S = 10.0


@dataclass(frozen=True, slots=True)
class KeyPermissions:
    """Ce que la venue dit d'une clé. None : la venue ne l'a pas dit."""

    trading: bool | None
    withdrawal: bool | None
    ip_restricted: bool | None


class PermissionProbe(Protocol):
    """Lecture des permissions d'une clé stockée. Aucune fonction d'ordre (I11)."""

    async def permissions(self, secret_id: UUID) -> KeyPermissions: ...


class UnverifiedProbe:
    """Aucune venue réelle dans cet environnement (SPEC §0.10) : rien n'est constaté."""

    async def permissions(self, secret_id: UUID) -> KeyPermissions:
        return KeyPermissions(trading=None, withdrawal=None, ip_restricted=None)


def get_permission_probe() -> PermissionProbe:
    return UnverifiedProbe()


def verdict(perms: KeyPermissions, usage: KeyUsage) -> Verdict:
    """Clé de trading : trading autorisé et retrait interdit. Clé de lecture : ni l'un ni
    l'autre. Retrait possible : refus. Réponse incomplète : non vérifié."""
    if not isinstance(perms, KeyPermissions):
        return "unverified"
    if perms.withdrawal is True:
        return "refused"
    if not isinstance(perms.trading, bool) or perms.withdrawal is not False:
        return "unverified"
    return "verified" if perms.trading is (usage == "trade") else "refused"


async def run_probe(
    probe: PermissionProbe, secret_id: UUID, usage: KeyUsage
) -> tuple[Verdict, bool | None]:
    """Rend (verdict, restriction d'IP constatée). Erreur ou délai dépassé : non vérifié."""
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_S):
            perms = await probe.permissions(secret_id)
    except Exception as exc:  # le message d'une erreur de venue peut porter une clé : type seul
        log.warning("account_probe_failed", error=type(exc).__name__)
        return "unverified", None
    result = verdict(perms, usage)
    ip = perms.ip_restricted if result == "verified" else None
    return result, ip if isinstance(ip, bool) else None
