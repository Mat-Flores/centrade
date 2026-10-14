import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import {
  actionPolicy,
  applyStreamMessage,
  countByState,
  currentCommand,
  degradation,
  deriveEngines,
  deriveMode,
  shownMode,
  describeCommand,
  stateView,
  unseenProblems,
  upsertCommand,
  wantedDiffers,
} from "./cockpit";
import { alertsKey, commandsKey, instancesKey, type Alert, type Command, type Instance, type Page } from "./instances";
import { iso, makeCommand, makeInstance, NOW } from "@/test/factories";

const instance = makeInstance;
const command = makeCommand;

describe("describeCommand: never done before verified (I8)", () => {
  it.each(["requested", "dispatched", "acknowledged"] as const)("%s stays pending", (status) => {
    expect(describeCommand(command({ status }), NOW).tone).toBe("pending");
  });

  it("verified is the only done command", () => {
    expect(describeCommand(command({ status: "verified", verified_at: iso(1) }), NOW).tone).toBe("done");
  });

  it.each(["failed", "timed_out"] as const)("%s is a problem with its reason", (status) => {
    const view = describeCommand(command({ status, result: { reason: "engine silent" } }), NOW);
    expect(view).toMatchObject({ tone: "problem", reason: "engine silent" });
  });

  it("a problem without a reason does not invent one", () => {
    expect(describeCommand(command({ status: "timed_out", result: null }), NOW)).toMatchObject({ reason: null });
  });

  it("the age counts from the request", () => {
    expect(describeCommand(command({ requested_at: iso(42) }), NOW).ageMs).toBe(42_000);
  });
});

describe("commands: most advanced version, unseen failures", () => {
  it("an older version never replaces a newer one", () => {
    const verified = command({ status: "verified", verified_at: iso(1), dispatched_at: iso(8), acknowledged_at: iso(5) });
    const older = command({ status: "acknowledged", dispatched_at: iso(8), acknowledged_at: iso(5) });
    expect(upsertCommand([verified], older)[0]!.status).toBe("verified");
    expect(upsertCommand([older], verified)[0]!.status).toBe("verified");
  });

  it("the instance's active command and the list complement each other", () => {
    const fromList = command({ status: "dispatched", dispatched_at: iso(8) });
    const active = command({ status: "acknowledged", dispatched_at: iso(8), acknowledged_at: iso(4) });
    expect(currentCommand(instance({ active_command: active }), [fromList])?.status).toBe("acknowledged");
  });

  it("failures and timeouts stay flagged until they are seen", () => {
    const list = [command({ id: "a", status: "timed_out" }), command({ id: "b", status: "failed" }), command({ id: "c", status: "verified" })];
    expect(unseenProblems(list, new Set()).map((c) => c.id)).toEqual(["a", "b"]);
    expect(unseenProblems(list, new Set(["a"])).map((c) => c.id)).toEqual(["b"]);
  });
});

describe("observed state", () => {
  it("fresh, stale, unknown", () => {
    expect(stateView(instance({ age: 3 }), NOW).kind).toBe("fresh");
    expect(stateView(instance({ age: 120 }), NOW).kind).toBe("stale");
    expect(stateView(instance({ age: null }), NOW).kind).toBe("unknown");
  });

  it("the server's stale flag wins over the computed age", () => {
    const i = instance({ age: 3 });
    i.state.stale = true;
    expect(stateView(i, NOW).kind).toBe("stale");
  });

  it("wanted state shown only when it differs from the fresh observed one", () => {
    expect(wantedDiffers(instance({ age: 2, stateValue: "running", desired_state: "running" }), NOW)).toBe(false);
    expect(wantedDiffers(instance({ age: 2, stateValue: "exits_only", desired_state: "running" }), NOW)).toBe(true);
    expect(wantedDiffers(instance({ age: 200, stateValue: "running", desired_state: "running" }), NOW)).toBe(true);
    expect(wantedDiffers(instance({ age: null }), NOW)).toBe(true);
  });

  it("counts per shown state", () => {
    const list = [instance({ id: "1" }), instance({ id: "2", age: 200 }), instance({ id: "3", age: null }), instance({ id: "4", stateValue: "exits_only" })];
    expect(countByState(list, NOW)).toEqual({ running: 1, stale: 1, unknown: 1, exits_only: 1 });
  });
});

