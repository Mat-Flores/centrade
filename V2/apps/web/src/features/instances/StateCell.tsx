import { fr } from "@/i18n/fr";
import { stateView } from "@/lib/cockpit";
import { observedTip, type RowCommand } from "@/lib/instance-row";
import { summarizeRow } from "@/lib/instance-stats";
import type { Instance } from "@/lib/instances";

const TONE = { running: "ok", starting: "info", exits_only: "warn", halted: "err", error: "err", stopped: "" } as const;

/**
 * Observed state only: the wanted state shows as a wish when it differs, a mode mismatch is loud, and a
 * command shows as "demandé" until it is observed (I1, I8).
 */
export function StateCell({ instance, nowMs, command }: { instance: Instance; nowMs: number; command: RowCommand | null }) {
  const view = stateView(instance, nowMs);
  const row = summarizeRow(instance, nowMs);
  const tone = view.kind === "unknown" || view.kind === "stale" ? "warn" : TONE[view.state];
  const tip = observedTip(instance.state, nowMs) ?? fr.observed.unknownHint;
  const mismatch = instance.mode_mismatch;
  const badge = command && (
    <span className={`small ${command.tone === "problem" ? "dn" : command.tone === "done" ? "up" : "dim"}`} data-tip={command.line}>{command.text}</span>
  );
  return (
    <>
      <span className={`chip ${tone}`} data-tip={tip}><span className="st-word">{row.state}</span></span>
      {(row.wanted || mismatch || badge) && (
        <span className="state-sub small">
          {mismatch && (
            <b className="dn" data-tip={fr.instances.modeMismatchTip(fr.instances.modeGroups[instance.desired_mode], fr.cockpit.modeLabels[instance.observed_mode.value])}>{fr.cockpit.modeMismatch}</b>
          )}
          {row.wanted && <span className="dim">{row.wanted}</span>}
          {badge}
        </span>
      )}
    </>
  );
}
