"""Classe de base de toute stratégie de la plateforme (SPEC §7, F2, F10, annexe C).

Montée dans le conteneur à côté de la stratégie (`from control_plane import ControlPlaneStrategy`).
Ne dépend que de Freqtrade et de la bibliothèque standard.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)


class ControlPlaneStrategy(IStrategy):
    INTERFACE_VERSION = 3
    can_short = False  # spot seulement (V1)

    def _entry_allowed(self, **order: Any) -> bool:
        """Point d'extension M3 : remplacer par POST /api/v1/risk/check (jeton lié à l'instance,
        request_id déterministe, délai 500 ms). Toute réponse autre qu'un `accept` valide et non
        expiré doit retourner False. À M2 il n'y a pas de Risk service : dry-run seulement."""
        return self.config.get("dry_run") is True

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
