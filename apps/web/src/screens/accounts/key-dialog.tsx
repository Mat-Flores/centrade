import { CircleAlertIcon } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { errorCause, labelMatches, SecretFormSchema, writeKey, type Account, type ErrorCause, type KeyUsage } from "@/lib/accounts";

const t = fr.accounts.keyDialog;

export interface KeyAction {
  account: Account;
  usage: KeyUsage;
  mode: "put" | "rotate";
}

/**
 * Dépôt, remplacement ou rotation d'une clé. Action dangereuse (SPEC §9) : confirmation par saisie du
 * libellé du compte, en plus du TOTP récent que l'API exige.
 * La clé et le secret sont des champs non contrôlés : ils n'entrent dans aucun état React, sont lus une
 * fois à l'envoi puis vidés aussitôt, et ne passent ni par le cache de requêtes ni par l'URL ni par un log.
 */
export function KeyDialog({ action, onClose, onDone }: { action: KeyAction; onClose: () => void; onDone: (message: string) => void }) {
  const { account, usage, mode } = action;
  const id = useId();
  const [typed, setTyped] = useState("");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<{ cause: ErrorCause; detail: string | null } | null>(null);
  const [empty, setEmpty] = useState(false);

  const usageName = t.usage[usage];
  const exists = (usage === "trade" ? account.trade_key : account.read_key) !== null;
  const title = mode === "rotate" ? t.rotateTitle(usageName) : exists ? t.replaceTitle(usageName) : t.depositTitle(usageName);
  const body = mode === "rotate" ? t.rotateBody : exists ? t.replaceBody : t.depositBody;
  const confirmed = labelMatches(typed, account.label);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !confirmed) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const parsed = SecretFormSchema.safeParse({ key: data.get("key"), secret: data.get("secret") });
    // Vidés dès l'envoi, succès ou échec : rien de la saisie ne reste dans le DOM.
    for (const name of ["key", "secret"]) (form.elements.namedItem(name) as HTMLInputElement).value = "";
    if (!parsed.success) {
      setEmpty(true);
      return;
    }
    setEmpty(false);
    setFailure(null);
    setPending(true);
    try {
      await writeKey(account.id, mode, { usage, ...parsed.data });
      onDone(mode === "rotate" ? t.done.rotate(usageName) : t.done.put(usageName));
    } catch (error) {
      setFailure(errorCause(error));
      setPending(false);
    }
  }

  return (
    <ConfirmDialog titleId={`${id}-title`} descriptionId={`${id}-desc`} busy={pending} onClose={onClose}>
      <h2 id={`${id}-title`} className="text-xl font-semibold tracking-tight">
        {title} <span className="text-muted-foreground">— {account.label}</span>
      </h2>
      <p id={`${id}-desc`} className="text-sm text-muted-foreground">
        {body} {t.totpNote}
      </p>
      <form onSubmit={onSubmit} noValidate autoComplete="off" className="flex flex-col gap-5" aria-label={title}>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor={`${id}-key`}>{t.key}</FieldLabel>
            <Input id={`${id}-key`} name="key" type="password" autoComplete="off" spellCheck={false} data-autofocus disabled={pending} data-1p-ignore />
          </Field>
          <Field>
            <FieldLabel htmlFor={`${id}-secret`}>{t.secret}</FieldLabel>
            <Input id={`${id}-secret`} name="secret" type="password" autoComplete="off" spellCheck={false} disabled={pending} data-1p-ignore aria-describedby={`${id}-wo`} />
            <FieldDescription id={`${id}-wo`}>{t.writeOnly}</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor={`${id}-confirm`}>{t.confirmField}</FieldLabel>
            <Input
              id={`${id}-confirm`}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              spellCheck={false}
              disabled={pending}
              aria-describedby={`${id}-confirm-help`}
            />
            <FieldDescription id={`${id}-confirm-help`}>{t.confirm(account.label)}</FieldDescription>
          </Field>
        </FieldGroup>

        {(failure || empty) && (
          <Alert role="alert">
            <CircleAlertIcon />
            <AlertTitle>{t.errorTitle}</AlertTitle>
            <AlertDescription>
              {empty
                ? `${t.empty} ${t.retype}`
                : (
                    <>
                      {failure && failure.cause === "refused" && failure.detail ? `${failure.detail} ` : ""}
                      {failure ? t.causes[failure.cause] : ""} {t.retype}
                    </>
                  )}
            </AlertDescription>
          </Alert>
        )}

        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={pending || !confirmed}>
            {pending && <Spinner data-icon="inline-start" />}
            {pending ? t.pending : mode === "rotate" ? t.submitRotate : t.submit}
          </Button>
          <Button type="button" variant="outline" disabled={pending} onClick={onClose}>
            {t.cancel}
          </Button>
        </div>
      </form>
    </ConfirmDialog>
  );
}
