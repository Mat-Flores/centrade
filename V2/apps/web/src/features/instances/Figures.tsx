import { fr } from "@/i18n/fr";
import { stateView } from "@/lib/cockpit";
import { formatDurationShort, formatTimestamp } from "@/lib/format";
import { observedTip } from "@/lib/instance-row";
import { summarizeRow } from "@/lib/instance-stats";
import type { Instance } from "@/lib/instances";

const SIGN = { "-1": "dn", "0": "dim", "1": "up" } as const;
const unknown = (tip: string) => <span className="dim" data-tip={tip}>{fr.observed.unknown}</span>;

/** Balance, one line per currency: observed and dated, never added across currencies. */
export function BalanceCell({ instance, nowMs }: { instance: Instance; nowMs: number }) {
  const row = summarizeRow(instance, nowMs);
  if (row.balances === null) return unknown(fr.observed.unknownHint);
  return (
    <span className={row.balancesStale ? "dim-stale" : ""} data-tip={observedTip(instance.balances, nowMs) ?? undefined}>
      {row.balancesText.map((t) => <span key={t} className="line">{t}</span>)}
    </span>
  );
}

/** Realized PnL (net of fees), one signed line per currency. */
export function RealizedCell({ instance, nowMs }: { instance: Instance; nowMs: number }) {
  const row = summarizeRow(instance, nowMs);
  if (instance.realized_pnl.value === null) return unknown(fr.observed.unknownHint);
  return (
    <span className={row.pnlStale ? "dim-stale" : ""} data-tip={observedTip(instance.realized_pnl, nowMs) ?? undefined}>
      {row.pnl.map((t, n) => <span key={t} className={`line ${SIGN[String(row.pnlSigns[n] ?? 0) as keyof typeof SIGN]}`}>{t}</span>)}
    </span>
  );
}

/** Unrealized PnL has no source yet: a dash that says so, never a zero. */
export function UnrealizedCell() {
  return <span className="dim" data-tip={fr.instances.unrealizedTip}>{fr.instances.unrealizedNone}</span>;
}

export function TradesCell({ instance, nowMs }: { instance: Instance; nowMs: number }) {
  const row = summarizeRow(instance, nowMs);
  if (instance.closed_trades.value === null) return unknown(fr.observed.unknownHint);
  const tip = [fr.instances.tradesTip(row.closedTrades, row.openPositions), observedTip(instance.closed_trades, nowMs)].filter(Boolean).join("\n");
  // The compact text carries its own "+?" and "(périmé)"; the sentence below is what a screen reader gets.
  return (
    <span className={row.tradesStale ? "warn" : ""} data-tip={tip}>
      <span aria-hidden="true">{row.tradesCompact}</span>
      <span className="sr">{fr.instances.tradesTip(row.closedTrades, row.openPositions)}{row.tradesStale && ` (${fr.observed.stale})`}</span>
    </span>
  );
}

/** Since when the bot runs; shown only while the observed state is known and fresh, else a dash. Empty when it does not run. */
export function SinceCell({ instance, nowMs }: { instance: Instance; nowMs: number }) {
  const view = stateView(instance, nowMs);
  if (view.kind !== "fresh") return <span className="dim" data-tip={fr.instances.sinceUnknownTip}>{fr.instances.sinceNone}</span>;
  if (instance.started_at === null || view.state === "stopped") return null;
  const seconds = (nowMs - Date.parse(instance.started_at)) / 1000;
  if (Number.isNaN(seconds)) return null;
  return <span data-tip={fr.instances.sinceTip(formatTimestamp(instance.started_at))}>{formatDurationShort(seconds)}</span>;
}
