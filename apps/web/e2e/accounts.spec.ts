import path from "node:path";
import { expect, test, type Page, type Route } from "@playwright/test";

import { mockCockpit, T0, type Json } from "./cockpit-support";
import { expectNoViolation } from "./support";

const CAPTURES = path.resolve(import.meta.dirname, "../../../docs/captures/m2");
const SENTINEL = "TEST-SECRET-DO-NOT-USE";
const iso = (ms: number) => new Date(ms).toISOString();

const key = (usage: string, over: Json = {}): Json => ({
  usage,
  key_version: 1,
  stored_at: iso(T0 - 86_400_000),
  rotated_at: null,
  last_used_at: null,
  ...over,
});
const account = (over: Json & { id: string; label: string }): Json => ({
  venue: "binance",
  type: "live",
  environment: "production",
  currency: "USDT",
  capital_cap: "1500.50",
  trade_key: null,
  read_key: null,
  permissions_verified_at: null,
  ip_restricted: null,
  created_at: iso(T0 - 5 * 86_400_000),
  updated_at: iso(T0 - 86_400_000),
  ...over,
});
const world = (): Json[] => [
  account({ id: "a-live", label: "Principal", trade_key: key("trade", { rotated_at: iso(T0 - 3_600_000), last_used_at: iso(T0 - 120_000) }), read_key: key("read"), permissions_verified_at: iso(T0 - 600_000), ip_restricted: true }),
  account({ id: "a-new", label: "Réserve", environment: "sandbox", capital_cap: "250", trade_key: key("trade") }),
  account({ id: "a-bare", label: "Sans clé", environment: "sandbox", capital_cap: null }),
  account({ id: "a-paper", label: "Bac paper", type: "paper", environment: "sandbox", capital_cap: "10000", venue: "paper" }),
];

interface Mock {
  accounts: Json[];
  requests: { method: string; path: string; body: string | null }[];
  status: Record<string, { status: number; detail: string }>; // par "METHOD /suffixe"
  listStatus: number;
  delayMs: number;
}

async function mockAccounts(page: Page, role: "admin" | "viewer" = "admin", data?: Json[]): Promise<Mock> {
  const state: Mock = { accounts: data ?? world(), requests: [], status: {}, listStatus: 200, delayMs: 0 };
  await mockCockpit(page, { role, now: () => T0 });
  const reply = (route: Route, status: number, body: unknown, ct = "application/json") => route.fulfill({ status, contentType: ct, body: JSON.stringify(body) });
  await page.route(/\/api\/v1\/accounts/, async (route) => {
    const req = route.request();
    const p = new URL(req.url()).pathname.replace("/api/v1", "");
    const suffix = p.replace(/^\/accounts\/?[^/]*/, "");
    state.requests.push({ method: req.method(), path: p, body: req.postData() });
    const forced = state.status[`${req.method()} ${suffix || "/"}`];
    if (forced) return reply(route, forced.status, { type: "about:blank", title: "x", status: forced.status, detail: forced.detail }, "application/problem+json");
    const id = p.split("/")[2];
    const target = state.accounts.find((a) => a.id === id);
    if (req.method() === "GET") {
      if (state.delayMs) await new Promise((r) => setTimeout(r, state.delayMs));
      if (state.listStatus !== 200) return reply(route, state.listStatus, { title: "Error", status: state.listStatus }, "application/problem+json");
      return reply(route, 200, { items: state.accounts, next_cursor: null, server_time: iso(T0) });
    }
    if (p === "/accounts") {
      const body = JSON.parse(req.postData() ?? "{}") as Json;
      const created = account({ capital_cap: null, ...body, id: "a-created", label: String(body.label) });
      state.accounts.unshift(created);
      return reply(route, 201, created);
    }
    if (suffix === "/secret" || suffix === "/rotate") {
      const body = JSON.parse(req.postData() ?? "{}") as { usage: string };
      const k = key(body.usage, { stored_at: iso(T0) });
      if (target) target[body.usage === "trade" ? "trade_key" : "read_key"] = k;
      return reply(route, 200, k);
    }
    if (suffix === "/test") return reply(route, 200, { result: "unverified", account: target });
    return route.fallback();
  });
  return state;
}

