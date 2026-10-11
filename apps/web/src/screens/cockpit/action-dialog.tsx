import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlertIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import { ApiError } from "@/lib/api";
import { applyStreamMessage, ENGINE_STALE_MS, stateView } from "@/lib/cockpit";
import { formatAge } from "@/lib/format";
import { sendAction, type ActionType, type Instance } from "@/lib/instances";

export interface PendingAction {
  instanceId: string;
  action: ActionType;
  /** Clé d'idempotence propre à cette ouverture : un second clic rejoue la même commande, il n'en crée pas une autre. */
  key: string;
}

/**
 * Confirmation avant toute commande. Les conséquences sont annoncées d'après l'état observé à cet
 * instant (SPEC §9), périmé ou inconnu dit tel quel. Aucune réussite n'est affichée ici : la
 * commande acceptée devient une ligne de suivi dans l'instance, qui n'est « faite » qu'à `verified`.
 */
export function ActionDialog({
  pending,
  instance,
  nowIso,
  onClose,
}: {
  pending: PendingAction;
  instance: Instance | undefined;
  nowIso: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => sendAction(pending.instanceId, pending.action, pending.key),
    onSuccess: ({ command }) => {
      applyStreamMessage(qc, { event: "command", server_time: command.server_time, command });
      onClose();
    },
  });

  const nowMs = Date.parse(nowIso);
  const label = fr.cockpit.actions[pending.action];
  const error = mutation.error;
  const reason =
    error instanceof ApiError && error.kind === "problem" ? (error.problem?.detail ?? fr.cockpit.confirm.errorFallback) : fr.cockpit.confirm.errorFallback;

  return (
    <ConfirmDialog titleId="confirm-title" descriptionId="confirm-description" busy={mutation.isPending} onClose={onClose}>
      <h2 id="confirm-title" className="text-xl font-semibold tracking-tight">
        {fr.cockpit.confirm.title(label, instance?.name ?? "")}
      </h2>
      <div id="confirm-description" className="flex flex-col gap-3">
        <p>{fr.cockpit.confirm.consequences[pending.action]}</p>
        {instance && <ObservedLine instance={instance} nowMs={nowMs} />}
      </div>
      {error && (
        <Alert role="alert">
          <CircleAlertIcon />
          <AlertTitle>{fr.cockpit.confirm.errorTitle}</AlertTitle>
          <AlertDescription>{reason}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" data-autofocus disabled={mutation.isPending} onClick={onClose}>
          {fr.cockpit.confirm.cancel}
        </Button>
        <Button
          type="button"
          variant={pending.action === "flatten" ? "destructive" : "default"}
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending && <Spinner data-icon="inline-start" />}
          {mutation.isPending ? fr.cockpit.confirm.pending : label}
        </Button>
      </div>
    </ConfirmDialog>
  );
}

function ObservedLine({ instance, nowMs }: { instance: Instance; nowMs: number }) {
  const view = stateView(instance, nowMs);
  if (view.kind === "unknown") return <p className="font-medium">{fr.cockpit.confirm.observedUnknown}</p>;
  const age = Math.max(0, nowMs - Date.parse(instance.state.observed_at ?? ""));
  const state = fr.cockpit.states[view.state];
  if (view.kind === "stale") {
    const since = formatAge(Math.max(0, age - ENGINE_STALE_MS)).replace(/^il y a /, "");
    return <p className="font-medium">{fr.cockpit.confirm.observedStale(state, since)}</p>;
  }
  return <p>{fr.cockpit.confirm.observedNow(state, formatAge(age))}</p>;
}
