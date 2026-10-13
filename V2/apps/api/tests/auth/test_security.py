"""Primitives : argon2id, AES-256-GCM lié à l'utilisateur, TOTP, codes de récupération, débit."""

from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from centrade_api.auth import security, throttle
from centrade_core.ids import uuid7
from cryptography.exceptions import InvalidTag

KEY = bytes(range(32))
SECRET = "JBSWY3DPEHPK3PXP"  # noqa: S105  # exemple public de la RFC, pas un secret
NOW = datetime(2026, 10, 10, 12, 0, 15, tzinfo=UTC)
FULLWIDTH = "".join(chr(0xFF10 + d) for d in range(1, 7))  # chiffres pleine chasse


def test_password_is_hashed_with_argon2id_and_verified() -> None:
    hashed = security.hash_password("SENTINELLE-a")

    assert hashed.startswith("$argon2id$")
    assert "SENTINELLE-a" not in hashed
    assert security.verify_password(hashed, "SENTINELLE-a") is True
    assert security.verify_password(hashed, "SENTINELLE-b") is False


@pytest.mark.parametrize("stored", [None, "", "pas-une-empreinte", "$argon2id$tronquee"])
def test_missing_or_unreadable_hash_never_verifies(stored: str | None) -> None:
    assert security.verify_password(stored, "SENTINELLE-a") is False
    assert security.verify_password(stored, "") is False


def test_dummy_hash_never_verifies_even_with_its_own_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(security, "_DUMMY_HASH", security.hash_password("SENTINELLE-factice"))

    assert security.verify_password(None, "SENTINELLE-factice") is False


def test_totp_secret_is_encrypted_with_unique_nonce_and_bound_to_user() -> None:
    user, other = uuid7(), uuid7()

    nonce, ciphertext = security.encrypt_totp_secret(master_key=KEY, user_id=user, secret=SECRET)
    nonce2, ciphertext2 = security.encrypt_totp_secret(master_key=KEY, user_id=user, secret=SECRET)

    assert len(nonce) == 12 and nonce != nonce2 and ciphertext != ciphertext2
    assert SECRET.encode() not in ciphertext
    assert (
        security.decrypt_totp_secret(
            master_key=KEY, user_id=user, nonce=nonce, ciphertext=ciphertext
        )
        == SECRET
    )
    # Un chiffré recopié sur un autre compte, une autre clé ou un octet altéré : refus.
    for kwargs in (
        {"master_key": KEY, "user_id": other, "nonce": nonce, "ciphertext": ciphertext},
        {"master_key": bytes(32), "user_id": user, "nonce": nonce, "ciphertext": ciphertext},
        {"master_key": KEY, "user_id": user, "nonce": nonce2, "ciphertext": ciphertext},
        {"master_key": KEY, "user_id": user, "nonce": nonce, "ciphertext": ciphertext[:-1] + b"!"},
    ):
        with pytest.raises(InvalidTag):
            security.decrypt_totp_secret(**kwargs)  # type: ignore[arg-type]


def test_master_key_of_wrong_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="32 octets"):
        security.encrypt_totp_secret(master_key=bytes(16), user_id=uuid7(), secret=SECRET)
    with pytest.raises(ValueError, match="32 octets"):
        security.decrypt_totp_secret(
            master_key=b"", user_id=uuid7(), nonce=bytes(12), ciphertext=bytes(32)
        )


def test_totp_step_is_accepted_within_one_step_and_returned() -> None:
    totp = pyotp.TOTP(SECRET)
    step = totp.timecode(NOW)

    assert security.totp_step(SECRET, totp.at(NOW), NOW) == step
    assert security.totp_step(SECRET, totp.at(NOW, -1), NOW) == step - 1
    assert security.totp_step(SECRET, totp.at(NOW, 1), NOW) == step + 1
    assert security.totp_step(SECRET, totp.at(NOW, -2), NOW) is None
    assert security.totp_step(SECRET, totp.at(NOW, 2), NOW) is None


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef", FULLWIDTH, "12 456", "-12345"])
def test_malformed_totp_code_is_rejected(code: str) -> None:
    assert security.totp_step(SECRET, code, NOW) is None


def test_recovery_codes_are_random_and_hashed() -> None:
    codes = security.new_recovery_codes()

    assert len(codes) == len(set(codes)) == 10
    assert all(len(c.replace("-", "")) == 16 for c in codes)  # 80 bits : hors de portée hors ligne
    assert codes != security.new_recovery_codes()
    hashed = security.recovery_code_hash(codes[0])
    assert codes[0] not in hashed and len(hashed) == 64
    assert security.recovery_code_hash(f" {codes[0].lower().replace('-', ' ')} ") == hashed
    assert security.recovery_code_hash(codes[1]) != hashed


def test_session_tokens_are_random_and_hashed() -> None:
    token = security.new_token()

    assert token != security.new_token()
    assert len(token) >= 43
    assert token not in security.token_hash(token)


def test_lockout_duration_is_progressive_and_capped() -> None:
    minutes = [throttle.lock_duration(n) for n in range(4, 11)]

    assert minutes[0] is None  # pas avant le 5e échec
    assert minutes[1:] == [timedelta(minutes=m) for m in (1, 2, 4, 8, 15, 15)]
    assert throttle.lock_duration(10**9) == timedelta(minutes=15)  # ni débordement ni verrou infini


def test_rate_limiter_uses_a_fixed_window_per_key() -> None:
    limiter = throttle.RateLimiter(limit=2, window=timedelta(seconds=60))

    assert limiter.retry_after("a", NOW) is None
    assert limiter.retry_after("a", NOW + timedelta(seconds=10)) is None
    assert limiter.retry_after("a", NOW + timedelta(seconds=20)) == 40
    assert limiter.retry_after("b", NOW + timedelta(seconds=20)) is None  # clés indépendantes
    assert limiter.retry_after("a", NOW + timedelta(seconds=60)) is None  # nouvelle fenêtre


def test_rate_limiter_does_not_grow_without_bound() -> None:
    limiter = throttle.RateLimiter(limit=1, window=timedelta(seconds=60))

    for n in range(throttle.RateLimiter.MAX_KEYS + 50):
        limiter.retry_after(f"ip-{n}", NOW)
    limiter.retry_after("tard", NOW + timedelta(seconds=61))

    assert limiter.size() <= throttle.RateLimiter.MAX_KEYS
