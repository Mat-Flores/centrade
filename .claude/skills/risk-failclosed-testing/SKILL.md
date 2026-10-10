---
name: risk-failclosed-testing
description: How to specify and test the Risk service invariants with property-based tests and chaos tests. Use when writing or changing anything under apps/risk or the kill switch.
paths:
  - apps/risk/**
---

# Fail-closed testing for the Risk service

Source of truth: SPEC.md §10, F2, F4 and invariants I4, I5, I6. The rule has two halves, and both are tested: refuse by default what increases risk; never block what reduces it.

## Shape of the code under test
The decision is a pure function of (request, limits, state snapshot, reference prices, now). No clock, randomness, I/O or LLM inside it: pass everything in. Each decision records the hash of the state and the version of the limits it used, so it can be replayed.

## Property tests (Hypothesis)
Generate arbitrary orders, limit sets (global/account/instance), prices, timestamps, reservations and kill-switch states, then assert:
1. kill switch active, or its state unreadable => decision is never `accept`;
2. the effective limit equals the most restrictive of the three levels, whatever the evaluation order;
3. `reduce` never returns a quantity above the requested one or above what the limits allow, and is never emitted when the engine cannot apply it (then `reject`);
4. lowering any limit never turns a `reject` into an `accept`;
5. same input => same decision and same reasons;
6. missing, malformed or out-of-range input => `reject` with an explicit reason;
7. a paper instance can never get an order accepted on a live account;
8. stale state, stale reference price or clock drift beyond the threshold => `reject`;
9. no interleaving of concurrent requests on one account exceeds a limit (accepted orders reserve exposure until observed or expired);
10. the same `request_id` replayed => same decision and a single reservation;
11. a request is evaluated for the instance of the presented token, whatever the body says;
12. an exit, a stop or a position reduction is never refused, delayed or made to wait on the Risk service.
Use `Decimal` strategies; include boundary values (zero, negative, huge, equal to the limit). Round on the prudent side: exposure never down, granted quantity never up.

## Chaos tests (CI profile)
Stop or break, one at a time: the Risk service, Redis, Postgres, the network between the strategy hook and the Risk service; return a malformed body; exceed the 500 ms timeout. Expected every time: no **entry** executed, a critical alert emitted, a `risk_decisions` row or an explicit log when the store is down — and, in the same outage, an exit and a stop still execute.
Add: engine crash with an open position => relaunched in exits-only; FakeEngine modes `rogue_entry`, `ignore_pause`, `lie_mode`, `drift` => detection and the reaction of SPEC F2, F4, F9.

## Kill switch
Layer 1 (Risk service rejects every entry in scope) is effective within 1 s and does not wait for engines. An engine that fails to confirm the pause is escalated, never stopped, unless it enters while entries are blocked. An incomplete flatten never stops the container.

## Unauthorized entry (I6)
Every observed entry order must match one valid, unconsumed `accept` (same instance, instrument and side; quantity at most the granted one; engine order time within validity). Test: no match => `order.unauthorized`, critical alert, entries paused.

## Mutation sanity check
Before closing M3, deliberately flip one comparison in each limit check and confirm at least one test fails. A test suite that survives the mutation is not protecting the invariant.

## Coverage
Branch coverage >= 90 % on apps/risk (SPEC.md §13). Latency p95 < 50 ms measured in a benchmark test.
