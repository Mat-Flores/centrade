import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlertIcon } from "lucide-react";
import { useState, type FormEvent } from "react";

import { AppLink } from "@/components/app-link";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { ApiError } from "@/lib/api";
import { pathWith, SCREEN_PATHS, navigate } from "@/lib/router";
import { createStrategy, STRATEGY_NAME, strategiesKey, type Strategy } from "@/lib/strategies";
import { cn } from "@/lib/utils";

const t = fr.strategies;

function CreateStrategy({ onDone }: { onDone: (message: string) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [invalid, setInvalid] = useState(false);
  const create = useMutation({
    mutationFn: (n: string) => createStrategy(n),
    onSuccess: async (s) => {
      await qc.invalidateQueries({ queryKey: strategiesKey });
      setName("");
      onDone(t.create.done(s.name));
      navigate(pathWith(SCREEN_PATHS.strategies, { s: s.id }));
    },
  });
  const error = create.error;
  const cause = error instanceof ApiError && error.status === 409 ? t.create.duplicate : t.create.other;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!STRATEGY_NAME.test(trimmed)) return setInvalid(true);
    setInvalid(false);
    create.mutate(trimmed);
  }
  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3" aria-label={t.create.submit}>
      <Field data-invalid={invalid || undefined}>
        <FieldLabel htmlFor="strategy-name">{t.create.label}</FieldLabel>
        <Input id="strategy-name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" spellCheck={false} aria-invalid={invalid || undefined} aria-describedby="strategy-name-help" disabled={create.isPending} />
        <FieldDescription id="strategy-name-help">{invalid ? t.create.invalid : t.create.help}</FieldDescription>
      </Field>
      {create.isError && (
        <Alert role="alert">
          <CircleAlertIcon />
          <AlertTitle>{t.create.errorTitle}</AlertTitle>
          <AlertDescription>{cause}</AlertDescription>
        </Alert>
      )}
      <div>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending && <Spinner data-icon="inline-start" />}
          {create.isPending ? t.create.pending : t.create.submit}
        </Button>
      </div>
    </form>
  );
}

/** Liste des stratégies (liens : URL partageable `?s=`), plus la création pour les rôles qui peuvent écrire. */
export function StrategyList({ items, selectedId, canAct, onNotice }: { items: Strategy[]; selectedId: string | null; canAct: boolean; onNotice: (m: string) => void }) {
  return (
    <div className="flex flex-col gap-5">
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{t.list.empty}</span> {canAct ? t.list.emptyBody : t.list.emptyViewer}
        </p>
      ) : (
        <nav aria-label={t.list.label}>
          <ul className="flex flex-col gap-1">
            {items.map((s) => (
              <li key={s.id}>
                <AppLink
                  to={pathWith(SCREEN_PATHS.strategies, { s: s.id })}
                  aria-current={s.id === selectedId ? "page" : undefined}
                  aria-label={t.list.open(s.name)}
                  data-strategy={s.name}
                  className={cn(
                    "flex min-h-11 items-center rounded-lg px-3 font-mono text-base focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none",
                    s.id === selectedId ? "bg-muted font-semibold" : "hover:bg-muted",
                  )}
                >
                  {s.name}
                </AppLink>
              </li>
            ))}
          </ul>
        </nav>
      )}
      {canAct && <CreateStrategy onDone={onNotice} />}
    </div>
  );
}
