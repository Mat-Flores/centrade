"""Authentication primitives. No algorithm choice is left to the caller.

Sources (uv.lock versions):
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

# TOTP secret encryption goes through the SecretStore (same primitive, M1 AAD).
from centrade_core.secrets import decrypt_totp_secret as decrypt_totp_secret
from centrade_core.secrets import encrypt_totp_secret as encrypt_totp_secret

_hasher = PasswordHasher()  # argon2id, library default parameters (RFC 9106)
# Verified when the account does not exist or is locked: same cost, never a success.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))
_TOTP_CODE = re.compile(r"[0-9]{6}", re.ASCII)
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 32 symbols, without I, O, 0, 1
RECOVERY_CODE_COUNT = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """One argon2 computation in every case. Without a readable hash, always False."""
    try:
        verified = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (Argon2Error, InvalidHashError):  # wrong password, or unreadable hash
        return False
    return verified and bool(password_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """SHA-256 is enough: the token carries 256 bits of randomness, nothing to guess offline."""
    return hashlib.sha256(token.encode()).hexdigest()


def is_totp_code(code: str) -> bool:
    return _TOTP_CODE.fullmatch(code) is not None


def totp_step(secret: str, code: str, now: datetime) -> int | None:
    """Time step (30 s) that `code` matches, within one step, or None if refused.

    The caller refuses an already accepted step (anti-replay): pyotp 2.10 does not return the step.
    """
    if not is_totp_code(code):
        return None
    totp = pyotp.TOTP(secret)
    current = totp.timecode(now)
    matched = None
    for offset in (-1, 0, 1):  # the three comparisons always happen, in constant time
        if hmac.compare_digest(totp.at(now, offset), code):
            matched = current + offset
    return matched


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Centrade")


def new_recovery_codes() -> list[str]:
    """80-bit codes, shown once, in the form XXXX-XXXX-XXXX-XXXX."""
    return [
        "-".join("".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4)) for _ in range(4))
        for _ in range(RECOVERY_CODE_COUNT)
    ]


def recovery_code_hash(code: str) -> str:
    """Hash of the normalized code (case, dashes, spaces ignored): the only form in the database."""
    normalized = re.sub(r"[\s-]", "", code).upper()
    return hashlib.sha256(normalized.encode()).hexdigest()


def matching_hash(hashes: list[str], candidate: str) -> str | None:
    """Search without early exit, constant-time comparisons."""
    found = None
    for stored in hashes:
        if hmac.compare_digest(stored, candidate):
            found = stored
    return found
