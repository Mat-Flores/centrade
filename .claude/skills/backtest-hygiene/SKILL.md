---
name: backtest-hygiene
description: Checklist for judging backtests and strategy code (lookahead, costs, walk-forward, sample size, parameter fragility). Use when reviewing backtests, strategy code, or the F8 reliability report.
---

# Backtest hygiene

A backtest is a hypothesis test, not a forecast. Reject or flag a result when any item fails.

1. **Lookahead / leakage.** Indicators or labels using future bars; resampling that peeks; signals computed on the current candle's close but filled at its open. Use the engine's own lookahead and recursive-analysis tooling when it exists (check the pinned Freqtrade version's docs through Context7) and add an adapter conformance test.
2. **Costs.** Fees, slippage, spread, funding must be explicit and plausible for the venue and size. No costs => flag `unreliable`.
3. **Separation.** Optimization window, validation window and out-of-sample window never overlap. Walk-forward preferred; report per-window metrics, not only the aggregate.
4. **Sample size.** Number of trades and independent episodes. Below the configured minimum => `insufficient_sample`.
5. **Parameter fragility.** Perturb each parameter (+/-10-20 %). A sharp optimum that collapses nearby => `parameter_fragile`.
6. **Regime dependence.** Performance concentrated in one period or one market direction. Separate market exposure (beta) from residual edge when possible.
7. **Execution realism.** Order type, partial fills, minimum notional, exchange rate limits, latency. Backtest fills must not be better than what the live path can obtain.
8. **Paper vs backtest.** After the minimum paper period, divergence beyond the configured threshold blocks promotion (SPEC.md §4 F1).
9. **Reporting.** Never present a metric as expected future return. Always show cost assumptions and the flags.

Output format for a review: verdict (BLOCK/WARN/OK), then findings as `file:line | check # | evidence | fix`.
