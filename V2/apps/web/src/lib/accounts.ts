import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { apiFetch } from "./api";
import { observeServerTime } from "./clock";

/** Read side of the accounts API (V2/apps/api/centrade_api/accounts/schemas.py). No key ever comes back: only dates. */

export const KeySchema = z.object({
  usage: z.enum(["trade", "read"]),
  key_version: z.number(),
  stored_at: z.string(),
  rotated_at: z.string().nullable(),
  last_used_at: z.string().nullable(),
});
export type Key = z.infer<typeof KeySchema>;

export const AccountSchema = z.object({
  id: z.string(),
  venue: z.string(),
  type: z.enum(["paper", "live"]),
  environment: z.enum(["production", "sandbox"]),
  label: z.string(),
  currency: z.string(),
  capital_cap: z.string().nullable(),
  trade_key: KeySchema.nullable(),
  read_key: KeySchema.nullable(),
  permissions_verified_at: z.string().nullable(),
  ip_restricted: z.boolean().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Account = z.infer<typeof AccountSchema>;

const AccountPageSchema = z.object({
  items: z.array(AccountSchema),
  next_cursor: z.string().nullable(),
  server_time: z.string(),
});

export const accountsKey = ["accounts"] as const;

export const accountsQuery = queryOptions({
  queryKey: accountsKey,
  queryFn: async ({ signal }) => {
    const data = await apiFetch("/accounts?limit=200", AccountPageSchema, { signal });
    observeServerTime(data.server_time);
    return data;
  },
});

/** Accounts a paper instance can be deployed on. */
export const paperAccounts = (accounts: readonly Account[]): Account[] => accounts.filter((a) => a.type === "paper");
