import { describe, expect, it } from "vitest";
import { BASE_STEP, EPOCH, PAIRS, aggregate, candles5m, candlesFor, priceAt, simulateTrades, viewTrade } from "./sim";
import type { Strategy } from "./types";

const strat: Strategy = {
  id: "s", name: "S", description: "", timeframe: "1h", extraTimeframes: [],
  stopLossPct: 3, takeProfitPct: 6, params: { rapide: 9, lente: 21 },
};
const input = { pair: "BTC/USDT", strategy: strat, stakePerTrade: 250, feePct: 0.1, slippagePct: 0.05, from: EPOCH, to: EPOCH + 30 * 86400 };

describe("séries", () => {
  it("8 paires, 8640 bougies, déterministes", () => {
    expect(PAIRS).toHaveLength(8);
    expect(candles5m("BTC/USDT")).toHaveLength(8640);
    expect(candles5m("ETH/USDT")[100]).toEqual(candles5m("ETH/USDT")[100]);
    expect(candles5m("BTC/USDT")[0].time).toBe(EPOCH);
  });
  it("bougies cohérentes et prix plausibles", () => {
    for (const p of PAIRS) {
      const s = candles5m(p);
      expect(s.every((c) => c.low <= Math.min(c.open, c.close) && c.high >= Math.max(c.open, c.close) && c.low > 0)).toBe(true);
      const last = s[s.length - 1].close;
      expect(last / s[0].open).toBeGreaterThan(0.5);
      expect(last / s[0].open).toBeLessThan(2);
    }
  });
});

describe("aggregate / candlesFor", () => {
  it("agrège 12 bougies de 5 min en 1 h", () => {
    const c5 = candles5m("BTC/USDT").slice(0, 12);
    const [h] = aggregate(c5, "1h");
    expect(h).toEqual({
      time: EPOCH, open: c5[0].open, close: c5[11].close,
      high: Math.max(...c5.map((c) => c.high)), low: Math.min(...c5.map((c) => c.low)),
    });
  });
  it("la dernière bougie est partielle", () => {
    const c = candlesFor("BTC/USDT", "1h", EPOCH + 3600 + 2 * BASE_STEP);
    expect(c).toHaveLength(2);
    expect(c[1].close).toBe(candles5m("BTC/USDT")[14].close);
    expect(c[1].time).toBe(EPOCH + 3600);
  });
  it("rien avant le début, tout à la fin", () => {
    expect(candlesFor("BTC/USDT", "5m", EPOCH - 1)).toHaveLength(0);
    expect(candlesFor("BTC/USDT", "1j", EPOCH + 40 * 86400)).toHaveLength(30);
    expect(priceAt("BTC/USDT", EPOCH + 10 * BASE_STEP)).toBe(candles5m("BTC/USDT")[10].close);
  });
});

describe("simulateTrades", () => {
  const trades = simulateTrades(input);
  it("produit des trades complets, un à la fois, avec gains et pertes", () => {
    expect(trades.length).toBeGreaterThan(3);
    expect(trades.some((t) => t.pnl > 0) && trades.some((t) => t.pnl < 0)).toBe(true);
    trades.forEach((t, i) => {
      expect(t.exitTime).toBeGreaterThan(t.entryTime);
      expect(t.fees).toBeCloseTo(0.5);
      if (i) expect(t.entryTime).toBeGreaterThanOrEqual(trades[i - 1].exitTime!);
    });
  });
  it("est déterministe et respecte la fenêtre", () => {
    expect(simulateTrades(input)).toEqual(trades);
    const w = simulateTrades({ ...input, from: EPOCH + 10 * 86400, to: EPOCH + 20 * 86400 });
    expect(w.every((t) => t.entryTime >= EPOCH + 10 * 86400 && t.exitTime! <= EPOCH + 20 * 86400)).toBe(true);
  });
});

describe("viewTrade", () => {
  const t = simulateTrades(input)[0];
  it("caché avant l'entrée", () => expect(viewTrade(t, t.entryTime - 1, 1)).toBeNull());
  it("ouvert entre l'entrée et la sortie", () => {
    const v = viewTrade(t, t.entryTime, t.entryPrice * 1.01)!;
    expect(v.exitTime).toBeUndefined();
    expect(v.exitCause).toBeUndefined();
    expect(v.fees).toBeCloseTo(t.fees / 2);
    expect(v.pnl).toBeCloseTo(t.stake * 0.01 - t.fees / 2);
  });
  it("inchangé après la sortie", () => expect(viewTrade(t, t.exitTime!, 1)).toBe(t));
});
