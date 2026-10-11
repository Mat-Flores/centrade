import { useQuery } from "@tanstack/react-query";

import { AppShell } from "@/components/app-shell";
import { useShellBar } from "@/components/use-shell-bar";
import { useAnnouncement } from "@/lib/announce";
import { commandsQuery } from "@/lib/instances";
import type { Me } from "@/lib/session";
import type { Theme } from "@/lib/theme";
import { CockpitScreen } from "./cockpit-screen";

/** Branche le Cockpit : requêtes, flux temps réel, mode dégradé, barre persistante. */
export function CockpitPage({ me, theme, onToggleTheme }: { me: Me; theme: Theme; onToggleTheme: () => void }) {
  const { bar, instances, alerts, health, report, degraded, items, nowIso } = useShellBar();
  const commands = useQuery(commandsQuery);

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
        bar={bar}
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
