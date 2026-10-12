import { useQuery, useQueries } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { CommandHistory } from "@/components/command-history";
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { fr } from "@/i18n/fr";
import { commandsQuery, type ActionType, type Instance } from "@/lib/instances";
import { useSeenCommands } from "@/lib/seen";
import { instanceDetailQuery } from "@/lib/strategies";
import { ActionDialog, type PendingAction } from "@/screens/cockpit/action-dialog";
import { InstanceRow } from "@/screens/cockpit/instance-row";
import { RunningPanel } from "./running-panel";

const t = fr.strategies.instances;

/**
 * Instances qui tournent une version de la stratégie, chacune avec son état voulu/observé, ses boutons d'action
 * (ceux du Cockpit : « fait » seulement sur `verified`), « Ce qui tourne réellement » et l'historique de ses commandes.
 * L'API ne filtre pas les instances par stratégie : le détail de chacune est lu, puis filtré ici.
 */
export function InstancesPanel({ strategyId, instances, nowIso, degraded, canAct, isAdmin }: { strategyId: string; instances: Instance[]; nowIso: string; degraded: boolean; canAct: boolean; isAdmin: boolean }) {
  const commands = useQuery(commandsQuery);
  const details = useQueries({ queries: instances.map((i) => instanceDetailQuery(i.id)) });
  const { seen, markSeen } = useSeenCommands();
  const [pending, setPending] = useState<PendingAction | null>(null);

  const byId = useMemo(() => new Map(instances.map((i) => [i.id, i])), [instances]);
  const loading = details.some((d) => d.isPending);
  const mine = details.flatMap((d) => (d.data && d.data.strategy?.strategy_id === strategyId ? [d.data] : []));
  const items = commands.data?.items ?? [];

  return (
    <section aria-labelledby="instances-title" className="flex flex-col gap-3">
      <h3 id="instances-title" className="text-xl font-semibold tracking-tight">{t.title}</h3>
      {loading && mine.length === 0 && <Skeleton role="status" aria-label={t.loading} className="h-24 w-full" />}
      {!loading && mine.length === 0 && (
        <Empty className="min-h-32 border">
          <EmptyHeader>
            <EmptyTitle className="text-base">{t.empty}</EmptyTitle>
          </EmptyHeader>
        </Empty>
      )}
      {mine.length > 0 && (
        <ul className="flex flex-col divide-y rounded-xl border bg-card text-card-foreground shadow-panel" data-degraded={degraded || undefined}>
          {mine.map((d) => {
            const instance = byId.get(d.id) ?? d;
            const own = items.filter((c) => c.instance_id === d.id);
            return (
              <InstanceRow
                key={d.id}
                instance={instance}
                commands={items}
                nowIso={nowIso}
                degraded={degraded}
                canAct={canAct}
                isAdmin={isAdmin}
                seen={seen}
                onSeen={markSeen}
                onAction={(i: Instance, action: ActionType) => setPending({ instanceId: i.id, action, key: crypto.randomUUID() })}
              >
                <RunningPanel detail={d} nowIso={nowIso} dimmed={degraded} />
                <div className="flex flex-col gap-2">
                  <h4 className="text-base font-semibold">{t.history}</h4>
                  <CommandHistory commands={own} nowIso={nowIso} seen={seen} onSeen={markSeen} label={`${t.history} : ${d.name}`} />
                </div>
                <dl className="grid gap-x-8 gap-y-1 text-sm text-muted-foreground sm:grid-cols-2">
                  <div>
                    <dt className="inline font-medium text-foreground">{t.logs} : </dt>
                    <dd className="inline">{t.logsSoon}</dd>
                  </div>
                  <div>
                    <dt className="inline font-medium text-foreground">{t.promotion} : </dt>
                    <dd className="inline">{t.promotionSoon}</dd>
                  </div>
                </dl>
              </InstanceRow>
            );
          })}
        </ul>
      )}
      {pending && <ActionDialog key={pending.key} pending={pending} instance={byId.get(pending.instanceId)} nowIso={nowIso} onClose={() => setPending(null)} />}
    </section>
  );
}
