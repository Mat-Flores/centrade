import { fr } from "@/i18n/fr";

// Customizable colors: presets, application on <html>, legibility checks.
// Roles are CSS values; presets use var(--...) so they follow the light or dark theme.

export interface ColorRoles {
  gain: string;
  loss: string;
  action: string;
  candleUp: string;
  candleDown: string;
  modeTest: string;
  modeLive: string;
  modeBacktest: string;
}

export const ROLE_KEYS: (keyof ColorRoles)[] = ["gain", "loss", "action", "candleUp", "candleDown", "modeTest", "modeLive", "modeBacktest"];

const VAR: Record<keyof ColorRoles, string> = {
  gain: "--c-gain", loss: "--c-loss", action: "--c-action", candleUp: "--c-candle-up", candleDown: "--c-candle-down",
  modeTest: "--c-mode-test", modeLive: "--c-mode-live", modeBacktest: "--c-mode-backtest",
};

const base: ColorRoles = {
  gain: "var(--bid)", loss: "var(--ask)", action: "var(--blue)", candleUp: "var(--bid)", candleDown: "var(--ask)",
  modeTest: "var(--amber)", modeLive: "var(--ask)", modeBacktest: "var(--violet)",
};

// Color blindness: blue / orange / teal. These three hues were validated with
// dataviz/scripts/validate_palette.js (--pairs all) against #12161d (dark) and #fbfaf7 (light):
// lightness band, chroma, CVD separation (worst pair 12.2) and 3:1 contrast, all PASS.
const CVD = { gain: "#2b7fe0", loss: "#d9730d", action: "#16a085" };

export interface Preset { id: string; label: string; roles: ColorRoles | null }
export const PRESETS: Preset[] = [
  { id: "reference", label: fr.colors.presets.reference, roles: null },
  {
    id: "colorblind", label: fr.colors.presets.colorblind,
    roles: { ...base, ...CVD, candleUp: CVD.gain, candleDown: CVD.loss, modeLive: "#d946b5" }, // magenta: distinct from the orange of losses
  },
  {
    id: "inverted", label: fr.colors.presets.inverted,
    roles: { ...base, gain: "var(--ask)", loss: "var(--bid)", candleUp: "var(--ask)", candleDown: "var(--bid)" },
  },
  { id: "neutral", label: fr.colors.presets.neutral, roles: { ...base, candleUp: "var(--bone)", candleDown: "var(--faint)" } },
];

export const sameRoles = (a: ColorRoles | null, b: ColorRoles | null): boolean =>
  a === b || (!!a && !!b && ROLE_KEYS.every((k) => a[k] === b[k]));

/** A role value is a hex color or a design token: anything else never reaches the DOM. */
const SAFE_VALUE = /^(#[0-9a-f]{6}|var\(--[a-z-]+\))$/i;
export function parseRoles(value: unknown): ColorRoles | null {
  if (typeof value !== "object" || value === null) return null;
  const roles = value as Record<string, unknown>;
  return ROLE_KEYS.every((k) => typeof roles[k] === "string" && SAFE_VALUE.test(roles[k] as string)) ? (roles as unknown as ColorRoles) : null;
}

/** Sets (or removes) the custom properties on <html>, then tells the chart. */
export function applyColors(roles: ColorRoles | null): void {
  const st = document.documentElement.style;
  for (const k of ROLE_KEYS) {
    if (roles) st.setProperty(VAR[k], roles[k]);
    else st.removeProperty(VAR[k]);
  }
  window.dispatchEvent(new Event("centrade:colors"));
}

/** Colors actually shown right now, as #rrggbb (for pickers and checks). */
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
  const s = probe.fillStyle; // "#rrggbb" or "rgba(...)"
  if (/^#[0-9a-f]{6}$/i.test(s)) return s;
  const m = s.match(/\d+/g);
  return m ? "#" + m.slice(0, 3).map((n) => Number(n).toString(16).padStart(2, "0")).join("") : "#808080";
}

// ---------- pure calculations ----------

const rgb = (hex: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as [number, number, number];
const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const lin3 = (hex: string): [number, number, number] => { const [r, g, b] = rgb(hex); return [lin(r), lin(g), lin(b)]; };

/** WCAG relative luminance. */
export function luminance(hex: string): number {
  const [r, g, b] = lin3(hex);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

/** sRGB (#rrggbb) to OKLab, Björn Ottosson matrices. */
export function oklab(hex: string): [number, number, number] {
  const [r, g, b] = lin3(hex);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}
/** OKLab distance x 100: under 15, two colors are easily confused. */
export function deltaE(a: string, b: string): number {
  const [x, y] = [oklab(a), oklab(b)];
  return 100 * Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]);
}

export const MIN_CONTRAST = 3;
export const MIN_DELTA = 15;

const PAIRS: [keyof ColorRoles, keyof ColorRoles, string][] = [
  ["gain", "loss", fr.colors.pairs.gainLoss],
  ["gain", "action", fr.colors.pairs.gainAction],
  ["loss", "action", fr.colors.pairs.lossAction],
  ["candleUp", "candleDown", fr.colors.pairs.candles],
  ["modeLive", "modeTest", fr.colors.pairs.liveTest],
  ["modeLive", "loss", fr.colors.pairs.liveLoss],
];

export function checkColors(roles: ColorRoles, surfaceHex: string): string[] {
  const out: string[] = [];
  for (const k of ROLE_KEYS) {
    const c = contrast(roles[k], surfaceHex);
    if (c < MIN_CONTRAST) out.push(fr.colors.lowContrast(fr.colors.roles[k], c.toFixed(1).replace(".", ",")));
  }
  for (const [a, b, msg] of PAIRS) if (deltaE(roles[a], roles[b]) < MIN_DELTA) out.push(msg);
  return out;
}
