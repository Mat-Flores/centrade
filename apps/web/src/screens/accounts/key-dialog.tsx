import { CircleAlertIcon } from "lucide-react";
import { useId, useRef, useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { confirmTotp, errorCause, labelMatches, SecretFormSchema, TOTP_CODE, TOTP_REUSE_MS, totpCause, writeKey, type Account, type ErrorCause, type KeyUsage, type TotpCause } from "@/lib/accounts";

const t = fr.accounts.keyDialog;
const totp = fr.totpConfirm;

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
  // Code TOTP : confirmé avant l'envoi de la clé, jamais après coup. `needsTotp` : l'API vient de le réclamer.
  const [totpFailure, setTotpFailure] = useState<TotpCause | "invalid" | null>(null);
  const [needsTotp, setNeedsTotp] = useState(false);
  const [totpDone, setTotpDone] = useState(false);
  const confirmedAt = useRef<number | null>(null);

  const usageName = t.usage[usage];
  const exists = (usage === "trade" ? account.trade_key : account.read_key) !== null;
  const title = mode === "rotate" ? t.rotateTitle(usageName) : exists ? t.replaceTitle(usageName) : t.depositTitle(usageName);
  const body = mode === "rotate" ? t.rotateBody : exists ? t.replaceBody : t.depositBody;
  const confirmed = labelMatches(typed, account.label);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !confirmed) return;
    const form = event.currentTarget;
    setFailure(null);
    setEmpty(false);

    // 1. Le code TOTP d'abord : la clé n'est ni lue ni vidée tant qu'il n'est pas confirmé, donc un refus laisse
    //    ressaisir le code seul, et rien ne doit être gardé pour « rejouer » l'envoi de la clé.
    const totpInput = form.elements.namedItem("totp") as HTMLInputElement;
    const code = totpInput.value.trim();
    totpInput.value = "";
    const recent = confirmedAt.current !== null && Date.now() - confirmedAt.current < TOTP_REUSE_MS;
    if (code !== "" || (needsTotp && !recent)) {
      if (!TOTP_CODE.test(code)) {
        setTotpFailure("invalid");
        totpInput.focus();
        return;
      }
      setPending(true);
      setTotpFailure(null);
      try {
        await confirmTotp(code);
        confirmedAt.current = Date.now();
        setTotpDone(true);
        setNeedsTotp(false);
      } catch (error) {
        setTotpFailure(totpCause(error));
        setPending(false);
        setTimeout(() => totpInput.focus(), 0); // le champ est désactivé jusqu'au rendu suivant
        return;
      }
    }

    // 2. La clé : lue une fois, vidée aussitôt, envoyée, jamais conservée.
    // `.value` plutôt que FormData : les champs sont désactivés pendant la confirmation du code, FormData les ignorerait.
    const read = (name: string) => (form.elements.namedItem(name) as HTMLInputElement).value;
    const parsed = SecretFormSchema.safeParse({ key: read("key"), secret: read("secret") });
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
      const failed = errorCause(error);
      if (failed.cause === "totp") {
        // La confirmation a expiré ou manquait : le code sera demandé avant le prochain envoi.
        confirmedAt.current = null;
        setTotpDone(false);
        setNeedsTotp(true);
      }
      setFailure(failed);
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
          <Field data-invalid={needsTotp || totpFailure ? true : undefined}>
            <FieldLabel htmlFor={`${id}-totp`}>{totp.code}</FieldLabel>
            <Input
              id={`${id}-totp`}
              name="totp"
              inputMode="numeric"
              autoComplete="one-time-code"
              spellCheck={false}
              disabled={pending}
              data-autofocus
              data-1p-ignore
              aria-required={needsTotp || undefined}
              aria-invalid={totpFailure ? true : undefined}
              aria-describedby={`${id}-totp-help`}
            />
            <FieldDescription id={`${id}-totp-help`}>{needsTotp ? totp.fieldHelpNeeded : totp.fieldHelp}</FieldDescription>
            {totpDone && !needsTotp && <p className="text-sm font-medium">{totp.confirmed}</p>}
          </Field>
          {totpFailure && (
            <Alert role="alert">
              <CircleAlertIcon />
              <AlertTitle>{totp.errorTitle}</AlertTitle>
              <AlertDescription>{totpFailure === "invalid" ? totp.invalid : totp.causes[totpFailure]}</AlertDescription>
            </Alert>
          )}
          <Field>
            <FieldLabel htmlFor={`${id}-key`}>{t.key}</FieldLabel>
            <Input id={`${id}-key`} name="key" type="password" autoComplete="off" spellCheck={false} disabled={pending} data-1p-ignore />
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
