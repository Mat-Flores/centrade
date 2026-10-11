import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { ApiError, apiFetch, setUnauthorizedHandler } from "./api";

const Me = z.object({ email: z.string(), role: z.enum(["viewer", "operator", "admin"]) });

const reply = (status: number, body: unknown, type = "application/json") =>
  vi.fn(async () => new Response(body === null ? null : JSON.stringify(body), { status, headers: { "content-type": type } }));

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  const error = await promise.then(
    () => null,
    (e: unknown) => e,
  );
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

afterEach(() => setUnauthorizedHandler(null));

describe("apiFetch", () => {
  it("appelle /api/v1 en same-origin et renvoie des données validées", async () => {
    const fetchImpl = reply(200, { email: "op@example.test", role: "operator" });
    const me = await apiFetch("/auth/me", Me, { fetchImpl });
    expect(me).toEqual({ email: "op@example.test", role: "operator" });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/me");
    expect(init.credentials).toBe("same-origin");
  });

  it("envoie le corps en JSON", async () => {
    const fetchImpl = reply(200, { ok: true });
    await apiFetch("/auth/totp", z.object({ ok: z.boolean() }), { method: "POST", body: { code: "123456" }, fetchImpl });
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ code: "123456" });
  });

  it("transforme un problème RFC 7807 en ApiError", async () => {
    const problem = { type: "about:blank", title: "Locked", status: 423, detail: "Compte verrouillé" };
    const error = await failure(apiFetch("/auth/login", Me, { fetchImpl: reply(423, problem, "application/problem+json") }));
    expect(error).toMatchObject({ kind: "problem", status: 423, message: "Locked" });
    expect(error.problem?.detail).toBe("Compte verrouillé");
  });

  it("transforme une erreur HTTP sans corps exploitable en ApiError", async () => {
    const fetchImpl = vi.fn(async () => new Response("<html>bad gateway</html>", { status: 502, headers: { "content-type": "text/html" } }));
    expect(await failure(apiFetch("/x", Me, { fetchImpl }))).toMatchObject({ kind: "problem", status: 502, problem: null });
  });

  it("signale 401 au gestionnaire de retour au login", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const error = await failure(apiFetch("/instances", Me, { fetchImpl: reply(401, { title: "Unauthorized", status: 401 }, "application/problem+json") }));
    expect(error.status).toBe(401);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("ne renvoie pas au login sur un 401 d'authentification (identifiants refusés)", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    await failure(apiFetch("/auth/login", Me, { authCall: true, fetchImpl: reply(401, null) }));
    expect(handler).not.toHaveBeenCalled();
  });

  it("signale une panne réseau", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    expect(await failure(apiFetch("/x", Me, { fetchImpl }))).toMatchObject({ kind: "network", status: null });
  });

  it("refuse une réponse hors contrat, y compris un rôle inconnu", async () => {
    const error = await failure(apiFetch("/auth/me", Me, { fetchImpl: reply(200, { email: "a@b.test", role: "root" }) }));
    expect(error.kind).toBe("invalid-response");
  });

  it("refuse une 2xx qui n'est pas du JSON", async () => {
    const fetchImpl = vi.fn(async () => new Response("<html></html>", { status: 200, headers: { "content-type": "text/html" } }));
    expect((await failure(apiFetch("/auth/me", Me, { fetchImpl }))).kind).toBe("invalid-response");
  });

  it("accepte un 204 quand le schéma l'admet", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 }));
    await expect(apiFetch("/auth/logout", z.undefined(), { method: "POST", fetchImpl })).resolves.toBeUndefined();
  });
});
