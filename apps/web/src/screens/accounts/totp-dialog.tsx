import { CircleAlertIcon } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { confirmTotp, TOTP_CODE, totpCause, type TotpCause } from "@/lib/accounts";

const t = fr.totpConfirm;

/**
 * Demande un code TOTP, le confirme auprès de l'API, puis rend la main pour rejouer l'action refusée. Réservé aux
 * actions qui ne portent aucun secret : une clé n'est jamais gardée pour être rejouée (voir `KeyDialog`).
 * Le code est un champ non contrôlé, vidé dès l'envoi ; un refus laisse ressaisir sans quitter l'écran.
 */
export function TotpDialog({ replayNote, onConfirmed, onClose }: { replayNote?: string; onConfirmed: () => void; onClose: () => void }) {
  const id = useId();
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<TotpCause | "invalid" | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const input = event.currentTarget.elements.namedItem("totp") as HTMLInputElement;
    const code = input.value.trim();
    input.value = "";
    if (!TOTP_CODE.test(code)) {
      setFailure("invalid");
      input.focus();
      return;
    }
    setFailure(null);
    setPending(true);
    try {
      await confirmTotp(code);
      onConfirmed();
    } catch (error) {
      setFailure(totpCause(error));
      setPending(false);
      setTimeout(() => input.focus(), 0); // le champ est désactivé jusqu'au rendu suivant
    }
  }

  return (
    <ConfirmDialog titleId={`${id}-title`} descriptionId={`${id}-desc`} busy={pending} onClose={onClose}>
      <h2 id={`${id}-title`} className="text-xl font-semibold tracking-tight">
        {t.title}
      </h2>
      <p id={`${id}-desc`} className="text-sm text-muted-foreground">
        {t.body} {replayNote ?? t.replay}
      </p>
      <form onSubmit={onSubmit} noValidate autoComplete="off" aria-label={t.title} className="flex flex-col gap-5">
        <Field>
          <FieldLabel htmlFor={`${id}-code`}>{t.code}</FieldLabel>
          <Input id={`${id}-code`} name="totp" inputMode="numeric" autoComplete="one-time-code" spellCheck={false} data-autofocus data-1p-ignore disabled={pending} aria-invalid={failure ? true : undefined} />
          <FieldDescription>{t.fieldHelp}</FieldDescription>
        </Field>
        {failure && (
          <Alert role="alert">
            <CircleAlertIcon />
            <AlertTitle>{t.errorTitle}</AlertTitle>
            <AlertDescription>{failure === "invalid" ? t.invalid : t.causes[failure]}</AlertDescription>
          </Alert>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={pending}>
            {pending && <Spinner data-icon="inline-start" />}
            {pending ? t.pending : t.submit}
          </Button>
          <Button type="button" variant="outline" disabled={pending} onClick={onClose}>
            {t.cancel}
          </Button>
        </div>
      </form>
    </ConfirmDialog>
  );
}
