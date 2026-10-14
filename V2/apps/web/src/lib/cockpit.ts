import type { QueryClient } from "@tanstack/react-query";

import { fr } from "@/i18n/fr";
import { freshness } from "@/lib/format";
import {
  alertsKey,
  commandsKey,
  instanceDetailKey,
  instancesKey,
  type ActionType,
  type Alert,
  type Command,
  type HealthReport,
  type Instance,
  type Page,
} from "@/lib/instances";
import type { StreamMessage } from "@/lib/stream";

export type Mode = "paper" | "live" | "unknown";
export type Health = "ok" | "degraded" | "down" | "unknown";

/** Display thresholds (SPEC §9, §13): 30 s for an engine value, 5 s for the stream. */
export const ENGINE_STALE_MS = 30_000;
export const STREAM_SILENT_MS = 5_000;
/** A verified command stays shown a short while, then the row goes quiet. */
export const VERIFIED_SHOWN_MS = 60_000;

const TERMINAL_PROBLEM = new Set(["failed", "timed_out"]);

/* ------------------------------------------------------------------ commands */

export type CommandView =
  | { tone: "pending"; status: Command["status"]; ageMs: number }
  | { tone: "done"; status: "verified"; ageMs: number }
  | { tone: "problem"; status: "failed" | "timed_out"; ageMs: number; reason: string | null }
  | { tone: "info"; status: "superseded"; ageMs: number };

/**
 * What the interface says about a command. "Done" only exists for `verified`: never from the click,
 * nor from `acknowledged` (I8). The age counts from the request.
 */
export function describeCommand(cmd: Command, nowMs: number): CommandView {
  const ageMs = Math.max(0, nowMs - Date.parse(cmd.requested_at));
  switch (cmd.status) {
    case "verified":
      return { tone: "done", status: "verified", ageMs };
    case "failed":
    case "timed_out": {
      const reason = cmd.result?.reason;
      return { tone: "problem", status: cmd.status, ageMs, reason: typeof reason === "string" ? reason : null };
    }
    case "superseded":
      return { tone: "info", status: "superseded", ageMs };
    default:
      return { tone: "pending", status: cmd.status, ageMs };
  }
}

const STAGES = ["requested_at", "dispatched_at", "acknowledged_at", "verified_at", "failed_at", "timed_out_at", "superseded_at"] as const;

/** Progress of a command: the instant of its last stage. An older version never replaces a newer one. */
function progress(cmd: Command): number {
  return Math.max(...STAGES.map((k) => (cmd[k] ? Date.parse(cmd[k] as string) : 0)));
}

export function newerCommand(a: Command, b: Command): Command {
  return progress(b) >= progress(a) ? b : a;
}

const byRequested = (a: Command, b: Command) =>
  Date.parse(b.requested_at) - Date.parse(a.requested_at) || (a.id < b.id ? 1 : -1);

export function upsertCommand(items: Command[], cmd: Command): Command[] {
  const rest = items.filter((c) => c.id !== cmd.id);
  const known = items.find((c) => c.id === cmd.id);
  return [known ? newerCommand(known, cmd) : cmd, ...rest].sort(byRequested);
}

/** Command to show for an instance: the most recent, from the list and the instance's active command. */
export function currentCommand(instance: Instance, commands: Command[]): Command | null {
  const own = commands.filter((c) => c.instance_id === instance.id);
  const all = instance.active_command ? upsertCommand(own, instance.active_command) : own;
  return all[0] ?? null;
}

/** Failures and timeouts the operator has not seen yet: they stay shown until told otherwise (SPEC §9). */
export function unseenProblems(commands: Command[], seen: ReadonlySet<string>): Command[] {
  return commands.filter((c) => TERMINAL_PROBLEM.has(c.status) && !seen.has(c.id));
}

/* ----------------------------------------------------------------- instances */

export type StateView = { kind: "unknown" } | { kind: "fresh" | "stale"; state: Exclude<Instance["state"]["value"], "unknown"> };

