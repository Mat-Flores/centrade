"""I10 : l'empreinte de déploiement ne dépend que de ce qui fait le comportement, jamais du mode."""

import json
from typing import Any

from centrade_core.deployment import config_hash, deployment_fingerprint
from hypothesis import example, given
from hypothesis import strategies as st

BASE: dict[str, Any] = {
    "code_hash": "c" * 64,
    "params": {"fast": 10, "slow": "30"},
    "exits": {"stoploss": "-0.05", "trailing": {}},
    "image": "freqtradeorg/freqtrade:2026.9",
    "digest": "sha256:" + "a" * 64,
    "config_hash": "f" * 64,
}


def test_i10_same_input_gives_same_fingerprint() -> None:
    assert deployment_fingerprint(**BASE) == deployment_fingerprint(**dict(BASE))


def test_i10_each_field_changes_the_fingerprint() -> None:
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


def test_i10_mode_is_not_part_of_the_fingerprint() -> None:
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
def test_i10_fingerprint_is_independent_of_key_order(params: dict[str, Any], seed: Any) -> None:
    items = list(params.items())
    seed.shuffle(items)
    a = deployment_fingerprint(**{**BASE, "params": params})
    b = deployment_fingerprint(**{**BASE, "params": dict(items)})
    assert a == b
    assert config_hash(params) == config_hash(dict(items))


@example(a={"": True}, b={"": 1})
@given(
    a=st.dictionaries(st.text(), json_values, max_size=4),
    b=st.dictionaries(st.text(), json_values, max_size=4),
)
def test_i10_different_params_give_different_fingerprints(
    a: dict[str, Any], b: dict[str, Any]
) -> None:
    fa = deployment_fingerprint(**{**BASE, "params": a})
    fb = deployment_fingerprint(**{**BASE, "params": b})

    # JSON canonique, pas `a == b` : en Python `{"": True} == {"": 1}`, pas en JSON.
    def canon(d: dict[str, Any]) -> str:
        return json.dumps(d, sort_keys=True)

    assert (fa == fb) == (canon(a) == canon(b))


# --- au déploiement et à la vérification de F9 (worker) -----------------------------------------


def _rows() -> tuple[Any, Any, Any]:
    from centrade_core.ids import uuid7
    from centrade_core.models.trading import Engine, Instance, StrategyVersion

    manifest = {
        "name": "s",
        "engine": "fake",
        "version": 1,
        "entrypoint": "s.py",
        "asset_classes": ["crypto"],
        "trading_mode": "spot",
        "timeframes": ["5m"],
        "modes": ["paper", "live"],
        "sizing": {"stake_amount": "50", "max_open_positions": 3},
        "exits": {"stoploss": "-0.05", "stop_on_venue": True},
    }
    engine = Engine(
        id=uuid7(), kind="fake", image="img:1", version="1", digest="sha256:" + "a" * 64
    )
    version = StrategyVersion(
        id=uuid7(), manifest=manifest, code="pass", code_hash="c" * 64, exits=manifest["exits"]
    )
    inst = Instance(
        id=uuid7(),
        engine_id=engine.id,
        name="i",
        mode="paper",
        params={"fast": 10},
        account_id=None,
    )
    return inst, engine, version


def _fake() -> Any:
    from centrade_core.ids import uuid7
    from centrade_fake.engine import FakeEngine
    from centrade_worker.testing import T0

    return FakeEngine(clock=lambda: T0, seed=1, new_id=uuid7)


# Ce qui change le comportement : un autre code, une autre image, une autre configuration.
CHANGES: dict[str, Any] = {
    "code": lambda i, e, v: setattr(v, "code_hash", "d" * 64),
    "image": lambda i, e, v: setattr(e, "image", "img:2"),
    "digest": lambda i, e, v: setattr(e, "digest", "sha256:" + "b" * 64),
    "params": lambda i, e, v: setattr(i, "params", {"fast": 11}),
    "exit policy": lambda i, e, v: setattr(v, "exits", {"stoploss": "-0.04"}),
    "generated config": lambda i, e, v: setattr(
        v, "manifest", {**v.manifest, "sizing": {"stake_amount": "60", "max_open_positions": 3}}
    ),
}


