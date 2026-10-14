import { describe, expect, it } from "vitest";

import { iso, makeCommand, makeInstance, NOW } from "@/test/factories";

import { needsAttention, observedTip, rowAction, rowCommand, visibleRows } from "./instance-row";

const none: ReadonlySet<string> = new Set();
const ctx = { degraded: false, nowMs: NOW, role: "operator" as const, busy: false };

describe("rowCommand: no optimism (I8)", () => {
  it.each(["requested", "dispatched", "acknowledged"] as const)("a %s command is only 'demandé'", (status) => {
    expect(rowCommand(makeInstance(), [makeCommand({ status })], none, NOW)?.text).toBe("demandé");
  });

  it("says 'fait' only for a verified command, and only for a short while", () => {
    const verified = makeCommand({ status: "verified", requested_at: iso(10) });
    expect(rowCommand(makeInstance(), [verified], none, NOW)?.text).toBe("fait");
    expect(rowCommand(makeInstance(), [{ ...verified, requested_at: iso(600) }], none, NOW)).toBeNull();
  });

  it("keeps an unseen failure and an unseen timeout until they are seen", () => {
    const failed = makeCommand({ id: "f", status: "failed", requested_at: iso(900), result: { reason: "engine refused" } });
    const late = makeCommand({ id: "t", status: "timed_out", requested_at: iso(1200) });
    expect(rowCommand(makeInstance(), [failed], none, NOW)).toMatchObject({ text: "échec", tone: "problem", reason: "engine refused" });
    expect(rowCommand(makeInstance(), [late], none, NOW)?.text).toBe("expirée");
    expect(rowCommand(makeInstance(), [failed], new Set(["f"]), NOW)).toBeNull();
  });

  it("ignores the commands of other instances", () => {
    expect(rowCommand(makeInstance(), [makeCommand({ instance_id: "other" })], none, NOW)).toBeNull();
  });
});

describe("needsAttention and visibleRows", () => {
  it("flags an error state, a mode mismatch and an unseen failure", () => {
    expect(needsAttention(makeInstance({ stateValue: "error" }), [], none, NOW)).toBe(true);
    expect(needsAttention(makeInstance({ mode_mismatch: true }), [], none, NOW)).toBe(true);
    expect(needsAttention(makeInstance(), [makeCommand({ status: "failed" })], none, NOW)).toBe(true);
    expect(needsAttention(makeInstance(), [], none, NOW)).toBe(false);
  });

  it("puts rows needing attention first, filters by name, and keeps the server order otherwise", () => {
    const rows = [makeInstance({ id: "1", name: "alpha" }), makeInstance({ id: "2", name: "beta", stateValue: "error" }), makeInstance({ id: "3", name: "alpine" })];
    expect(visibleRows(rows, "", [], none, NOW).map((i) => i.id)).toEqual(["2", "1", "3"]);
    expect(visibleRows(rows, " AL ", [], none, NOW).map((i) => i.id)).toEqual(["1", "3"]);
  });
});

describe("rowAction: from the observed state, refusal by default", () => {
  it("offers to open an unknown, halted or faulty instance, never an action", () => {
    expect(rowAction(makeInstance({ age: null }), ctx)).toEqual({ kind: "open" });
    expect(rowAction(makeInstance({ stateValue: "error" }), ctx)).toEqual({ kind: "open" });
    expect(rowAction(makeInstance({ stateValue: "halted" }), ctx)).toEqual({ kind: "open" });
  });

  it("offers the action that matches the observed state", () => {
    expect(rowAction(makeInstance({ stateValue: "stopped" }), ctx)).toMatchObject({ action: "start", enabled: true });
    expect(rowAction(makeInstance({ stateValue: "exits_only" }), ctx)).toMatchObject({ action: "resume_entries", enabled: true });
    expect(rowAction(makeInstance({ stateValue: "running" }), ctx)).toMatchObject({ action: "pause_entries", enabled: true });
    expect(rowAction(makeInstance({ stateValue: "starting" }), ctx)).toEqual({ kind: "starting" });
  });

  it("refuses to reopen entries on a stale state or in degraded mode, but never refuses to pause", () => {
    expect(rowAction(makeInstance({ stateValue: "exits_only", age: 120 }), ctx)).toMatchObject({ action: "resume_entries", enabled: false });
    expect(rowAction(makeInstance({ stateValue: "exits_only" }), { ...ctx, degraded: true })).toMatchObject({ enabled: false });
    expect(rowAction(makeInstance({ stateValue: "running" }), { ...ctx, degraded: true })).toMatchObject({ action: "pause_entries", enabled: true });
  });

  it("gives a viewer no action and blocks a second request while one is in flight", () => {
    expect(rowAction(makeInstance(), { ...ctx, role: "viewer" })).toEqual({ kind: "open" });
    expect(rowAction(makeInstance(), { ...ctx, busy: true })).toMatchObject({ enabled: false });
  });
});

describe("observedTip", () => {
  it("dates a value, says when it is stale, and says nothing for a value never observed", () => {
    expect(observedTip({ value: 1, observed_at: iso(3), stale: false }, NOW)).toBe("Observé il y a 3 s");
    expect(observedTip({ value: 1, observed_at: iso(150), stale: false }, NOW)).toBe("périmé depuis 2 min");
    expect(observedTip({ value: null, observed_at: null, stale: false }, NOW)).toBeNull();
  });
});
