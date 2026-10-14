import { describe, expect, it } from "vitest";

import { iso, makeInstance, NOW } from "@/test/factories";

import { groupByMode, groupTotals, summarizeRow } from "./instance-stats";
import type { Balance, Instance, Money } from "./instances";

const pnl = (money: Money[] | null, age: number | null = 2): Instance["realized_pnl"] => ({ value: money, observed_at: age === null ? null : iso(age), stale: false });
const bal = (balances: Balance[] | null, age: number | null = 2): Instance["balances"] => ({ value: balances, observed_at: age === null ? null : iso(age), stale: false });
const usdt = (amount: string): Money => ({ currency: "USDT", amount, fees: "0" });

describe("groupByMode", () => {
  it("puts paper instances under Dry-run and live ones under Live, Dry-run first", () => {
    const groups = groupByMode([makeInstance({ id: "1", desired_mode: "live" }), makeInstance({ id: "2" })]);
    expect(groups.map((g) => [g.label, g.instances.map((i) => i.id)])).toEqual([["Dry-run", ["2"]], ["Live", ["1"]]]);
  });

  it("leaves out a mode with no instance", () => {
    expect(groupByMode([makeInstance()]).map((g) => g.mode)).toEqual(["paper"]);
  });
});

describe("summarizeRow", () => {
  it("says the observed state, and shows the wanted state only as a wish when it differs", () => {
    const row = summarizeRow(makeInstance({ stateValue: "exits_only", desired_state: "running" }), NOW);
    expect(row.state).toBe("sorties seules");
    expect(row.wanted).toBe("voulu : en marche");
    expect(summarizeRow(makeInstance({ stateValue: "running", desired_state: "running" }), NOW).wanted).toBeNull();
  });

  it("never presents the wanted state as the real one when the observed state is unknown", () => {
    const row = summarizeRow(makeInstance({ age: null, desired_state: "running" }), NOW);
    expect(row.state).toBe("inconnu");
    expect(row.state).not.toContain("en marche");
    expect(row.wanted).toBe("voulu : en marche");
  });

  it("marks a stale state as stale instead of showing it as current", () => {
    expect(summarizeRow(makeInstance({ age: 120 }), NOW).state).toBe("en marche (périmé)");
  });

  it("shows unknown, never zero, when aggregates were never observed", () => {
    const row = summarizeRow(makeInstance({ age: null }), NOW);
    expect([row.openPositions, row.closedTrades, ...row.pnl, ...row.balancesText]).toEqual(["inconnu", "inconnu", "inconnu", "inconnu"]);
    expect(row.balances).toBeNull();
  });

  it("shows known zero as zero, and no closed trade as such", () => {
    const row = summarizeRow(makeInstance({}), NOW);
    expect(row.openPositions).toBe("0 position ouverte");
    expect(row.pnl).toEqual(["aucun trade terminé"]);
  });

  it("formats the realized PnL per currency without adding across currencies", () => {
    const row = summarizeRow(
      makeInstance({ realized_pnl: pnl([usdt("12.5"), { currency: "BTC", amount: "-0.001", fees: "0" }]) }),
      NOW,
    );
    expect(row.pnl).toHaveLength(2);
    expect(row.pnl[0]).toContain("USDT");
    expect(row.pnl[1]).toContain("BTC");
  });

  it("adds the stale mention to a stale PnL and a stale count", () => {
    const row = summarizeRow(makeInstance({ realized_pnl: pnl([usdt("1")], 200), open_positions: { value: 2, observed_at: iso(200), stale: false } }), NOW);
    expect(row.pnl[0]).toMatch(/\(périmé\)$/);
    expect(row.openPositions).toBe("2 positions ouvertes (périmé)");
  });

  it("treats a value without an observation date as unknown", () => {
    expect(summarizeRow(makeInstance({ open_positions: { value: 3, observed_at: null, stale: false } }), NOW).openPositions).toBe("inconnu");
  });

  it("formats balances when present and reports them unknown when absent", () => {
    const withBalances = summarizeRow(makeInstance({ balances: bal([{ currency: "USDT", free: "10", total: "12.50" }]) }), NOW);
    expect(withBalances.balancesText[0]).toContain("12,50");
    expect(summarizeRow(makeInstance({}), NOW).balancesText).toEqual(["inconnu"]);
  });
});

describe("groupTotals", () => {
  const group = (instances: Instance[]) => groupByMode(instances)[0]!;

  it("sums exactly per currency, never across currencies", () => {
    const t = groupTotals(
      group([
        makeInstance({ id: "1", realized_pnl: pnl([usdt("0.1")]) }),
        makeInstance({ id: "2", realized_pnl: pnl([usdt("0.2"), { currency: "BTC", amount: "1", fees: "0" }]) }),
      ]),
      NOW,
    );
    expect(t.pnl.map((x) => [x.currency, x.amount])).toEqual([["BTC", "1"], ["USDT", "0.3"]]);
  });

  it("leaves unknown values out of the sum and counts them, instead of adding zero", () => {
    const t = groupTotals(group([makeInstance({ id: "1", realized_pnl: pnl([usdt("5")]) }), makeInstance({ id: "2", age: null })]), NOW);
    expect(t.pnl.map((x) => x.amount)).toEqual(["5"]);
    expect(t.unknownPnl).toBe(1);
  });

  it("counts stale instances so the total is not read as current", () => {
    const t = groupTotals(group([makeInstance({ realized_pnl: pnl([usdt("5")], 300) })]), NOW);
    expect(t.staleCount).toBe(1);
  });

  it("only sums instances of the group's mode and keeps out an instance whose observed mode differs", () => {
    const paper = makeInstance({ id: "1", realized_pnl: pnl([usdt("5")]) });
    const mismatched = makeInstance({ id: "2", mode_mismatch: true, realized_pnl: pnl([usdt("1000")]) });
    const live = makeInstance({ id: "3", desired_mode: "live", realized_pnl: pnl([usdt("7")]) });
    const groups = groupByMode([paper, mismatched, live]);
    const [dry, liveGroup] = groups.map((g) => groupTotals(g, NOW));
    expect(dry!.pnl[0]!.amount).toBe("5");
    expect(dry!.mismatchCount).toBe(1);
    expect(liveGroup!.pnl[0]!.amount).toBe("7");
  });

  it("sums balances per currency", () => {
    const t = groupTotals(
      group([
        makeInstance({ id: "1", balances: bal([{ currency: "USDT", free: "1", total: "10.1" }]) }),
        makeInstance({ id: "2", balances: bal([{ currency: "USDT", free: "1", total: "0.2" }]) }),
      ]),
      NOW,
    );
    expect(t.balances[0]!.amount).toBe("10.3");
  });
});
