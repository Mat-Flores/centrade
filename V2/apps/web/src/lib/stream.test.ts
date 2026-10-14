import { afterEach, describe, expect, it, vi } from "vitest";

import { iso, makeAlert, makeCommand, makeInstance, without } from "@/test/factories";

import { meKey, queryClient } from "./session";
import { parseStreamMessage, shouldReconnect } from "./stream";

describe("parseStreamMessage", () => {
  it("returns the event with its payload when it matches the contract", () => {
    expect(parseStreamMessage("heartbeat", '{"server_time":"2026-10-10T18:32:05Z"}')).toEqual({
      event: "heartbeat",
      server_time: "2026-10-10T18:32:05Z",
    });
  });

  it("rejects a payload without server time", () => {
    expect(parseStreamMessage("trade", "{}")).toBeNull();
  });

  it("rejects content that is not JSON", () => {
    expect(parseStreamMessage("order", "<html></html>")).toBeNull();
  });
});

describe("parseStreamMessage with whole objects", () => {
  it("accepts an instance message that matches the contract", () => {
    const instance = makeInstance();
    const message = parseStreamMessage("instance", JSON.stringify({ server_time: iso(0), instance }));
    expect(message).toMatchObject({ event: "instance", instance: { id: "i-1" } });
  });

  it("rejects an instance message that is out of contract", () => {
    const broken = without(makeInstance(), "realized_pnl");
    expect(parseStreamMessage("instance", JSON.stringify({ server_time: iso(0), instance: broken }))).toBeNull();
  });

  it("accepts a command message and an alert message", () => {
    expect(parseStreamMessage("command", JSON.stringify({ server_time: iso(0), command: makeCommand() }))).not.toBeNull();
    expect(parseStreamMessage("alert", JSON.stringify({ server_time: iso(0), alert: makeAlert("a-1") }))).not.toBeNull();
  });
});

describe("shouldReconnect after the stream closed", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    queryClient.clear();
  });

  const answer = (status: number, body: unknown) =>
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "content-type": status === 200 ? "application/json" : "application/problem+json" } })),
    );

  it("ends the session and does not reconnect when the session expired (401 on /auth/me)", async () => {
    queryClient.setQueryData(meKey, { email: "op@example.test", role: "operator" });
    queryClient.setQueryData(["instances"], { items: [] });
    answer(401, { title: "Unauthorized", status: 401 });
    expect(await shouldReconnect()).toBe(false);
    expect(queryClient.getQueryData(meKey)).toBeNull();
    expect(queryClient.getQueryData(["instances"])).toBeUndefined();
  });

  it("reconnects and keeps the session when it is still valid", async () => {
    queryClient.setQueryData(meKey, { email: "op@example.test", role: "operator" });
    answer(200, { email: "op@example.test", role: "operator" });
    expect(await shouldReconnect()).toBe(true);
    expect(queryClient.getQueryData(meKey)).not.toBeNull();
  });

  it("reconnects without ending the session when the API is unreachable", async () => {
    queryClient.setQueryData(meKey, { email: "op@example.test", role: "operator" });
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    expect(await shouldReconnect()).toBe(true);
    expect(queryClient.getQueryData(meKey)).not.toBeNull();
  });
});
