import { columnShares, DataTable } from "@/app/table";
import { Empty, SectionHead } from "@/app/common";
import { fr } from "@/i18n/fr";
import type { ModeGroupId } from "@/lib/instance-stats";
import type { Instance } from "@/lib/instances";
import { Button, G, Panel, SimTag } from "@/ui/ui";

import { InstanceRow, type RowContext } from "./InstanceRow";
import { Totals } from "./Totals";

// Eight columns as shares of the width: the table always fits its frame (see app/table.tsx).
const COLS = columnShares(2.2, 1.4, 1.4, 1.3, 1.1, 0.8, 1, 1.4);
const RIGHT = [2, 3, 4, 5, 6];
const HIDE = [5, 6];

const c = fr.instances.columns;
const HEAD = [c.name, c.state, c.balance, <G key="r" k="realized">{c.realized}</G>, <G key="u" k="unrealized">{c.unrealized}</G>, c.trades, c.since, ""];

/** One mode, one table. `all` is every instance of the mode (the filter only narrows `rows`). */
export function ModeTable({ mode, all, rows, query, ctx, onCreate }: { mode: ModeGroupId; all: Instance[]; rows: Instance[]; query: string; ctx: RowContext; onCreate: (() => void) | null }) {
  const t = fr.instances;
  const title = t.modeGroups[mode];
  const empty = mode === "live" ? t.emptyLive : t.emptyPaper;
  return (
    <section aria-label={title}>
      <SectionHead title={<><G k={mode === "live" ? "live" : "dryRun"} />{mode === "paper" && <SimTag />}<span className="count">{all.length}</span></>} desc={t.modeDesc[mode]} />
      <Panel className="tbl">
        {rows.length > 0 ? (
          <DataTable label={t.tableLabel(title)} cols={COLS} head={HEAD} right={RIGHT} hideNarrow={HIDE} foot={<Totals group={{ mode, label: title, instances: all }} nowMs={ctx.nowMs} />}>
            {rows.map((i) => <InstanceRow key={i.id} instance={i} ctx={ctx} />)}
          </DataTable>
        ) : all.length > 0 ? (
          <Empty title={t.noMatch.title}><span>{t.noMatch.body(query.trim())}</span></Empty>
        ) : (
          <Empty title={empty.title}>
            <span>{empty.body}</span>
            {mode === "paper" && onCreate && <Button variant="go" onClick={onCreate}>{t.create.open}</Button>}
          </Empty>
        )}
      </Panel>
    </section>
  );
}

/** Backtest: announced, never faked. Nothing is shown that the API does not provide. */
export function BacktestSection() {
  return (
    <section aria-label={fr.instances.backtest.title}>
      <SectionHead title={<><G k="backtest" /><SimTag /></>} />
      <Panel><Empty title={fr.soon}><span>{fr.instances.backtest.pending}</span></Empty></Panel>
    </section>
  );
}
