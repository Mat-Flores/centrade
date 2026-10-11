import { CircleAlertIcon } from "lucide-react";
import { useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { fr } from "@/i18n/fr";
import { countByState } from "@/lib/cockpit";
import type { ActionType, Alert as AlertItem, Command, HealthReport, Instance } from "@/lib/instances";
import { useSeenCommands } from "@/lib/seen";
import { cn } from "@/lib/utils";
import { ActionDialog, type PendingAction } from "./action-dialog";
import { CreateInstance } from "./create-instance";
import { InstanceRow } from "./instance-row";
import { AlertsPanel, HealthPanel } from "./side-panels";

type Load = "pending" | "error" | "success";

export interface CockpitScreenProps {
  nowIso: string;
  degraded: boolean;
  canAct: boolean;
  isAdmin: boolean;
  instances: { state: Load; items: Instance[]; retry: () => void };
  commands: Command[];
  alerts: { state: Load; items: AlertItem[] | undefined };
  health: { report: HealthReport | undefined; failed: boolean };
}

const SUMMARY_ORDER = ["running", "exits_only", "starting", "stopped", "halted", "error", "stale", "unknown"] as const;

export function CockpitScreen({ nowIso, degraded, canAct, isAdmin, instances, commands, alerts, health }: CockpitScreenProps) {
  const { seen, markSeen } = useSeenCommands();
  const [pending, setPending] = useState<PendingAction | null>(null);
  const nowMs = Date.parse(nowIso);
  const counts = countByState(instances.items, nowMs);

  const open = (instance: Instance, action: ActionType) =>
    setPending({ instanceId: instance.id, action, key: crypto.randomUUID() });

  return (
    <div className="flex flex-col gap-10">
      <section aria-labelledby="instances-title" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <h2 id="instances-title" className="text-xl font-semibold tracking-tight">
            {fr.cockpit.instances}
          </h2>
          {instances.state === "success" && instances.items.length > 0 && (
            <ul aria-label={fr.cockpit.summary.label} className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
              <li className="text-muted-foreground">{fr.cockpit.summary.total(instances.items.length)}</li>
              {SUMMARY_ORDER.filter((k) => counts[k]).map((key) => (
                <li key={key}>
                  <span className="font-mono font-medium">{counts[key]}</span>{" "}
                  {key === "stale"
                    ? fr.cockpit.summary.stale
                    : key === "unknown"
                      ? fr.cockpit.summary.unknown
                      : fr.cockpit.states[key]}
                </li>
              ))}
            </ul>
          )}
        </div>

        {instances.state === "pending" && (
          <div role="status" aria-label={fr.cockpit.loading} className="flex flex-col divide-y rounded-xl border bg-card">
            {[0, 1, 2].map((n) => (
              <div key={n} className="flex flex-col gap-3 p-5">
                <Skeleton className="h-6 w-40" />
                <Skeleton className="h-5 w-64" />
                <Skeleton className="h-11 w-full max-w-md" />
              </div>
            ))}
          </div>
        )}

        {instances.state === "error" && (
          <div className="flex flex-col items-start gap-3">
            <Alert role="alert">
              <CircleAlertIcon />
              <AlertTitle>{fr.cockpit.loadError.title}</AlertTitle>
              <AlertDescription>{fr.cockpit.loadError.body}</AlertDescription>
            </Alert>
            <Button type="button" onClick={instances.retry}>
              {fr.cockpit.loadError.retry}
            </Button>
          </div>
        )}

        {instances.state === "success" && instances.items.length === 0 && (
          <Empty className="min-h-56 border">
            <EmptyHeader>
              <EmptyTitle className="text-base">{fr.cockpit.empty.title}</EmptyTitle>
              <EmptyDescription>{canAct ? fr.cockpit.empty.body : fr.cockpit.empty.bodyViewer}</EmptyDescription>
            </EmptyHeader>
            {canAct && <CreateInstance degraded={degraded} />}
          </Empty>
        )}

        {instances.state === "success" && instances.items.length > 0 && (
          <>
            <ul
              className={cn("flex flex-col divide-y rounded-xl border bg-card text-card-foreground shadow-panel")}
              data-degraded={degraded || undefined}
            >
              {instances.items.map((instance) => (
                <InstanceRow
                  key={instance.id}
                  instance={instance}
                  commands={commands}
                  nowIso={nowIso}
                  degraded={degraded}
                  canAct={canAct}
                  isAdmin={isAdmin}
                  seen={seen}
                  onSeen={markSeen}
                  onAction={open}
                />
              ))}
            </ul>
            {canAct && <CreateInstance degraded={degraded} />}
          </>
        )}
      </section>

      <div className="grid gap-10 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <AlertsPanel
          alerts={alerts.items}
          instances={instances.items}
          nowIso={nowIso}
          state={alerts.state}
          dimmed={degraded}
        />
        <HealthPanel health={health.report} failed={health.failed} nowIso={nowIso} dimmed={degraded} />
      </div>

      {pending && (
        <ActionDialog
          key={pending.key}
          pending={pending}
          instance={instances.items.find((i) => i.id === pending.instanceId)}
          nowIso={nowIso}
          onClose={() => setPending(null)}
        />
      )}
    </div>
  );
}
