import { expect, test } from "@playwright/test";

import { ME, expectNoViolation, mockAuth, problem, signIn, signOut, useTheme, watchConsole } from "./support";

const shellHeading = (page: import("@playwright/test").Page) => page.getByRole("heading", { level: 1, name: "Instances" });

test("password, then code, then the shell", async ({ page }) => {
  const errors = watchConsole(page);
  const state = await mockAuth(page);
  await signIn(page);

  const code = page.getByLabel("Code");
  await expect(code).toBeFocused();
  await expect(code).toHaveAttribute("type", "text");
  await expect(code).toHaveAttribute("autocomplete", "one-time-code");
  await expect(code).toHaveAttribute("autocapitalize", "characters");
  await expect(code).toHaveAttribute("spellcheck", "false");
  await expect(code).not.toHaveAttribute("maxlength", /.*/);
  await code.fill("123456");
  await page.getByRole("button", { name: "Valider le code" }).click();

  await expect(shellHeading(page)).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Navigation principale" })).toBeVisible();
  expect(state.codes).toEqual(["123456"]);
  expect(errors).toEqual([]);
});

test("a recovery code is accepted and sent trimmed", async ({ page }) => {
  const state = await mockAuth(page);
  await signIn(page);
  await page.getByLabel("Code").fill("  ABCD-EFGH-2345  ");
  await page.getByRole("button", { name: "Valider le code" }).click();
  await expect(shellHeading(page)).toBeVisible();
  expect(state.codes).toEqual(["ABCD-EFGH-2345"]);
});

test("a refused code shows a message, empties and focuses the field, and allows going back to the password", async ({ page }) => {
  await mockAuth(page, { codeStatus: 401 });
  await signIn(page);
  await page.getByLabel("Code").fill("000000");
  await page.getByRole("button", { name: "Valider le code" }).click();

  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Code non validé");
  await expect(alert).toContainText("Code refusé");
  const code = page.getByLabel("Code");
  await expect(code).toHaveValue("");
  await expect(code).toBeFocused();
  await expect(code).toHaveAttribute("aria-describedby", (await alert.getAttribute("id")) ?? "");
  await expectNoViolation(page);

  await page.getByRole("button", { name: "Revenir au mot de passe" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Connexion" })).toBeVisible();
  await expect(page.getByLabel("Identifiant")).toBeFocused();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("a locked account and too many attempts get different messages", async ({ page }) => {
  await mockAuth(page, { codeStatus: 423 });
  await signIn(page);
  await page.getByLabel("Code").fill("000000");
  await page.getByRole("button", { name: "Valider le code" }).click();
  await expect(page.getByRole("alert")).toContainText("Compte verrouillé");
  await expect(page.getByRole("alert")).not.toContainText("Trop de tentatives");

  await page.unrouteAll();
  await mockAuth(page, { codeStatus: 429 });
  await page.getByLabel("Code").fill("000000");
  await page.getByRole("button", { name: "Valider le code" }).click();
  await expect(page.getByRole("alert")).toContainText("Trop de tentatives");
  await expect(page.getByRole("alert")).not.toContainText("verrouillé");
});

test("an existing session shows the shell without the login, and signing out brings the login back", async ({ page }) => {
  const state = await mockAuth(page, { authenticated: true });
  await page.goto("/");
  await expect(shellHeading(page)).toBeVisible();
  await signOut(page);
  await expect(page.getByLabel("Identifiant")).toBeVisible();
  expect(state.logouts).toBe(1);
});

test("a failing session API shows an explicit error, never a false login", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.abort("connectionrefused"));
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Session impossible à vérifier");
  await expect(page.getByLabel("Identifiant")).toHaveCount(0);
  await expectNoViolation(page);
});

test("a 401 during the session brings the login back", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ME) }),
  );
  await page.route("**/api/v1/auth/logout", (route) => problem(route, 401, "Unauthorized"));
  await page.goto("/");
  await signOut(page);
  await expect(page.getByLabel("Identifiant")).toBeVisible();
});

for (const theme of ["light", "dark"] as const) {
  test(`the code step and the shell have no axe violation in the ${theme} theme`, async ({ page }) => {
    await useTheme(page, theme);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockAuth(page);
    await signIn(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    await expectNoViolation(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    await page.getByLabel("Code").fill("123456");
    await page.getByRole("button", { name: "Valider le code" }).click();
    await expect(shellHeading(page)).toBeVisible();
    await expectNoViolation(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}
