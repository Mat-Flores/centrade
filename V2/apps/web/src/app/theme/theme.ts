import { useSyncExternalStore } from "react";

import { applyColors, parseRoles, type ColorRoles } from "./colors";

export type Theme = "dark" | "light";
const THEME_KEY = "centrade-theme";
const COLORS_KEY = "centrade-colors";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // storage blocked: the choice holds for the session only
  }
}
function write(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* session only */
  }
}

function storedTheme(): Theme {
  const v = read(THEME_KEY);
  return v === "light" || v === "dark" ? v : "dark";
}
function storedColors(): ColorRoles | null {
  const v = read(COLORS_KEY);
  if (!v) return null;
  try {
    return parseRoles(JSON.parse(v));
  } catch {
    return null;
  }
}

let theme: Theme = storedTheme();
let colors: ColorRoles | null = storedColors();
const listeners = new Set<() => void>();
const subscribe = (cb: () => void) => (listeners.add(cb), () => listeners.delete(cb));

/** Applies the stored choices to <html>; called once at startup, before the first render. */
export function applyTheme(): void {
  document.documentElement.dataset.theme = theme;
  applyColors(colors);
}

/** The chart listens to the same event as for colors. */
export function setTheme(t: Theme): void {
  theme = t;
  write(THEME_KEY, t);
  applyTheme();
  listeners.forEach((l) => l());
}
export function setColors(next: ColorRoles | null): void {
  colors = next;
  write(COLORS_KEY, next ? JSON.stringify(next) : null);
  applyTheme();
  listeners.forEach((l) => l());
}
export const useTheme = (): Theme => useSyncExternalStore(subscribe, () => theme);
export const useColors = (): ColorRoles | null => useSyncExternalStore(subscribe, () => colors);
