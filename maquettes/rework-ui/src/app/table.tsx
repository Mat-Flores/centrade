import type { ReactNode } from "react";

/** Tableau en grille : défile dans son cadre quand la place manque, jamais dans la page. */
export function DataTable({ label, cols, minW, head, right = [], children }: { label: string; cols: string; minW: number; head: string[]; right?: number[]; children: ReactNode }) {
  return (
    <div className="scroll-x tbl" tabIndex={0} aria-label={label}>
      <div role="table" aria-label={label} style={{ minWidth: minW }}>
        <div role="rowgroup">
          <div role="row" className="cols" style={{ gridTemplateColumns: cols }}>
            {head.map((h, n) => <span key={n} role="columnheader" className={right.includes(n) ? "right" : ""}>{h || <span className="sr">Action</span>}</span>)}
          </div>
        </div>
        <div role="rowgroup">{children}</div>
      </div>
    </div>
  );
}
