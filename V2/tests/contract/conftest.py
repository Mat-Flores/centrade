"""Fixture parametrized by adapter: adding an adapter = adding a factory below."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from centrade_core.engine.contract import EngineAdapter
from centrade_core.engine.types import InstanceRef, InstanceSpec
from centrade_fake.engine import Failure, FakeEngine
from freqtrade_adapter.double import Rig

from .contract_support import make_clock, make_id_factory, make_spec


@dataclass
class Harness:
    adapter: EngineAdapter
    drive: Callable[[InstanceRef, int], None]  # advances the engine by n steps
    make_unreachable: Callable[[InstanceRef], None]
    make_drift: Callable[[InstanceRef], None]
    spec: Callable[[], InstanceSpec]


def _fake() -> Harness:
    eng = FakeEngine(clock=make_clock(), seed=7, new_id=make_id_factory())

    def drive(ref: InstanceRef, n: int) -> None:
        for _ in range(n):
            eng.step(ref)

    return Harness(
        adapter=eng,
        drive=drive,
        make_unreachable=lambda ref: eng.set_failure(ref, Failure.SILENT),
        make_drift=lambda ref: eng.set_failure(ref, Failure.DRIFT),
        spec=make_spec,
    )


def _freqtrade() -> Harness:
    rig = Rig()

    def make_drift(ref: InstanceRef) -> None:
        rig.server.cfg["max_open_trades"] = 99.0

    def drive(ref: InstanceRef, n: int) -> None:
        for _ in range(n):
            rig.server.step()

    def unreachable(ref: InstanceRef) -> None:
        rig.server.unreachable = True

    return Harness(
        adapter=rig.adapter,
        drive=drive,
        make_unreachable=unreachable,
        make_drift=make_drift,
        spec=lambda: rig.prepare(make_spec()),
    )


ADAPTERS: dict[str, Callable[[], Harness]] = {"fake": _fake, "freqtrade": _freqtrade}


@pytest.fixture(params=sorted(ADAPTERS))
def harness(request: pytest.FixtureRequest) -> Harness:
    return ADAPTERS[request.param]()
