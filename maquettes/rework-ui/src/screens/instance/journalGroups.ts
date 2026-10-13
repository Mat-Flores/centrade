// Regroupement du journal : un groupe par trade (trié par achat, le plus ancien en haut), lignes isolées pour le reste.
import type { LogEntry, Trade } from "../../data/types";

export type JFilter = "tous" | "gain" | "perte" | "cours";
export type JItem =
  | { kind: "day"; id: string; label: string }
  | { kind: "trade"; id: string; time: number; trade: Trade; extra: LogEntry[] }
  | { kind: "line"; id: string; time: number; entry: LogEntry };
export interface Grouped { items: JItem[]; counts: Record<JFilter, number>; listed: number; total: number }

const TZ = "America/Toronto";
const key = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const label = new Intl.DateTimeFormat("fr-CA", { timeZone: TZ, day: "numeric", month: "short" });

export const tradeKind = (t: Trade): Exclude<JFilter, "tous"> => (t.exitTime === undefined ? "cours" : t.pnl > 0 ? "gain" : "perte");

/** `limit` : nombre maximal de trades gardés, les plus récents (défilement infini vers le haut). */
export function groupJournal(trades: Trade[], log: LogEntry[], filter: JFilter, limit = Infinity): Grouped {
  const byId = new Map(trades.map((t) => [t.id, t]));
  const extra = new Map<string, LogEntry[]>();
  const lines: LogEntry[] = [];
  for (const e of log) {
    const t = e.tradeId ? byId.get(e.tradeId) : undefined;
    if (!t) lines.push(e);
    else if (e.kind !== "achat" && e.kind !== "vente") extra.set(t.id, [...(extra.get(t.id) ?? []), e]); // achat et vente sont déjà dans le détail
  }
  const counts: Record<JFilter, number> = { tous: trades.length, gain: 0, perte: 0, cours: 0 };
  for (const t of trades) counts[tradeKind(t)]++;

  const all: (JItem & { time: number })[] = [
    ...trades.filter((t) => filter === "tous" || tradeKind(t) === filter).map((t) => ({ kind: "trade" as const, id: t.id, time: t.entryTime, trade: t, extra: extra.get(t.id) ?? [] })),
    ...(filter === "tous" ? lines.map((e) => ({ kind: "line" as const, id: e.id, time: e.time, entry: e })) : []),
  ].sort((a, b) => a.time - b.time);

  const total = all.filter((i) => i.kind === "trade").length;
  let start = 0, seen = 0;
  for (let i = all.length - 1; i >= 0; i--) {
    if (all[i].kind === "trade" && ++seen > limit) { start = i + 1; break; }
  }
  const items: JItem[] = [];
  let day = "";
  for (const it of all.slice(start)) {
    const d = new Date(it.time * 1000), k = key.format(d);
    if (k !== day) { day = k; items.push({ kind: "day", id: `day-${k}`, label: label.format(d) }); }
    items.push(it);
  }
  return { items, counts, listed: Math.min(total, limit), total };
}
