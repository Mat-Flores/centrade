import { hashString, mulberry32 } from "../lib/prng";
import type { Candle, Strategy, Timeframe, Trade } from "./types";

export const BASE_STEP = 300;
export const EPOCH = Date.UTC(2026, 8, 12) / 1000;
export const SERIES_LENGTH = 8640; // 30 jours de bougies de 5 minutes
export const SERIES_END = EPOCH + (SERIES_LENGTH - 1) * BASE_STEP;

export const TF_SECONDS: Record<Timeframe, number> = { "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1j": 86400 };

const START_PRICE: Record<string, number> = {
  "BTC/USDT": 61000, "ETH/USDT": 2600, "SOL/USDT": 148, "ADA/USDT": 0.38,
  "XRP/USDT": 0.55, "BNB/USDT": 580, "DOGE/USDT": 0.11, "LINK/USDT": 11.5,
};
/** Volatilité par bougie de 5 min (écart type du rendement). */
const VOL: Record<string, number> = {
  "BTC/USDT": 0.0012, "ETH/USDT": 0.0015, "SOL/USDT": 0.0019, "ADA/USDT": 0.002,
  "XRP/USDT": 0.0018, "BNB/USDT": 0.0013, "DOGE/USDT": 0.0023, "LINK/USDT": 0.002,
};
export const PAIRS = Object.keys(START_PRICE);

function gauss(rng: () => number): number {
  return Math.sqrt(-2 * Math.log(1 - rng())) * Math.cos(2 * Math.PI * rng());
}

function roundPrice(p: number): number {
  return Number(p.toFixed(p >= 1000 ? 2 : p >= 1 ? 4 : 6));
}

function generate(pair: string): Candle[] {
  const rng = mulberry32(hashString(pair));
  const vol = VOL[pair];
  const out: Candle[] = [];
  let price = START_PRICE[pair];
  let left = 0;
  let drift = 0;
  let volMult = 1;
  let reversion = 0;
  let anchor = price;
  for (let i = 0; i < SERIES_LENGTH; i++) {
    if (left-- <= 0) {
      // Nouveau régime : tendance haussière, baissière ou range.
      left = 80 + Math.floor(rng() * 420);
      const kind = rng();
      drift = kind < 0.3 ? 0.05 : kind < 0.6 ? -0.05 : 0;
      drift *= vol * (0.5 + rng());
      reversion = drift === 0 ? 0.015 : 0;
      volMult = 0.7 + rng() * 0.7;
      anchor = price;
    }
    const r = drift + vol * volMult * gauss(rng) - reversion * Math.log(price / anchor);
    const open = price;
    const close = open * Math.exp(r);
    const wick = vol * volMult * 0.5;
    const high = Math.max(open, close) * (1 + Math.abs(gauss(rng)) * wick);
    const low = Math.min(open, close) * (1 - Math.abs(gauss(rng)) * wick);
    out.push({
      time: EPOCH + i * BASE_STEP,
      open: roundPrice(open), high: roundPrice(high), low: roundPrice(low), close: roundPrice(close),
    });
    price = close;
  }
  return out;
}

const series = new Map<string, Candle[]>();
export function candles5m(pair: string): Candle[] {
  if (!(pair in START_PRICE)) throw new Error(`Paire inconnue : ${pair}`);
  let s = series.get(pair);
  if (!s) series.set(pair, (s = generate(pair)));
  return s;
}

export function aggregate(c5: Candle[], tf: Timeframe): Candle[] {
  const step = TF_SECONDS[tf];
  const out: Candle[] = [];
  for (const c of c5) {
    const t = Math.floor(c.time / step) * step;
    const last = out[out.length - 1];
    if (last && last.time === t) {
      last.high = Math.max(last.high, c.high);
      last.low = Math.min(last.low, c.low);
      last.close = c.close;
    } else {
      out.push({ time: t, open: c.open, high: c.high, low: c.low, close: c.close });
    }
  }
  return out;
}

const aggCache = new Map<string, Candle[]>();
function fullSeries(pair: string, tf: Timeframe): Candle[] {
  const key = `${pair}|${tf}`;
  let a = aggCache.get(key);
  if (!a) aggCache.set(key, (a = aggregate(candles5m(pair), tf)));
  return a;
}

/** Nombre de bougies de 5 min dont l'ouverture est ≤ t. */
function revealed(t: number): number {
  return Math.min(SERIES_LENGTH, Math.max(0, Math.floor((t - EPOCH) / BASE_STEP) + 1));
}

