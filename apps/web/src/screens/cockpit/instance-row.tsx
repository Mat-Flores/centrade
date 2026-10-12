import { CircleAlertIcon } from "lucide-react";
import type { ReactNode } from "react";

import { ObservedValue } from "@/components/observed-value";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { fr } from "@/i18n/fr";
import {
  ACTIONS,
  actionPolicy,
  currentCommand,
  describeCommand,
  ENGINE_STALE_MS,
  stateView,
  unseenProblems,
  VERIFIED_SHOWN_MS,
  wantedDiffers,
} from "@/lib/cockpit";
import { formatAge } from "@/lib/format";
import type { ActionType, Command, Instance } from "@/lib/instances";
import { cn } from "@/lib/utils";

export interface InstanceRowProps {
  instance: Instance;
  commands: Command[];
  nowIso: string;
  degraded: boolean;
  /** Rôles operator et admin : les autres ne voient aucun bouton d'action. */
  canAct: boolean;
  /** Administrateur : seul rôle à rouvrir les entrées et démarrer une instance qui n'est pas paper. */
  isAdmin: boolean;
  seen: ReadonlySet<string>;
  onSeen: (commandId: string) => void;
  onAction: (instance: Instance, action: ActionType) => void;
  /** Contenu propre à l'écran hôte (écran Stratégies : « Ce qui tourne réellement »), sous les actions. */
  children?: ReactNode;
}

const typeLabel = (type: string) => fr.cockpit.command.types[type] ?? type;

export function InstanceRow({ instance, commands, nowIso, degraded, canAct, isAdmin, seen, onSeen, onAction, children }: InstanceRowProps) {
  const nowMs = Date.parse(nowIso);
  const view = stateView(instance, nowMs);
  const mode = instance.observed_mode;
  const modeLabel = fr.bar.modes[mode.value];

  const own = commands.filter((c) => c.instance_id === instance.id);
  const problems = unseenProblems(own, seen);
  const latest = currentCommand(instance, own);

  const modeBadge = instance.mode_mismatch ? (
    <Badge variant="danger">{fr.cockpit.modeMismatch}</Badge>
  ) : (
    <Badge variant={mode.value === "live" ? "live" : "default"}>{modeLabel}</Badge>
  );

  return (
    <li className="flex flex-col gap-4 p-4 sm:p-5" data-instance={instance.name}>
      <div className="grid gap-x-8 gap-y-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]" data-dimmed={degraded || undefined}>
        <div className="flex min-w-0 flex-col gap-2">
          <h3 className="truncate font-mono text-lg font-semibold tracking-tight">{instance.name}</h3>
          <div className="flex flex-wrap items-center gap-2">
            <ObservedValue
              mono={false}
              value={mode.value === "unknown" ? "unknown" : modeBadge}
              observedAt={mode.observed_at}
              serverTime={nowIso}
              staleAfterMs={ENGINE_STALE_MS}
            />
            {instance.mode_mismatch && (
              <span className="text-sm text-muted-foreground">
                {fr.cockpit.modeMismatchDetail(fr.bar.modes[instance.desired_mode], modeLabel)}
              </span>
            )}
            {instance.desired_mode === "paper" && (
              <span className="text-sm text-muted-foreground" title={fr.cockpit.simulatedHint}>
                {fr.cockpit.simulated}
              </span>
            )}
          </div>
        </div>

        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <dt className="text-sm text-muted-foreground">{fr.cockpit.observedState}</dt>
            <dd className="text-base font-medium">
              <ObservedValue
                mono={false}
                value={view.kind === "unknown" ? "unknown" : fr.cockpit.states[view.state]}
                observedAt={instance.state.observed_at}
                serverTime={nowIso}
                staleAfterMs={ENGINE_STALE_MS}
              />
            </dd>
          </div>
          {wantedDiffers(instance, nowMs) && (
            <div className="flex flex-col gap-1">
              <dt className="text-sm text-muted-foreground">{fr.cockpit.wantedState}</dt>
              <dd className="text-base">{fr.cockpit.wantedLabels[instance.desired_state]}</dd>
            </div>
          )}
        </dl>
      </div>

      {problems.map((cmd) => (
        <ProblemNotice key={cmd.id} command={cmd} nowMs={nowMs} onSeen={onSeen} />
      ))}
      {latest && !problems.some((p) => p.id === latest.id) && <CommandLine command={latest} nowMs={nowMs} />}

      {canAct && <Actions instance={instance} degraded={degraded} role={isAdmin ? "admin" : "operator"} nowMs={nowMs} onAction={onAction} />}
      {children}
    </li>
  );
}

