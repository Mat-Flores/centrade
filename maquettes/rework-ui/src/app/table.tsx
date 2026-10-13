import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

const MIN = 56, STEP = 16, NARROW = "(max-width: 900px)";

/** Parts de largeur : `fr(2, 1, 1)` donne trois colonnes qui se partagent toute la largeur, sans jamais la dépasser. */
export const fr = (...parts: number[]): string[] => parts.map((n) => `minmax(0, ${n}fr)`);

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => matchMedia(NARROW).matches);
  useEffect(() => {
    const mq = matchMedia(NARROW), on = () => setNarrow(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}

/** Tableau en grille qui tient toujours dans sa largeur : aucune barre de défilement horizontale, un texte trop long est coupé
 *  et se lit en entier au survol. La bordure droite d'un titre se glisse pour redimensionner la colonne aux dépens de sa voisine
 *  (flèches au clavier, double clic pour revenir aux largeurs d'origine). `hideNarrow` : colonnes masquées sous 900 px, à marquer
 *  aussi `hide-sm` sur les cellules des lignes. */
export function DataTable({ label, cols, head, right = [], hideNarrow = [], children, foot }: {
  label: string; cols: string[]; head: ReactNode[]; right?: number[]; hideNarrow?: number[]; children: ReactNode; foot?: ReactNode;
}) {
  const root = useRef<HTMLDivElement>(null);
  const drag = useRef<{ i: number; x: number; w: number[] } | null>(null);
  const [custom, setCustom] = useState<number[] | null>(null);
  const narrow = useNarrow();
  const shown = cols.map((_, n) => n).filter((n) => !narrow || !hideNarrow.includes(n));
  useEffect(() => setCustom(null), [narrow]);
  const tpl = custom && custom.length === shown.length ? custom.map((w) => `minmax(0, ${w}fr)`).join(" ") : shown.map((n) => cols[n]).join(" ");

  const widths = () => Array.from(root.current!.querySelectorAll<HTMLElement>('[role="columnheader"]')).filter((c) => c.offsetParent !== null).map((c) => c.getBoundingClientRect().width);
  /** Déplace la limite entre la colonne i et la suivante : la largeur totale ne change pas. */
  const shift = (w: number[], i: number, d: number) => {
    const by = Math.max(MIN - w[i], Math.min(w[i + 1] - MIN, d));
    setCustom(w.map((x, n) => (n === i ? x + by : n === i + 1 ? x - by : x)));
  };
  const down = (i: number) => (e: PointerEvent<HTMLElement>) => { e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); drag.current = { i, x: e.clientX, w: widths() }; };
  const move = (e: PointerEvent) => { const d = drag.current; if (d) shift(d.w, d.i, e.clientX - d.x); };
  const up = () => { drag.current = null; };
  const key = (i: number) => (e: KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    shift(widths(), i, e.key === "ArrowRight" ? STEP : -STEP);
  };

  return (
    <div ref={root} className="tbl" role="table" aria-label={label} style={{ "--tcols": tpl } as CSSProperties}>
      <div role="rowgroup">
        <div role="row" className="cols">
          {head.map((h, n) => (
            <span key={n} role="columnheader" className={`${right.includes(n) ? "right" : ""} ${hideNarrow.includes(n) ? "hide-sm" : ""}`}>
              {h || <span className="sr">Action</span>}
              {shown.indexOf(n) >= 0 && shown.indexOf(n) < shown.length - 1 && (
                <i role="separator" aria-orientation="vertical" aria-label="Largeur de la colonne" tabIndex={0} className="col-rz" data-tip="Glisser pour redimensionner · double clic pour réinitialiser"
                  onPointerDown={down(shown.indexOf(n))} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onDoubleClick={() => setCustom(null)} onKeyDown={key(shown.indexOf(n))} />
              )}
            </span>
          ))}
        </div>
      </div>
      <div role="rowgroup">{children}</div>
      {foot && <div role="rowgroup">{foot}</div>}
    </div>
  );
}
