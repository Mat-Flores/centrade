import { fr } from "@/i18n/fr";
import { groupTotals, type CurrencyTotal, type ModeGroup } from "@/lib/instance-stats";

const lines = (totals: CurrencyTotal[]) =>
  totals.length === 0 ? <span className="dim">{fr.observed.unknown}</span> : totals.map((t) => <span key={t.currency} className="line">{t.text}</span>);

/** Footer of one mode: exact sums per currency over that mode only, and what was left out (unknown, stale, mismatch). */
export function Totals({ group, nowMs }: { group: ModeGroup; nowMs: number }) {
  const t = groupTotals(group, nowMs);
  const notes = [
    t.unknownBalances > 0 || t.unknownPnl > 0 ? fr.instances.footPartial(Math.max(t.unknownBalances, t.unknownPnl)) : null,
    t.staleCount > 0 ? fr.instances.footStale(t.staleCount) : null,
    t.mismatchCount > 0 ? fr.instances.footMismatch(t.mismatchCount) : null,
  ].filter(Boolean);
  return (
    <div role="row" className="foot-row">
      <span role="cell" className="label" style={{ gridColumn: "1 / 3" }}>
        {fr.instances.totals}
        {notes.length > 0 && <span className="line dim small">{notes.join(" · ")}</span>}
      </span>
      <span role="cell" className="right">{lines(t.balances)}</span>
      <span role="cell" className="right">{lines(t.pnl)}</span>
      <span role="cell" className="right"><span className="dim" data-tip={fr.instances.unrealizedTip}>{fr.instances.unrealizedNone}</span></span>
      <span role="cell" className="hide-sm" />
      <span role="cell" className="hide-sm" />
      <span role="cell" />
    </div>
  );
}
