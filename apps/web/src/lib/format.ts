/** Formats d'affichage (SPEC §9, Nombres) : fr-CA, America/Toronto, aucun flottant pour l'argent. */

const LOCALE = "fr-CA";
const TIME_ZONE = "America/Toronto";
const DECIMAL = /^[+-]?\d+(\.\d+)?$/;

/** Âge lisible. Un âge négatif (horloge du moteur en avance) est ramené à zéro. */
export function formatAge(ms: number): string {
  const s = Math.floor(Math.max(0, ms) / 1000);
  if (s < 1) return "à l'instant";
  if (s < 60) return `il y a ${s} s`;
  const min = Math.floor(s / 60);
  if (min < 60) return `il y a ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `il y a ${h} h ${String(min % 60).padStart(2, "0")} min`;
  return `il y a ${Math.floor(h / 24)} j ${h % 24} h`;
}

export type Freshness =
  | { state: "fresh"; ageMs: number }
  | { state: "stale"; ageMs: number; staleForMs: number }
  | { state: "unknown" };

/**
 * Fraîcheur d'après l'heure du serveur (jamais l'horloge du navigateur).
 * Un horodatage absent ou illisible donne « inconnu » : sans date, rien n'est présentable comme actuel (I1).
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

/** Horodatage en heure de Toronto, fuseau indiqué (HNE ou HAE). */
export function formatTimestamp(iso: string): string {
  return timestampFormat.format(new Date(iso)); // lève RangeError si la date est illisible
}

/** Chaîne décimale -> texte fr-CA, sans arrondi : les décimales de la chaîne sont toutes conservées. */
function formatDecimal(amount: string, signDisplay: "auto" | "always"): string {
  if (!DECIMAL.test(amount)) throw new RangeError(`Montant décimal invalide : ${amount}`);
  const digits = (amount.split(".")[1] ?? "").length;
  return new Intl.NumberFormat(LOCALE, {
    signDisplay,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(amount as `${number}`); // la chaîne est transmise telle quelle : pas de passage par un flottant
}

function withCurrency(text: string, currency: string): string {
  if (!currency.trim()) throw new Error("La devise est obligatoire");
  return `${text}\u00a0${currency}`;
}

/** Montant avec sa devise (toujours affichée). */
export function formatMoney(amount: string, currency: string): string {
  return withCurrency(formatDecimal(amount, "auto"), currency);
}

/** PnL : signe toujours explicite, devise toujours affichée. */
export function formatPnl(amount: string, currency: string): string {
  return withCurrency(formatDecimal(amount, "always"), currency);
}
