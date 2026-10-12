import type { Page, Route } from "@playwright/test";

import { command, mockCockpit, type Api, type Json } from "./cockpit-support";

/** Positions, ordres et trades simulés : formes de apps/api/centrade_api/trading.py, heures relatives à `now`. */
const iso = (ms: number) => new Date(ms).toISOString();
export const ID = (n: number) => `00000000-0000-4000-8000-0000000000${String(n).padStart(2, "0")}`;
// Instances de `world` : alpha=1 (paper), bravo=2 (périmée), charlie=3 (inconnue), delta=4 (live observé), echo=5.

export function position(now: number, over: Json & { id: string; instance_id: string }): Json {
  return {
    mode: "paper",
    account_id: over.instance_id === ID(4) ? null : "acc-paper", // delta (live) : sans compte
    account_label: over.instance_id === ID(4) ? null : "Bac paper",
    instrument: "BTC/USDT",
    side: "long",
    quantity: "0.5",
    entry_price: "60000.50",
    currency: "USDT",
    observed_at: iso(now - 2000),
    stale: false,
    stop_price: "57000.25",
    stop_venue: "venue",
    stop_type: "fixed",
    stop_distance_pct: "5.0001",
    protection_state: "protected",
    protection_verified_at: iso(now - 3000),
    ...over,
  };
}
export function order(now: number, over: Json & { id: string; instance_id: string }): Json {
  return {
    mode: "paper",
    account_id: over.instance_id === ID(4) ? null : "acc-paper", // delta (live) : sans compte
    account_label: over.instance_id === ID(4) ? null : "Bac paper",
    client_order_id: `co-${over.id}`,
    instrument: "BTC/USDT",
    side: "buy",
    intent: "entry",
    status: "open",
    quantity: "0.1",
    price: "59000",
    currency: "USDT",
    decision_id: null,
    observed_at: iso(now - 2000),
    stale: false,
    cancelable: true,
    created_at: iso(now - 60_000),
    ...over,
  };
}
export function trade(now: number, over: Json & { id: string; instance_id: string }): Json {
  return {
    mode: "paper",
    account_id: over.instance_id === ID(4) ? null : "acc-paper", // delta (live) : sans compte
    account_label: over.instance_id === ID(4) ? null : "Bac paper",
    instrument: "BTC/USDT",
    quantity: "0.25",
    entry_price: "60000.50",
    exit_price: "59000.25",
    entry_cause: "signal",
    exit_cause: "stop_loss",
    pnl: "-12.50",
    fees: "0.10",
    currency: "USDT",
    opened_at: iso(now - 7_200_000),
    closed_at: iso(now - 3_600_000),
    duration_s: 3600,
    ...over,
  };
}

export function tradingWorld(now: number) {
  const positions = [
    position(now, { id: ID(21), instance_id: ID(1), instrument: "BTC/USDT" }),
    position(now, { id: ID(22), instance_id: ID(1), instrument: "ETH/USDT", quantity: "2", entry_price: "3000", stop_price: null, stop_venue: null, stop_type: null, stop_distance_pct: null, protection_state: "unprotected" }),
    position(now, { id: ID(23), instance_id: ID(2), instrument: "SOL/USDT", quantity: "10", entry_price: "150.125", observed_at: iso(now - 95_000), stale: true, stop_venue: "engine", stop_type: "trailing", stop_price: "140", stop_distance_pct: "6.7415", protection_state: "engine_only", protection_verified_at: iso(now - 95_000) }),
    position(now, { id: ID(24), instance_id: ID(3), instrument: "ADA/USDT", quantity: "100", entry_price: "0.4521", stop_price: null, stop_venue: null, stop_type: null, stop_distance_pct: null, protection_state: "unknown", protection_verified_at: null }),
    position(now, { id: ID(25), instance_id: ID(4), mode: "live", currency: "EUR", instrument: "BTC/EUR", quantity: "0.01", entry_price: "55000" }),
  ];
  const orders = [
    order(now, { id: ID(31), instance_id: ID(1) }),
    order(now, { id: ID(32), instance_id: ID(1), intent: "exit", side: "sell", price: "61000", cancelable: false }),
    order(now, { id: ID(33), instance_id: ID(1), intent: "stop", side: "sell", price: "57000.25", cancelable: false, instrument: "ETH/USDT" }),
    order(now, { id: ID(34), instance_id: ID(5), status: "filled", cancelable: false }),
  ];
  const trades = [
    trade(now, { id: ID(41), instance_id: ID(1) }),
    trade(now, { id: ID(42), instance_id: ID(1), pnl: "-0.10", exit_cause: "stop_loss", closed_at: iso(now - 3_000_000) }),
    trade(now, { id: ID(43), instance_id: ID(1), pnl: "30.25", exit_cause: "take_profit", closed_at: iso(now - 2_000_000) }),
    trade(now, { id: ID(44), instance_id: ID(4), mode: "live", currency: "EUR", pnl: "5.5", exit_cause: "manual", instrument: "BTC/EUR" }),
    trade(now, { id: ID(45), instance_id: ID(5), currency: "EUR", pnl: "-3", exit_cause: "signal" }),
  ];
  return { positions, orders, trades };
}

