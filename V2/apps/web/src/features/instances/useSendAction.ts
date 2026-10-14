import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";

import { applyStreamMessage } from "@/lib/cockpit";
import { sendAction, type ActionType } from "@/lib/instances";

export interface Slot { scope: string; value: string }

/**
 * The key is bound to (instance, action): a retry replays it, anything else gets a fresh one. The server
 * refuses (422) a key replayed on another instance, which would block a stop or a flatten (I4).
 */
export function keyFor(slot: Slot | null, instanceId: string, action: ActionType): Slot {
  const scope = `${instanceId}:${action}`;
  return slot?.scope === scope ? slot : { scope, value: crypto.randomUUID() };
}

/**
 * One action = one command with an Idempotency-Key. A retry of the same action on the same instance replays
 * the same key (the server answers with the same command). On success the accepted command (`requested`)
 * enters the cache: the row says "demandé", never "fait" (I8).
 */
export function useSendAction(instanceId: string) {
  const qc = useQueryClient();
  const slot = useRef<Slot | null>(null);
  return useMutation({
    mutationFn: (action: ActionType) => {
      slot.current = keyFor(slot.current, instanceId, action);
      return sendAction(instanceId, action, slot.current.value);
    },
    onSuccess: ({ command }) => {
      slot.current = null;
      applyStreamMessage(qc, { event: "command", server_time: command.server_time, command });
    },
  });
}
