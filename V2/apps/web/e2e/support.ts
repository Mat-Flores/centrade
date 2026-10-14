import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type Route } from "@playwright/test";

export const ME = { email: "operateur@example.test", role: "operator" };

const json = (route: Route, status: number, body: unknown, type = "application/json") =>
  route.fulfill({ status, contentType: type, body: JSON.stringify(body) });

export const problem = (route: Route, status: number, title: string) =>
  json(route, status, { type: "about:blank", title, status }, "application/problem+json");

/** Simulates the auth API; `state.authenticated` flips when the code is accepted. `codes` records the posted codes. */
export async function mockAuth(page: Page, opts: { authenticated?: boolean; codeStatus?: number; role?: string } = {}) {
  await mockStream(page); // the real EventSource would hit the file server and log a MIME error
  const state = { authenticated: opts.authenticated ?? false, logouts: 0, codes: [] as string[] };
  const me = { ...ME, role: opts.role ?? ME.role };
  await page.route("**/api/v1/auth/me", (route) =>
    state.authenticated ? json(route, 200, me) : problem(route, 401, "Unauthorized"),
  );
  await page.route("**/api/v1/auth/login", (route) => json(route, 200, { totp_required: true }));
  await page.route("**/api/v1/auth/totp", (route) => {
    state.codes.push((route.request().postDataJSON() as { code: string }).code);
    const status = opts.codeStatus ?? 200;
    if (status !== 200) return problem(route, status, "Refused");
    state.authenticated = true;
    return json(route, 200, me);
  });
  await page.route("**/api/v1/auth/logout", (route) => {
    state.authenticated = false;
    state.logouts += 1;
    return route.fulfill({ status: 204 });
  });
  return state;
}

/** Theme is the stored choice of the app (dark by default), set before the first script runs. */
export const storeTheme = (page: Page, theme: "light" | "dark") =>
  page.addInitScript((t) => localStorage.setItem("centrade-theme", t), theme);
export const useTheme = storeTheme;

/** Page errors and console errors, minus the browser's own line for an HTTP error status (an expected 401 on /auth/me). */
export function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && !/^Failed to load resource: the server responded with a status of 4\d\d/.test(m.text())) errors.push(m.text());
  });
  return errors;
}

