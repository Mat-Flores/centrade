import { fr } from "@/i18n/fr";

import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

const MIN = 56, STEP = 16, NARROW = "(max-width: 900px)";

/** Width shares: `columnShares(2, 1, 1)` gives three columns sharing the whole width, never exceeding it. */
export const columnShares = (...parts: number[]): string[] => parts.map((n) => `minmax(0, ${n}fr)`);

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => matchMedia(NARROW).matches);
  useEffect(() => {
    const mq = matchMedia(NARROW), on = () => setNarrow(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}

/** Grid table that always fits its width: no horizontal scrollbar, a text too long is cut and read in full on hover.
 *  The right border of a header is dragged to resize the column at the expense of its neighbour (arrow keys, double click
 *  to restore the original widths). `hideNarrow`: columns hidden under 900 px, also to be marked `hide-sm` on row cells. */
export function DataTable({ label, cols, head, right = [], hideNarrow = [], children, foot }: {
  label: string; cols: string[]; head: ReactNode[]; right?: number[]; hideNarrow?: number[]; children: ReactNode; foot?: ReactNode;
}) {
  const root = useRef<HTMLDivElement>(null);
  const drag = useRef<{ i: number; x: number; w: number[] } | null>(null);
  const [custom, setCustom] = useState<number[] | null>(null);
  const narrow = useNarrow();
  const shown = cols.map((_, n) => n).filter((n) => !narrow || !hideNarrow.includes(n));
  // Widths set by hand are dropped when the breakpoint changes (state adjusted during render, not in an effect).
  const [wasNarrow, setWasNarrow] = useState(narrow);
  if (wasNarrow !== narrow) { setWasNarrow(narrow); setCustom(null); }
  const tpl = custom && custom.length === shown.length ? custom.map((w) => `minmax(0, ${w}fr)`).join(" ") : shown.map((n) => cols[n]).join(" ");

  // Current width of each shown column, for the separators' value (a focusable separator needs one).
  const [px, setPx] = useState<number[]>([]);
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const measure = () => setPx(Array.from(el.querySelectorAll<HTMLElement>('[role="columnheader"]')).filter((c) => c.offsetParent !== null).map((c) => Math.round(c.getBoundingClientRect().width)));
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [tpl]);
  const widths = () => Array.from(root.current!.querySelectorAll<HTMLElement>('[role="columnheader"]')).filter((c) => c.offsetParent !== null).map((c) => c.getBoundingClientRect().width);
  /** Moves the limit between column i and the next: the total width does not change. */
  const shift = (w: number[], i: number, d: number) => {
    const by = Math.max(MIN - w[i]!, Math.min(w[i + 1]! - MIN, d));
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
              {h || <span className="sr">{fr.ui.columnAction}</span>}
              {shown.indexOf(n) >= 0 && shown.indexOf(n) < shown.length - 1 && (
                <i role="separator" aria-orientation="vertical" aria-label={fr.ui.columnWidth} aria-valuemin={MIN} aria-valuenow={px[shown.indexOf(n)] ?? MIN} tabIndex={0} className="col-rz" data-tip={fr.ui.columnResizeTip}
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
