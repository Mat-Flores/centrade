---
name: freqtrade-adapter
description: How to build and test the Freqtrade adapter and ControlPlaneStrategy for this platform (generated config, exits-only boot, REST control, risk hook, static checks). Use when touching packages/adapters/freqtrade or strategies/.
paths:
  - packages/adapters/freqtrade/**
  - strategies/**
---

# Freqtrade adapter

Source of truth: SPEC.md §7, F9, F10 and annexe C (command mapping, platform-owned keys, verified facts). Read them first. Before coding, re-verify every fact of annexe C against the docs and source of the **pinned** `freqtradeorg/freqtrade` tag (Context7 with `agent-skills:source-driven-development`); record any difference in an ADR. Do not code routes or commands from memory.

## Traps that shape the design (verified on the `stable` branch, 2026-10-10)
- `confirm_trade_entry` is called only for the initial entry of a trade, not for position adjustments or order replacements. Close those paths: `position_adjustment_enable: false`, and the registry rejects strategies that override `adjust_trade_position`, `adjust_entry_price` or `adjust_order_price`.
- An exception raised inside `confirm_trade_entry` means **accept** (Freqtrade falls back to its default return value, `True`). The hook catches everything and returns `False`; it never raises.
- `confirm_trade_exit` can block a stop-loss exit. Strategies may not override it; the platform never blocks an exit (SPEC I4).
- `POST /stop` leaves the bot alive with open trades unmanaged (the `halted` state of F9). Never use it alone: facade `stop` = pause, cancel unfilled entry orders, then stop the container.
- Configuration wins over strategy attributes: platform-owned keys are imposed through the generated config, then read back with `GET /show_config`.

## Rules
- The engine config is produced by `render_config` (pure function) from the manifest, the instance parameters and platform policies. Strategy authors supply only `params_schema` values and the manifest `exits` block.
- Boot in exits-only (`initial_state: paused`). Entries open only after the F9 verification: observed mode, effective config equal to generated config on platform-owned keys, strategy and engine versions matching the fingerprint.
- Mode: derive the dry-run flag from the instance mode enum inside `render_config`. Never write a literal that turns dry-run off: the project hook blocks such edits outside tests, and a paper instance must never receive exchange keys.
- One container per instance, from the hardened template of SPEC §13; image pinned by tag and digest. Keys and REST credentials reach the container as read-only files mounted from memory, never as environment variables.
- Single door (I2): Freqtrade's REST API listens on the engines network only, with per-instance credentials known to the worker; `force_entry_enable: false`; Freqtrade's own Telegram bot disabled; FreqUI reachable by no browser.
- Events: webhooks are hints that trigger a re-read through REST; their content is never the source of truth. Keep a polling fallback, a per-instance sequence number, and resync from a snapshot on any gap. Emit canonical events with `client_order_id` (derived deterministically from the engine order id), `intent`, `decision_id` for entries, decimal strings and currency.
- Risk hook: `confirm_trade_entry` calls `POST /api/v1/risk/check` with a deterministic `request_id` and the instance-bound token (timeout 500 ms). Anything other than a valid, unexpired `accept` returns `False`. Log the decision id.
- Registry static checks (AST) on every strategy version: inherits `ControlPlaneStrategy`; overrides no platform hook (`confirm_trade_entry`, `confirm_trade_exit`, `adjust_trade_position`, `adjust_entry_price`, `adjust_order_price`, `leverage`); imports nothing that opens a network connection or spawns a process. Test aliased imports and indirect inheritance.
- Exit policy (F10): write `stoploss`, trailing settings, `minimal_roi` and `order_types` (stop on venue when supported, emergency and forced exits at market) from the manifest; report per-position protection (stop price, where it lives, state) in every snapshot.

## Tests (conformance suite + adapter-specific)
- Boots in exits-only; no entry before `resume_entries`; `start`/`stop`/`pause_entries` idempotent; engine unreachable => status `unknown`, never `running`.
- Effective config equals generated config on platform-owned keys; a changed key is reported as drift.
- Hook: exception, timeout, non-200, malformed or expired answer => no entry (scenario S11). Risk service down => an exit still executes (S12).
- No entry path escapes the hook; a strategy overriding a platform hook is refused.
- Webhook replay, duplicates and gaps produce no duplicate events and exact projections after resync.
- `flatten` leaves no position; it is never followed by an automatic container stop.
