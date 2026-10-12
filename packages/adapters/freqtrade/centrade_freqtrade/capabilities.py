"""Capacités de Freqtrade sur le tag épinglé (ADR 0008)."""

from centrade_core.engine.types import Capabilities

# Exchanges dont la classe déclare `stoploss_on_exchange: True` au tag 2026.9.
_STOP_ON_VENUE = ("binance", "bingx", "bitget", "bybit", "gate", "htx", "hyperliquid",
                  "kraken", "kucoin", "okx")  # fmt: skip


def capabilities() -> Capabilities:
    return Capabilities(
        asset_classes=("crypto",),
        modes=("backtest", "paper", "live"),
        supports_flatten=True,  # POST /forceexit, tradeid "all"
        supports_pause_entries=True,  # POST /pause
        event_transport="poll",  # relevé REST qui fait foi ; le webhook n'est qu'un indice
        hot_reload=False,
        risk_enforcement="hook",
        boots_exits_only=True,  # initial_state "paused"
        reports_effective_config=True,  # GET /show_config, partiel : voir config.OBSERVABLE_KEYS
        supports_reduce=True,  # POST /forceexit accepte `amount`
        supports_close_position=True,
        supports_cancel_entry_order=True,  # attention : DELETE /trades/<id>/open-order annule tout
        stop_on_venue=dict.fromkeys(_STOP_ON_VENUE, True),  # inerte en dry-run (ADR 0008)
        native_limits=("stake_amount", "max_open_trades", "available_capital", "stoploss"),
        supports_sandbox=True,
    )
