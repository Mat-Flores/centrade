import { fr } from "@/i18n/fr";

/** Display formats (SPEC §9, Numbers): fr-CA, America/Toronto, no float for money. */

const LOCALE = "fr-CA";
const TIME_ZONE = "America/Toronto";
const DECIMAL = /^[+-]?\d+(\.\d+)?$/;

/** Readable age. A negative age (engine clock ahead) is brought back to zero. */
export function formatAge(ms: number): string {
  const s = Math.floor(Math.max(0, ms) / 1000);
  if (s < 1) return fr.age.instant;
  if (s < 60) return fr.age.seconds(s);
  const min = Math.floor(s / 60);
  if (min < 60) return fr.age.minutes(min);
  const h = Math.floor(min / 60);
  if (h < 24) return fr.age.hours(h, String(min % 60).padStart(2, "0"));
  return fr.age.days(Math.floor(h / 24), h % 24);
}

/** Elapsed time in seconds, shortened: "3 j 4 h 12 min". Under a minute: seconds only. */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  if (s < 60) return fr.duration.seconds(s);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return [d && fr.duration.days(d), (d || h) && fr.duration.hours(h), fr.duration.minutes(m)].filter(Boolean).join(" ");
}

export type Timeframe = keyof typeof fr.timeframes;

export const formatTimeframe = (timeframe: Timeframe): string => fr.timeframes[timeframe];

export type Freshness =
  | { state: "fresh"; ageMs: number }
  | { state: "stale"; ageMs: number; staleForMs: number }
  | { state: "unknown" };

/**
 * Freshness from the server time (never the browser clock).
 * A missing or unreadable timestamp gives "unknown": without a date, nothing can be shown as current (I1).
 */
export function freshness(input: {
  observedAt: string | null | undefined;
  serverTime: string;
  staleAfterMs: number;
}): Freshness {
  const observed = input.observedAt ? Date.parse(input.observedAt) : NaN;
  const server = Date.parse(input.serverTime);
  if (Number.isNaN(observed) || Number.isNaN(server)) return { state: "unknown" };
  const ageMs = Math.max(0, server - observed);
  return ageMs <= input.staleAfterMs
    ? { state: "fresh", ageMs }
    : { state: "stale", ageMs, staleForMs: ageMs - input.staleAfterMs };
}

const timestampFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
  timeZoneName: "short",
});

/** Timestamp in Toronto time, time zone shown (EST or EDT). */
export function formatTimestamp(iso: string): string {
  return timestampFormat.format(new Date(iso)); // throws RangeError if the date is unreadable
}

function zonedParts(epochSeconds: number, options: Intl.DateTimeFormatOptions): Record<string, string> {
  const format = new Intl.DateTimeFormat(LOCALE, { timeZone: TIME_ZONE, hourCycle: "h23", ...options });
  return Object.fromEntries(format.formatToParts(new Date(epochSeconds * 1000)).map((p) => [p.type, p.value]));
}

/** Time of day in Toronto, "17:42". Input: epoch seconds. */
export function formatClock(epochSeconds: number): string {
  const p = zonedParts(epochSeconds, { hour: "2-digit", minute: "2-digit" });
  return `${p.hour}:${p.minute}`;
}

/** Short date and time in Toronto, "12 oct. 17:42". Input: epoch seconds. */
export function formatDateTime(epochSeconds: number): string {
  const p = zonedParts(epochSeconds, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return `${p.day} ${p.month} ${p.hour}:${p.minute}`;
}

/** Calendar days (Toronto) between two instants: 23:50 then 00:10 gives 1. */
export function dayOffset(fromEpochSeconds: number, toEpochSeconds: number): number {
  const day = (t: number) => {
    const p = zonedParts(t, { year: "numeric", month: "2-digit", day: "2-digit" });
    return Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day));
  };
  return Math.round((day(toEpochSeconds) - day(fromEpochSeconds)) / 86_400_000);
}

/** Decimal string -> fr-CA text, no rounding: every decimal of the string is kept. */
function formatDecimal(amount: string, signDisplay: "auto" | "always"): string {
  if (!DECIMAL.test(amount)) throw new RangeError(fr.errors.invalidDecimal(amount));
  const digits = (amount.split(".")[1] ?? "").length;
  return new Intl.NumberFormat(LOCALE, {
    signDisplay,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(amount as `${number}`); // the string is passed as is: never through a float
}

function withCurrency(text: string, currency: string): string {
  if (!currency.trim()) throw new Error(fr.errors.currencyRequired);
  return `${text}\u00a0${currency}`;
}

/** Amount with its currency (always shown). */
export function formatMoney(amount: string, currency: string): string {
  return withCurrency(formatDecimal(amount, "auto"), currency);
}

/** PnL: explicit sign, currency always shown. */
export function formatPnl(amount: string, currency: string): string {
  return withCurrency(formatDecimal(amount, "always"), currency);
}

/** Decimal number without currency (ratio, quantity, price), every decimal of the string kept. */
export function formatDecimalText(amount: string, signed = false): string {
  return formatDecimal(amount, signed ? "always" : "auto");
}
