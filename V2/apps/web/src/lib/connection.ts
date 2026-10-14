import { fr } from "@/i18n/fr";

import { stateView, type Degradation } from "./cockpit";
import { formatAge } from "./format";
import type { Instance } from "./instances";

/** Connection pill of the shell. Said only from what is observed: a dot is colored only if something is observed. */

export interface Connection {
  tone: "neutral" | "ok" | "warn";
  text: string;
  tip: string;
}

/** An instance counts as "running" when it should be, or is seen, doing something: a stopped, wanted-stopped one does not. */
const isRunning = (i: Instance, nowMs: number): boolean => {
  const v = stateView(i, nowMs);
  return i.desired_state !== "stopped" || (v.kind !== "unknown" && v.state !== "stopped");
};

export function connectionSummary(instances: readonly Instance[] | undefined, degradation: Degradation, nowMs: number): Connection {
  const t = fr.shell;
  const causes = degradation.causes.map((c) => ({ stream: t.causeStream, health: t.causeHealth, "health-unknown": t.causeHealthUnknown })[c]).join(" ");
  if (!instances) return { tone: degradation.degraded ? "warn" : "neutral", text: degradation.degraded ? t.degraded : t.sessionOpen, tip: degradation.degraded ? causes : t.sessionOpenTip };
  const running = instances.filter((i) => isRunning(i, nowMs));
  if (running.length === 0) return { tone: degradation.degraded ? "warn" : "neutral", text: degradation.degraded ? t.degraded : t.sessionOpen, tip: [t.noBotRunning, causes].filter(Boolean).join("\n") };
  const views = running.map((i) => ({ i, v: stateView(i, nowMs) }));
  const fresh = views.filter((x) => x.v.kind === "fresh").length;
  const stale = running.length - fresh;
  const ages = views.flatMap(({ i }) => (i.state.observed_at ? [nowMs - Date.parse(i.state.observed_at)] : []));
  const oldest = ages.length > 0 ? t.oldestObservation(formatAge(Math.max(0, ...ages))) : t.noObservation;
  const count = `${fresh}/${running.length}`;
  const lines = [stale > 0 ? t.staleCount(stale) : t.allFresh(running.length), oldest, causes].filter(Boolean);
  if (degradation.degraded) return { tone: "warn", text: t.botsDegraded(count), tip: lines.join("\n") };
  return { tone: stale > 0 ? "warn" : "ok", text: stale > 0 ? t.botsStale(count) : t.bots(count), tip: lines.join("\n") };
}
