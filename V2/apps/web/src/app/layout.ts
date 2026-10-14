// Dashboard layout of an instance: zone order, collapse, sizes. Shared by all instances.
// In memory only. "Reset the layout" (account menu, Settings) goes back to the default.
import { useSyncExternalStore } from "react";

export type ZoneId = "balance" | "indicators" | "composition" | "chart" | "pairs" | "journal";
/** Slots, in order: 2 on top, then left column, center top, center bottom, right column. */
export const SLOT = { top: [0, 1], left: 2, center: [3, 4], right: 5 } as const;
export interface Layout {
  /** Which zone holds which slot. Two zones swap by drag and drop, within the same row (top or grid). */
  slots: ZoneId[];
  closed: Record<ZoneId, boolean>;
  /** Width of a zone when it holds a side column, or the first place of the top row. */
  width: Record<ZoneId, number>;
  /** Height of the two center slots (top, bottom). Side columns follow the visible height of the screen. */
  centerH: [number, number];
  /** Increases on each swap or reset: moved zones animate. */
  rev: number;
}

export const SIDE = { min: 200, max: 720 } as const;
export const CENTER_H = { min: 160, def: [520, 240] } as const;
export const isTablet = (): boolean => typeof window !== "undefined" && window.matchMedia("(max-width: 1100px)").matches;

const initial = (): Layout => ({
  slots: ["balance", "indicators", "composition", "chart", "pairs", "journal"],
  closed: { balance: false, indicators: false, composition: isTablet(), chart: false, pairs: false, journal: false },
  width: { balance: 400, indicators: 520, composition: 264, chart: 420, pairs: 420, journal: 420 },
  centerH: [...CENTER_H.def],
  rev: 0,
});

let state = initial();
const subs = new Set<() => void>();
const set = (next: Layout) => { state = next; subs.forEach((l) => l()); };

export const useLayout = (): Layout => useSyncExternalStore((cb) => (subs.add(cb), () => subs.delete(cb)), () => state);
export const slotOf = (l: Layout, z: ZoneId): number => l.slots.indexOf(z);
const row = (slot: number) => (slot < 2 ? "top" : "grid");
/** Two zones only swap within the same row: the balance does not go into the grid, the chart not on top. */
export const canSwap = (l: Layout, a: ZoneId, b: ZoneId): boolean => a !== b && row(slotOf(l, a)) === row(slotOf(l, b));

export const layout = {
  get: (): Layout => state,
  defaults: initial,
  toggle: (z: ZoneId) => set({ ...state, closed: { ...state.closed, [z]: !state.closed[z] } }),
  swap: (a: ZoneId, b: ZoneId) => {
    if (!canSwap(state, a, b)) return;
    set({ ...state, rev: state.rev + 1, slots: state.slots.map((z) => (z === a ? b : z === b ? a : z)) });
  },
  setWidth: (z: ZoneId, n: number) => set({ ...state, width: { ...state.width, [z]: n } }),
  setCenterH: (i: 0 | 1, n: number) => set({ ...state, centerH: i === 0 ? [n, state.centerH[1]] : [state.centerH[0], n] }),
  reset: () => set({ ...initial(), rev: state.rev + 1 }),
};
