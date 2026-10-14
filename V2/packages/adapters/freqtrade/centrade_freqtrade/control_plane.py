"""Base class of every platform strategy (SPEC §7, F2, F10, annex C).

Mounted in the container next to the strategy (`from control_plane import ControlPlaneStrategy`).
Depends only on Freqtrade and the standard library.
"""

from __future__ import annotations

import logging
from abc import ABCMeta
from datetime import datetime
from typing import Any

from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)

PROTECTED: frozenset[str] = frozenset()  # filled after the class, from what it defines


class _Sealed(ABCMeta):
    """Metaclass: a protected name is neither reassigned nor deleted on the base class or
    on a subclass (`S.confirm_trade_entry = …`). `IStrategy` is an ABC (tag 2026.9)."""

    def __setattr__(cls, name: str, value: Any) -> None:
        if name in PROTECTED:
            raise TypeError(f"{cls.__name__}.{name} : nom de la plateforme, non modifiable")
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if name in PROTECTED:
            raise TypeError(f"{cls.__name__}.{name} : nom de la plateforme, non modifiable")
        super().__delattr__(name)


class ControlPlaneStrategy(IStrategy, metaclass=_Sealed):
    can_short = False  # spot only (V1)
    _boot_dry_run = False  # refuse until __init__ has read the mode

    def __init__(self, config: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        # Mode read once, at construction: the strategy does not change it afterwards.
        object.__setattr__(self, "_boot_dry_run", config.get("dry_run") is True)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        mro = cls.__mro__  # the subclass and any class placed before the base
        clash = sorted(
            {n for k in mro[: mro.index(ControlPlaneStrategy)] for n in vars(k)} & PROTECTED
        )
        if clash:  # TypeError: not caught by Freqtrade's loader, the engine does not start
            raise TypeError(f"{cls.__name__} redéfinit des noms de la plateforme : {clash}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in PROTECTED:  # no platform method masked on the instance
            raise TypeError(f"{name} : nom de la plateforme, non modifiable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in PROTECTED:
            raise TypeError(f"{name} : nom de la plateforme, non modifiable")
        super().__delattr__(name)

    def _intact(self) -> bool:
        """The protected names resolved on this type are the base's: nothing masks them, neither a
        class placed before it, nor the instance. Covers a write that would have avoided
        `__setattr__`; not a replacement of `confirm_trade_entry` itself nor of the base."""
        mro = type(self).__mro__
        before = mro[: mro.index(ControlPlaneStrategy)]
        shadows = [vars(k).keys() & PROTECTED for k in before]
        return not any(shadows) and not vars(self).keys() & (PROTECTED - {"_boot_dry_run"})

    def _entry_allowed(self, **order: Any) -> bool:
        """M3 extension point: replace with POST /api/v1/risk/check (token bound to the instance,
        deterministic request_id, 500 ms timeout). Any response other than a valid, unexpired
        `accept` must return False. In M2 there is no Risk service: dry-run only."""
        return self._boot_dry_run is True and self.config.get("dry_run") is True

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs: Any,
    ) -> bool:
        # An exception counts as acceptance on the engine side (annex C, fact 2): catch all.
        try:
            if not self._intact():
                logger.error("confirm_trade_entry : noms de la plateforme masqués, refus")
                return False
            return self._entry_allowed(pair=pair, amount=amount, rate=rate, side=side) is True
        except Exception:
            logger.exception("confirm_trade_entry : refus sur erreur")
            return False

    def confirm_trade_exit(self, *args: Any, **kwargs: Any) -> bool:
        return True  # an exit is never blocked (I4)

    def adjust_trade_position(self, *args: Any, **kwargs: Any) -> None:
        return None  # no top-up: it would escape confirm_trade_entry

    def adjust_order_price(self, *args: Any, current_order_rate: float, **kwargs: Any) -> float:
        # Only adjust_order_price is defined: the engine refuses at load a strategy that
        # redefines it in addition to adjust_entry_price or adjust_exit_price (ADR 0008). It covers
        # entry and exit orders; the order in place is kept, never replaced.
        return current_order_rate

    def leverage(self, *args: Any, **kwargs: Any) -> float:
        return 1.0


# Names a subclass cannot redefine: everything the base defines (apart from Python and ABC
# noise), plus two hooks the engine refuses alongside adjust_order_price. checks.py
# derives the same list from this file; a test checks that they do not diverge.
_OWN_DUNDERS = ("__init__", "__init_subclass__", "__setattr__", "__delattr__")
PROTECTED = frozenset(
    n
    for n in vars(ControlPlaneStrategy)
    if not n.startswith("_abc_") and (not n.startswith("__") or n in _OWN_DUNDERS)
) | {"adjust_entry_price", "adjust_exit_price"}
