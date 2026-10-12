import { useQuery } from "@tanstack/react-query";
import { CircleAlertIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fr } from "@/i18n/fr";
import { versionQuery, type Version } from "@/lib/strategies";
import { DeployForm } from "./deploy-form";
import { CodeView, ExitPolicy, ManifestView, StaticChecks } from "./version-detail";

const t = fr.strategies.detail;

/** Détail d'une version : manifest, politique de sortie, contrôles, code (lecture seule) et déploiement en paper. */
export function VersionPanel({ strategyName, version, serverTime, canAct, onNotice }: { strategyName: string; version: Version; serverTime: string; canAct: boolean; onNotice: (m: string) => void }) {
  const detail = useQuery(versionQuery(version.strategy_id, version.version));
  return (
    <section aria-labelledby="version-title" className="flex flex-col gap-6 rounded-xl border bg-card p-4 sm:p-6" data-version-panel={version.version}>
      <div className="flex flex-col gap-1">
        <h3 id="version-title" className="text-xl font-semibold tracking-tight">
          <span className="font-mono">{t.title(strategyName, version.version)}</span>
        </h3>
        <p className="text-sm text-muted-foreground">{t.immutable}</p>
      </div>
      <ManifestView manifest={version.manifest} />
      <ExitPolicy exits={version.exits} />
      <StaticChecks checks={version.static_checks} serverTime={serverTime} />
      {detail.isPending && <Skeleton role="status" aria-label={fr.strategies.loading} className="h-11 w-full" />}
      {detail.isError && (
        <div className="flex flex-col items-start gap-2">
          <Alert role="alert">
            <CircleAlertIcon />
            <AlertDescription>{t.loadError}</AlertDescription>
          </Alert>
          <Button type="button" onClick={() => void detail.refetch()}>
            {fr.strategies.loadError.retry}
          </Button>
        </div>
      )}
      {detail.data && <CodeView code={detail.data.code} />}
      {canAct && <DeployForm key={version.id} version={version} onDone={onNotice} />}
    </section>
  );
}
