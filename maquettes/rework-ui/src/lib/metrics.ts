import type { ExitCause, PairStats, Trade } from "../data/types";

const YEAR_SEC = 365 * 86400; // crypto : 365 jours

function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}

/** Solde aux instants donnés : départ + encaissé à l'instant + latent des positions alors ouvertes. */
function equityCurve(trades: Trade[], startBalance: number, times: number[], priceAt: (pair: string, t: number) => number) {
  return times.map((time) => {
    let value = startBalance;
    for (const t of trades) {
      if (t.entryTime > time) continue;
      if (t.exitTime !== undefined && t.exitTime <= time) value += t.pnl;
      else value += (t.stake / t.entryPrice) * (priceAt(t.pair, time) - t.entryPrice) - t.fees / (t.exitTime === undefined ? 1 : 2);
    }
    return { time, value };
  });
}

/** Reculs depuis un sommet, en pourcent du sommet et en devise. */
function drawdowns(values: number[], startBalance: number): { max: number; current: number; maxAmount: number; currentAmount: number } {
  let peak = startBalance;
  let max = 0, maxAmount = 0;
  let dd = 0, amount = 0;
  for (const v of values) {
    peak = Math.max(peak, v);
    dd = (v / peak - 1) * 100;
    amount = v - peak;
    if (dd < max) { max = dd; maxAmount = amount; }
  }
  return { max, current: dd, maxAmount, currentAmount: amount };
}

function ratios(values: number[], times: number[], maxDdPct: number) {
  const r = values.slice(1).map((v, i) => v / values[i] - 1);
  if (r.length < 2) return { sharpe: 0, sortino: 0, calmar: 0 };
  const perYear = YEAR_SEC / (times[1] - times[0]);
  const m = mean(r);
  const sd = Math.sqrt(r.reduce((a, x) => a + (x - m) ** 2, 0) / (r.length - 1));
  const down = Math.sqrt(mean(r.map((x) => Math.min(x, 0) ** 2)));
  const annualReturn = (values[values.length - 1] / values[0] - 1) * (YEAR_SEC / (times[times.length - 1] - times[0]));
  return {
    sharpe: sd > 0 ? (m / sd) * Math.sqrt(perYear) : 0,
    sortino: down > 0 ? (m / down) * Math.sqrt(perYear) : 0,
    calmar: maxDdPct < 0 ? annualReturn / (Math.abs(maxDdPct) / 100) : 0,
  };
}

/**
 * `trades` : tels qu'on les voit au curseur (ouverts = sans sortie, résultat latent).
 * Pourcentages en pourcent (3,2 = 3,2 %), sauf winRate (0 à 1).
 */
export function computeStats(
  trades: Trade[],
  startBalance: number,
  equityTimes: number[],
  priceAt: (pair: string, t: number) => number,
  refusedEntries: number,
): PairStats {
  const closed = trades.filter((t) => t.exitTime !== undefined);
  const open = trades.filter((t) => t.exitTime === undefined);
  const wins = closed.filter((t) => t.pnl > 0);
  const losses = closed.filter((t) => t.pnl <= 0);
  const gains = wins.reduce((a, t) => a + t.pnl, 0);
  const lossSum = losses.reduce((a, t) => a + t.pnl, 0);
  const realized = closed.reduce((a, t) => a + t.pnl, 0);
  const unrealized = open.reduce((a, t) => a + t.pnl, 0);
  const balance = startBalance + realized + unrealized;
  const exposure = open.reduce((a, t) => a + t.stake, 0);
  const equity = equityCurve(trades, startBalance, equityTimes, priceAt);
  const values = equity.map((e) => e.value);
  const dd = drawdowns(values, startBalance);
  const exitCauses: Partial<Record<ExitCause, number>> = {};
  for (const t of closed) exitCauses[t.exitCause!] = (exitCauses[t.exitCause!] ?? 0) + 1;
  const pct = (x: number) => (x / startBalance) * 100;

  return {
    trades: closed.length,
    wins: wins.length,
    losses: losses.length,
    winRate: closed.length ? wins.length / closed.length : 0,
    avgWin: mean(wins.map((t) => t.pnl)),
    avgLoss: mean(losses.map((t) => t.pnl)),
    profitFactor: lossSum < 0 ? gains / Math.abs(lossSum) : gains > 0 ? Number.POSITIVE_INFINITY : 0,
    expectancy: mean(closed.map((t) => t.pnl)),
    best: closed.length ? Math.max(...closed.map((t) => t.pnl)) : 0,
    worst: closed.length ? Math.min(...closed.map((t) => t.pnl)) : 0,
    ...ratios(values, equityTimes, dd.max),
    maxDrawdownPct: dd.max,
    maxDrawdown: dd.maxAmount,
    currentDrawdownPct: dd.current,
    currentDrawdown: dd.currentAmount,
    exposurePct: balance > 0 ? (exposure / balance) * 100 : 0,
    exposure,
    openPositions: open.length,
    avgDurationSec: mean(closed.map((t) => t.exitTime! - t.entryTime)),
    fees: trades.reduce((a, t) => a + t.fees, 0),
    refusedEntries,
    exitCauses,
    realized,
    realizedPct: pct(realized),
    unrealized,
    unrealizedPct: pct(unrealized),
    balance,
    equity,
  };
}
