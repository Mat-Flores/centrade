import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlertIcon, PlusIcon } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { ApiError } from "@/lib/api";
import { applyStreamMessage, canCreate } from "@/lib/cockpit";
import { createInstance } from "@/lib/instances";

// Même règle que l'API (InstanceCreate.name).
const NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

/** Création d'une instance simulée : un nom, rien d'autre d'obligatoire. Formulaire en ligne, pas de fenêtre. */
export function CreateInstance({ degraded }: { degraded: boolean }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [invalid, setInvalid] = useState(false);
  const policy = canCreate(degraded);

  const mutation = useMutation({
    mutationFn: createInstance,
    onSuccess: (instance) => {
      applyStreamMessage(qc, { event: "instance", server_time: instance.server_time, instance });
      setOpen(false);
    },
  });

  if (!open || !policy.enabled) {
    return (
      <div className="flex flex-col items-start gap-1">
        <Button
          type="button"
          variant="outline"
          aria-disabled={policy.enabled ? undefined : true}
          aria-describedby={policy.enabled ? undefined : "create-reason"}
          className={policy.enabled ? undefined : "cursor-not-allowed opacity-50"}
          onClick={() => policy.enabled && setOpen(true)}
        >
          <PlusIcon data-icon="inline-start" />
          {fr.cockpit.create.open}
        </Button>
        {!policy.enabled && (
          <p id="create-reason" className="text-sm text-muted-foreground">
            {fr.cockpit.reasons.unavailable(fr.cockpit.create.open, policy.reason ?? "")}
          </p>
        )}
      </div>
    );
  }

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") ?? "").trim();
    if (!NAME.test(name)) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    mutation.mutate(name);
  };

  const error = mutation.error;
  const conflict = error instanceof ApiError && error.status === 409;
  const shown = invalid || error;

  return (
    <form onSubmit={onSubmit} noValidate className="flex w-full max-w-xl flex-col gap-4" aria-label={fr.cockpit.create.open}>
      <Field>
        <FieldLabel htmlFor="instance-name">{fr.cockpit.create.name}</FieldLabel>
        <Input
          id="instance-name"
          name="name"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          required
          maxLength={64}
          autoFocus
          disabled={mutation.isPending}
          aria-invalid={shown ? true : undefined}
          aria-describedby="instance-name-help"
        />
        <FieldDescription id="instance-name-help">{fr.cockpit.create.help}</FieldDescription>
      </Field>
      {shown && (
        <Alert role="alert">
          <CircleAlertIcon />
          <AlertTitle>{fr.cockpit.create.errorTitle}</AlertTitle>
          <AlertDescription>
            {invalid ? fr.cockpit.create.invalid : conflict ? fr.cockpit.create.conflict : fr.cockpit.create.error}
          </AlertDescription>
        </Alert>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending && <Spinner data-icon="inline-start" />}
          {mutation.isPending ? fr.cockpit.create.pending : fr.cockpit.create.submit}
        </Button>
        <Button type="button" variant="outline" disabled={mutation.isPending} onClick={() => setOpen(false)}>
          {fr.cockpit.create.cancel}
        </Button>
      </div>
    </form>
  );
}
