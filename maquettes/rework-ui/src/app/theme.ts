import { useSyncExternalStore } from "react";

export type Theme = "dark" | "light";
let theme: Theme = "dark";
const listeners = new Set<() => void>();

/** Non persistant, comme le reste de la maquette. Le graphique écoute le même évènement que pour les couleurs. */
export function setTheme(t: Theme): void {
  theme = t;
  document.documentElement.dataset.theme = t;
  listeners.forEach((l) => l());
  window.dispatchEvent(new Event("centrade:colors"));
}
export function useTheme(): Theme {
  return useSyncExternalStore((cb) => (listeners.add(cb), () => listeners.delete(cb)), () => theme);
}
