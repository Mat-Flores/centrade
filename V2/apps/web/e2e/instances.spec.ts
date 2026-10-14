import { expect, test, type Page } from "@playwright/test";

import { emptyWorld, expectNoViolation, mockAuth, mockCockpit, mockStream, storeTheme, watchConsole, wireCommand, wireInstance, type Spec, type World } from "./support";

const DAY = 86_400;
const live: Spec = { id: "i-live", name: "btc-live", mode: "live", strategy: { name: "momentum", version: 3 }, account: { label: "Binance live", currency: "USDT" }, startedAgoS: 3 * DAY + 4 * 3600, balances: [{ currency: "USDT", free: "400.00", total: "1000.50" }], pnl: [{ currency: "USDT", amount: "120.25" }], trades: 12, positions: 2 };
const alpha: Spec = { id: "i-alpha", name: "alpha", startedAgoS: 7200, balances: [{ currency: "USDT", free: "100", total: "10250.50" }, { currency: "BTC", free: "0.1", total: "0.5" }], pnl: [{ currency: "USDT", amount: "-12.40" }, { currency: "BTC", amount: "0.001" }], trades: 7, positions: 1 };
const beta: Spec = { id: "i-beta", name: "beta", state: "exits_only", desired: "running", balances: [{ currency: "USDT", free: "1", total: "500" }], pnl: [{ currency: "USDT", amount: "3.10" }], trades: 2, positions: 0 };
const gamma: Spec = { id: "i-gamma", name: "gamma", age: null };
const delta: Spec = { id: "i-delta", name: "delta", state: "stopped", desired: "stopped", balances: [{ currency: "USDT", free: "50", total: "50" }], pnl: [], trades: 0, positions: 0 };

const world = (over: Partial<World> = {}): World => ({ ...emptyWorld(), instances: [live, alpha, beta, gamma, delta], ...over });
const row = (page: Page, name: string) => page.locator(`[data-instance="${name}"]`);

async function open(page: Page, w: World, opts: { theme?: "light" | "dark"; mute?: boolean } = {}) {
  await storeTheme(page, opts.theme ?? "light");
  await mockAuth(page, { authenticated: true });
  const emit = await mockStream(page, { mute: opts.mute });
  await mockCockpit(page, w);
  await page.goto("/instances");
  return emit;
}

