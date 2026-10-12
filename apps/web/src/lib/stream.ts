import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { z } from "zod";

import { API_BASE } from "./api";
import { applyStreamMessage, type StreamMessage } from "./cockpit";
import { observeServerTime } from "./clock";
import { alertsKey, AlertSchema, commandsKey, CommandSchema, InstanceSchema, instancesKey } from "./instances";

const timed = { server_time: z.string() };
const SCHEMAS = {
  heartbeat: z.object(timed),
  instance: z.object({ ...timed, instance: InstanceSchema }),
  command: z.object({ ...timed, command: CommandSchema }),
  alert: z.object({ ...timed, alert: AlertSchema }),
  order: z.object(timed),
  position: z.object(timed),
  trade: z.object(timed),
} as const;
const EVENTS = Object.keys(SCHEMAS) as (keyof typeof SCHEMAS)[];

const RECONNECT_MS = 3_000;

/** Lit un message du flux ; `null` si le contenu n'est pas du JSON conforme au contrat. */
export function parseStreamMessage(event: keyof typeof SCHEMAS, data: string): StreamMessage | null {
  try {
    const parsed = SCHEMAS[event].safeParse(JSON.parse(data));
    return parsed.success ? ({ event, ...parsed.data } as StreamMessage) : null;
  } catch {
    return null;
  }
}

/** À l'ouverture et à la reconnexion : relecture complète des listes (rien n'est supposé d'avant la coupure). */
function reload(qc: QueryClient): void {
  for (const key of [instancesKey, commandsKey, alertsKey, ["trading"], ["instance-detail"]]) void qc.refetchQueries({ queryKey: key });
}

/**
 * Un seul `EventSource` sur `/stream`. Chaque message met le cache TanStack Query à jour ; le silence
 * du flux est mesuré par l'appelant. Source : https://developer.mozilla.org/docs/Web/API/EventSource
 * (reconnexion automatique tant que le serveur répond 200 ; sur une réponse d'erreur, la connexion est
 * fermée définitivement et on la rouvre nous-mêmes).
 */
export function useCockpitStream(): { silentMs: number } {
  const qc = useQueryClient();
  const [lastMessageAt, setLastMessageAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      source = new EventSource(`${API_BASE}/stream`);
      const es = source;
      es.onopen = () => {
        setLastMessageAt(Date.now());
        reload(qc);
      };
      es.onerror = () => {
        if (!closed && es.readyState === EventSource.CLOSED) retry = setTimeout(connect, RECONNECT_MS);
      };
      for (const name of EVENTS) {
        es.addEventListener(name, (e) => {
          setLastMessageAt(Date.now());
          const msg = parseStreamMessage(name, (e as MessageEvent<string>).data);
          if (!msg) return;
          observeServerTime(msg.server_time);
          applyStreamMessage(qc, msg);
        });
      }
    };
    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      source?.close();
    };
  }, [qc]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  return { silentMs: Math.max(0, now - lastMessageAt) };
}
