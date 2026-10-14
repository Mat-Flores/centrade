"""Tamper-proof audit log (I14): each row is chained to the previous row's fingerprint."""

import hashlib
import ipaddress
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_core.ids import uuid7
from centrade_core.models import AuditLog

GENESIS = "0" * 64
SYSTEM_WORKER = "system:worker"  # author of the worker's actions (I14)
_LOCK_KEY = 0x43454E54  # arbitrary, specific to the audit log


def fingerprint(value: Any) -> str:
    """SHA-256 fingerprint of a state (canonical JSON): the log never keeps the state itself."""
    return hashlib.sha256(_canonical(value)).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _row_hash(e: AuditLog) -> str:
    fields = [e.seq, e.ts.astimezone(UTC).isoformat(), e.actor, e.action, e.target]
    fields += [e.before_hash, e.after_hash, e.ip, e.prev_hash]
    return hashlib.sha256(_canonical(fields)).hexdigest()


async def write_audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    target: str,
    before: Any = None,
    after: Any = None,
    ip: str | None = None,
) -> AuditLog:
    """Appends a row in the caller's transaction.

    The advisory lock is held until the end of this transaction: writes are serialized,
    the chain does not fork. The caller commits right after (do not prolong it).
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    last = (await session.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1))).scalar()
    entry = AuditLog(
        id=uuid7(),
        seq=1 if last is None else last.seq + 1,
        ts=datetime.now(UTC),
        actor=actor,
        action=action,
        target=target,
        before_hash=None if before is None else fingerprint(before),
        after_hash=None if after is None else fingerprint(after),
        ip=None if ip is None else str(ipaddress.ip_address(ip)),
        prev_hash=GENESIS if last is None else last.row_hash,
        row_hash="",
    )
    entry.row_hash = _row_hash(entry)
    session.add(entry)
    await session.flush()
    return entry


async def verify_chain(session: AsyncSession) -> int | None:
    """Returns the `seq` of the first row that breaks the chain, or None if it is intact."""
    prev, expected_seq = GENESIS, 1
    rows = await session.stream_scalars(select(AuditLog).order_by(AuditLog.seq))
    async for e in rows:
        if e.seq != expected_seq or e.prev_hash != prev or e.row_hash != _row_hash(e):
            return e.seq
        prev, expected_seq = e.row_hash, expected_seq + 1
    return None
