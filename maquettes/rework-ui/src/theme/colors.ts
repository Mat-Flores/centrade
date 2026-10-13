import type { ColorRoles } from "../data/types";

// Couleurs personnalisables : jeux prédéfinis, application sur <html>, contrôle de lisibilité.
// Les rôles sont des valeurs CSS ; les jeux utilisent var(--…) pour suivre le thème clair ou sombre.

export const ROLE_KEYS: (keyof ColorRoles)[] = ["gain", "perte", "action", "bougieHausse", "bougieBaisse", "modeTest", "modeReel", "modeBacktest"];

export const ROLE_LABEL: Record<keyof ColorRoles, string> = {
  gain: "Gain", perte: "Perte", action: "Achats, ventes et en cours",
  bougieHausse: "Bougie en hausse", bougieBaisse: "Bougie en baisse",
  modeTest: "Mode test", modeReel: "Mode réel", modeBacktest: "Backtest",
};

const VAR: Record<keyof ColorRoles, string> = {
  gain: "--c-gain", perte: "--c-loss", action: "--c-action", bougieHausse: "--c-candle-up", bougieBaisse: "--c-candle-down",
  modeTest: "--c-mode-test", modeReel: "--c-mode-reel", modeBacktest: "--c-mode-backtest",
};

const base: ColorRoles = {
  gain: "var(--bid)", perte: "var(--ask)", action: "var(--blue)", bougieHausse: "var(--bid)", bougieBaisse: "var(--ask)",
  modeTest: "var(--amber)", modeReel: "var(--ask)", modeBacktest: "var(--violet)",
};

// Daltonisme : bleu / orange / vert-bleu. Ces trois teintes ont été validées avec
// dataviz/scripts/validate_palette.js (--pairs all) contre #12161d (sombre) et #fbfaf7 (clair) :
// bande de luminosité, chroma, séparation CVD (pire paire 12,2) et contraste 3:1, tous PASS.
const CVD = { gain: "#2b7fe0", perte: "#d9730d", action: "#16a085" };

export interface Preset { id: string; label: string; roles: ColorRoles | null }
export const PRESETS: Preset[] = [
  { id: "reference", label: "Référence", roles: null },
  {
    id: "daltonisme", label: "Adapté au daltonisme",
    roles: { ...base, ...CVD, bougieHausse: CVD.gain, bougieBaisse: CVD.perte, modeReel: "#d946b5" }, // magenta : distinct de l'orange des pertes
  },
  {
    id: "inverse", label: "Inversé (marchés asiatiques)",
    roles: { ...base, gain: "var(--ask)", perte: "var(--bid)", bougieHausse: "var(--ask)", bougieBaisse: "var(--bid)" },
  },
  { id: "neutres", label: "Bougies neutres", roles: { ...base, bougieHausse: "var(--bone)", bougieBaisse: "var(--faint)" } },
];

/** Pose (ou retire) les propriétés personnalisées sur <html>, puis prévient le graphique. */
export function applyColors(roles: ColorRoles | null): void {
  const st = document.documentElement.style;
  for (const k of ROLE_KEYS) {
    if (roles) st.setProperty(VAR[k], roles[k]);
    else st.removeProperty(VAR[k]);
  }
  window.dispatchEvent(new Event("centrade:colors"));
}

/** Couleurs réellement affichées en ce moment, en #rrggbb (pour les sélecteurs et les contrôles). */
export function readRoles(): ColorRoles {
  const cs = getComputedStyle(document.documentElement);
  return Object.fromEntries(ROLE_KEYS.map((k) => [k, toHex(cs.getPropertyValue(VAR[k]).trim())])) as unknown as ColorRoles;
}
export function readSurface(): string {
  return toHex(getComputedStyle(document.documentElement).getPropertyValue("--c-surface").trim());
}

let probe: CanvasRenderingContext2D | null = null;
export function toHex(v: string): string {
  if (/^#[0-9a-f]{6}$/i.test(v)) return v.toLowerCase();
  probe ??= document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  if (!probe) return "#808080";
  probe.fillStyle = "#808080";
  probe.fillStyle = v;
  const s = probe.fillStyle; // "#rrggbb" ou "rgba(…)"
  if (/^#[0-9a-f]{6}$/i.test(s)) return s;
  const m = s.match(/\d+/g);
  return m ? "#" + m.slice(0, 3).map((n) => Number(n).toString(16).padStart(2, "0")).join("") : "#808080";
}

// ---------- calculs purs ----------

const rgb = (hex: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as [number, number, number];
const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);

/** Luminance relative WCAG. */
export function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map(lin);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** sRGB (#rrggbb) vers OKLab, matrices de Björn Ottosson. */
export function oklab(hex: string): [number, number, number] {
  const [r, g, b] = rgb(hex).map(lin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}
/** Distance OKLab × 100 : sous 15, deux couleurs se confondent facilement. */
export function deltaE(a: string, b: string): number {
  const [x, y] = [oklab(a), oklab(b)];
  return 100 * Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]);
}

export const MIN_CONTRAST = 3;
export const MIN_DELTA = 15;

const PAIRS: [keyof ColorRoles, keyof ColorRoles, string][] = [
  ["gain", "perte", "Gain et perte se ressemblent : le signe et la flèche restent le seul repère fiable."],
  ["gain", "action", "Gain et achats/en cours se ressemblent : un solde en cours se confond avec un gain encaissé."],
  ["perte", "action", "Perte et achats/en cours se ressemblent."],
  ["bougieHausse", "bougieBaisse", "Les bougies en hausse et en baisse se ressemblent."],
  ["modeReel", "modeTest", "Mode réel et mode test se ressemblent : le mode réel doit se distinguer au premier regard."],
  ["modeReel", "perte", "Mode réel et perte ont la même teinte ou presque. Le tag réel reste le seul plein, mais la couleur ne les sépare plus."],
];

export function checkColors(roles: ColorRoles, surfaceHex: string): string[] {
  const out: string[] = [];
  for (const k of ROLE_KEYS) {
    const c = contrast(roles[k], surfaceHex);
    if (c < MIN_CONTRAST) out.push(`${ROLE_LABEL[k]} : contraste ${c.toFixed(1).replace(".", ",")}:1 sur le fond, sous le minimum de 3:1. Illisible pour une part des yeux.`);
  }
  for (const [a, b, msg] of PAIRS) if (deltaE(roles[a], roles[b]) < MIN_DELTA) out.push(msg);
  return out;
}
