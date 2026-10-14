import { useSyncExternalStore } from "react";

/**
 * Display clock aligned on the server (SPEC §9, I1): every received `server_time` (list, heartbeat,
 * event) readjusts the offset; the age of a value is computed against this clock, never against the
 * browser clock alone. Between two messages, local time moves the clock forward.
 */
let offsetMs = 0;
let tick = 0;
const listeners = new Set<() => void>();

export function observeServerTime(iso: string): void {
  const server = Date.parse(iso);
  if (!Number.isNaN(server)) offsetMs = server - Date.now();
}

export const serverNow = (): number => Date.now() + offsetMs;

/** For tests: puts the clock back on the browser's. */
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

/** Server time (ISO 8601), refreshed every second: the only clock that ages the display. */
export function useServerNow(): string {
  useSyncExternalStore(subscribe, () => tick);
  return new Date(serverNow()).toISOString();
}
