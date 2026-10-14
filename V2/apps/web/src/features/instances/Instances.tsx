import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Arrow, Empty, PageHead } from "@/app/common";
import { useDegradation } from "@/app/degradation";
import { Link } from "@/app/Link";
import { ALL_TAB } from "@/app/router";
import { fr } from "@/i18n/fr";
import { useServerNow } from "@/lib/clock";
import { canCreate } from "@/lib/cockpit";
import { needsAttention, visibleRows } from "@/lib/instance-row";
import { commandsQuery, instancesQuery, type Instance } from "@/lib/instances";
import { useSeenCommands } from "@/lib/seen";
import { meQuery } from "@/lib/session";
import { Button } from "@/ui/ui";

import { ActionDialog, type PendingConfirm } from "./ActionDialog";
import { CreateInstanceDialog } from "./CreateInstanceDialog";
import type { RowContext } from "./InstanceRow";
import { BacktestSection, ModeTable, NewInstanceButton } from "./ModeTable";
import { TableSkeleton } from "./TableSkeleton";

const FILTER_FROM = 7; // a filter only earns its place on a longer list
const MODES = ["live", "paper"] as const;

/** Instances list: two real tables (Live, Dry-run), observed and dated; Backtest is announced, not faked. */
export function Instances() {
  const t = fr.instances;
  const instances = useQuery(instancesQuery);
  const commands = useQuery(commandsQuery);
  const me = useQuery(meQuery).data;
  const { degraded } = useDegradation();
  const nowMs = Date.parse(useServerNow());
  const { seen, markSeen } = useSeenCommands();
  const [creating, setCreating] = useState(false);
  const [confirm, setConfirm] = useState<PendingConfirm | null>(null);
  const [query, setQuery] = useState("");

  const role = me?.role ?? "viewer";
  const items = instances.data?.items;
  const cmds = commands.data?.items ?? [];
  const create = canCreate(degraded);
  const ctx: RowContext = { nowMs, commands: cmds, seen, onSeen: markSeen, degraded, role, onConfirm: (instanceId, action) => setConfirm({ instanceId, action }) };
  const attention = (items ?? []).filter((i) => needsAttention(i, cmds, seen, nowMs));
  const createAction = role === "viewer" ? null : { ...create, open: () => create.enabled && setCreating(true) };
  // A list read with a limit and a next page is partial: its totals are never exact.
  const truncated = instances.data?.next_cursor != null;
  // The filter only applies while its field is shown: a list that shrank below the threshold shows everything.
  const q = (items?.length ?? 0) >= FILTER_FROM ? query : "";

  return (
    <div className="page">
      <PageHead title={t.title} desc={t.desc}>
        {createAction && <NewInstanceButton action={createAction} />}
      </PageHead>

      {degraded && <div role="status" className="notice">{t.degraded}</div>}
      {commands.isError && (
        <div className="notice loss" role="alert">
          <span><strong>{t.commandsError.title}.</strong> {t.commandsError.body}</span>
          <Button small onClick={() => void commands.refetch()}>{t.commandsError.retry}</Button>
        </div>
      )}
      {truncated && <div className="notice" role="status">{t.truncated}</div>}
      {attention.length > 0 && <AttentionNotice rows={attention} />}
      {items && items.length >= FILTER_FROM && (
        <input className="input filter" type="search" aria-label={t.filter} placeholder={t.filterPlaceholder} value={query} onChange={(e) => setQuery(e.target.value)} />
      )}

      {instances.isPending && MODES.map((m) => <TableSkeleton key={m} title={t.modeGroups[m]} />)}
      {instances.isError && (
        <div className="panel">
          <Empty title={t.loadError.title}>
            <span role="alert">{t.loadError.body}</span>
            <Button variant="go" onClick={() => void instances.refetch()}>{t.loadError.retry}</Button>
          </Empty>
        </div>
      )}
      {items && (
        <>
          {MODES.map((m) => {
            const all = items.filter((i) => i.desired_mode === m);
            return <ModeTable key={m} mode={m} all={all} rows={visibleRows(all, q, cmds, seen, nowMs)} query={q} ctx={ctx} create={createAction} truncated={truncated} />;
          })}
          <BacktestSection />
        </>
      )}
      <p className="quiet">{t.footnote}</p>

      <CreateInstanceDialog open={creating} onClose={() => setCreating(false)} degraded={degraded} />
      <ActionDialog pending={confirm} instance={items?.find((i) => i.id === confirm?.instanceId)} nowMs={nowMs} degraded={degraded} role={role} onClose={() => setConfirm(null)} />
    </div>
  );
}

function AttentionNotice({ rows }: { rows: Instance[] }) {
  return (
    <div className="notice loss" role="status">
      <Arrow up={false} />
      <span>
        {fr.instances.attentionPrefix}
        {rows.map((i, n) => <span key={i.id}>{n > 0 && fr.instances.attentionJoin}<Link to={{ page: "instance", id: i.id, tab: ALL_TAB }}>{i.name}</Link></span>)}
        {fr.instances.attentionSuffix}
      </span>
    </div>
  );
}