/** Bougies visibles à `untilTime` ; la dernière peut être partielle. */
export function candlesFor(pair: string, tf: Timeframe, untilTime: number): Candle[] {
  const n = revealed(untilTime);
  const per = TF_SECONDS[tf] / BASE_STEP;
  const whole = Math.floor(n / per);
  const out = fullSeries(pair, tf).slice(0, whole);
  if (n % per) out.push(...aggregate(candles5m(pair).slice(whole * per, n), tf));
  return out;
}

/** Dernier prix connu à l'instant t. */
export function priceAt(pair: string, t: number): number {
  const s = candles5m(pair);
  return s[Math.max(0, revealed(t) - 1)].close;
}

function sma(values: number[], n: number): number[] {
  const out: number[] = [];
  let sum = 0;
  values.forEach((v, i) => {
    sum += v;
    if (i >= n) sum -= values[i - n];
    out.push(i >= n - 1 ? sum / n : NaN);
  });
  return out;
}

export interface SimInput {
  pair: string;
  strategy: Strategy;
  stakePerTrade: number;
  /** En pourcent, par côté (0.1 = 0,1 %). */
  feePct: number;
  slippagePct: number;
  from: number;
  to: number;
}

const TIMEOUT_CANDLES = 48;

// Matériel d'affichage : un croisement de moyennes banal, volontairement non optimisé.
export function simulateTrades(input: SimInput): Trade[] {
  const { pair, strategy, stakePerTrade, feePct, slippagePct, from, to } = input;
  const cs = fullSeries(pair, strategy.timeframe);
  const step = TF_SECONDS[strategy.timeframe];
  const closes = cs.map((c) => c.close);
  const fast = sma(closes, strategy.params.rapide ?? 9);
  const slow = sma(closes, strategy.params.lente ?? 21);
  const up = (i: number) => i > 0 && fast[i - 1] <= slow[i - 1] && fast[i] > slow[i];
  const down = (i: number) => i > 0 && fast[i - 1] >= slow[i - 1] && fast[i] < slow[i];
  const slip = slippagePct / 100;
  const trades: Trade[] = [];

  for (let i = 0; i < cs.length; ) {
    const entryTime = cs[i].time + step;
    if (!up(i) || entryTime < from) { i++; continue; }
    if (entryTime > to) break;
    const entryPrice = closes[i] * (1 + slip);
    const stopLoss = entryPrice * (1 - strategy.stopLossPct / 100);
    const takeProfit = entryPrice * (1 + strategy.takeProfitPct / 100);
    let exit: { j: number; price: number; cause: Trade["exitCause"] } | null = null;
    for (let j = i + 1; j < cs.length && !exit; j++) {
      const c = cs[j];
      if (c.low <= stopLoss) exit = { j, price: stopLoss * (1 - slip), cause: "stop_loss" };
      else if (c.high >= takeProfit) exit = { j, price: takeProfit * (1 - slip), cause: "take_profit" };
      else if (down(j)) exit = { j, price: c.close * (1 - slip), cause: "signal" };
      else if (j - i >= TIMEOUT_CANDLES) exit = { j, price: c.close * (1 - slip), cause: "timeout" };
    }
    if (!exit || cs[exit.j].time + step > to) break;
    const fees = stakePerTrade * (feePct / 100) * 2;
    const pnl = (stakePerTrade / entryPrice) * (exit.price - entryPrice) - fees;
    trades.push({
      id: `${pair}-${strategy.id}-${entryTime}`, pair, strategyId: strategy.id,
      entryTime, entryPrice, stake: stakePerTrade, stopLoss, takeProfit,
      exitTime: cs[exit.j].time + step, exitPrice: exit.price, exitCause: exit.cause,
      fees, pnl, pnlPct: (pnl / stakePerTrade) * 100,
    });
    i = exit.j + 1;
  }
  return trades;
}

/** Le trade tel qu'on le voit au curseur : caché, ouvert (résultat latent) ou terminé. */
export function viewTrade(trade: Trade, cursor: number, priceAtCursor: number): Trade | null {
  if (trade.entryTime > cursor) return null;
  if (trade.exitTime === undefined || trade.exitTime <= cursor) return trade;
  const { exitTime: _t, exitPrice: _p, exitCause: _c, ...open } = trade;
  const entryFee = trade.fees / 2;
  const pnl = (trade.stake / trade.entryPrice) * (priceAtCursor - trade.entryPrice) - entryFee;
  return { ...open, fees: entryFee, pnl, pnlPct: (pnl / trade.stake) * 100 };
}