/** Observed state as it can be shown now: unknown, fresh or stale. */
export function stateView(instance: Instance, nowMs: number): StateView {
  const { value, observed_at, stale } = instance.state;
  if (value === "unknown" || observed_at === null) return { kind: "unknown" };
  const f = freshness({ observedAt: observed_at, serverTime: new Date(nowMs).toISOString(), staleAfterMs: ENGINE_STALE_MS });
  if (f.state === "unknown") return { kind: "unknown" };
  return { kind: stale || f.state === "stale" ? "stale" : "fresh", state: value };
}

/** Do wanted and observed differ? An unknown or stale observed state "matches" nothing. */
export function wantedDiffers(instance: Instance, nowMs: number): boolean {
  const view = stateView(instance, nowMs);
  return view.kind !== "fresh" || view.state !== instance.desired_state;
}

/* ------------------------------------------------------------------- actions */

export const RISK_REDUCING: ReadonlySet<ActionType> = new Set(["pause_entries", "flatten", "stop"]);
export const ACTIONS: readonly ActionType[] = ["pause_entries", "resume_entries", "flatten", "stop", "start"];

export interface ActionPolicy {
  enabled: boolean;
  /** Readable reason when the action is disabled. */
  reason: string | null;
}

/**
 * Who may act and when. What reduces risk (block, flatten, stop) is never disabled by an outage or a
 * doubtful state (I4, I5); what increases it is, at the slightest doubt.
 */
export function actionPolicy(
  action: ActionType,
  ctx: { instance: Instance; degraded: boolean; nowMs: number; role: "operator" | "admin" },
): ActionPolicy {
  if (RISK_REDUCING.has(action)) return { enabled: true, reason: null };
  const r = fr.cockpit.reasons;
  if (ctx.degraded) return { enabled: false, reason: r.degraded };
  // Like the server: outside paper, reopening and starting require an administrator.
  if (ctx.role !== "admin" && ctx.instance.desired_mode !== "paper") return { enabled: false, reason: r.adminOnly };
  const view = stateView(ctx.instance, ctx.nowMs);
  if (action === "resume_entries") {
    if (view.kind === "unknown") return { enabled: false, reason: r.unknown };
    if (view.kind === "stale") return { enabled: false, reason: r.stale };
    if (view.state === "running") return { enabled: false, reason: r.alreadyOpen };
    if (view.state !== "exits_only") return { enabled: false, reason: r.notExitsOnly(fr.cockpit.states[view.state]) };
    if (ctx.instance.mode_mismatch) return { enabled: false, reason: r.modeMismatch };
    return { enabled: true, reason: null };
  }
  // start
  if (view.kind === "fresh" && (view.state === "running" || view.state === "starting" || view.state === "exits_only")) {
    return { enabled: false, reason: r.alreadyStarted };
  }
  return { enabled: true, reason: null };
}

export function canCreate(degraded: boolean): ActionPolicy {
  return degraded ? { enabled: false, reason: fr.cockpit.reasons.degraded } : { enabled: true, reason: null };
}

/* ------------------------------------------------------------ degraded mode */

export interface Degradation {
  degraded: boolean;
  /** Causes shown in the banner. */
  causes: ("stream" | "health" | "health-unknown")[];
}

/** Stream silent over 5 s, degraded health or health not found: degraded mode (SPEC §9). */
export function degradation(input: {
  streamSilentMs: number;
  health: HealthReport | undefined;
  healthFailed: boolean;
}): Degradation {
  const causes: Degradation["causes"] = [];
  if (input.streamSilentMs > STREAM_SILENT_MS) causes.push("stream");
  if (input.health?.status === "degraded") causes.push("health");
  if (input.healthFailed) causes.push("health-unknown");
  return { degraded: causes.length > 0, causes };
}

/* ------------------------------------------------------------ persistent bar */

