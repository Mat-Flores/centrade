// Disposition du tableau de bord d'une instance : ordre des zones, repli, tailles. Commune à toutes les instances.
// En mémoire, comme le reste de la maquette. « Réinitialiser la disposition » (menu du compte, Paramètres) revient au défaut.
import { useSyncExternalStore } from "react";

export type ZoneId = "balance" | "ind" | "comp" | "chart" | "pairs" | "journal";
/** Emplacements, dans l'ordre : 2 en haut, puis colonne gauche, centre haut, centre bas, colonne droite. */
export const SLOT = { top: [0, 1], left: 2, center: [3, 4], right: 5 } as const;
export interface Layout {
  /** Quelle zone occupe quel emplacement. Deux zones s'échangent par glisser-déposer, dans la même rangée (haut ou grille). */
  slots: ZoneId[];
  closed: Record<ZoneId, boolean>;
  /** Largeur d'une zone quand elle occupe une colonne latérale, ou la première place de la rangée du haut. */
  width: Record<ZoneId, number>;
  /** Hauteur des deux emplacements du centre (haut, bas). Les colonnes latérales, elles, suivent la hauteur visible de l'écran. */
  centerH: [number, number];
  /** Augmente à chaque échange ou réinitialisation : les zones déplacées s'animent. */
  rev: number;
}

export const SIDE = { min: 200, max: 720 } as const;
export const CENTER_H = { min: 160, def: [520, 240] } as const;
export const isTablet = (): boolean => typeof window !== "undefined" && window.matchMedia("(max-width: 1100px)").matches;

const initial = (): Layout => ({
  slots: ["balance", "ind", "comp", "chart", "pairs", "journal"],
  closed: { balance: false, ind: false, comp: isTablet(), chart: false, pairs: false, journal: false },
  width: { balance: 400, ind: 520, comp: 264, chart: 420, pairs: 420, journal: 420 },
  centerH: [...CENTER_H.def],
  rev: 0,
});

let state = initial();
const subs = new Set<() => void>();
const set = (next: Layout) => { state = next; subs.forEach((l) => l()); };

export const useLayout = (): Layout => useSyncExternalStore((cb) => (subs.add(cb), () => subs.delete(cb)), () => state);
export const slotOf = (l: Layout, z: ZoneId): number => l.slots.indexOf(z);
const row = (slot: number) => (slot < 2 ? "top" : "grid");
/** Deux zones ne s'échangent que dans la même rangée : le solde ne va pas dans la grille, le graphique pas en haut. */
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
