import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type Route } from "@playwright/test";

export const ME = { email: "operateur@example.test", role: "operator" };

const json = (route: Route, status: number, body: unknown, type = "application/json") =>
  route.fulfill({ status, contentType: type, body: JSON.stringify(body) });

export const problem = (route: Route, status: number, title: string) =>
  json(route, status, { type: "about:blank", title, status }, "application/problem+json");

/** Simule l'API d'authentification ; `state.authenticated` bascule quand le code est accepté. */
export async function mockAuth(page: Page, opts: { authenticated?: boolean; codeStatus?: number } = {}) {
  const state = { authenticated: opts.authenticated ?? false, logouts: 0 };
  await page.route("**/api/v1/auth/me", (route) =>
    state.authenticated ? json(route, 200, ME) : problem(route, 401, "Unauthorized"),
  );
  await page.route("**/api/v1/auth/login", (route) => json(route, 200, { totp_required: true }));
  await page.route("**/api/v1/auth/totp", (route) => {
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

export async function expectNoViolation(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

/** L'élément est entièrement dans le champ visible de sa zone défilable et de la fenêtre : rien n'est caché à droite. */
export async function expectInView(locator: import("@playwright/test").Locator) {
  const ok = await locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const region = el.closest('[role="region"]')?.getBoundingClientRect();
    const right = Math.min(window.innerWidth, region?.right ?? Infinity);
    return r.width > 0 && r.left >= (region?.left ?? 0) - 1 && r.right <= right + 1;
  });
  expect(ok, "élément hors du champ visible").toBe(true);
}
