import { describe, expect, it } from "vitest";
import type { Candle, Trade } from "../data/types";
import { candleIndexAt, overlaps, pathPoints, pickRect } from "./geometry";

const candles: Candle[] = [0, 1, 2, 3, 4, 5].map((i) => ({ time: 1000 + i * 300, open: 100, high: 110, low: 90, close: 100 + i }));
const base: Trade = { id: "a", pair: "BTC/USDT", strategyId: "s", entryTime: 1350, entryPrice: 99, stake: 1000, stopLoss: 95, takeProfit: 108, fees: 1, pnl: 0, pnlPct: 0 };

describe("candleIndexAt", () => {
  it("prend la bougie qui contient l'instant, bornée aux extrémités", () => {
    expect(candleIndexAt(candles, 1000)).toBe(0);
    expect(candleIndexAt(candles, 1299)).toBe(0);
    expect(candleIndexAt(candles, 1300)).toBe(1);
    expect(candleIndexAt(candles, 1)).toBe(0);
    expect(candleIndexAt(candles, 99999)).toBe(5);
  });
});

describe("pathPoints", () => {
  it("trade fermé : entrée, clôtures intermédiaires, sortie", () => {
    const p = pathPoints(candles, { ...base, exitTime: 2400, exitPrice: 106 });
    expect(p).toEqual([
      { time: 1300, price: 99 },
      { time: 1600, price: 102 },
      { time: 1900, price: 103 },
      { time: 2200, price: 106 },
    ]);
  });
  it("trade ouvert : va jusqu'à la dernière clôture", () => {
    const p = pathPoints(candles, base);
    expect(p[0]).toEqual({ time: 1300, price: 99 });
    expect(p[p.length - 1]).toEqual({ time: 2500, price: 105 });
  });
  it("aucune bougie : aucun point", () => expect(pathPoints([], base)).toEqual([]));
});

describe("overlaps / pickRect", () => {
  it("écarte un trade terminé avant la première bougie", () => {
    expect(overlaps(candles, { ...base, entryTime: 10, exitTime: 500 })).toBe(false);
    expect(overlaps(candles, base)).toBe(true);
  });
  it("choisit la plus petite zone touchée", () => {
    const big = { id: "big", rect: { x1: 0, x2: 100, y1: 0, y2: 100 } };
    const small = { id: "small", rect: { x1: 40, x2: 60, y1: 40, y2: 60 } };
    expect(pickRect([big, small], 50, 50)?.id).toBe("small");
    expect(pickRect([big, small], 10, 10)?.id).toBe("big");
    expect(pickRect([big, small], 300, 300)).toBeNull();
  });
});
