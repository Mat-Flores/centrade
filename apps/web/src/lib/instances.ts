import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { apiFetch } from "./api";
import { observeServerTime } from "./clock";

/** Formes de l'API de pilotage (apps/api/centrade_api/schemas.py). Toute réponse hors contrat est refusée. */

const observed = <T extends z.ZodType>(value: T) =>
  z.object({ value, observed_at: z.string().nullable(), stale: z.boolean() });

export const OBSERVED_STATES = ["starting", "exits_only", "running", "halted", "stopped", "error", "unknown"] as const;
export type ObservedState = (typeof OBSERVED_STATES)[number];
export const DESIRED_STATES = ["running", "exits_only", "stopped"] as const;
export type DesiredState = (typeof DESIRED_STATES)[number];

export const COMMAND_STATUSES = [
  "requested",
  "dispatched",
  "acknowledged",
  "verified",
  "failed",
  "timed_out",
  "superseded",
] as const;
export type CommandStatus = (typeof COMMAND_STATUSES)[number];

export const CommandSchema = z.object({
  id: z.string(),
  instance_id: z.string(),
  type: z.string(),
  status: z.enum(COMMAND_STATUSES),
  requested_at: z.string(),
  deadline_at: z.string(),
  dispatched_at: z.string().nullish(),
  acknowledged_at: z.string().nullish(),
  verified_at: z.string().nullish(),
  failed_at: z.string().nullish(),
  timed_out_at: z.string().nullish(),
  superseded_at: z.string().nullish(),
  result: z.record(z.string(), z.unknown()).nullish(),
  server_time: z.string(),
});
export type Command = z.infer<typeof CommandSchema>;

export const InstanceSchema = z.object({
  id: z.string(),
  name: z.string(),
  engine: z.string(),
  desired_mode: z.enum(["paper", "live"]),
  desired_state: z.enum(DESIRED_STATES),
  state: observed(z.enum(OBSERVED_STATES)),
  observed_mode: observed(z.enum(["paper", "live", "unknown"])),
  mode_mismatch: z.boolean(),
  active_command: CommandSchema.nullish(),
  created_at: z.string(),
  server_time: z.string(),
});
export type Instance = z.infer<typeof InstanceSchema>;

export const AlertSchema = z.object({
  id: z.string(),
  rule: z.string(),
  severity: z.string(),
  target_kind: z.string(),
  target_id: z.string().nullish(),
  status: z.string(),
  message: z.string(),
  created_at: z.string(),
});
export type Alert = z.infer<typeof AlertSchema>;

const page = <T extends z.ZodType>(item: T) =>
  z.object({ items: z.array(item), next_cursor: z.string().nullable(), server_time: z.string() });
export type Page<T> = { items: T[]; next_cursor: string | null; server_time: string };

export const CheckSchema = z.object({ status: z.enum(["ok", "down"]), observed_at: z.string() });
export const HealthSchema = z.object({
  status: z.enum(["ok", "degraded"]),
  ts: z.string(),
  checks: z.record(z.string(), CheckSchema),
});
export type HealthReport = z.infer<typeof HealthSchema>;

export const CommandAcceptedSchema = z.object({ command_id: z.string(), command: CommandSchema });

export const instancesKey = ["instances"] as const;
export const commandsKey = ["commands"] as const;
export const alertsKey = ["alerts", "open"] as const;
export const healthKey = ["health"] as const;
export const instanceDetailKey = (id: string) => ["instance-detail", id] as const;

/** Les dates du serveur recalent l'horloge d'affichage : l'âge ne dépend jamais de celle du navigateur. */
async function timed<T extends { server_time: string }>(promise: Promise<T>): Promise<T> {
  const data = await promise;
  observeServerTime(data.server_time);
  return data;
}

export const instancesQuery = queryOptions({
  queryKey: instancesKey,
  queryFn: ({ signal }) => timed(apiFetch("/instances?limit=200", page(InstanceSchema), { signal })),
  staleTime: Infinity, // tenu à jour par le flux ; relu en entier à la reconnexion
});

/**
 * Les 100 dernières commandes, plus les échecs et expirations quel que soit leur âge : une commande en
 * échec non vue ne disparaît pas au rechargement parce que 100 autres sont venues après (SPEC §9).
 */
async function loadCommands(signal: AbortSignal): Promise<Page<Command>> {
  const [recent, problems] = await Promise.all([
    timed(apiFetch("/commands?limit=100", page(CommandSchema), { signal })),
    timed(apiFetch("/commands?status=timed_out&status=failed&limit=100", page(CommandSchema), { signal })),
  ]);
  const byId = new Map([...problems.items, ...recent.items].map((c) => [c.id, c]));
  const items = [...byId.values()].sort(
    (a, b) => Date.parse(b.requested_at) - Date.parse(a.requested_at) || (a.id < b.id ? 1 : -1),
  );
  return { ...recent, items };
}

export const commandsQuery = queryOptions({
  queryKey: commandsKey,
  queryFn: ({ signal }) => loadCommands(signal),
  staleTime: Infinity,
});

export const alertsQuery = queryOptions({
  queryKey: alertsKey,
  queryFn: ({ signal }) => timed(apiFetch("/alerts?status=open&limit=100", page(AlertSchema), { signal })),
  staleTime: Infinity,
});

/** Pas d'événement pour la santé : seul relevé interrogé périodiquement (ce n'est pas une liste). */
export const HEALTH_POLL_MS = 10_000;
export const healthQuery = queryOptions({
  queryKey: healthKey,
  queryFn: ({ signal }) => apiFetch("/system/health", HealthSchema, { signal, authCall: true }),
  refetchInterval: HEALTH_POLL_MS,
});

export type ActionType = "start" | "stop" | "pause_entries" | "resume_entries" | "flatten";
const SLUG: Record<ActionType, string> = {
  start: "start",
  stop: "stop",
  pause_entries: "pause-entries",
  resume_entries: "resume-entries",
  flatten: "flatten",
};

/** Une commande : le serveur répond 202 `requested`, jamais « fait ». La clé d'idempotence est rejouable. */
export function sendAction(instanceId: string, action: ActionType, idempotencyKey: string) {
  return apiFetch(`/instances/${instanceId}/${SLUG[action]}`, CommandAcceptedSchema, {
    method: "POST",
    body: undefined,
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

export function createInstance(name: string) {
  // Le moteur n'est pas choisi ici (le serveur prend l'unique moteur enregistré). Toujours paper (le live passe par la promotion, F1).
  return apiFetch("/instances", InstanceSchema, { method: "POST", body: { name, mode: "paper" } });
}
