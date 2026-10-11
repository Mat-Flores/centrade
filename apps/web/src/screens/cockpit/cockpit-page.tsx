import { useQuery } from "@tanstack/react-query";
import { TriangleAlertIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { fr } from "@/i18n/fr";
import { useAnnouncement } from "@/lib/announce";
import { degradation, deriveCheck, deriveEngines, deriveMode, type Degradation } from "@/lib/cockpit";
import { useServerNow } from "@/lib/clock";
import { alertsQuery, commandsQuery, healthQuery, instancesQuery } from "@/lib/instances";
import type { Me } from "@/lib/session";
import { useCockpitStream } from "@/lib/stream";
import type { Theme } from "@/lib/theme";
import { CockpitScreen } from "./cockpit-screen";

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

/** Branche le Cockpit : requêtes, flux temps réel, mode dégradé, barre persistante. */
export function CockpitPage({ me, theme, onToggleTheme }: { me: Me; theme: Theme; onToggleTheme: () => void }) {
  const instances = useQuery(instancesQuery);
  const commands = useQuery(commandsQuery);
  const alerts = useQuery(alertsQuery);
  const health = useQuery(healthQuery);
  const { silentMs } = useCockpitStream();
  const nowIso = useServerNow();
  const nowMs = Date.parse(nowIso);

  const report = health.isError ? undefined : health.data;
  const degraded = degradation({ streamSilentMs: silentMs, health: report, healthFailed: health.isError });
  const items = instances.data?.items;
  const announced = useAnnouncement(
    { instances: items ?? [], commands: commands.data?.items ?? [], alerts: alerts.data?.items ?? [], degraded: degraded.degraded },
    !!instances.data && !!commands.data && !!alerts.data,
  );

  return (
    <>
      <AppShell
        me={me}
        theme={theme}
        onToggleTheme={onToggleTheme}
        bar={{
          mode: deriveMode(items),
          connections: {
            engines: deriveEngines(items, nowMs),
            bus: deriveCheck(report, "bus"),
            database: deriveCheck(report, "database"),
          },
          alertCount: alerts.data ? alerts.data.items.length : null,
          degradedBanner: degraded.degraded ? <DegradedBanner causes={degraded.causes} /> : undefined,
        }}
      >
        <CockpitScreen
          nowIso={nowIso}
          degraded={degraded.degraded}
          canAct={me.role === "operator" || me.role === "admin"}
          isAdmin={me.role === "admin"}
          instances={{
            state: instances.isPending ? "pending" : instances.isError ? "error" : "success",
            items: items ?? [],
            retry: () => void instances.refetch(),
          }}
          commands={commands.data?.items ?? []}
          alerts={{
            state: alerts.isPending ? "pending" : alerts.isError ? "error" : "success",
            items: alerts.data?.items,
          }}
          health={{ report, failed: health.isError }}
        />
      </AppShell>
      {/* Toujours montée : seul son texte change, ce qui le fait annoncer (WCAG 4.1.3). */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only" data-live-region>
        {announced}
      </div>
    </>
  );
}
