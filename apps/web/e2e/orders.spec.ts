import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

import { command, emit, sseEvent, stopBeats, T0, world } from "./cockpit-support";
import { expectNoViolation } from "./support";
import { ID, mockTrading } from "./trading-support";

const CAPTURES = path.resolve(import.meta.dirname, "../../../docs/captures/m2");
const iso = (ms: number) => new Date(ms).toISOString();
const posRow = (page: Page, instrument: string, instance?: string) => {
  const rows = page.locator(`tr[data-position="${instrument}"]`);
  return instance ? rows.filter({ hasText: instance }) : rows;
};

test("positions : non protégées en tête, stop et protection datés, périmé estompé, inconnu dit inconnu", async ({ page }) => {
  const noise: string[] = [];
  page.on("console", (m) => (m.type() === "error" || m.text().includes("Content Security Policy")) && noise.push(m.text()));
  await page.setViewportSize({ width: 1280, height: 1600 });
  await mockTrading(page);
  await page.goto("/orders");
  await expect(page.getByRole("heading", { level: 1, name: "Ordres et positions" })).toBeVisible();
  await expect(page.locator("figure[data-breakdown]").first()).toBeVisible();
  expect(noise).toEqual([]); // la CSP stricte accepte les barres de la répartition

  const order = await page.locator("tr[data-position]").evaluateAll((rows) => rows.map((r) => (r as HTMLElement).dataset.protection));
  expect(order).toEqual(["unprotected", "unknown", "engine_only", "protected", "protected"]); // les moins protégées d'abord
  await expect(page.getByText("1 position(s) non protégée(s)")).toBeVisible();

  const eth = posRow(page, "ETH/USDT");
  await expect(eth.getByText("NON PROTÉGÉE")).toBeVisible();
  await expect(eth.getByText("aucun stop", { exact: true })).toBeVisible();

  const btc = posRow(page, "BTC/USDT", "alpha");
  await expect(btc.getByText("57 000,25")).toBeVisible(); // fr-CA, aucune décimale perdue
  await expect(btc.getByText("60 000,50 USDT")).toBeVisible();
  await expect(btc.getByText("+5,0001 % du prix d'entrée")).toBeVisible();
  await expect(btc.getByText("sur la venue, fixe")).toBeVisible();
  await expect(btc.getByText("simulé").first()).toBeVisible();
  await expect(btc.getByText("Protégée")).toBeVisible();
  await expect(btc.getByText(/vérifiée/)).toBeVisible();
  await expect(btc.getByText(/HNE|HAE/).first()).toBeVisible(); // fuseau indiqué

  const sol = posRow(page, "SOL/USDT");
  await expect(sol.locator('[data-state="stale"]').first()).toBeVisible();
  await expect(sol.getByText(/périmé depuis/).first()).toBeVisible();
  await expect(sol.getByText("Moteur seul", { exact: true })).toBeVisible();

  const ada = posRow(page, "ADA/USDT");
  await expect(ada.locator('[data-state="unknown"]').first()).toBeVisible();
  await expect(ada.getByText("inconnu").first()).toBeVisible();
  await expect(ada.getByText("jamais vérifiée")).toBeVisible();

  // L'âge est donné au survol.
  await btc.locator('[data-state="fresh"]').first().hover();
  await expect(page.getByRole("tooltip")).toContainText("Observé il y a");
});

test("jamais de mélange : paper « simulé », live à part, totaux par mode et par devise", async ({ page }) => {
  await mockTrading(page);
  await page.goto("/orders");
  const totals = page.locator("[data-total]");
  await expect(totals).toHaveCount(3); // live/EUR, paper/EUR, paper/USDT : trois totaux, jamais fusionnés
  await expect(page.locator('[data-total="paper|USDT"]')).toContainText("+17,65 USDT"); // -12,50 - 0,10 + 30,25
  await expect(page.locator('[data-total="paper|USDT"]')).toContainText("simulé");
  await expect(page.locator('[data-total="live|EUR"]')).toContainText("+5,5 EUR");
  await expect(page.locator('[data-total="live|EUR"]')).not.toContainText("simulé");
  await expect(page.locator('[data-total="paper|EUR"]')).toContainText(/[-−]3\sEUR/);
  // Le tableau des positions porte le mode de chaque ligne.
  await expect(posRow(page, "BTC/EUR").getByText("LIVE", { exact: true })).toBeVisible();
  await expect(posRow(page, "BTC/EUR").getByText("simulé")).toHaveCount(0);
});

