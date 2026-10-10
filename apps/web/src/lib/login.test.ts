import { describe, expect, it, vi } from "vitest";

import { submitLogin } from "./login";

const credentials = { username: "operateur", password: "motdepasse-secret" };

const respond = (status: number, body: string | null = "{}", type = "application/json") =>
  vi.fn(async () => new Response(body, { status, headers: { "content-type": type } }));

describe("submitLogin", () => {
  it("poste les identifiants en JSON sur /api/v1/auth/login", async () => {
    const fetchImpl = respond(200);
    await submitLogin(credentials, fetchImpl);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/login");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(credentials);
  });

  it("réussit seulement sur une réponse 2xx de l'API", async () => {
    expect(await submitLogin(credentials, respond(200))).toEqual({ ok: true });
    expect(await submitLogin(credentials, respond(204, null))).toEqual({ ok: true });
  });

  it("ne simule pas un succès quand une 2xx n'est pas une réponse JSON de l'API", async () => {
    const result = await submitLogin(credentials, respond(200, "<html></html>", "text/html"));
    expect(result).toEqual({ ok: false, cause: "unexpected" });
  });

  it.each([
    [401, "refused"],
    [403, "refused"],
    [429, "rate-limited"],
  ] as const)("classe la réponse %i en %s", async (status, cause) => {
    expect(await submitLogin(credentials, respond(status))).toEqual({ ok: false, cause });
  });

  it.each([404, 500, 503])("signale la réponse %i comme erreur HTTP avec son code", async (status) => {
    expect(await submitLogin(credentials, respond(status))).toEqual({ ok: false, cause: "http", status });
  });

  it("signale une erreur réseau, sans succès", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    expect(await submitLogin(credentials, fetchImpl)).toEqual({ ok: false, cause: "network" });
  });

  it("ne renvoie jamais le mot de passe dans le résultat", async () => {
    const result = await submitLogin(credentials, respond(401));
    expect(JSON.stringify(result)).not.toContain(credentials.password);
  });
});
