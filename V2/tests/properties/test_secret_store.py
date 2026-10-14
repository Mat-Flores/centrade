"""SecretStore V1 (AES-256-GCM): encryption properties. Sentinel values only."""

import json
from uuid import UUID

import pytest
from centrade_core import secrets as core
from centrade_worker import secrets as worker
from cryptography.exceptions import InvalidTag
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, SecretStr

KEY = bytes(range(32))
USAGES: tuple[core.Usage, ...] = ("trade", "read", "engine_api", "webhook")
values = st.text(min_size=1, max_size=200)
usages = st.sampled_from(USAGES)


def _open(nonce: bytes, ciphertext: bytes, **over: object) -> SecretStr:
    args: dict[str, object] = {
        "secret_id": UUID(int=1),
        "usage": "trade",
        "owner": UUID(int=2),
        "key_version": core.KEY_VERSION,
    }
    return worker.open_secret(KEY, nonce=nonce, ciphertext=ciphertext, **{**args, **over})  # type: ignore[arg-type]


@given(value=values, secret_id=st.uuids(), owner=st.uuids(), usage=usages)
def test_encrypt_decrypt_roundtrip(
    value: str, secret_id: UUID, owner: UUID, usage: core.Usage
) -> None:
    nonce, ct = core.encrypt_secret(
        KEY, secret_id=secret_id, usage=usage, owner=owner, value=SecretStr(value)
    )
    out = worker.open_secret(
        KEY,
        secret_id=secret_id,
        usage=usage,
        owner=owner,
        key_version=core.KEY_VERSION,
        nonce=nonce,
        ciphertext=ct,
    )
    assert out.get_secret_value() == value
    assert len(nonce) == 12


@given(value=values)
def test_two_encryptions_of_the_same_value_differ(value: str) -> None:
    args = {"secret_id": UUID(int=1), "usage": "trade", "owner": UUID(int=2)}
    a = core.encrypt_secret(KEY, value=SecretStr(value), **args)  # type: ignore[arg-type]
    b = core.encrypt_secret(KEY, value=SecretStr(value), **args)  # type: ignore[arg-type]
    assert a[0] != b[0] and a[1] != b[1]


@given(value=values, data=st.data())
def test_tampered_ciphertext_or_nonce_is_rejected(value: str, data: st.DataObject) -> None:
    nonce, ct = core.encrypt_secret(
        KEY, secret_id=UUID(int=1), usage="trade", owner=UUID(int=2), value=SecretStr(value)
    )
    target = data.draw(st.sampled_from(("nonce", "ct")))
    raw = bytearray(nonce if target == "nonce" else ct)
    raw[data.draw(st.integers(0, len(raw) - 1))] ^= data.draw(st.integers(1, 255))
    with pytest.raises(InvalidTag):
        _open(bytes(raw), ct) if target == "nonce" else _open(nonce, bytes(raw))
    with pytest.raises(InvalidTag):  # truncated ciphertext: never a partial value
        _open(nonce, ct[: data.draw(st.integers(0, len(ct) - 1))])


@given(value=values, other=st.uuids().filter(lambda u: u.int > 2), usage=usages)
def test_ciphertext_replayed_elsewhere_is_rejected(
    value: str, other: UUID, usage: core.Usage
) -> None:
    """Different identifier, different use or different owner: the AAD no longer matches."""
    nonce, ct = core.encrypt_secret(
        KEY, secret_id=UUID(int=1), usage="trade", owner=UUID(int=2), value=SecretStr(value)
    )
    replays: list[dict[str, object]] = [{"secret_id": other}, {"owner": other}]
    if usage != "trade":
        replays.append({"usage": usage})
    for over in replays:
        with pytest.raises(InvalidTag):
            _open(nonce, ct, **over)
    with pytest.raises(InvalidTag):  # another master key
        worker.open_secret(
            bytes(32),
            secret_id=UUID(int=1),
            usage="trade",
            owner=UUID(int=2),
            key_version=core.KEY_VERSION,
            nonce=nonce,
            ciphertext=ct,
        )


@given(size=st.integers(0, 64).filter(lambda n: n != 32))
def test_wrong_key_length_is_rejected(size: int) -> None:
    with pytest.raises(ValueError, match="32 octets"):
        core.encrypt_secret(
            bytes(size),
            secret_id=UUID(int=1),
            usage="trade",
            owner=UUID(int=2),
            value=SecretStr("x"),
        )
    with pytest.raises(ValueError, match="32 octets"):
        worker.open_secret(
            bytes(size),
            secret_id=UUID(int=1),
            usage="trade",
            owner=UUID(int=2),
            key_version=core.KEY_VERSION,
            nonce=bytes(12),
            ciphertext=bytes(32),
        )
    with pytest.raises(ValueError, match="32 octets"):
        core.AesGcmSecretStore(bytes(size))


@given(version=st.integers().filter(lambda v: v != core.KEY_VERSION))
def test_unknown_key_version_is_rejected(version: int) -> None:
    nonce, ct = core.encrypt_secret(
        KEY, secret_id=UUID(int=1), usage="trade", owner=UUID(int=2), value=SecretStr("x")
    )
    with pytest.raises(ValueError, match="version de clé"):
        _open(nonce, ct, key_version=version)


def test_empty_value_or_unknown_usage_is_rejected() -> None:
    args = {"secret_id": UUID(int=1), "owner": UUID(int=2)}
    with pytest.raises(ValueError, match="vide"):
        core.encrypt_secret(KEY, usage="trade", value=SecretStr(""), **args)
    with pytest.raises(ValueError, match="usage"):
        core.encrypt_secret(KEY, usage="autre", value=SecretStr("x"), **args)  # type: ignore[arg-type]


@given(user=st.uuids(), secret=values)
def test_totp_and_secrets_cannot_decrypt_each_other(user: UUID, secret: str) -> None:
    """TOTP decryption, the only one accessible to the API, opens no row of `secrets`."""
    for usage in USAGES:
        nonce, ct = core.encrypt_secret(
            KEY, secret_id=user, usage=usage, owner=user, value=SecretStr(secret)
        )
        with pytest.raises(InvalidTag):
            core.decrypt_totp_secret(master_key=KEY, user_id=user, nonce=nonce, ciphertext=ct)
    nonce, ct = core.encrypt_totp_secret(master_key=KEY, user_id=user, secret=secret)
    assert (
        core.decrypt_totp_secret(master_key=KEY, user_id=user, nonce=nonce, ciphertext=ct) == secret
    )
    with pytest.raises(InvalidTag):
        _open(nonce, ct, secret_id=user, owner=user)


def test_plaintext_value_leaks_neither_via_repr_nor_serialization() -> None:
    sentinel = "TEST-SECRET-DO-NOT-USE-repr"
    nonce, ct = core.encrypt_secret(
        KEY, secret_id=UUID(int=1), usage="trade", owner=UUID(int=2), value=SecretStr(sentinel)
    )
    value = _open(nonce, ct)

    class Enveloppe(BaseModel):
        v: SecretStr

    box = Enveloppe(v=value)
    store = core.AesGcmSecretStore(KEY)
    for text in (
        repr(value),
        str(value),
        f"{value}",
        repr(box),
        box.model_dump_json(),
        repr(box.model_dump()),
        json.dumps(box.model_dump(mode="json")),
        repr(store),
        repr(vars(store)),
    ):
        assert sentinel not in text
        assert KEY.hex() not in text and repr(KEY) not in text
    with pytest.raises(TypeError):
        json.dumps({"v": value})
