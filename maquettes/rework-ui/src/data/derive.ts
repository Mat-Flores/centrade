import { computeStats } from "../lib/metrics";
import { hashString, mulberry32 } from "../lib/prng";
import { SERIES_END, candlesFor, priceAt, simulateTrades, viewTrade } from "./sim";
import type { State } from "./state";
import type { Candle, ExitCause, Instance, LogEntry, PairStats, Timeframe, Trade } from "./types";

/** Coûts supposés des instances en direct (test et réel). */
export const LIVE_FEE_PCT = 0.1;
export const LIVE_SLIPPAGE_PCT = 0.05;

export const CAUSE_LABEL: Record<ExitCause, string> = {
  take_profit: "Objectif atteint", stop_loss: "Stop", trailing_stop: "Stop suiveur", signal: "Signal de la stratégie",
  timeout: "Délai dépassé", manual: "Manuel", kill_switch: "Arrêt d'urgence", engine_protection: "Protection du bot", unknown: "Inconnue",
};

const REFUSAL_REASONS = ["perte du jour atteinte", "trop de positions ouvertes", "données de prix trop anciennes"];

// Cache par identité : l'état est immuable, donc une instance inchangée donne un résultat identique (et même référence).
const caches = new WeakMap<object, WeakMap<Instance, Map<string, unknown>>>();
function memo<T>(s: State, inst: Instance, key: string, fn: () => T): T {
  let byInst = caches.get(s.strategies);
  if (!byInst) caches.set(s.strategies, (byInst = new WeakMap()));
  let m = byInst.get(inst);
  if (!m) byInst.set(inst, (m = new Map()));
  const k = `${s.cursor}|${key}`;
  if (!m.has(k)) {
    if (m.size > 200) m.clear();
    m.set(k, fn());
  }
  return m.get(k) as T;
}

function findInstance(s: State, id: string): Instance {
  const inst = s.instances.find((i) => i.id === id);
  if (!inst) throw new Error(`Instance inconnue : ${id}`);
  return inst;
}

/** Fenêtre de simulation et instant de vue ; null = rien à montrer (jamais démarrée, backtest non terminé). */
function tradeWindow(s: State, inst: Instance): { from: number; to: number; view: number } | null {
  if (inst.mode === "backtest") {
    const b = inst.backtest;
    if (!b || b.run.status !== "termine") return null;
    return { from: b.from, to: b.to, view: b.playhead ?? b.to };
  }
  if (inst.startedAt === null) return null;
  return { from: inst.startedAt, to: SERIES_END, view: s.cursor };
}

/** Instant jusqu'où l'on montre les bougies. */
function viewTime(s: State, inst: Instance): number {
  return inst.mode === "backtest" && inst.backtest ? (inst.backtest.playhead ?? inst.backtest.to) : s.cursor;
}

const rawCache = new Map<string, Trade[]>();
function rawTrades(input: Parameters<typeof simulateTrades>[0]): Trade[] {
  const key = JSON.stringify(input);
  let t = rawCache.get(key);
  if (!t) {
    if (rawCache.size > 300) rawCache.clear();
    rawCache.set(key, (t = simulateTrades(input)));
  }
  return t;
}

function inPause(inst: Instance, t: number): boolean {
  return inst.entryPauses.some((p) => t >= p.from && (p.to === null || t < p.to));
}

/** Applique une fermeture à la main ou une position laissée ouverte sans bot. */
function override(inst: Instance, t: Trade): Trade {
  const m = inst.manualExits[t.id];
  if (m === undefined) return t;
  if (m === null) return { ...t, exitTime: Number.POSITIVE_INFINITY };
  if (t.exitTime === undefined || t.exitTime <= m.time) return t;
  const pnl = (t.stake / t.entryPrice) * (m.price - t.entryPrice) - t.fees;
  return { ...t, exitTime: m.time, exitPrice: m.price, exitCause: "manual", pnl, pnlPct: (pnl / t.stake) * 100 };
}