test("lists Live and Dry-run apart, with observed and dated values", async ({ page }) => {
  const errors = watchConsole(page);
  await open(page, world());
  await expect(page.getByRole("heading", { level: 1, name: "Instances" })).toBeVisible();

  const liveTable = page.getByRole("table", { name: "Instances, Live" });
  const paperTable = page.getByRole("table", { name: "Instances, Dry-run" });
  await expect(liveTable.getByRole("row")).toHaveCount(3); // header, one instance, totals
  await expect(paperTable.locator("[data-instance]")).toHaveCount(4);

  const a = row(page, "alpha");
  await expect(a).toContainText("freqtrade · momentum v3");
  await expect(a).toContainText("en marche");
  await expect(a).toContainText("10 250,50 USDT");
  await expect(a).toContainText("0,5 BTC"); // one line per currency
  await expect(a).toContainText("−12,40 USDT".replace("−", "-"));
  await expect(a).toContainText("+0,001 BTC");
  await expect(a).toContainText("7 +1");
  await expect(a).toContainText("2 h");
  await expect(row(page, "btc-live")).toContainText("3 j 4 h");

  // Unrealized has no source: a dash with its reason, never a zero.
  await expect(a.locator('[data-tip="pas encore relevé"]')).toHaveText("—");
  // Backtest is announced and nothing else.
  const backtest = page.getByRole("region", { name: "Backtest" });
  await expect(backtest).toContainText("Pas encore disponible");
  await expect(backtest.getByRole("table")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("an unknown value says 'inconnu' and a stale one says 'périmé', never a zero", async ({ page }) => {
  const stale: Spec = { id: "i-stale", name: "old", age: 120, dataAge: 120, balances: [{ currency: "USDT", free: "1", total: "77.70" }], pnl: [{ currency: "USDT", amount: "5.00" }], trades: 4, positions: 0 };
  await open(page, world({ instances: [gamma, stale] }));
  const g = row(page, "gamma");
  await expect(g).toContainText("inconnu");
  expect(await g.getByText("inconnu").count()).toBeGreaterThanOrEqual(4); // state, balance, realized, trades
  await expect(g).not.toContainText("0,00");
  await expect(g).not.toContainText(/\b0\b/);
  const s = row(page, "old");
  await expect(s).toContainText("en marche (périmé)");
  await expect(s).toContainText("77,70 USDT (périmé)");
  await expect(s).toContainText("+5,00 USDT (périmé)");
  await expect(s.getByText("4")).toContainText("périmé");
});

test("footer totals are per currency and per mode", async ({ page }) => {
  await open(page, world());
  const paper = page.getByRole("table", { name: "Instances, Dry-run" });
  const foot = paper.getByRole("row").last();
  await expect(foot).toContainText("Total, ce mode seulement");
  await expect(foot).toContainText("10 800,50 USDT"); // 10250.50 + 500 + 50, delta and beta included
  await expect(foot).toContainText("0,5 BTC");
  await expect(foot).toContainText("partiel : 1 inconnu"); // gamma left out, said so
  await expect(foot).not.toContainText("1 000"); // the live balance never leaks in
  const liveFoot = page.getByRole("table", { name: "Instances, Live" }).getByRole("row").last();
  await expect(liveFoot).toContainText("1 000,50 USDT");
});

test("a mode mismatch is loud and the instance leaves the totals", async ({ page }) => {
  const odd: Spec = { id: "i-odd", name: "odd", mismatch: true, observedMode: "live", balances: [{ currency: "USDT", free: "1", total: "999" }], pnl: [], trades: 0, positions: 0 };
  await open(page, world({ instances: [odd, alpha] }));
  await expect(row(page, "odd")).toContainText("MODE INCOHÉRENT");
  await expect(row(page, "odd")).toHaveClass(/warn-row/);
  await expect(page.getByRole("table", { name: "Instances, Dry-run" }).getByRole("row").last()).toContainText("1 exclue : mode incohérent");
});

test("pause stays 'demandé' until the effect is observed", async ({ page }) => {
  const w = world({ instances: [alpha] });
  const emit = await open(page, w);
  const a = row(page, "alpha");
  await a.getByRole("button", { name: "Pause achats" }).click();
  await expect(a).toContainText("demandé");
  expect(w.posts).toHaveLength(1);
  expect(w.posts[0]).toMatchObject({ path: "/instances/i-alpha/pause-entries" });
  expect(w.posts[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
  // Accepted is not done: the observed state is unchanged and no 'fait' appears.
  await expect(a).toContainText("en marche");
  await expect(a).not.toContainText("fait");
  await expect(a.getByRole("button", { name: "Pause achats" })).toHaveAttribute("aria-disabled", "true");

  await emit("command", { command: wireCommand({ id: "c-1", instance_id: "i-alpha", status: "acknowledged", agoS: 2 }) });
  await expect(a).toContainText("demandé");
  await expect(a).not.toContainText("fait");

  await emit("command", { command: wireCommand({ id: "c-1", instance_id: "i-alpha", status: "verified", agoS: 3 }) });
  await emit("instance", { instance: wireInstance({ ...alpha, state: "exits_only", desired: "exits_only" }) });
  await expect(a).toContainText("fait");
  await expect(a).toContainText("sorties seules");
  await expect(a.getByRole("button", { name: "Reprendre" })).toBeVisible();
});

test("a failed and a timed-out command stay visible until seen", async ({ page }) => {
  const w = world({
    instances: [alpha, beta],
    commands: [
      { id: "c-f", instance_id: "i-alpha", status: "failed", agoS: 200, reason: "engine refused the request" },
      { id: "c-t", instance_id: "i-beta", status: "timed_out", agoS: 400 },
    ],
  });
  await open(page, w);
  const a = row(page, "alpha");
  await expect(a).toContainText("échec");
  await expect(a).toContainText("Commande à vérifier");
  await expect(a).toContainText("engine refused the request");
  await expect(a).toHaveClass(/warn-row/);
  await expect(row(page, "beta")).toContainText("expirée");
  await expect(page.locator(".notice.loss")).toContainText("alpha");
  // Failed rows come first.
  const names = await page.getByRole("table", { name: "Instances, Dry-run" }).locator("[data-instance]").evaluateAll((els) => els.map((e) => e.getAttribute("data-instance")));
  expect(names.slice(0, 2).sort()).toEqual(["alpha", "beta"]);

  await a.getByRole("button", { name: "Marquer comme vu" }).click();
  await expect(a).not.toContainText("échec");
  await page.reload();
  await expect(row(page, "alpha")).not.toContainText("échec"); // remembered by this browser
  await expect(row(page, "beta")).toContainText("expirée");
});

test("flatten and stop ask for a confirmation that announces the consequences, and send one command", async ({ page }) => {
  const w = world({ instances: [alpha] });
  await open(page, w);
  const a = row(page, "alpha");

  await a.getByRole("button", { name: "Autres actions : alpha" }).click();
  await page.getByRole("menuitem", { name: /Tout vendre/ }).click();
  const dialog = page.getByRole("dialog", { name: "Tout vendre : alpha" });
  await expect(dialog).toContainText("Toutes les positions de l'instance seront fermées");
  await expect(dialog).toContainText("État observé à cet instant : en marche");
  await dialog.getByRole("button", { name: "Annuler" }).click();
  expect(w.posts).toHaveLength(0); // cancelling sends nothing

  await a.getByRole("button", { name: "Autres actions : alpha" }).click();
  await page.getByRole("menuitem", { name: /Arrêter/ }).click();
  await page.getByRole("dialog", { name: "Arrêter : alpha" }).getByRole("button", { name: "Arrêter" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(w.posts.map((p) => p.path)).toEqual(["/instances/i-alpha/stop"]);
  await expect(a).toContainText("demandé");
});

test("start and resume follow the observed state; resume is confirmed and refused when stale", async ({ page }) => {
  const staleExits: Spec = { id: "i-s", name: "slow", state: "exits_only", age: 120 };
  const w = world({ instances: [delta, beta, staleExits] });
  await open(page, w);
  await row(page, "delta").getByRole("button", { name: "Démarrer" }).click();
  await expect(row(page, "delta")).toContainText("demandé");
  expect(w.posts[0]?.path).toBe("/instances/i-delta/start");

  await row(page, "beta").getByRole("button", { name: "Reprendre" }).click();
  await expect(page.getByRole("dialog", { name: "Reprendre : beta" })).toContainText("Augmente le risque");
  await page.getByRole("button", { name: "Annuler" }).click();
  expect(w.posts).toHaveLength(1);

  const slow = row(page, "slow").getByRole("button", { name: "Reprendre" });
  await expect(slow).toHaveAttribute("aria-disabled", "true");
  await slow.click({ force: true }); // aria-disabled: Playwright would wait forever
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(w.posts).toHaveLength(1);
});

test("an engine refusal of a command is shown on the row", async ({ page }) => {
  await open(page, world({ instances: [alpha] }));
  await page.route(/\/instances\/i-alpha\/pause-entries$/, (route) => route.fulfill({ status: 409, contentType: "application/problem+json", body: JSON.stringify({ title: "Conflict", detail: "A command is already running." }) }));
  await row(page, "alpha").getByRole("button", { name: "Pause achats" }).click();
  await expect(row(page, "alpha").getByRole("alert")).toContainText("A command is already running.");
  await expect(row(page, "alpha")).not.toContainText("demandé");
});

test("a stream message updates the row without reloading the list", async ({ page }) => {
  const w = world({ instances: [alpha] });
  const emit = await open(page, w);
  await expect(row(page, "alpha")).toContainText("en marche");
  await emit("instance", { instance: wireInstance({ ...alpha, state: "error", trades: 9 }) });
  await expect(row(page, "alpha")).toContainText("erreur");
  await expect(row(page, "alpha")).toHaveClass(/warn-row/);
  await expect(row(page, "alpha").getByRole("button", { name: "Ouvrir" })).toBeVisible();
});

test("the list filters by name and says when nothing matches", async ({ page }) => {
  const many = Array.from({ length: 8 }, (_, n): Spec => ({ id: `i-${n}`, name: n === 3 ? "needle" : `bot-${n}`, age: 2 }));
  await open(page, world({ instances: many }));
  const filter = page.getByRole("searchbox", { name: "Filtrer les instances par nom" });
  await filter.fill("NEED");
  await expect(page.locator("[data-instance]")).toHaveCount(1);
  await filter.fill("zzz");
  await expect(page.getByText("Aucune instance ne correspond").first()).toBeVisible();
  await expect(page.getByText("Aucun nom de ce mode ne contient « zzz »").first()).toBeVisible();
});

test("empty lists say what to do", async ({ page }) => {
  await open(page, world({ instances: [] }));
  await expect(page.getByText("Aucune instance live")).toBeVisible();
  await expect(page.getByText("Aucune instance dry-run")).toBeVisible();
  await page.getByRole("region", { name: "Dry-run" }).getByRole("button", { name: "Nouvelle instance" }).click();
  await expect(page.getByRole("dialog", { name: "Nouvelle instance" })).toBeVisible();
});

test("an API error shows a retry that works", async ({ page }) => {
  const w = world({ instancesStatus: 500 });
  await open(page, w);
  await expect(page.getByText("Instances indisponibles")).toBeVisible();
  w.instancesStatus = 200;
  await page.getByRole("button", { name: "Réessayer" }).click();
  await expect(row(page, "alpha")).toBeVisible();
});

test("the connection pill counts fresh bots and warns when the stream is silent", async ({ page }) => {
  await open(page, world({ instances: [alpha, beta] }));
  const pill = page.locator("a.conn");
  await expect(pill).toContainText("2/2 bots");
  await expect(pill).toHaveClass(/\bok\b/);
});

test("a silent stream is a warning: degraded notice, creation disabled", async ({ page }) => {
  await open(page, world({ instances: [alpha] }), { mute: true });
  await expect(page.locator("a.conn")).toContainText("dégradé", { timeout: 9000 });
  await expect(page.locator("a.conn")).toHaveClass(/warn/);
  await expect(page.getByRole("status").filter({ hasText: "Mode dégradé" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nouvelle instance" })).toHaveAttribute("aria-disabled", "true");
  // Reducing risk stays possible.
  await expect(row(page, "alpha").getByRole("button", { name: "Pause achats" })).not.toHaveAttribute("aria-disabled", "true");
});

test("the pill says 'Session ouverte' with a neutral dot until the instances are loaded", async ({ page }) => {
  await open(page, world({ instancesStatus: 500 }));
  const pill = page.locator("a.conn");
  await expect(pill).toContainText("Session ouverte");
  await expect(pill).not.toHaveClass(/\b(ok|warn)\b/);
});

/* ----------------------------------------------------------------- creation */

const schema = { type: "object", required: ["stake"], properties: { stake: { type: "number", title: "Stake", minimum: 1, maximum: 100, default: 10 }, timeframe: { enum: ["5m", "1h"], default: "5m" }, dry: { type: "boolean", default: true }, opts: { type: "object" } } };
const createWorld = () => world({
  instances: [alpha],
  strategies: [{ id: "s-1", name: "momentum" }],
  versions: { "s-1": [{ id: "ver-1", version: 1, status: "draft" }, { id: "ver-2", version: 2, status: "approved", params_schema: schema }, { id: "ver-3", version: 3, status: "retired" }] },
  accounts: [{ id: "acc-p", label: "Paper USDT", currency: "USDT" }, { id: "acc-l", label: "Real", currency: "USDT", type: "live" }],
});

test("creation: strategy, approved version, account, generated parameters, then the new instance opens", async ({ page }) => {
  const w = createWorld();
  await open(page, w);
  await page.getByRole("button", { name: "Nouvelle instance" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Nouvelle instance" });

  await dialog.getByLabel("Nom").fill("my-bot");
  await dialog.getByLabel(/Stratégie/).selectOption({ label: "momentum" });
  const versions = await dialog.getByLabel(/Version/).locator("option").allTextContents();
  expect(versions).toEqual(["Choisir une version", "v2"]); // draft and retired are never offered
  await dialog.getByLabel(/Version/).selectOption({ label: "v2" });
  const accounts = await dialog.getByLabel(/Compte paper/).locator("option").allTextContents();
  expect(accounts).toEqual(["Choisir un compte", "Paper USDT (USDT)"]); // a live account is never offered
  await dialog.getByLabel(/Compte paper/).selectOption({ label: "Paper USDT (USDT)" });

  // Generated fields with their defaults; an unsupported property is said, not silently dropped.
  await expect(dialog.getByLabel(/Stake/)).toHaveValue("10");
  await expect(dialog.getByLabel("timeframe")).toHaveValue("5m");
  await expect(dialog.getByLabel("dry")).toHaveValue("true");
  await expect(dialog).toContainText("opts");
  await dialog.getByLabel(/Stake/).fill("500");
  await dialog.getByRole("button", { name: "Créer l'instance" }).click();
  await expect(dialog.getByText("Doit être au plus 100.")).toBeVisible();
  expect(w.posts).toHaveLength(0);
  await dialog.getByLabel(/Stake/).fill("25,5");
  await dialog.getByRole("button", { name: "Créer l'instance" }).click();

  await expect(page).toHaveURL(/\/instances\/i-new$/);
  expect(w.posts).toHaveLength(1);
  expect(w.posts[0]?.body).toEqual({ name: "my-bot", params: { stake: 25.5, timeframe: "5m", dry: true }, strategy_version_id: "ver-2", account_id: "acc-p", mode: "paper" });
  expect(w.posts[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
});

test("creation: invalid fields are refused locally, the server's 422 reasons are listed", async ({ page }) => {
  const w = createWorld();
  w.deployError = { status: 422, body: { type: "about:blank", title: "Unprocessable", status: 422, detail: ["stake above the account cap", "unknown timeframe"] } };
  await open(page, w);
  await page.getByRole("button", { name: "Nouvelle instance" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Nouvelle instance" });
  await dialog.getByLabel("Nom").fill("-bad name");
  await dialog.getByRole("button", { name: "Créer l'instance" }).click();
  await expect(dialog.getByText("Nom invalide")).toBeVisible();
  await expect(dialog.getByText("Choisir une stratégie.")).toBeVisible();
  await expect(dialog.getByText("Choisir un compte paper.")).toBeVisible();
  expect(w.posts).toHaveLength(0);

  await dialog.getByLabel("Nom").fill("ok-name");
  await dialog.getByLabel(/Stratégie/).selectOption({ label: "momentum" });
  await dialog.getByLabel(/Version/).selectOption({ label: "v2" });
  await dialog.getByLabel(/Compte paper/).selectOption({ label: "Paper USDT (USDT)" });
  await dialog.getByRole("button", { name: "Créer l'instance" }).click();
  const alert = dialog.getByRole("alert").filter({ hasText: "Instance non créée" });
  await expect(alert).toContainText("stake above the account cap");
  await expect(alert.getByRole("listitem")).toHaveText(["stake above the account cap", "unknown timeframe"]);
  await expect(page).toHaveURL(/\/instances$/);
  await expectNoViolation(page);
});

test("creation: a name conflict is said plainly", async ({ page }) => {
  const w = createWorld();
  w.deployError = { status: 409, body: { type: "about:blank", title: "Conflict", status: 409, detail: "name taken" } };
  await open(page, w);
  await page.getByRole("button", { name: "Nouvelle instance" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Nouvelle instance" });
  await dialog.getByLabel("Nom").fill("alpha");
  await dialog.getByLabel(/Stratégie/).selectOption({ label: "momentum" });
  await dialog.getByLabel(/Version/).selectOption({ label: "v2" });
  await dialog.getByLabel(/Compte paper/).selectOption({ label: "Paper USDT (USDT)" });
  await dialog.getByRole("button", { name: "Créer l'instance" }).click();
  await expect(dialog).toContainText("Une instance porte déjà ce nom.");
});

/* ---------------------------------------------------------------- a11y, layout */

for (const theme of ["light", "dark"] as const) {
  test(`no accessibility violation, ${theme} theme, with every kind of row`, async ({ page }) => {
    const errors = watchConsole(page);
    const stale: Spec = { id: "i-stale", name: "old", age: 120, dataAge: 120, balances: [{ currency: "USDT", free: "1", total: "77.70" }], pnl: [{ currency: "USDT", amount: "5.00" }], trades: 4, positions: 0 };
    const w = world({ instances: [live, alpha, beta, gamma, delta, stale], commands: [{ id: "c-f", instance_id: "i-alpha", status: "failed", reason: "refused" }] });
    await open(page, w, { theme });
    await expect(row(page, "alpha")).toBeVisible();
    await expectNoViolation(page);
    await page.getByRole("button", { name: "Nouvelle instance" }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished))); // axe reads settled colors
    await expectNoViolation(page);
    expect(errors).toEqual([]);
  });
}

test("no horizontal scroll at 1280 and 880 px", async ({ page }) => {
  await open(page, world());
  for (const width of [1280, 880]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(row(page, "alpha")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  }
});
