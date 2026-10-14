import { describe, expect, it, vi } from "vitest";

import { submitLogin, submitTotp } from "./login";

const credentials = { username: "operator", password: "secret-password" };

const respond = (status: number, body: string | null = '{"totp_required":true}', type = "application/json") =>
  vi.fn(async () => new Response(body, { status, headers: { "content-type": type } }));

describe("submitLogin (password step)", () => {
  it("posts the credentials as JSON to /api/v1/auth/login", async () => {
    const fetchImpl = respond(200);
    await submitLogin(credentials, fetchImpl);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/login");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(credentials);
  });

  it("moves to the code step only when the API answers totp_required", async () => {
    expect(await submitLogin(credentials, respond(200))).toEqual({ ok: true });
  });

  it("does not report success on a 2xx without totp_required (nor on HTML)", async () => {
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
  ] as const)("classifies the %i response as %s", async (status, cause) => {
    expect(await submitLogin(credentials, respond(status, '{"title":"x"}', "application/problem+json"))).toEqual({
      ok: false,
      cause,
    });
  });

  it.each([404, 500, 503])("reports the %i response as an HTTP error with its status", async (status) => {
    expect(await submitLogin(credentials, respond(status))).toEqual({ ok: false, cause: "http", status });
  });

  it("reports a network error, never a success", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    expect(await submitLogin(credentials, fetchImpl)).toEqual({ ok: false, cause: "network" });
  });

  it("never returns the password in the result", async () => {
    expect(JSON.stringify(await submitLogin(credentials, respond(401)))).not.toContain(credentials.password);
  });
});

describe("submitTotp (code step)", () => {
  it("posts the code to /api/v1/auth/totp with spaces trimmed", async () => {
    const fetchImpl = respond(200, '{"email":"a@b.test","role":"admin"}');
    expect(await submitTotp(" 123456 ", fetchImpl)).toEqual({ ok: true });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/totp");
    expect(JSON.parse(init.body as string)).toEqual({ code: "123456" });
  });

  it("accepts a 204", async () => {
    expect(await submitTotp("123456", respond(204, null))).toEqual({ ok: true });
  });

  it.each([
    [401, "refused"],
    [423, "locked"],
    [429, "rate-limited"],
  ] as const)("classifies the %i response as %s", async (status, cause) => {
    expect(await submitTotp("000000", respond(status))).toEqual({ ok: false, cause });
  });
});
