import { describe, expect, it } from "vitest";

import {
  dayOffset,
  formatAge,
  formatClock,
  formatDateTime,
  formatDecimalText,
  formatDuration,
  formatMoney,
  formatPnl,
  formatTimeframe,
  formatTimestamp,
  freshness,
} from "./format";

const SERVER = "2026-10-10T18:32:05Z";
const NBSP = /\u00a0/;

describe("formatAge", () => {
  it.each([
    [0, "à l'instant"],
    [-4_000, "à l'instant"], // engine clock ahead: never a negative age
    [3_000, "il y a 3 s"],
    [125_000, "il y a 2 min"],
    [3_900_000, "il y a 1 h 05 min"],
    [90_000_000, "il y a 1 j 1 h"],
  ])("formats %i ms as %s", (ms, text) => {
    expect(formatAge(ms)).toBe(text);
  });
});

describe("freshness", () => {
  const base = { serverTime: SERVER, staleAfterMs: 5_000 };

  it("is fresh up to the threshold, threshold included", () => {
    expect(freshness({ ...base, observedAt: "2026-10-10T18:32:02Z" })).toEqual({ state: "fresh", ageMs: 3_000 });
    expect(freshness({ ...base, observedAt: "2026-10-10T18:32:00Z" })).toEqual({ state: "fresh", ageMs: 5_000 });
  });

  it("is stale beyond the threshold, with the time elapsed since the crossing", () => {
    expect(freshness({ ...base, observedAt: "2026-10-10T18:31:50Z" })).toEqual({
      state: "stale",
      ageMs: 15_000,
      staleForMs: 10_000,
    });
  });

  it.each([null, undefined, "", "pas une date"])("is unknown when the timestamp is %j", (observedAt) => {
    expect(freshness({ ...base, observedAt })).toEqual({ state: "unknown" });
  });

  it("is unknown when the server time is unreadable", () => {
    expect(freshness({ observedAt: "2026-10-10T18:32:00Z", serverTime: "x", staleAfterMs: 5_000 })).toEqual({
      state: "unknown",
    });
  });
});

describe("formatTimestamp", () => {
  it("shows Toronto time with the zone, in summer and in winter", () => {
    expect(formatTimestamp("2026-10-10T18:32:05Z")).toBe("2026-10-10 14 h 32 min 05 s HAE");
    expect(formatTimestamp("2026-01-10T18:32:05Z")).toBe("2026-01-10 13 h 32 min 05 s HNE");
  });
  it("rejects an unreadable date instead of showing an invented time", () => {
    expect(() => formatTimestamp("nope")).toThrow(RangeError);
  });
});

describe("formatPnl", () => {
  it("puts an explicit sign and the currency", () => {
    expect(formatPnl("12.5", "USDT")).toMatch(/^\+12,5\s?USDT$/u);
    expect(formatPnl("-1234.50", "USDT")).toMatch(/^-1\s234,50\s?USDT$/u);
    expect(formatPnl("0.00", "CAD")).toMatch(/^\+0,00\s?CAD$/u);
  });
  it("keeps the full precision of the decimal string, without rounding", () => {
    expect(formatPnl("-0.00000123", "BTC")).toMatch(/^-0,00000123\s?BTC$/u);
    expect(formatPnl("9007199254740993.01", "USD")).toMatch(/^\+9\s007\s199\s254\s740\s993,01\s?USD$/u);
  });
});

describe("formatMoney", () => {
  it("always shows the currency, separated by a non-breaking space", () => {
    const text = formatMoney("1500.00", "USDT");
    expect(text).toMatch(/^1\s500,00\s?USDT$/u);
    expect(text).toMatch(NBSP);
  });
  it("rejects a missing currency", () => {
    expect(() => formatMoney("1.00", "")).toThrow();
  });
  it("rejects a floating-point number or exponent notation", () => {
    expect(() => formatMoney("1e3", "USD")).toThrow(RangeError);
    expect(() => formatMoney("abc", "USD")).toThrow(RangeError);
  });
});

const sp = (text: string) => text.replace(/\s/g, " "); // the fr-CA thousands separator is non-breaking

describe("formatDecimalText", () => {
  it("keeps every decimal and never goes through a float", () => {
    expect(formatDecimalText("0.1000000000000000055511151231257827")).toBe("0,1000000000000000055511151231257827");
    expect(sp(formatDecimalText("60000.50"))).toBe("60 000,50");
    expect(sp(formatDecimalText("12345678901234567890.123456789"))).toBe("12 345 678 901 234 567 890,123456789");
  });
  it("keeps a loss visible: sign kept, no decimal rounded to zero", () => {
    expect(formatDecimalText("-0.00000001", true)).toMatch(/^[-−]0,00000001$/);
    expect(formatDecimalText("5.0001", true)).toBe("+5,0001");
    expect(formatPnl("-0.00000001", "USDT")).toMatch(/^[-−]0,00000001\u00a0USDT$/);
  });
  it("rejects a text that is not a decimal", () => {
    expect(() => formatDecimalText("1e5")).toThrow(RangeError);
  });
});

describe("formatDuration", () => {
  it("shortens to days, hours and minutes", () => {
    expect(formatDuration(3 * 86400 + 4 * 3600 + 12 * 60)).toBe("3 j 4 h 12 min");
    expect(formatDuration(720)).toBe("12 min");
    expect(formatDuration(3600)).toBe("1 h 0 min");
  });
  it("keeps seconds under a minute and never goes negative", () => {
    expect(formatDuration(45)).toBe("45 s");
    expect(formatDuration(-5)).toBe("0 s");
  });
});

describe("Toronto clock helpers", () => {
  const t = Date.UTC(2026, 9, 12, 21, 42) / 1000; // 17:42 in Toronto (UTC-4 in October)
  it("formats the time of day and the short date", () => {
    expect(formatClock(t)).toBe("17:42");
    expect(formatDateTime(t)).toBe("12 oct. 17:42");
  });
  it("counts calendar days in Toronto, not elapsed hours", () => {
    const late = Date.UTC(2026, 9, 13, 3, 50) / 1000; // 23:50 on the 12th in Toronto
    expect(dayOffset(late, late + 300)).toBe(0);
    expect(dayOffset(late, late + 1200)).toBe(1);
    expect(dayOffset(late, late + 86400 + 1200)).toBe(2);
  });
});

describe("formatTimeframe", () => {
  it("labels each timeframe", () => {
    expect((["5m", "15m", "1h", "4h", "1d"] as const).map(formatTimeframe)).toEqual(["5 min", "15 min", "1 h", "4 h", "1 j"]);
  });
});
