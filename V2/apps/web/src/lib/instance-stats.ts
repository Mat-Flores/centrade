import { fr } from "@/i18n/fr";

import { ENGINE_STALE_MS, stateView, wantedDiffers } from "./cockpit";
import { signOf, sumDecimals } from "./decimal";
import { formatMoney, formatPnl, freshness } from "./format";
import type { DesiredState, Instance, Observed } from "./instances";

/** Pure derivations for the instance list. Nothing here turns a wish into a fact, or an unknown into zero (I1). */

export type ObservedValue<T> = { kind: "unknown" } | { kind: "known"; value: T; stale: boolean };

/**
 * A dated value as it can be shown now. No value, no date or an unreadable date: unknown. Stale as soon
 * as the server says so or the age computed on the server clock passes the engine threshold.
 */
export function observedValue<T>(obs: Observed<T | null> | null | undefined, nowMs: number): ObservedValue<T> {
  if (!obs || obs.value === null) return { kind: "unknown" };
  const f = freshness({ observedAt: obs.observed_at, serverTime: new Date(nowMs).toISOString(), staleAfterMs: ENGINE_STALE_MS });
  if (f.state === "unknown") return { kind: "unknown" };
  return { kind: "known", value: obs.value, stale: obs.stale || f.state === "stale" };
}

/* ---------------------------------------------------------------- grouping */

export type ModeGroupId = "paper" | "live";
export const MODE_GROUPS: readonly ModeGroupId[] = ["paper", "live"];

export interface ModeGroup {
  mode: ModeGroupId;
  /** "Dry-run" or "Live". */
  label: string;
  instances: Instance[];
}

/** Groups by the mode the instance was created in. Empty groups are kept out; the order is fixed (Dry-run, Live). */
export function groupByMode(instances: readonly Instance[]): ModeGroup[] {
  return MODE_GROUPS.map((mode) => ({
    mode,
    label: fr.instances.modeGroups[mode],
    instances: instances.filter((i) => i.desired_mode === mode),
  })).filter((g) => g.instances.length > 0);
}

/* ---------------------------------------------------------------- row summary */

export interface BalanceLine {
  currency: string;
  total: string;
  free: string;
}

export interface RowSummary {
  /** Observed state, said as observed: "en marche", "en marche (périmé)" or "inconnu". Never the wanted state. */
  state: string;
  stateKind: "fresh" | "stale" | "unknown";
  /** Shown only when the wanted state differs from the fresh observed one; always worded as a wish. */
  wanted: string | null;
  openPositions: string;
  closedTrades: string;
  /** One line per currency, never added across currencies. */
  pnl: string[];
  /** Sign of each `pnl` line (0 when unknown or empty): the caller colors, the text already carries the sign. */
  pnlSigns: (-1 | 0 | 1)[];
  /** "12 +2" (closed trades, open positions), "12 +?" when the positions are unknown, "(périmé)" when stale, or "inconnu". */
  tradesCompact: string;
  tradesStale: boolean;
  /** Whether any figure of the row is stale. */
  balancesStale: boolean;
  pnlStale: boolean;
  balances: BalanceLine[] | null;
  balancesText: string[];
}

const staleMark = (text: string, stale: boolean) => (stale ? fr.observed.staleValue(text) : text);
const wantedText = (s: DesiredState) => fr.cockpit.wantedLabels[s];

