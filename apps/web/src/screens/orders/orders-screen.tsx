import { useQuery } from "@tanstack/react-query";
import { CircleAlertIcon } from "lucide-react";
import { useId, useMemo, useState, type ReactNode } from "react";

import { CommandHistory } from "@/components/command-history";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Field, FieldLabel } from "@/components/ui/field";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { fr } from "@/i18n/fr";
import { accountsQuery } from "@/lib/accounts";
import { commandsQuery, type Instance } from "@/lib/instances";
import { useSeenCommands } from "@/lib/seen";
import { NO_FILTERS, ordersQuery, positionsQuery, sortPositions, tradesQuery, type Order, type Position } from "@/lib/trading";
import { OrdersTable } from "./orders-table";
import { PositionsTable } from "./positions-table";
import { TradeActionDialog, type TradeAction } from "./trade-action-dialog";
import { TradesSection } from "./trades-section";

const t = fr.orders;
const TRADING_COMMANDS = new Set(["close_position", "cancel_entry_order"]);

interface Load<T> {
  isPending: boolean;
  isError: boolean;
  data: { items: T[]; next_cursor: string | null } | undefined;
  refetch: () => unknown;
}

/** Chargement, erreur (cause + action) et liste vide (message utile) de chaque section. */
function Section<T>({ id, title, load, empty, aside, children }: { id: string; title: string; load: Load<T>; empty: string; aside?: ReactNode; children: (items: T[]) => ReactNode }) {
  const items = load.data?.items;
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <h2 id={id} className="text-xl font-semibold tracking-tight">
          {title}
        </h2>
        {aside}
      </div>
      {load.isPending && (
        <div role="status" aria-label={t.loading} className="flex flex-col gap-2 rounded-xl border bg-card p-4">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-11 w-full" />
        </div>
      )}
      {load.isError && (
        <div className="flex flex-col items-start gap-3">
          <Alert role="alert">
            <CircleAlertIcon />
            <AlertTitle>{t.loadError.title}</AlertTitle>
            <AlertDescription>{t.loadError.body}</AlertDescription>
          </Alert>
          <Button type="button" onClick={() => void load.refetch()}>
            {t.loadError.retry}
          </Button>
        </div>
      )}
      {items && items.length === 0 && (
        <Empty className="min-h-32 border">
          <EmptyHeader>
            <EmptyTitle className="text-base">{empty}</EmptyTitle>
          </EmptyHeader>
        </Empty>
      )}
      {items && items.length > 0 && (
        <>
          {children(items)}
          {load.data?.next_cursor != null && <p className="text-sm text-muted-foreground">{t.truncated(items.length)}</p>}
        </>
      )}
    </section>
  );
}

export interface OrdersScreenProps {
  canAct: boolean;
  degraded: boolean;
  nowIso: string;
  instances: Instance[] | undefined;
}

/**
 * Écran 3 : positions, ordres, trades. Chaque valeur d'un moteur passe par `ObservedValue` (âge, péremption,
 * inconnu). Fermer et annuler une entrée réduisent le risque : ils restent actifs en mode dégradé (I4).
 */
export function OrdersScreen({ canAct, degraded, nowIso, instances }: OrdersScreenProps) {
  const filterId = useId();
  const whyId = useId();
  const [filters, setFilters] = useState(NO_FILTERS);
  const [action, setAction] = useState<TradeAction | null>(null);
  const { seen, markSeen } = useSeenCommands();

  const accounts = useQuery(accountsQuery);
  const positions = useQuery(positionsQuery(filters));
  const orders = useQuery(ordersQuery(filters));
  const trades = useQuery(tradesQuery(filters));
  const commands = useQuery(commandsQuery);

  const byId = useMemo(() => new Map((instances ?? []).map((i) => [i.id, i])), [instances]);
  const names = useMemo(() => new Map((instances ?? []).map((i) => [i.id, i.name])), [instances]);
  const tradingCommands = (commands.data?.items ?? []).filter((c) => TRADING_COMMANDS.has(c.type) && (!filters.instanceId || c.instance_id === filters.instanceId));

  const openClose = (position: Position) => setAction({ kind: "close", position, key: crypto.randomUUID() });
  const openCancel = (order: Order) => setAction({ kind: "cancel", order, key: crypto.randomUUID() });
  const instanceOf = (id: string) => byId.get(id);

  return (
    <>
      <p className="max-w-3xl text-muted-foreground">{t.intro}</p>
      {!canAct && <p className="max-w-3xl text-sm font-medium">{t.readOnly}</p>}

      <form role="search" aria-label={t.filters.label} onSubmit={(e) => e.preventDefault()} className="grid max-w-3xl gap-4 sm:grid-cols-2">
        <Field>
          <FieldLabel htmlFor={`${filterId}-instance`}>{t.filters.instance}</FieldLabel>
          <Select id={`${filterId}-instance`} value={filters.instanceId} onChange={(e) => setFilters({ ...filters, instanceId: e.target.value })}>
            <option value="">{t.filters.allInstances}</option>
            {(instances ?? []).map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field>
          <FieldLabel htmlFor={`${filterId}-account`}>{t.filters.account}</FieldLabel>
          <Select id={`${filterId}-account`} value={filters.accountId} onChange={(e) => setFilters({ ...filters, accountId: e.target.value })}>
            <option value="">{t.filters.allAccounts}</option>
            {(accounts.data?.items ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.label} ({a.type === "paper" ? `${t.modes.paper}, ${t.simulated}` : t.modes.live})
              </option>
            ))}
          </Select>
        </Field>
      </form>

      <Section<Position>
        id="positions-title"
        title={t.positions.title}
        load={positions}
        empty={t.positions.empty}
        aside={
          positions.data && (
            <p className="text-sm text-muted-foreground">
              {(() => {
                const n = positions.data.items.filter((p) => p.protection_state === "unprotected").length;
                return n > 0 ? <strong className="font-semibold text-foreground">{t.positions.unprotectedCount(n)}. </strong> : null;
              })()}
              {t.positions.unprotectedFirst}
            </p>
          )
        }
      >
        {(items) => <PositionsTable positions={sortPositions(items)} instances={byId} nowIso={nowIso} canAct={canAct} dimmed={degraded} onClose={openClose} />}
      </Section>

      <Section<Order>
        id="orders-title"
        title={t.ordersList.title}
        load={orders}
        empty={t.ordersList.empty}
        aside={
          <p id={whyId} className="max-w-xl text-sm text-muted-foreground">
            {t.ordersList.why}
          </p>
        }
      >
        {(items) => <OrdersTable orders={items} instances={byId} nowIso={nowIso} canAct={canAct} dimmed={degraded} whyId={whyId} onCancel={openCancel} />}
      </Section>

      <Section id="trades-title" title={t.trades.title} load={trades} empty={t.trades.empty}>
        {(items) => <TradesSection trades={items} instances={byId} dimmed={degraded} />}
      </Section>

      <section aria-labelledby="commands-title" className="flex flex-col gap-3">
        <h2 id="commands-title" className="text-xl font-semibold tracking-tight">
          {t.commands.title}
        </h2>
        <CommandHistory commands={tradingCommands} nowIso={nowIso} seen={seen} onSeen={markSeen} label={t.commands.title} names={names} />
      </section>

      {action && (
        <TradeActionDialog
          key={action.key}
          action={action}
          instance={instanceOf(action.kind === "close" ? action.position.instance_id : action.order.instance_id)}
          nowIso={nowIso}
          onClose={() => setAction(null)}
        />
      )}
    </>
  );
}
