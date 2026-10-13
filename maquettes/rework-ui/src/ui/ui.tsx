import { forwardRef, useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { animate, useReducedMotion } from "motion/react";
import type { Mode } from "../data/types";
import "./ui.css";

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "go" | "danger" | "ghost"; small?: boolean };
export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button({ variant, small, className = "", ...p }, ref) {
  return <button ref={ref} type="button" {...p} className={`btn ${variant ?? ""} ${small ? "sm" : ""} ${className}`} />;
});

const MODE_LABEL: Record<Mode, string> = { test: "Mode test", reel: "Mode réel", backtest: "Backtest" };
export function ModeTag({ mode }: { mode: Mode }) {
  return <span className={`mode mode-${mode}`}>{MODE_LABEL[mode]}</span>;
}

/** Mention obligatoire sur tout chiffre du mode test ou d'un backtest. */
export function SimTag() {
  return <span className="tag-sim">Simulé</span>;
}

/** Mot courant à l'écran, terme technique et explication en infobulle (voir VOCABULAIRE.md). */
export function Term({ children, tech, tip }: { children: ReactNode; tech?: string; tip: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span
      className="term"
      tabIndex={0}
      aria-describedby={open ? id : undefined}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
    >
      {children}
      {open && (
        <span role="tooltip" id={id} className="term-tip">
          {tech && <b>{tech}</b>}
          {tip}
        </span>
      )}
    </span>
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
