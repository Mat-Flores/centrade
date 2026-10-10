---
paths:
  - apps/risk/**
  - apps/worker/**
  - apps/api/**/orders*
  - apps/api/**/risk*
  - packages/adapters/**
---

- Fail closed for anything that increases risk (entry, position increase, limit raise): on any error, timeout, stale or unknown state, refuse. Never default to accept.
- Never block an exit, a stop or a position reduction: no risk check, limit, outage or kill switch stands in their way (SPEC I4).
- The calling instance comes from the presented token, never from the request body.
- An accept is valid for one order, a maximum quantity and a short time; it reserves exposure until the order is observed or it expires. Decisions for one account are serialized.
- Never stop an engine container that holds open positions as an automatic reaction, except an engine that enters while entries are blocked (SPEC F4).
- The platform never calls an order function of a venue library (SPEC I11).
- Money, prices, quantities: Decimal in code, NUMERIC in DB, decimal strings in JSON/events. Never float.
- Every order has a deterministic client_order_id; replays never create a second order.
- Every risk decision is written to risk_decisions with reasons and latency, and shares the correlation_id.
- No LLM, no network call to third parties, and no wall-clock reads inside decision functions.
- Never log secrets, API keys, TOTP, tokens. Use the structlog redaction processor.
