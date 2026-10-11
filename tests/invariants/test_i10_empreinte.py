"""I10 : l'empreinte de déploiement ne dépend que de ce qui fait le comportement, jamais du mode."""

from typing import Any

from centrade_core.deployment import config_hash, deployment_fingerprint
from hypothesis import given
from hypothesis import strategies as st

BASE: dict[str, Any] = {
    "code_hash": "c" * 64,
    "params": {"fast": 10, "slow": "30"},
    "exits": {"stoploss": "-0.05", "trailing": {}},
    "image": "freqtradeorg/freqtrade:2026.9",
    "digest": "sha256:" + "a" * 64,
    "config_hash": "f" * 64,
}


def test_i10_meme_entree_meme_empreinte() -> None:
    assert deployment_fingerprint(**BASE) == deployment_fingerprint(**dict(BASE))


def test_i10_chaque_champ_change_l_empreinte() -> None:
    ref = deployment_fingerprint(**BASE)
    changes: dict[str, Any] = {
        "code_hash": "d" * 64,
        "params": {"fast": 11, "slow": "30"},
        "exits": {"stoploss": "-0.04", "trailing": {}},
        "image": "freqtradeorg/freqtrade:2026.10",
        "digest": "sha256:" + "b" * 64,
        "config_hash": "e" * 64,
    }
    for key, value in changes.items():
        assert deployment_fingerprint(**{**BASE, key: value}) != ref, key


def test_i10_le_mode_n_entre_pas_dans_l_empreinte() -> None:
    paper = {"dry_run": True, "db_url": "sqlite:///paper.db", "bot_name": "p", "exchange": {"k": 1}}
    live = {"dry_run": False, "db_url": "sqlite:///live.db", "bot_name": "l", "exchange": {"k": 2}}
    shared = {"strategy": "sma-cross", "stoploss": "-0.05"}
    # Les champs propres au mode sont retirés de la configuration avant le hash : même hash.
    assert config_hash({**shared, **paper}, exclude=set(paper)) == config_hash(
        {**shared, **live}, exclude=set(live)
    )
    assert config_hash({**shared, "stoploss": "-0.04"}, exclude=set(paper)) != config_hash(
        {**shared, **paper}, exclude=set(paper)
    )


json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(),
    lambda c: st.lists(c, max_size=3) | st.dictionaries(st.text(), c, max_size=3),
    max_leaves=8,
)


@given(params=st.dictionaries(st.text(), json_values, max_size=5), seed=st.randoms())
def test_i10_independant_de_l_ordre_des_cles(params: dict[str, Any], seed: Any) -> None:
    items = list(params.items())
    seed.shuffle(items)
    a = deployment_fingerprint(**{**BASE, "params": params})
    b = deployment_fingerprint(**{**BASE, "params": dict(items)})
    assert a == b
    assert config_hash(params) == config_hash(dict(items))


@given(
    a=st.dictionaries(st.text(), json_values, max_size=4),
    b=st.dictionaries(st.text(), json_values, max_size=4),
)
def test_i10_parametres_differents_empreintes_differentes(
    a: dict[str, Any], b: dict[str, Any]
) -> None:
    fa = deployment_fingerprint(**{**BASE, "params": a})
    fb = deployment_fingerprint(**{**BASE, "params": b})
    assert (fa == fb) == (a == b)