const row = (page: Page, label: string) => page.locator(`tr[data-account="${label}"]`);

test("navigation : liens au clavier entre écrans, URL partageables, bouton retour, titre et focus", async ({ page }) => {
  await mockAccounts(page);
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Écrans" });
  await expect(nav.getByRole("link", { name: "Cockpit" })).toHaveAttribute("aria-current", "page");

  await nav.getByRole("link", { name: "Comptes et clés" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/accounts$/);
  await expect(page.getByRole("heading", { level: 1, name: "Comptes et clés" })).toBeVisible();
  await expect(page).toHaveTitle("Comptes et clés · Centrade");
  await expect(page.locator("main")).toBeFocused();
  await expect(nav.getByRole("link", { name: "Comptes et clés" })).toHaveAttribute("aria-current", "page");

  for (const [name, url] of [["Stratégies", /\/strategies$/], ["Ordres et positions", /\/orders$/]] as const) {
    await nav.getByRole("link", { name }).focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(url);
    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
    await expect(page.getByText("Pas encore disponible")).toBeVisible();
  }

  await page.goBack();
  await page.goBack();
  await expect(page).toHaveURL(/\/accounts$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1, name: "Cockpit" })).toBeVisible();

  // Une adresse partagée s'ouvre directement ; une adresse inconnue le dit.
  await page.goto("/accounts");
  await expect(page.getByRole("heading", { level: 1, name: "Comptes et clés" })).toBeVisible();
  await page.goto("/nulle-part");
  await expect(page.getByRole("heading", { level: 1, name: "Page introuvable" })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Aller au contenu" })).toBeFocused(); // lien d'évitement
});