/** LIVE as soon as an instance is observed live; PAPER while none is; unknown if nothing is observed. */
export function deriveMode(instances: Instance[] | undefined): Mode {
  const modes = (instances ?? []).map((i) => i.observed_mode.value);
  if (modes.includes("live")) return "live";
  if (modes.includes("paper")) return "paper";
  return "unknown";
}

export type ShownMode = Mode;

/**
 * Mode to show for an instance: the observed one if fresh, otherwise "unknown". Never the wanted mode,
 * nor a stale observed one (SPEC §9, I1): "simulated" is only said for a fresh observed paper mode.
 */
export function shownMode(instance: Instance | undefined, nowIso: string): ShownMode {
  const m = instance?.observed_mode;
  if (!m || m.value === "unknown") return "unknown";
  return freshness({ observedAt: m.observed_at, serverTime: nowIso, staleAfterMs: ENGINE_STALE_MS }).state === "fresh" ? m.value : "unknown";
}

/** Engines: from the observed states of the instances, never from the wanted state. */
export function deriveEngines(instances: Instance[] | undefined, nowMs: number): Health {
  if (!instances || instances.length === 0) return "unknown";
  const views = instances.map((i) => stateView(i, nowMs));
  if (views.some((v) => v.kind !== "unknown" && (v.state === "error" || v.state === "halted"))) return "down";
  if (views.some((v) => v.kind !== "fresh")) return "degraded";
  return "ok";
}

export function deriveCheck(health: HealthReport | undefined, name: string): Health {
  const check = health?.checks[name];
  if (!check) return "unknown";
  return check.status === "ok" ? "ok" : "down";
}

/** Number of instances per shown state (unknown and stale count apart). */
export function countByState(instances: Instance[], nowMs: number): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const i of instances) {
    const v = stateView(i, nowMs);
    const key = v.kind === "unknown" ? "unknown" : v.kind === "stale" ? "stale" : v.state;
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

/* ------------------------------------------------------------------- stream */

const byCreated = (a: Instance, b: Instance) =>
  Date.parse(b.created_at) - Date.parse(a.created_at) || (a.id < b.id ? 1 : -1);

/**
 * Applies a stream message to the cache. No reload: the message holds the whole object. A version older
 * than the cached one is ignored. A list not loaded yet is not created: the initial load, rerun when the
 * stream opens, fills it.
 */
export function applyStreamMessage(qc: QueryClient, msg: StreamMessage): void {
  switch (msg.event) {
    case "instance": {
      const inst = msg.instance;
      if (!qc.getQueryData<Page<Instance>>(instancesKey)?.items.some((i) => i.id === inst.id)) {
        void qc.invalidateQueries({ queryKey: [...instancesKey, "strategy"] }); // new instance: per-strategy lists re-read
      }
      qc.setQueryData<Page<Instance>>(instancesKey, (page) => {
        if (!page) return undefined;
        const known = page.items.find((i) => i.id === inst.id);
        if (known && Date.parse(known.server_time) > Date.parse(inst.server_time)) return page;
        const items = [inst, ...page.items.filter((i) => i.id !== inst.id)].sort(byCreated);
        return { ...page, items };
      });
      // The detail (fingerprint, effective configuration, drift) is re-read: the message does not carry it.
      void qc.invalidateQueries({ queryKey: instanceDetailKey(inst.id) });
      break;
    }
    case "position":
    case "trade":
      // Open positions, closed trades and realized PnL of the list rows come from the server: re-read, never assumed.
      void qc.invalidateQueries({ queryKey: instancesKey });
      break;
    case "command":
      qc.setQueryData<Page<Command>>(commandsKey, (page) =>
        page ? { ...page, items: upsertCommand(page.items, msg.command) } : undefined,
      );
      break;
    case "alert":
      qc.setQueryData<Page<Alert>>(alertsKey, (page) => {
        if (!page) return undefined;
        const rest = page.items.filter((a) => a.id !== msg.alert.id);
        const items = msg.alert.status === "open" ? [msg.alert, ...rest] : rest;
        return { ...page, items: items.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)) };
      });
      break;
    case "order":
    case "heartbeat":
      break;
  }
}
