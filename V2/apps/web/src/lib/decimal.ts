import { fr } from "@/i18n/fr";

/** Exact decimal arithmetic on strings (SPEC §9: no float for money, no rounding). */

const DECIMAL = /^([+-]?)(\d+)(?:\.(\d+))?$/;

interface Scaled {
  units: bigint;
  scale: number;
}

function parse(amount: string): Scaled {
  const m = DECIMAL.exec(amount);
  if (!m) throw new RangeError(fr.errors.invalidDecimal(amount));
  const frac = m[3] ?? "";
  const units = BigInt(`${m[2]}${frac}`);
  return { units: m[1] === "-" ? -units : units, scale: frac.length };
}

function render({ units, scale }: Scaled): string {
  const neg = units < 0n;
  const digits = (neg ? -units : units).toString().padStart(scale + 1, "0");
  const int = digits.slice(0, digits.length - scale);
  const frac = digits.slice(digits.length - scale);
  return `${neg ? "-" : ""}${int}${scale > 0 ? `.${frac}` : ""}`;
}

/** Exact sum: the scale is that of the most precise term. Empty list: "0". */
export function sumDecimals(amounts: readonly string[]): string {
  const parsed = amounts.map(parse);
  const scale = Math.max(0, ...parsed.map((p) => p.scale));
  const units = parsed.reduce((acc, p) => acc + p.units * 10n ** BigInt(scale - p.scale), 0n);
  return render({ units, scale });
}

/** Multiplies by 10^places without rounding (e.g. a ratio "-0.05" to a percentage "-5"). */
export function shiftDecimal(amount: string, places: number): string {
  const { units, scale } = parse(amount);
  return places >= scale ? render({ units: units * 10n ** BigInt(places - scale), scale: 0 }) : render({ units, scale: scale - places });
}

/** Sign of an amount: -1, 0 or 1. */
export function signOf(amount: string): -1 | 0 | 1 {
  const { units } = parse(amount);
  return units < 0n ? -1 : units > 0n ? 1 : 0;
}