test("liste : clés, dates à Toronto, permissions, IP ; compte paper sans dépôt avec sa raison ; données absentes dites absentes", async ({ page }) => {
  await mockAccounts(page);
  await page.goto("/accounts");

  const main = row(page, "Principal");
  await expect(main.getByText("LIVE", { exact: true })).toBeVisible();
  await expect(main.getByText("Production")).toBeVisible();
  await expect(main.getByText("1 500,50 USDT")).toBeVisible(); // fr-CA, devise affichée, aucun arrondi
  await expect(main.getByText("Présente").first()).toBeVisible();
  await expect(main.getByText(/HNE|HAE/).first()).toBeVisible(); // fuseau indiqué
  await expect(main.getByText(/Vérifiées/)).toBeVisible();
  await expect(main.getByText("oui", { exact: true })).toBeVisible();
  await expect(row(page, "Réserve").getByText("Absente")).toBeVisible(); // clé de lecture

  await expect(row(page, "Réserve").getByText("Non vérifiées")).toBeVisible();
  await expect(row(page, "Réserve").getByText("inconnue")).toBeVisible();
  await expect(row(page, "Sans clé").getByText("non défini")).toBeVisible();

  const paper = row(page, "Bac paper");
  await expect(paper.getByText(/une instance paper ne reçoit jamais de clé/)).toBeVisible();
  await expect(paper.getByRole("button")).toHaveCount(0);
  await expect(paper.getByText("simulé")).toBeVisible();

  await expect(page.getByText("Matrice instance ↔ compte")).toBeVisible();
  await expect(page.getByText(/Non disponible : l'API n'expose pas encore/)).toBeVisible();
  await expect(page.getByText(/aucun relevé de solde n'est branché/)).toBeVisible();
  await expectNoViolation(page);
});

test("création : plafond envoyé en chaîne décimale telle quelle, champs invalides signalés", async ({ page }) => {
  const api = await mockAccounts(page);
  await page.goto("/accounts");
  await page.getByRole("button", { name: "Créer un compte" }).click();
  await page.getByLabel("Libellé").fill("Nouveau");
  await page.getByLabel("Venue").fill("Binance!");
  await page.getByLabel("Devise", { exact: true }).fill("u");
  await page.getByLabel("Plafond de capital").fill("0");
  await page.getByRole("button", { name: "Créer le compte" }).click();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("venue");
  await expect(alert).toContainText("devise");
  await expect(alert).toContainText("plafond");
  expect(api.requests.some((r) => r.method === "POST")).toBe(false);

  await page.getByLabel("Venue").fill("binance");
  await page.getByLabel("Devise", { exact: true }).fill("usdt");
  await page.getByLabel("Plafond de capital").fill("1500.50");
  await page.getByLabel("Type").selectOption("live");
  await page.getByRole("button", { name: "Créer le compte" }).click();
  await expect(page.getByText(/Compte « Nouveau » créé/)).toBeVisible();
  const post = api.requests.find((r) => r.method === "POST" && r.path === "/accounts");
  expect(post?.body).toContain('"capital_cap":"1500.50"'); // chaîne, zéro final conservé
  expect(JSON.parse(post!.body!)).toMatchObject({ label: "Nouveau", venue: "binance", currency: "USDT", type: "live", environment: "sandbox" });
  await expect(row(page, "Nouveau")).toBeVisible();
});

test("dépôt d'une clé : confirmation par le libellé, valeur envoyée une fois puis introuvable partout", async ({ page }) => {
  const logs: string[] = [];
  page.on("console", (m) => logs.push(m.text()));
  const api = await mockAccounts(page);
  await page.goto("/accounts");

  await row(page, "Sans clé").getByRole("button", { name: /Déposer : Clé de trading/ }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible();
  const keyField = dialog.getByLabel("Clé d'API");
  await expect(keyField).toHaveAttribute("type", "password");
  await expect(keyField).toHaveAttribute("autocomplete", "off");
  await expect(keyField).toHaveValue(""); // jamais pré-rempli
  await keyField.fill(SENTINEL);
  await dialog.getByLabel("Secret", { exact: true }).fill(SENTINEL);

  const submit = dialog.getByRole("button", { name: "Envoyer la clé" });
  await expect(submit).toBeDisabled(); // libellé non saisi
  await dialog.getByLabel("Libellé du compte").fill("sans clef");
  await expect(submit).toBeDisabled();
  await dialog.getByLabel("Libellé du compte").fill("Sans clé");
  await expect(submit).toBeEnabled();
  await submit.click();

  await expect(page.getByText(/Clé de trading enregistrée/)).toBeVisible();
  await expect(dialog).toHaveCount(0);
  await expect(row(page, "Sans clé").getByText("Présente")).toBeVisible();

  const put = api.requests.find((r) => r.method === "PUT");
  expect(put?.path).toBe("/accounts/a-bare/secret");
  expect(JSON.parse(put!.body!)).toEqual({ usage: "trade", key: SENTINEL, secret: SENTINEL });

  // Nulle part après l'envoi : ni DOM, ni valeurs de champs, ni stockage, ni URL, ni console.
  expect(await page.content()).not.toContain(SENTINEL);
  expect(await page.evaluate(() => [...document.querySelectorAll("input")].map((i) => i.value).join("|"))).not.toContain(SENTINEL);
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }))).not.toContain(SENTINEL);
  expect(page.url()).not.toContain(SENTINEL);
  expect(logs.join("\n")).not.toContain(SENTINEL);
});

