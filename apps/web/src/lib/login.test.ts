import { describe, expect, it, vi } from "vitest";

import { loginErrorMessage } from "@/i18n/fr";
import { submitLogin, submitTotp } from "./login";

const credentials = { username: "operateur", password: "motdepasse-secret" };

const respond = (status: number, body: string | null = '{"totp_required":true}', type = "application/json") =>
  vi.fn(async () => new Response(body, { status, headers: { "content-type": type } }));

describe("submitLogin (étape du mot de passe)", () => {
  it("poste les identifiants en JSON sur /api/v1/auth/login", async () => {
    const fetchImpl = respond(200);
    await submitLogin(credentials, fetchImpl);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/login");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(credentials);
  });

  it("passe à l'étape du code seulement si l'API répond totp_required", async () => {
    expect(await submitLogin(credentials, respond(200))).toEqual({ ok: true });
  });

  it("ne déclare pas de succès sur une 2xx sans totp_required (ni sur du HTML)", async () => {
    expect(await submitLogin(credentials, respond(200, "{}"))).toEqual({ ok: false, cause: "unexpected" });
    expect(await submitLogin(credentials, respond(204, null))).toEqual({ ok: false, cause: "unexpected" });
    expect(await submitLogin(credentials, respond(200, "<html></html>", "text/html"))).toEqual({
      ok: false,
      cause: "unexpected",
    });
  });

  it.each([
    [401, "refused"],
    [403, "refused"],
    [423, "locked"],
    [429, "rate-limited"],
  ] as const)("classe la réponse %i en %s", async (status, cause) => {
    expect(await submitLogin(credentials, respond(status, '{"title":"x"}', "application/problem+json"))).toEqual({
      ok: false,
      cause,
    });
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
    expect(JSON.stringify(await submitLogin(credentials, respond(401)))).not.toContain(credentials.password);
  });
});

describe("submitTotp (étape du code)", () => {
  it("poste le code sur /api/v1/auth/totp, espaces retirés", async () => {
    const fetchImpl = respond(200, '{"email":"a@b.test","role":"admin"}');
    expect(await submitTotp(" 123456 ", fetchImpl)).toEqual({ ok: true });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/totp");
    expect(JSON.parse(init.body as string)).toEqual({ code: "123456" });
  });

  it("accepte un 204", async () => {
    expect(await submitTotp("123456", respond(204, null))).toEqual({ ok: true });
  });

  it.each([
    [401, "refused"],
    [423, "locked"],
    [429, "rate-limited"],
  ] as const)("classe la réponse %i en %s", async (status, cause) => {
    expect(await submitTotp("000000", respond(status))).toEqual({ ok: false, cause });
  });
});

describe("messages d'erreur", () => {
  it("distinguent les deux étapes et disent quoi faire", () => {
    const refused = { ok: false, cause: "refused" } as const;
    expect(loginErrorMessage(refused, "password")).toMatch(/identifiant ou mot de passe/i);
    expect(loginErrorMessage(refused, "totp")).toMatch(/code/i);
    expect(loginErrorMessage({ ok: false, cause: "locked" }, "password")).toMatch(/verrouillé/i);
    expect(loginErrorMessage({ ok: false, cause: "rate-limited" }, "totp")).toMatch(/trop de tentatives/i);
  });
});
