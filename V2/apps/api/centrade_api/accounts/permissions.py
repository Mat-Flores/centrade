"""Permissions of an exchange key (SPEC F6, I5, I11).

The probe receives a secret reference, never its value, and exposes no order function.
Refuse by default: a key whose test does not complete is not verified, which blocks live.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

import structlog

log = structlog.get_logger()

KeyUsage = Literal["trade", "read"]  # `engine_api` and `webhook` are not entered here
Verdict = Literal["verified", "refused", "unverified"]
PROBE_TIMEOUT_S = 10.0


@dataclass(frozen=True, slots=True)
class KeyPermissions:
    """What the venue says about a key. None: the venue did not say."""

    trading: bool | None
    withdrawal: bool | None
    ip_restricted: bool | None


class PermissionProbe(Protocol):
    """Reads the permissions of a stored key. No order function (I11)."""

    async def permissions(self, secret_id: UUID) -> KeyPermissions: ...


class UnverifiedProbe:
    """No real venue in this environment (SPEC §0.10): nothing is observed."""

    async def permissions(self, secret_id: UUID) -> KeyPermissions:
        return KeyPermissions(trading=None, withdrawal=None, ip_restricted=None)


def get_permission_probe() -> PermissionProbe:
    return UnverifiedProbe()


def verdict(perms: KeyPermissions, usage: KeyUsage) -> Verdict:
    """Trading key: trading allowed and withdrawal forbidden. Read key: neither one.
    Withdrawal possible: refuse. Incomplete response: not verified."""
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
    """Returns (verdict, observed IP restriction). Error or timeout: not verified."""
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_S):
            perms = await probe.permissions(secret_id)
    except Exception as exc:  # a venue error message may carry a key: type only
        log.warning("account_probe_failed", error=type(exc).__name__)
        return "unverified", None
    result = verdict(perms, usage)
    ip = perms.ip_restricted if result == "verified" else None
    return result, ip if isinstance(ip, bool) else None