function pairTrades(s: State, inst: Instance, pair: string, w: { from: number; to: number; view: number }): Trade[] {
  const pc = inst.pairs.find((p) => p.pair === pair);
  const strategy = s.strategies.find((x) => x.id === pc?.strategyId);
  if (!pc || !strategy) return [];
  const bt = inst.mode === "backtest" ? inst.backtest : undefined;
  const raw = rawTrades({
    pair, strategy, stakePerTrade: inst.startBalance / (inst.pairs.length * 2),
    feePct: bt?.feePct ?? LIVE_FEE_PCT, slippagePct: bt?.slippagePct ?? LIVE_SLIPPAGE_PCT, from: w.from, to: w.to,
  });
  const px = priceAt(pair, w.view);
  return raw
    .filter((t) => !inPause(inst, t.entryTime))
    .map((t) => viewTrade(override(inst, t), w.view, px))
    .filter((t): t is Trade => t !== null);
}

export function selectCandles(s: State, instanceId: string, pair: string, tf: Timeframe): Candle[] {
  const inst = findInstance(s, instanceId);
  return memo(s, inst, `c|${pair}|${tf}|${viewTime(s, inst)}`, () => candlesFor(pair, tf, viewTime(s, inst)));
}

export function selectTrades(s: State, instanceId: string, pair?: string): Trade[] {
  const inst = findInstance(s, instanceId);
  return memo(s, inst, `t|${pair ?? ""}`, () => {
    const w = tradeWindow(s, inst);
    if (!w) return [];
    const pairs = pair ? [pair] : inst.pairs.map((p) => p.pair);
    return pairs.flatMap((p) => pairTrades(s, inst, p, w)).sort((a, b) => a.entryTime - b.entryTime);
  });
}

/** Heures des achats refusés : fonction de l'instance seule, pas du curseur. */
function refusals(inst: Instance, pair: string, until: number): number[] {
  if (inst.mode === "backtest" || inst.startedAt === null) return [];
  const rng = mulberry32(hashString(`${inst.id}|${pair}`));
  const out: number[] = [];
  for (let t = inst.startedAt + 8 * 3600 + rng() * 22 * 3600; t <= until; t += 8 * 3600 + rng() * 22 * 3600) out.push(Math.floor(t));
  return out;
}

export function selectLog(s: State, instanceId: string, pair?: string): LogEntry[] {
  const inst = findInstance(s, instanceId);
  return memo(s, inst, `l|${pair ?? ""}`, () => {
    const entries: LogEntry[] = [];
    for (const t of selectTrades(s, instanceId, pair)) {
      entries.push({ id: `${t.id}-achat`, time: t.entryTime, kind: "achat", pair: t.pair, text: `Achat ${t.pair}`, amount: t.entryPrice, tradeId: t.id });
      if (t.exitTime !== undefined && t.exitCause) {
        const label = CAUSE_LABEL[t.exitCause];
        entries.push({
          id: `${t.id}-vente`, time: t.exitTime, kind: "vente", pair: t.pair,
          text: `Vente ${t.pair}, ${label[0].toLowerCase()}${label.slice(1)}`, amount: t.pnl, tradeId: t.id,
        });
      }
    }
    for (const p of pair ? [pair] : inst.pairs.map((x) => x.pair)) {
      refusals(inst, p, s.cursor).forEach((time, i) => {
        const why = REFUSAL_REASONS[(hashString(p) + i) % REFUSAL_REASONS.length];
        entries.push({ id: `refus-${p}-${time}`, time, kind: "achat_refuse", pair: p, text: `Achat refusé ${p}, protection : ${why}` });
      });
    }
    if (!pair) entries.push(...inst.events.filter((e) => e.time <= s.cursor));
    return entries.sort((a, b) => a.time - b.time);
  });
}

/** ~150 points au plus, pas multiple d'une heure. */
function sampleTimes(start: number, end: number): number[] {
  if (end <= start) return [end];
  const step = Math.max(3600, Math.ceil((end - start) / 150 / 3600) * 3600);
  const times: number[] = [];
  for (let t = start; t < end; t += step) times.push(t);
  return [...times, end];
}

export function selectStats(s: State, instanceId: string, pair?: string): PairStats {
  const inst = findInstance(s, instanceId);
  return memo(s, inst, `s|${pair ?? ""}`, () => {
    const w = tradeWindow(s, inst);
    const view = w?.view ?? viewTime(s, inst);
    const startBalance = pair ? inst.startBalance / Math.max(1, inst.pairs.length) : inst.startBalance;
    const refused = (pair ? [pair] : inst.pairs.map((p) => p.pair)).reduce((n, p) => n + refusals(inst, p, view).length, 0);
    return computeStats(selectTrades(s, instanceId, pair), startBalance, sampleTimes(w?.from ?? view, view), priceAt, refused);
  });
}