export function summarizeRow(instance: Instance, nowMs: number): RowSummary {
  const view = stateView(instance, nowMs);
  const stateKind = view.kind;
  const state = view.kind === "unknown" ? fr.observed.unknown : staleMark(fr.cockpit.states[view.state], view.kind === "stale");

  const positions = observedValue(instance.open_positions, nowMs);
  const trades = observedValue(instance.closed_trades, nowMs);
  const pnl = observedValue(instance.realized_pnl, nowMs);
  const balances = observedValue(instance.balances, nowMs);

  return {
    state,
    stateKind,
    wanted: wantedDiffers(instance, nowMs) ? fr.instances.wanted(wantedText(instance.desired_state)) : null,
    openPositions: positions.kind === "unknown" ? fr.observed.unknown : staleMark(fr.instances.positions(positions.value), positions.stale),
    closedTrades: trades.kind === "unknown" ? fr.observed.unknown : staleMark(fr.instances.trades(trades.value), trades.stale),
    pnl:
      pnl.kind === "unknown"
        ? [fr.observed.unknown]
        : pnl.value.length === 0
          ? [staleMark(fr.instances.noClosedTrade, pnl.stale)]
          : pnl.value.map((m) => staleMark(formatPnl(m.amount, m.currency), pnl.stale)),
    pnlSigns: pnl.kind === "unknown" ? [0] : pnl.value.length === 0 ? [0] : pnl.value.map((m) => signOf(m.amount)),
    tradesCompact:
      trades.kind === "unknown"
        ? fr.observed.unknown
        : staleMark(
            // An open-position count that is unknown is "?", never nothing: absence would read as zero.
            `${trades.value}${positions.kind === "unknown" ? " +?" : positions.value > 0 ? ` +${positions.value}` : ""}`,
            trades.stale || (positions.kind === "known" && positions.stale),
          ),
    tradesStale: (trades.kind === "known" && trades.stale) || (positions.kind === "known" && positions.stale),
    balancesStale: balances.kind === "known" && balances.stale,
    pnlStale: pnl.kind === "known" && pnl.stale,
    balances: balances.kind === "unknown" ? null : balances.value,
    balancesText:
      balances.kind === "unknown"
        ? [fr.observed.unknown]
        : balances.value.map((b) => staleMark(formatMoney(b.total, b.currency), balances.stale)),
  };
}

/* ---------------------------------------------------------------- footer totals */

export interface CurrencyTotal {
  currency: string;
  /** Exact decimal sum string. */
  amount: string;
  text: string;
}

export interface GroupTotals {
  mode: ModeGroupId;
  pnl: CurrencyTotal[];
  balances: CurrencyTotal[];
  /** Instances left out of a sum because the value is unknown: the total is partial, and says so. */
  unknownPnl: number;
  unknownBalances: number;
  /** Instances counted with a stale value. */
  staleCount: number;
  /** Instances left out because their observed mode differs from the wanted one: mixing real and simulated money is refused. */
  mismatchCount: number;
}

function sumPerCurrency(entries: { currency: string; amount: string }[], format: (a: string, c: string) => string): CurrencyTotal[] {
  const byCurrency = new Map<string, string[]>();
  for (const e of entries) byCurrency.set(e.currency, [...(byCurrency.get(e.currency) ?? []), e.amount]);
  return [...byCurrency.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([currency, amounts]) => {
      const amount = sumDecimals(amounts);
      return { currency, amount, text: format(amount, currency) };
    });
}

/** Footer of one mode group: exact per-currency sums, only over instances of that group, never across currencies. */
export function groupTotals(group: ModeGroup, nowMs: number): GroupTotals {
  const pnl: { currency: string; amount: string }[] = [];
  const balances: { currency: string; amount: string }[] = [];
  let unknownPnl = 0;
  let unknownBalances = 0;
  let staleCount = 0;
  let mismatchCount = 0;
  for (const i of group.instances) {
    if (i.mode_mismatch) {
      mismatchCount += 1;
      continue;
    }
    const p = observedValue(i.realized_pnl, nowMs);
    const b = observedValue(i.balances, nowMs);
    if (p.kind === "unknown") unknownPnl += 1;
    if (b.kind === "unknown") unknownBalances += 1;
    if ((p.kind === "known" && p.stale) || (b.kind === "known" && b.stale)) staleCount += 1;
    if (p.kind === "known") pnl.push(...p.value.map((m) => ({ currency: m.currency, amount: m.amount })));
    if (b.kind === "known") balances.push(...b.value.map((x) => ({ currency: x.currency, amount: x.total })));
  }
  return {
    mode: group.mode,
    pnl: sumPerCurrency(pnl, formatPnl),
    balances: sumPerCurrency(balances, formatMoney),
    unknownPnl,
    unknownBalances,
    staleCount,
    mismatchCount,
  };
}
