import type { Page, Route } from "@playwright/test";

import { ME } from "./support";

/** Données simulées du Cockpit : formes de apps/api/centrade_api/schemas.py, heures relatives à `now`. */

export type Json = Record<string, unknown>;
export const T0 = Date.parse("2026-10-11T15:00:00Z"); // horloge figée des captures (11 oct. 2026, 11:00 HAE)

const iso = (ms: number) => new Date(ms).toISOString();

export function observed(value: string, now: number, ageS: number | null, stale = false) {
  return { value, observed_at: ageS === null ? null : iso(now - ageS * 1000), stale };
}

export function instance(now: number, over: Json & { name: string; id: string }): Json {
  return {
    engine: "fake",
    desired_mode: "paper",
    desired_state: "exits_only",
    state: observed("exits_only", now, 2),
    observed_mode: observed("paper", now, 2),
    mode_mismatch: false,
    active_command: null,
    created_at: iso(now - 3_600_000),
    server_time: iso(now),
    ...over,
  };
}

export function command(now: number, over: Json & { id: string; instance_id: string }): Json {
  return {
    type: "resume_entries",
    status: "requested",
    requested_at: iso(now - 4000),
    deadline_at: iso(now + 26_000),
    dispatched_at: null,
    acknowledged_at: null,
    verified_at: null,
    failed_at: null,
    timed_out_at: null,
    superseded_at: null,
    result: null,
    server_time: iso(now),
    ...over,
  };
}

/** Quatre instances : fraîche, périmée, inconnue, mode incohérent. */
export function world(now: number) {
  const instances = [
    instance(now, { id: "00000000-0000-4000-8000-000000000001", name: "alpha", desired_state: "running", state: observed("exits_only", now, 3), created_at: iso(now - 1000) }),
    instance(now, { id: "00000000-0000-4000-8000-000000000002", name: "bravo", desired_state: "running", state: observed("running", now, 95, true), observed_mode: observed("paper", now, 95, true), created_at: iso(now - 2000) }),
    instance(now, { id: "00000000-0000-4000-8000-000000000003", name: "charlie", desired_state: "exits_only", state: observed("unknown", now, null), observed_mode: observed("unknown", now, null), created_at: iso(now - 3000) }),
    instance(now, { id: "00000000-0000-4000-8000-000000000004", name: "delta", desired_state: "running", state: observed("running", now, 4), observed_mode: observed("live", now, 4), mode_mismatch: true, created_at: iso(now - 4000) }),
    instance(now, { id: "00000000-0000-4000-8000-000000000005", name: "echo", desired_state: "running", state: observed("running", now, 1), created_at: iso(now - 5000) }),
  ];
  const alerts = [
    { id: "a1", rule: "mode_mismatch", severity: "critical", target_kind: "instance", target_id: instances[3]!.id, status: "open", message: "Le mode observé diffère du mode voulu (I3).", created_at: iso(now - 90_000) },
    { id: "a2", rule: "engine_silent", severity: "warning", target_kind: "instance", target_id: instances[1]!.id, status: "open", message: "Le moteur ne donne plus de relevé.", created_at: iso(now - 600_000) },
  ];
  const health = (status: "ok" | "degraded" = "ok", workerDown = false) => ({
    status,
    ts: iso(now),
    checks: {
      database: { status: "ok", observed_at: iso(now - 3000) },
      bus: { status: "ok", observed_at: iso(now - 3000) },
      worker: { status: workerDown ? "down" : "ok", observed_at: iso(now - 3000) },
    },
  });
  return { instances, alerts, health };
}

export interface Api {
  now: () => number;
  instances: Json[];
  commands: Json[];
  alerts: Json[];
  health: Json;
  healthFails: boolean;
  instancesStatus: number;
  instancesDelayMs: number;
  /** Réponse aux POST d'action (par défaut 202 `requested`). */
  actionResponse: (path: string) => { status: number; body: Json; contentType?: string };
  requests: { path: string; method: string; headers: Record<string, string>; body: string | null }[];
}

const page_ = (items: Json[], now: number) => ({ items, next_cursor: null, server_time: iso(now) });
const fulfill = (route: Route, status: number, body: unknown, contentType = "application/json") =>
  route.fulfill({ status, contentType, body: JSON.stringify(body) });

