import { useCallback, useState } from "react";

const KEY = "centrade-commands-seen";
const KEEP = 200;

function load(): string[] {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return []; // stockage bloqué ou illisible : tout reste à voir, jamais l'inverse
  }
}

/**
 * Commandes en échec ou expirées que l'opérateur a explicitement vues. Mémoire de ce navigateur
 * seulement : l'API n'a pas (encore) d'acquittement par commande ; sans stockage, elles restent à voir.
 */
export function useSeenCommands() {
  const [ids, setIds] = useState<string[]>(load);
  const markSeen = useCallback((id: string) => {
    setIds((current) => {
      const next = [...current.filter((x) => x !== id), id].slice(-KEEP);
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        // stockage indisponible : la mémoire de session suffit
      }
      return next;
    });
  }, []);
  return { seen: new Set(ids) as ReadonlySet<string>, markSeen };
}
