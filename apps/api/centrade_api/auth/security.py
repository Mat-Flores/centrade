"""Primitives d'authentification. Aucun choix d'algorithme n'est laissé à l'appelant.

Sources (versions de uv.lock) :
- argon2-cffi 25.1 : https://argon2-cffi.readthedocs.io/en/stable/api.html
- pyotp 2.10 : https://pyauth.github.io/pyotp/
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

# Le chiffrement du secret TOTP passe par le SecretStore (même primitive, AAD de M1).
from centrade_core.secrets import decrypt_totp_secret as decrypt_totp_secret
from centrade_core.secrets import encrypt_totp_secret as encrypt_totp_secret

_hasher = PasswordHasher()  # argon2id, paramètres par défaut de la bibliothèque (RFC 9106)
# Vérifiée quand le compte n'existe pas ou est verrouillé : même coût, jamais de succès.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))
_TOTP_CODE = re.compile(r"[0-9]{6}", re.ASCII)
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 32 signes, sans I, O, 0, 1
RECOVERY_CODE_COUNT = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Un calcul argon2 dans tous les cas. Sans empreinte lisible, toujours False."""
    try:
        verified = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (Argon2Error, InvalidHashError):  # mot de passe faux, ou empreinte illisible
        return False
    return verified and bool(password_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """SHA-256 suffit : le jeton porte 256 bits d'aléa, il n'y a rien à deviner hors ligne."""
    return hashlib.sha256(token.encode()).hexdigest()


def totp_step(secret: str, code: str, now: datetime) -> int | None:
    """Pas de temps (30 s) auquel `code` correspond, à un pas près, ou None s'il est refusé.

    L'appelant refuse un pas déjà accepté (anti-rejeu) : pyotp 2.10 ne renvoie pas le pas.
    """
    if not _TOTP_CODE.fullmatch(code):
        return None
    totp = pyotp.TOTP(secret)
    current = totp.timecode(now)
    matched = None
    for offset in (-1, 0, 1):  # les trois comparaisons ont toujours lieu, en temps constant
        if hmac.compare_digest(totp.at(now, offset), code):
            matched = current + offset
    return matched


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Centrade")


def new_recovery_codes() -> list[str]:
    """Codes de 80 bits, affichés une fois, sous la forme XXXX-XXXX-XXXX-XXXX."""
    return [
        "-".join("".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4)) for _ in range(4))
        for _ in range(RECOVERY_CODE_COUNT)
    ]


def recovery_code_hash(code: str) -> str:
    """Empreinte du code normalisé (casse, tirets et espaces ignorés) : seule forme en base."""
    normalized = re.sub(r"[\s-]", "", code).upper()
    return hashlib.sha256(normalized.encode()).hexdigest()


def matching_hash(hashes: list[str], candidate: str) -> str | None:
    """Recherche sans sortie anticipée, comparaisons en temps constant."""
    found = None
    for stored in hashes:
        if hmac.compare_digest(stored, candidate):
            found = stored
    return found
