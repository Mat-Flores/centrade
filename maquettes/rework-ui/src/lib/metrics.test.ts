import { describe, expect, it } from "vitest";
import type { Trade } from "../data/types";
import { computeStats } from "./metrics";

const flat = () => 100;
function trade(p: Partial<Trade> & { id: string }): Trade {
  return {
    pair: "X/USDT", strategyId: "s", entryTime: 0, entryPrice: 100, stake: 100, stopLoss: 90, takeProfit: 110,
    fees: 0, pnl: 0, pnlPct: 0, ...p,
  };
}
const closed = (id: string, entry: number, exit: number, pnl: number, cause: Trade["exitCause"] = "signal") =>
  trade({ id, entryTime: entry, exitTime: exit, exitPrice: 100, exitCause: cause, pnl });

describe("computeStats", () => {
  it("entrée vide : tout à zéro, solde = départ", () => {
    const s = computeStats([], 1000, [], flat, 0);
    expect(s).toMatchObject({
      trades: 0, winRate: 0, profitFactor: 0, expectancy: 0, best: 0, worst: 0, sharpe: 0, sortino: 0, calmar: 0,
      maxDrawdownPct: 0, currentDrawdownPct: 0, exposurePct: 0, avgDurationSec: 0, balance: 1000, equity: [],
    });
  });

  // gains 10 + 20, pertes -5 + -15 ; départ 1000
  const trades = [
    closed("a", 0, 100, 10, "take_profit"), closed("b", 100, 300, -5, "stop_loss"),
    closed("c", 300, 400, 20, "take_profit"), closed("d", 400, 700, -15, "stop_loss"),
  ];
  const s = computeStats(trades, 1000, [0, 100, 300, 400, 700], flat, 3);

  it("comptes, taux, moyennes", () => {
    expect(s).toMatchObject({ trades: 4, wins: 2, losses: 2, winRate: 0.5, avgWin: 15, avgLoss: -10, refusedEntries: 3 });
    expect(s.best).toBe(20);
    expect(s.worst).toBe(-15);
    expect(s.expectancy).toBe(2.5);
    expect(s.exitCauses).toEqual({ take_profit: 2, stop_loss: 2 });
  });
  it("rapport gains/pertes = 30 / 20", () => expect(s.profitFactor).toBe(1.5));
  it("encaissé, solde et pourcentages", () => {
    expect(s.realized).toBe(10);
    expect(s.realizedPct).toBeCloseTo(1);
    expect(s.balance).toBe(1010);
    expect(s.unrealized).toBe(0);
  });
  it("durée moyenne : (100+200+100+300)/4", () => expect(s.avgDurationSec).toBe(175));
  it("courbe : 1000, 1010, 1005, 1025, 1010 ; baisse max au dernier point", () => {
    expect(s.equity.map((e) => e.value)).toEqual([1000, 1010, 1005, 1025, 1010]);
    // sommet 1025, creux 1010 : -15/1025
    expect(s.maxDrawdownPct).toBeCloseTo((1010 / 1025 - 1) * 100, 10);
    expect(s.currentDrawdownPct).toBeCloseTo(s.maxDrawdownPct, 10);
  });
  it("aucune perte : rapport gains/pertes infini, sortino 0 (pas de baisse)", () => {
    const w = computeStats([closed("a", 0, 100, 10), closed("b", 100, 200, 5)], 1000, [0, 100, 200], flat, 0);
    expect(w.profitFactor).toBe(Number.POSITIVE_INFINITY);
    expect(w.maxDrawdownPct).toBe(0);
    expect(w.sortino).toBe(0);
    expect(w.calmar).toBe(0);
    expect(w.sharpe).toBeGreaterThan(0);
  });
  it("aucun gain : rapport 0 ; que des nuls : 0", () => {
    expect(computeStats([closed("a", 0, 100, -10)], 1000, [0, 100], flat, 0).profitFactor).toBe(0);
    expect(computeStats([closed("a", 0, 100, 0)], 1000, [0, 100], flat, 0).profitFactor).toBe(0);
  });
  it("écart nul ou moins de 2 rendements : sharpe 0", () => {
    expect(computeStats([], 1000, [0, 100, 200], flat, 0).sharpe).toBe(0);
    expect(computeStats([closed("a", 0, 100, 10)], 1000, [0, 100], flat, 0).sharpe).toBe(0);
  });

  it("position ouverte : latent, exposition, courbe au prix de l'instant", () => {
    const o = trade({ id: "o", entryTime: 100, entryPrice: 100, stake: 200, fees: 0.2, pnl: 9.8 });
    const st = computeStats([o], 1000, [0, 100, 200], (_p, t) => (t === 200 ? 105 : 100), 0);
    expect(st.openPositions).toBe(1);
    expect(st.unrealized).toBeCloseTo(9.8);
    expect(st.balance).toBeCloseTo(1009.8);
    expect(st.exposurePct).toBeCloseTo((200 / 1009.8) * 100, 8);
    // t=100 : prix 100, seulement les frais d'achat ; t=200 : 200/100*5 - 0.2
    expect(st.equity.map((e) => e.value)).toEqual([1000, 999.8, 1009.8]);
    expect(st.trades).toBe(0);
    expect(st.fees).toBeCloseTo(0.2);
  });
  it("sharpe : valeur calculée à la main", () => {
    // courbe 1000, 1010, 1010+... on prend pas 3600 s : rendements r1=+1 %, r2=-0,5 % approx
    const tr = [closed("a", 0, 3600, 10), closed("b", 3600, 7200, -5.05)];
    const st = computeStats(tr, 1000, [0, 3600, 7200], flat, 0);
    const r = [1010 / 1000 - 1, 1004.95 / 1010 - 1];
    const m = (r[0] + r[1]) / 2;
    const sd = Math.sqrt(((r[0] - m) ** 2 + (r[1] - m) ** 2) / 1);
    expect(st.sharpe).toBeCloseTo((m / sd) * Math.sqrt((365 * 24)), 8);
    const down = Math.sqrt((r[1] ** 2) / 2);
    expect(st.sortino).toBeCloseTo((m / down) * Math.sqrt(365 * 24), 8);
  });
});
