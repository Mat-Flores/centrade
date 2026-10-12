import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { apiFetch } from "./api";
import { observeServerTime } from "./clock";
import { sumDecimals } from "./decimal";
import { CommandAcceptedSchema } from "./instances";

/** Formes de l'API de trading (apps/api/centrade_api/trading.py). Argent et quantités : chaînes décimales. */

const Mode = z.enum(["paper", "live"]);
export type TradingMode = z.infer<typeof Mode>;

export const PROTECTION_STATES = ["protected", "engine_only", "unprotected", "unknown"] as const;
export const EXIT_CAUSES = [
  "stop_loss",
  "trailing_stop",
  "take_profit",
  "signal",
  "timeout",
  "manual",
  "kill_switch",
  "engine_protection",
  "liquidation",
  "unknown",
] as const;
export type ExitCause = (typeof EXIT_CAUSES)[number];

export const OrderSchema = z.object({
  id: z.string(),
  instance_id: z.string(),
  mode: Mode,
  account_id: z.string().nullable(),
  account_label: z.string().nullable(),
  client_order_id: z.string(),
  instrument: z.string(),
  side: z.string(),
  intent: z.string(),
  status: z.string(),
  quantity: z.string(),
  price: z.string().nullable(),
  currency: z.string(),
  decision_id: z.string().nullable(),
  observed_at: z.string(),
  stale: z.boolean(),
  cancelable: z.boolean(),
  created_at: z.string(),
});
export type Order = z.infer<typeof OrderSchema>;

export const PositionSchema = z.object({
  id: z.string(),
  instance_id: z.string(),
  mode: Mode,
  account_id: z.string().nullable(),
  account_label: z.string().nullable(),
  instrument: z.string(),
  side: z.string(),
  quantity: z.string(),
  entry_price: z.string().nullable(),
  currency: z.string(),
  observed_at: z.string(),
  stale: z.boolean(),
  stop_price: z.string().nullable(),
  stop_venue: z.string().nullable(),
  stop_type: z.string().nullable(),
  stop_distance_pct: z.string().nullable(),
  protection_state: z.enum(PROTECTION_STATES),
  protection_verified_at: z.string().nullable(),
});
export type Position = z.infer<typeof PositionSchema>;

export const TradeSchema = z.object({
  id: z.string(),
  instance_id: z.string(),
  mode: Mode,
  account_id: z.string().nullable(),
  account_label: z.string().nullable(),
  instrument: z.string(),
  quantity: z.string(),
  entry_price: z.string(),
  exit_price: z.string(),
  entry_cause: z.string(),
  exit_cause: z.enum(EXIT_CAUSES),
  pnl: z.string(),
  fees: z.string(),
  currency: z.string(),
  opened_at: z.string(),
  closed_at: z.string(),
  duration_s: z.number(),
});
export type Trade = z.infer<typeof TradeSchema>;

const page = <T extends z.ZodType>(item: T) =>
  z.object({ items: z.array(item), next_cursor: z.string().nullable(), server_time: z.string() });

export interface TradingFilters {
  instanceId: string;
  accountId: string;
}
export const NO_FILTERS: TradingFilters = { instanceId: "", accountId: "" };

const LIMIT = 200;
const SCHEMAS = { orders: OrderSchema, positions: PositionSchema, trades: TradeSchema } as const;
export type TradingKind = keyof typeof SCHEMAS;
export const tradingKey = (kind?: TradingKind, filters?: TradingFilters) =>
  ["trading", kind, filters].filter((x) => x !== undefined);

function query(f: TradingFilters): string {
  const params = new URLSearchParams({ limit: String(LIMIT) });
  if (f.instanceId) params.set("instance_id", f.instanceId);
  if (f.accountId) params.set("account_id", f.accountId);
  return params.toString();
}

function listQuery<K extends TradingKind>(kind: K, filters: TradingFilters) {
  return queryOptions({
    queryKey: tradingKey(kind, filters),
    queryFn: async ({ signal }) => {
      const data = await apiFetch(`/${kind}?${query(filters)}`, page(SCHEMAS[kind]), { signal });
      observeServerTime(data.server_time);
      return data as { items: z.infer<(typeof SCHEMAS)[K]>[]; next_cursor: string | null; server_time: string };
    },
    staleTime: Infinity, // tenu à jour par le flux (invalidation) ; relu à la reconnexion
  });
}
export const ordersQuery = (f: TradingFilters) => listQuery("orders", f);
export const positionsQuery = (f: TradingFilters) => listQuery("positions", f);
export const tradesQuery = (f: TradingFilters) => listQuery("trades", f);

