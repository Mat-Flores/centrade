import { describe, expect, it } from "vitest";

import { makeInstance, NOW } from "@/test/factories";

import { connectionSummary } from "./connection";

const calm = { degraded: false, causes: [] };
const silent = { degraded: true, causes: ["stream" as const] };

describe("connectionSummary", () => {
  it("says 'Session ouverte' with a neutral dot while nothing is loaded", () => {
    expect(connectionSummary(undefined, calm, NOW)).toMatchObject({ tone: "neutral", text: "Session ouverte" });
  });

  it("counts fresh over running bots and turns green only when all are fresh", () => {
    const rows = [makeInstance({ id: "1" }), makeInstance({ id: "2" })];
    expect(connectionSummary(rows, calm, NOW)).toMatchObject({ tone: "ok", text: "2/2 bots" });
  });

  it("warns, never a green dot, when a running bot is stale or unknown", () => {
    const rows = [makeInstance({ id: "1" }), makeInstance({ id: "2", age: 120 }), makeInstance({ id: "3", age: null })];
    const c = connectionSummary(rows, calm, NOW);
    expect(c.tone).toBe("warn");
    expect(c.text).toBe("1/3 bots · périmé");
    expect(c.tip).toContain("2 bots");
  });

  it("does not count a stopped instance that is wanted stopped", () => {
    const rows = [makeInstance({ id: "1" }), makeInstance({ id: "2", stateValue: "stopped", desired_state: "stopped" })];
    expect(connectionSummary(rows, calm, NOW).text).toBe("1/1 bots");
  });

  it("warns on a silent stream even when every bot is fresh", () => {
    expect(connectionSummary([makeInstance()], silent, NOW)).toMatchObject({ tone: "warn" });
  });

  it("keeps a neutral dot when no bot runs", () => {
    const rows = [makeInstance({ stateValue: "stopped", desired_state: "stopped" })];
    expect(connectionSummary(rows, calm, NOW)).toMatchObject({ tone: "neutral", text: "Session ouverte" });
  });
});
