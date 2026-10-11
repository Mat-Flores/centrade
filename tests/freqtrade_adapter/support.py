"""Fabriques partagées. Le paquet de l'adaptateur n'est pas encore dans `pythonpath`
(pyproject.toml) : on l'ajoute ici, sans toucher à la configuration commune."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml  # type: ignore[import-untyped]
from centrade_core.engine.types import InstanceSpec, Manifest, Mode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "adapters" / "freqtrade"))

SMA_DIR = ROOT / "strategies" / "sma-cross"


def sma_manifest(**exits: Any) -> Manifest:
    raw = yaml.safe_load((SMA_DIR / "strategy.yaml").read_text(encoding="utf-8"))
    raw["exits"] = {**raw["exits"], **exits}
    return Manifest.model_validate(raw)


def make_spec(
    mode: Mode = "paper", manifest: Manifest | None = None, **params: Any
) -> InstanceSpec:
    return InstanceSpec(
        instance_id=UUID(int=7),
        engine="freqtrade",
        mode=mode,
        account_id="acc-paper-01",
        manifest=manifest or sma_manifest(),
        params={"pairs": ["crypto:binance:BTC/USDT", "crypto:binance:ETH/USDT"], **params},
    )


TRAILING = {"enabled": True, "positive": "0.01", "offset": "0.02", "only_offset_reached": True}


def make_trailing_spec(mode: Mode = "paper", stoploss: Decimal = Decimal("-0.05")) -> InstanceSpec:
    return make_spec(mode, sma_manifest(trailing=TRAILING, stoploss=stoploss))
