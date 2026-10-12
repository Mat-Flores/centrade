import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlertIcon } from "lucide-react";
import { useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { fr } from "@/i18n/fr";
import { useSearch } from "@/lib/router";
import { changeStatus, NEXT_STATUS, strategiesQuery, versionsKey, versionsQuery, type Strategy, type Version } from "@/lib/strategies";
import { DepositDialog } from "./deposit-dialog";
import { InstancesPanel } from "./instances-panel";
import { StrategyList } from "./strategy-list";
import { VersionPanel } from "./version-panel";
import { VersionsTable } from "./versions-table";

const t = fr.strategies;

function Failure({ title, body, onRetry }: { title: string; body: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-start gap-3">
      <Alert role="alert">
        <CircleAlertIcon />
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription>{body}</AlertDescription>
      </Alert>
      <Button type="button" onClick={onRetry}>
        {t.loadError.retry}
      </Button>
    </div>
  );
}

function StrategyView({ strategy, versionNumber, canAct, isAdmin, degraded, nowIso, onNotice }: { strategy: Strategy; versionNumber: number | null; canAct: boolean; isAdmin: boolean; degraded: boolean; nowIso: string; onNotice: (m: string) => void }) {
  const qc = useQueryClient();
  const versions = useQuery(versionsQuery(strategy.id));
  const [depositing, setDepositing] = useState(false);
  const [advancing, setAdvancing] = useState<number | null>(null);
  const advance = useMutation({
    mutationFn: (v: Version) => changeStatus(v.strategy_id, v.version, NEXT_STATUS[v.status]!),
    onMutate: (v) => setAdvancing(v.version),
    onSuccess: (v) => onNotice(t.versions.advanceDone(v.version, t.versions.status[v.status] ?? v.status)),
    onSettled: async () => {
      setAdvancing(null);
      await qc.invalidateQueries({ queryKey: versionsKey(strategy.id) });
    },
  });

  const items = versions.data?.items ?? [];
  const selected = items.find((v) => v.version === versionNumber) ?? null;
  return (
    <div className="flex min-w-0 flex-col gap-8">
      <section aria-labelledby="versions-title" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="versions-title" className="text-xl font-semibold tracking-tight">
            {t.versions.title(strategy.name)}
          </h2>
          {canAct && (
            <Button type="button" variant="outline" onClick={() => setDepositing(true)}>
              {t.versions.deposit}
            </Button>
          )}
        </div>
        <p className="max-w-3xl text-sm text-muted-foreground">{t.versions.immutable}</p>
        {versions.isPending && <Skeleton role="status" aria-label={t.loading} className="h-24 w-full" />}
        {versions.isError && <Failure title={t.loadError.title} body={t.loadError.body} onRetry={() => void versions.refetch()} />}
        {advance.isError && (
          <Alert role="alert">
            <CircleAlertIcon />
            <AlertDescription>{t.versions.advanceError}</AlertDescription>
          </Alert>
        )}
        {versions.data && items.length === 0 && (
          <Empty className="min-h-32 border">
            <EmptyHeader>
              <EmptyTitle className="text-base">{t.versions.empty}</EmptyTitle>
            </EmptyHeader>
          </Empty>
        )}
        {versions.data && items.length > 0 && (
          <VersionsTable versions={items} strategyId={strategy.id} selected={versionNumber} serverTime={versions.data.server_time} canAct={canAct} advancing={advancing} onAdvance={(v) => advance.mutate(v)} />
        )}
      </section>

      {selected && versions.data && <VersionPanel strategyName={strategy.name} version={selected} serverTime={versions.data.server_time} canAct={canAct} onNotice={onNotice} />}

      <InstancesPanel strategyId={strategy.id} nowIso={nowIso} degraded={degraded} canAct={canAct} isAdmin={isAdmin} />

      {depositing && (
        <DepositDialog
          strategyId={strategy.id}
          strategyName={strategy.name}
          onClose={() => setDepositing(false)}
          onDone={async (v) => {
            setDepositing(false);
            onNotice(t.deposit.done(v.version));
            await qc.invalidateQueries({ queryKey: versionsKey(strategy.id) });
          }}
        />
      )}
    </div>
  );
}

export interface StrategiesScreenProps {
  canAct: boolean;
  isAdmin: boolean;
  degraded: boolean;
  nowIso: string;
}

/** Écran 2 : registre, versions, détail, déploiement en paper, instances et « Ce qui tourne réellement ». */
export function StrategiesScreen({ canAct, isAdmin, degraded, nowIso }: StrategiesScreenProps) {
  const search = useSearch();
  const strategies = useQuery(strategiesQuery);
  const [notice, setNotice] = useState<string | null>(null);
  const selectedId = search.get("s");
  const v = Number(search.get("v"));
  const versionNumber = Number.isInteger(v) && v > 0 ? v : null;
  const items = strategies.data?.items ?? [];
  const selected = items.find((s) => s.id === selectedId) ?? null;

  return (
    <>
      <p className="max-w-3xl text-muted-foreground">{t.intro}</p>
      {!canAct && <p className="max-w-3xl text-sm font-medium">{t.readOnly}</p>}
      <div role="status" aria-live="polite" className="empty:hidden">
        {notice && (
          <Alert>
            <AlertDescription>{notice}</AlertDescription>
          </Alert>
        )}
      </div>

      {strategies.isPending && <Skeleton role="status" aria-label={t.loading} className="h-32 w-full" />}
      {strategies.isError && <Failure title={t.loadError.title} body={t.loadError.body} onRetry={() => void strategies.refetch()} />}
      {strategies.data && (
        <div className="grid gap-8 2xl:grid-cols-[18rem_minmax(0,1fr)]">
          <section aria-labelledby="strategies-title" className="flex flex-col gap-3">
            <h2 id="strategies-title" className="text-xl font-semibold tracking-tight">
              {t.list.title}
            </h2>
            <StrategyList items={items} selectedId={selectedId} canAct={canAct} onNotice={setNotice} />
          </section>
          {selected ? (
            <StrategyView key={selected.id} strategy={selected} versionNumber={versionNumber} canAct={canAct} isAdmin={isAdmin} degraded={degraded} nowIso={nowIso} onNotice={setNotice} />
          ) : (
            <p className="text-muted-foreground">{t.pick}</p>
          )}
        </div>
      )}
    </>
  );
}
