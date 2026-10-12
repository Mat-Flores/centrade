import { describe, expect, it } from "vitest";

import { pathWith, screenAt } from "./router";

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

describe("pathWith", () => {
  it("compose l'adresse d'un détail et omet les valeurs vides", () => {
    expect(pathWith("/strategies", { s: "abc", v: 2 })).toBe("/strategies?s=abc&v=2");
    expect(pathWith("/strategies", { s: "abc", v: null })).toBe("/strategies?s=abc");
    expect(pathWith("/strategies", {})).toBe("/strategies");
  });
});
