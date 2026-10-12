import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Cellules des tableaux compacts : en-têtes fixes, chiffres à droite en chasse fixe (DESIGN.md, SPEC §9). */
export const TH = "px-3 py-2 text-left text-sm font-medium text-muted-foreground";
export const THR = "px-3 py-2 text-right text-sm font-medium text-muted-foreground";
export const TD = "px-3 py-2 align-top";
export const TDR = "px-3 py-2 align-top text-right font-mono";

/**
 * Zone défilable d'un tableau : `tabIndex` pour que le défilement se fasse au clavier (WCAG 2.1.1).
 * Pas de hauteur maximale : aucune ligne n'est coupée, la page défile. Une ombre sur le bord dit qu'il reste des colonnes
 * hors champ (`scroll-shadow`). `bare` : sans cadre, quand le tableau est déjà dans un panneau (jamais de carte dans une carte).
 */
export function TableShell({ label, minWidth = "min-w-[48rem]", dimmed, bare, children }: { label: string; minWidth?: string; dimmed?: boolean; bare?: boolean; children: ReactNode }) {
  return (
    <div className={cn("scroll-shadow overflow-x-auto bg-card", !bare && "rounded-xl border")} tabIndex={0} role="region" aria-label={label} data-dimmed={dimmed || undefined}>
      <table className={cn("w-full border-collapse text-sm", minWidth)}>
        <caption className="sr-only">{label}</caption>
        {children}
      </table>
    </div>
  );
}
export const THEAD = "sticky top-0 z-10 border-b bg-card";