/** Fermer une position est une commande (F9) : l'API répond 202, jamais « fait ». Rejouable par sa clé. */
export const closePosition = (id: string, idempotencyKey: string) =>
  apiFetch(`/positions/${id}/close`, CommandAcceptedSchema, { method: "POST", headers: { "Idempotency-Key": idempotencyKey } });

/** Annuler un ordre d'entrée seulement : l'API refuse (409) toute sortie ou tout stop. */
export const cancelOrder = (id: string, idempotencyKey: string) =>
  apiFetch(`/orders/${id}`, CommandAcceptedSchema, { method: "DELETE", headers: { "Idempotency-Key": idempotencyKey } });

/* ------------------------------------------------------------------ présentation */

/** Regroupe des lignes par compte, dans l'ordre d'apparition ; les lignes sans compte forment un groupe à part. */
export function groupByAccount<T extends { account_id: string | null; account_label: string | null }>(rows: readonly T[]): { key: string; label: string | null; rows: T[] }[] {
  const groups = new Map<string, { key: string; label: string | null; rows: T[] }>();
  for (const r of rows) {
    const key = r.account_id ?? "";
    const g = groups.get(key) ?? { key, label: r.account_label, rows: [] };
    g.rows.push(r);
    groups.set(key, g);
  }
  return [...groups.values()];
}

/** Les moins protégées d'abord : `unprotected`, puis `unknown`, `engine_only`, `protected`. Stable. */
const RANK: Record<Position["protection_state"], number> = { unprotected: 0, unknown: 1, engine_only: 2, protected: 3 };
export function sortPositions(positions: readonly Position[]): Position[] {
  return positions.map((p, i) => [p, i] as const).sort(([a, i], [b, j]) => RANK[a.protection_state] - RANK[b.protection_state] || i - j).map(([p]) => p);
}

export interface Total {
  mode: TradingMode;
  currency: string;
  pnl: string;
  fees: string;
  count: number;
}

/**
 * Totaux par mode ET par devise : jamais de somme entre paper et live, ni entre devises (SPEC §9).
 * Live d'abord, puis paper ; devises dans l'ordre alphabétique.
 */
export function totalsByModeCurrency(trades: readonly Trade[]): Total[] {
  const groups = new Map<string, Trade[]>();
  for (const t of trades) {
    const key = `${t.mode}|${t.currency}`;
    groups.set(key, [...(groups.get(key) ?? []), t]);
  }
  return [...groups.values()]
    .map((g) => ({ mode: g[0]!.mode, currency: g[0]!.currency, pnl: sumDecimals(g.map((t) => t.pnl)), fees: sumDecimals(g.map((t) => t.fees)), count: g.length }))
    .sort((a, b) => (a.mode === b.mode ? a.currency.localeCompare(b.currency) : a.mode === "live" ? -1 : 1));
}

export interface Breakdown {
  instanceId: string;
  total: number;
  causes: { cause: ExitCause; count: number }[];
}

/** Répartition des sorties par cause, par instance : causes les plus fréquentes d'abord. */
export function exitBreakdown(trades: readonly Trade[]): Breakdown[] {
  const byInstance = new Map<string, Map<ExitCause, number>>();
  for (const t of trades) {
    const causes = byInstance.get(t.instance_id) ?? new Map<ExitCause, number>();
    causes.set(t.exit_cause, (causes.get(t.exit_cause) ?? 0) + 1);
    byInstance.set(t.instance_id, causes);
  }
  return [...byInstance].map(([instanceId, causes]) => ({
    instanceId,
    total: [...causes.values()].reduce((a, b) => a + b, 0),
    causes: [...causes].map(([cause, count]) => ({ cause, count })).sort((a, b) => b.count - a.count || EXIT_CAUSES.indexOf(a.cause) - EXIT_CAUSES.indexOf(b.cause)),
  }));
}
