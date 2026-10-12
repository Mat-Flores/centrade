import { ObservedValue } from "@/components/observed-value";
import { TableShell, TD, TDR, TH, THEAD, THR } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fr } from "@/i18n/fr";
import { ENGINE_STALE_MS } from "@/lib/cockpit";
import type { Instance } from "@/lib/instances";
import type { Position } from "@/lib/trading";
import { InstanceCell, num, Ts } from "./cells";

const t = fr.orders.positions;
// L'état de protection et la fermeture ne sortent jamais du champ : ces colonnes restent collées à droite quand le tableau défile.
const PIN = "sticky z-[1] bg-card";
const PROT = `${PIN} min-w-44 border-l`;

function Protection({ p, nowIso }: { p: Position; nowIso: string }) {
  // Une position non protégée s'affiche toujours : l'alarme n'est jamais estompée ni masquée par l'âge.
  const badge =
    p.protection_state === "unprotected" ? (
      <Badge variant="danger">{t.protection.unprotected}</Badge>
    ) : (
      <ObservedValue
        value={p.protection_state === "unknown" ? "unknown" : <Badge variant="default">{t.protection[p.protection_state]}</Badge>}
        observedAt={p.protection_verified_at}
        serverTime={nowIso}
        staleAfterMs={ENGINE_STALE_MS}
      />
    );
  return (
    <div className="flex flex-col items-start gap-1" data-protection={p.protection_state}>
      {badge}
      <span className="text-xs text-muted-foreground">{t.protectionDetail[p.protection_state]}</span>
      <span className="text-xs text-muted-foreground">
        {p.protection_verified_at ? (
          <>
            {t.verifiedAt} <Ts iso={p.protection_verified_at} serverTime={nowIso} />
          </>
        ) : (
          t.neverVerified
        )}
      </span>
    </div>
  );
}

function Stop({ p, nowIso }: { p: Position; nowIso: string }) {
  if (p.stop_price === null) {
    return p.protection_state === "unknown" ? (
      <ObservedValue value="unknown" observedAt={null} serverTime={nowIso} staleAfterMs={ENGINE_STALE_MS} />
    ) : (
      <span className="font-medium">{t.noStop}</span>
    );
  }
  return (
    <ObservedValue
      observedAt={p.observed_at}
      serverTime={nowIso}
      staleAfterMs={ENGINE_STALE_MS}
      value={
        <span className="flex flex-col items-start">
          <span className="font-mono">{num(p.stop_price)}</span>
          <span className="text-xs text-muted-foreground" title={t.stopDistanceHint}>
            {p.stop_distance_pct === null ? "" : t.stopDistance(num(p.stop_distance_pct, true))}
          </span>
          <span className="text-xs text-muted-foreground">
            {[p.stop_venue && (t.venues[p.stop_venue] ?? p.stop_venue), p.stop_type && (t.stopTypes[p.stop_type] ?? p.stop_type)].filter(Boolean).join(", ")}
          </span>
        </span>
      }
    />
  );
}

/** Positions ouvertes, les moins protégées en tête (tri fait par l'appelant). Fermer reste possible quel que soit l'état (I4). */
export function PositionsTable({
  positions,
  instances,
  nowIso,
  canAct,
  dimmed,
  onClose,
}: {
  positions: Position[];
  instances: ReadonlyMap<string, Instance>;
  nowIso: string;
  canAct: boolean;
  dimmed: boolean;
  onClose: (p: Position) => void;
}) {
  return (
    <TableShell label={t.list} dimmed={dimmed} minWidth="min-w-[46rem]">
      <thead className={THEAD}>
        <tr>
          <th scope="col" className={TH}>{t.columns.instance}</th>
          <th scope="col" className={TH}>{t.columns.instrument}</th>
          <th scope="col" className={THR}>{t.columns.quantity}</th>
          <th scope="col" className={THR}>{t.columns.entry}</th>
          <th scope="col" className={`${TH} min-w-32`}>{t.columns.stop}</th>
          <th scope="col" className={`${TH} ${PROT} ${canAct ? "right-28" : "right-0"}`}>{t.columns.protection}</th>
          {canAct && <th scope="col" className={`${TH} ${PIN} right-0 w-28`}>{t.columns.action}</th>}
        </tr>
      </thead>
      <tbody className="divide-y">
        {positions.map((p) => {
          const name = instances.get(p.instance_id)?.name ?? fr.orders.unknownInstance;
          return (
            <tr key={p.id} data-position={p.instrument} data-protection={p.protection_state}>
              <td className={TD}>
                <InstanceCell id={p.instance_id} nowIso={nowIso} instances={instances} />
              </td>
              <td className={TD}>
                <span className="font-mono">{p.instrument}</span>
                <p className="text-xs text-muted-foreground">{t.sides[p.side] ?? p.side}</p>
              </td>
              <td className={TDR}>
                <ObservedValue mono value={num(p.quantity)} observedAt={p.observed_at} serverTime={nowIso} staleAfterMs={ENGINE_STALE_MS} className="justify-end" />
              </td>
              <td className={TDR}>
                <ObservedValue mono value={p.entry_price === null ? "unknown" : `${num(p.entry_price)}\u00a0${p.currency}`} observedAt={p.observed_at} serverTime={nowIso} staleAfterMs={ENGINE_STALE_MS} className="justify-end" />
              </td>
              <td className={TD}>
                <Stop p={p} nowIso={nowIso} />
              </td>
              <td className={`${TD} ${PROT} ${canAct ? "right-28" : "right-0"}`}>
                <Protection p={p} nowIso={nowIso} />
              </td>
              {canAct && (
                <td className={`${TD} ${PIN} right-0 w-28`}>
                  <Button type="button" variant="outline" aria-label={t.closeLabel(p.instrument, name)} onClick={() => onClose(p)}>
                    {t.close}
                  </Button>
                </td>
              )}
            </tr>
          );
        })}
      </tbody>
    </TableShell>
  );
}
