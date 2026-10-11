import { describe, expect, it } from "vitest";

import { formatAge, formatMoney, formatPnl, formatTimestamp, freshness } from "./format";

const SERVER = "2026-10-10T18:32:05Z";
const NBSP = /\u00a0/;

describe("formatAge", () => {
  it.each([
    [0, "à l'instant"],
    [-4_000, "à l'instant"], // horloge du moteur en avance : jamais d'âge négatif
    [3_000, "il y a 3 s"],
    [125_000, "il y a 2 min"],
    [3_900_000, "il y a 1 h 05 min"],
    [90_000_000, "il y a 1 j 1 h"],
  ])("formate %i ms en %s", (ms, text) => {
    expect(formatAge(ms)).toBe(text);
  });
});

describe("freshness", () => {
  const base = { serverTime: SERVER, staleAfterMs: 5_000 };

  it("est frais en deçà du seuil, seuil compris", () => {
    expect(freshness({ ...base, observedAt: "2026-10-10T18:32:02Z" })).toEqual({ state: "fresh", ageMs: 3_000 });
    expect(freshness({ ...base, observedAt: "2026-10-10T18:32:00Z" })).toEqual({ state: "fresh", ageMs: 5_000 });
  });

  it("est périmé au-delà du seuil, avec le temps écoulé depuis le dépassement", () => {
    expect(freshness({ ...base, observedAt: "2026-10-10T18:31:50Z" })).toEqual({
      state: "stale",
      ageMs: 15_000,
      staleForMs: 10_000,
    });
  });

  it.each([null, undefined, "", "pas une date"])("est inconnu quand l'horodatage vaut %j", (observedAt) => {
    expect(freshness({ ...base, observedAt })).toEqual({ state: "unknown" });
  });

  it("est inconnu quand l'heure du serveur est illisible", () => {
    expect(freshness({ observedAt: "2026-10-10T18:32:00Z", serverTime: "x", staleAfterMs: 5_000 })).toEqual({
      state: "unknown",
    });
  });
});

describe("formatTimestamp", () => {
  it("affiche l'heure de Toronto avec le fuseau, l'été comme l'hiver", () => {
    expect(formatTimestamp("2026-10-10T18:32:05Z")).toBe("2026-10-10 14 h 32 min 05 s HAE");
    expect(formatTimestamp("2026-01-10T18:32:05Z")).toBe("2026-01-10 13 h 32 min 05 s HNE");
  });
  it("refuse une date illisible plutôt que d'afficher une heure inventée", () => {
    expect(() => formatTimestamp("nope")).toThrow(RangeError);
  });
});

describe("formatPnl", () => {
  it("met un signe explicite et la devise", () => {
    expect(formatPnl("12.5", "USDT")).toMatch(/^\+12,5\s?USDT$/u);
    expect(formatPnl("-1234.50", "USDT")).toMatch(/^-1\s234,50\s?USDT$/u);
    expect(formatPnl("0.00", "CAD")).toMatch(/^\+0,00\s?CAD$/u);
  });
  it("garde toute la précision de la chaîne décimale, sans arrondi", () => {
    expect(formatPnl("-0.00000123", "BTC")).toMatch(/^-0,00000123\s?BTC$/u);
    expect(formatPnl("9007199254740993.01", "USD")).toMatch(/^\+9\s007\s199\s254\s740\s993,01\s?USD$/u);
  });
});

describe("formatMoney", () => {
  it("affiche toujours la devise, séparée par une espace insécable", () => {
    const text = formatMoney("1500.00", "USDT");
    expect(text).toMatch(/^1\s500,00\s?USDT$/u);
    expect(text).toMatch(NBSP);
  });
  it("refuse une devise absente", () => {
    expect(() => formatMoney("1.00", "")).toThrow();
  });
  it("refuse un nombre à virgule flottante ou une notation exponentielle", () => {
    expect(() => formatMoney("1e3", "USD")).toThrow(RangeError);
    expect(() => formatMoney("abc", "USD")).toThrow(RangeError);
  });
});