describe("degraded mode: which actions stay active", () => {
  const fresh = instance({ age: 2, stateValue: "exits_only", desired_state: "exits_only" });
  const ctx = (degraded: boolean, i = fresh, role: "operator" | "admin" = "operator") => ({ instance: i, degraded, nowMs: NOW, role });

  it("block, flatten and stop stay active in degraded mode", () => {
    for (const action of ["pause_entries", "flatten", "stop"] as const) {
      expect(actionPolicy(action, ctx(true)).enabled).toBe(true);
    }
  });

  it("reopen and start are disabled in degraded mode, with the reason", () => {
    for (const action of ["resume_entries", "start"] as const) {
      const p = actionPolicy(action, ctx(true));
      expect(p.enabled).toBe(false);
      expect(p.reason).toMatch(/dégradé/);
    }
  });

  it("reopening entries outside degraded mode: allowed on a fresh exits-only state", () => {
    expect(actionPolicy("resume_entries", ctx(false)).enabled).toBe(true);
  });

  it("reopening is refused at the slightest doubt: unknown, stale, already open, inconsistent mode", () => {
    expect(actionPolicy("resume_entries", ctx(false, instance({ age: null }))).reason).toMatch(/inconnu/);
    expect(actionPolicy("resume_entries", ctx(false, instance({ age: 200, stateValue: "exits_only" }))).reason).toMatch(/périmé/);
    expect(actionPolicy("resume_entries", ctx(false, instance({ stateValue: "running" }))).enabled).toBe(false);
    expect(actionPolicy("resume_entries", ctx(false, instance({ stateValue: "exits_only", mode_mismatch: true }))).reason).toMatch(/mode/);
  });

  it("every disabled action has a reason to show", () => {
    const cases = [
      ctx(true),
      ctx(false, instance({ age: null })),
      ctx(false, instance({ age: 200, stateValue: "exits_only" })),
      ctx(false, instance({ stateValue: "running" })),
      ctx(false, instance({ stateValue: "exits_only", mode_mismatch: true })),
      ctx(false, instance({ stateValue: "exits_only", desired_mode: "live" })),
    ];
    for (const c of cases) {
      for (const action of ["resume_entries", "start"] as const) {
        const p = actionPolicy(action, c);
        if (!p.enabled) expect(p.reason, `${action}`).toBeTruthy();
      }
    }
  });

  it("an operator neither reopens nor starts an instance whose wanted mode is not paper: administrator required", () => {
    const live = instance({ stateValue: "exits_only", desired_mode: "live" });
    const stopped = instance({ stateValue: "stopped", desired_mode: "live" });
    const resume = actionPolicy("resume_entries", ctx(false, live, "operator"));
    expect(resume.enabled).toBe(false);
    expect(resume.reason).toMatch(/administrateur/);
    const start = actionPolicy("start", ctx(false, stopped, "operator"));
    expect(start.enabled).toBe(false);
    expect(start.reason).toMatch(/administrateur/);
    expect(actionPolicy("resume_entries", ctx(false, live, "admin")).enabled).toBe(true);
    expect(actionPolicy("start", ctx(false, stopped, "admin")).enabled).toBe(true);
    expect(actionPolicy("start", ctx(false, instance({ stateValue: "stopped" }), "operator")).enabled).toBe(true);
  });

  it("the operator keeps the risk-reducing actions on a live instance", () => {
    const live = instance({ desired_mode: "live" });
    for (const action of ["pause_entries", "flatten", "stop"] as const) {
      expect(actionPolicy(action, ctx(false, live, "operator")).enabled).toBe(true);
    }
  });

  it("risk-reducing actions are never blocked by a doubtful state", () => {
    const unknown = instance({ age: null });
    for (const action of ["pause_entries", "flatten", "stop"] as const) {
      expect(actionPolicy(action, ctx(false, unknown)).enabled).toBe(true);
    }
  });

  it("5 s without a heartbeat, degraded or missing health: degraded", () => {
    const ok = { status: "ok" as const, ts: iso(0), checks: {} };
    expect(degradation({ streamSilentMs: 4_000, health: ok, healthFailed: false }).degraded).toBe(false);
    expect(degradation({ streamSilentMs: 5_001, health: ok, healthFailed: false }).causes).toEqual(["stream"]);
    expect(degradation({ streamSilentMs: 0, health: { ...ok, status: "degraded" }, healthFailed: false }).causes).toEqual(["health"]);
    expect(degradation({ streamSilentMs: 0, health: undefined, healthFailed: true }).causes).toEqual(["health-unknown"]);
  });
});

describe("persistent bar", () => {
  it("mode badge from the observed modes", () => {
    expect(deriveMode(undefined)).toBe("unknown");
    expect(deriveMode([instance({ age: null })])).toBe("unknown");
    expect(deriveMode([instance()])).toBe("paper");
    const live = instance({ id: "2" });
    live.observed_mode.value = "live";
    expect(deriveMode([instance(), live])).toBe("live");
  });

  it("engines from the observed states, never the wanted states", () => {
    expect(deriveEngines([], NOW)).toBe("unknown");
    expect(deriveEngines([instance()], NOW)).toBe("ok");
    expect(deriveEngines([instance(), instance({ id: "2", age: 200 })], NOW)).toBe("degraded");
    expect(deriveEngines([instance(), instance({ id: "2", stateValue: "error" })], NOW)).toBe("down");
  });
});

