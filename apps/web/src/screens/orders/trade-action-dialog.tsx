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
import type { Instance } from "@/lib/instances";
import { cancelOrder, closePosition, tradingKey, type Order, type Position } from "@/lib/trading";
import { num } from "./cells";

export type TradeAction = { kind: "close"; position: Position; key: string } | { kind: "cancel"; order: Order; key: string };

const t = fr.orders;
const sinceOf = (ms: number) => formatAge(Math.max(0, ms - ENGINE_STALE_MS)).replace(/^il y a /, "");

/** État observé de l'instance, tel qu'il est à cet instant : frais, périmé ou inconnu, dit tel quel. */
function InstanceLine({ instance, nowMs }: { instance: Instance | undefined; nowMs: number }) {
  if (!instance) return <p className="font-medium">{t.close.instanceUnknown}</p>;
  const view = stateView(instance, nowMs);
  if (view.kind === "unknown") return <p className="font-medium">{t.close.instanceUnknown}</p>;
  const age = Math.max(0, nowMs - Date.parse(instance.state.observed_at ?? ""));
  const state = fr.cockpit.states[view.state] as string;
  return view.kind === "stale" ? <p className="font-medium">{t.close.instanceStale(state, sinceOf(age))}</p> : <p>{t.close.instanceState(state, formatAge(age))}</p>;
}

function ProtectionLine({ position, nowMs }: { position: Position; nowMs: number }) {
  const at = position.protection_verified_at ? Date.parse(position.protection_verified_at) : NaN;
  if (position.protection_state === "unknown" || Number.isNaN(at)) return <p className="font-medium">{t.close.protectionUnknown}</p>;
  const age = Math.max(0, nowMs - at);
  const state = t.positions.protection[position.protection_state] ?? position.protection_state;
  return age > ENGINE_STALE_MS ? <p className="font-medium">{t.close.protectionStale(state, sinceOf(age))}</p> : <p>{t.close.protectionNow(state, formatAge(age))}</p>;
}

/**
 * Fermer une position / annuler un ordre d'entrée : deux commandes qui réduisent le risque (I4). Ni 2FA ni
 * autorisation, jamais refusées pour un état inconnu ou périmé : l'état est annoncé, pas exigé. La réussite
 * n'est pas affichée ici : la commande acceptée devient une ligne de l'historique, « faite » à `verified` seulement.
 */
export function TradeActionDialog({ action, instance, nowIso, onClose }: { action: TradeAction; instance: Instance | undefined; nowIso: string; onClose: () => void }) {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => (action.kind === "close" ? closePosition(action.position.id, action.key) : cancelOrder(action.order.id, action.key)),
    onSuccess: ({ command }) => {
      applyStreamMessage(qc, { event: "command", server_time: command.server_time, command });
      void qc.invalidateQueries({ queryKey: tradingKey() });
      onClose();
    },
  });
  const nowMs = Date.parse(nowIso);
  const name = instance?.name ?? t.unknownInstance;
  const error = mutation.error;
  const reason = error instanceof ApiError && error.kind === "problem" ? (error.problem?.detail ?? t.close.errorFallback) : t.close.errorFallback;
  const isClose = action.kind === "close";
  const subject = isClose ? action.position : action.order;
  const title = isClose ? t.close.title(action.position.instrument) : t.ordersList.dialogTitle(action.order.instrument);
  const mode = t.modes[subject.mode] + (subject.mode === "paper" ? ` ${t.simulated}` : "");

  return (
    <ConfirmDialog titleId="trade-title" descriptionId="trade-description" busy={mutation.isPending} onClose={onClose}>
      <h2 id="trade-title" className="text-xl font-semibold tracking-tight">
        {title}
      </h2>
      <div id="trade-description" className="flex flex-col gap-3">
        {isClose ? (
          <>
            <p>{t.close.position(t.positions.sides[action.position.side] ?? action.position.side, num(action.position.quantity), action.position.instrument, name, mode)}</p>
            <ProtectionLine position={action.position} nowMs={nowMs} />
            <InstanceLine instance={instance} nowMs={nowMs} />
            <p>{t.close.consequence}</p>
          </>
        ) : (
          <>
            <p>{t.ordersList.dialogBody(t.ordersList.sides[action.order.side] ?? action.order.side, num(action.order.quantity), action.order.instrument, name, mode)}</p>
            <InstanceLine instance={instance} nowMs={nowMs} />
            <p>{t.ordersList.dialogConsequence}</p>
          </>
        )}
      </div>
      {error && (
        <Alert role="alert">
          <CircleAlertIcon />
          <AlertTitle>{t.close.errorTitle}</AlertTitle>
          <AlertDescription>{reason}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" data-autofocus disabled={mutation.isPending} onClick={onClose}>
          {isClose ? t.close.cancel : t.ordersList.keep}
        </Button>
        <Button type="button" variant={isClose ? "destructive" : "default"} disabled={mutation.isPending} onClick={() => mutation.mutate()}>
          {mutation.isPending && <Spinner data-icon="inline-start" />}
          {mutation.isPending ? t.close.pending : isClose ? t.close.submit : t.ordersList.submit}
        </Button>
      </div>
    </ConfirmDialog>
  );
}
