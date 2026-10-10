import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const CAPTURES = path.resolve(import.meta.dirname, "../../../docs/captures/m0");
const LOGIN_API = "**/api/v1/auth/login";

const viewports = {
  bureau: { width: 1280, height: 800 },
  tablette: { width: 820, height: 1180 },
};

async function expectNoSeriousViolation(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  // Toute violation bloque, quelle que soit sa gravité.
  expect(violations.map((v) => v.id)).toEqual([]);
}

for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of Object.entries(viewports)) {
    test(`login ${scheme} ${name} : affichage, axe, capture`, async ({ page }) => {
      const violations: string[] = [];
      page.on("console", (m) => {
        if (m.text().includes("Content Security Policy")) violations.push(m.text());
      });
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await page.setViewportSize(viewport);
      await page.goto("/");

      await expect(page.getByRole("heading", { level: 1, name: "Centrade" })).toBeVisible();
      await expect(page.getByLabel("Identifiant")).toBeVisible();
      await expect(page.getByLabel("Mot de passe")).toBeVisible();
      const submit = page.getByRole("button", { name: "Se connecter" });
      await expect(submit).toBeVisible();
      expect((await submit.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      expect((await page.getByLabel("Identifiant").boundingBox())?.height).toBeGreaterThanOrEqual(44);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

      await expectNoSeriousViolation(page);

      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: path.join(CAPTURES, `login-${scheme === "light" ? "clair" : "sombre"}-${name}.png`) });

      // État d'erreur (API absente) : même contrôle axe dans ce thème.
      await page.route(LOGIN_API, (route) => route.fulfill({ status: 404, body: "not found" }));
      await page.getByLabel("Identifiant").fill("operateur");
      await page.getByLabel("Mot de passe").fill("motdepasse");
      await submit.click();
      await expect(page.getByRole("alert")).toContainText("HTTP 404");
      await expectNoSeriousViolation(page);
      expect(violations).toEqual([]);
    });
  }
}

test("login : parcours au clavier, erreur 404 reliée au formulaire, mot de passe non conservé", async ({ page }) => {
  await page.route(LOGIN_API, (route) => route.fulfill({ status: 404, body: "not found" }));
  await page.goto("/");

  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Identifiant")).toBeFocused();
  await page.keyboard.type("operateur");
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Mot de passe")).toBeFocused();
  await page.keyboard.type("motdepasse");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Se connecter" })).toBeFocused();
  await page.keyboard.press("Enter");

  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Connexion impossible");
  await expect(alert).toContainText("HTTP 404");
  await expect(page.getByLabel("Mot de passe")).toHaveValue("");
  await expect(page.getByLabel("Mot de passe")).toBeFocused();
  await expect(page.getByLabel("Identifiant")).toHaveValue("operateur");
  await expect(page.getByLabel("Mot de passe")).toHaveAttribute("aria-describedby", await alert.getAttribute("id") ?? "");
  await expect(page.getByText("Connexion acceptée")).toHaveCount(0);
});

test("login : l'envoi en cours désactive le bouton et est annoncé", async ({ page }) => {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => (release = resolve));
  await page.route(LOGIN_API, async (route) => {
    await gate;
    await route.abort("connectionrefused");
  });
  await page.goto("/");
  await page.getByLabel("Identifiant").fill("operateur");
  await page.getByLabel("Mot de passe").fill("motdepasse");
  await page.getByRole("button", { name: "Se connecter" }).click();

  await expect(page.getByRole("button", { name: "Connexion en cours…" })).toBeDisabled();
  await expect(page.getByRole("status")).toContainText("Connexion en cours…");
  release();
  await expect(page.getByRole("alert")).toContainText("injoignable");
});
