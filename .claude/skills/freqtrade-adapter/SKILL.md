---
name: freqtrade-adapter
description: How to build and test the Freqtrade adapter and ControlPlaneStrategy for this platform (REST control, webhooks, dry-run, risk hook, AST check). Use when touching packages/adapters/freqtrade or strategies/.
paths:
  - packages/adapters/freqtrade/**
  - strategies/**
---

# Freqtrade adapter

Always verify API details against the docs of the **pinned** `freqtradeorg/freqtrade` tag (use Context7 with `agent-skills:source-driven-development`). Route names and CLI commands change between versions; do not code them from memory.

## Rules
- One container per instance; image tag pinned (monthly tag), never `latest`; dry-run by default; the adapter never turns dry-run off (live goes through the promotion procedure only).
- Control through `freqtrade-client` / REST: start, stop, block new entries, force exit all, status, trades, profit, balance. Map the engine's names to the canonical `EngineAdapter` methods; no Freqtrade names leak into tables, routes or screens.
- Events: ingest webhooks and keep a polling fallback; deduplicate by (engine order id, status); emit canonical events with `client_order_id`, `correlation_id`, decimal strings.
- `ControlPlaneStrategy`: `confirm_trade_entry` calls `POST /api/v1/risk/check` (timeout 500 ms). Any exception, timeout, non-200 or malformed body returns **False** (fail closed). Log the decision id.
- Registry check: reject any strategy version whose class does not inherit `ControlPlaneStrategy` — static AST check plus a test that proves a non-conforming strategy is refused, including aliased imports and indirect inheritance.
- REST credentials for each instance are generated per instance, stored in the SecretStore, never in logs or compose files committed to Git.

## Tests (conformance suite + adapter-specific)
- Start/stop/pause idempotent; engine unreachable => status `unknown`, never `running`.
- Webhook replay produces no duplicate events.
- Risk service down => no entry order is placed (end-to-end with FakeEngine and, when available, Freqtrade dry-run).
- Flatten and pause confirmed by the engine within the configured delay, else container stop + critical alert.
