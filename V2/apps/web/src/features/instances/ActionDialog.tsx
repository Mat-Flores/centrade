import { useEffect } from "react";

import { fr } from "@/i18n/fr";
import { ENGINE_STALE_MS, stateView } from "@/lib/cockpit";
import { formatAge } from "@/lib/format";
import type { ActionType, Instance } from "@/lib/instances";
import { Button, Dialog } from "@/ui/ui";

import { refusal } from "./errors";
import { useSendAction } from "./useSendAction";

export type ConfirmedAction = Extract<ActionType, "flatten" | "stop" | "resume_entries">;

const LABEL: Record<ConfirmedAction, string> = { flatten: fr.instances.moreActions.flatten, stop: fr.instances.moreActions.stop, resume_entries: fr.instances.rowActions.resume_entries };

function ObservedLine({ instance, nowMs }: { instance: Instance; nowMs: number }) {
  const t = fr.instances.confirm;
  const view = stateView(instance, nowMs);
  if (view.kind === "unknown") return <p><strong>{t.observedUnknown}</strong></p>;
  const age = Math.max(0, nowMs - Date.parse(instance.state.observed_at ?? ""));
  const state = fr.cockpit.states[view.state];
  if (view.kind === "stale") {
    return <p><strong>{t.observedStale(state, formatAge(Math.max(0, age - ENGINE_STALE_MS)).replace(/^il y a /, ""))}</strong></p>;
  }
  return <p>{t.observedNow(state, formatAge(age))}</p>;
}

export interface PendingConfirm { instanceId: string; action: ConfirmedAction }

/**
 * Confirmation before a command that closes, stops or increases risk. The consequences are announced from
 * the state observed at this instant (SPEC §9); no success is shown here: the accepted command becomes a
 * "demandé" line on the row, and only `verified` is "fait" (I8). Always mounted, so the browser returns the
 * focus to the button that opened it.
 */
export function ActionDialog({ pending, instance, nowMs, onClose }: { pending: PendingConfirm | null; instance: Instance | undefined; nowMs: number; onClose: () => void }) {
  const t = fr.instances.confirm;
  const send = useSendAction(pending?.instanceId ?? "");
  const { reset } = send;
  const open = pending !== null && instance !== undefined;
  useEffect(() => reset(), [pending?.instanceId, pending?.action, reset]);
  const failure = send.isError ? refusal(send.error, t.errorFallback) : null;
  const action = pending?.action ?? "stop";
  return (
    <Dialog
      open={open}
      narrow
      onClose={onClose}
      title={open ? t.title(LABEL[action], instance.name) : ""}
      foot={
        <>
          <Button data-autofocus disabled={send.isPending} onClick={onClose}>{t.cancel}</Button>
          <Button variant={action === "resume_entries" ? "go" : "danger"} disabled={send.isPending} onClick={() => send.mutate(action, { onSuccess: onClose })}>
            {send.isPending ? t.pending : LABEL[action]}
          </Button>
        </>
      }
    >
      {open && (
        <>
          <p style={{ margin: 0 }}>{t.consequences[action]}</p>
          <ObservedLine instance={instance} nowMs={nowMs} />
          <p className="quiet">{t.sent}</p>
          {failure && <div role="alert" className="inline-err"><strong>{t.errorTitle}</strong> {failure.text}</div>}
        </>
      )}
    </Dialog>
  );
}
