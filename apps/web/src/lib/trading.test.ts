import { describe, expect, it } from "vitest";

import { exitBreakdown, groupByAccount, sortPositions, totalsByModeCurrency, type Position, type Trade } from "./trading";

const trade = (over: Partial<Trade>): Trade => ({
  id: "t", instance_id: "i1", mode: "paper", account_id: null, account_label: null, instrument: "BTC/USDT", quantity: "1", entry_price: "100", exit_price: "99",
  entry_cause: "signal", exit_cause: "stop_loss", pnl: "-1", fees: "0.1", currency: "USDT", opened_at: "", closed_at: "", duration_s: 1, ...over,
});
const position = (id: string, protection_state: Position["protection_state"]): Position => ({
  id, instance_id: "i1", mode: "paper", account_id: null, account_label: null, instrument: "BTC/USDT", side: "long", quantity: "1", entry_price: "100", currency: "USDT",
  observed_at: "", stale: false, stop_price: null, stop_venue: null, stop_type: null, stop_distance_pct: null, protection_state, protection_verified_at: null,
});

describe("totaux", () => {
  it("ne mélange jamais paper et live, ni les devises", () => {
    const totals = totalsByModeCurrency([
      trade({ pnl: "10.5" }),
      trade({ pnl: "-0.5" }),
      trade({ mode: "live", pnl: "3" }),
      trade({ currency: "EUR", pnl: "7" }),
    ], (t) => t.mode);
    expect(totals.map((t) => [t.mode, t.currency, t.pnl, t.count])).toEqual([
      ["live", "USDT", "3", 1],
      ["paper", "EUR", "7", 1],
      ["paper", "USDT", "10.0", 2],
    ]);
  });
  it("groupe par le mode présenté (observé), pas par le mode voulu porté par la ligne", () => {
    const totals = totalsByModeCurrency([trade({ pnl: "1" }), trade({ pnl: "2" }), trade({ pnl: "4" })], (t) => (t.pnl === "4" ? "unknown" : "live"));
    expect(totals.map((t) => [t.mode, t.pnl, t.count])).toEqual([["live", "3", 2], ["unknown", "4", 1]]);
  });
  it("somme exacte des frais, sans flottant", () => {
    expect(totalsByModeCurrency([trade({ fees: "0.1" }), trade({ fees: "0.2" })], (t) => t.mode)[0]!.fees).toBe("0.3");
  });
  it("aucun trade : aucun total", () => expect(totalsByModeCurrency([], (t) => t.mode)).toEqual([]));
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

describe("regroupement par compte", () => {
  it("un groupe par compte, ordre d'apparition, les lignes sans compte à part", () => {
    const rows = [
      { ...position("a", "protected"), account_id: "A", account_label: "Compte A" },
      position("b", "protected"),
      { ...position("c", "protected"), account_id: "A", account_label: "Compte A" },
    ];
    expect(groupByAccount(rows).map((g) => [g.key, g.label, g.rows.map((r) => r.id)])).toEqual([
      ["A", "Compte A", ["a", "c"]],
      ["", null, ["b"]],
    ]);
  });
});