export const paperAccount = (now: number): Json => ({
  id: "acc-paper",
  venue: "paper",
  type: "paper",
  environment: "sandbox",
  label: "Bac paper",
  currency: "USDT",
  capital_cap: "10000",
  trade_key: null,
  read_key: null,
  permissions_verified_at: null,
  ip_restricted: null,
  created_at: iso(now - 86_400_000),
  updated_at: iso(now - 86_400_000),
});

export interface Trading {
  positions: Json[];
  orders: Json[];
  trades: Json[];
  listStatus: number;
  requests: { method: string; path: string; search: string; key: string | undefined }[];
}

const reply = (route: Route, status: number, body: unknown, ct = "application/json") => route.fulfill({ status, contentType: ct, body: JSON.stringify(body) });

/** Cockpit simulé, plus les routes de trading : lecture filtrée par instance, fermeture (202) et annulation (202 ou 409). */
export async function mockTrading(page: Page, opts: { now?: () => number; role?: "viewer" | "operator" | "admin"; data?: Partial<Pick<Api, "instances" | "commands" | "alerts">> } = {}) {
  const now = opts.now ?? (() => Date.now());
  const api = await mockCockpit(page, { now, role: opts.role, data: opts.data });
  const w = tradingWorld(now());
  const state: Trading = { positions: w.positions, orders: w.orders, trades: w.trades, listStatus: 200, requests: [] };
  await page.route(/\/api\/v1\/(positions|orders|trades)/, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const p = url.pathname.replace("/api/v1", "");
    const [, kind, id, verb] = p.split("/") as [string, "positions" | "orders" | "trades", string?, string?];
    state.requests.push({ method: req.method(), path: p, search: url.search, key: req.headers()["idempotency-key"] });
    if (req.method() === "GET") {
      if (state.listStatus !== 200) return reply(route, state.listStatus, { title: "Error", status: state.listStatus }, "application/problem+json");
      const inst = url.searchParams.get("instance_id");
      const items = state[kind].filter((r) => !inst || r.instance_id === inst);
      return reply(route, 200, { items, next_cursor: null, server_time: iso(now()) });
    }
    const target = state[kind].find((r) => r.id === id);
    if (!target) return reply(route, 404, { title: "Not Found", status: 404 }, "application/problem+json");
    const accepted = (type: string) => {
      const cmd = command(now(), { id: `cmd-${type}-${id}`, instance_id: target.instance_id as string, type });
      api.commands.unshift(cmd);
      return reply(route, 202, { command_id: cmd.id, command: cmd });
    };
    if (kind === "positions" && verb === "close") return accepted("close_position");
    if (kind === "orders" && req.method() === "DELETE") {
      if (target.intent !== "entry" && target.intent !== "increase") return reply(route, 409, { type: "about:blank", title: "Conflict", status: 409, detail: "Annuler une sortie ou un stop augmente le risque : la plateforme ne le propose pas." }, "application/problem+json");
      return accepted("cancel_entry_order");
    }
    return reply(route, 404, { title: "Not Found", status: 404 }, "application/problem+json");
  });
  await page.route(/\/api\/v1\/accounts/, (route) => reply(route, 200, { items: [paperAccount(now())], next_cursor: null, server_time: iso(now()) }));
  return { api, state };
}
