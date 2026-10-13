import { describe, expect, it } from "vitest";
import type { LogEntry, Trade } from "../../data/types";
import { groupJournal } from "./journalGroups";

const D = 86400, T0 = Date.UTC(2025, 9, 4, 16) / 1000; // 4 oct. 12 h à Toronto
const tr = (id: string, entry: number, pnl: number, open = false): Trade => ({
  id, pair: "BTC/USDT", strategyId: "s", entryTime: entry, entryPrice: 100, stake: 100, stopLoss: 98, takeProfit: 104, fees: 0.2, pnl, pnlPct: pnl,
  ...(open ? {} : { exitTime: entry + 600, exitPrice: 101, exitCause: "take_profit" as const }),
});
const trades = [tr("c", T0 + D, -1), tr("a", T0, 2), tr("b", T0 + 100, 0.5), tr("o", T0 + D + 50, 1, true)];
const log: LogEntry[] = [
  { id: "a-achat", time: T0, kind: "achat", tradeId: "a", text: "Achat" },
  { id: "r", time: T0 + 10, kind: "achat_refuse", text: "Achat refusé" },
  { id: "al", time: T0 + 2 * D, kind: "alerte", text: "Alerte" },
  { id: "note", time: T0 + 5, kind: "commande", tradeId: "a", text: "Ordre" },
];

describe("groupJournal", () => {
  it("trie par achat, le plus ancien en haut, et place les lignes isolées à leur heure", () => {
    const ids = groupJournal(trades, log, "tous").items.filter((i) => i.kind !== "day").map((i) => i.id);
    expect(ids).toEqual(["a", "r", "b", "c", "o", "al"]);
  });
  it("filtre gain, perte, en cours ; les lignes isolées restent sous « Tous »", () => {
    const f = (k: "gain" | "perte" | "cours") => groupJournal(trades, log, k).items.filter((i) => i.kind !== "day").map((i) => i.id);
    expect(f("gain")).toEqual(["a", "b"]);
    expect(f("perte")).toEqual(["c"]);
    expect(f("cours")).toEqual(["o"]);
    expect(groupJournal(trades, log, "perte").counts).toEqual({ tous: 4, gain: 2, perte: 1, cours: 1 });
  });
  it("insère un séparateur à chaque changement de jour de Toronto", () => {
    const g = groupJournal(trades, log, "tous");
    expect(g.items.filter((i) => i.kind === "day")).toHaveLength(3);
    expect(g.items[0].kind).toBe("day");
  });
  it("garde les entrées d'un trade dans son groupe, sans doubler l'achat et la vente", () => {
    const a = groupJournal(trades, log, "tous").items.find((i) => i.id === "a");
    expect(a && a.kind === "trade" && a.extra.map((e) => e.id)).toEqual(["note"]);
  });
  it("limite aux trades les plus récents", () => {
    const g = groupJournal(trades, log, "tous", 2);
    expect(g.items.filter((i) => i.kind === "trade").map((i) => i.id)).toEqual(["c", "o"]);
    expect(g.total).toBe(4);
  });
});
