import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlertIcon } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { accountsQuery } from "@/lib/accounts";
import { ApiError } from "@/lib/api";
import { applyStreamMessage } from "@/lib/cockpit";
import { fieldsFromSchema, initialValues, validateParams, type Field as ParamField, type FieldError } from "@/lib/params-form";
import { deployPaper, INSTANCE_NAME, type Version } from "@/lib/strategies";

const t = fr.strategies.deploy;

function errorText(e: FieldError): string {
  switch (e.code) {
    case "min":
      return t.errors.min(e.bound, e.exclusive);
    case "max":
      return t.errors.max(e.bound, e.exclusive);
    case "minLength":
      return t.errors.minLength(e.bound);
    case "maxLength":
      return t.errors.maxLength(e.bound);
    default:
      return t.errors[e.code];
  }
}

function hint(f: ParamField): string {
  const parts = [f.description, f.initial !== null && f.kind !== "boolean" ? t.defaultIs(f.initial) : null, f.min !== null || f.max !== null ? t.range(f.min === null ? null : String(f.min), f.max === null ? null : String(f.max)) : null];
  return parts.filter(Boolean).join(" ");
}

function ParamInput({ f, value, error, onChange, disabled }: { f: ParamField; value: string; error: FieldError | undefined; onChange: (v: string) => void; disabled: boolean }) {
  const id = `param-${f.key}`;
  const describedBy = `${id}-help`;
  const invalid = error ? true : undefined;
  return (
    <Field data-invalid={invalid}>
      <FieldLabel htmlFor={id}>
        {f.label}
        {f.required && <span className="font-normal text-muted-foreground"> ({t.required})</span>}
      </FieldLabel>
      {f.kind === "boolean" ? (
        <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} aria-describedby={describedBy}>
          <option value="true">{t.yes}</option>
          <option value="false">{t.no}</option>
        </Select>
      ) : f.kind === "enum" ? (
        <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} aria-invalid={invalid} aria-describedby={describedBy}>
          {!f.required && <option value="" />}
          {f.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </Select>
      ) : (
        <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} inputMode={f.kind === "string" ? "text" : "decimal"} autoComplete="off" aria-invalid={invalid} aria-describedby={describedBy} />
      )}
      <FieldDescription id={describedBy}>{error ? errorText(error) : hint(f) || "\u00a0"}</FieldDescription>
    </Field>
  );
}

/**
 * Déploiement en paper d'une version : champs générés depuis `params_schema`, validés avant l'envoi. Ni le mode
 * ni le moteur ne se choisissent ici. L'instance créée n'est pas « en marche » : elle apparaît dans la liste, état observé inconnu
 * tant que le moteur n'a rien rapporté.
 */
export function DeployForm({ version, onDone }: { version: Version; onDone: (message: string) => void }) {
  const qc = useQueryClient();
  const accounts = useQuery(accountsQuery);
  const { fields, unsupported } = useMemo(() => fieldsFromSchema(version.manifest.params_schema), [version.manifest.params_schema]);
  const [values, setValues] = useState(() => initialValues(fields));
  const [name, setName] = useState("");
  const [accountId, setAccountId] = useState("");
  const [shown, setShown] = useState(false); // les erreurs ne s'affichent qu'après une tentative d'envoi
  const [key, setKey] = useState(() => crypto.randomUUID());

  const paper = (accounts.data?.items ?? []).filter((a) => a.type === "paper");
  const checked = validateParams(fields, values);
  const nameOk = INSTANCE_NAME.test(name.trim()) && name.trim().length <= 64;
  const valid = nameOk && accountId !== "" && Object.keys(checked.errors).length === 0;

  const deploy = useMutation({
    mutationFn: () => deployPaper({ name: name.trim(), params: checked.values, strategy_version_id: version.id, account_id: accountId }, key),
    onSuccess: (instance) => {
      applyStreamMessage(qc, { event: "instance", server_time: instance.server_time, instance });
      onDone(t.done(instance.name));
      setName("");
      setShown(false);
      setKey(crypto.randomUUID()); // un nouveau déploiement est une nouvelle demande
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setShown(true);
    if (valid && !deploy.isPending) deploy.mutate();
  }

  const refusal = deploy.error instanceof ApiError && deploy.error.kind === "problem" ? (deploy.error.problem?.detail ?? t.errorFallback) : t.errorFallback;
  const retired = version.status === "retired";
  return (
    <section aria-labelledby="deploy-title" className="flex flex-col gap-3">
      <h4 id="deploy-title" className="text-base font-semibold">{t.title}</h4>
      <p className="max-w-3xl text-sm text-muted-foreground">{retired ? t.retired : t.body}</p>
      {!retired && (
        <form onSubmit={onSubmit} noValidate aria-label={t.title} className="flex max-w-xl flex-col gap-5">
          <FieldGroup>
            <Field data-invalid={shown && !nameOk ? true : undefined}>
              <FieldLabel htmlFor="deploy-name">{t.name}</FieldLabel>
              <Input id="deploy-name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" spellCheck={false} aria-invalid={shown && !nameOk ? true : undefined} aria-describedby="deploy-name-help" disabled={deploy.isPending} />
              <FieldDescription id="deploy-name-help">{shown && !nameOk ? t.nameInvalid : t.nameHelp}</FieldDescription>
            </Field>
            <Field data-invalid={shown && accountId === "" ? true : undefined}>
              <FieldLabel htmlFor="deploy-account">{t.account}</FieldLabel>
              <Select id="deploy-account" value={accountId} onChange={(e) => setAccountId(e.target.value)} disabled={deploy.isPending || paper.length === 0} aria-invalid={shown && accountId === "" ? true : undefined} aria-describedby="deploy-account-help">
                <option value="">{t.accountNone}</option>
                {paper.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label} ({a.currency})
                  </option>
                ))}
              </Select>
              <FieldDescription id="deploy-account-help">{accounts.isSuccess && paper.length === 0 ? t.noAccount : shown && accountId === "" ? t.accountInvalid : "\u00a0"}</FieldDescription>
            </Field>
            <fieldset className="flex flex-col gap-4">
              <legend className="mb-2 text-sm font-medium">{t.params}</legend>
              {fields.length === 0 && <p className="text-sm text-muted-foreground">{t.noParams}</p>}
              {fields.map((f) => (
                <ParamInput key={f.key} f={f} value={values[f.key] ?? ""} error={shown ? checked.errors[f.key] : undefined} disabled={deploy.isPending} onChange={(v) => setValues({ ...values, [f.key]: v })} />
              ))}
              {unsupported.length > 0 && <p className="text-sm text-muted-foreground">{t.unsupported(unsupported.join(", "))}</p>}
            </fieldset>
          </FieldGroup>
          {shown && !valid && <p role="alert" className="text-sm font-medium">{t.fix}</p>}
          {deploy.isError && (
            <Alert role="alert">
              <CircleAlertIcon />
              <AlertTitle>{t.errorTitle}</AlertTitle>
              <AlertDescription>{refusal}</AlertDescription>
            </Alert>
          )}
          <div>
            <Button type="submit" disabled={deploy.isPending}>
              {deploy.isPending && <Spinner data-icon="inline-start" />}
              {deploy.isPending ? t.pending : t.submit}
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
