"""Fabriques partagées par les tests de contrat."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import count
from uuid import UUID

from centrade_core.engine.types import Exits, InstanceSpec, Manifest, Mode, Sizing


def make_clock() -> Callable[[], datetime]:
    """Horloge injectée : avance d'une seconde à chaque lecture, aucun sommeil."""
    t = count()
    return lambda: datetime(2026, 10, 10, tzinfo=UTC) + timedelta(seconds=next(t))


def make_id_factory() -> Callable[[], UUID]:
    n = count(1)
    return lambda: UUID(int=next(n))


def make_spec(n: int = 1, mode: Mode = "paper") -> InstanceSpec:
    manifest = Manifest(
        name="demo",
        engine="fake",
        version=1,
        entrypoint="demo.py",
        asset_classes=("crypto",),
        trading_mode="spot",
        timeframes=("5m",),
        modes=("backtest", "paper", "live"),
        params_schema={"properties": {"fast": {"type": "integer"}}},
        sizing=Sizing(stake_amount=Decimal("50"), max_open_positions=3),
        exits=Exits(stoploss=Decimal("-0.05"), stop_on_venue=True),
    )
    return InstanceSpec(
        instance_id=UUID(int=10_000 + n),
        engine="fake",
        mode=mode,
        account_id=f"acc-{mode}-{n:02d}",
        manifest=manifest,
        params={"fast": 10},
    )
