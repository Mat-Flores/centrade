import type { Page, Route } from "@playwright/test";

import { mockCockpit, type Api, type Json } from "./cockpit-support";
import { ID, paperAccount } from "./trading-support";

const iso = (ms: number) => new Date(ms).toISOString();
const reply = (route: Route, status: number, body: unknown, ct = "application/json") => route.fulfill({ status, contentType: ct, body: JSON.stringify(body) });

export const S1 = "00000000-0000-4000-8000-0000000000a1";

export const manifest = (): Json => ({
  name: "sma-cross",
  engine: "fake",
  version: 2,
  entrypoint: "sma_cross.SmaCross",
  asset_classes: ["crypto"],
  trading_mode: "spot",
  timeframes: ["5m"],
  modes: ["paper", "live"],
  params_schema: {
    type: "object",
    required: ["fast"],
    properties: {
      fast: { type: "integer", title: "Moyenne rapide", default: 10, minimum: 2, maximum: 50 },
      slow: { type: "integer", title: "Moyenne lente", default: 30, minimum: 5 },
    },
  },
  sizing: { stake_amount: "100.50", max_open_positions: 3 },
  exits: { stoploss: "-0.05", stop_on_venue: true, trailing: {}, take_profit: { "60": "0.02" } },
  risk_defaults: { max_notional_per_order: "500" },
  requires_data: [],
});

export const version = (now: number, n: number, status: string): Json => ({
  id: `00000000-0000-4000-8000-0000000000b${n}`,
  strategy_id: S1,
  version: n,
  status,
  engine: "fake",
  manifest: manifest(),
  code_hash: `a1b2c3d4e5f60718293a4b5c6d7e8f90${n}`,
  author: "operateur@example.test",
  static_checks: { ok: true, errors: [], checked_at: iso(now - 86_400_000) },
  exits: (manifest().exits as Json),
  created_at: iso(now - n * 3_600_000),
});

const ref = (now: number): Json => ({ version_id: version(now, 2, "approved").id, strategy_id: S1, name: "sma-cross", version: 2, status: "approved", code_hash: "a1b2c3d4e5f60718293a4b5c6d7e8f902", exits: manifest().exits });
const account = { id: "acc-paper", venue: "paper", type: "paper", environment: "sandbox", label: "Bac paper", currency: "USDT" };
const cfg = (over: Json = {}): Json => ({ mode: "paper", stake_amount: "100.50", stoploss: "-0.05", engine_version: "2026.9", ...over });

export function strategiesWorld(now: number) {
  const base = { strategy: ref(now), account, deployment_fingerprint: "f".repeat(64), config_hash: "c".repeat(64) };
  const fresh = (ageS: number, stale = false) => iso(now - ageS * 1000) && { observed_at: iso(now - ageS * 1000), stale };
  const details: Record<string, Json> = {
    [ID(1)]: { ...base, effective_config: { value: cfg(), ...fresh(4) }, drift: { value: [], ...fresh(4) } },
    [ID(2)]: { ...base, effective_config: { value: cfg({ stoploss: "-0.10" }), ...fresh(95, true) }, drift: { value: [{ key: "stoploss", expected: "-0.05", observed: "-0.10" }], ...fresh(95, true) } },
    [ID(3)]: { ...base, strategy: null, account: null, deployment_fingerprint: null, config_hash: null, effective_config: { value: null, observed_at: null, stale: false }, drift: { value: null, observed_at: null, stale: false } },
    [ID(4)]: { ...base, effective_config: { value: cfg({ mode: "live" }), ...fresh(4) }, drift: { value: [{ key: "mode", expected: "paper", observed: "live" }], ...fresh(4) } },
    [ID(5)]: { ...base, effective_config: { value: null, observed_at: null, stale: false }, drift: { value: null, observed_at: null, stale: false } },
  };
  return { versions: [version(now, 2, "approved"), version(now, 1, "draft")], details };
}

export interface Registry {
  strategies: Json[];
  versions: Json[];
  details: Record<string, Json>;
  /** Motifs de refus renvoyés au prochain dépôt (422) ; vide : accepté. */
  reasons: string[];
  requests: { method: string; path: string; body: Json | null; key: string | undefined }[];
}

