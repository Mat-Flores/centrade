import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlertIcon, PlusIcon } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { accountFormErrors, accountsKey, createAccount } from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const t = fr.accounts.create;

// Même habillage que `Input`, pour les listes à choix fermé (l'élément natif reste accessible au clavier).
const SELECT = cn(
  "h-11 w-full rounded-lg border border-input bg-background px-3 text-base outline-none",
  "focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
  "disabled:cursor-not-allowed disabled:opacity-60",
);

/** Création d'un compte. Aucune clé ici : elles se déposent ensuite, compte par compte. */
export function CreateAccount({ canWrite, onDone }: { canWrite: boolean; onDone: (message: string) => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [invalid, setInvalid] = useState<string[]>([]);

  const mutation = useMutation({
    mutationFn: createAccount,
    onSuccess: async (account) => {
      await qc.invalidateQueries({ queryKey: accountsKey });
      setOpen(false);
      onDone(t.done(account.label));
    },
  });

  if (!open) {
    return (
      <Button type="button" variant="outline" disabled={!canWrite} onClick={() => setOpen(true)}>
        <PlusIcon data-icon="inline-start" />
        {t.open}
      </Button>
    );
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const { data: form, fields } = accountFormErrors(Object.fromEntries(data));
    setInvalid(fields);
    if (form) mutation.mutate(form);
  }

  const error = mutation.error;
  const status = error instanceof ApiError ? error.status : null;
  const bad = (name: string) => (invalid.includes(name) ? true : undefined);
  const message =
    invalid.length > 0 ? (
      <>
        {t.invalid}
        <ul className="mt-1 list-disc pl-5">
          {invalid.map((f) => (
            <li key={f}>{t.invalidFields[f]}</li>
          ))}
        </ul>
      </>
    ) : status === 403 ? (
      t.forbidden
    ) : (
      t.other
    );

  return (
    <form onSubmit={onSubmit} noValidate aria-label={t.title} className="flex w-full max-w-2xl flex-col gap-5 rounded-xl border bg-card p-5">
      <h2 className="text-xl font-semibold tracking-tight">{t.title}</h2>
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="acc-label">{t.label}</FieldLabel>
          <Input id="acc-label" name="label" autoComplete="off" maxLength={80} required autoFocus disabled={mutation.isPending} aria-invalid={bad("label")} aria-describedby="acc-label-h" className="font-sans" />
          <FieldDescription id="acc-label-h">{t.labelHelp}</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="acc-venue">{t.venue}</FieldLabel>
          <Input id="acc-venue" name="venue" autoComplete="off" autoCapitalize="none" spellCheck={false} maxLength={32} required disabled={mutation.isPending} aria-invalid={bad("venue")} aria-describedby="acc-venue-h" />
          <FieldDescription id="acc-venue-h">{t.venueHelp}</FieldDescription>
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="acc-type">{t.type}</FieldLabel>
            <select id="acc-type" name="type" defaultValue="paper" disabled={mutation.isPending} className={SELECT}>
              <option value="paper">{fr.accounts.types.paper}</option>
              <option value="live">{fr.accounts.types.live}</option>
            </select>
          </Field>
          <Field>
            <FieldLabel htmlFor="acc-env">{t.environment}</FieldLabel>
            <select id="acc-env" name="environment" defaultValue="sandbox" disabled={mutation.isPending} className={SELECT}>
              <option value="sandbox">{fr.accounts.environments.sandbox}</option>
              <option value="production">{fr.accounts.environments.production}</option>
            </select>
          </Field>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="acc-cur">{t.currency}</FieldLabel>
            <Input id="acc-cur" name="currency" autoComplete="off" autoCapitalize="characters" spellCheck={false} maxLength={10} required disabled={mutation.isPending} aria-invalid={bad("currency")} aria-describedby="acc-cur-h" />
            <FieldDescription id="acc-cur-h">{t.currencyHelp}</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="acc-cap">{t.cap}</FieldLabel>
            <Input id="acc-cap" name="capital_cap" inputMode="decimal" autoComplete="off" spellCheck={false} disabled={mutation.isPending} aria-invalid={bad("capital_cap")} aria-describedby="acc-cap-h" />
            <FieldDescription id="acc-cap-h">{t.capHelp}</FieldDescription>
          </Field>
        </div>
      </FieldGroup>
      {(invalid.length > 0 || error) && (
        <Alert role="alert">
          <CircleAlertIcon />
          <AlertTitle>{t.errorTitle}</AlertTitle>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending && <Spinner data-icon="inline-start" />}
          {mutation.isPending ? t.pending : t.submit}
        </Button>
        <Button type="button" variant="outline" disabled={mutation.isPending} onClick={() => setOpen(false)}>
          {t.cancel}
        </Button>
      </div>
    </form>
  );
}
