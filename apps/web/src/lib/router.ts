import { useSyncExternalStore } from "react";

/**
 * Routeur minimal sur l'API History : URL partageables, bouton retour, aucune dépendance.
 * Source : https://developer.mozilla.org/docs/Web/API/History_API
 * shortcut: chemins plats sans paramètres ; passer à un vrai routeur (ADR) si un écran a besoin de /x/:id.
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
  if (path === window.location.pathname) return;
  navigated = true;
  window.history.pushState(null, "", path);
  notify();
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname);
}
