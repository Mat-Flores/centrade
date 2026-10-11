import { CircleCheckIcon, CircleXIcon } from "lucide-react";

import { ObservedValue } from "@/components/observed-value";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { fr } from "@/i18n/fr";
import { formatAge, formatTimestamp } from "@/lib/format";
import type { Alert, HealthReport, Instance } from "@/lib/instances";

const CHECKS = ["database", "bus", "worker"] as const;
const HEALTH_STALE_MS = 30_000;

export function AlertsPanel({
  alerts,
  instances,
  nowIso,
  state,
  dimmed,
}: {
  alerts: Alert[] | undefined;
  instances: Instance[];
  nowIso: string;
  state: "pending" | "error" | "success";
  dimmed: boolean;
}) {
  const nowMs = Date.parse(nowIso);
  const names = new Map(instances.map((i) => [i.id, i.name]));
  return (
    <section aria-labelledby="alerts-title" className="flex flex-col gap-3" data-dimmed={dimmed || undefined}>
      <h2 id="alerts-title" className="text-xl font-semibold tracking-tight">
        {fr.cockpit.alerts.title}
      </h2>
      {state === "pending" && <Skeleton className="h-16" aria-label={fr.cockpit.alerts.loading} role="status" />}
      {state === "error" && <p className="text-sm">{fr.cockpit.alerts.error}</p>}
      {state === "success" && alerts && alerts.length === 0 && (
        <p className="text-sm text-muted-foreground">{fr.cockpit.alerts.none}</p>
      )}
      {state === "success" && alerts && alerts.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{fr.cockpit.alerts.title}</caption>
            <thead className="text-muted-foreground">
              <tr className="border-b">
                <th scope="col" className="py-2 pr-4 font-medium">{fr.cockpit.alerts.columns.severity}</th>
                <th scope="col" className="py-2 pr-4 font-medium">{fr.cockpit.alerts.columns.target}</th>
                <th scope="col" className="py-2 pr-4 font-medium">{fr.cockpit.alerts.columns.message}</th>
                <th scope="col" className="py-2 text-right font-medium">{fr.cockpit.alerts.columns.age}</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id} className="border-b align-top">
                  <td className="py-2 pr-4">
                    <Badge variant={a.severity === "critical" ? "danger" : "default"}>
                      {fr.cockpit.alerts.severity[a.severity] ?? a.severity}
                    </Badge>
                  </td>
                  <td className="py-2 pr-4">
                    {(fr.cockpit.alerts.target[a.target_kind] ?? a.target_kind)}
                    {a.target_id && names.get(a.target_id) && <span className="font-mono"> {names.get(a.target_id)}</span>}
                  </td>
                  <td className="py-2 pr-4">{a.message}</td>
                  <td className="py-2 text-right font-mono whitespace-nowrap">
                    {formatAge(nowMs - Date.parse(a.created_at))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function HealthPanel({
  health,
  failed,
  nowIso,
  dimmed,
}: {
  health: HealthReport | undefined;
  failed: boolean;
  nowIso: string;
  dimmed: boolean;
}) {
  return (
    <section aria-labelledby="health-title" className="flex flex-col gap-3" data-dimmed={dimmed || undefined}>
      <h2 id="health-title" className="text-xl font-semibold tracking-tight">
        {fr.cockpit.health.title}
      </h2>
      {failed && <p className="text-sm font-medium">{fr.cockpit.health.error}</p>}
      {!failed && !health && <Skeleton className="h-16" role="status" aria-label={fr.cockpit.health.loading} />}
      {!failed && health && (
        <ul className="flex flex-col divide-y border-y">
          {CHECKS.map((name) => {
            const check = health.checks[name];
            const Icon = check?.status === "ok" ? CircleCheckIcon : CircleXIcon;
            return (
              <li key={name} className="flex flex-col gap-1 py-2 text-sm">
                <div className="flex items-center justify-between gap-4">
                  <span className="flex items-center gap-2">
                    <Icon className="size-4 shrink-0" aria-hidden="true" />
                    {fr.cockpit.health.names[name]}
                  </span>
                  <ObservedValue
                    mono={false}
                    value={check ? fr.cockpit.health[check.status] : "unknown"}
                    observedAt={check?.observed_at}
                    serverTime={nowIso}
                    staleAfterMs={HEALTH_STALE_MS}
                    className={check?.status === "down" ? "font-semibold" : undefined}
                  />
                </div>
                {check && (
                  <span className="pl-6 font-mono text-xs text-muted-foreground">
                    {fr.cockpit.health.observedAt(formatTimestamp(check.observed_at))}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
