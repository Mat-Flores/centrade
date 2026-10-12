import type { QueryClient } from "@tanstack/react-query";

import { fr } from "@/i18n/fr";
import type { Health, Mode } from "@/components/persistent-bar";
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

/** Seuils de l'affichage (SPEC §9, §13) : 30 s pour une valeur de moteur, 5 s pour le flux. */
export const ENGINE_STALE_MS = 30_000;
export const STREAM_SILENT_MS = 5_000;
/** Une commande vérifiée reste affichée un court instant, puis la ligne revient au calme. */
export const VERIFIED_SHOWN_MS = 60_000;

const TERMINAL_PROBLEM = new Set(["failed", "timed_out"]);

/* ----------------------------------------------------------------- commandes */

export type CommandView =
  | { tone: "pending"; status: Command["status"]; ageMs: number }
  | { tone: "done"; status: "verified"; ageMs: number }
  | { tone: "problem"; status: "failed" | "timed_out"; ageMs: number; reason: string | null }
  | { tone: "info"; status: "superseded"; ageMs: number };

/**
 * Ce que l'interface dit d'une commande. « Fait » (`done`) n'existe que pour `verified` : jamais
 * d'après le clic, ni d'après `acknowledged` (I8). L'ancienneté se compte depuis la demande.
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

/** Avancement d'une commande : l'instant de sa dernière étape. Une version plus ancienne ne remplace jamais une plus récente. */
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

/** Commande à montrer pour une instance : la plus récente, d'après la liste et la commande active de l'instance. */
export function currentCommand(instance: Instance, commands: Command[]): Command | null {
  const own = commands.filter((c) => c.instance_id === instance.id);
  const all = instance.active_command ? upsertCommand(own, instance.active_command) : own;
  return all[0] ?? null;
}

/** Échecs et expirations pas encore vus par l'opérateur : ils restent affichés jusqu'à ce qu'il le dise (SPEC §9). */
export function unseenProblems(commands: Command[], seen: ReadonlySet<string>): Command[] {
  return commands.filter((c) => TERMINAL_PROBLEM.has(c.status) && !seen.has(c.id));
}

/* ----------------------------------------------------------------- instances */

export type StateView = { kind: "unknown" } | { kind: "fresh" | "stale"; state: Exclude<Instance["state"]["value"], "unknown"> };

/** État observé tel qu'il peut être présenté à cet instant : inconnu, frais ou périmé. */
export function stateView(instance: Instance, nowMs: number): StateView {
  const { value, observed_at, stale } = instance.state;
  if (value === "unknown" || observed_at === null) return { kind: "unknown" };
  const f = freshness({ observedAt: observed_at, serverTime: new Date(nowMs).toISOString(), staleAfterMs: ENGINE_STALE_MS });
  if (f.state === "unknown") return { kind: "unknown" };
  return { kind: stale || f.state === "stale" ? "stale" : "fresh", state: value };
}

/** Voulu et observé diffèrent-ils ? Un état observé inconnu ou périmé ne « correspond » à rien. */
export function wantedDiffers(instance: Instance, nowMs: number): boolean {
  const view = stateView(instance, nowMs);
  return view.kind !== "fresh" || view.state !== instance.desired_state;
}

/* ------------------------------------------------------------------- actions */

export const RISK_REDUCING: ReadonlySet<ActionType> = new Set(["pause_entries", "flatten", "stop"]);
export const ACTIONS: readonly ActionType[] = ["pause_entries", "resume_entries", "flatten", "stop", "start"];

export interface ActionPolicy {
  enabled: boolean;
  /** Raison lisible quand l'action est désactivée. */
  reason: string | null;
}

/**
 * Qui a le droit d'agir et quand. Ce qui réduit le risque (bloquer, tout fermer, arrêter) n'est jamais
 * désactivé par une panne ni par un état douteux (I4, I5) ; ce qui l'augmente l'est au moindre doute.
 */
