import { describe, expect, it } from "vitest";

import type { LoginFailure } from "@/lib/login";

import { loginErrorMessage } from "./fr";

const steps = ["password", "totp"] as const;
const failures: LoginFailure[] = [
  { ok: false, cause: "refused" },
  { ok: false, cause: "locked" },
  { ok: false, cause: "rate-limited" },
  { ok: false, cause: "network" },
  { ok: false, cause: "unexpected" },
  { ok: false, cause: "http", status: 404 },
  { ok: false, cause: "http", status: 503 },
];

describe("loginErrorMessage", () => {
  it("tells the password step and the code step apart when the API refuses", () => {
    const refused = { ok: false, cause: "refused" } as const;
    expect(loginErrorMessage(refused, "password")).toMatch(/identifiant ou mot de passe/i);
    expect(loginErrorMessage(refused, "totp")).toMatch(/code refusé/i);
  });

  it.each(steps)("gives each cause its own message at the %s step", (step) => {
    const messages = failures.map((f) => loginErrorMessage(f, step));
    expect(new Set(messages).size).toBe(failures.length);
    messages.forEach((m) => expect(m).not.toBe(""));
  });

  it.each(steps)("tells a locked account from too many attempts at the %s step", (step) => {
    expect(loginErrorMessage({ ok: false, cause: "locked" }, step)).toMatch(/verrouillé/i);
    expect(loginErrorMessage({ ok: false, cause: "rate-limited" }, step)).toMatch(/trop de tentatives/i);
  });

  it.each(steps)("names the network as the cause when the API is unreachable at the %s step", (step) => {
    expect(loginErrorMessage({ ok: false, cause: "network" }, step)).toMatch(/injoignable/i);
  });

  it.each(steps)("says the response is not the login API when it is unexpected at the %s step", (step) => {
    expect(loginErrorMessage({ ok: false, cause: "unexpected" }, step)).toMatch(/pas celle de l'API/i);
  });

  it.each([404, 500, 503])("shows the HTTP status %i", (status) => {
    for (const step of steps) expect(loginErrorMessage({ ok: false, cause: "http", status }, step)).toContain(`HTTP ${status}`);
  });
});
