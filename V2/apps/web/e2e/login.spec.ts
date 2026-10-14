import { expect, test } from "@playwright/test";

import { expectNoViolation, mockAuth, signIn, useTheme, watchConsole } from "./support";

const LOGIN_API = "**/api/v1/auth/login";

test.beforeEach(async ({ page }) => {
  await mockAuth(page);
});

for (const theme of ["light", "dark"] as const) {
  test(`the password step renders without console error nor axe violation in the ${theme} theme`, async ({ page }) => {
    const errors = watchConsole(page);
    await useTheme(page, theme);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expect(page.getByRole("heading", { level: 1, name: "Connexion" })).toBeVisible();
    await expect(page.getByText("Accès réservé à l'opérateur, par VPN.")).toBeVisible();
    await expect(page.getByText(/maquette/i)).toHaveCount(0);
    const username = page.getByLabel("Identifiant");
    await expect(username).toHaveAttribute("autocapitalize", "none");
    await expect(username).toHaveAttribute("spellcheck", "false");
    await expect(username).not.toBeFocused(); // never focused on first display
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expectNoViolation(page);

    // Error state (API missing): same axe check in this theme.
    await page.route(LOGIN_API, (route) => route.fulfill({ status: 404, body: "not found" }));
    await username.fill("operateur");
    await page.getByLabel("Mot de passe").fill("motdepasse");
    await page.getByRole("button", { name: "Se connecter" }).click();
    await expect(page.getByRole("alert")).toContainText("HTTP 404");
    await expectNoViolation(page);
    expect(errors).toEqual([]);
  });
}

test("the keyboard path works, a 404 is tied to the fields, and the password is not kept", async ({ page }) => {
  await page.route(LOGIN_API, (route) => route.fulfill({ status: 404, body: "not found" }));
  await page.goto("/");
  await expect(page.getByLabel("Identifiant")).toBeVisible(); // the form waits for /auth/me

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
  const password = page.getByLabel("Mot de passe");
  await expect(password).toHaveValue("");
  await expect(password).toBeFocused();
  await expect(password).toHaveAttribute("aria-invalid", "true");
  await expect(password).toHaveAttribute("aria-describedby", (await alert.getAttribute("id")) ?? "");
  await expect(page.getByLabel("Identifiant")).toHaveValue("operateur");

  // The password never reaches the URL nor the browser storage.
  expect(page.url()).not.toContain("motdepasse");
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }))).not.toContain("motdepasse");
});

test("the code step stays pending until /auth/me is refetched, so the code cannot be sent twice", async ({ page }) => {
  const state = await mockAuth(page);
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/v1/auth/me", async (route) => {
    if (state.authenticated) await gate; // the refetch that follows the accepted code
    await route.fallback();
  });
  await signIn(page);
  await page.getByLabel("Code").fill("123456");
  await page.getByRole("button", { name: "Valider le code" }).click();

  await expect(page.getByRole("button", { name: "Vérification en cours…" })).toBeDisabled();
  await page.locator("form").evaluate((form: HTMLFormElement) => form.requestSubmit());
  release();
  await expect(page.getByRole("heading", { level: 1, name: "Instances" })).toBeVisible();
  expect(state.codes).toEqual(["123456"]);
});

test("a pending submit disables the button, is announced, and cannot be sent twice", async ({ page }) => {
  let calls = 0;
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => (release = resolve));
  await page.route(LOGIN_API, async (route) => {
    calls += 1;
    await gate;
    await route.abort("connectionrefused");
  });
  await page.goto("/");
  await page.getByLabel("Identifiant").fill("operateur");
  await page.getByLabel("Mot de passe").fill("motdepasse");
  await page.getByRole("button", { name: "Se connecter" }).click();

  await expect(page.getByRole("button", { name: "Connexion en cours…" })).toBeDisabled();
  await expect(page.getByRole("status")).toContainText("Connexion en cours…");
  await page.locator("form").evaluate((form: HTMLFormElement) => form.requestSubmit()); // second submit while pending
  release();
  await expect(page.getByRole("alert")).toContainText("injoignable");
  expect(calls).toBe(1);
});
