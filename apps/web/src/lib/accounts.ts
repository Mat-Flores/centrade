import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { ApiError, apiFetch } from "./api";
import { observeServerTime } from "./clock";

/** Formes de l'API des comptes (apps/api/centrade_api/accounts.py). Aucune clé n'y revient jamais : seulement des dates. */

export const KeySchema = z.object({
  usage: z.enum(["trade", "read"]),
  key_version: z.number(),
  stored_at: z.string(),
  rotated_at: z.string().nullable(),
  last_used_at: z.string().nullable(),
});
export type Key = z.infer<typeof KeySchema>;
export type KeyUsage = Key["usage"];

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

export const TestResultSchema = z.object({ result: z.enum(["verified", "refused", "unverified"]), account: AccountSchema });
export type TestResult = z.infer<typeof TestResultSchema>;

export const accountsKey = ["accounts"] as const;
const LIMIT = 200;

export const accountsQuery = queryOptions({
  queryKey: accountsKey,
  queryFn: async ({ signal }) => {
    const page = await apiFetch(`/accounts?limit=${LIMIT}`, AccountPageSchema, { signal });
    observeServerTime(page.server_time);
    return page;
  },
});

/* ----------------------------------------------------------------- validation des formulaires */

// Mêmes règles que l'API (AccountCreate) ; le plafond reste une chaîne décimale, jamais un nombre.
export const CAPITAL = /^\d{1,19}(\.\d{1,18})?$/;

export const AccountFormSchema = z.object({
  label: z.string().trim().min(1, "label").max(80, "label"),
  venue: z.string().trim().regex(/^[a-z][a-z0-9_-]{0,31}$/, "venue"),
  type: z.enum(["paper", "live"]),
  environment: z.enum(["production", "sandbox"]),
  currency: z
    .string()
    .trim()
    .toUpperCase()
    .regex(/^[A-Z0-9]{2,10}$/, "currency"),
  // Vide : aucun plafond. Sinon chaîne décimale strictement positive.
  capital_cap: z
    .string()
    .trim()
    .refine((v) => v === "" || (CAPITAL.test(v) && /[1-9]/.test(v)), "capital_cap"),
});
export type AccountForm = z.infer<typeof AccountFormSchema>;

/** Champs en erreur d'un formulaire de compte ; vide si tout est valide. */
export function accountFormErrors(raw: Record<string, unknown>): { data: AccountForm | null; fields: string[] } {
  const parsed = AccountFormSchema.safeParse(raw);
  if (parsed.success) return { data: parsed.data, fields: [] };
  return { data: null, fields: [...new Set(parsed.error.issues.map((i) => String(i.path[0])))] };
}

export const SecretFormSchema = z.object({
  key: z.string().min(1).max(512),
  secret: z.string().min(1).max(1024),
});

/** La saisie du libellé doit être exacte (espaces de bord tolérés) : confirmation d'une action dangereuse. */
export const labelMatches = (typed: string, label: string) => typed.trim() === label;

/* ------------------------------------------------------------------------------- écritures */

export async function createAccount(form: AccountForm): Promise<Account> {
  const { capital_cap, ...rest } = form;
  return apiFetch("/accounts", AccountSchema, {
    method: "POST",
    body: capital_cap === "" ? rest : { ...rest, capital_cap },
  });
}

export const testAccount = (id: string) => apiFetch(`/accounts/${id}/test`, TestResultSchema, { method: "POST" });

export interface KeyInput {
  usage: KeyUsage;
  key: string;
  secret: string;
}

/**
 * Dépôt (PUT) ou rotation (POST) d'une clé. Volontairement hors de `useMutation` : TanStack Query garde
 * les variables d'une mutation dans son cache (`gcTime`), et la valeur d'une clé ne doit exister nulle part
 * en dehors de cette requête. La fonction ne la conserve pas ; l'appelant l'a déjà effacée du champ.
 */
export function writeKey(accountId: string, mode: "put" | "rotate", input: KeyInput): Promise<Key> {
  return apiFetch(mode === "put" ? `/accounts/${accountId}/secret` : `/accounts/${accountId}/rotate`, KeySchema, {
    method: mode === "put" ? "PUT" : "POST",
    body: input,
  });
}

/* ---------------------------------------------------------------------------- présentation */

export type PermissionState =
  | { kind: "none" } // compte paper : aucune clé, rien à vérifier
  | { kind: "no-key" }
  | { kind: "verified"; at: string }
  | { kind: "unverified" };

export function permissionState(a: Account): PermissionState {
  if (a.type === "paper") return { kind: "none" };
  if (a.trade_key === null) return { kind: "no-key" };
  return a.permissions_verified_at ? { kind: "verified", at: a.permissions_verified_at } : { kind: "unverified" };
}

export type ErrorCause = "totp" | "refused" | "forbidden" | "network" | "other";

/** Cause d'un échec d'écriture, pour afficher la cause et l'action possible (jamais « une erreur est survenue »). */
export function errorCause(error: unknown): { cause: ErrorCause; detail: string | null } {
  if (!(error instanceof ApiError)) return { cause: "other", detail: null };
  if (error.kind === "network") return { cause: "network", detail: null };
  const detail = error.problem?.detail ?? error.problem?.title ?? null;
  if (error.status === 403) return { cause: /totp/i.test(detail ?? "") ? "totp" : "forbidden", detail };
  if (error.status === 409) return { cause: "refused", detail };
  return { cause: "other", detail };
}
