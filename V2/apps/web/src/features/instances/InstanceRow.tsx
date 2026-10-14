import { Link } from "@/app/Link";
import { ALL_TAB } from "@/app/router";
import { fr } from "@/i18n/fr";
import { needsAttention, rowAction, rowCommand } from "@/lib/instance-row";
import type { Command, Instance } from "@/lib/instances";
import type { Me } from "@/lib/session";
import { Button } from "@/ui/ui";

import type { ConfirmedAction } from "./ActionDialog";
import { refusal } from "./errors";
import { BalanceCell, RealizedCell, SinceCell, TradesCell, UnrealizedCell } from "./Figures";
import { RowActions } from "./RowActions";
import { StateCell } from "./StateCell";
import { useSendAction } from "./useSendAction";

export interface RowContext {
  nowMs: number;
  commands: readonly Command[];
  seen: ReadonlySet<string>;
  onSeen: (commandId: string) => void;
  degraded: boolean;
  role: Me["role"];
  onConfirm: (instanceId: string, action: ConfirmedAction) => void;
}

/** What the sub-line of an instance says: engine, strategy and version; the account is on hover. */
function Subline({ instance }: { instance: Instance }) {
  const t = fr.instances;
  const strategy = instance.strategy ? t.strategyVersion(instance.strategy.name, instance.strategy.version) : t.noStrategy;
  const account = instance.account ? `${instance.account.label} (${instance.account.currency})` : t.noAccount;
  return <span className="sec" data-tip={t.nameTip(instance.engine, strategy, account)}>{instance.engine} · {strategy}</span>;
}

export function InstanceRow({ instance, ctx }: { instance: Instance; ctx: RowContext }) {
  const { nowMs, commands, seen, degraded, role } = ctx;
  const send = useSendAction(instance.id);
  const command = rowCommand(instance, commands, seen, nowMs);
  const action = rowAction(instance, { degraded, nowMs, role, busy: command?.tone === "pending" });
  const sendError = send.isError ? refusal(send.error, fr.instances.confirm.errorFallback).text : null;
  return (
    <div role="row" className={`r tall ${needsAttention(instance, commands, seen, nowMs) ? "warn-row" : ""}`} data-instance={instance.name}>
      <span role="cell" className="r-name">
        <Link className="cover" to={{ page: "instance", id: instance.id, tab: ALL_TAB }}>{instance.name}</Link>
        <Subline instance={instance} />
      </span>
      <span role="cell" className="t"><StateCell instance={instance} nowMs={nowMs} command={command} /></span>
      <span role="cell" className="right"><BalanceCell instance={instance} nowMs={nowMs} /></span>
      <span role="cell" className="right"><RealizedCell instance={instance} nowMs={nowMs} /></span>
      <span role="cell" className="right"><UnrealizedCell /></span>
      <span role="cell" className="right hide-sm"><TradesCell instance={instance} nowMs={nowMs} /></span>
      <span role="cell" className="right hide-sm"><SinceCell instance={instance} nowMs={nowMs} /></span>
      <span role="cell" className="act-cell">
        <RowActions instance={instance} action={action} canAct={role !== "viewer"} sending={send.isPending} onSend={(a) => send.mutate(a)} onConfirm={ctx.onConfirm} />
      </span>
      {command?.tone === "problem" && (
        <span role="cell" className="row-err">
          <span role="alert">
            <strong>{fr.instances.command.problemTitle}.</strong> {command.line}. {fr.instances.command.reason} : {command.reason}{" "}
          </span>
          <Button small onClick={() => ctx.onSeen(command.command.id)}>{fr.instances.command.seen}</Button>
        </span>
      )}
      {sendError && <span role="cell" className="row-err"><span role="alert">{sendError}</span></span>}
    </div>
  );
}
