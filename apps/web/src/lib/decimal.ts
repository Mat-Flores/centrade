/** Arithmétique décimale exacte sur des chaînes (SPEC §9 : aucun flottant pour l'argent, aucun arrondi). */

const DECIMAL = /^([+-]?)(\d+)(?:\.(\d+))?$/;

interface Scaled {
  units: bigint;
  scale: number;
}

function parse(amount: string): Scaled {
  const m = DECIMAL.exec(amount);
  if (!m) throw new RangeError(`Montant décimal invalide : ${amount}`);
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

/** Somme exacte : l'échelle est celle du terme le plus précis. Liste vide : "0". */
export function sumDecimals(amounts: readonly string[]): string {
  const parsed = amounts.map(parse);
  const scale = Math.max(0, ...parsed.map((p) => p.scale));
  const units = parsed.reduce((acc, p) => acc + p.units * 10n ** BigInt(scale - p.scale), 0n);
  return render({ units, scale });
}

/** Multiplie par 10^places sans arrondi (ex. un ratio "-0.05" vers des pourcentages "-5"). */
export function shiftDecimal(amount: string, places: number): string {
  const { units, scale } = parse(amount);
  return places >= scale ? render({ units: units * 10n ** BigInt(places - scale), scale: 0 }) : render({ units, scale: scale - places });
}

/** Signe d'un montant : -1, 0 ou 1. */
export function signOf(amount: string): -1 | 0 | 1 {
  const { units } = parse(amount);
  return units < 0n ? -1 : units > 0n ? 1 : 0;
}
