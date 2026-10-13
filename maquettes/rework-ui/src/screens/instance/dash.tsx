// Tableau de bord : zone repliable et déplaçable, séparateur redimensionnable, grille de l'observation.
// La disposition (ordre, repli, tailles) vit dans app/layout.ts ; ici, seulement le trade choisi, propre à l'écran.
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type DragEvent, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";
import { CENTER_H, SIDE, SLOT, canSwap, layout, slotOf, useLayout, type Layout, type ZoneId } from "../../app/layout";

const STEP = 16;
const RAIL = 36;
const HEAD = 44; // hauteur d'un en-tête de zone (--head sous .dash)
const EDGE = 12; // marge autour du tableau de bord
const SIDE_MIN = 320; // hauteur plancher des colonnes latérales, quand le centre est replié

export interface FocusReq { id: string; pair: string; nonce: number }
export interface Dash {
  sel: string | null; setSel: (id: string | null) => void;
  focus: FocusReq | null; requestFocus: (id: string, pair: string) => void; clearFocus: () => void;
}

/** Trade choisi et demande de centrage, levés dans l'écran de l'instance pour survivre aux changements d'onglet. */
export function useDash(): Dash {
  const [sel, setSel] = useState<string | null>(null);
  const [focus, setFocus] = useState<FocusReq | null>(null);
  const nonce = useRef(0);
  const requestFocus = useCallback((id: string, pair: string) => { setSel(id); setFocus({ id, pair, nonce: ++nonce.current }); }, []);
  const clearFocus = useCallback(() => setFocus(null), []);
  return { sel, setSel, focus, requestFocus, clearFocus };
}

