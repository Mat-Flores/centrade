---
paths:
  - apps/risk/**
  - apps/api/**/orders*
  - apps/api/**/risk*
  - packages/adapters/**
---

- Fail closed: on any error, timeout or unknown state, refuse. Never default to accept.
- Money, prices, quantities: Decimal in code, NUMERIC in DB, decimal strings in JSON/events. Never float.
- Every order has a deterministic client_order_id; replays never create a second order.
- Every risk decision is written to risk_decisions with reasons and latency, and shares the correlation_id.
- No LLM, no network call to third parties, and no wall-clock reads inside decision functions.
- Never log secrets, API keys, TOTP, tokens. Use the structlog redaction processor.
