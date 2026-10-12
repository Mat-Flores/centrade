import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import type { Account, KeyUsage } from "@/lib/accounts";
import { formatMoney } from "@/lib/format";
import { attempt, IpCell, KeyCell, PermissionCell } from "./cells";

const t = fr.accounts;
const TH = "px-3 py-2 text-left text-sm font-medium text-muted-foreground";
const TD = "px-3 py-3 align-top";

function Cap({ account }: { account: Account }) {
  if (account.capital_cap === null) return <span className="text-muted-foreground">{t.noCap}</span>;
  const cap = account.capital_cap;
  const text = attempt(() => formatMoney(cap, account.currency));
  if (text === null) return <span className="text-muted-foreground">{t.unreadableDate}</span>;
  return (
    <>
      <span className="font-mono whitespace-nowrap">{text}</span>
      {account.type === "paper" && <p className="text-sm text-muted-foreground">{t.simulated}</p>}
    </>
  );
}

export function AccountTable({
  accounts,
  serverTime,
  canWrite,
  testingId,
  onKey,
  onTest,
}: {
  accounts: Account[];
  serverTime: string;
  canWrite: boolean;
  testingId: string | null;
  onKey: (account: Account, usage: KeyUsage, mode: "put" | "rotate") => void;
  onTest: (account: Account) => void;
}) {
  return (
    // tabIndex : une zone défilable doit se parcourir au clavier (WCAG 2.1.1).
    <div className="overflow-x-auto rounded-xl border bg-card" tabIndex={0} role="region" aria-label={t.list}>
      <table className="w-full min-w-[52rem] border-collapse text-sm">
        <caption className="sr-only">{t.list}</caption>
        <thead className="border-b">
          <tr>
            <th scope="col" className={TH}>{t.columns.account}</th>
            <th scope="col" className={TH}>{t.columns.environment}</th>
            <th scope="col" className={`${TH} text-right`}>{t.columns.cap}</th>
            <th scope="col" className={TH}>{t.columns.tradeKey}</th>
            <th scope="col" className={TH}>{t.columns.readKey}</th>
            <th scope="col" className={TH}>{t.columns.permissions}</th>
            <th scope="col" className={TH}>{t.columns.ip}</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {accounts.map((a) => {
            const live = a.type === "live";
            const canTest = canWrite && live && a.trade_key !== null;
            return (
              <tr key={a.id} data-account={a.label}>
                <th scope="row" className={`${TD} text-left font-normal`}>
                  <p className="text-base font-semibold">{a.label}</p>
                  <p className="font-mono text-muted-foreground">{a.venue}</p>
                  <Badge variant={live ? "live" : "default"} className="mt-1">
                    {t.types[a.type]}
                  </Badge>
                </th>
                <td className={TD}>
                  {t.environments[a.environment]}
                  <p className="text-muted-foreground">{a.currency}</p>
                </td>
                <td className={`${TD} text-right`}>
                  <Cap account={a} />
                </td>
                {live ? (
                  <>
                    <td className={TD}>
                      <KeyCell account={a} usage="trade" serverTime={serverTime} canWrite={canWrite} onAction={(m) => onKey(a, "trade", m)} />
                    </td>
                    <td className={TD}>
                      <KeyCell account={a} usage="read" serverTime={serverTime} canWrite={canWrite} onAction={(m) => onKey(a, "read", m)} />
                    </td>
                  </>
                ) : (
                  <td colSpan={2} className={`${TD} max-w-xs text-muted-foreground`}>
                    {t.key.paper}
                  </td>
                )}
                <td className={TD}>
                  <div className="flex flex-col items-start gap-2">
                    <PermissionCell account={a} serverTime={serverTime} />
                    {live && (
                      <Button
                        type="button"
                        variant="outline"
                        className="h-auto min-h-11 py-2 whitespace-normal"
                        disabled={!canTest || testingId !== null}
                        aria-label={`${t.permissions.test} : ${a.label}`}
                        onClick={() => onTest(a)}
                      >
                        {testingId === a.id && <Spinner data-icon="inline-start" />}
                        {testingId === a.id ? t.permissions.testing : t.permissions.test}
                      </Button>
                    )}
                  </div>
                </td>
                <td className={TD}>
                  <IpCell account={a} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
