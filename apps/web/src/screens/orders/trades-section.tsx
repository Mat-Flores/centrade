import { TableShell, TD, TDR, TH, THEAD, THR } from "@/components/data-table";
import { fr } from "@/i18n/fr";
import { formatPnl, formatTimestamp } from "@/lib/format";
import type { Instance } from "@/lib/instances";
import { exitBreakdown, totalsByModeCurrency, type Breakdown, type Trade } from "@/lib/trading";
import { attempt } from "@/screens/accounts/cells";
import { InstanceCell, ModeMark, num } from "./cells";

const t = fr.orders.trades;
const causeLabel = (c: string) => t.causes[c] ?? c;

const pnl = (amount: string, currency: string) => attempt(() => formatPnl(amount, currency)) ?? fr.orders.unreadable;

/** Totaux par (mode, devise) : une ligne chacun, jamais de somme entre deux d'entre eux. */
function Totals({ trades }: { trades: Trade[] }) {
  const totals = totalsByModeCurrency(trades);
  return (
    <section aria-labelledby="totals-title" className="flex flex-col gap-2">
      <h3 id="totals-title" className="text-base font-semibold">{t.totalsTitle}</h3>
      <p className="text-sm text-muted-foreground">{t.totalsHint}</p>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {totals.map((x) => (
          <li key={`${x.mode}|${x.currency}`} data-total={`${x.mode}|${x.currency}`} className="flex flex-col gap-1 rounded-lg border p-3">
            <ModeMark mode={x.mode} />
            <p className="text-sm text-muted-foreground">{t.pnl}</p>
            <p className="font-mono text-lg font-semibold">{pnl(x.pnl, x.currency)}</p>
            <p className="text-sm text-muted-foreground">
              {t.fees} <span className="font-mono">{num(x.fees)}&nbsp;{x.currency}</span> · {t.totalLine(x.count)}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Répartition des sorties par cause : barres horizontales, une seule teinte neutre (la longueur porte la
 * quantité, le libellé direct porte l'identité : aucune couleur à distinguer). Le détail chiffré est écrit
 * à droite de chaque barre, donc la figure se lit aussi sans la voir.
 */
function Breakdowns({ trades, instances }: { trades: Trade[]; instances: ReadonlyMap<string, Instance> }) {
  const groups = exitBreakdown(trades);
  const modeOf = new Map(trades.map((x) => [x.instance_id, x.mode]));
  return (
    <section aria-labelledby="breakdown-title" className="flex flex-col gap-3">
      <h3 id="breakdown-title" className="text-base font-semibold">{t.breakdownTitle}</h3>
      <div className="grid gap-4 lg:grid-cols-2">
        {groups.map((g: Breakdown) => {
          const name = instances.get(g.instanceId)?.name ?? fr.orders.unknownInstance;
          const max = Math.max(...g.causes.map((c) => c.count));
          return (
            <figure key={g.instanceId} data-breakdown={name} className="flex flex-col gap-2 rounded-lg border p-3">
              <figcaption className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-mono font-semibold">{name}</span>
                {modeOf.get(g.instanceId) && <ModeMark mode={modeOf.get(g.instanceId)!} />}
                <span className="text-sm text-muted-foreground">{t.breakdownTotal(g.total)}</span>
              </figcaption>
              <ul className="flex flex-col gap-1.5">
                {g.causes.map((c) => {
                  const pct = Math.round((c.count * 100) / g.total);
                  return (
                    <li key={c.cause} data-cause={c.cause} title={t.breakdownRow(causeLabel(c.cause), c.count, pct)} className="grid grid-cols-[minmax(8rem,12rem)_1fr_auto] items-center gap-3 text-sm">
                      <span>{causeLabel(c.cause)}</span>
                      <span aria-hidden="true" className="h-3 rounded-r-sm bg-muted-foreground/70" style={{ width: `${Math.max(2, (c.count * 100) / max)}%` }} />
                      <span className="font-mono whitespace-nowrap">
                        {c.count} · {pct}&nbsp;%
                      </span>
                    </li>
                  );
                })}
              </ul>
            </figure>
          );
        })}
      </div>
    </section>
  );
}

function when(iso: string): string {
  return attempt(() => formatTimestamp(iso)) ?? fr.orders.unreadable;
}

export function TradesSection({ trades, instances, dimmed }: { trades: Trade[]; instances: ReadonlyMap<string, Instance>; dimmed: boolean }) {
  return (
    <div className="flex flex-col gap-6" data-dimmed={dimmed || undefined}>
      <Totals trades={trades} />
      <Breakdowns trades={trades} instances={instances} />
      <TableShell label={t.list} dimmed={dimmed} minWidth="min-w-[58rem]">
        <thead className={THEAD}>
          <tr>
            <th scope="col" className={TH}>{t.columns.instance}</th>
            <th scope="col" className={TH}>{t.columns.instrument}</th>
            <th scope="col" className={THR}>{t.columns.quantity}</th>
            <th scope="col" className={THR}>{t.columns.prices}</th>
            <th scope="col" className={TH}>{t.columns.cause}</th>
            <th scope="col" className={THR}>{t.columns.pnl}</th>
            <th scope="col" className={THR}>{t.columns.fees}</th>
            <th scope="col" className={TH}>{t.columns.closed}</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {trades.map((x) => (
            <tr key={x.id} data-trade={x.instrument} data-exit-cause={x.exit_cause}>
              <td className={TD}>
                <InstanceCell id={x.instance_id} mode={x.mode} instances={instances} />
              </td>
              <td className={`${TD} font-mono`}>{x.instrument}</td>
              <td className={TDR}>{num(x.quantity)}</td>
              <td className={TDR}>
                {num(x.entry_price)} → {num(x.exit_price)}
              </td>
              <td className={TD}>{causeLabel(x.exit_cause)}</td>
              <td className={TDR}>{pnl(x.pnl, x.currency)}</td>
              <td className={TDR}>
                {num(x.fees)}&nbsp;{x.currency}
              </td>
              <td className={`${TD} font-mono whitespace-nowrap`}>{when(x.closed_at)}</td>
            </tr>
          ))}
        </tbody>
      </TableShell>
    </div>
  );
}
