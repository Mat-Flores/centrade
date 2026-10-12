import { ObservedValue } from "@/components/observed-value";
import { TableShell, TD, TDR, TH, THEAD, THR } from "@/components/data-table";
import { Button } from "@/components/ui/button";
import { fr } from "@/i18n/fr";
import { ENGINE_STALE_MS } from "@/lib/cockpit";
import type { Instance } from "@/lib/instances";
import type { Order } from "@/lib/trading";
import { InstanceCell, num } from "./cells";

const t = fr.orders.ordersList;
// L'action (annuler, ou pourquoi elle n'existe pas) reste collée à droite quand le tableau défile.
const PIN = "sticky right-0 z-[1] min-w-44 border-l bg-card";

/**
 * Ordres en cours. Le bouton d'annulation n'existe que pour un ordre d'entrée encore ouvert (`cancelable`) ;
 * pour une sortie ou un stop, la ligne dit pourquoi il n'y en a pas (annuler augmenterait le risque).
 */
export function OrdersTable({
  orders,
  instances,
  nowIso,
  canAct,
  dimmed,
  whyId,
  onCancel,
}: {
  orders: Order[];
  instances: ReadonlyMap<string, Instance>;
  nowIso: string;
  canAct: boolean;
  dimmed: boolean;
  whyId: string;
  onCancel: (o: Order) => void;
}) {
  return (
    <TableShell label={t.list} dimmed={dimmed} minWidth="min-w-[52rem]">
      <thead className={THEAD}>
        <tr>
          <th scope="col" className={TH}>{t.columns.instance}</th>
          <th scope="col" className={TH}>{t.columns.instrument}</th>
          <th scope="col" className={TH}>{t.columns.intent}</th>
          <th scope="col" className={TH}>{t.columns.status}</th>
          <th scope="col" className={THR}>{t.columns.quantity}</th>
          <th scope="col" className={THR}>{t.columns.price}</th>
          <th scope="col" className={`${TH} ${PIN}`}>{t.columns.action}</th>
        </tr>
      </thead>
      <tbody className="divide-y">
        {orders.map((o) => {
          const name = instances.get(o.instance_id)?.name ?? fr.orders.unknownInstance;
          const entry = o.intent === "entry" || o.intent === "increase";
          return (
            <tr key={o.id} data-order={o.client_order_id} data-intent={o.intent}>
              <td className={TD}>
                <InstanceCell id={o.instance_id} nowIso={nowIso} instances={instances} />
              </td>
              <td className={TD}>
                <span className="font-mono">{o.instrument}</span>
                <p className="text-xs text-muted-foreground">{t.sides[o.side] ?? o.side}</p>
              </td>
              <td className={TD}>{t.intents[o.intent] ?? o.intent}</td>
              <td className={TD}>
                <ObservedValue value={o.status} observedAt={o.observed_at} serverTime={nowIso} staleAfterMs={ENGINE_STALE_MS} />
              </td>
              <td className={TDR}>
                <ObservedValue mono value={num(o.quantity)} observedAt={o.observed_at} serverTime={nowIso} staleAfterMs={ENGINE_STALE_MS} className="justify-end" />
              </td>
              <td className={TDR}>
                {o.price === null ? (
                  <span className="font-sans text-muted-foreground">{t.noPrice}</span>
                ) : (
                  <ObservedValue mono value={`${num(o.price)}\u00a0${o.currency}`} observedAt={o.observed_at} serverTime={nowIso} staleAfterMs={ENGINE_STALE_MS} className="justify-end" />
                )}
              </td>
              <td className={`${TD} ${PIN}`}>
                {o.cancelable && entry ? (
                  canAct ? (
                    <Button type="button" variant="outline" aria-label={t.cancelLabel(o.instrument, name)} onClick={() => onCancel(o)}>
                      {t.cancel}
                    </Button>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )
                ) : entry ? (
                  <span className="text-muted-foreground">{t.notOpen}</span>
                ) : (
                  <span aria-describedby={whyId} className="text-muted-foreground">
                    {t.notCancelable}
                    <span className="block text-xs">{t.notCancelableReason}</span>
                  </span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </TableShell>
  );
}
