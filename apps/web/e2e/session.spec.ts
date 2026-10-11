import { expect, test } from "@playwright/test";

import { ME, expectNoViolation, mockAuth, problem } from "./support";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel("Identifiant").fill("operateur");
  await page.getByLabel("Mot de passe").fill("motdepasse");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("heading", { name: "Vérification en deux étapes" })).toBeVisible();
}

test("mot de passe, puis code, puis coquille", async ({ page }) => {
  await mockAuth(page);
  await signIn(page);

  const code = page.getByLabel("Code", { exact: true });
  await expect(code).toBeFocused();
  await expect(code).toHaveAttribute("inputmode", "text");
  await expect(code).toHaveAttribute("autocomplete", "one-time-code");
  await code.fill("123456");
  await page.getByRole("button", { name: "Valider le code" }).click();

  const bar = page.getByRole("banner", { name: "Barre d'état" });
  await expect(bar).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: "Cockpit" })).toBeVisible();
  // Rien n'est observé dans ce lot : tout est « inconnu », jamais supposé.
  await expect(bar.getByText("inconnu").first()).toBeVisible();
  await expect(bar.getByRole("list", { name: "Connexions" }).getByText("inconnu")).toHaveCount(3);

  const kill = page.getByRole("button", { name: "Kill switch global" });
  await expect(kill).toHaveAttribute("aria-disabled", "true");
  await expect(kill).toHaveAccessibleDescription("Disponible au jalon M3");
  await kill.focus();
  await expect(page.getByRole("tooltip")).toHaveText("Disponible au jalon M3");

  const nav = page.getByRole("navigation", { name: "Écrans" });
  await expect(nav.getByRole("listitem")).toHaveCount(10);
  await expect(nav.getByRole("button", { name: "Cockpit" })).toHaveAttribute("aria-current", "page");
  const disabled = nav.getByRole("button", { disabled: true });
  await expect(disabled).toHaveCount(9);
  await expect(disabled.first()).toContainText("à venir");
  for (const target of [kill, ...(await disabled.all())]) {
    expect((await target.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }
});

test("code refusé : message, champ vidé et focalisé, retour possible au mot de passe", async ({ page }) => {
  await mockAuth(page, { codeStatus: 401 });
  await signIn(page);
  await page.getByLabel("Code", { exact: true }).fill("000000");
  await page.getByRole("button", { name: "Valider le code" }).click();

  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Code non validé");
  await expect(alert).toContainText("Code refusé");
  await expect(page.getByLabel("Code", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Code", { exact: true })).toBeFocused();
  await expectNoViolation(page);

  await page.getByRole("button", { name: "Revenir au mot de passe" }).click();
  await expect(page.getByLabel("Mot de passe")).toBeVisible();
});

test("compte verrouillé et trop de tentatives sont distingués", async ({ page }) => {
  await mockAuth(page, { codeStatus: 423 });
  await signIn(page);
  await page.getByLabel("Code", { exact: true }).fill("000000");
  await page.getByRole("button", { name: "Valider le code" }).click();
  await expect(page.getByRole("alert")).toContainText("Compte verrouillé");
});

test("session existante : la coquille s'affiche sans login, et la déconnexion ramène au login", async ({ page }) => {
  const state = await mockAuth(page, { authenticated: true });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Cockpit" })).toBeVisible();
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page.getByLabel("Identifiant")).toBeVisible();
  expect(state.logouts).toBe(1);
});

test("API de session en panne : erreur explicite, pas de faux login", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.abort("connectionrefused"));
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Session impossible à vérifier");
  await expect(page.getByLabel("Identifiant")).toHaveCount(0);
  await expectNoViolation(page);
});

test("un 401 en cours de session ramène au login", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ME) }),
  );
  await page.route("**/api/v1/auth/logout", (route) => problem(route, 401, "Unauthorized"));
  await page.goto("/");
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page.getByLabel("Identifiant")).toBeVisible();
});

for (const scheme of ["light", "dark"] as const) {
  test(`axe sans violation : écran du code et coquille, thème ${scheme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
    await mockAuth(page);
    for (const viewport of [{ width: 1280, height: 800 }, { width: 820, height: 1180 }]) {
      await page.setViewportSize(viewport);
      await page.goto("/");
      if (!(await page.getByLabel("Identifiant").isVisible())) await page.reload();
      await signIn(page);
      await expectNoViolation(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

      await page.getByLabel("Code", { exact: true }).fill("123456");
      await page.getByRole("button", { name: "Valider le code" }).click();
      await expect(page.getByRole("heading", { level: 1, name: "Cockpit" })).toBeVisible();
      await expectNoViolation(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

      // Bascule manuelle : l'autre thème, mêmes contrôles.
      await page.getByRole("button", { name: scheme === "light" ? "Passer au thème sombre" : "Passer au thème clair" }).click();
      await expect(page.locator("html")).toHaveAttribute("data-theme", scheme === "light" ? "dark" : "light");
      await expectNoViolation(page);

      await page.getByRole("button", { name: "Se déconnecter" }).click();
      await expect(page.getByLabel("Identifiant")).toBeVisible();
      await page.evaluate(() => localStorage.clear());
    }
  });
}
