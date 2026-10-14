import { useEffect, useRef, useState } from "react";
import { z } from "zod";

import { API_BASE } from "./api";
import { observeServerTime } from "./clock";

/** Every stream event carries the server time, which recalibrates the display clock. */
const timed = { server_time: z.string() };

/** Event name -> payload schema. Screens add their own events here as they arrive. */
export const STREAM_SCHEMAS = {
  heartbeat: z.object(timed),
  order: z.object(timed),
  position: z.object(timed),
  trade: z.object(timed),
} as const;

export type StreamEventName = keyof typeof STREAM_SCHEMAS;
export type StreamMessage = { [E in StreamEventName]: { event: E } & z.infer<(typeof STREAM_SCHEMAS)[E]> }[StreamEventName];

const EVENTS = Object.keys(STREAM_SCHEMAS) as StreamEventName[];
const RECONNECT_MS = 3_000;

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
        if (!closed && es.readyState === EventSource.CLOSED) retry = setTimeout(connect, RECONNECT_MS);
      };
      for (const name of EVENTS) {
        es.addEventListener(name, (e) => {
          setLastMessageAt(Date.now());
          const message = parseStreamMessage(name, (e as MessageEvent<string>).data);
          if (!message) return;
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