/** Simule l'API du Cockpit et l'EventSource (contrôlé par `emit`). `realtime: false` : pas de temps réel du tout. */
export async function mockCockpit(
  page: Page,
  opts: { now?: () => number; role?: "viewer" | "operator" | "admin"; data?: Partial<Pick<Api, "instances" | "commands" | "alerts">>; fixedClock?: boolean } = {},
): Promise<Api> {
  const now = opts.now ?? (() => Date.now());
  const w = world(now());
  const api: Api = {
    now,
    instances: opts.data?.instances ?? w.instances,
    commands: opts.data?.commands ?? [],
    alerts: opts.data?.alerts ?? w.alerts,
    health: w.health(),
    healthFails: false,
    instancesStatus: 200,
    instancesDelayMs: 0,
    actionResponse: () => ({ status: 500, body: {} }),
    requests: [],
  };
  const me = { ...ME, id: "u1", role: opts.role ?? "operator" };

  await page.addInitScript(() => {
    type Listener = (e: { data: string }) => void;
    class FakeEventSource {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      readyState = 0;
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      private listeners: Record<string, Listener[]> = {};
      constructor(public url: string) {
        (window as unknown as { __streams: FakeEventSource[] }).__streams.push(this);
        setTimeout(() => {
          this.readyState = 1;
          this.onopen?.();
        }, 0);
      }
      addEventListener(type: string, fn: Listener) {
        (this.listeners[type] ??= []).push(fn);
      }
      close() {
        this.readyState = 2;
      }
      emit(type: string, data: unknown) {
        for (const fn of this.listeners[type] ?? []) fn({ data: JSON.stringify(data) });
      }
    }
    const w = window as unknown as Record<string, unknown>;
    w.__streams = [];
    w.__beats = true;
    w.EventSource = FakeEventSource;
    w.__emit = (type: string, data: unknown) => (w.__streams as FakeEventSource[]).forEach((s) => s.readyState !== 2 && s.emit(type, data));
    // Battement toutes les 2 s, comme l'API ; coupé par `stopBeats`.
    setInterval(() => w.__beats && (w.__emit as (t: string, d: unknown) => void)("heartbeat", { server_time: new Date().toISOString() }), 2000);
    setTimeout(() => w.__beats && (w.__emit as (t: string, d: unknown) => void)("heartbeat", { server_time: new Date().toISOString() }), 50);
  });

  await page.route("**/api/v1/auth/me", (route) => fulfill(route, 200, me));
  await page.route("**/api/v1/auth/logout", (route) => route.fulfill({ status: 204 }));
  await page.route("**/api/v1/system/health", (route) =>
    api.healthFails ? fulfill(route, 503, { title: "Service Unavailable", status: 503 }, "application/problem+json") : fulfill(route, 200, api.health),
  );
  await page.route(
    (url) => url.pathname.startsWith("/api/v1/") && !/\/(auth|system)\//.test(url.pathname),
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname.replace("/api/v1", "");
      api.requests.push({ path, method: request.method(), headers: request.headers(), body: request.postData() });
      if (request.method() === "POST") {
        if (path === "/instances") {
          const name = (JSON.parse(request.postData() ?? "{}") as { name: string }).name;
          const created = instance(now(), { id: `00000000-0000-4000-8000-0000000000${api.instances.length + 10}`, name, state: observed("unknown", now(), null), observed_mode: observed("unknown", now(), null), created_at: iso(now()) });
          return fulfill(route, 201, created);
        }
        const r = api.actionResponse(path);
        return fulfill(route, r.status, r.body, r.contentType);
      }
      if (path === "/instances") {
        if (api.instancesDelayMs) await new Promise((r) => setTimeout(r, api.instancesDelayMs));
        if (api.instancesStatus !== 200) return fulfill(route, api.instancesStatus, { title: "Error", status: api.instancesStatus }, "application/problem+json");
        return fulfill(route, 200, page_(api.instances, now()));
      }
      if (path === "/commands") return fulfill(route, 200, page_(api.commands, now()));
      if (path === "/alerts") return fulfill(route, 200, page_(api.alerts, now()));
      return fulfill(route, 404, { title: "Not Found", status: 404 }, "application/problem+json");
    },
  );
  return api;
}

export const emit = (page: Page, type: "instance" | "command" | "alert" | "heartbeat", data: unknown) =>
  page.evaluate(([t, d]) => (window as unknown as { __emit: (t: string, d: unknown) => void }).__emit(t as string, d), [type, data] as const);

export const stopBeats = (page: Page) => page.evaluate(() => ((window as unknown as { __beats: boolean }).__beats = false));
export const sseEvent = (now: number, key: "instance" | "command" | "alert", obj: Json) => ({ server_time: iso(now), [key]: obj });