@given(names=st.lists(st.sampled_from(sorted(CHANGES)), min_size=1, unique=True))
def test_i10_different_image_code_or_config_rejects_entries(names: list[str]) -> None:
    from centrade_core.engine.types import EffectiveConfig, InstanceStatus
    from centrade_core.engine.verification import FINGERPRINT, entry_refusals
    from centrade_worker.guard import spec_for
    from centrade_worker.testing import T0

    fake = _fake()
    deployed, _ = spec_for(*_rows(), fake)
    assert deployed.deployment is not None
    recorded = (
        deployed.deployment.fingerprint
    )  # enregistrée au déploiement, portée par ce qui tourne

    def codes(spec: Any) -> set[str]:
        return {
            r.code
            for r in entry_refusals(
                spec=spec,
                status=InstanceStatus(state="exits_only", mode="paper", observed_at=T0),
                effective=EffectiveConfig(
                    values={}, observed_at=T0, fingerprint=recorded, engine_version="1"
                ),
                drifts=(),
                recorded_fingerprint=recorded,
                now=T0,
                stale_after_s=30,
            )
        }

    assert codes(deployed) == set()  # rien n'a changé : les entrées peuvent s'ouvrir
    rows = _rows()
    for name in names:
        CHANGES[name](*rows)
    changed, _ = spec_for(*rows, fake)
    assert changed.deployment is not None
    assert changed.deployment.fingerprint != recorded
    assert codes(changed) == {FINGERPRINT}


def test_i10_mode_specific_fields_are_excluded_from_comparison() -> None:
    from centrade_core.ids import uuid7
    from centrade_worker.guard import spec_for

    fake = _fake()
    base, generated = spec_for(*_rows(), fake)
    inst, engine, version = _rows()
    inst.id, inst.name, inst.account_id = uuid7(), "autre", uuid7()  # autre instance, autre compte
    other, other_generated = spec_for(inst, engine, version, fake)
    assert base.deployment is not None and other.deployment is not None
    assert generated.values != other_generated.values  # la configuration diffère bien…
    assert other.deployment.fingerprint == base.deployment.fingerprint  # … pas l'empreinte


async def test_i10_fingerprint_recorded_at_deploy_is_that_of_what_runs(
    stack: Any,
) -> None:
    from centrade_api.testing import act, create_instance, get, ref_of
    from centrade_core.models.trading import Engine
    from sqlalchemy import update
    from worker_support import alerts, commands, instance, spy

    w = stack.world
    c = await stack.client("operator")
    iid = str((await create_instance(c))["id"])
    assert (await instance(w, iid)).deployment_fingerprint is None  # rien n'est encore déployé
    await w.worker.run_once()

    row = await instance(w, iid)
    running = await w.fake.effective_config(ref_of(iid))
    assert row.deployment_fingerprint and row.deployment_fingerprint == running.fingerprint
    generated = (await w.worker.guard.target(row.id)).generated
    assert row.config_hash == config_hash(generated.values, exclude=generated.mode_keys)
    assert (await commands(w, iid, "deploy"))[0].status == "verified"
    detail = await get(c, f"/api/v1/instances/{iid}")
    assert detail["deployment_fingerprint"] == row.deployment_fingerprint

    # L'image du moteur change dans la table `engines` : ce qui tourne n'est plus ce que le
    # registre décrit. La reprise est refusée et rien ne part vers le moteur.
    calls = spy(w.fake)
    r = await act(c, iid, "resume-entries")
    assert r.status_code == 202
    async with w.sessions() as s:
        image = (await s.get_one(Engine, row.engine_id)).image
    try:
        async with w.sessions.begin() as s:
            await s.execute(update(Engine).where(Engine.id == row.engine_id).values(image="autre"))
        await w.worker.run_once()
    finally:  # la ligne `engines` est partagée entre les tests
        async with w.sessions.begin() as s:
            await s.execute(update(Engine).where(Engine.id == row.engine_id).values(image=image))
    cmd = await get(c, f"/api/v1/commands/{r.json()['command_id']}")
    assert cmd["status"] == "failed", cmd
    assert {x["code"] for x in cmd["result"]["reasons"]} == {"fingerprint"}
    assert calls == [] and (await w.fake.status(ref_of(iid))).state == "exits_only"
    assert [a.rule for a in await alerts(w, iid)] == ["fingerprint_mismatch", "entries_refused"]
