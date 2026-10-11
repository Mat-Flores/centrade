import { describe, expect, it } from "vitest";

import { screenAt } from "./router";

describe("screenAt", () => {
  it("reconnaît les écrans routés, avec ou sans barre finale", () => {
    expect(screenAt("/")).toBe("cockpit");
    expect(screenAt("/accounts")).toBe("accounts");
    expect(screenAt("/accounts/")).toBe("accounts");
    expect(screenAt("/orders")).toBe("orders");
    expect(screenAt("/strategies")).toBe("strategies");
  });
  it("refuse un chemin inconnu", () => {
    expect(screenAt("/nope")).toBeNull();
    expect(screenAt("/accounts/x")).toBeNull();
  });
});
