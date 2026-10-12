import { CircleAlertIcon } from "lucide-react";
import { useId, useRef, useState, type ChangeEvent, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { ApiError } from "@/lib/api";
import { depositVersion, type Version } from "@/lib/strategies";
import { cn } from "@/lib/utils";

const t = fr.strategies.deposit;
const AREA = "min-h-40 w-full rounded-lg border border-input bg-background p-3 font-mono text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-60 aria-invalid:border-foreground";

type Failure = { kind: "reasons"; reasons: string[] } | { kind: "local"; message: string } | { kind: "error"; message: string };

/** Sélecteur de fichier : bouton de la maison (français) qui ouvre le sélecteur du navigateur ; l'entrée native reste cachée. */
function FilePick({ label, accept, disabled, onChange }: { label: string; accept: string; disabled: boolean; onChange: (event: ChangeEvent<HTMLInputElement>) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div>
      <input ref={input} type="file" hidden accept={accept} aria-label={label} disabled={disabled} onChange={onChange} />
      <Button type="button" variant="outline" disabled={disabled} onClick={() => input.current?.click()}>
        {label}
      </Button>
    </div>
  );
}

/** Lit un fichier local dans la zone de saisie : le contenu reste modifiable avant le dépôt. */
async function readInto(event: ChangeEvent<HTMLInputElement>, area: HTMLTextAreaElement | null, onError: () => void) {
  const file = event.target.files?.[0];
  if (!file || !area) return;
  try {
    area.value = await file.text();
  } catch {
    onError();
  }
}

/**
 * Dépôt d'une version. Les contrôles du registre refusent avec une liste de motifs : chacun est affiché
 * séparément. Un refus n'enregistre rien ; la clé d'idempotence reste celle de l'ouverture, donc un clic répété
 * ne dépose jamais deux versions.
 */
export function DepositDialog({ strategyId, strategyName, onClose, onDone }: { strategyId: string; strategyName: string; onClose: () => void; onDone: (v: Version) => void }) {
  const id = useId();
  const [key] = useState(() => crypto.randomUUID());
  const manifest = useRef<HTMLTextAreaElement>(null);
  const code = useRef<HTMLTextAreaElement>(null);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(manifest.current?.value ?? "");
    } catch {
      return setFailure({ kind: "local", message: t.manifestInvalid });
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return setFailure({ kind: "local", message: t.manifestInvalid });
    const source = code.current?.value ?? "";
    if (source.trim() === "") return setFailure({ kind: "local", message: t.codeEmpty });
    setFailure(null);
    setPending(true);
    try {
      onDone(await depositVersion(strategyId, { manifest: parsed as Record<string, unknown>, code: source }, key));
    } catch (error) {
      setPending(false);
      if (error instanceof ApiError && error.status === 422 && error.problem?.reasons?.length) setFailure({ kind: "reasons", reasons: error.problem.reasons });
      else if (error instanceof ApiError && error.kind === "network") setFailure({ kind: "error", message: t.errors.network });
      else if (error instanceof ApiError && error.status === 403) setFailure({ kind: "error", message: t.errors.forbidden });
      else setFailure({ kind: "error", message: t.errors.other });
    }
  }

  const fileError = () => setFailure({ kind: "local", message: t.fileError });
  const local = failure?.kind === "local";
  return (
    <ConfirmDialog titleId={`${id}-title`} descriptionId={`${id}-desc`} busy={pending} onClose={onClose} className="max-w-3xl">
      <h2 id={`${id}-title`} className="text-xl font-semibold tracking-tight">
        {t.title} <span className="font-mono text-muted-foreground">— {strategyName}</span>
      </h2>
      <p id={`${id}-desc`} className="text-sm text-muted-foreground">
        {t.body}
      </p>
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5" aria-label={t.title}>
        {/* Seuls les champs défilent : le pied (Déposer, Annuler) reste visible. */}
        <div className="max-h-[50dvh] overflow-y-auto px-1 py-1">
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor={`${id}-manifest`}>{t.manifest}</FieldLabel>
            <textarea id={`${id}-manifest`} ref={manifest} className={AREA} spellCheck={false} data-autofocus disabled={pending} aria-invalid={local || undefined} />
            <FilePick label={t.manifestFile} accept=".json,application/json" disabled={pending} onChange={(e) => void readInto(e, manifest.current, fileError)} />
          </Field>
          <Field>
            <FieldLabel htmlFor={`${id}-code`}>{t.code}</FieldLabel>
            <textarea id={`${id}-code`} ref={code} className={cn(AREA, "min-h-56")} spellCheck={false} disabled={pending} />
            <FilePick label={t.codeFile} accept=".py,text/x-python,text/plain" disabled={pending} onChange={(e) => void readInto(e, code.current, fileError)} />
            <FieldDescription>{t.body}</FieldDescription>
          </Field>
        </FieldGroup>
        </div>

        {failure?.kind === "reasons" && (
          <Alert role="alert">
            <CircleAlertIcon />
            <AlertTitle>{t.rejectedTitle}</AlertTitle>
            <AlertDescription>
              <p>{t.rejectedBody}</p>
              <ul data-reasons className="mt-2 flex list-disc flex-col gap-1 pl-5">
                {failure.reasons.map((r, n) => (
                  <li key={n} className="font-mono text-sm break-words">
                    {r}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        {(failure?.kind === "local" || failure?.kind === "error") && (
          <Alert role="alert">
            <CircleAlertIcon />
            <AlertTitle>{t.errorTitle}</AlertTitle>
            <AlertDescription>{failure.message}</AlertDescription>
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
