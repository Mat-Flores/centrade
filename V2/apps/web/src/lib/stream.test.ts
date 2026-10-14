import { describe, expect, it } from "vitest";

import { parseStreamMessage } from "./stream";

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
