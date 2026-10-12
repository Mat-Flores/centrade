"""Classe de base de toute stratégie de la plateforme (SPEC §7, F2, F10, annexe C).

Montée dans le conteneur à côté de la stratégie (`from control_plane import ControlPlaneStrategy`).
Ne dépend que de Freqtrade et de la bibliothèque standard.
"""

from __future__ import annotations

import logging
from abc import ABCMeta
from datetime import datetime
from typing import Any

from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)

PROTECTED: frozenset[str] = frozenset()  # rempli après la classe, à partir de ce qu'elle définit


class _Sealed(ABCMeta):
    """Métaclasse : un nom protégé ne se réaffecte ni ne se supprime sur la classe de base ou
    sur une sous-classe (`S.confirm_trade_entry = …`). `IStrategy` est une ABC (tag 2026.9)."""

    def __setattr__(cls, name: str, value: Any) -> None:
        if name in PROTECTED:
            raise TypeError(f"{cls.__name__}.{name} : nom de la plateforme, non modifiable")
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if name in PROTECTED:
            raise TypeError(f"{cls.__name__}.{name} : nom de la plateforme, non modifiable")
        super().__delattr__(name)


class ControlPlaneStrategy(IStrategy, metaclass=_Sealed):
    can_short = False  # spot seulement (V1)
    _boot_dry_run = False  # refus tant que __init__ n'a pas lu le mode

    def __init__(self, config: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        # Mode lu une fois, à la construction : la stratégie ne le change pas après coup.
        object.__setattr__(self, "_boot_dry_run", config.get("dry_run") is True)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        mro = cls.__mro__  # la sous-classe et toute classe placée avant la base
        clash = sorted(
            {n for k in mro[: mro.index(ControlPlaneStrategy)] for n in vars(k)} & PROTECTED
        )
        if clash:  # TypeError : non attrapée par le chargeur de Freqtrade, le moteur ne démarre pas
            raise TypeError(f"{cls.__name__} redéfinit des noms de la plateforme : {clash}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in PROTECTED:  # pas de méthode de la plateforme masquée sur l'instance
            raise TypeError(f"{name} : nom de la plateforme, non modifiable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in PROTECTED:
            raise TypeError(f"{name} : nom de la plateforme, non modifiable")
        super().__delattr__(name)

    def _intact(self) -> bool:
        """Les noms protégés résolus sur ce type sont ceux de la base : rien ne les masque, ni une
        classe placée avant elle, ni l'instance. Couvre une écriture qui aurait évité
        `__setattr__` ; pas un remplacement de `confirm_trade_entry` lui-même ni de la base."""
        mro = type(self).__mro__
        before = mro[: mro.index(ControlPlaneStrategy)]
        shadows = [vars(k).keys() & PROTECTED for k in before]
        return not any(shadows) and not vars(self).keys() & (PROTECTED - {"_boot_dry_run"})

    def _entry_allowed(self, **order: Any) -> bool:
        """Point d'extension M3 : remplacer par POST /api/v1/risk/check (jeton lié à l'instance,
        request_id déterministe, délai 500 ms). Toute réponse autre qu'un `accept` valide et non
        expiré doit retourner False. À M2 il n'y a pas de Risk service : dry-run seulement."""
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
        # Une exception vaut acceptation côté moteur (annexe C, fait 2) : on attrape tout.
        try:
            if not self._intact():
                logger.error("confirm_trade_entry : noms de la plateforme masqués, refus")
                return False
            return self._entry_allowed(pair=pair, amount=amount, rate=rate, side=side) is True
        except Exception:
            logger.exception("confirm_trade_entry : refus sur erreur")
            return False

    def confirm_trade_exit(self, *args: Any, **kwargs: Any) -> bool:
        return True  # une sortie n'est jamais bloquée (I4)

    def adjust_trade_position(self, *args: Any, **kwargs: Any) -> None:
        return None  # pas de renfort : il échapperait à confirm_trade_entry

    def adjust_order_price(self, *args: Any, current_order_rate: float, **kwargs: Any) -> float:
        # Seul adjust_order_price est défini : le moteur refuse au chargement une stratégie qui
        # le redéfinit en plus de adjust_entry_price ou adjust_exit_price (ADR 0008). Il couvre
        # les ordres d'entrée et de sortie ; l'ordre en place est maintenu, jamais remplacé.
        return current_order_rate

    def leverage(self, *args: Any, **kwargs: Any) -> float:
        return 1.0


# Noms qu'une sous-classe ne peut pas redéfinir : tout ce que la base définit (hors bruit de
# Python et d'ABC), plus deux hooks que le moteur refuse avec adjust_order_price. checks.py
# dérive la même liste de ce fichier ; un test vérifie qu'elles ne divergent pas.
_OWN_DUNDERS = ("__init__", "__init_subclass__", "__setattr__", "__delattr__")
PROTECTED = frozenset(
    n
    for n in vars(ControlPlaneStrategy)
    if not n.startswith("_abc_") and (not n.startswith("__") or n in _OWN_DUNDERS)
) | {"adjust_entry_price", "adjust_exit_price"}
