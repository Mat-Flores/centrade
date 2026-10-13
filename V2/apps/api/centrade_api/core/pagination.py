"""Pagination par curseur opaque, du plus récent au plus ancien.

Le client repasse `next_cursor` tel quel. Un curseur illisible vaut 422, jamais une liste vide.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel


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


def page_args(cursor: str | None) -> tuple[datetime, UUID] | None:
    """Curseur d'une liste triée par (date, identifiant) ; None : première page."""
    if cursor is None:
        return None
    head, ident = decode_cursor(cursor)
    try:
        return datetime.fromisoformat(head), UUID(ident)
    except ValueError:
        raise HTTPException(422, "Curseur invalide.") from None
