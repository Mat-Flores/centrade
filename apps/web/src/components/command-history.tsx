import { CircleAlertIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { describeCommand } from "@/lib/cockpit";
import { formatAge, formatTimestamp } from "@/lib/format";
import type { Command } from "@/lib/instances";
import { cn } from "@/lib/utils";

const t = fr.commandHistory;
const SHOWN = 8;
const STEPS = [
  ["requested", "requested_at"],
  ["dispatched", "dispatched_at"],
  ["acknowledged", "acknowledged_at"],
  ["verified", "verified_at"],
  ["failed", "failed_at"],
  ["timed_out", "timed_out_at"],
  ["superseded", "superseded_at"],
] as const;

const typeLabel = (type: string) => fr.cockpit.command.types[type] ?? type;
function stamp(iso: string): string {
  try {
    return formatTimestamp(iso);
  } catch {
    return fr.orders.unreadable;
  }
}

/**
 * Commandes d'une instance (ou d'un type d'action) avec l'étape atteinte et l'heure de chacune (F9).
 * « Faite » n'existe que pour `verified` ; un échec ou une expiration non vus restent en alerte jusqu'à « Marquer comme vu ».
 */
export function CommandHistory({
  commands,
  nowIso,
  seen,
  onSeen,
  label,
  names,
}: {
  commands: Command[];
  nowIso: string;
  seen: ReadonlySet<string>;
  onSeen: (id: string) => void;
  label: string;
  /** Nom des instances, pour les listes qui mêlent plusieurs instances. */
  names?: ReadonlyMap<string, string>;
}) {
  const nowMs = Date.parse(nowIso);
  // Les échecs et expirations non vus passent devant : ils ne se perdent jamais au-delà de la limite d'affichage.
  const isUnseen = (c: Command) => describeCommand(c, nowMs).tone === "problem" && !seen.has(c.id);
  const ordered = [...commands.filter(isUnseen), ...commands.filter((c) => !isUnseen(c))];
  if (ordered.length === 0) return <p className="text-sm text-muted-foreground">{t.none}</p>;
  return (
    <div className="flex flex-col gap-2">
      <ol aria-label={label} className="flex flex-col divide-y rounded-lg border">
        {ordered.slice(0, SHOWN).map((c) => {
          const v = describeCommand(c, nowMs);
          const unseen = v.tone === "problem" && !seen.has(c.id);
          return (
            <li key={c.id} data-command-status={c.status} data-command-type={c.type} role={unseen ? "alert" : undefined} className="flex flex-col gap-1.5 p-3 text-sm">
              <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                {v.tone === "pending" && <Spinner />}
                {v.tone === "problem" && <CircleAlertIcon className="size-4 shrink-0" aria-hidden="true" />}
                {names && <span className="font-mono font-semibold">{names.get(c.instance_id) ?? fr.orders.unknownInstance}</span>}
                <span className="font-medium">{typeLabel(c.type)}</span>
                <span className={cn(v.tone === "problem" && "font-semibold")}>{fr.cockpit.command.status[c.status]}</span>
                <span className="text-muted-foreground">{formatAge(v.ageMs)}</span>
              </p>
              <ul className="flex flex-wrap gap-x-4 gap-y-0.5 text-muted-foreground">
                {STEPS.filter(([, key]) => c[key]).map(([step, key]) => (
                  <li key={step}>
                    {t.steps[step]} <span className="font-mono">{stamp(c[key] as string)}</span>
                  </li>
                ))}
                {v.tone === "pending" && (
                  <li>
                    {t.deadline} <span className="font-mono">{stamp(c.deadline_at)}</span>
                  </li>
                )}
              </ul>
              {v.tone === "problem" && (
                <p>
                  {fr.cockpit.command.reason} : {v.reason ?? fr.cockpit.command.noReason}
                </p>
              )}
              {unseen && (
                <div>
                  <Button type="button" variant="outline" onClick={() => onSeen(c.id)}>
                    {fr.cockpit.command.seen}
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {ordered.length > SHOWN && <p className="text-sm text-muted-foreground">{t.older(ordered.length - SHOWN)}</p>}
    </div>
  );
}
