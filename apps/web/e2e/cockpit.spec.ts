import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

import { command, emit, instance, mockCockpit, observed, sseEvent, stopBeats, T0, world } from "./cockpit-support";
import { expectNoViolation } from "./support";

const CAPTURES = path.resolve(import.meta.dirname, "../../../docs/captures/m1");
const row = (page: Page, name: string) => page.locator(`li[data-instance="${name}"]`);
const iso = (ms: number) => new Date(ms).toISOString();

test("grille : fraîche, périmée, inconnue, mode incohérent ; voulu à côté de l'observé seulement s'il diffère", async ({ page }) => {
  await mockCockpit(page);
  await page.goto("/");

  const alpha = row(page, "alpha");
  await expect(alpha.getByText("sorties seules")).toBeVisible();
  await expect(alpha.getByText("État voulu")).toBeVisible(); // voulu running ≠ observé exits_only
  await expect(alpha.getByText("en marche")).toBeVisible(); // la valeur voulue, à côté
  await expect(alpha.getByText("simulé")).toBeVisible();

  const bravo = row(page, "bravo");
  await expect(bravo.getByText(/périmé depuis/).first()).toBeVisible();

  const charlie = row(page, "charlie");
  await expect(charlie.getByText("inconnu").first()).toBeVisible();
  await expect(charlie.locator('[data-state="unknown"]').first()).toBeVisible();

  const delta = row(page, "delta");
  await expect(delta.getByText("MODE INCOHÉRENT")).toBeVisible();
  await expect(delta.getByText("voulu PAPER, observé LIVE")).toBeVisible();

  const echo = row(page, "echo");
  await expect(echo.getByText("État voulu")).toHaveCount(0); // voulu = observé frais : rien à ajouter

  // L'âge est donné au survol...
  await echo.locator('[data-state="fresh"]').first().hover();
  await expect(page.getByRole("tooltip")).toContainText("Observé il y a");
  // ... et au focus clavier.
  await page.mouse.move(0, 0);
  for (let i = 0; i < 120; i++) {
    await page.keyboard.press("Tab");
    if (await page.evaluate(() => !!document.activeElement?.closest('li[data-instance="echo"]') && (document.activeElement as HTMLElement).dataset.state === "fresh")) break;
  }
  await expect(page.getByRole("tooltip")).toContainText("Observé il y a");
});

test("barre persistante : mode d'après l'observé, alertes, connexions ; kill switch grisé", async ({ page }) => {
  await mockCockpit(page);
  await page.goto("/");
  const bar = page.getByRole("banner");
  await expect(bar).toContainText("LIVE"); // delta est observée live
  await expect(bar.getByText("Alertes")).toBeVisible();
  await expect(bar.getByText("2", { exact: true })).toBeVisible();
  await expect(bar).toContainText("Bus");
  await expect(bar.getByRole("button", { name: "Kill switch global" })).toHaveAttribute("aria-disabled", "true");
});

test("barre persistante : PAPER tant qu'aucune instance live n'est observée, inconnu si rien n'est observé", async ({ page }) => {
  const now = Date.now();
  await mockCockpit(page, { data: { instances: [instance(now, { id: "i1", name: "solo" })], alerts: [] } });
  await page.goto("/");
  await expect(page.getByRole("banner").getByText(/Mode : PAPER/)).toBeVisible();

  const page2 = await page.context().newPage();
  await mockCockpit(page2, { data: { instances: [instance(now, { id: "i2", name: "muette", state: observed("unknown", now, null), observed_mode: observed("unknown", now, null) })], alerts: [] } });
  await page2.goto("/");
  await expect(page2.getByRole("banner").getByText("Mode : inconnu")).toBeVisible();
});

