import { useQuery } from "@tanstack/react-query";
import { TriangleAlertIcon } from "lucide-react";

import type { PersistentBarProps } from "@/components/persistent-bar";
import { fr } from "@/i18n/fr";
import { degradation, deriveCheck, deriveEngines, deriveMode, type Degradation } from "@/lib/cockpit";
import { useServerNow } from "@/lib/clock";
import { alertsQuery, healthQuery, instancesQuery } from "@/lib/instances";
import { useCockpitStream } from "@/lib/stream";

function DegradedBanner({ causes }: { causes: Degradation["causes"] }) {
  const d = fr.cockpit.degraded;
  const text = { stream: d.stream, health: d.health, "health-unknown": d.healthUnknown };
  return (
    <div className="flex items-start gap-3 border-t-2 border-foreground bg-muted px-4 py-3 text-sm sm:px-6">
      <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <p>
        <span className="font-semibold">{d.title}.</span> {causes.map((c) => text[c]).join(" ")} {d.rule}
      </p>
    </div>
  );
}

/** Données de la barre persistante, communes à tous les écrans : mode, connexions, alertes, mode dégradé. */
export function useShellBar() {
  const instances = useQuery(instancesQuery);
  const alerts = useQuery(alertsQuery);
  const health = useQuery(healthQuery);
  const { silentMs } = useCockpitStream();
  const nowIso = useServerNow();
  const nowMs = Date.parse(nowIso);

  const report = health.isError ? undefined : health.data;
  const degraded = degradation({ streamSilentMs: silentMs, health: report, healthFailed: health.isError });
  const items = instances.data?.items;
  const bar: Partial<PersistentBarProps> = {
    mode: deriveMode(items),
    connections: {
      engines: deriveEngines(items, nowMs),
      bus: deriveCheck(report, "bus"),
      database: deriveCheck(report, "database"),
    },
    alertCount: alerts.data ? alerts.data.items.length : null,
    degradedBanner: degraded.degraded ? <DegradedBanner causes={degraded.causes} /> : undefined,
  };
  return { bar, instances, alerts, health, report, degraded, items, nowIso };
}
