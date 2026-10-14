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
  it("calls /api/v1 same-origin and returns validated data", async () => {
    const fetchImpl = reply(200, { email: "op@example.test", role: "operator" });
    const me = await apiFetch("/auth/me", Me, { fetchImpl });
    expect(me).toEqual({ email: "op@example.test", role: "operator" });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/me");
    expect(init.credentials).toBe("same-origin");
  });

  it("sends the body as JSON", async () => {
    const fetchImpl = reply(200, { ok: true });
    await apiFetch("/auth/totp", z.object({ ok: z.boolean() }), { method: "POST", body: { code: "123456" }, fetchImpl });
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ code: "123456" });
  });

  it("turns an RFC 7807 problem into an ApiError", async () => {
    const problem = { type: "about:blank", title: "Locked", status: 423, detail: "Account locked" };
    const error = await failure(apiFetch("/auth/login", Me, { fetchImpl: reply(423, problem, "application/problem+json") }));
    expect(error).toMatchObject({ kind: "problem", status: 423, message: "Locked" });
    expect(error.problem?.detail).toBe("Account locked");
  });

  it("turns an HTTP error without a usable body into an ApiError", async () => {
    const fetchImpl = vi.fn(async () => new Response("<html>bad gateway</html>", { status: 502, headers: { "content-type": "text/html" } }));
    expect(await failure(apiFetch("/x", Me, { fetchImpl }))).toMatchObject({ kind: "problem", status: 502, problem: null });
  });

  it("reports a 401 to the return-to-login handler", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const error = await failure(apiFetch("/instances", Me, { fetchImpl: reply(401, { title: "Unauthorized", status: 401 }, "application/problem+json") }));
    expect(error.status).toBe(401);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not return to login on an authentication 401 (credentials refused)", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    await failure(apiFetch("/auth/login", Me, { authCall: true, fetchImpl: reply(401, null) }));
    expect(handler).not.toHaveBeenCalled();
  });

  it("reports a network outage", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    expect(await failure(apiFetch("/x", Me, { fetchImpl }))).toMatchObject({ kind: "network", status: null });
  });

  it("rejects a response outside the contract, including an unknown role", async () => {
    const error = await failure(apiFetch("/auth/me", Me, { fetchImpl: reply(200, { email: "a@b.test", role: "root" }) }));
    expect(error.kind).toBe("invalid-response");
  });

  it("rejects a 2xx that is not JSON", async () => {
    const fetchImpl = vi.fn(async () => new Response("<html></html>", { status: 200, headers: { "content-type": "text/html" } }));
    expect((await failure(apiFetch("/auth/me", Me, { fetchImpl }))).kind).toBe("invalid-response");
  });

  it("accepts a 204 when the schema allows it", async () => {
    const fetchImpl = vi.fn(async () => new Response(null, { status: 204 }));
    await expect(apiFetch("/auth/logout", z.undefined(), { method: "POST", fetchImpl })).resolves.toBeUndefined();
  });
});