test("commande : étapes réelles, « faite » seulement à verified, clé d'idempotence, aucune ressource tierce", async ({ page }) => {
  const foreign: string[] = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (!["127.0.0.1", "localhost"].includes(u.hostname) && u.protocol.startsWith("http")) foreign.push(r.url());
  });
  const api = await mockCockpit(page);
  const alpha = api.instances[0]!;
  const cmd = (over: Record<string, unknown>) => command(Date.now(), { id: "c-resume", instance_id: alpha.id as string, ...over });
  api.actionResponse = () => ({ status: 202, body: { command_id: "c-resume", command: cmd({ status: "requested" }) } });
  await page.goto("/");

  await row(page, "alpha").getByRole("button", { name: "Rouvrir les entrées" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("Rouvrir les entrées : alpha");
  await expect(dialog).toContainText("Augmente le risque");
  await expect(dialog).toContainText("État observé à cet instant : sorties seules");
  await dialog.getByRole("button", { name: "Rouvrir les entrées" }).click();
  await expect(dialog).toHaveCount(0);

  const status = row(page, "alpha").locator("[data-command-status]");
  await expect(status).toContainText("demandée, pas encore transmise");
  expect(api.requests.find((r) => r.method === "POST")?.headers["idempotency-key"]).toMatch(/^[0-9a-f-]{36}$/);

  const base = { id: "c-resume", instance_id: alpha.id as string };
  await emit(page, "command", sseEvent(Date.now(), "command", cmd({ status: "dispatched", dispatched_at: iso(Date.now()) })));
  await expect(status).toContainText("transmise au moteur");
  await emit(page, "command", sseEvent(Date.now(), "command", cmd({ status: "acknowledged", dispatched_at: iso(Date.now() - 1000), acknowledged_at: iso(Date.now()) })));
  await expect(status).toContainText("reçue par le moteur, effet pas encore observé");
  await expect(row(page, "alpha")).not.toContainText("faite");

  await emit(page, "command", sseEvent(Date.now(), "command", command(Date.now(), { ...base, status: "verified", dispatched_at: iso(Date.now() - 2000), acknowledged_at: iso(Date.now() - 1000), verified_at: iso(Date.now()) })));
  await expect(status).toContainText("faite, effet observé dans le moteur");
  expect(foreign).toEqual([]);
});

