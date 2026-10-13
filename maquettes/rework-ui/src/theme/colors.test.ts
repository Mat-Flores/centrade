import { describe, expect, it } from "vitest";
import type { ColorRoles } from "../data/types";
import { PRESETS, checkColors, contrast, deltaE, oklab } from "./colors";

const roles = (o: Partial<ColorRoles> = {}): ColorRoles => ({
  gain: "#2fbf71", perte: "#e5484d", action: "#4c8dff", bougieHausse: "#2fbf71", bougieBaisse: "#e5484d",
  modeTest: "#f2b233", modeReel: "#e5484d", modeBacktest: "#a78bfa", ...o,
});

describe("oklab", () => {
  it("blanc, noir et rouge pur (valeurs de référence d'Ottosson)", () => {
    const [L, a, b] = oklab("#ffffff");
    expect(L).toBeCloseTo(1, 3);
    expect(Math.abs(a) + Math.abs(b)).toBeLessThan(0.001);
    expect(oklab("#000000")[0]).toBeCloseTo(0, 5);
    const r = oklab("#ff0000");
    expect(r[0]).toBeCloseTo(0.628, 3);
    expect(r[1]).toBeCloseTo(0.2249, 3);
    expect(r[2]).toBeCloseTo(0.1258, 3);
  });
  it("deltaE : nul pour la même couleur, grand entre noir et blanc", () => {
    expect(deltaE("#336699", "#336699")).toBe(0);
    expect(deltaE("#000000", "#ffffff")).toBeCloseTo(100, 0);
  });
});

describe("contraste WCAG", () => {
  it("21:1 entre noir et blanc, 1:1 entre identiques", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#777777")).toBe(1);
  });
});

describe("checkColors", () => {
  it("le jeu de référence ne se plaint que de mode réel = perte", () => {
    const w = checkColors(roles(), "#12161d");
    expect(w).toHaveLength(1);
    expect(w[0]).toMatch(/Mode réel et perte/);
  });
  it("signale deux couleurs proches et un contraste trop faible", () => {
    const w = checkColors(roles({ gain: "#2fbf70", action: "#2fbf72", modeTest: "#14181f" }), "#12161d");
    expect(w.some((m) => m.startsWith("Gain et perte") || m.startsWith("Gain et achats"))).toBe(true);
    expect(w.some((m) => m.startsWith("Mode test : contraste"))).toBe(true);
  });
  it("le jeu daltonisme passe sur les deux surfaces", () => {
    const r = PRESETS[1].roles!;
    const hex = { ...r, bougieHausse: r.gain, bougieBaisse: r.perte, modeTest: "#f2b233", modeBacktest: "#a78bfa" };
    expect(checkColors(hex, "#12161d")).toEqual([]);
    expect(checkColors({ ...hex, modeTest: "#8a5c00", modeBacktest: "#6d3fd1" }, "#fbfaf7")).toEqual([]);
  });
});
