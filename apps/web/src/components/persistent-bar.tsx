import { CircleAlertIcon, CircleCheckIcon, CircleHelpIcon, CircleXIcon, PowerIcon, TriangleAlertIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fr } from "@/i18n/fr";

export type Mode = "paper" | "live" | "unknown";
export type Health = "ok" | "degraded" | "down" | "unknown";
export type ConnectionName = "engines" | "bus" | "database";

export interface PersistentBarProps {
  /** Mode observé : LIVE dès qu'une instance live existe. `unknown` tant que rien n'est observé. */
  mode: Mode;
  /** État observé de chaque connexion. */
  connections: Record<ConnectionName, Health>;
  /** Alertes ouvertes ; `null` tant que le compte n'est pas observé. */
  alertCount: number | null;
  /** Bandeau de mode dégradé (permanent tant qu'il est fourni). */
  degradedBanner?: ReactNode;
  /** Extrémité droite : thème, session. */
  actions?: ReactNode;
}

const HEALTH_ICON = {
  ok: CircleCheckIcon,
  degraded: TriangleAlertIcon,
  down: CircleXIcon,
  unknown: CircleHelpIcon,
} as const;

const CONNECTIONS: ConnectionName[] = ["engines", "bus", "database"];

export function PersistentBar({ mode, connections, alertCount, degradedBanner, actions }: PersistentBarProps) {
  return (
    <header aria-label={fr.bar.label} className="sticky top-0 z-40 border-b bg-card text-card-foreground">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <span className="text-lg font-semibold tracking-tight">{fr.productName}</span>
          <Badge variant={mode === "live" ? "live" : mode === "paper" ? "default" : "unknown"}>
            <span className="sr-only">{fr.bar.mode} : </span>
            {fr.bar.modes[mode]}
          </Badge>
        </div>

        <ul aria-label={fr.bar.connections} className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          {CONNECTIONS.map((name) => {
            const health = connections[name];
            const Icon = HEALTH_ICON[health];
            return (
              <li key={name} className="flex items-center gap-1.5">
                <Icon className="size-4 shrink-0" aria-hidden="true" />
                <span className="text-muted-foreground">{fr.bar.connectionNames[name]}</span>
                <span className={health === "down" ? "font-semibold text-destructive" : "font-medium"}>
                  {fr.bar.health[health]}
                </span>
              </li>
            );
          })}
        </ul>

        <div className="ml-auto flex flex-wrap items-center gap-3">
          <p className="flex items-center gap-1.5 text-sm">
            <CircleAlertIcon className="size-4 shrink-0" aria-hidden="true" />
            <span className="text-muted-foreground">{fr.bar.alerts}</span>
            <span className="font-medium">{alertCount ?? fr.bar.alertsUnknown}</span>
          </p>
          <KillSwitch />
          {actions}
        </div>
      </div>
      {degradedBanner}
    </header>
  );
}

/**
 * Présent mais inactif jusqu'à M3. Style « inactif » neutre (DESIGN.md : 50 % d'opacité, pas de rouge) et
 * raison écrite à côté, en permanence ; `aria-disabled` garde le bouton focalisable et la raison lui est reliée.
 */
function KillSwitch() {
  const reasonId = "kill-switch-reason";
  return (
    <div className="flex flex-col items-start gap-0.5">
      <Button
        type="button"
        variant="outline"
        aria-disabled="true"
        aria-describedby={reasonId}
        className="cursor-not-allowed text-muted-foreground opacity-50 hover:bg-background"
        onClick={(event) => event.preventDefault()}
      >
        <PowerIcon data-icon="inline-start" />
        {fr.bar.killSwitch}
      </Button>
      <span id={reasonId} className="text-xs text-muted-foreground">
        {fr.bar.killSwitchReason}
      </span>
    </div>
  );
}
