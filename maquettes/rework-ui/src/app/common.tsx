import { useCallback, useState, type ReactNode } from "react";
import type { Instance, Mode, ObservedState } from "../data/types";
import type { State } from "../data/state";
import { age, signedPct } from "../lib/format";

/** Au-delà d'une heure sans observation, une valeur est périmée.
 *  À remplacer par `STALE_AFTER_SEC` de screens/instance/shared.tsx dès qu'il existe (même valeur, 3600). */
export const STALE_AFTER = 3600;
export const LIVE_STATES: ObservedState[] = ["lancement", "verification", "actif", "achats_en_pause"];

export const ageOf = (i: Instance, s: State) => Math.max(0, s.cursor - i.observedAt);
export const isStale = (i: Instance, s: State) => i.mode !== "backtest" && i.observed !== "arrete" && ageOf(i, s) > STALE_AFTER;
export const isRunning = (i: Instance) => i.mode !== "backtest" && LIVE_STATES.includes(i.observed);
export const ageText = (sec: number) => (sec < 5 ? "à l'instant" : age(sec));

export const OBSERVED_LABEL: Record<ObservedState, string> = {
  arrete: "Arrêté", lancement: "Lancement", verification: "Vérification", actif: "Actif",
  achats_en_pause: "Achats en pause", erreur: "Erreur", inconnu: "Inconnu",
};

export const MODE_ORDER: Mode[] = ["reel", "test", "backtest"];

export function Arrow({ up }: { up: boolean }) {
  return (
    <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true" className="arrow">
      <path d={up ? "M4 1 7.5 7h-7z" : "M4 7 .5 1h7z"} fill="currentColor" />
    </svg>
  );
}

/** Variation signée : signe, flèche et couleur (vert / rouge, ou bleu pour ce qui est en cours). */
export function Delta({ pct, blue }: { pct: number; blue?: boolean }) {
  const text = signedPct(pct);
  const zero = !/[+−]/.test(text);
  const tone = blue ? "act" : zero ? "dim" : pct > 0 ? "up" : "dn";
  return (
    <span className={`delta ${tone}`}>
      {!zero && <Arrow up={pct > 0} />}
      {text}
    </span>
  );
}

/** Exécute une action du magasin ; un refus (Error en français) est gardé pour l'afficher sur place. */
export function useAttempt(): [string | null, (fn: () => unknown) => boolean, () => void] {
  const [err, setErr] = useState<string | null>(null);
  const run = useCallback((fn: () => unknown) => {
    try { fn(); setErr(null); return true; } catch (e) { setErr(e instanceof Error ? e.message : String(e)); return false; }
  }, []);
  return [err, run, useCallback(() => setErr(null), [])];
}

export function InlineError({ message }: { message: string | null }) {
  return <div role="alert" aria-live="polite" className={message ? "inline-err" : "sr"}>{message}</div>;
}

export function PageHead({ title, desc, children }: { title: ReactNode; desc?: ReactNode; children?: ReactNode }) {
  return (
    <div className="page-head">
      <div className="page-head-text">
        <h1>{title}</h1>
        {desc && <p>{desc}</p>}
      </div>
      {children && <div className="page-head-act">{children}</div>}
    </div>
  );
}

/** Titre de section d'une page : titre, description d'une phrase, et une action facultative à droite. */
export function SectionHead({ title, desc, extra, children }: { title: ReactNode; desc?: ReactNode; extra?: ReactNode; children?: ReactNode }) {
  return (
    <div className="sec-head">
      <div>
        <h2>{title}{extra}</h2>
        {desc && <p>{desc}</p>}
      </div>
      {children}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty" role="status">
      <strong className="empty-title">{title}</strong>
      {children}
    </div>
  );
}

export function Chevron() {
  return <svg className="chev" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3.5 10.5 8 6 12.5" /></svg>;
}

/** Validation en ligne : une erreur s'affiche à la sortie du champ (blur) ou après un clic sur le bouton principal. */
export function useTouched(): { show: (k: string) => boolean; blur: (k: string) => void; all: () => void; reset: () => void } {
  const [t, setT] = useState<Record<string, boolean>>({});
  const [all, setAll] = useState(false);
  return {
    show: (k) => all || !!t[k],
    blur: (k) => setT((p) => (p[k] ? p : { ...p, [k]: true })),
    all: () => setAll(true),
    reset: useCallback(() => { setT({}); setAll(false); }, []),
  };
}
