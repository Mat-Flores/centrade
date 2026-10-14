import { useCallback, useState } from "react";

const KEY = "centrade-commands-seen";
const KEEP = 200;

function load(): string[] {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return []; // storage blocked or unreadable: everything stays unseen, never the opposite
  }
}

/**
 * Failed or timed-out commands the operator explicitly saw. This browser's memory only: the API has no
 * per-command acknowledgement (yet); without storage they stay unseen.
 */
export function useSeenCommands() {
  const [ids, setIds] = useState<string[]>(load);
  const markSeen = useCallback((id: string) => {
    setIds((current) => {
      const next = [...current.filter((x) => x !== id), id].slice(-KEEP);
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        // storage unavailable: session memory is enough
      }
      return next;
    });
  }, []);
  return { seen: new Set(ids) as ReadonlySet<string>, markSeen };
}
