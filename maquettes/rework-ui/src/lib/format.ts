import type { Timeframe } from "../data/types";

const TZ = "America/Toronto";
const MINUS = "−";

function num(n: number, min: number, max: number): string {
  return new Intl.NumberFormat("fr-CA", { minimumFractionDigits: min, maximumFractionDigits: max }).format(n);
}

export function money(n: number, currency: string): string {
  return `${num(n, 2, 2)} ${currency}`;
}

/** Prix d'instrument : plus il est petit, plus on garde de décimales. */
export function price(n: number): string {
  const a = Math.abs(n);
  if (a >= 1000) return num(n, 2, 2);
  if (a >= 1) return num(n, 2, 4);
  return num(n, 4, 5);
}

function signed(n: number, body: (abs: number) => string): string {
  // Un résultat qui s'arrondit à zéro (2 décimales) s'affiche sans signe.
  if (Math.round(Math.abs(n) * 100) === 0) return body(0);
  return `${n > 0 ? "+" : MINUS}${body(Math.abs(n))}`;
}

export function signedMoney(n: number, currency: string): string {
  return signed(n, (a) => money(a, currency));
}

export function signedPct(n: number): string {
  return signed(n, (a) => `${num(a, 2, 2)} %`);
}

export function duration(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  if (s < 60) return `${s} s`;
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return [d && `${d} j`, (d || h) && `${h} h`, `${m} min`].filter(Boolean).join(" ");
}

export function age(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  if (s < 60) return `il y a ${s} s`;
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return `il y a ${Math.floor(s / 86400)} j`;
}

function parts(t: number, opts: Intl.DateTimeFormatOptions): Record<string, string> {
  const f = new Intl.DateTimeFormat("fr-CA", { timeZone: TZ, hourCycle: "h23", ...opts });
  return Object.fromEntries(f.formatToParts(new Date(t * 1000)).map((p) => [p.type, p.value]));
}

export function clock(t: number): string {
  const p = parts(t, { hour: "2-digit", minute: "2-digit" });
  return `${p.hour}:${p.minute}`;
}

export function dateTime(t: number): string {
  const p = parts(t, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return `${p.day} ${p.month} ${p.hour}:${p.minute}`;
}

export function tfLabel(tf: Timeframe): string {
  return { "5m": "5 min", "15m": "15 min", "1h": "1 h", "4h": "4 h", "1j": "1 j" }[tf];
}