describe("stream: applying messages to the cache", () => {
  function client() {
    const qc = new QueryClient();
    qc.setQueryData<Page<Instance>>(instancesKey, { items: [instance()], next_cursor: null, server_time: iso(0) });
    qc.setQueryData<Page<Command>>(commandsKey, { items: [], next_cursor: null, server_time: iso(0) });
    qc.setQueryData<Page<Alert>>(alertsKey, { items: [], next_cursor: null, server_time: iso(0) });
    return qc;
  }
  const items = <T,>(qc: QueryClient, key: readonly unknown[]) => qc.getQueryData<Page<T>>(key)!.items;

  it("a created instance appears, a known instance is replaced", () => {
    const qc = client();
    const created = instance({ id: "i-2", name: "beta", created_at: iso(1), server_time: iso(0) });
    applyStreamMessage(qc, { event: "instance", server_time: iso(0), instance: created });
    expect(items<Instance>(qc, instancesKey).map((i) => i.name)).toEqual(["beta", "alpha"]);
    const changed = instance({ stateValue: "exits_only", server_time: iso(0) });
    applyStreamMessage(qc, { event: "instance", server_time: iso(0), instance: changed });
    expect(items<Instance>(qc, instancesKey).find((i) => i.id === "i-1")?.state.value).toBe("exits_only");
  });

  it("a message older than the cache is ignored", () => {
    const qc = client();
    const stale = instance({ stateValue: "stopped", server_time: iso(60) });
    applyStreamMessage(qc, { event: "instance", server_time: iso(60), instance: stale });
    expect(items<Instance>(qc, instancesKey)[0]!.state.value).toBe("running");
  });

  it("commands advance stage by stage up to verified", () => {
    const qc = client();
    applyStreamMessage(qc, { event: "command", server_time: iso(0), command: command({ status: "requested" }) });
    applyStreamMessage(qc, { event: "command", server_time: iso(0), command: command({ status: "acknowledged", dispatched_at: iso(6), acknowledged_at: iso(4) }) });
    expect(items<Command>(qc, commandsKey)[0]!.status).toBe("acknowledged");
    applyStreamMessage(qc, { event: "command", server_time: iso(0), command: command({ status: "verified", dispatched_at: iso(6), acknowledged_at: iso(4), verified_at: iso(1) }) });
    expect(items<Command>(qc, commandsKey)).toHaveLength(1);
    expect(items<Command>(qc, commandsKey)[0]!.status).toBe("verified");
  });

  it("a resolved alert leaves the open alerts list", () => {
    const qc = client();
    const alert: Alert = { id: "a-1", rule: "r", severity: "critical", target_kind: "instance", target_id: "i-1", status: "open", message: "m", created_at: iso(5) };
    applyStreamMessage(qc, { event: "alert", server_time: iso(0), alert });
    expect(items<Alert>(qc, alertsKey)).toHaveLength(1);
    applyStreamMessage(qc, { event: "alert", server_time: iso(0), alert: { ...alert, status: "resolved" } });
    expect(items<Alert>(qc, alertsKey)).toHaveLength(0);
  });

  it("a list not loaded yet is not invented", () => {
    const qc = new QueryClient();
    applyStreamMessage(qc, { event: "instance", server_time: iso(0), instance: instance() });
    expect(qc.getQueryData(instancesKey)).toBeUndefined();
  });
});

describe("shownMode: the shown mode comes from the observed mode, never the wanted one (I1)", () => {
  const nowIso = new Date(NOW).toISOString();
  it("wanted paper, fresh observed live: live", () => {
    const i = instance({ desired_mode: "paper", mode_mismatch: true, observed_mode: { value: "live", observed_at: iso(2), stale: false } });
    expect(shownMode(i, nowIso)).toBe("live");
  });
  it("fresh observed paper: paper", () => expect(shownMode(instance(), nowIso)).toBe("paper"));
  it("stale observed: unknown, even if the wanted mode is paper", () => expect(shownMode(instance({ age: 95 }), nowIso)).toBe("unknown"));
  it("unknown observed or missing instance: unknown", () => {
    expect(shownMode(instance({ age: null }), nowIso)).toBe("unknown");
    expect(shownMode(undefined, nowIso)).toBe("unknown");
  });
});
