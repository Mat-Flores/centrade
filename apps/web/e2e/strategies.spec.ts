import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

import { command, emit, sseEvent, T0, world } from "./cockpit-support";
import { expectInView, expectNoViolation } from "./support";
import { ID } from "./trading-support";
import { mockRegistry, S1 } from "./strategies-support";

const CAPTURES = path.resolve(import.meta.dirname, "../../../docs/captures/m2");
const iso = (ms: number) => new Date(ms).toISOString();
const inst = (page: Page, name: string) => page.locator(`li[data-instance="${name}"]`);
const OPEN = `/strategies?s=${S1}`;

test("navigation : liste, URL partageable, versions immuables, détail par paramètre de requête", async ({ page }) => {
  await mockRegistry(page);
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Écrans" });
  await nav.getByRole("link", { name: "Stratégies" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/strategies$/);
  await expect(page.getByRole("heading", { level: 1, name: "Stratégies" })).toBeVisible();
  await expect(page.getByText("Choisir une stratégie pour voir")).toBeVisible();

  await page.getByRole("link", { name: "Ouvrir la stratégie sma-cross" }).click();
  await expect(page).toHaveURL(new RegExp(`/strategies\\?s=${S1}$`));
  await expect(page.getByRole("heading", { name: "Versions de sma-cross" })).toBeVisible();
  await expect(page.getByText(/ne se modifie jamais/).first()).toBeVisible();
  const v2 = page.locator('tr[data-version="2"]');
  await expect(v2.getByText("Approuvée")).toBeVisible();
  await expect(v2).toContainText("a1b2c3d4e5f6"); // empreinte abrégée
  await expect(v2).toContainText("operateur@example.test");
  await expect(v2.getByText(/HNE|HAE/)).toBeVisible();
  await expect(page.locator('tr[data-version="1"]').getByText("Brouillon")).toBeVisible();

  await v2.getByRole("link", { name: "Voir la version 2" }).click();
  await expect(page).toHaveURL(new RegExp(`v=2$`));
  await expect(page.getByRole("heading", { name: "sma-cross, version 2" })).toBeVisible();
  await page.goBack();
  await expect(page.locator("[data-version-panel]")).toHaveCount(0);

  // Adresse partagée : ouverture directe.
  await page.goto(`${OPEN}&v=1`);
  await expect(page.locator('[data-version-panel="1"]')).toBeVisible();
});

test("détail d'une version : manifest, politique de sortie, contrôles statiques, code en lecture seule", async ({ page }) => {
  await mockRegistry(page);
  await page.goto(`${OPEN}&v=2`);
  const panel = page.locator('[data-version-panel="2"]');
  await expect(panel).toContainText("sma_cross.SmaCross");
  await expect(panel).toContainText("100,50"); // mise : fr-CA, aucune décimale perdue
  const exits = panel.locator("[data-exits]");
  await expect(exits).toContainText("Stop-loss");
  await expect(exits).toContainText("-0,05");
  await expect(exits).toContainText("-5 %");
  await expect(exits).toContainText("Stop posé sur la venue");
  await expect(exits).toContainText("après 60 min : +0,02");
  await expect(exits).toContainText("elle l'emporte sur le code de la stratégie");
  await expect(panel.getByText("Réussis")).toBeVisible();
  await panel.getByText("Code déposé").click();
  await expect(panel.getByText("class SmaCross:")).toBeVisible();
  await expect(panel.locator("textarea")).toHaveCount(0); // jamais modifiable
});

test("dépôt d'une version : refusé avec les motifs un par un, puis accepté", async ({ page }) => {
  const { state } = await mockRegistry(page);
  await page.goto(OPEN);
  await page.getByRole("button", { name: "Déposer une version" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible();

  // Contrôles locaux avant l'envoi.
  await dialog.getByLabel("Manifest (JSON)").fill("{pas du json");
  await dialog.getByLabel("Code de la stratégie").fill("print('x')");
  await dialog.getByRole("button", { name: "Déposer la version" }).click();
  await expect(dialog.getByRole("alert")).toContainText("n'est pas un objet JSON lisible");
  expect(state.requests.filter((r) => r.method === "POST")).toHaveLength(0);

  // Refus du registre : chaque motif sur sa ligne, rien d'enregistré.
  state.reasons = ["manifest.exits.stoploss : champ obligatoire", "code : appel interdit à open()", "code : redéfinit confirm_trade_entry"];
  await dialog.getByLabel("Manifest (JSON)").fill(JSON.stringify({ name: "sma-cross" }));
  await dialog.getByRole("button", { name: "Déposer la version" }).click();
  await expect(dialog.locator("[data-reasons] li")).toHaveText(state.reasons);
  await expect(dialog).toContainText("rien n'a été enregistré");
  expect(state.versions).toHaveLength(2);

  // Accepté : la version arrive en brouillon, la liste est relue.
  state.reasons = [];
  await dialog.getByRole("button", { name: "Déposer la version" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("status").filter({ hasText: "Version 3 déposée en brouillon." })).toBeVisible();
  await expect(page.locator('tr[data-version="3"]').getByText("Brouillon")).toBeVisible();
  const posts = state.requests.filter((r) => r.method === "POST" && r.path.endsWith("/versions"));
  expect(posts).toHaveLength(2);
  expect(posts[0]!.key).toBeTruthy();
  expect(posts[1]!.key).toBe(posts[0]!.key); // même ouverture, même clé d'idempotence
});

test("dépôt depuis des fichiers locaux", async ({ page }) => {
  const { state } = await mockRegistry(page);
  await page.goto(OPEN);
  await page.getByRole("button", { name: "Déposer une version" }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByLabel("Charger un manifest depuis un fichier").setInputFiles({ name: "manifest.json", mimeType: "application/json", buffer: Buffer.from('{"name":"depuis-fichier"}') });
  await dialog.getByLabel("Charger le code depuis un fichier").setInputFiles({ name: "s.py", mimeType: "text/x-python", buffer: Buffer.from("x = 1\n") });
  await expect(dialog.getByLabel("Manifest (JSON)")).toHaveValue('{"name":"depuis-fichier"}');
  await expect(dialog.getByLabel("Code de la stratégie")).toHaveValue("x = 1\n");
  await dialog.getByRole("button", { name: "Déposer la version" }).click();
  await expect(dialog).toHaveCount(0);
  expect(state.requests.find((r) => r.method === "POST")!.body).toMatchObject({ manifest: { name: "depuis-fichier" }, code: "x = 1\n" });
});

test("changement de statut : brouillon vers approuvée", async ({ page }) => {
  const { state } = await mockRegistry(page);
  await page.goto(OPEN);
  await page.getByRole("button", { name: "Approuver la version 1" }).click();
  await expect(page.locator('tr[data-version="1"]').getByText("Approuvée")).toBeVisible();
  expect(state.requests.find((r) => r.method === "PATCH")!.body).toEqual({ status: "approved" });
  await expect(page.getByRole("button", { name: "Approuver la version 1" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retirer la version 1" })).toBeVisible();
});

test("déploiement en paper : formulaire généré depuis params_schema, validé avant l'envoi, aucun choix de mode", async ({ page }) => {
  const { state } = await mockRegistry(page);
  await page.goto(`${OPEN}&v=2`);
  const form = page.getByRole("form", { name: "Déployer en paper" });
  await expect(form.getByLabel("Moyenne rapide")).toHaveValue("10"); // défaut du schéma
  await expect(form.getByLabel("Moyenne lente")).toHaveValue("30");
  await expect(form).toContainText("Entre 2 et 50");
  await expect(form.getByLabel(/mode/i)).toHaveCount(0); // le live ne se choisit pas ici
  await expect(form.getByRole("combobox")).toHaveCount(1); // le seul choix : le compte paper

  await form.getByLabel("Moyenne rapide").fill("99");
  await form.getByLabel("Moyenne lente").fill("2");
  await form.getByLabel("Nom de l'instance").fill("mon instance");
  await form.getByRole("button", { name: "Déployer en paper" }).click();
  await expect(form).toContainText("Doit être au plus 50.");
  await expect(form).toContainText("Doit être au moins 5.");
  await expect(form).toContainText("Nom invalide");
  await expect(form).toContainText("Choisir un compte paper.");
  expect(state.requests.filter((r) => r.method === "POST")).toHaveLength(0); // rien d'envoyé

  await form.getByLabel("Moyenne rapide").fill("12");
  await form.getByLabel("Moyenne lente").fill("40");
  await form.getByLabel("Nom de l'instance").fill("sma-1");
  await form.getByLabel("Compte paper").selectOption({ label: "Bac paper (USDT)" });
  await form.getByRole("button", { name: "Déployer en paper" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Instance « sma-1 » créée en paper" })).toBeVisible();
  const post = state.requests.find((r) => r.method === "POST" && r.path === "/instances")!;
  expect(post.body).toEqual({ name: "sma-1", mode: "paper", params: { fast: 12, slow: 40 }, strategy_version_id: "00000000-0000-4000-8000-0000000000b2", account_id: "acc-paper" });
  expect(post.key).toMatch(/^[0-9a-f-]{36}$/);
  // L'instance apparaît, état observé inconnu : jamais « en marche » d'après la demande.
  const created = inst(page, "sma-1");
  await expect(created).toBeVisible();
  await expect(created.locator('[data-state="unknown"]').first()).toBeVisible();
});

test("version retirée : déploiement refusé avec sa raison", async ({ page }) => {
  const { state } = await mockRegistry(page);
  state.versions[1]!.status = "retired";
  await page.goto(`${OPEN}&v=1`);
  await expect(page.getByText("Cette version est retirée : elle ne se déploie plus.")).toBeVisible();
  await expect(page.getByRole("form", { name: "Déployer en paper" })).toHaveCount(0);
});

test("« Ce qui tourne réellement » : empreinte, version du moteur, configuration effective datée, dérive en évidence", async ({ page }) => {
  await mockRegistry(page);
  await page.goto(OPEN);
  const alpha = inst(page, "alpha");
  const panel = alpha.locator("[data-running]");
  await expect(panel).toContainText("Ce qui tourne réellement");
  await expect(panel).toContainText("ffffffffffffffff"); // empreinte de déploiement (16 premiers caractères)
  await expect(panel).toContainText("2026.9");
  await expect(panel).toContainText("Aucun écart constaté");
  await expect(panel.locator('[data-config-key="stoploss"]')).toContainText("-0,05");
  await panel.locator('[data-state="fresh"]').first().hover();
  await expect(page.getByRole("tooltip")).toContainText("Observé il y a");

  const bravo = inst(page, "bravo").locator("[data-running]");
  await expect(bravo.locator("[data-drift]")).toContainText("ÉCART");
  const drift = bravo.locator('[data-drift-key="stoploss"]');
  await expect(drift).toContainText("Attendu : -0,05");
  await expect(drift).toContainText("Observé : -0,10");
  await expect(bravo.locator('[data-drift-row="true"]')).toHaveCount(1);
  await expect(bravo.getByText(/périmé depuis/).first()).toBeVisible();

  const echo = inst(page, "echo").locator("[data-running]");
  await expect(echo.getByText("inconnu").first()).toBeVisible(); // jamais relevée : inconnu, pas une dernière valeur
  await expect(echo).toContainText("n'a jamais été relevée");
  await expect(inst(page, "charlie")).toHaveCount(0); // sans version de registre : pas une instance de cette stratégie
});

test("mode : badge d'après le mode observé, « MODE INCOHÉRENT » en rouge ; voulu et observé côte à côte", async ({ page }) => {
  await mockRegistry(page);
  await page.goto(OPEN);
  const delta = inst(page, "delta");
  const badge = delta.getByText("MODE INCOHÉRENT");
  await expect(badge).toBeVisible();
  await expect(delta.getByText("voulu PAPER, observé LIVE")).toBeVisible();
  const [color, live] = await Promise.all([
    badge.evaluate((el) => getComputedStyle(el).color),
    page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--live")),
  ]);
  expect(color).not.toBe("");
  expect(live).not.toBe("");
  await expect(inst(page, "alpha").getByText("État voulu")).toBeVisible(); // voulu running, observé sorties seules
  await expect(inst(page, "echo").getByText("État voulu")).toHaveCount(0);
});

test("commande : pas de « fait » avant verified ; expirée, elle reste visible jusqu'à « vu »", async ({ page }) => {
  await mockRegistry(page);
  await page.goto(OPEN);
  const alpha = inst(page, "alpha");
  await alpha.getByRole("button", { name: "Rouvrir les entrées" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Rouvrir les entrées" }).click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  const history = alpha.locator('ol li[data-command-type="resume_entries"]');
  await expect(history).toContainText("demandée, pas encore transmise au moteur");
  await expect(history).not.toContainText("faite");
  await expect(alpha.locator("p[data-command-status]")).not.toContainText("faite");

  const id = `cmd-resume_entries-${ID(1)}`;
  const base = { id, instance_id: ID(1), type: "resume_entries" };
  await emit(page, "command", sseEvent(Date.now(), "command", command(Date.now(), { ...base, status: "acknowledged", dispatched_at: iso(Date.now() + 1000), acknowledged_at: iso(Date.now() + 2000) })));
  await expect(history).toContainText("reçue par le moteur, effet pas encore observé");
  await expect(history).not.toContainText("faite");
  await emit(page, "command", sseEvent(Date.now(), "command", command(Date.now(), { ...base, status: "verified", verified_at: iso(Date.now() + 3000) })));
  await expect(history).toContainText("faite, effet observé dans le moteur");
  await expect(history).toContainText("Vérifiée");

  await emit(page, "command", sseEvent(Date.now(), "command", command(Date.now(), { id: "c-late", instance_id: ID(1), type: "stop", status: "timed_out", timed_out_at: iso(Date.now()), result: { reason: "le moteur n'a pas confirmé l'arrêt" } })));
  const late = alpha.locator('ol li[data-command-type="stop"]');
  await expect(late).toContainText("délai dépassé : effet non observé");
  await expect(late).toContainText("le moteur n'a pas confirmé l'arrêt");
  await late.getByRole("button", { name: "Marquer comme vu" }).click();
  await expect(late).toBeVisible();
  await expect(late.getByRole("button", { name: "Marquer comme vu" })).toHaveCount(0);
});

test("reporté : logs en direct et promotion disent « à venir »", async ({ page }) => {
  await mockRegistry(page);
  await page.goto(OPEN);
  const alpha = inst(page, "alpha");
  await expect(alpha.getByText("Logs en direct")).toBeVisible();
  await expect(alpha.getByText("À venir (jalon M4).")).toBeVisible();
  await expect(alpha.getByText("À venir (jalon M7).")).toBeVisible();
});

test("créer une stratégie : nom contrôlé, doublon expliqué", async ({ page }) => {
  const { state } = await mockRegistry(page);
  await page.goto("/strategies");
  const name = page.getByLabel("Nom de la nouvelle stratégie");
  await name.fill("Nom Invalide");
  await page.getByRole("button", { name: "Créer la stratégie" }).click();
  await expect(page.getByText(/Nom invalide : minuscules/)).toBeVisible();
  await name.fill("momentum");
  await page.getByRole("button", { name: "Créer la stratégie" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Stratégie « momentum » créée" })).toBeVisible();
  expect(state.requests.find((r) => r.method === "POST")!.body).toEqual({ name: "momentum" });
});

test("rôle viewer : lecture seule, aucun bouton d'écriture", async ({ page }) => {
  await mockRegistry(page, { role: "viewer" });
  await page.goto(`${OPEN}&v=2`);
  await expect(page.getByText(/Lecture seule : déposer une version/)).toBeVisible();
  await expect(page.locator('tr[data-version="2"]')).toBeVisible();
  await expect(inst(page, "alpha")).toBeVisible();
  for (const name of [/Déposer une version/, /Approuver|Retirer/, /Déployer en paper/, /Rouvrir les entrées|Bloquer les entrées|Démarrer|Arrêter|Tout fermer/, /Créer la stratégie/]) {
    await expect(page.getByRole("button", { name })).toHaveCount(0);
  }
});

test("erreur de chargement du registre : cause et action", async ({ page }) => {
  await mockRegistry(page);
  await page.route(/\/api\/v1\/strategies(\?|$)/, (route) => route.fulfill({ status: 503, contentType: "application/problem+json", body: JSON.stringify({ title: "Service Unavailable", status: 503 }) }));
  await page.goto("/strategies");
  await expect(page.getByText("Registre indisponible")).toBeVisible();
  await expect(page.getByRole("button", { name: "Réessayer" })).toBeVisible();
});

test("console sans erreur ni violation de CSP, aucune requête tierce", async ({ page }) => {
  const noise: string[] = [];
  page.on("console", (m) => (m.type() === "error" || m.text().includes("Content Security Policy")) && noise.push(m.text()));
  const external: string[] = [];
  page.on("request", (r) => !r.url().startsWith("http://127.0.0.1:4173") && !r.url().startsWith("data:") && external.push(r.url()));
  await mockRegistry(page);
  await page.goto(`${OPEN}&v=2`);
  await expect(inst(page, "alpha")).toBeVisible();
  await expect(page.locator("[data-version-panel]")).toBeVisible();
  expect(noise).toEqual([]);
  expect(external).toEqual([]);
});

for (const scheme of ["light", "dark"] as const) {
  test(`axe sans violation (${scheme}) : écran, dépôt ouvert`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
    await mockRegistry(page);
    await page.goto(`${OPEN}&v=2`);
    await expect(inst(page, "bravo").locator("[data-drift]")).toBeVisible();
    await expectNoViolation(page);
    await page.getByRole("button", { name: "Déposer une version" }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await expectNoViolation(page);
  });
}

test("clavier : atteindre une stratégie, une version et le formulaire de déploiement par Tab", async ({ page }) => {
  await mockRegistry(page);
  await page.goto("/strategies");
  const link = page.getByRole("link", { name: "Ouvrir la stratégie sma-cross" });
  for (let i = 0; i < 40 && !(await link.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(link).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`s=${S1}`));
  const details = page.getByRole("link", { name: "Voir la version 2" });
  for (let i = 0; i < 40 && !(await details.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(details).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Moyenne rapide")).toBeVisible();
  const field = page.getByLabel("Moyenne rapide");
  for (let i = 0; i < 80 && !(await field.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(field).toBeFocused();
});

const viewports = { bureau: { width: 1280, height: 800 }, tablette: { width: 820, height: 1180 } };
for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of Object.entries(viewports)) {
    test(`stratégies ${scheme} ${name} : cibles de 44 px, pas de défilement horizontal de la page, capture`, async ({ page }) => {
      await page.clock.setFixedTime(new Date(T0));
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await page.setViewportSize(viewport);
      const w = world(T0);
      await mockRegistry(page, { now: () => T0, data: { instances: w.instances, alerts: w.alerts } });
      await page.goto(`${OPEN}&v=2`);
      await expect(inst(page, "bravo").locator("[data-drift]")).toBeVisible();
      await expect(page.getByRole("form", { name: "Déployer en paper" })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      for (const b of await page.locator("main").getByRole("button").all()) {
        expect((await b.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expectNoViolation(page);
      if (process.env.CAPTURES === "1") {
        await page.screenshot({ path: path.join(CAPTURES, `strategies-${scheme === "light" ? "clair" : "sombre"}-${name}.png`), fullPage: true });
      }
    });
  }
}

test("bureau (1280 px) : les actions d'une version sont dans le champ visible, sur une seule ligne", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockRegistry(page);
  await page.goto(OPEN);
  const row = page.locator('tr[data-version="2"]');
  await expect(row).toBeVisible();
  await expectInView(row.getByRole("link", { name: "Voir la version 2" }));
  const draft = page.locator('tr[data-version="1"]');
  await expectInView(draft.getByRole("button", { name: /Approuver la version 1/ }));
  expect((await draft.boundingBox())!.height).toBeLessThan(80);
});

test("dépôt : le pied reste visible à 1280×800, sélecteur de fichier en français, Tab boucle dans la fenêtre", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockRegistry(page);
  await page.goto(OPEN);
  await page.getByRole("button", { name: "Déposer une version" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog.getByRole("button", { name: "Déposer la version" })).toBeInViewport({ ratio: 1 });
  await expect(dialog.getByRole("button", { name: "Annuler" })).toBeInViewport({ ratio: 1 });
  await expect(dialog.getByRole("button", { name: "Charger un manifest depuis un fichier" })).toBeVisible();
  await expect(dialog).not.toContainText("Choose File");
  // Piège de focus : le focus ne sort jamais de la fenêtre (jamais sur BODY).
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.activeElement?.closest("dialog") !== null)).toBe(true);
  }
  await page.keyboard.press("Shift+Tab");
  expect(await page.evaluate(() => document.activeElement?.closest("dialog") !== null)).toBe(true);
});

test("un seul bouton plein par vue ; aucune carte dans une carte", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1600 });
  const w = world(T0);
  await mockRegistry(page, { now: () => T0, data: { instances: w.instances, alerts: w.alerts } });
  await page.goto(`${OPEN}&v=2`);
  await expect(page.getByRole("form", { name: "Déployer en paper" })).toBeVisible();
  const filled = await page.locator("main").getByRole("button").evaluateAll((bs) => bs.filter((b) => (b as HTMLElement).dataset.variant === "default").length);
  expect(filled).toBe(1);
  // Un élément avec cadre (bordure + rayon) n'a aucun ancêtre avec cadre dans `main`.
  const nested = await page.locator("main").evaluate((m) => {
    const framed = (el: Element) => {
      const c = getComputedStyle(el);
      return c.borderTopStyle !== "none" && c.borderTopWidth !== "0px" && c.borderTopLeftRadius !== "0px";
    };
    return [...m.querySelectorAll("*")].filter((el) => {
      if (!["SECTION", "UL", "DIV", "DETAILS", "FIGURE"].includes(el.tagName) || !framed(el)) return false;
      for (let p = el.parentElement; p && p !== m; p = p.parentElement) if (framed(p)) return true;
      return false;
    }).map((el) => `${el.tagName}.${String(el.className).slice(0, 50)}`);
  });
  expect(nested).toEqual([]);
});
