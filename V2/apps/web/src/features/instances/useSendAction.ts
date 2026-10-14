import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";

import { applyStreamMessage } from "@/lib/cockpit";
import { sendAction, type ActionType } from "@/lib/instances";

/**
 * One action = one command with an Idempotency-Key. A retry of the same action replays the same key
 * (the server answers with the same command); a different action gets its own. On success the accepted
 * command (`requested`) enters the cache: the row says "demandé", never "fait" (I8).
 */
export function useSendAction(instanceId: string) {
  const qc = useQueryClient();
  const key = useRef<{ action: ActionType; value: string } | null>(null);
  return useMutation({
    mutationFn: (action: ActionType) => {
      if (key.current?.action !== action) key.current = { action, value: crypto.randomUUID() };
      return sendAction(instanceId, action, key.current.value);
    },
    onSuccess: ({ command }) => {
      key.current = null;
      applyStreamMessage(qc, { event: "command", server_time: command.server_time, command });
    },
  });
}
