import { describe, expect, it } from "vitest";

import { fr } from "@/i18n/fr";

import { PRESETS, checkColors, contrast, deltaE, oklab, parseRoles, type ColorRoles } from "./colors";

const roles = (o: Partial<ColorRoles> = {}): ColorRoles => ({
  gain: "#2fbf71", loss: "#e5484d", action: "#4c8dff", candleUp: "#2fbf71", candleDown: "#e5484d",
  modeTest: "#f2b233", modeLive: "#e5484d", modeBacktest: "#a78bfa", ...o,
});

describe("oklab", () => {
  it("matches Ottosson's reference values for white, black and pure red", () => {
    const [L, a, b] = oklab("#ffffff");
    expect(L).toBeCloseTo(1, 3);
    expect(Math.abs(a) + Math.abs(b)).toBeLessThan(0.001);
    expect(oklab("#000000")[0]).toBeCloseTo(0, 5);
    const r = oklab("#ff0000");
    expect(r[0]).toBeCloseTo(0.628, 3);
    expect(r[1]).toBeCloseTo(0.2249, 3);
    expect(r[2]).toBeCloseTo(0.1258, 3);
  });
  it("gives a zero distance for the same color and a large one between black and white", () => {
    expect(deltaE("#336699", "#336699")).toBe(0);
    expect(deltaE("#000000", "#ffffff")).toBeCloseTo(100, 0);
  });
});

describe("WCAG contrast", () => {
  it("is 21:1 between black and white and 1:1 between identical colors", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#777777")).toBe(1);
  });
});

describe("checkColors", () => {
  it("warns only about live mode equal to loss for the reference set", () => {
    const w = checkColors(roles(), "#12161d");
    expect(w).toEqual([fr.colors.pairs.liveLoss]);
  });
  it("flags two close colors and a contrast that is too low", () => {
    const w = checkColors(roles({ gain: "#2fbf70", action: "#2fbf72", modeTest: "#14181f" }), "#12161d");
    expect(w.some((m) => m === fr.colors.pairs.gainLoss || m === fr.colors.pairs.gainAction)).toBe(true);
    expect(w.some((m) => m.startsWith(fr.colors.lowContrast(fr.colors.roles.modeTest, "").split(":")[0]!))).toBe(true);
  });
  it("passes the color blindness preset on both surfaces", () => {
    const preset = PRESETS.find((p) => p.id === "colorblind")!.roles!;
    // Only the roles the preset leaves to the theme (var(--...)) are resolved here; every other value is the preset's own.
    const resolve = (tokens: Record<string, string>): ColorRoles =>
      Object.fromEntries(Object.entries(preset).map(([k, v]) => [k, v.startsWith("var(") ? tokens[v]! : v])) as unknown as ColorRoles;
    const dark = resolve({ "var(--amber)": "#f2b233", "var(--violet)": "#a78bfa" });
    const light = resolve({ "var(--amber)": "#8a5c00", "var(--violet)": "#6d3fd1" });
    expect(dark.gain).toBe(preset.gain);
    expect(dark.modeLive).toBe(preset.modeLive);
    expect(checkColors(dark, "#12161d")).toEqual([]);
    expect(checkColors(light, "#fbfaf7")).toEqual([]);
  });
});

describe("parseRoles", () => {
  it("accepts hex colors and design tokens", () => {
    expect(parseRoles({ ...roles(), gain: "var(--bid)" })).not.toBeNull();
  });
  it("rejects a missing role and a value that is neither hex nor a token", () => {
    const missing: Partial<ColorRoles> = roles();
    delete missing.gain;
    expect(parseRoles(missing)).toBeNull();
    expect(parseRoles(roles({ gain: "url(https://example.com/x)" }))).toBeNull();
    expect(parseRoles("nope")).toBeNull();
  });
});
