import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlertIcon } from "lucide-react";
import { useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { fr } from "@/i18n/fr";
import { accountsKey, accountsQuery, errorCause, testAccount, type Account, type TestResult } from "@/lib/accounts";
import { AccountTable } from "./account-table";
import { CreateAccount } from "./create-account";
import { KeyDialog, type KeyAction } from "./key-dialog";

const t = fr.accounts;

/** Emplacements honnêtes des données que l'API n'expose pas encore : rien n'est simulé. */
function Unavailable() {
  return (
    <section aria-labelledby="unavailable-title" className="flex flex-col gap-3">
      <h2 id="unavailable-title" className="text-xl font-semibold tracking-tight">
        {t.unavailable.title}
      </h2>
      <dl className="grid max-w-3xl gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-dashed p-4">
          <dt className="font-semibold">{t.unavailable.matrix}</dt>
          <dd className="mt-1 text-sm text-muted-foreground">{t.unavailable.matrixBody}</dd>
        </div>
        <div className="rounded-lg border border-dashed p-4">
          <dt className="font-semibold">{t.unavailable.balance}</dt>
          <dd className="mt-1 text-sm text-muted-foreground">{t.unavailable.balanceBody}</dd>
        </div>
      </dl>
    </section>
  );
}

/** Écran 5 : comptes, clés en écriture seule, test des permissions. Les rôles non admin le lisent seulement. */
export function AccountsScreen({ isAdmin }: { isAdmin: boolean }) {
  const qc = useQueryClient();
  const accounts = useQuery(accountsQuery);
  const [keyAction, setKeyAction] = useState<KeyAction | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);

  const test = useMutation({
    mutationFn: (account: Account) => testAccount(account.id),
    onMutate: (account) => {
      setTesting(account.id);
      setNotice(null);
    },
    onSuccess: async (out: TestResult, account) => {
      await qc.invalidateQueries({ queryKey: accountsKey });
      setNotice(t.testResult[out.result](account.label));
    },
    onSettled: () => setTesting(null),
  });

  const page = accounts.data;
  const items = page?.items ?? [];
  const testFailure = test.isError ? errorCause(test.error) : null;

  return (
    <>
      <p className="max-w-3xl text-muted-foreground">{t.intro}</p>
      {!isAdmin && (
        <p id="read-only" className="max-w-3xl text-sm font-medium">
          {t.readOnly}
        </p>
      )}

      <div role="status" aria-live="polite" className="empty:hidden">
        {notice && (
          <Alert>
            <AlertDescription>{notice}</AlertDescription>
          </Alert>
        )}
      </div>

      {testFailure && (
        <Alert role="alert">
          <CircleAlertIcon />
          <AlertTitle>{t.testError.title}</AlertTitle>
          <AlertDescription>
            {testFailure.cause === "refused" ? t.testError.noKey : testFailure.cause === "totp" || testFailure.cause === "forbidden" ? fr.accounts.keyDialog.causes[testFailure.cause] : t.testError.other}
          </AlertDescription>
        </Alert>
      )}

      {accounts.isPending && (
        <div role="status" aria-label={t.loading} className="flex flex-col divide-y rounded-xl border bg-card">
          {[0, 1, 2].map((n) => (
            <div key={n} className="flex flex-col gap-3 p-5">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-5 w-full max-w-2xl" />
            </div>
          ))}
        </div>
      )}

      {accounts.isError && (
        <div className="flex flex-col items-start gap-3">
          <Alert role="alert">
            <CircleAlertIcon />
            <AlertTitle>{t.loadError.title}</AlertTitle>
            <AlertDescription>{t.loadError.body}</AlertDescription>
          </Alert>
          <Button type="button" onClick={() => void accounts.refetch()}>
            {t.loadError.retry}
          </Button>
        </div>
      )}

      {page && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-start gap-3" aria-describedby={isAdmin ? undefined : "read-only"}>
            <CreateAccount canWrite={isAdmin} onDone={setNotice} />
          </div>
          {items.length === 0 ? (
            <Empty className="min-h-48">
              <EmptyHeader>
                <EmptyTitle className="text-base">{t.empty.title}</EmptyTitle>
                <EmptyDescription>{isAdmin ? t.empty.body : t.empty.bodyViewer}</EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <AccountTable
              accounts={items}
              serverTime={page.server_time}
              canWrite={isAdmin}
              testingId={testing}
              onKey={(account, usage, mode) => setKeyAction({ account, usage, mode })}
              onTest={(account) => test.mutate(account)}
            />
          )}
          {page.next_cursor !== null && <p className="text-sm text-muted-foreground">{t.truncated(items.length)}</p>}
        </div>
      )}

      <Unavailable />

      {keyAction && (
        <KeyDialog
          action={keyAction}
          onClose={() => setKeyAction(null)}
          onDone={(message) => {
            setKeyAction(null);
            setNotice(message);
            void qc.invalidateQueries({ queryKey: accountsKey });
          }}
        />
      )}
    </>
  );
}
