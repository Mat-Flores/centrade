import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { apiFetch } from "./api";
import { observeServerTime } from "./clock";

/** Shapes of the strategy registry API (V2/apps/api/centrade_api/strategies/schemas.py). Read-only here. */

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

const page = <T extends z.ZodType>(item: T) =>
  z.object({ items: z.array(item), next_cursor: z.string().nullable(), server_time: z.string() });

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

/** Only approved versions can be deployed (draft and retired are never offered). */
export const approvedVersions = (versions: readonly Version[]): Version[] =>
  versions.filter((v) => v.status === "approved").sort((a, b) => b.version - a.version);

/** Same pattern as the API for a strategy name. */
export const STRATEGY_NAME = /^[a-z0-9][a-z0-9_-]{0,63}$/;
