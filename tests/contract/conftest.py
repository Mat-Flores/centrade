"""Fixture paramétrée par adaptateur : ajouter un adaptateur = ajouter une fabrique ci-dessous."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from centrade_core.engine.contract import EngineAdapter
from centrade_core.engine.types import InstanceRef
from centrade_fake.engine import Failure, FakeEngine

from .contract_support import make_clock, make_id_factory


@dataclass
class Harness:
    adapter: EngineAdapter
    drive: Callable[[InstanceRef, int], None]  # avance le moteur de n pas
    make_unreachable: Callable[[InstanceRef], None]
    make_drift: Callable[[InstanceRef], None]


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
    )


ADAPTERS: dict[str, Callable[[], Harness]] = {"fake": _fake}


@pytest.fixture(params=sorted(ADAPTERS))
def harness(request: pytest.FixtureRequest) -> Harness:
    return ADAPTERS[request.param]()