/** Cockpit simulé, plus le registre de stratégies, le détail d'instance et le déploiement (POST /instances). */
export async function mockRegistry(page: Page, opts: { now?: () => number; role?: "viewer" | "operator" | "admin"; data?: Partial<Pick<Api, "instances" | "commands" | "alerts">> } = {}) {
  const now = opts.now ?? (() => Date.now());
  const api = await mockCockpit(page, { now, role: opts.role, data: opts.data });
  const w = strategiesWorld(now());
  const state: Registry = { strategies: [{ id: S1, name: "sma-cross", created_at: iso(now() - 86_400_000) }], versions: w.versions, details: w.details, reasons: [], requests: [] };
  api.actionResponse = (path) => {
    const id = path.split("/")[2]!;
    const type = path.split("/")[3]!.replace("-", "_");
    const cmd = { id: `cmd-${type}-${id}`, instance_id: id, type, status: "requested", requested_at: iso(now()), deadline_at: iso(now() + 30_000), dispatched_at: null, acknowledged_at: null, verified_at: null, failed_at: null, timed_out_at: null, superseded_at: null, result: null, server_time: iso(now()) };
    api.commands.unshift(cmd);
    return { status: 202, body: { command_id: cmd.id, command: cmd } };
  };

  await page.route(/\/api\/v1\/accounts/, (route) => reply(route, 200, { items: [paperAccount(now())], next_cursor: null, server_time: iso(now()) }));
  await page.route(/\/api\/v1\/(strategies|instances)/, async (route) => {
    const req = route.request();
    const p = new URL(req.url()).pathname.replace("/api/v1", "");
    const parts = p.split("/");
    const body = req.postData() ? (JSON.parse(req.postData()!) as Json) : null;
    const logged = () => state.requests.push({ method: req.method(), path: p, body, key: req.headers()["idempotency-key"] });
    const page_ = (items: Json[]) => reply(route, 200, { items, next_cursor: null, server_time: iso(now()) });

    if (parts[1] === "instances") {
      if (parts.length === 3 && req.method() === "GET") {
        const inst = api.instances.find((i) => i.id === parts[2]);
        return inst ? reply(route, 200, { ...inst, ...state.details[parts[2]!], server_time: iso(now()) }) : reply(route, 404, { title: "Not Found", status: 404 }, "application/problem+json");
      }
      if (p === "/instances" && req.method() === "POST") {
        logged();
        const created = { id: ID(60), name: (body as Json).name, engine: "fake", desired_mode: "paper", desired_state: "exits_only", state: { value: "unknown", observed_at: null, stale: false }, observed_mode: { value: "unknown", observed_at: null, stale: false }, mode_mismatch: false, active_command: null, created_at: iso(now()), server_time: iso(now()) };
        api.instances.unshift(created);
        state.details[ID(60)] = { strategy: ref(now()), account, deployment_fingerprint: null, config_hash: null, effective_config: { value: null, observed_at: null, stale: false }, drift: { value: null, observed_at: null, stale: false } };
        return reply(route, 201, created);
      }
      return route.fallback();
    }
    // /strategies...
    if (p === "/strategies") {
      if (req.method() === "GET") return page_(state.strategies);
      logged();
      const created = { id: "00000000-0000-4000-8000-0000000000a2", name: (body as Json).name, created_at: iso(now()) };
      state.strategies.unshift(created);
      return reply(route, 201, created);
    }
    const n = Number(parts[4]);
    if (parts[3] === "versions" && parts.length === 4) {
      if (req.method() === "GET") return page_(state.versions);
      logged();
      if (state.reasons.length > 0) return reply(route, 422, { type: "about:blank", title: "Unprocessable Entity", status: 422, detail: state.reasons }, "application/problem+json");
      const v = { ...version(now(), state.versions.length + 1, "draft"), manifest: (body as Json).manifest, code: (body as Json).code };
      state.versions.unshift(v);
      return reply(route, 201, v);
    }
    if (parts[3] === "versions" && parts.length === 5) {
      const v = state.versions.find((x) => x.version === n);
      if (!v) return reply(route, 404, { title: "Not Found", status: 404 }, "application/problem+json");
      if (req.method() === "GET") return reply(route, 200, { ...v, code: "class SmaCross:\n    pass\n" });
      logged();
      v.status = (body as Json).status;
      return reply(route, 200, v);
    }
    return route.fallback();
  });
  return { api, state };
}
