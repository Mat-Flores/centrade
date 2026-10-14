import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type Route } from "@playwright/test";

export const ME = { email: "operateur@example.test", role: "operator" };

const json = (route: Route, status: number, body: unknown, type = "application/json") =>
  route.fulfill({ status, contentType: type, body: JSON.stringify(body) });

export const problem = (route: Route, status: number, title: string) =>
  json(route, status, { type: "about:blank", title, status }, "application/problem+json");

/** Simulates the auth API; `state.authenticated` flips when the code is accepted. `codes` records the posted codes. */
export async function mockAuth(page: Page, opts: { authenticated?: boolean; codeStatus?: number } = {}) {
  const state = { authenticated: opts.authenticated ?? false, logouts: 0, codes: [] as string[] };
  await page.route("**/api/v1/auth/me", (route) =>
    state.authenticated ? json(route, 200, ME) : problem(route, 401, "Unauthorized"),
  );
  await page.route("**/api/v1/auth/login", (route) => json(route, 200, { totp_required: true }));
  await page.route("**/api/v1/auth/totp", (route) => {
    state.codes.push((route.request().postDataJSON() as { code: string }).code);
    const status = opts.codeStatus ?? 200;
    if (status !== 200) return problem(route, status, "Refused");
    state.authenticated = true;
    return json(route, 200, ME);
  });
  await page.route("**/api/v1/auth/logout", (route) => {
    state.authenticated = false;
    state.logouts += 1;
    return route.fulfill({ status: 204 });
  });
  return state;
}

/** Theme is the stored choice of the app (dark by default), set before the first script runs. */
export const useTheme = (page: Page, theme: "light" | "dark") =>
  page.addInitScript((t) => localStorage.setItem("centrade-theme", t), theme);

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
