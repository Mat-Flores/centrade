import { AppLink } from "@/components/app-link";
import { TableShell, TD, TH, THEAD } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { pathWith, SCREEN_PATHS } from "@/lib/router";
import { NEXT_STATUS, shortHash, type Version } from "@/lib/strategies";
import { Ts } from "@/screens/accounts/cells";

const t = fr.strategies.versions;

/** Versions d'une stratégie, la plus récente d'abord. Aucune ligne n'est modifiable : seul le statut avance. */
export function VersionsTable({
  versions,
  strategyId,
  selected,
  serverTime,
  canAct,
  advancing,
  onAdvance,
}: {
  versions: Version[];
  strategyId: string;
  selected: number | null;
  serverTime: string;
  canAct: boolean;
  advancing: number | null;
  onAdvance: (v: Version) => void;
}) {
  return (
    <TableShell label={t.list} minWidth="min-w-[38rem]">
      <thead className={THEAD}>
        <tr>
          <th scope="col" className={TH}>{t.columns.version}</th>
          <th scope="col" className={TH}>{t.columns.status}</th>
          <th scope="col" className={TH}>{t.columns.hash}</th>
          <th scope="col" className={TH}>{t.columns.author}</th>
          <th scope="col" className={TH}>{t.columns.date}</th>
          <th scope="col" className={TH}>{t.columns.actions}</th>
        </tr>
      </thead>
      <tbody className="divide-y">
        {versions.map((v) => {
          const next = NEXT_STATUS[v.status];
          return (
            <tr key={v.id} data-version={v.version} aria-current={v.version === selected ? "true" : undefined}>
              <th scope="row" className={`${TD} text-left font-mono font-semibold`}>
                v{v.version}
                {v.version === selected && <span className="ml-2 font-sans text-xs font-normal text-muted-foreground">{t.current}</span>}
              </th>
              <td className={TD}>
                <Badge variant="default">{t.status[v.status] ?? v.status}</Badge>
              </td>
              <td className={`${TD} font-mono`} title={v.code_hash}>
                {shortHash(v.code_hash)}
              </td>
              <td className={`${TD} whitespace-nowrap`}>{v.author}</td>
              <td className={`${TD} whitespace-nowrap`}>
                <Ts iso={v.created_at} serverTime={serverTime} />
              </td>
              <td className={TD}>
                <div className="flex flex-wrap gap-2">
                  <AppLink
                    to={pathWith(SCREEN_PATHS.strategies, { s: strategyId, v: v.version })}
                    aria-label={t.detailsLabel(v.version)}
                    className="inline-flex min-h-11 items-center rounded-lg border px-4 text-base font-medium hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none"
                  >
                    {t.details}
                  </AppLink>
                  {canAct && next && (
                    <Button type="button" variant="outline" disabled={advancing !== null} aria-label={t.advanceLabel(t.advance[next] ?? next, v.version)} onClick={() => onAdvance(v)}>
                      {advancing === v.version && <Spinner data-icon="inline-start" />}
                      {t.advance[next] ?? next}
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </TableShell>
  );
}
