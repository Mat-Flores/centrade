import { forwardRef, useEffect, useId, useRef, useState, useSyncExternalStore, type ButtonHTMLAttributes, type MouseEvent, type ReactNode } from "react";
import { animate, useReducedMotion } from "motion/react";
import type { Mode } from "../data/types";
import { signedMoney, signedPct } from "../lib/format";
import "./ui.css";

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "go" | "danger" | "ghost"; small?: boolean };
export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button({ variant, small, className = "", ...p }, ref) {
  return <button ref={ref} type="button" {...p} className={`btn ${variant ?? ""} ${small ? "sm" : ""} ${className}`} />;
});

const MODE_KEY = { test: "dryRun", reel: "live", backtest: "backtest" } as const;
export function ModeTag({ mode }: { mode: Mode }) {
  return <span className={`mode mode-${mode}`} data-tip={GLOSSARY[MODE_KEY[mode]][1]}>{GLOSSARY[MODE_KEY[mode]][0]}</span>;
}

/** Mention obligatoire sur tout chiffre du mode test ou d'un backtest. */
export function SimTag() {
  return <span className="tag-sim" data-tip="Argent fictif : aucun de ces chiffres n'est réel.">Simulé</span>;
}

/** Terme technique à l'écran (en anglais quand c'est l'usage), explication en français au survol (voir VOCABULAIRE.md). */
export function Term({ children, tech, tip }: { children: ReactNode; tech?: string; tip: string }) {
  return <span className="term" tabIndex={0} data-tip={tip} data-tip-tech={tech}>{children}</span>;
}

/** Termes techniques : libellé affiché, puis explication de l'aperçu de survol. */
export const GLOSSARY = {
  timeframe: ["Timeframe", "Unité de temps : la durée d'une bougie du graphique."],
  stopLoss: ["Stop-loss", "Prix auquel la position est vendue pour limiter la perte."],
  takeProfit: ["Take-profit", "Prix auquel la position est vendue pour encaisser le gain."],
  trailing: ["Trailing stop", "Stop suiveur : le stop-loss remonte avec le prix, sans jamais redescendre."],
  realized: ["Realized PnL", "Résultat encaissé : celui des trades terminés, frais déduits."],
  unrealized: ["Unrealized PnL", "Résultat en cours : celui des positions encore ouvertes, au dernier prix reçu."],
  wins: ["Wins", "Trades terminés en gain."],
  losses: ["Losses", "Trades terminés en perte."],
  stake: ["Stake", "Mise : le montant engagé dans le trade, dans la devise du compte."],
  fees: ["Fees", "Frais de l'exchange, achat et vente."],
  slippage: ["Slippage", "Glissement : l'écart entre le prix attendu et le prix d'exécution."],
  provider: ["Provider", "Le moteur de trading qui fait tourner l'instance. Une stratégie n'existe que pour un provider."],
  dryRun: ["Dry-run", "Mode test : le bot trade avec de l'argent fictif. Tous les chiffres sont simulés."],
  live: ["Live", "Mode réel : le bot trade avec l'argent du compte."],
  backtest: ["Backtest", "Le bot rejoue une période passée. Un backtest n'est pas une prévision."],
  totp: ["TOTP", "Code à 6 chiffres, renouvelé toutes les 30 secondes par l'application d'authentification."],
} as const;
export type GlossaryKey = keyof typeof GLOSSARY;
export function G({ k, children }: { k: GlossaryKey; children?: ReactNode }) {
  return <Term tip={GLOSSARY[k][1]}>{children ?? GLOSSARY[k][0]}</Term>;
}

// ---------- unité des variations : % ou devise, pour toute l'interface ----------
let unit: "pct" | "money" = "pct";
const unitSubs = new Set<() => void>();
const subUnit = (cb: () => void) => (unitSubs.add(cb), () => unitSubs.delete(cb));
export const useUnit = (): "pct" | "money" => useSyncExternalStore(subUnit, () => unit);
export function toggleUnit(): void {
  unit = unit === "pct" ? "money" : "pct";
  unitSubs.forEach((l) => l());
}

export function Arrow({ up }: { up: boolean }) {
  return (
    <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true" className="arrow">
      <path d={up ? "M4 1 7.5 7h-7z" : "M4 7 .5 1h7z"} fill="currentColor" />
    </svg>
  );
}

/** Variation signée : flèche, signe et couleur (vert / rouge, ou bleu pour ce qui est en cours).
 *  Avec `amount`, un clic bascule toute l'interface entre % et devise ; `still` suit l'unité sans être cliquable. */
