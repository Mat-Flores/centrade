// Géométrie pure : bougies, trajets, zones et sélection. Aucun accès au canvas ni au DOM.
import type { Candle, ExitCause, Trade } from "../data/types";

export interface Pt { time: number; price: number }
export interface Rect { x1: number; x2: number; y1: number; y2: number }

/** Indice de la bougie qui contient `t` (dernière bougie commencée avant t), borné à [0, n-1]. */
export function candleIndexAt(candles: Candle[], t: number): number {
  let lo = 0, hi = candles.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (candles[mid].time <= t) lo = mid; else hi = mid - 1;
  }
  return lo;
}

/** Entrée -> sortie, puis les clôtures des bougies entre les deux ; position ouverte : jusqu'à la dernière bougie. */
export function pathPoints(candles: Candle[], tr: Trade): Pt[] {
  if (candles.length === 0) return [];
  const i0 = candleIndexAt(candles, tr.entryTime);
  const closed = tr.exitTime !== undefined && tr.exitPrice !== undefined;
  const i1 = closed ? candleIndexAt(candles, tr.exitTime as number) : candles.length - 1;
  const pts: Pt[] = [{ time: candles[i0].time, price: tr.entryPrice }];
  for (let i = i0 + 1; i < i1; i++) pts.push({ time: candles[i].time, price: candles[i].close });
  if (i1 > i0 || closed) pts.push({ time: candles[i1].time, price: closed ? (tr.exitPrice as number) : candles[i1].close });
  return pts;
}

/** Le trade touche-t-il la fenêtre de bougies affichée ? */
export function overlaps(candles: Candle[], tr: Trade): boolean {
  if (candles.length === 0) return false;
  return (tr.exitTime ?? Infinity) >= candles[0].time && tr.entryTime <= candles[candles.length - 1].time;
}

export function rectContains(r: Rect, x: number, y: number, pad = 0): boolean {
  return x >= Math.min(r.x1, r.x2) - pad && x <= Math.max(r.x1, r.x2) + pad && y >= Math.min(r.y1, r.y2) - pad && y <= Math.max(r.y1, r.y2) + pad;
}

/** Parmi les zones touchées, la plus petite : elle reste cliquable quand une grande la recouvre. */
export function pickRect<T extends { id: string; rect: Rect }>(items: T[], x: number, y: number, pad = 0): T | null {
  let best: T | null = null, bestArea = Infinity;
  for (const it of items) {
    if (!rectContains(it.rect, x, y, pad)) continue;
    const a = (Math.abs(it.rect.x2 - it.rect.x1) + 2 * pad) * (Math.abs(it.rect.y2 - it.rect.y1) + 2 * pad);
    if (a < bestArea) { best = it; bestArea = a; }
  }
  return best;
}

export const CAUSE_FR: Record<ExitCause, string> = {
  take_profit: "Take-profit", stop_loss: "Stop-loss", trailing_stop: "Stop suiveur", signal: "Signal de la stratégie",
  timeout: "Délai dépassé", manual: "Manuel", kill_switch: "Arrêt d'urgence", engine_protection: "Protection du bot", unknown: "Inconnue",
};
