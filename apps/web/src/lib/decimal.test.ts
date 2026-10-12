import { describe, expect, it } from "vitest";

import { shiftDecimal, signOf, sumDecimals } from "./decimal";

describe("décimaux exacts", () => {
  it("additionne sans erreur de flottant", () => {
    expect(sumDecimals(["0.1", "0.2"])).toBe("0.3");
    expect(sumDecimals(["0.1", "0.2", "-0.30"])).toBe("0.00");
  });
  it("garde l'échelle la plus précise et le signe d'une perte", () => {
    expect(sumDecimals(["12.5", "-20.125"])).toBe("-7.625");
    expect(sumDecimals(["-0.0000000001", "0"])).toBe("-0.0000000001");
  });
  it("liste vide : zéro", () => expect(sumDecimals([])).toBe("0"));
  it("refuse un montant illisible", () => expect(() => sumDecimals(["1e5"])).toThrow(RangeError));
  it("décale sans arrondi", () => {
    expect(shiftDecimal("-0.05", 2)).toBe("-5");
    expect(shiftDecimal("0.0123", 2)).toBe("1.23");
    expect(shiftDecimal("2", 2)).toBe("200");
  });
  it("signe", () => {
    expect([signOf("-0.01"), signOf("0.00"), signOf("3")]).toEqual([-1, 0, 1]);
  });
});