test("refus 409 de rouvrir les entrées : la raison est affichée, la fenêtre reste ouverte", async ({ page }) => {
  const api = await mockCockpit(page);
  api.actionResponse = () => ({
    status: 409,
    contentType: "application/problem+json",
    body: { type: "about:blank", title: "Conflict", status: 409, detail: "L'état observé est périmé : reprise des entrées refusée." },
  });
  await page.goto("/");
  await row(page, "alpha").getByRole("button", { name: "Rouvrir les entrées" }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByRole("button", { name: "Rouvrir les entrées" }).click();
  await expect(dialog.getByRole("alert")).toContainText("reprise des entrées refusée");
  await expect(dialog).toBeVisible();
});

test("commande expirée : visible avec sa raison, jamais « faite », jusqu'à ce que l'opérateur l'ait vue", async ({ page }) => {
  const now = Date.now();
  const w = world(now);
  await mockCockpit(page, {
    data: {
      instances: w.instances,
      commands: [command(now, { id: "c-late", instance_id: w.instances[0]!.id as string, status: "timed_out", timed_out_at: iso(now - 5000), result: { reason: "le moteur n'a pas confirmé l'effet" } })],
    },
  });
  await page.goto("/");
  const notice = row(page, "alpha").getByRole("alert");
  await expect(notice).toContainText("délai dépassé : effet non observé");
  await expect(notice).toContainText("le moteur n'a pas confirmé l'effet");
  await expect(row(page, "alpha")).not.toContainText("faite");
  await page.reload();
  await expect(notice).toBeVisible(); // toujours là : non vue
  await notice.getByRole("button", { name: "Marquer comme vu" }).click();
  await expect(notice).toHaveCount(0);
  await page.reload();
  await expect(row(page, "alpha")).toBeVisible();
  await expect(row(page, "alpha").getByRole("alert")).toHaveCount(0);
});

test("lecteur : aucun bouton d'action ni de création", async ({ page }) => {
  await mockCockpit(page, { role: "viewer" });
  await page.goto("/");
  await expect(row(page, "alpha")).toBeVisible();
  await expect(page.getByRole("button", { name: /Bloquer|Rouvrir|Tout fermer|Arrêter|Démarrer|Créer/ })).toHaveCount(0);
});

test("temps réel : une instance créée apparaît sans rechargement ni relecture périodique", async ({ page }) => {
  const api = await mockCockpit(page);
  await page.goto("/");
  await expect(row(page, "alpha")).toBeVisible();
  const before = api.requests.filter((r) => r.path === "/instances").length;
  await emit(page, "instance", sseEvent(Date.now(), "instance", instance(Date.now(), { id: "00000000-0000-4000-8000-0000000000aa", name: "nouvelle", created_at: iso(Date.now()), state: observed("starting", Date.now(), 0) })));
  await expect(row(page, "nouvelle")).toBeVisible();
  await expect(row(page, "nouvelle")).toContainText("démarrage");
  await emit(page, "instance", sseEvent(Date.now(), "instance", instance(Date.now(), { id: "00000000-0000-4000-8000-0000000000aa", name: "nouvelle", created_at: iso(Date.now()), state: observed("exits_only", Date.now(), 0) })));
  await expect(row(page, "nouvelle")).toContainText("sorties seules");
  await page.waitForTimeout(3000);
  expect(api.requests.filter((r) => r.path === "/instances").length).toBe(before);
});

test("création d'une instance simulée : un nom suffit", async ({ page }) => {
  const api = await mockCockpit(page, { data: { instances: [], alerts: [] } });
  await page.goto("/");
  await expect(page.getByText("Aucune instance")).toBeVisible();
  await page.getByRole("button", { name: "Créer une instance simulée" }).click();
  await page.getByLabel("Nom de l'instance").fill("-mauvais");
  await page.getByRole("button", { name: "Créer l'instance" }).click();
  await expect(page.getByRole("alert")).toContainText("Nom invalide");
  await page.getByLabel("Nom de l'instance").fill("gamma");
  await page.getByRole("button", { name: "Créer l'instance" }).click();
  await expect(row(page, "gamma")).toBeVisible();
  const post = api.requests.find((r) => r.method === "POST" && r.path === "/instances");
  expect(JSON.parse(post!.body!)).toEqual({ name: "gamma", engine: "fake", mode: "paper" });
});

test("états de chargement, vide (lecteur) et erreur avec reprise", async ({ page }) => {
  const api = await mockCockpit(page, { role: "viewer", data: { instances: [], alerts: [] } });
  api.instancesDelayMs = 800;
  api.instancesStatus = 500;
  await page.goto("/");
  await expect(page.getByRole("status", { name: "Chargement des instances…" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Instances indisponibles");
  api.instancesStatus = 200;
  await page.getByRole("button", { name: "Réessayer" }).click();
  await expect(page.getByText("Aucune instance n'existe encore")).toBeVisible();
  await expect(page.getByRole("button", { name: /Créer/ })).toHaveCount(0);
});

test("mode dégradé (santé) : bandeau, bloquer/tout fermer/arrêter actifs, rouvrir/démarrer/créer désactivés avec raison", async ({ page }) => {
  const api = await mockCockpit(page);
  api.health = { ...api.health, status: "degraded", checks: { ...(api.health.checks as object), worker: { status: "down", observed_at: iso(Date.now()) } } };
  await page.goto("/");
  await expect(page.getByRole("banner").getByText(/Mode dégradé/)).toBeVisible();
  const echo = row(page, "echo");
  for (const name of ["Bloquer les entrées", "Tout fermer", "Arrêter"]) {
    await expect(echo.getByRole("button", { name })).not.toHaveAttribute("aria-disabled", "true");
  }
  for (const name of ["Rouvrir les entrées", "Démarrer"]) {
    const b = echo.getByRole("button", { name });
    await expect(b).toHaveAttribute("aria-disabled", "true");
    await expect(b).toHaveAccessibleDescription(/indisponible : Mode dégradé/);
  }
  await expect(page.getByRole("button", { name: "Créer une instance simulée" })).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByText("Santé des services")).toBeVisible();
  await expectNoViolation(page);
});

test("mode dégradé (flux) : 5 s sans battement, bandeau permanent", async ({ page }) => {
  await mockCockpit(page);
  await page.goto("/");
  await expect(row(page, "alpha")).toBeVisible();
  await expect(page.getByText(/Mode dégradé/)).toHaveCount(0);
  await stopBeats(page);
  await expect(page.getByRole("banner").getByText(/flux temps réel est coupé/)).toBeVisible({ timeout: 10_000 });
  await expect(row(page, "echo").getByRole("button", { name: "Démarrer" })).toHaveAttribute("aria-disabled", "true");
  await expect(row(page, "echo").getByRole("button", { name: "Tout fermer" })).not.toHaveAttribute("aria-disabled", "true");
});

test("clavier : atteindre une action, ouvrir la confirmation, page inerte, Échap rend le focus", async ({ page }) => {
  const csp: string[] = [];
  page.on("console", (m) => m.text().includes("Content Security Policy") && csp.push(m.text()));
  await mockCockpit(page);
  await page.goto("/");
  await expect(row(page, "alpha")).toBeVisible();
  const target = row(page, "alpha").getByRole("button", { name: "Bloquer les entrées" });
  let reached = false;
  for (let i = 0; i < 60 && !reached; i++) {
    await page.keyboard.press("Tab");
    reached = await target.evaluate((el) => el === document.activeElement);
  }
  expect(reached).toBe(true);
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("alertdialog");
  await expect(dialog.getByRole("button", { name: "Annuler" })).toBeFocused(); // le focus entre dans la fenêtre
  for (let i = 0; i < 4; i++) {
    await page.keyboard.press("Tab");
    // Fenêtre modale native : le reste de la page est inerte, le focus ne peut qu'y rester ou quitter le document.
    expect(await dialog.evaluate((el) => el.contains(document.activeElement) || document.activeElement === document.body)).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(target).toBeFocused();
  expect(csp).toEqual([]); // la fenêtre de confirmation respecte la CSP stricte
});

for (const scheme of ["light", "dark"] as const) {
  test(`axe sans violation (${scheme}) : grille, confirmation ouverte`, async ({ page }) => {
    const now = Date.now();
    const w = world(now);
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
    await mockCockpit(page, {
      data: { instances: w.instances, commands: [command(now, { id: "c-x", instance_id: w.instances[0]!.id as string, status: "failed", failed_at: iso(now - 3000), result: { reason: "refusé par le moteur" } })] },
    });
    await page.goto("/");
    await expect(row(page, "alpha")).toBeVisible();
    await expect(row(page, "alpha").getByRole("alert")).toBeVisible();
    await expectNoViolation(page);
    await row(page, "echo").getByRole("button", { name: "Tout fermer" }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await expectNoViolation(page);
  });
}

const viewports = { bureau: { width: 1280, height: 800 }, tablette: { width: 820, height: 1180 } };
for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of Object.entries(viewports)) {
    test(`cockpit ${scheme} ${name} : cibles de 44 px, pas de défilement horizontal, capture`, async ({ page }) => {
      await page.clock.setFixedTime(new Date(T0));
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await page.setViewportSize(viewport);
      const w = world(T0);
      await mockCockpit(page, {
        now: () => T0,
        data: {
          instances: w.instances,
          alerts: w.alerts,
          commands: [command(T0, { id: "c-cap", instance_id: w.instances[1]!.id as string, type: "flatten", status: "timed_out", requested_at: iso(T0 - 70_000), timed_out_at: iso(T0 - 10_000), result: { reason: "le moteur n'a pas confirmé la fermeture" } })],
        },
      });
      await page.goto("/");
      await expect(row(page, "alpha")).toBeVisible();
      await expect(page.getByText("Santé des services")).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      for (const b of await row(page, "echo").getByRole("button").all()) {
        expect((await b.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expectNoViolation(page);
      if (process.env.CAPTURES === "1") {
        await page.screenshot({ path: path.join(CAPTURES, `cockpit-${scheme === "light" ? "clair" : "sombre"}-${name}.png`), fullPage: true });
      }
    });
  }
}
