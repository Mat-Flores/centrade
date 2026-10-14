"""F9 verification properties (SPEC F9, I3, I4, I5, I10): whatever the snapshot, a
failed check or missing data forbids opening entries; the verification never
holds back a command that reduces risk."""

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


ages = st.integers(-120, 120)  # negative: snapshot dated in the future
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
def test_f9_entries_open_only_if_everything_matches(
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
    assert refusals == verify()  # same input, same decision

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
    assert all(r.code and r.message for r in refusals)  # a refusal always carries its reason


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
# Each degradation of a compliant snapshot, and the reason it must produce.
DEGRADATIONS: dict[str, tuple[dict[str, object], str]] = {
    "live instance": ({"spec": _spec("live", "fp-a")}, LIVE),
    "unreadable state": ({"status": None}, UNKNOWN),
    "unknown state": (
        {"status": InstanceStatus(state="unknown", mode=None, observed_at=T0)},
        UNKNOWN,
    ),
    "stale state": (
        {"status": InstanceStatus(state="exits_only", mode="paper", observed_at=OLD)},
        STALE,
    ),
    "unreadable mode": (
        {"status": InstanceStatus(state="exits_only", mode=None, observed_at=T0)},
        UNKNOWN,
    ),
    "wrong mode": (
        {"status": InstanceStatus(state="exits_only", mode="live", observed_at=T0)},
        MODE,
    ),
    "config not reread": ({"effective": None}, UNKNOWN),
    "comparison not done": ({"drifts": None}, UNKNOWN),
    "stale config": (
        {
            "effective": EffectiveConfig(
                values={}, observed_at=OLD, fingerprint="fp-a", engine_version="1"
            )
        },
        STALE,
    ),
    "drift": ({"drifts": (Drift(key="k", expected="1", observed="2"),)}, DRIFT),
    "registry changed": ({"spec": _spec("paper", "fp-b")}, FINGERPRINT),
    "spec without deployment": ({"spec": _spec("paper", None)}, FINGERPRINT),
    "fingerprint never recorded": ({"recorded_fingerprint": None}, FINGERPRINT),
    "something else is running": (
        {
            "effective": EffectiveConfig(
                values={}, observed_at=T0, fingerprint="fp-b", engine_version="1"
            )
        },
        FINGERPRINT,
    ),
    "unreadable fingerprint": (
        {"effective": EffectiveConfig(values={}, observed_at=T0, engine_version="1")},
        FINGERPRINT,
    ),
    "other engine version": (
        {
            "effective": EffectiveConfig(
                values={}, observed_at=T0, fingerprint="fp-a", engine_version="2"
            )
        },
        FINGERPRINT,
    ),
}


def test_f9_conforming_snapshot_opens_entries() -> None:
    # Without this control case, the next property would pass with a function that always refuses.
    assert entry_refusals(**_conforming(), now=T0, stale_after_s=STALE_S) == ()  # type: ignore[arg-type]


@given(names=st.lists(st.sampled_from(sorted(DEGRADATIONS)), min_size=1, unique=True))
def test_f9_any_degradation_of_a_conforming_snapshot_is_rejected(names: list[str]) -> None:
    case = _conforming()
    for name in names:
        case.update(DEGRADATIONS[name][0])
    codes = {r.code for r in entry_refusals(**case, now=T0, stale_after_s=STALE_S)}  # type: ignore[arg-type]
    assert codes  # never opens
    if len(names) == 1:
        assert DEGRADATIONS[names[0]][1] in codes  # and the right reason


@given(
    type_=st.sampled_from(sorted(RISK_REDUCING)) | st.text(max_size=12),
    mode=st.sampled_from(("paper", "live", "", "x")),
    status=statuses,
    entries=st.none() | refusal_lists,
    stale_after_s=st.floats(0, 3600),
)
def test_f9_never_holds_back_what_reduces_risk(
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
        assert out == ()  # pause, flatten, stop, close, cancel: never a reason (I4)
    assert not (RISK_REDUCING & GATED)


@given(
    type_=st.sampled_from(sorted(GATED)),
    mode=st.sampled_from(("paper", "live", "backtest", "")),
    status=statuses,
    entries=st.none() | refusal_lists,
)
def test_f9_risk_increasing_actions_go_out_only_without_any_doubt(
    type_: str, mode: str, status: InstanceStatus | None, entries: tuple[Refusal, ...] | None
) -> None:
    out = command_refusals(
        type_, mode=mode, status=status, entries=entries, now=T0, stale_after_s=STALE_S
    )
    if mode != "paper":
        assert out and out[0].code == LIVE  # no promotion path before M7
    elif type_ == "resume_entries" and (entries is None or entries):
        assert out  # verification absent or failed: nothing is sent
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
def test_f9_owned_key_missing_from_readback_is_drift_unless_declared(
    generated: dict[str, str], read: set[str], unreadable: set[str], reported: set[str]
) -> None:
    config = EngineConfig(values=generated, unreadable=frozenset(unreadable))
    effective = EffectiveConfig(values=dict.fromkeys(read, "1"), observed_at=T0)
    by_adapter = tuple(Drift(key=k, expected="1", observed="9") for k in sorted(reported))
    out = owned_drifts(config, effective, by_adapter)
    assert out[: len(by_adapter)] == by_adapter  # nothing the adapter reports is lost
    added = {d.key for d in out[len(by_adapter) :]}
    assert added == set(generated) - read - unreadable - reported  # never silent ignorance
    assert all(d.observed is None for d in out[len(by_adapter) :])


def test_f9_resume_is_rejected_if_verification_did_not_happen() -> None:
    """However perfect the snapshot: without a verification result, nothing is sent."""
    good = InstanceStatus(state="exits_only", mode="paper", observed_at=T0)

    def refusals(entries: tuple[Refusal, ...] | None) -> tuple[Refusal, ...]:
        return command_refusals(
            "resume_entries", mode="paper", status=good, entries=entries, now=T0, stale_after_s=30
        )

    assert refusals(()) == ()  # control case: verification passed, the resume is sent
    assert [r.code for r in refusals(None)] == [UNKNOWN]
    drift = (Refusal(DRIFT, "drift"),)
    assert refusals(drift) == drift
