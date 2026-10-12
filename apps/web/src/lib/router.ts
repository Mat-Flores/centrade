import { useMemo, useSyncExternalStore } from "react";

/**
 * Routeur minimal sur l'API History : URL partageables, bouton retour, aucune dépendance.
 * Source : https://developer.mozilla.org/docs/Web/API/History_API
 * shortcut: chemins plats ; un détail passe par un paramètre de requête (?s=…&v=…), pas par /x/:id. Un vrai routeur (ADR) si cela ne suffit plus.
 */

export const SCREEN_PATHS = {
  cockpit: "/",
  strategies: "/strategies",
  orders: "/orders",
  accounts: "/accounts",
} as const;
export type RoutedScreen = keyof typeof SCREEN_PATHS;

/** Écran routé pour un chemin ; `null` : chemin inconnu (page introuvable). Barre finale tolérée. */
export function screenAt(pathname: string): RoutedScreen | null {
  const clean = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const hit = (Object.entries(SCREEN_PATHS) as [RoutedScreen, string][]).find(([, p]) => p === clean);
  return hit ? hit[0] : null;
}

// Vrai dès la première navigation de la session : le premier affichage ne vole pas le focus, les suivants le déplacent.
let navigated = false;
export const hasNavigated = () => navigated;
if (typeof window !== "undefined") window.addEventListener("popstate", () => (navigated = true));

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

export function navigate(path: string): void {
  if (path === window.location.pathname + window.location.search) return;
  navigated = true;
  window.history.pushState(null, "", path);
  notify();
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname);
}

/** Paramètres de requête de l'adresse courante (détail d'un écran : stratégie et version choisies). */
export function useSearch(): URLSearchParams {
  const search = useSyncExternalStore(subscribe, () => window.location.search);
  return useMemo(() => new URLSearchParams(search), [search]);
}

/** Adresse d'un écran avec ses paramètres ; les valeurs vides sont omises. */
export function pathWith(path: string, params: Record<string, string | number | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
  const text = q.toString();
  return text ? `${path}?${text}` : path;
}
