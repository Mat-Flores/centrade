"""Freqtrade capabilities on the pinned tag (ADR 0008)."""

from centrade_core.engine.types import Capabilities

# Exchanges whose class declares `stoploss_on_exchange: True` at tag 2026.9.
_STOP_ON_VENUE = ("binance", "bingx", "bitget", "bybit", "gate", "htx", "hyperliquid",
                  "kraken", "kucoin", "okx")  # fmt: skip


def capabilities() -> Capabilities:
    return Capabilities(
        asset_classes=("crypto",),
        modes=("backtest", "paper", "live"),
        supports_flatten=True,  # POST /forceexit, tradeid "all"
        supports_pause_entries=True,  # POST /pause
        event_transport="poll",  # REST snapshot is authoritative; the webhook is only a hint
        hot_reload=False,
        risk_enforcement="hook",
        boots_exits_only=True,  # initial_state "paused"
        reports_effective_config=True,  # GET /show_config, partial: see config.OBSERVABLE_KEYS
        supports_reduce=True,  # POST /forceexit accepts `amount`
        supports_close_position=True,
        supports_cancel_entry_order=True,  # note: DELETE /trades/<id>/open-order cancels all
        stop_on_venue=dict.fromkeys(_STOP_ON_VENUE, True),  # inert in dry-run (ADR 0008)
        native_limits=("stake_amount", "max_open_trades", "available_capital", "stoploss"),
        supports_sandbox=True,
    )
