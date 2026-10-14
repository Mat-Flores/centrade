import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { apiFetch } from "./api";
import { observeServerTime } from "./clock";

/** Shapes of the control API (V2/apps/api/centrade_api/instances/schemas.py). Any out-of-contract response is refused. */

const observed = <T extends z.ZodType>(value: T) =>
  z.object({ value, observed_at: z.string().nullable(), stale: z.boolean() });
export type Observed<T> = { value: T; observed_at: string | null; stale: boolean };

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

const json = z.record(z.string(), z.unknown());

export const StrategyRefSchema = z.object({
  version_id: z.string(),
  strategy_id: z.string(),
  name: z.string(),
  version: z.number(),
  status: z.string(),
  code_hash: z.string(),
  exits: json,
});
export type StrategyRef = z.infer<typeof StrategyRefSchema>;

/** Never a secret reference (I12). */
export const AccountRefSchema = z.object({
  id: z.string(),
  venue: z.string(),
  type: z.string(),
  environment: z.string(),
  label: z.string(),
  currency: z.string(),
});
export type AccountRef = z.infer<typeof AccountRefSchema>;

/** Sums for one currency, as decimal strings; never converted nor added across currencies. */
export const MoneySchema = z.object({ currency: z.string(), amount: z.string(), fees: z.string() });
export type Money = z.infer<typeof MoneySchema>;

export const BalanceSchema = z.object({ currency: z.string(), free: z.string(), total: z.string() });
export type Balance = z.infer<typeof BalanceSchema>;

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
  strategy: StrategyRefSchema.nullable(),
  account: AccountRefSchema.nullable(),
  started_at: z.string().nullable(),
  // Value null = never observed: "unknown", never zero (I1).
  realized_pnl: observed(z.array(MoneySchema).nullable()),
  closed_trades: observed(z.number().int().nullable()),
  open_positions: observed(z.number().int().nullable()),
  // shortcut: absent from the server contract at the time of writing (backend commit in progress);
  // make it exact (drop `.nullish()`) once `balances` ships in InstanceOut.
  balances: observed(z.array(BalanceSchema).nullable()).nullish(),
  created_at: z.string(),
  server_time: z.string(),
});
export type Instance = z.infer<typeof InstanceSchema>;

export const DriftItemSchema = z.object({ key: z.string(), expected: z.unknown(), observed: z.unknown() });

/** The detail inherits the whole list item, plus what only one instance carries. */
export const InstanceDetailSchema = InstanceSchema.extend({
  deployment_fingerprint: z.string().nullable(),
  config_hash: z.string().nullable(),
  engine_version: observed(z.string().nullable()),
  effective_config: observed(json.nullable()),
  drift: observed(z.array(DriftItemSchema).nullable()),
});
export type InstanceDetail = z.infer<typeof InstanceDetailSchema>;

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

/** Server dates recalibrate the display clock: ages never depend on the browser clock. */
async function timed<T extends { server_time: string }>(promise: Promise<T>): Promise<T> {
  const data = await promise;
  observeServerTime(data.server_time);
  return data;
}

export const instancesQuery = queryOptions({
  queryKey: instancesKey,
  queryFn: ({ signal }) => timed(apiFetch("/instances?limit=200", page(InstanceSchema), { signal })),
  staleTime: Infinity, // kept up to date by the stream; fully re-read on reconnection
});

/** Instances of one strategy: the filter is applied by the API. */
export const strategyInstancesQuery = (strategyId: string) =>
  queryOptions({
    queryKey: [...instancesKey, "strategy", strategyId] as const,
    queryFn: ({ signal }) => timed(apiFetch(`/instances?limit=200&strategy_id=${strategyId}`, page(InstanceSchema), { signal })),
  });

/** The detail carries the fingerprint, the effective configuration and the drift: re-read by the stream and every 30 s. */
export const instanceDetailQuery = (id: string) =>
  queryOptions({
    queryKey: instanceDetailKey(id),
    queryFn: ({ signal }) => timed(apiFetch(`/instances/${id}`, InstanceDetailSchema, { signal })),
    refetchInterval: 30_000,
  });

/**
 * The last 100 commands, plus failures and timeouts whatever their age: an unseen failed command does
 * not vanish on reload because 100 others came after it (SPEC §9).
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

export const commandsQuery = queryOptions({ queryKey: commandsKey, queryFn: ({ signal }) => loadCommands(signal), staleTime: Infinity });

export const alertsQuery = queryOptions({
  queryKey: alertsKey,
  queryFn: ({ signal }) => timed(apiFetch("/alerts?status=open&limit=100", page(AlertSchema), { signal })),
  staleTime: Infinity,
});

/** No stream event for health: the only reading polled periodically (it is not a list). */
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

/** One command: the server answers 202 `requested`, never "done". The idempotency key can be replayed. */
export function sendAction(instanceId: string, action: ActionType, idempotencyKey: string) {
  return apiFetch(`/instances/${instanceId}/${SLUG[action]}`, CommandAcceptedSchema, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

/** Same pattern as the API for an instance name (max 64 characters). */
export const INSTANCE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
export const INSTANCE_NAME_MAX_LENGTH = 64;
export const isValidInstanceName = (name: string): boolean => name.length <= INSTANCE_NAME_MAX_LENGTH && INSTANCE_NAME.test(name);

export interface DeployPaperBody {
  name: string;
  params: Record<string, unknown>;
  strategy_version_id: string;
  account_id: string;
}

/**
 * Always paper: going live follows the promotion procedure (F1), the API only accepts `mode: "paper"`.
 * The key is derived from the intent by the caller and reused on retry (the server replays with 200).
 */
export const deployPaper = (body: DeployPaperBody, idempotencyKey: string) =>
  apiFetch("/instances", InstanceSchema, { method: "POST", body: { ...body, mode: "paper" }, headers: { "Idempotency-Key": idempotencyKey } });