test("trades : cause de sortie par trade, répartition par instance, PnL signé avec devise", async ({ page }) => {
  await mockTrading(page);
  await page.goto("/orders");
  await expect(page.locator('tr[data-exit-cause="take_profit"]').getByText("Objectif de gain")).toBeVisible();
  await expect(page.locator('tr[data-exit-cause="take_profit"]')).toContainText("+30,25 USDT");
  await expect(page.locator('tr[data-trade]').filter({ hasText: "-12,50" }).first()).toContainText("USDT");
  const alpha = page.locator('figure[data-breakdown="alpha"]');
  await expect(alpha).toContainText("3 sortie(s)");
  await expect(alpha.locator('li[data-cause="stop_loss"]')).toContainText("2 · 67 %");
  await expect(alpha.locator('li[data-cause="take_profit"]')).toContainText("1 · 33 %");
});

test("ordres : annulation proposée pour l'entrée seulement ; sortie et stop disent pourquoi", async ({ page }) => {
  const { state } = await mockTrading(page);
  await page.goto("/orders");
  const entry = page.locator(`tr[data-order="co-${ID(31)}"]`);
  const exit = page.locator(`tr[data-order="co-${ID(32)}"]`);
  const stop = page.locator(`tr[data-order="co-${ID(33)}"]`);
  await expect(entry.getByRole("button", { name: /Annuler l'ordre d'entrée BTC\/USDT de alpha/ })).toBeVisible();
  for (const r of [exit, stop]) {
    await expect(r.getByRole("button")).toHaveCount(0);
    await expect(r.getByText("Non annulable")).toBeVisible();
  }
  await expect(page.getByText(/annuler une sortie ou un stop augmenterait le risque/)).toBeVisible();
  await expect(page.locator(`tr[data-order="co-${ID(34)}"]`).getByText("Plus ouvert")).toBeVisible();

  await entry.getByRole("button", { name: /Annuler l'ordre d'entrée/ }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("aucune nouvelle exposition");
  await dialog.getByRole("button", { name: "Annuler l'ordre" }).click();
  await expect(dialog).toHaveCount(0);
  const sent = state.requests.filter((r) => r.method === "DELETE");
  expect(sent).toHaveLength(1);
  expect(sent[0]!.key).toMatch(/^[0-9a-f-]{36}$/);
  // Pas d'optimisme : demandée n'est pas « faite ».
  const line = page.locator('li[data-command-type="cancel_entry_order"]');
  await expect(line).toContainText("demandée, pas encore transmise au moteur");
  await expect(line).not.toContainText("faite");
  await emit(page, "command", sseEvent(Date.now(), "command", command(Date.now(), { id: `cmd-cancel_entry_order-${ID(31)}`, instance_id: ID(1), type: "cancel_entry_order", status: "verified", verified_at: iso(Date.now()) })));
  await expect(line).toContainText("faite, effet observé dans le moteur");
});

test("fermeture possible en état inconnu et en mode dégradé ; conséquences d'après l'état observé ; échec visible jusqu'à « vu »", async ({ page }) => {
  const { state } = await mockTrading(page);
  await page.goto("/orders");
  await expect(posRow(page, "ADA/USDT")).toBeVisible();
  await stopBeats(page);
  await expect(page.getByRole("banner").getByText(/flux temps réel est coupé/)).toBeVisible({ timeout: 10_000 });
  const close = posRow(page, "ADA/USDT").getByRole("button", { name: /Fermer la position ADA\/USDT de charlie/ });
  await expect(close).toBeEnabled();
  await expect(close).not.toHaveAttribute("aria-disabled", "true");
  await close.click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("Protection non relevée");
  await expect(dialog).toContainText("État de l'instance inconnu");
  await expect(dialog).toContainText("reste possible quand l'état est inconnu ou périmé");
  await dialog.getByRole("button", { name: "Fermer la position" }).click();
  await expect(dialog).toHaveCount(0);
  const sent = state.requests.filter((r) => r.path.endsWith("/close"));
  expect(sent).toHaveLength(1);
  expect(sent[0]!.key).toBeTruthy();

  const line = page.locator('li[data-command-type="close_position"]');
  await expect(line).toContainText("demandée, pas encore transmise");
  await emit(page, "command", sseEvent(Date.now(), "command", command(Date.now(), { id: `cmd-close_position-${ID(24)}`, instance_id: ID(3), type: "close_position", status: "timed_out", timed_out_at: iso(Date.now()), result: { reason: "le moteur n'a pas confirmé" } })));
  await expect(line).toContainText("délai dépassé : effet non observé");
  await expect(line.getByRole("alert").or(line)).toBeVisible();
  await line.getByRole("button", { name: "Marquer comme vu" }).click();
  await expect(line).toBeVisible(); // reste dans l'historique, sans alerte
  await expect(line.getByRole("button", { name: "Marquer comme vu" })).toHaveCount(0);
});

test("la confirmation annonce l'état observé frais, périmé ou inconnu de la protection", async ({ page }) => {
  await mockTrading(page);
  await page.goto("/orders");
  await posRow(page, "BTC/USDT", "alpha").getByRole("button", { name: /Fermer/ }).click();
  await expect(page.getByRole("alertdialog")).toContainText("Protection observée à cet instant : Protégée");
  await page.keyboard.press("Escape");
  await posRow(page, "SOL/USDT").getByRole("button", { name: /Fermer/ }).click();
  await expect(page.getByRole("alertdialog")).toContainText("Protection observée périmée depuis");
  await expect(page.getByRole("alertdialog")).toContainText("État de l'instance périmé depuis");
});

test("filtre par instance au clavier : la requête porte l'identifiant, les lignes suivent", async ({ page }) => {
  const { state } = await mockTrading(page);
  await page.goto("/orders");
  await expect(posRow(page, "BTC/EUR")).toBeVisible();
  const select = page.getByLabel("Instance", { exact: true });
  await select.focus();
  await page.keyboard.press("ArrowDown"); // première instance de la liste
  await expect(select).not.toHaveValue("");
  await expect(posRow(page, "BTC/EUR")).toHaveCount(0);
  expect(state.requests.some((r) => r.method === "GET" && r.search.includes("instance_id="))).toBe(true);
  await expect(page.getByLabel("Compte", { exact: true })).toBeVisible();
});

test("rôle viewer : lecture seule, aucun bouton d'action", async ({ page }) => {
  await mockTrading(page, { role: "viewer" });
  await page.goto("/orders");
  await expect(page.getByText(/Lecture seule : fermer une position/)).toBeVisible();
  await expect(posRow(page, "ETH/USDT")).toBeVisible();
  await expect(page.getByRole("button", { name: /Fermer la position|Annuler l'ordre/ })).toHaveCount(0);
});

test("erreur de chargement : cause et action ; liste vide : message utile", async ({ page }) => {
  const { state } = await mockTrading(page);
  state.listStatus = 500;
  await page.goto("/orders");
  await expect(page.getByText("Données indisponibles").first()).toBeVisible();
  state.listStatus = 200;
  state.positions.length = 0;
  await page.getByRole("button", { name: "Réessayer" }).first().click();
  await expect(page.getByText("Aucune position ouverte.")).toBeVisible();
});

test("temps réel : un événement de position relit la liste", async ({ page }) => {
  const { state } = await mockTrading(page);
  await page.goto("/orders");
  await expect(posRow(page, "ADA/USDT")).toBeVisible();
  state.positions.pop(); // BTC/EUR disparaît côté serveur
  await emit(page, "position", { server_time: iso(Date.now()) });
  await expect(posRow(page, "BTC/EUR")).toHaveCount(0);
});

for (const scheme of ["light", "dark"] as const) {
  test(`axe sans violation (${scheme}) : écran, confirmation ouverte`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
    await mockTrading(page);
    await page.goto("/orders");
    await expect(posRow(page, "ETH/USDT")).toBeVisible();
    await expectNoViolation(page);
    await posRow(page, "ETH/USDT").getByRole("button", { name: /Fermer/ }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await expectNoViolation(page);
  });
}

const viewports = { bureau: { width: 1280, height: 800 }, tablette: { width: 820, height: 1180 } };
for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of Object.entries(viewports)) {
    test(`ordres ${scheme} ${name} : cibles de 44 px, pas de défilement horizontal de la page, capture`, async ({ page }) => {
      await page.clock.setFixedTime(new Date(T0));
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await page.setViewportSize(viewport);
      const w = world(T0);
      await mockTrading(page, { now: () => T0, data: { instances: w.instances, alerts: w.alerts } });
      await page.goto("/orders");
      await expect(posRow(page, "ETH/USDT")).toBeVisible();
      await expect(page.locator("[data-total]").first()).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      for (const b of await page.locator("main").getByRole("button").all()) {
        expect((await b.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expectNoViolation(page);
      if (process.env.CAPTURES === "1") {
        await page.screenshot({ path: path.join(CAPTURES, `ordres-${scheme === "light" ? "clair" : "sombre"}-${name}.png`), fullPage: true });
      }
    });
  }
}

test("regroupement par compte : un sous-titre par compte, les lignes sans compte à part", async ({ page }) => {
  await mockTrading(page);
  await page.goto("/orders");
  await expect(posRow(page, "BTC/USDT", "alpha")).toBeVisible();
  await expect(page.getByRole("heading", { level: 3, name: "Bac paper" })).toHaveCount(0);
  await page.getByLabel("Grouper par compte").check();
  await expect(page.getByRole("heading", { level: 3, name: "Bac paper" })).toHaveCount(3); // positions, ordres, trades
  await expect(page.getByRole("heading", { level: 3, name: "Sans compte" })).toHaveCount(2); // positions et trades live
  await expect(posRow(page, "BTC/USDT", "alpha")).toBeVisible();
});
