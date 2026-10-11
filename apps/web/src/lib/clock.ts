import { useSyncExternalStore } from "react";

/**
 * Horloge d'affichage calée sur le serveur (SPEC §9, I1) : chaque `server_time` reçu (liste, battement,
 * événement) recale le décalage ; l'âge d'une valeur se calcule contre cette horloge, jamais contre
 * celle du navigateur seule. Entre deux messages, le temps local fait avancer l'horloge.
 */
let offsetMs = 0;
let tick = 0;
const listeners = new Set<() => void>();

export function observeServerTime(iso: string): void {
  const server = Date.parse(iso);
  if (!Number.isNaN(server)) offsetMs = server - Date.now();
}

export const serverNow = (): number => Date.now() + offsetMs;

/** Pour les tests : remet l'horloge sur celle du navigateur. */
export function resetServerClock(): void {
  offsetMs = 0;
}

let timer: ReturnType<typeof setInterval> | null = null;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (timer === null) {
    timer = setInterval(() => {
      tick += 1;
      listeners.forEach((l) => l());
    }, 1000);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
}

/** Heure du serveur (ISO 8601), rafraîchie chaque seconde : seule horloge qui fait vieillir l'affichage. */
export function useServerNow(): string {
  useSyncExternalStore(subscribe, () => tick);
  return new Date(serverNow()).toISOString();
}
