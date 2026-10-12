import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { apiFetch } from "./api";
import { observeServerTime } from "./clock";
import { InstanceSchema, instanceDetailKey } from "./instances";

/** Formes de l'API du registre (apps/api/centrade_api/strategies.py) et du détail d'instance (schemas.py). */

export const VERSION_STATUSES = ["draft", "approved", "retired"] as const;
export type VersionStatus = (typeof VERSION_STATUSES)[number];

export const StrategySchema = z.object({ id: z.string(), name: z.string(), created_at: z.string() });
export type Strategy = z.infer<typeof StrategySchema>;

const json = z.record(z.string(), z.unknown());
export const VersionSchema = z.object({
  id: z.string(),
  strategy_id: z.string(),
  version: z.number(),
  status: z.enum(VERSION_STATUSES),
  engine: z.string(),
  manifest: json,
  code_hash: z.string(),
  author: z.string(),
  static_checks: json,
  exits: json,
  created_at: z.string(),
});
export type Version = z.infer<typeof VersionSchema>;
export const VersionDetailSchema = VersionSchema.extend({ code: z.string() });

const page = <T extends z.ZodType>(item: T) =>
  z.object({ items: z.array(item), next_cursor: z.string().nullable(), server_time: z.string() });

const observed = <T extends z.ZodType>(value: T) => z.object({ value, observed_at: z.string().nullable(), stale: z.boolean() });

export const InstanceDetailSchema = InstanceSchema.extend({
  strategy: z.object({ version_id: z.string(), strategy_id: z.string(), name: z.string(), version: z.number(), status: z.string(), code_hash: z.string(), exits: json }).nullable(),
  account: z.object({ id: z.string(), venue: z.string(), type: z.string(), environment: z.string(), label: z.string(), currency: z.string() }).nullable(),
  deployment_fingerprint: z.string().nullable(),
  config_hash: z.string().nullable(),
  effective_config: observed(json.nullable()),
  drift: observed(z.array(z.object({ key: z.string(), expected: z.unknown(), observed: z.unknown() })).nullable()),
});
export type InstanceDetail = z.infer<typeof InstanceDetailSchema>;

export const strategiesKey = ["strategies"] as const;
export const versionsKey = (strategyId: string) => ["strategies", strategyId, "versions"] as const;

export const strategiesQuery = queryOptions({
  queryKey: strategiesKey,
  queryFn: async ({ signal }) => {
    const data = await apiFetch("/strategies?limit=200", page(StrategySchema), { signal });
    observeServerTime(data.server_time);
    return data;
  },
});

export const versionsQuery = (strategyId: string) =>
  queryOptions({
    queryKey: versionsKey(strategyId),
    queryFn: async ({ signal }) => {
      const data = await apiFetch(`/strategies/${strategyId}/versions?limit=200`, page(VersionSchema), { signal });
      observeServerTime(data.server_time);
      return data;
    },
  });

export const versionQuery = (strategyId: string, version: number) =>
  queryOptions({
    queryKey: [...versionsKey(strategyId), version] as const,
    queryFn: ({ signal }) => apiFetch(`/strategies/${strategyId}/versions/${version}`, VersionDetailSchema, { signal }),
    staleTime: Infinity, // une version déposée ne change jamais (seul son statut : la liste le porte)
  });

/** Le détail porte l'empreinte, la configuration effective et la dérive : relu par le flux et toutes les 30 s. */
export const instanceDetailQuery = (id: string) =>
  queryOptions({
    queryKey: instanceDetailKey(id),
    queryFn: async ({ signal }) => {
      const data = await apiFetch(`/instances/${id}`, InstanceDetailSchema, { signal });
      observeServerTime(data.server_time);
      return data;
    },
    refetchInterval: 30_000,
  });

/* ----------------------------------------------------------------------------- écritures */

export const createStrategy = (name: string) => apiFetch("/strategies", StrategySchema, { method: "POST", body: { name } });

export const depositVersion = (strategyId: string, body: { manifest: Record<string, unknown>; code: string }, idempotencyKey: string) =>
  apiFetch(`/strategies/${strategyId}/versions`, VersionDetailSchema, { method: "POST", body, headers: { "Idempotency-Key": idempotencyKey } });

export const changeStatus = (strategyId: string, version: number, status: VersionStatus) =>
  apiFetch(`/strategies/${strategyId}/versions/${version}`, VersionSchema, { method: "PATCH", body: { status } });

/** Toujours paper : le live ne se choisit pas ici, il passe par la promotion (F1). */
export const deployPaper = (body: { name: string; params: Record<string, unknown>; strategy_version_id: string; account_id: string }, idempotencyKey: string) =>
  apiFetch("/instances", InstanceSchema, { method: "POST", body: { ...body, mode: "paper" }, headers: { "Idempotency-Key": idempotencyKey } });

/* ------------------------------------------------------------------------- présentation */

/** Transitions permises par l'API : brouillon -> approuvée -> retirée. */
export const NEXT_STATUS: Record<VersionStatus, VersionStatus | null> = { draft: "approved", approved: "retired", retired: null };

export const shortHash = (hash: string, n = 12) => hash.slice(0, n);

/** Même motif que l'API pour le nom d'une instance. */
export const INSTANCE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
/** Même motif que l'API pour le nom d'une stratégie. */
export const STRATEGY_NAME = /^[a-z0-9][a-z0-9_-]{0,63}$/;
