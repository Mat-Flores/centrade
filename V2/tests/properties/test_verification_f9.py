"""Propriétés de la vérification de F9 (SPEC F9, I3, I4, I5, I10) : quel que soit le relevé, un
contrôle en échec ou une donnée manquante interdit d'ouvrir les entrées ; la vérification ne
retient jamais une commande qui réduit le risque."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from centrade_core.commands import RISK_REDUCING
from centrade_core.engine.contract import owned_drifts
from centrade_core.engine.types import (
    Deployment,
    Drift,
    EffectiveConfig,
    EngineConfig,
    Exits,
    InstanceSpec,
    InstanceStatus,
    Manifest,
    Sizing,
)
from centrade_core.engine.verification import (
    DRIFT,
    FINGERPRINT,
    GATED,
    LIVE,
    MODE,
    STALE,
    UNKNOWN,
    Refusal,
    command_refusals,
    entry_refusals,
)
from centrade_worker.testing import T0
from hypothesis import given
from hypothesis import strategies as st

STALE_S = 30.0
PRINTS = (None, "", "fp-a", "fp-b")
VERSIONS = (None, "1", "2")
STATES = ("starting", "exits_only", "running", "halted", "stopped", "error", "unknown")
MANIFEST = Manifest(
    name="s",
    engine="fake",
    version=1,
    entrypoint="s.py",
    asset_classes=("crypto",),
    trading_mode="spot",
    timeframes=("5m",),
    modes=("backtest", "paper", "live"),
    sizing=Sizing(stake_amount=Decimal("50"), max_open_positions=3),
    exits=Exits(stoploss=Decimal("-0.05"), stop_on_venue=True),
)


def _spec(mode: str, fingerprint: str | None, engine_version: str = "1") -> InstanceSpec:
    dep = (
        None
        if not fingerprint
        else Deployment(
            fingerprint=fingerprint,
            config_hash="c",
            code="",
            image="img",
            digest="",
            engine_version=engine_version,
        )
    )
    return InstanceSpec(
        instance_id=UUID(int=1),
        engine="fake",
        mode=mode,
        account_id="acc",
        manifest=MANIFEST,
        deployment=dep,
    )


ages = st.integers(-120, 120)  # négatif : relevé daté du futur
statuses = st.none() | st.builds(
    lambda state, mode, age: InstanceStatus(
        state=state, mode=mode, observed_at=T0 - timedelta(seconds=age)
    ),
    st.sampled_from(STATES),
    st.sampled_from((None, "paper", "live", "backtest")),
    ages,
)
effectives = st.none() | st.builds(
    lambda age, fp, version: EffectiveConfig(
        values={}, observed_at=T0 - timedelta(seconds=age), fingerprint=fp, engine_version=version
    ),
    ages,
    st.sampled_from(PRINTS),
    st.sampled_from(VERSIONS),
)
drift_lists = st.none() | st.lists(
    st.builds(Drift, key=st.sampled_from(("a", "b")), expected=st.just("1"), observed=st.none()),
    max_size=2,
).map(tuple)
refusal_lists = st.lists(st.builds(Refusal, code=st.text(max_size=5), message=st.just("m"))).map(
    tuple
)


@given(
    mode=st.sampled_from(("paper", "live", "backtest")),
    spec_fp=st.sampled_from(PRINTS),
    status=statuses,
    effective=effectives,
    drifts=drift_lists,
    recorded=st.sampled_from(PRINTS),
)
def test_f9_entrees_ouvertes_seulement_si_tout_concorde(
    mode: str,
    spec_fp: str | None,
    status: InstanceStatus | None,
    effective: EffectiveConfig | None,
    drifts: tuple[Drift, ...] | None,
    recorded: str | None,
) -> None:
    def verify() -> tuple[Refusal, ...]:
        return entry_refusals(
            spec=_spec(mode, spec_fp),
            status=status,
            effective=effective,
            drifts=drifts,
            recorded_fingerprint=recorded,
            now=T0,
            stale_after_s=STALE_S,
        )

    refusals = verify()
    assert refusals == verify()  # même entrée, même décision

    def fresh(at: datetime) -> bool:
        return abs((T0 - at).total_seconds()) <= STALE_S

    all_good = (
        mode == "paper"
        and status is not None
        and status.state != "unknown"
        and fresh(status.observed_at)
        and status.mode == "paper"
        and effective is not None
        and drifts == ()
        and fresh(effective.observed_at)
        and bool(spec_fp)
        and spec_fp == recorded == effective.fingerprint
        and effective.engine_version == "1"
    )
    assert (refusals == ()) == all_good
    assert all(r.code and r.message for r in refusals)  # un refus porte toujours son motif


def _conforming() -> dict[str, object]:
    return {
        "spec": _spec("paper", "fp-a"),
        "status": InstanceStatus(state="exits_only", mode="paper", observed_at=T0),
        "effective": EffectiveConfig(
            values={}, observed_at=T0, fingerprint="fp-a", engine_version="1"
        ),
        "drifts": (),
        "recorded_fingerprint": "fp-a",
    }


OLD = T0 - timedelta(seconds=STALE_S + 1)
# Chaque dégradation d'un relevé conforme, et le motif qu'elle doit produire.
DEGRADATIONS: dict[str, tuple[dict[str, object], str]] = {
    "instance live": ({"spec": _spec("live", "fp-a")}, LIVE),
    "état illisible": ({"status": None}, UNKNOWN),
    "état inconnu": (
        {"status": InstanceStatus(state="unknown", mode=None, observed_at=T0)},
        UNKNOWN,
    ),
    "état périmé": (
        {"status": InstanceStatus(state="exits_only", mode="paper", observed_at=OLD)},
        STALE,
    ),
    "mode illisible": (
        {"status": InstanceStatus(state="exits_only", mode=None, observed_at=T0)},
        UNKNOWN,
    ),
    "mode faux": (
        {"status": InstanceStatus(state="exits_only", mode="live", observed_at=T0)},
        MODE,
    ),
    "configuration non relue": ({"effective": None}, UNKNOWN),
    "comparaison non faite": ({"drifts": None}, UNKNOWN),
    "configuration périmée": (
        {
            "effective": EffectiveConfig(
                values={}, observed_at=OLD, fingerprint="fp-a", engine_version="1"
            )
        },
        STALE,
    ),
    "dérive": ({"drifts": (Drift(key="k", expected="1", observed="2"),)}, DRIFT),
    "registre modifié": ({"spec": _spec("paper", "fp-b")}, FINGERPRINT),
    "spécification sans déploiement": ({"spec": _spec("paper", None)}, FINGERPRINT),
    "empreinte jamais enregistrée": ({"recorded_fingerprint": None}, FINGERPRINT),
    "autre chose tourne": (
        {
            "effective": EffectiveConfig(
                values={}, observed_at=T0, fingerprint="fp-b", engine_version="1"
            )
        },
        FINGERPRINT,
    ),
    "empreinte illisible": (
        {"effective": EffectiveConfig(values={}, observed_at=T0, engine_version="1")},
        FINGERPRINT,
    ),
    "autre version de moteur": (
        {
            "effective": EffectiveConfig(
                values={}, observed_at=T0, fingerprint="fp-a", engine_version="2"
            )
        },
        FINGERPRINT,
    ),
}


def test_f9_un_releve_conforme_ouvre_les_entrees() -> None:
    # Sans ce témoin, la propriété suivante passerait avec une fonction qui refuse toujours.
    assert entry_refusals(**_conforming(), now=T0, stale_after_s=STALE_S) == ()  # type: ignore[arg-type]


@given(names=st.lists(st.sampled_from(sorted(DEGRADATIONS)), min_size=1, unique=True))
def test_f9_toute_degradation_d_un_releve_conforme_est_refusee(names: list[str]) -> None:
    case = _conforming()
    for name in names:
        case.update(DEGRADATIONS[name][0])
    codes = {r.code for r in entry_refusals(**case, now=T0, stale_after_s=STALE_S)}  # type: ignore[arg-type]
    assert codes  # jamais d'ouverture
    if len(names) == 1:
        assert DEGRADATIONS[names[0]][1] in codes  # et le bon motif


@given(
    type_=st.sampled_from(sorted(RISK_REDUCING)) | st.text(max_size=12),
    mode=st.sampled_from(("paper", "live", "", "x")),
    status=statuses,
    entries=st.none() | refusal_lists,
    stale_after_s=st.floats(0, 3600),
)
def test_f9_ne_retient_jamais_ce_qui_reduit_le_risque(
    type_: str,
    mode: str,
    status: InstanceStatus | None,
    entries: tuple[Refusal, ...] | None,
    stale_after_s: float,
) -> None:
    out = command_refusals(
        type_, mode=mode, status=status, entries=entries, now=T0, stale_after_s=stale_after_s
    )
    if type_ not in GATED:
        assert out == ()  # pause, flatten, stop, fermeture, annulation : jamais de motif (I4)
    assert not (RISK_REDUCING & GATED)


@given(
    type_=st.sampled_from(sorted(GATED)),
    mode=st.sampled_from(("paper", "live", "backtest", "")),
    status=statuses,
    entries=st.none() | refusal_lists,
)
def test_f9_ce_qui_augmente_le_risque_part_seulement_sans_aucun_doute(
    type_: str, mode: str, status: InstanceStatus | None, entries: tuple[Refusal, ...] | None
) -> None:
    out = command_refusals(
        type_, mode=mode, status=status, entries=entries, now=T0, stale_after_s=STALE_S
    )
    if mode != "paper":
        assert out and out[0].code == LIVE  # aucun chemin de promotion avant M7
    elif type_ == "resume_entries" and (entries is None or entries):
        assert out  # vérification absente ou en échec : rien ne part
    elif type_ != "deploy" and out == ():
        assert status is not None and status.state != "unknown"
        assert abs((T0 - status.observed_at).total_seconds()) <= STALE_S
        if type_ == "resume_entries":
            assert status.state in ("exits_only", "running") and status.mode == "paper"


keys = st.sampled_from(("a", "b", "c", "d", "e"))


@given(
    generated=st.dictionaries(keys, st.sampled_from(("1", "2"))),
    read=st.sets(keys),
    unreadable=st.sets(keys),
    reported=st.sets(keys),
)
def test_f9_cle_possedee_absente_de_la_relecture_est_une_derive_sauf_declaree(
    generated: dict[str, str], read: set[str], unreadable: set[str], reported: set[str]
) -> None:
    config = EngineConfig(values=generated, unreadable=frozenset(unreadable))
    effective = EffectiveConfig(values=dict.fromkeys(read, "1"), observed_at=T0)
    by_adapter = tuple(Drift(key=k, expected="1", observed="9") for k in sorted(reported))
    out = owned_drifts(config, effective, by_adapter)
    assert out[: len(by_adapter)] == by_adapter  # rien de ce que l'adaptateur rapporte ne se perd
    added = {d.key for d in out[len(by_adapter) :]}
    assert added == set(generated) - read - unreadable - reported  # jamais d'ignorance silencieuse
    assert all(d.observed is None for d in out[len(by_adapter) :])


def test_f9_reprise_refusee_si_la_verification_n_a_pas_eu_lieu() -> None:
    """Le relevé a beau être parfait : sans résultat de vérification, rien ne part."""
    good = InstanceStatus(state="exits_only", mode="paper", observed_at=T0)

    def refusals(entries: tuple[Refusal, ...] | None) -> tuple[Refusal, ...]:
        return command_refusals(
            "resume_entries", mode="paper", status=good, entries=entries, now=T0, stale_after_s=30
        )

    assert refusals(()) == ()  # témoin : vérification passée, la reprise part
    assert [r.code for r in refusals(None)] == [UNKNOWN]
    drift = (Refusal(DRIFT, "dérive"),)
    assert refusals(drift) == drift
