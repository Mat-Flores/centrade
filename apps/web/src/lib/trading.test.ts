import { describe, expect, it } from "vitest";

import { exitBreakdown, sortPositions, totalsByModeCurrency, type Position, type Trade } from "./trading";

const trade = (over: Partial<Trade>): Trade => ({
  id: "t", instance_id: "i1", mode: "paper", instrument: "BTC/USDT", quantity: "1", entry_price: "100", exit_price: "99",
  entry_cause: "signal", exit_cause: "stop_loss", pnl: "-1", fees: "0.1", currency: "USDT", opened_at: "", closed_at: "", duration_s: 1, ...over,
});
const position = (id: string, protection_state: Position["protection_state"]): Position => ({
  id, instance_id: "i1", mode: "paper", instrument: "BTC/USDT", side: "long", quantity: "1", entry_price: "100", currency: "USDT",
  observed_at: "", stale: false, stop_price: null, stop_venue: null, stop_type: null, stop_distance_pct: null, protection_state, protection_verified_at: null,
});

describe("totaux", () => {
  it("ne mélange jamais paper et live, ni les devises", () => {
    const totals = totalsByModeCurrency([
      trade({ pnl: "10.5" }),
      trade({ pnl: "-0.5" }),
      trade({ mode: "live", pnl: "3" }),
      trade({ currency: "EUR", pnl: "7" }),
    ]);
    expect(totals.map((t) => [t.mode, t.currency, t.pnl, t.count])).toEqual([
      ["live", "USDT", "3", 1],
      ["paper", "EUR", "7", 1],
      ["paper", "USDT", "10.0", 2],
    ]);
  });
  it("somme exacte des frais, sans flottant", () => {
    expect(totalsByModeCurrency([trade({ fees: "0.1" }), trade({ fees: "0.2" })])[0]!.fees).toBe("0.3");
  });
  it("aucun trade : aucun total", () => expect(totalsByModeCurrency([])).toEqual([]));
});

describe("positions", () => {
  it("les non protégées en tête, puis inconnues, moteur seul, protégées ; ordre stable", () => {
    const sorted = sortPositions([position("a", "protected"), position("b", "unknown"), position("c", "unprotected"), position("d", "engine_only"), position("e", "unprotected")]);
    expect(sorted.map((p) => p.id)).toEqual(["c", "e", "b", "d", "a"]);
  });
});

describe("répartition des sorties", () => {
  it("compte par instance et par cause, la plus fréquente d'abord", () => {
    const out = exitBreakdown([trade({}), trade({}), trade({ exit_cause: "take_profit" }), trade({ instance_id: "i2", exit_cause: "manual" })]);
    expect(out).toEqual([
      { instanceId: "i1", total: 3, causes: [{ cause: "stop_loss", count: 2 }, { cause: "take_profit", count: 1 }] },
      { instanceId: "i2", total: 1, causes: [{ cause: "manual", count: 1 }] },
    ]);
  });
});
