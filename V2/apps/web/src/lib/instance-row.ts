import { fr } from "@/i18n/fr";

import { currentCommand, describeCommand, actionPolicy, stateView, unseenProblems, VERIFIED_SHOWN_MS, ENGINE_STALE_MS } from "./cockpit";
import { formatAge } from "./format";
import type { ActionType, Command, Instance, Observed } from "./instances";
import type { Me } from "./session";

/** Pure view logic of one list row. Nothing here turns a request into a fact: "done" only exists for `verified` (I8). */

/* ------------------------------------------------------------------ command */

export type CommandTone = "pending" | "done" | "problem" | "info";
export interface RowCommand {
  command: Command;
  tone: CommandTone;
  /** Short word shown in the row: "demandé", "fait", "échec", "expirée", "remplacée". */
  text: string;
  /** What the command is, its stage and its age. */
  line: string;
  /** Only for a problem: the engine's reason, or the standard sentence when it gave none. */
  reason: string | null;
}

const typeLabel = (type: string) => fr.cockpit.command.types[type] ?? type;

/**
 * Command worth showing on the row. An unseen failure or timeout comes first and stays until the
 * operator saw it (SPEC §9). Otherwise the latest command: pending as long as it is, done or replaced
 * only for a short while.
 */
export function rowCommand(instance: Instance, commands: readonly Command[], seen: ReadonlySet<string>, nowMs: number): RowCommand | null {
  const own = commands.filter((c) => c.instance_id === instance.id);
  const problem = unseenProblems(own, seen)[0];
  const latest = problem ?? currentCommand(instance, own);
  if (!latest) return null;
  const v = describeCommand(latest, nowMs);
  const t = fr.instances.command;
  const line = t.line(typeLabel(latest.type), fr.cockpit.command.status[v.status], formatAge(v.ageMs));
  switch (v.tone) {
    case "pending":
      return { command: latest, tone: "pending", text: t.pending, line, reason: null };
    case "problem":
      return problem ? { command: latest, tone: "problem", text: v.status === "failed" ? t.failed : t.timed_out, line, reason: v.reason ?? fr.cockpit.command.noReason } : null;
    case "done":
    case "info":
      if (v.ageMs > VERIFIED_SHOWN_MS) return null;
      return { command: latest, tone: v.tone, text: v.tone === "done" ? t.done : t.superseded, line, reason: null };
  }
}

/* ---------------------------------------------------------------- attention */

/** An error state, an unseen failed command, or a mode mismatch: the row goes first and is highlighted. */
export function needsAttention(instance: Instance, commands: readonly Command[], seen: ReadonlySet<string>, nowMs: number): boolean {
  const view = stateView(instance, nowMs);
  if (view.kind !== "unknown" && view.state === "error") return true;
  if (instance.mode_mismatch) return true;
  return unseenProblems(commands.filter((c) => c.instance_id === instance.id), seen).length > 0;
}

/** Filter by name, then attention first; the order the server gave (newest first) is kept otherwise. */
export function visibleRows(instances: readonly Instance[], query: string, commands: readonly Command[], seen: ReadonlySet<string>, nowMs: number): Instance[] {
  const q = query.trim().toLowerCase();
  return instances
    .filter((i) => i.name.toLowerCase().includes(q))
    .map((i, n) => ({ i, n, a: needsAttention(i, commands, seen, nowMs) }))
    .sort((x, y) => Number(y.a) - Number(x.a) || x.n - y.n)
    .map((x) => x.i);
}

/* ------------------------------------------------------------------- action */

export type RowAction =
  | { kind: "open" }
  | { kind: "starting" }
  | { kind: "command"; action: ActionType; enabled: boolean; reason: string | null };

/** Actions that ask for a confirmation: they close or stop, or they increase risk. */
export const CONFIRMED: ReadonlySet<ActionType> = new Set(["flatten", "stop", "resume_entries"]);

/**
 * The one button of a row, from the OBSERVED state (never the wanted one). Unknown or faulty states only
 * offer to open the instance. Refusal by default: whatever increases risk goes through `actionPolicy`.
 * A command in flight disables the button (no double request), but never a reduction elsewhere.
 */
export function rowAction(
  instance: Instance,
  ctx: { degraded: boolean; nowMs: number; role: Me["role"]; busy: boolean },
): RowAction {
  const view = stateView(instance, ctx.nowMs);
  if (ctx.role === "viewer" || view.kind === "unknown") return { kind: "open" };
  let action: ActionType;
  switch (view.state) {
    case "starting":
      return { kind: "starting" };
    case "error":
    case "halted":
      return { kind: "open" };
    case "stopped":
      action = "start";
      break;
    case "exits_only":
      action = "resume_entries";
      break;
    case "running":
      action = "pause_entries";
      break;
  }
  const policy = actionPolicy(action, { instance, degraded: ctx.degraded, nowMs: ctx.nowMs, role: ctx.role });
  if (ctx.busy) return { kind: "command", action, enabled: false, reason: fr.instances.commandPending };
  return { kind: "command", action, ...policy };
}

/* ---------------------------------------------------------------- age hover */

/** "Observé il y a 3 s" or "périmé depuis 2 min": the date of a value, said as observed. `null` if never observed. */
export function observedTip(obs: Observed<unknown> | null | undefined, nowMs: number): string | null {
  if (!obs?.observed_at) return null;
  const age = Math.max(0, nowMs - Date.parse(obs.observed_at));
  if (Number.isNaN(age)) return null;
  return obs.stale || age > ENGINE_STALE_MS ? fr.observed.staleSince(formatAge(Math.max(0, age - ENGINE_STALE_MS))) : fr.instances.observedAge(formatAge(age));
}