export function Delta({ pct, amount, currency = "", blue, still }: { pct: number; amount?: number; currency?: string; blue?: boolean; still?: boolean }) {
  const money = useUnit() === "money" && amount !== undefined;
  const v = money ? amount : pct;
  const zero = Math.round(Math.abs(v) * 100) === 0;
  const cls = `delta num ${blue ? "act" : zero ? "dim" : v > 0 ? "up" : "dn"}`;
  const body = <>{!zero && <Arrow up={v > 0} />}{money ? signedMoney(amount, currency) : signedPct(pct)}</>;
  if (amount === undefined || still) return <span className={cls}>{body}</span>;
  return <button type="button" className={`${cls} unit`} data-tip={money ? "Afficher en %" : `Afficher en ${currency}`} data-tip-live onClick={(e) => { e.stopPropagation(); toggleUnit(); }}>{body}</button>;
}

/** Valeur copiable au clic, avec sa petite icône à droite. */
export function Copy({ value, children, what = "" }: { value: string; children?: ReactNode; what?: string }) {
  const [done, setDone] = useState(false);
  const copy = (e: MouseEvent) => {
    e.stopPropagation();
    void navigator.clipboard?.writeText(value).then(() => { setDone(true); setTimeout(() => setDone(false), 1400); }, () => {});
  };
  return (
    <button type="button" className={`copy ${done ? "is-done" : ""}`} onClick={copy} data-tip={done ? "Copié" : `Copier ${what}`.trim()} data-tip-live>
      <span className="copy-t">{children ?? value}</span>
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
        {done ? <path d="M2.5 6.5 5 9l4.5-5.5" /> : <><rect x="4" y="4" width="6.5" height="6.5" rx="1.2" /><path d="M8 4V2.7A1.2 1.2 0 0 0 6.8 1.5H2.7A1.2 1.2 0 0 0 1.5 2.7v4.1A1.2 1.2 0 0 0 2.7 8H4" /></>}
      </svg>
    </button>
  );
}

export function Panel({ title, actions, children, className = "", foot }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; foot?: ReactNode }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="panel-head">
          {title}
          <span className="sp" />
          {actions}
        </header>
      )}
      {children}
      {foot && <footer className="panel-foot">{foot}</footer>}
    </section>
  );
}

export function Field({ label, hint, error, required, children }: { label: string; hint?: string; error?: string; required?: boolean; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}{required && <span className="req"> (obligatoire)</span>}</span>
      {children}
      {error ? <small className="err" role="alert">{error}</small> : hint ? <small>{hint}</small> : null}
    </label>
  );
}

export function Progress({ value, label }: { value: number; label: string }) {
  return (
    <div className="progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value)}>
      <i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

const FIELD = 'input:not([type=hidden]):not([type=color]):not([type=checkbox]):not([type=radio]):not(:disabled), select:not(:disabled), textarea:not(:disabled)';

/** Fenêtre modale centrée (dialog natif : focus piégé, Échap, retour du focus au déclencheur). Le focus entre sur le premier champ, sinon sur le bouton principal. */
export function Dialog({ open, onClose, title, children, foot, wide, narrow }: { open: boolean; onClose: () => void; title: string; children: ReactNode; foot?: ReactNode; wide?: boolean; narrow?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      const target = d.querySelector<HTMLElement>("[data-autofocus]") ?? d.querySelector<HTMLElement>(`.dialog-body ${FIELD.replace(/, /g, ", .dialog-body ")}`) ?? d.querySelector<HTMLElement>(".dialog-foot .btn.go, .dialog-foot .btn:last-child");
      target?.focus();
    }
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref} className={`dialog ${wide ? "wide" : ""} ${narrow ? "narrow" : ""}`} onClose={onClose} aria-labelledby={titleId}
      onClick={(e) => e.target === ref.current && onClose()}
    >
      {open && (
        <>
          <header className="dialog-head">
            <h2 id={titleId}>{title}</h2>
            <Button variant="ghost" className="icon" aria-label="Fermer" onClick={onClose}>
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M3.5 3.5l9 9M12.5 3.5l-9 9" /></svg>
            </Button>
          </header>
          <div className="dialog-body">{children}</div>
          {foot && <footer className="dialog-foot">{foot}</footer>}
        </>
      )}
    </dialog>
  );
}

/** Chiffre qui glisse vers sa nouvelle valeur ; la largeur reste fixe grâce aux chiffres tabulaires. */
export function AnimatedNumber({ value, format, className = "" }: { value: number; format: (n: number) => string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const prev = useRef(value);
  const reduce = useReducedMotion();
  useEffect(() => {
    const el = ref.current;
    const from = prev.current;
    prev.current = value;
    if (!el || reduce || from === value || !Number.isFinite(from) || !Number.isFinite(value)) return;
    const ctrl = animate(from, value, { duration: 0.4, ease: [0.2, 0.8, 0.2, 1], onUpdate: (v) => (el.textContent = format(v)) });
    return () => ctrl.stop();
  }, [value, format, reduce]);
  return <span ref={ref} className={`num ${className}`}>{format(value)}</span>;
}
