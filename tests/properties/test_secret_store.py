"""SecretStore V1 (AES-256-GCM) : propriétés du chiffrement. Valeurs sentinelles uniquement."""

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
def test_aller_retour(value: str, secret_id: UUID, owner: UUID, usage: core.Usage) -> None:
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
def test_deux_chiffrements_de_la_meme_valeur_different(value: str) -> None:
    args = {"secret_id": UUID(int=1), "usage": "trade", "owner": UUID(int=2)}
    a = core.encrypt_secret(KEY, value=SecretStr(value), **args)  # type: ignore[arg-type]
    b = core.encrypt_secret(KEY, value=SecretStr(value), **args)  # type: ignore[arg-type]
    assert a[0] != b[0] and a[1] != b[1]


@given(value=values, data=st.data())
def test_chiffre_ou_nonce_altere_refuse(value: str, data: st.DataObject) -> None:
    nonce, ct = core.encrypt_secret(
        KEY, secret_id=UUID(int=1), usage="trade", owner=UUID(int=2), value=SecretStr(value)
    )
    target = data.draw(st.sampled_from(("nonce", "ct")))
    raw = bytearray(nonce if target == "nonce" else ct)
    raw[data.draw(st.integers(0, len(raw) - 1))] ^= data.draw(st.integers(1, 255))
    with pytest.raises(InvalidTag):
        _open(bytes(raw), ct) if target == "nonce" else _open(nonce, bytes(raw))
    with pytest.raises(InvalidTag):  # chiffré tronqué : jamais de valeur partielle
        _open(nonce, ct[: data.draw(st.integers(0, len(ct) - 1))])


@given(value=values, other=st.uuids().filter(lambda u: u.int > 2), usage=usages)
def test_chiffre_rejoue_ailleurs_refuse(value: str, other: UUID, usage: core.Usage) -> None:
    """Autre identifiant, autre usage ou autre propriétaire : l'AAD ne correspond plus."""
    nonce, ct = core.encrypt_secret(
        KEY, secret_id=UUID(int=1), usage="trade", owner=UUID(int=2), value=SecretStr(value)
    )
    replays: list[dict[str, object]] = [{"secret_id": other}, {"owner": other}]
    if usage != "trade":
        replays.append({"usage": usage})
    for over in replays:
        with pytest.raises(InvalidTag):
            _open(nonce, ct, **over)
    with pytest.raises(InvalidTag):  # autre clé maître
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
def test_mauvaise_longueur_de_cle_refusee(size: int) -> None:
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
def test_version_de_cle_inconnue_refusee(version: int) -> None:
    nonce, ct = core.encrypt_secret(
        KEY, secret_id=UUID(int=1), usage="trade", owner=UUID(int=2), value=SecretStr("x")
    )
    with pytest.raises(ValueError, match="version de clé"):
        _open(nonce, ct, key_version=version)


def test_valeur_vide_ou_usage_inconnu_refuses() -> None:
    args = {"secret_id": UUID(int=1), "owner": UUID(int=2)}
    with pytest.raises(ValueError, match="vide"):
        core.encrypt_secret(KEY, usage="trade", value=SecretStr(""), **args)
    with pytest.raises(ValueError, match="usage"):
        core.encrypt_secret(KEY, usage="autre", value=SecretStr("x"), **args)  # type: ignore[arg-type]


@given(user=st.uuids(), secret=values)
def test_totp_et_secrets_ne_se_dechiffrent_pas_l_un_pour_l_autre(user: UUID, secret: str) -> None:
    """Le déchiffrement du TOTP, seul accessible à l'API, n'ouvre aucune ligne de `secrets`."""
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


def test_la_valeur_en_clair_ne_fuit_ni_par_repr_ni_par_serialisation() -> None:
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
