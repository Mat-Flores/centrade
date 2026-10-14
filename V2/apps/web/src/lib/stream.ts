import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { z } from "zod";

import { API_BASE } from "./api";
import { observeServerTime } from "./clock";
import { applyStreamMessage } from "./cockpit";
import { alertsKey, AlertSchema, commandsKey, CommandSchema, InstanceSchema, instancesKey } from "./instances";
import { endSession, fetchMe } from "./session";

/** Every stream event carries the server time, which recalibrates the display clock. */
const timed = { server_time: z.string() };

/**
 * Event name -> payload schema (V2/apps/api/centrade_api/stream/routes.py). `instance`, `command` and
 * `alert` carry the whole object; `order`, `position` and `trade` carry a row the cockpit does not
 * read: only the signal counts, the lists are re-read.
 */
export const STREAM_SCHEMAS = {
  heartbeat: z.object(timed),
  instance: z.object({ ...timed, instance: InstanceSchema }),
  command: z.object({ ...timed, command: CommandSchema }),
  alert: z.object({ ...timed, alert: AlertSchema }),
  order: z.object(timed),
  position: z.object(timed),
  trade: z.object(timed),
} as const;

export type StreamEventName = keyof typeof STREAM_SCHEMAS;
export type StreamMessage = { [E in StreamEventName]: { event: E } & z.infer<(typeof STREAM_SCHEMAS)[E]> }[StreamEventName];

const EVENTS = Object.keys(STREAM_SCHEMAS) as StreamEventName[];
export const RECONNECT_MS = 3_000;

/**
 * After the stream closed for good: does a session still exist? Expired (401 on /auth/me): the session
 * is ended (back to login) and the stream is not reopened, otherwise it would loop on 401 forever.
 * Any other failure (API down) keeps the retry going: the session is not guessed lost.
 */
export async function shouldReconnect(): Promise<boolean> {
  try {
    if ((await fetchMe()) !== null) return true;
  } catch {
    return true;
  }
  await endSession();
  return false;
}

/** Reads a stream message; `null` when the content is not JSON matching the contract. */
export function parseStreamMessage(event: StreamEventName, data: string): StreamMessage | null {
  try {
    const parsed = STREAM_SCHEMAS[event].safeParse(JSON.parse(data));
    return parsed.success ? ({ event, ...parsed.data } as StreamMessage) : null;
  } catch {
    return null;
  }
}

export interface StreamHandlers {
  /** Called for each valid message (the server time is already observed). */
  onMessage: (message: StreamMessage) => void;
  /** Called on open and on reconnection: reload everything, nothing is assumed from before the cut. */
  onOpen: () => void;
}

/**
 * A single `EventSource` on `/stream`. The silence of the stream is measured and returned: the caller
 * decides when it becomes a degraded state. Source: https://developer.mozilla.org/docs/Web/API/EventSource
 * (automatic reconnection while the server answers 200; on an error response the connection is closed
 * for good, so we reopen it ourselves).
 */
export function useEventStream(handlers: StreamHandlers): { silentMs: number } {
  const [lastMessageAt, setLastMessageAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      source = new EventSource(`${API_BASE}/stream`);
      const es = source;
      es.onopen = () => {
        setLastMessageAt(Date.now());
        latest.current.onOpen();
      };
      es.onerror = () => {
        if (closed || es.readyState !== EventSource.CLOSED) return;
        void shouldReconnect().then((again) => {
          if (again && !closed) retry = setTimeout(connect, RECONNECT_MS);
        });
      };
      for (const name of EVENTS) {
        es.addEventListener(name, (e) => {
          const message = parseStreamMessage(name, (e as MessageEvent<string>).data);
          if (!message) return; // an invalid message is not a sign of life: the silence keeps counting
          setLastMessageAt(Date.now());
          observeServerTime(message.server_time);
          latest.current.onMessage(message);
        });
      }
    };
    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      source?.close();
    };
  }, []);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  return { silentMs: Math.max(0, now - lastMessageAt) };
}

/** On open and on reconnection: full re-read of the lists (nothing is assumed from before the cut). */
export function reloadLists(qc: QueryClient): void {
  for (const key of [instancesKey, commandsKey, alertsKey, ["instance-detail"]]) void qc.refetchQueries({ queryKey: key });
}

/** The cockpit's single stream: each message updates the TanStack Query cache; the caller reads the silence. */
export function useCockpitStream(): { silentMs: number } {
  const qc = useQueryClient();
  return useEventStream({ onMessage: (message) => applyStreamMessage(qc, message), onOpen: () => reloadLists(qc) });
}