export function Chevron({ open, dir = "down" }: { open: boolean; dir?: "down" | "side" }) {
  const rot = dir === "side" ? (open ? 90 : 0) : open ? 0 : -90;
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" style={{ flex: "none", transform: `rotate(${rot}deg)`, transition: "transform 0.2s var(--ease)" }}>
      <path d={dir === "side" ? "M4 2.5 8 6 4 9.5" : "M2.5 4 6 8l3.5-4"} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// La zone en cours de déplacement : le navigateur ne laisse pas lire les données d'un glisser pendant le survol.
let dragged: ZoneId | null = null;

function useZoneDrag(id: ZoneId, l: Layout) {
  const [over, setOver] = useState(false);
  return {
    over,
    handle: {
      draggable: true,
      onDragStart: (e: DragEvent) => { dragged = id; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", id); },
      onDragEnd: () => { dragged = null; },
    },
    target: {
      onDragOver: (e: DragEvent) => { if (!dragged || !canSwap(l, dragged, id)) return; e.preventDefault(); e.dataTransfer.dropEffect = "move"; setOver(true); },
      onDragLeave: (e: DragEvent) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(false); },
      onDrop: (e: DragEvent) => { e.preventDefault(); setOver(false); if (dragged) layout.swap(dragged, id); dragged = null; },
    },
  };
}

const onActivate = (fn: () => void) => (e: KeyboardEvent) => {
  if (e.target !== e.currentTarget || (e.key !== "Enter" && e.key !== " ")) return;
  e.preventDefault();
  fn();
};

// Dernier échange déjà animé, par zone : une zone qui vient de changer de place apparaît en fondu, pas à chaque changement d'onglet.
const movedAt = new Map<ZoneId, number>();

/** Zone du tableau de bord. Tout l'en-tête replie ou déplie ; on le glisse sur une autre zone pour échanger leurs places.
 *  Repliée en hauteur, elle garde sa largeur (toujours réglable) ; dans une colonne latérale elle se replie en largeur, en rail de 36 px.
 *  Le contenu reste monté quand la zone se replie en hauteur : c'est ce qui permet d'animer l'ouverture. `summary` : ce qui reste visible repliée. */
export function Zone({ id, name, actions, summary, className = "", children, label }: {
  id: ZoneId; name: string; actions?: ReactNode; summary?: ReactNode; className?: string; children: ReactNode; label?: string;
}) {
  const l = useLayout();
  const drag = useZoneDrag(id, l);
  const el = useRef<HTMLElement>(null);
  const closed = l.closed[id];
  const slot = slotOf(l, id);
  const side = slot === SLOT.left || slot === SLOT.right;
  const toggle = () => layout.toggle(id);
  const cls = `panel zone zone-${id} ${side ? "zone-side" : ""} ${closed ? "is-closed" : ""} ${drag.over ? "is-drop" : ""} ${className}`;
  const tip = closed ? "Déplier" : "Replier";

  useEffect(() => {
    if ((movedAt.get(id) ?? 0) === l.rev) return;
    movedAt.set(id, l.rev);
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) el.current?.animate([{ opacity: 0, transform: "scale(0.985)" }, { opacity: 1, transform: "none" }], { duration: 260, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)" });
  }, [id, l.rev]);

  if (closed && side) {
    return (
      <section ref={el} className={`${cls} zone-rail`} aria-label={label ?? name} {...drag.target}>
        <div className="zone-rail-h" role="button" tabIndex={0} aria-expanded={false} aria-label={`Déplier : ${name}`} onClick={toggle} onKeyDown={onActivate(toggle)} {...drag.handle}>
          <Chevron open={false} dir="side" />
          <span className="zone-rail-t">{name}</span>
        </div>
      </section>
    );
  }
  return (
    <section ref={el} className={cls} aria-label={label ?? name} {...drag.target}>
      <header className="panel-head zone-head" role="button" tabIndex={0} aria-expanded={!closed} aria-label={`${tip} : ${name}`} onClick={toggle} onKeyDown={onActivate(toggle)} {...drag.handle}>
        <Chevron open={!closed} />
        <span className="zone-title">{name}</span>
        {closed && summary}
        <span className="sp" />
        {actions}
        <svg className="zone-grip" width="10" height="14" viewBox="0 0 10 14" aria-hidden="true" data-tip="Glisser l'en-tête sur une autre zone pour échanger leurs places">
          {[2, 7, 12].flatMap((y) => [2, 8].map((x) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.2" fill="currentColor" />))}
        </svg>
      </header>
      <div className="zone-fold" {...(closed ? { inert: "" } : {})}>
        <div className="zone-body">{children}</div>
      </div>
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

/** Grille de l'observation : colonne gauche | centre (une ou deux zones empilées) | colonne droite. La page défile.
 *  Au centre, chaque zone a sa hauteur, réglable par son bord bas, jusqu'à l'écran entier. Les colonnes latérales ne se règlent
 *  pas en hauteur : elles occupent ce qui est visible de l'écran, et grandissent à mesure que le haut de la page défile hors de vue.
 *  Une zone absente de la vue (les paires, dans l'onglet d'une paire) libère sa place. */
export function ObsGrid({ zones }: { zones: Partial<Record<ZoneId, ReactNode>> }) {
  const l = useLayout();
  const grid = useRef<HTMLDivElement>(null);
  const [maxH, setMaxH] = useState(900);
  const at = (slot: number): ZoneId | null => (zones[l.slots[slot]] ? l.slots[slot] : null);
  const left = at(SLOT.left), right = at(SLOT.right);
  const center = SLOT.center.map((slot, i) => ({ id: at(slot), i: i as 0 | 1 })).filter((c): c is { id: ZoneId; i: 0 | 1 } => c.id !== null);
  const defaults = layout.defaults();
  const col = (id: ZoneId | null) => (id === null ? [] : [l.closed[id] ? `${RAIL}px` : `${l.width[id]}px`, "var(--gap)"]);
  const sep = (id: ZoneId, dir: 1 | -1) =>
    l.closed[id]
      ? <div className="sep-gap" aria-hidden="true" />
      : <Separator orientation="vertical" value={l.width[id]} min={SIDE.min} max={SIDE.max} onChange={(n) => layout.setWidth(id, n)} reset={defaults.width[id]} dir={dir} label="Largeur de la colonne" />;

  // Colonnes latérales = partie visible de la colonne du centre : même haut, même bas, à tout moment. Le haut suit la grille,
  // puis se cale sous la barre ; le bas est celui du centre, ou celui de l'écran si le centre le dépasse.
  // Une mesure par image au plus, écrite dans une variable CSS (aucun rendu React) : la hauteur glisse ensuite par transition.
  useLayoutEffect(() => {
    const el = grid.current!, mid = el.querySelector<HTMLElement>(".in-center")!;
    const bar = () => (document.querySelector<HTMLElement>(".bar")?.offsetHeight ?? 56) + EDGE;
    let frame = 0;
    const measure = () => {
      frame = 0;
      const top = Math.max(bar(), el.getBoundingClientRect().top);
      const last = Array.from(mid.querySelectorAll<HTMLElement>(".cz")).at(-1);
      const bottom = Math.max(last?.getBoundingClientRect().bottom ?? 0, top + SIDE_MIN);
      el.style.setProperty("--side-h", `${Math.round(Math.min(innerHeight - EDGE, bottom) - top)}px`);
    };
    const update = () => { frame ||= requestAnimationFrame(measure); };
    const resize = () => { setMaxH(innerHeight - bar() - EDGE); update(); };
    measure();
    resize();
    const ro = new ResizeObserver(update);
    ro.observe(mid);
    addEventListener("scroll", update, { passive: true });
    addEventListener("resize", resize);
    return () => { cancelAnimationFrame(frame); ro.disconnect(); removeEventListener("scroll", update); removeEventListener("resize", resize); };
  }, []);

  return (
    <div ref={grid} className="obs-grid" style={{ gridTemplateColumns: [...col(left), "minmax(0, 1fr)", ...col(right).reverse()].join(" ") }}>
      {left && <>{zones[left]}{sep(left, 1)}</>}
      <div className="in-center">
        {center.map(({ id, i }, n) => {
          const closed = l.closed[id], h = Math.min(l.centerH[i], maxH);
          return [
            <div key={id} className="cz" style={{ height: closed ? HEAD : h }}>{zones[id]}</div>,
            closed
              ? n < center.length - 1 && <div key={`${id}-gap`} className="sep-gap" aria-hidden="true" />
              : <Separator key={`${id}-sep`} orientation="horizontal" value={h} min={CENTER_H.min} max={maxH} onChange={(v) => layout.setCenterH(i, v)} reset={CENTER_H.def[i]} dir={1} label="Hauteur de la zone" />,
          ];
        })}
      </div>
      {right && <>{sep(right, -1)}{zones[right]}</>}
    </div>
  );
}
