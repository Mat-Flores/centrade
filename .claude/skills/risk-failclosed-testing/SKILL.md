---
name: risk-failclosed-testing
description: How to specify and test the Risk service invariants with property-based tests and chaos tests. Use when writing or changing anything under apps/risk or the kill switch.
paths:
  - apps/risk/**
---

# Fail-closed testing for the Risk service

## Property tests (Hypothesis)
Generate arbitrary orders, limit sets (global/account/instance), prices, timestamps and kill-switch states, then assert:
1. kill switch active => decision is never `accept`;
2. the effective limit equals the most restrictive of the three levels, whatever the evaluation order;
3. `reduce` never returns a quantity above the requested one or above what the limits allow;
4. lowering any limit never turns a `reject` into an `accept`;
5. same input => same decision and same reasons (determinism; no clock or randomness inside the decision function — pass time in);
6. missing, malformed or out-of-range input => `reject` with an explicit reason;
7. a paper instance can never get an order accepted on a live account.
Use `Decimal` strategies; include boundary values (zero, negative, huge, equal to the limit).

## Chaos tests (CI profile)
Stop or break, one at a time: the Risk service, Redis, Postgres, the network between the strategy hook and the API; return a malformed body; exceed the 500 ms timeout. Expected every time: no order executed, a critical alert emitted, a `risk_decisions` row or an explicit log when the store is down.

## Mutation sanity check
Before closing M3, deliberately flip one comparison in each limit check and confirm at least one test fails. A test suite that survives the mutation is not protecting the invariant.

## Coverage
Branch coverage >= 90 % on apps/risk (SPEC.md §13). Latency p95 < 50 ms measured in a benchmark test.