export async function expectNoViolation(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

export async function signIn(page: Page) {
  await page.goto("/");
  await page.getByLabel("Identifiant").fill("operateur");
  await page.getByLabel("Mot de passe").fill("motdepasse");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Vérification en deux étapes" })).toBeVisible();
}

export async function signOut(page: Page) {
  await page.getByRole("button", { name: `Compte : ${ME.email}` }).click();
  await page.getByRole("menuitem", { name: "Se déconnecter" }).click();
}

/* ------------------------------------------------------------------ cockpit API */

/** Wire object of an observed value, dated `ageS` seconds before the response (so it never ages while the test runs). */
const obs = (value: unknown, ageS: number | null, nowMs: number, stale = false) => ({ value, observed_at: ageS === null ? null : new Date(nowMs - ageS * 1000).toISOString(), stale });

export interface Spec {
  id: string;
  name: string;
  mode?: "paper" | "live";
  desired?: "running" | "exits_only" | "stopped";
  /** Observed state and its age in seconds; `age: null` = never observed. */
  state?: string;
  age?: number | null;
  observedMode?: "paper" | "live";
  mismatch?: boolean;
  strategy?: { name: string; version: number } | null;
  account?: { label: string; currency: string } | null;
  startedAgoS?: number | null;
  /** `undefined` = never observed. */
  pnl?: { currency: string; amount: string; fees?: string }[];
  trades?: number;
  positions?: number;
  balances?: { currency: string; free: string; total: string }[];
  /** Age of pnl / trades / balances rows. */
  dataAge?: number;
}

export function wireInstance(s: Spec, nowMs = Date.now()) {
  const age = s.age === undefined ? 2 : s.age;
  const da = s.dataAge ?? 2;
  const known = age !== null;
  return {
    id: s.id,
    name: s.name,
    engine: "freqtrade",
    desired_mode: s.mode ?? "paper",
    desired_state: s.desired ?? "running",
    state: obs(known ? (s.state ?? "running") : "unknown", age, nowMs),
    observed_mode: obs(known ? (s.observedMode ?? s.mode ?? "paper") : "unknown", age, nowMs),
    mode_mismatch: s.mismatch ?? false,
    active_command: null,
    strategy: s.strategy === null ? null : { version_id: `v-${s.id}`, strategy_id: `s-${s.id}`, name: s.strategy?.name ?? "momentum", version: s.strategy?.version ?? 3, status: "approved", code_hash: "abc", exits: {} },
    account: s.account === null ? null : { id: `a-${s.id}`, venue: "binance", type: s.mode ?? "paper", environment: "sandbox", label: s.account?.label ?? "Paper USDT", currency: s.account?.currency ?? "USDT" },
    started_at: s.startedAgoS == null ? null : new Date(nowMs - s.startedAgoS * 1000).toISOString(),
    realized_pnl: obs(s.pnl ? s.pnl.map((m) => ({ fees: "0", ...m })) : null, s.pnl ? da : null, nowMs),
    closed_trades: obs(s.trades ?? null, s.trades === undefined ? null : da, nowMs),
    open_positions: obs(s.positions ?? null, s.positions === undefined ? null : da, nowMs),
    balances: obs(s.balances ?? null, s.balances ? da : null, nowMs),
    created_at: new Date(nowMs - 3_600_000).toISOString(),
    server_time: new Date(nowMs).toISOString(),
  };
}

export interface CommandSpec { id: string; instance_id: string; type?: string; status: string; agoS?: number; reason?: string }
export const wireCommand = (c: CommandSpec, nowMs = Date.now()) => ({
  id: c.id,
  instance_id: c.instance_id,
  type: c.type ?? "pause_entries",
  status: c.status,
  requested_at: new Date(nowMs - (c.agoS ?? 5) * 1000).toISOString(),
  deadline_at: new Date(nowMs + 20_000).toISOString(),
  // The stage reached carries its own date, as the server does: progress is read from these.
  ...(["dispatched", "acknowledged", "verified", "failed", "timed_out"].includes(c.status) ? { [`${c.status}_at`]: new Date(nowMs).toISOString() } : {}),
  result: c.reason ? { reason: c.reason } : null,
  server_time: new Date(nowMs).toISOString(),
});

export interface World {
  instances: Spec[];
  commands: CommandSpec[];
  strategies: { id: string; name: string }[];
  versions: Record<string, { id: string; version: number; status: string; params_schema?: unknown }[]>;
  accounts: { id: string; label: string; currency: string; type?: string }[];
  /** `instances` answers an error status (a 500) while set. */
  instancesStatus: number;
  /** `commands` answers an error status while set. */
  commandsStatus: number;
  /** The instances page announces a next page: the list is truncated. */
  instancesNextCursor: string | null;
  healthStatus: "ok" | "degraded";
  /** The next deployment answers this problem. */
  deployError: { status: number; body: unknown } | null;
  /** Every POST received: path, Idempotency-Key and JSON body. */
  posts: { path: string; key: string | null; body: unknown }[];
}

export const emptyWorld = (): World => ({
  instances: [], commands: [], strategies: [], versions: {}, accounts: [], instancesStatus: 200, commandsStatus: 200, instancesNextCursor: null, healthStatus: "ok", deployError: null, posts: [],
});

const page_ = <T,>(items: T[], nowMs = Date.now(), nextCursor: string | null = null) => ({ items, next_cursor: nextCursor, server_time: new Date(nowMs).toISOString() });

/** Replaces the browser's EventSource with one the test drives: `emit` delivers a stream event; a heartbeat every second unless muted. */
export async function mockStream(page: Page, opts: { mute?: boolean } = {}) {
  await page.addInitScript((mute) => {
    const w = window as unknown as Record<string, unknown>;
    class FakeEventSource {
      static CLOSED = 2;
      readyState = 0;
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      listeners: Record<string, ((e: { data: string }) => void)[]> = {};
      constructor() {
        w.__stream = this;
        setTimeout(() => { this.readyState = 1; this.onopen?.(); }, 0);
        if (!mute) setInterval(() => this.emit("heartbeat", { server_time: new Date().toISOString() }), 1000);
      }
      addEventListener(name: string, fn: (e: { data: string }) => void) { (this.listeners[name] ??= []).push(fn); }
      emit(name: string, data: unknown) { for (const fn of this.listeners[name] ?? []) fn({ data: JSON.stringify(data) }); }
      close() { this.readyState = 2; }
    }
    w.EventSource = FakeEventSource;
  }, opts.mute ?? false);
  return (name: string, data: Record<string, unknown>) =>
    page.evaluate(([n, d]) => (window as unknown as { __stream: { emit: (n: string, d: unknown) => void } }).__stream.emit(n as string, d), [name, { server_time: new Date().toISOString(), ...data }] as const);
}

/** Simulates the cockpit API (lists, commands, health, strategies, accounts) from a mutable `world`. */
export async function mockCockpit(page: Page, world: World) {
  const slug = (p: string) => p.replace(/^.*\/api\/v1/, "");
  await page.route(/\/api\/v1\/instances(\?.*)?$/, async (route) => {
    const req = route.request();
    if (req.method() === "POST") {
      world.posts.push({ path: "/instances", key: await req.headerValue("idempotency-key"), body: req.postDataJSON() });
      if (world.deployError) return json(route, world.deployError.status, world.deployError.body, "application/problem+json");
      const spec: Spec = { id: "i-new", name: (req.postDataJSON() as { name: string }).name, state: "stopped", desired: "stopped", pnl: [], trades: 0, positions: 0 };
      world.instances.push(spec);
      return json(route, 201, wireInstance(spec));
    }
    if (world.instancesStatus !== 200) return problem(route, world.instancesStatus, "Boom");
    const now = Date.now();
    return json(route, 200, page_(world.instances.map((s) => wireInstance(s, now)), now, world.instancesNextCursor));
  });
  await page.route(/\/api\/v1\/instances\/[^/?]+\/(start|stop|pause-entries|resume-entries|flatten)$/, async (route) => {
    const req = route.request();
    const [, , id, action] = slug(req.url()).split("/");
    world.posts.push({ path: slug(req.url()), key: await req.headerValue("idempotency-key"), body: null });
    const command: CommandSpec = { id: `c-${world.posts.length}`, instance_id: id as string, type: (action as string).replace("-", "_"), status: "requested", agoS: 0 };
    world.commands.unshift(command);
    return json(route, 202, { command_id: command.id, command: wireCommand(command) });
  });
  await page.route(/\/api\/v1\/commands(\?.*)?$/, (route) => {
    if (world.commandsStatus !== 200) return problem(route, world.commandsStatus, "Boom");
    const now = Date.now();
    const status = new URL(route.request().url()).searchParams.getAll("status");
    const items = world.commands.filter((c) => status.length === 0 || status.includes(c.status));
    return json(route, 200, page_(items.map((c) => wireCommand(c, now)), now));
  });
  await page.route(/\/api\/v1\/alerts(\?.*)?$/, (route) => json(route, 200, page_([])));
  await page.route(/\/api\/v1\/system\/health$/, (route) => {
    const now = new Date().toISOString();
    return json(route, 200, { status: world.healthStatus, ts: now, checks: { bus: { status: "ok", observed_at: now }, database: { status: "ok", observed_at: now } } });
  });
  await page.route(/\/api\/v1\/strategies(\?.*)?$/, (route) => json(route, 200, page_(world.strategies.map((s) => ({ ...s, created_at: new Date().toISOString() })))));
  await page.route(/\/api\/v1\/strategies\/[^/]+\/versions(\?.*)?$/, (route) => {
    const id = slug(route.request().url()).split("/")[2] as string;
    const items = (world.versions[id] ?? []).map((v) => ({
      id: v.id, strategy_id: id, version: v.version, status: v.status, engine: "freqtrade", manifest: v.params_schema ? { params_schema: v.params_schema } : {},
      code_hash: "h", author: "op", static_checks: {}, exits: {}, created_at: new Date().toISOString(),
    }));
    return json(route, 200, page_(items));
  });
  await page.route(/\/api\/v1\/accounts(\?.*)?$/, (route) =>
    json(route, 200, page_(world.accounts.map((a) => ({
      id: a.id, venue: "binance", type: a.type ?? "paper", environment: "sandbox", label: a.label, currency: a.currency, capital_cap: null,
      trade_key: null, read_key: null, permissions_verified_at: null, ip_restricted: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    })))),
  );
}
