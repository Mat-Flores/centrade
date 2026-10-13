"""SecretStore (SPEC §5, F6, I12) : interface et implémentation V1, AES-256-GCM.

Ce module chiffre ; il ne déchiffre aucune ligne de `secrets`. Le déchiffrement des secrets
d'usage `trade`, `read`, `engine_api` et `webhook` vit dans `centrade_worker.secrets`, que l'API
n'importe pas (tests/invariants/test_i12_frontiere_dechiffrement.py). Seul le secret TOTP, dont
l'API a besoin pour vérifier un code, se déchiffre ici, et son AAD n'ouvre rien d'autre.

Une valeur en clair circule en `pydantic.SecretStr` : `repr`, `str` et la sérialisation la
masquent.

Source (cryptography 50, uv.lock) :
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
# Version de la clé maître, écrite sur chaque ligne. Une version inconnue ne se déchiffre pas.
KEY_VERSION = 1
# Plus long que l'AAD du TOTP (16 octets) : les deux domaines ne se recouvrent jamais.
_AAD_PREFIX = b"centrade.secret.v1"


def cipher(master_key: bytes) -> AESGCM:
    if len(master_key) != 32:  # AESGCM accepterait 16 ou 24 octets : on exige AES-256
        raise ValueError("la clé maître doit faire 32 octets")
    return AESGCM(master_key)


def secret_aad(secret_id: UUID, usage: str, owner: UUID) -> bytes:
    """Lie le chiffré à sa ligne, à son usage et à son propriétaire (compte ou instance)."""
    if usage not in get_args(Usage):
        raise ValueError("usage de secret inconnu")
    return _AAD_PREFIX + secret_id.bytes + owner.bytes + usage.encode()


def _seal(aes: AESGCM, aad: bytes, data: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)  # neuf à chaque chiffrement, jamais fourni par l'appelant
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
    """Renvoie (nonce, chiffré)."""
    return _encrypt(cipher(master_key), secret_id, usage, owner, value)


def encrypt_totp_secret(*, master_key: bytes, user_id: UUID, secret: str) -> tuple[bytes, bytes]:
    """Renvoie (nonce, chiffré). AAD de M1 conservé (l'utilisateur) : les lignes existantes
    restent lisibles."""
    return _seal(cipher(master_key), user_id.bytes, secret.encode())


def decrypt_totp_secret(
    *, master_key: bytes, user_id: UUID, nonce: bytes, ciphertext: bytes
) -> str:
    """Lève `InvalidTag` si la clé, le nonce, le chiffré ou l'utilisateur ne correspondent pas."""
    return cipher(master_key).decrypt(nonce, ciphertext, user_id.bytes).decode()


class SecretStore(Protocol):
    """Écriture seule. `owner` : le compte d'une clé de venue, l'instance d'un identifiant de
    moteur. Les écritures se font dans la transaction de l'appelant, qui commit."""

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
        """Chiffre et stocke. Renvoie la référence du secret."""

    async def rotate(
        self,
        session: AsyncSession,
        secret_id: UUID,
        *,
        owner: UUID,
        value: SecretStr,
        now: datetime,
    ) -> UUID:
        """Stocke le successeur de `secret_id` (même usage, même genre) et renvoie sa référence.
        L'ancien reste en place : l'appelant bascule, puis le révoque."""

    async def revoke(self, session: AsyncSession, secret_id: UUID) -> None:
        """Détruit le chiffré. La révocation sur la venue se fait avant, par l'opérateur."""


class AesGcmSecretStore:
    def __init__(self, master_key: bytes) -> None:
        self._aes = cipher(master_key)  # la clé elle-même n'est pas gardée en attribut

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
