import type { ReactNode } from "react";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { fr } from "@/i18n/fr";
import { formatAge, formatTimestamp, freshness } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface ObservedValueProps {
  /** Valeur déjà formatée. Absente (`null`, `undefined`, vide) ou `"unknown"` : l'état n'est pas connu. */
  value: ReactNode;
  /** Instant d'observation par le moteur ou la venue (ISO 8601). */
  observedAt: string | null | undefined;
  /** `server_time` de la réponse de l'API : l'âge se calcule contre lui, jamais contre l'horloge du navigateur. */
  serverTime: string;
  /** Seuil de fraîcheur en millisecondes (5 000 pour un flux, 30 000 pour un moteur). */
  staleAfterMs: number;
  className?: string;
}

/**
 * Seul moyen d'afficher une valeur issue d'un moteur ou d'une venue (SPEC §9, I1) : la valeur avec
 * son âge au survol et au focus ; estompée et marquée « périmé depuis … » au-delà du seuil ;
 * « inconnu » si elle est absente ou sans horodatage. La dernière valeur connue n'est jamais
 * présentée comme actuelle.
 */
export function ObservedValue({ value, observedAt, serverTime, staleAfterMs, className }: ObservedValueProps) {
  const missing = value == null || value === "" || value === "unknown";
  const f = missing ? ({ state: "unknown" } as const) : freshness({ observedAt, serverTime, staleAfterMs });

  if (f.state === "unknown") {
    return (
      <Hint text={fr.observed.unknownHint}>
        <span data-state="unknown" tabIndex={0} className={cn("rounded-sm text-muted-foreground italic", className)}>
          {fr.observed.unknown}
        </span>
      </Hint>
    );
  }

  // `observedAt` est lisible ici : `freshness` a déjà refusé le reste.
  const hint = `${fr.observed.observedAt} ${formatAge(f.ageMs)} · ${formatTimestamp(observedAt as string)}`;
  return (
    <Hint text={hint}>
      <span data-state={f.state} tabIndex={0} className={cn("inline-flex items-baseline gap-2 rounded-sm", className)}>
        <span className={cn("font-mono", f.state === "stale" && "opacity-70")}>{value}</span>
        {f.state === "stale" && (
          <span className="text-xs text-muted-foreground">{fr.observed.staleSince(formatAge(f.staleForMs))}</span>
        )}
      </span>
    </Hint>
  );
}

function Hint({ text, children }: { text: string; children: ReactNode }) {
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent>{text}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
