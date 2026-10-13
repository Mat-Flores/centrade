// Tableau de bord : état des zones (repli, tailles), zone repliable et séparateur redimensionnable.
import { useCallback, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

export type ZoneId = "strip" | "comp" | "chart" | "journal" | "pairs";
export const SIDE = { min: 200, max: 480, comp: 264, journal: 420 } as const;
export const PAIRS_H = { min: 96, def: 150 } as const;
const STEP = 16;
export const isTablet = (): boolean => typeof window !== "undefined" && window.matchMedia("(max-width: 1100px)").matches;

export interface FocusReq { id: string; pair: string; nonce: number }
export interface Dash {
  collapsed: Record<ZoneId, boolean>; toggle: (z: ZoneId) => void;
  comp: number; journal: number; pairsH: number;
  setComp: (n: number) => void; setJournal: (n: number) => void; setPairsH: (n: number) => void;
  sel: string | null; setSel: (id: string | null) => void;
  focus: FocusReq | null; requestFocus: (id: string, pair: string) => void; clearFocus: () => void;
}

/** État du tableau de bord, levé dans l'écran de l'instance pour survivre aux changements d'onglet. */
export function useDash(): Dash {
  const [collapsed, setCollapsed] = useState<Record<ZoneId, boolean>>(() => ({ strip: false, comp: isTablet(), chart: false, journal: false, pairs: false }));
  const [comp, setComp] = useState<number>(SIDE.comp);
  const [journal, setJournal] = useState<number>(SIDE.journal);
  const [pairsH, setPairsH] = useState<number>(PAIRS_H.def);
  const [sel, setSel] = useState<string | null>(null);
  const [focus, setFocus] = useState<FocusReq | null>(null);
  const nonce = useRef(0);
  const toggle = useCallback((z: ZoneId) => setCollapsed((c) => ({ ...c, [z]: !c[z] })), []);
  const requestFocus = useCallback((id: string, pair: string) => { setSel(id); setFocus({ id, pair, nonce: ++nonce.current }); }, []);
  const clearFocus = useCallback(() => setFocus(null), []);
  return { collapsed, toggle, comp, journal, pairsH, setComp, setJournal, setPairsH, sel, setSel, focus, requestFocus, clearFocus };
}

export function Chevron({ open, dir = "down" }: { open: boolean; dir?: "down" | "side" }) {
  const rot = dir === "side" ? (open ? 90 : 0) : open ? 0 : -90;
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" style={{ flex: "none", transform: `rotate(${rot}deg)`, transition: "transform 0.2s var(--ease)" }}>
      <path d={dir === "side" ? "M4 2.5 8 6 4 9.5" : "M2.5 4 6 8l3.5-4"} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ToggleBtn({ open, onClick, name }: { open: boolean; onClick: () => void; name: string }) {
  const tip = open ? "Replier" : "Déplier";
  return (
    <button type="button" className="zone-tgl" aria-expanded={open} aria-label={`${tip} : ${name}`} title={tip} onClick={onClick}>
      <Chevron open={open} />
    </button>
  );
}

/** Zone du tableau de bord : panneau à part, repliable. Une zone latérale repliée devient un rail de 36 px. */
export function Zone({ id, name, dash, side, actions, className = "", children, label }: {
  id: ZoneId; name: string; dash: Dash; side?: boolean; actions?: ReactNode; className?: string; children: ReactNode; label?: string;
}) {
  const closed = dash.collapsed[id];
  if (closed && side) {
    return (
      <button type="button" className={`panel zone zone-rail ${className}`} aria-expanded={false} aria-label={`Déplier : ${name}`} title="Déplier" onClick={() => dash.toggle(id)}>
        <Chevron open={false} dir="side" />
        <span className="zone-rail-t">{name}</span>
      </button>
    );
  }
  return (
    <section className={`panel zone ${closed ? "is-closed" : ""} ${className}`} aria-label={label ?? name}>
      <header className="panel-head">
        <span className="zone-title">{name}</span>
        <span className="sp" />
        {actions}
        <ToggleBtn open={!closed} onClick={() => dash.toggle(id)} name={name} />
      </header>
      {!closed && children}
    </section>
  );
}

/** Séparateur : glisser (pointeur capturé), flèches par pas de 16 px, double clic pour revenir à la valeur par défaut. */
export function Separator({ orientation, value, min, max, onChange, reset, dir, label }: {
  orientation: "vertical" | "horizontal"; value: number; min: number; max: number; onChange: (n: number) => void; reset: number; dir: 1 | -1; label: string;
}) {
  const drag = useRef<{ p: number; v: number } | null>(null);
  const vertical = orientation === "vertical"; // barre verticale : sépare deux zones côte à côte
  const clamp = (n: number) => Math.max(min, Math.min(max, Math.round(n)));
  const down = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { p: vertical ? e.clientX : e.clientY, v: value };
  };
  const move = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    onChange(clamp(drag.current.v + dir * ((vertical ? e.clientX : e.clientY) - drag.current.p)));
  };
  const up = (e: PointerEvent<HTMLDivElement>) => { drag.current = null; if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId); };
  const key = (e: KeyboardEvent) => {
    const k = e.key;
    const plus = vertical ? k === "ArrowRight" : k === "ArrowDown";
    const minus = vertical ? k === "ArrowLeft" : k === "ArrowUp";
    if (!plus && !minus) return;
    e.preventDefault();
    onChange(clamp(value + dir * (plus ? STEP : -STEP)));
  };
  return (
    <div role="separator" aria-orientation={orientation} aria-label={label} aria-valuenow={Math.round(value)} aria-valuemin={min} aria-valuemax={max}
      tabIndex={0} className={`sep sep-${vertical ? "v" : "h"}`}
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onLostPointerCapture={() => { drag.current = null; }}
      onDoubleClick={() => onChange(reset)} onKeyDown={key}>
      <i aria-hidden="true" />
    </div>
  );
}

/** Grille de l'observation : Composition | centre | Journal, séparés par des séparateurs qui sont aussi les gouttières. */
export function ObsGrid({ dash, left, center, right }: { dash: Dash; left: ReactNode; center: ReactNode; right: ReactNode }) {
  const wl = dash.collapsed.comp ? 36 : dash.comp;
  const wr = dash.collapsed.journal ? 36 : dash.journal;
  const sep = (closed: boolean, value: number, set: (n: number) => void, reset: number, dir: 1 | -1, label: string) =>
    closed
      ? <div className="sep-gap" aria-hidden="true" />
      : <Separator orientation="vertical" value={value} min={SIDE.min} max={SIDE.max} onChange={set} reset={reset} dir={dir} label={label} />;
  return (
    <div className="obs-grid" style={{ "--w-left": `${wl}px`, "--w-right": `${wr}px` } as CSSProperties}>
      {left}
      {sep(dash.collapsed.comp, dash.comp, dash.setComp, SIDE.comp, 1, "Largeur de la Composition")}
      {center}
      {sep(dash.collapsed.journal, dash.journal, dash.setJournal, SIDE.journal, -1, "Largeur du Journal")}
      {right}
    </div>
  );
}
