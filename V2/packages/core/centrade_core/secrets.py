"""SecretStore (SPEC §5, F6, I12): interface and V1 implementation, AES-256-GCM.

This module encrypts; it decrypts no `secrets` row. Decryption of secrets with usage
`trade`, `read`, `engine_api` and `webhook` lives in `centrade_worker.secrets`, which the API
does not import (tests/invariants/test_i12_frontiere_dechiffrement.py). Only the TOTP secret,
which the API needs to verify a code, is decrypted here, and its AAD opens nothing else.

A plaintext value travels as `pydantic.SecretStr`: `repr`, `str` and serialization
mask it.

Source (cryptography 50, uv.lock):
https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM
"""

import os
from datetime import datetime
from typing import Literal, Protocol, get_args
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from centrade_core.ids import uuid7
from centrade_core.models.trading import Secret

Usage = Literal["trade", "read", "engine_api", "webhook"]
# Master key version, written on every row. An unknown version does not decrypt.
KEY_VERSION = 1
# Longer than the TOTP AAD (16 bytes): the two domains never overlap.
_AAD_PREFIX = b"centrade.secret.v1"


def cipher(master_key: bytes) -> AESGCM:
    if len(master_key) != 32:  # AESGCM would accept 16 or 24 bytes: we require AES-256
        raise ValueError("la clé maître doit faire 32 octets")
    return AESGCM(master_key)


def secret_aad(secret_id: UUID, usage: str, owner: UUID) -> bytes:
    """Binds the ciphertext to its row, its usage and its owner (account or instance)."""
    if usage not in get_args(Usage):
        raise ValueError("usage de secret inconnu")
    return _AAD_PREFIX + secret_id.bytes + owner.bytes + usage.encode()


def _seal(aes: AESGCM, aad: bytes, data: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)  # new for every encryption, never supplied by the caller
    return nonce, aes.encrypt(nonce, data, aad)


def _encrypt(
    aes: AESGCM, secret_id: UUID, usage: Usage, owner: UUID, value: SecretStr
) -> tuple[bytes, bytes]:
    plain = value.get_secret_value()
    if not plain:
        raise ValueError("secret vide refusé")
    return _seal(aes, secret_aad(secret_id, usage, owner), plain.encode())


def encrypt_secret(
    master_key: bytes, *, secret_id: UUID, usage: Usage, owner: UUID, value: SecretStr
) -> tuple[bytes, bytes]:
    """Returns (nonce, ciphertext)."""
    return _encrypt(cipher(master_key), secret_id, usage, owner, value)


def encrypt_totp_secret(*, master_key: bytes, user_id: UUID, secret: str) -> tuple[bytes, bytes]:
    """Returns (nonce, ciphertext). M1 AAD kept (the user): existing rows
    stay readable."""
    return _seal(cipher(master_key), user_id.bytes, secret.encode())


def decrypt_totp_secret(
    *, master_key: bytes, user_id: UUID, nonce: bytes, ciphertext: bytes
) -> str:
    """Raises `InvalidTag` if the key, nonce, ciphertext or user do not match."""
    return cipher(master_key).decrypt(nonce, ciphertext, user_id.bytes).decode()


class SecretStore(Protocol):
    """Write-only. `owner`: the account of a venue key, the instance of an engine
    credential. Writes happen in the caller's transaction, which commits."""

    async def put(
        self,
        session: AsyncSession,
        *,
        usage: Usage,
        kind: str,
        owner: UUID,
        value: SecretStr,
        now: datetime,
    ) -> UUID:
        """Encrypts and stores. Returns the secret's reference."""

    async def rotate(
        self,
        session: AsyncSession,
        secret_id: UUID,
        *,
        owner: UUID,
        value: SecretStr,
        now: datetime,
    ) -> UUID:
        """Stores the successor of `secret_id` (same usage, same kind) and returns its reference.
        The old one stays in place: the caller switches over, then revokes it."""

    async def revoke(self, session: AsyncSession, secret_id: UUID) -> None:
        """Destroys the ciphertext. Revocation on the venue happens beforehand, by the operator."""


class AesGcmSecretStore:
    def __init__(self, master_key: bytes) -> None:
        self._aes = cipher(master_key)  # the key itself is not kept as an attribute

    async def _store(
        self,
        session: AsyncSession,
        usage: Usage,
        kind: str,
        owner: UUID,
        value: SecretStr,
        now: datetime,
        rotated_at: datetime | None,
    ) -> UUID:
        secret_id = uuid7()
        nonce, ciphertext = _encrypt(self._aes, secret_id, usage, owner, value)
        session.add(
            Secret(
                id=secret_id,
                kind=kind,
                usage=usage,
                ciphertext=ciphertext,
                nonce=nonce,
                key_version=KEY_VERSION,
                rotated_at=rotated_at,
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        return secret_id

    async def put(
        self,
        session: AsyncSession,
        *,
        usage: Usage,
        kind: str,
        owner: UUID,
        value: SecretStr,
        now: datetime,
    ) -> UUID:
        return await self._store(session, usage, kind, owner, value, now, None)

    async def rotate(
        self,
        session: AsyncSession,
        secret_id: UUID,
        *,
        owner: UUID,
        value: SecretStr,
        now: datetime,
    ) -> UUID:
        old = await session.get(Secret, secret_id)
        if old is None:
            raise LookupError("secret inconnu")
        return await self._store(session, old.usage, old.kind, owner, value, now, now)  # type: ignore[arg-type]

    async def revoke(self, session: AsyncSession, secret_id: UUID) -> None:
        await session.execute(delete(Secret).where(Secret.id == secret_id))