test("échec d'un dépôt : cause et action, champs déjà vidés ; TOTP périmé expliqué", async ({ page }) => {
  const api = await mockAccounts(page);
  api.status["PUT /secret"] = { status: 403, detail: "Confirmation par code TOTP requise." };
  await page.goto("/accounts");
  await row(page, "Sans clé").getByRole("button", { name: /Déposer : Clé de trading/ }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByLabel("Clé d'API").fill(SENTINEL);
  await dialog.getByLabel("Secret", { exact: true }).fill(SENTINEL);
  await dialog.getByLabel("Libellé du compte").fill("Sans clé");
  await dialog.getByRole("button", { name: "Envoyer la clé" }).click();
  await expect(dialog.getByRole("alert")).toContainText("plus de cinq minutes");
  await expect(dialog.getByRole("alert")).toContainText("Se déconnecter puis se reconnecter");
  await expect(dialog.getByLabel("Clé d'API")).toHaveValue("");
  await expect(dialog.getByLabel("Secret", { exact: true })).toHaveValue("");
  expect(await page.content()).not.toContain(SENTINEL);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("rotation refusée (409) : la cause du serveur est affichée", async ({ page }) => {
  const api = await mockAccounts(page);
  api.status["POST /rotate"] = { status: 409, detail: "Nouvelle clé non vérifiée : l'ancienne reste en place." };
  await page.goto("/accounts");
  await row(page, "Principal").getByRole("button", { name: /Rotation : Clé de trading/ }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByLabel("Clé d'API").fill(SENTINEL);
  await dialog.getByLabel("Secret", { exact: true }).fill(SENTINEL);
  await dialog.getByLabel("Libellé du compte").fill("Principal");
  await dialog.getByRole("button", { name: "Lancer la rotation" }).click();
  await expect(dialog.getByRole("alert")).toContainText("l'ancienne reste en place");
  expect(await page.content()).not.toContain(SENTINEL);
});

test("test des permissions : « non vérifié » n'est jamais présenté comme un succès", async ({ page }) => {
  const api = await mockAccounts(page);
  await page.goto("/accounts");
  await row(page, "Réserve").getByRole("button", { name: /Tester les permissions/ }).click();
  const status = page.getByRole("status").filter({ hasText: "Réserve" });
  await expect(status).toContainText("non vérifié");
  await expect(status).toContainText("le passage en live reste bloqué");
  await expect(status).not.toContainText("permissions vérifiées");
  await expect(row(page, "Réserve").getByText("Non vérifiées")).toBeVisible();
  expect(api.requests.some((r) => r.method === "POST" && r.path === "/accounts/a-new/test")).toBe(true);
});

test("rôle lecteur : tout est lisible, aucune écriture possible", async ({ page }) => {
  await mockAccounts(page, "viewer");
  await page.goto("/accounts");
  await expect(page.getByText(/Lecture seule/)).toBeVisible();
  await expect(row(page, "Principal")).toBeVisible();
  await expect(page.getByRole("button", { name: "Créer un compte" })).toBeDisabled();
  for (const b of await row(page, "Principal").getByRole("button").all()) await expect(b).toBeDisabled();
  for (const b of await row(page, "Sans clé").getByRole("button").all()) await expect(b).toBeDisabled();
  await expectNoViolation(page);
});

test("états : squelette, erreur avec reprise, vide", async ({ page }) => {
  const api = await mockAccounts(page, "admin", []);
  api.delayMs = 600;
  api.listStatus = 500;
  await page.goto("/accounts");
  await expect(page.getByRole("status", { name: "Chargement des comptes…" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Comptes indisponibles");
  api.listStatus = 200;
  api.delayMs = 0;
  await page.getByRole("button", { name: "Réessayer" }).click();
  await expect(page.getByText("Aucun compte", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Créer un compte" })).toBeEnabled();
});

const viewports = { bureau: { width: 1280, height: 800 }, tablette: { width: 820, height: 1180 } };
for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of Object.entries(viewports)) {
    test(`comptes ${scheme} ${name} : cibles de 44 px, pas de défilement de page, axe, capture`, async ({ page }) => {
      await page.clock.setFixedTime(new Date(T0));
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await page.setViewportSize(viewport);
      await mockAccounts(page);
      await page.goto("/accounts");
      await expect(row(page, "Principal")).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      for (const b of await page.locator("main").getByRole("button").all()) {
        expect((await b.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expectNoViolation(page);
      if (process.env.CAPTURES === "1") {
        await page.screenshot({ path: path.join(CAPTURES, `comptes-${scheme === "light" ? "clair" : "sombre"}-${name}.png`), fullPage: true });
      }
      await row(page, "Sans clé").getByRole("button", { name: /Déposer : Clé de trading/ }).click();
      await expect(page.getByRole("alertdialog")).toBeVisible();
      await expectNoViolation(page);
    });
  }
}
