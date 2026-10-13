import { describe, expect, it } from "vitest";
import { age, clock, dateTime, duration, money, price, signedMoney, signedPct, tfLabel } from "./format";

const NB = " ";
describe("format", () => {
  it("money: deux décimales, espace insécable", () => {
    expect(money(2000, "USDT")).toBe(`2${NB}000,00 USDT`);
  });
  it("price: décimales selon l'ordre de grandeur", () => {
    expect(price(61234.5)).toBe(`61${NB}234,50`);
    expect(price(148.1234)).toBe("148,1234");
    expect(price(148)).toBe("148,00");
    expect(price(0.38)).toBe("0,3800");
    expect(price(0.11234)).toBe("0,11234");
  });
  it("signedMoney: signe réel, zéro sans signe", () => {
    expect(signedMoney(41.06, "USDT")).toBe("+41,06 USDT");
    expect(signedMoney(-12.4, "USDT")).toBe("−12,40 USDT");
    expect(signedMoney(0, "USDT")).toBe("0,00 USDT");
    expect(signedMoney(0.001, "USDT")).toBe("0,00 USDT");
  });
  it("signedPct", () => {
    expect(signedPct(3.2)).toBe(`+3,20${NB}%`);
    expect(signedPct(-0.8)).toBe(`−0,80${NB}%`);
    expect(signedPct(0)).toBe(`0,00${NB}%`);
  });
  it("duration", () => {
    expect(duration(3 * 86400 + 4 * 3600 + 12 * 60)).toBe("3 j 4 h 12 min");
    expect(duration(720)).toBe("12 min");
    expect(duration(45)).toBe("45 s");
    expect(duration(3600)).toBe("1 h 0 min");
  });
  it("age", () => {
    expect(age(2)).toBe("il y a 2 s");
    expect(age(190)).toBe("il y a 3 min");
  });
  it("clock et dateTime à Toronto (UTC-4 en octobre)", () => {
    const t = Date.UTC(2026, 9, 12, 21, 42) / 1000;
    expect(clock(t)).toBe("17:42");
    expect(dateTime(t)).toBe("12 oct. 17:42");
  });
  it("tfLabel", () => {
    expect(["5m", "15m", "1h", "4h", "1j"].map((t) => tfLabel(t as never))).toEqual(["5 min", "15 min", "1 h", "4 h", "1 j"]);
  });
});
