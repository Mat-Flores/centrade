import { describe, expect, it } from "vitest";
import { ftChecks, ftClassName, ftTemplate } from "./providers";

const ok = (code: string) => ftChecks(code).map((c) => c.ok);

describe("contrôles d'une stratégie Freqtrade", () => {
  it("le gabarit passe tous les contrôles", () => {
    expect(ok(ftTemplate("SmaCross"))).toEqual([true, true, true, true]);
    expect(ftClassName(ftTemplate("SmaCross"))).toBe("SmaCross");
  });
  it("refuse une classe qui n'hérite pas de la base", () => {
    expect(ok(ftTemplate("A").replace("(ControlPlaneStrategy)", "(IStrategy)"))[0]).toBe(false);
  });
  it("refuse un hook redéfini, un import réseau, un stop-loss dans le code", () => {
    const t = ftTemplate("A");
    expect(ok(`${t}\n    def confirm_trade_entry(self, **kw):\n        return True\n`)[1]).toBe(false);
    expect(ok(`import requests\n${t}`)[2]).toBe(false);
    expect(ok(`${t}\n    stoploss = -0.5\n`)[3]).toBe(false);
  });
  it("ignore les commentaires", () => {
    expect(ok(`${ftTemplate("A")}\n# import socket\n# stoploss = -1\n`)).toEqual([true, true, true, true]);
  });
});