function CommandLine({ command, nowMs }: { command: Command; nowMs: number }) {
  const v = describeCommand(command, nowMs);
  // Une commande finie (faite ou remplacée) s'efface après un court instant ; une commande en cours reste.
  if ((v.tone === "done" || v.tone === "info") && v.ageMs > VERIFIED_SHOWN_MS) return null;
  if (v.tone === "problem") return null;
  return (
    <p
      data-command-status={command.status}
      className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
    >
      {v.tone === "pending" && <Spinner />}
      <span className="font-medium">{typeLabel(command.type)}</span>
      <span>{fr.cockpit.command.status[v.status]}</span>
      <span className="text-muted-foreground">{formatAge(v.ageMs)}</span>
    </p>
  );
}

/** Sans cadre ni fond : la ligne est déjà dans un panneau. L'icône et le titre en graisse la distinguent. */
function ProblemNotice({ command, nowMs, onSeen }: { command: Command; nowMs: number; onSeen: (id: string) => void }) {
  const v = describeCommand(command, nowMs);
  if (v.tone !== "problem") return null;
  return (
    <div role="alert" data-command-status={command.status} className="flex items-start gap-2 text-sm">
      <CircleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="flex flex-col gap-2">
        <p className="font-semibold">{fr.cockpit.command.problemTitle}</p>
        <p>
          <span className="font-medium">{typeLabel(command.type)}</span> : {fr.cockpit.command.status[v.status]}{" "}
          <span className="text-muted-foreground">({formatAge(v.ageMs)})</span>
        </p>
        <p>
          {fr.cockpit.command.reason} : {v.reason ?? fr.cockpit.command.noReason}
        </p>
        <div>
          <Button type="button" variant="outline" onClick={() => onSeen(command.id)}>
            {fr.cockpit.command.seen}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Actions({
  instance,
  degraded,
  role,
  nowMs,
  onAction,
}: {
  instance: Instance;
  degraded: boolean;
  role: "operator" | "admin";
  nowMs: number;
  onAction: InstanceRowProps["onAction"];
}) {
  const policies = ACTIONS.map((action) => [action, actionPolicy(action, { instance, degraded, nowMs, role })] as const);
  const disabled = policies.filter(([, p]) => !p.enabled);
  const reasonId = (action: ActionType) => `reason-${instance.id}-${action}`;
  return (
    <div className="flex flex-col gap-2">
      <div role="group" aria-label={fr.cockpit.actions.label(instance.name)} className="flex flex-wrap gap-2">
        {policies.map(([action, policy]) => (
          <Button
            key={action}
            type="button"
            variant={action === "flatten" ? "destructive" : "outline"}
            // `aria-disabled` : le bouton reste focalisable ; sa raison, visible dessous, lui est reliée.
            aria-disabled={policy.enabled ? undefined : true}
            aria-describedby={policy.enabled ? undefined : reasonId(action)}
            className={cn(!policy.enabled && "cursor-not-allowed opacity-50")}
            onClick={() => policy.enabled && onAction(instance, action)}
          >
            {fr.cockpit.actions[action]}
          </Button>
        ))}
      </div>
      {disabled.length > 0 && (
        <ul className="flex flex-col gap-0.5 text-sm text-muted-foreground">
          {disabled.map(([action, policy]) => (
            <li key={action} id={reasonId(action)}>
              {fr.cockpit.reasons.unavailable(fr.cockpit.actions[action], policy.reason ?? "")}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