export function actionPolicy(
  action: ActionType,
  ctx: { instance: Instance; degraded: boolean; nowMs: number; role: "operator" | "admin" },
): ActionPolicy {
  if (RISK_REDUCING.has(action)) return { enabled: true, reason: null };
  const r = fr.cockpit.reasons;
  if (ctx.degraded) return { enabled: false, reason: r.degraded };
  // Comme le serveur : hors paper, rouvrir et démarrer exigent un administrateur.
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

/* ------------------------------------------------------------- mode dégradé */

export interface Degradation {
  degraded: boolean;
  /** Causes affichées dans le bandeau. */
  causes: ("stream" | "health" | "health-unknown")[];
}

/** Flux silencieux plus de 5 s, santé dégradée ou santé introuvable : mode dégradé (SPEC §9). */
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

/* ------------------------------------------------------------ barre persistante */

/** LIVE dès qu'une instance est observée live ; PAPER tant qu'aucune ne l'est ; inconnu si rien n'est observé. */
export function deriveMode(instances: Instance[] | undefined): Mode {
  const modes = (instances ?? []).map((i) => i.observed_mode.value);
  if (modes.includes("live")) return "live";
  if (modes.includes("paper")) return "paper";
  return "unknown";
}

/** Moteurs : d'après les états observés des instances, jamais d'après l'état voulu. */
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

/** Nombre d'instances par état présenté (inconnu et périmé comptent à part). */
export function countByState(instances: Instance[], nowMs: number): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const i of instances) {
    const v = stateView(i, nowMs);
    const key = v.kind === "unknown" ? "unknown" : v.kind === "stale" ? "stale" : v.state;
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

/* --------------------------------------------------------------------- flux */

export type StreamMessage =
  | { event: "heartbeat"; server_time: string }
  | { event: "instance"; server_time: string; instance: Instance }
  | { event: "command"; server_time: string; command: Command }
  | { event: "alert"; server_time: string; alert: Alert }
  | { event: "order" | "position" | "trade"; server_time: string };

const byCreated = (a: Instance, b: Instance) =>
  Date.parse(b.created_at) - Date.parse(a.created_at) || (a.id < b.id ? 1 : -1);

/**
 * Applique un message du flux au cache. Pas de rechargement : le message contient l'objet complet.
 * Une version plus ancienne que celle du cache est ignorée. Une liste pas encore chargée n'est pas
 * créée : le chargement initial, relancé à l'ouverture du flux, la remplit.
 */
export function applyStreamMessage(qc: QueryClient, msg: StreamMessage): void {
  switch (msg.event) {
    case "instance": {
      const inst = msg.instance;
      if (!qc.getQueryData<Page<Instance>>(instancesKey)?.items.some((i) => i.id === inst.id)) {
        void qc.invalidateQueries({ queryKey: [...instancesKey, "strategy"] }); // nouvelle instance : listes par stratégie relues
      }
      qc.setQueryData<Page<Instance>>(instancesKey, (page) => {
        if (!page) return undefined;
        const known = page.items.find((i) => i.id === inst.id);
        if (known && Date.parse(known.server_time) > Date.parse(inst.server_time)) return page;
        const items = [inst, ...page.items.filter((i) => i.id !== inst.id)].sort(byCreated);
        return { ...page, items };
      });
      // Le détail (empreinte, configuration effective, dérive) est relu : le message ne le porte pas.
      void qc.invalidateQueries({ queryKey: instanceDetailKey(inst.id) });
      break;
    }
    case "order":
    case "position":
    case "trade":
      // Le message ne porte que la ligne ; les listes filtrées sont relues (jamais d'état supposé).
      void qc.invalidateQueries({ queryKey: ["trading", `${msg.event}s`] });
      break;
    case "command": {
      qc.setQueryData<Page<Command>>(commandsKey, (page) =>
        page ? { ...page, items: upsertCommand(page.items, msg.command) } : undefined,
      );
      break;
    }
    case "alert": {
      qc.setQueryData<Page<Alert>>(alertsKey, (page) => {
        if (!page) return undefined;
        const rest = page.items.filter((a) => a.id !== msg.alert.id);
        const items = msg.alert.status === "open" ? [msg.alert, ...rest] : rest;
        return { ...page, items: items.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)) };
      });
      break;
    }
    case "heartbeat":
      break;
  }
}
