import { describe, expect, it } from "vitest";

import { keyFor } from "./useSendAction";

describe("keyFor: one idempotency key per (instance, action)", () => {
  it("replays the key of the same instance and action", () => {
    const first = keyFor(null, "i-a", "flatten");
    expect(keyFor(first, "i-a", "flatten")).toBe(first);
  });

  it("never replays a key to another instance (the server would refuse it: 422)", () => {
    const first = keyFor(null, "i-a", "flatten");
    const second = keyFor(first, "i-b", "flatten");
    expect(second.value).not.toBe(first.value);
  });

  it("gives another action its own key", () => {
    const first = keyFor(null, "i-a", "flatten");
    expect(keyFor(first, "i-a", "stop").value).not.toBe(first.value);
  });
});
