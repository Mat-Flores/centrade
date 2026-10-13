// Lit les variables CSS du thème sur le conteneur : le canvas veut des valeurs résolues.
export type Rgb = readonly [number, number, number];
export interface Palette {
  bg: Rgb; surface: Rgb; line: Rgb; ink: Rgb; mute: Rgb;
  gain: Rgb; loss: Rgb; action: Rgb; up: Rgb; down: Rgb;
  font: string;
}

// Valeurs de repli, utilisées seulement si une variable manque.
const FALLBACK: Record<string, string> = {
  "--c-bg": "#101418", "--c-surface": "#171c22", "--c-line": "#2a323b", "--c-ink": "#e6eaee", "--c-mute": "#8b96a1",
  "--c-gain": "#2fa66a", "--c-loss": "#d9534f", "--c-action": "#4a90e2", "--c-candle-up": "#2fa66a", "--c-candle-down": "#d9534f",
};

let probe: CanvasRenderingContext2D | null = null;

/** Résout n'importe quelle couleur CSS (oklch, color-mix…) en RGB via un pixel de canvas. */
function resolve(value: string, fallback: string): Rgb {
  probe ??= Object.assign(document.createElement("canvas"), { width: 1, height: 1 }).getContext("2d", { willReadFrequently: true });
  if (!probe) return [128, 128, 128];
  probe.fillStyle = fallback;
  probe.fillStyle = value; // une valeur invalide est ignorée : le repli reste
  probe.clearRect(0, 0, 1, 1);
  probe.fillRect(0, 0, 1, 1);
  const d = probe.getImageData(0, 0, 1, 1).data;
  return [d[0], d[1], d[2]];
}

export function readPalette(el: HTMLElement): Palette {
  const cs = getComputedStyle(el);
  const c = (name: string): Rgb => resolve(cs.getPropertyValue(name).trim(), FALLBACK[name]);
  return {
    bg: c("--c-bg"), surface: c("--c-surface"), line: c("--c-line"), ink: c("--c-ink"), mute: c("--c-mute"),
    gain: c("--c-gain"), loss: c("--c-loss"), action: c("--c-action"), up: c("--c-candle-up"), down: c("--c-candle-down"),
    font: cs.getPropertyValue("--font-num").trim() || "ui-monospace, monospace",
  };
}

export const css = (c: Rgb, alpha = 1): string => `rgba(${c[0]},${c[1]},${c[2]},${alpha})`;

/** Appelle `cb` quand le thème change (attribut data-theme ou événement centrade:colors). Renvoie le nettoyage. */
export function watchTheme(cb: () => void): () => void {
  const mo = new MutationObserver(cb);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  window.addEventListener("centrade:colors", cb);
  return () => { mo.disconnect(); window.removeEventListener("centrade:colors", cb); };
}
