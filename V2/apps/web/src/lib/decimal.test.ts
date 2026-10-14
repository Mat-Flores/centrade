import { describe, expect, it } from "vitest";

import { shiftDecimal, signOf, sumDecimals } from "./decimal";

describe("exact decimals", () => {
  it("adds without float error", () => {
    expect(sumDecimals(["0.1", "0.2"])).toBe("0.3");
    expect(sumDecimals(["0.1", "0.2", "-0.30"])).toBe("0.00");
  });
  it("keeps the most precise scale and the sign of a loss", () => {
    expect(sumDecimals(["12.5", "-20.125"])).toBe("-7.625");
    expect(sumDecimals(["-0.0000000001", "0"])).toBe("-0.0000000001");
  });
  it("returns zero for an empty list", () => expect(sumDecimals([])).toBe("0"));
  it("rejects an unreadable amount", () => expect(() => sumDecimals(["1e5"])).toThrow(RangeError));
  it("shifts without rounding", () => {
    expect(shiftDecimal("-0.05", 2)).toBe("-5");
    expect(shiftDecimal("0.0123", 2)).toBe("1.23");
    expect(shiftDecimal("2", 2)).toBe("200");
  });
  it("returns the sign", () => {
    expect([signOf("-0.01"), signOf("0.00"), signOf("3")]).toEqual([-1, 0, 1]);
  });
});
