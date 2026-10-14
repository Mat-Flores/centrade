import { forwardRef, useEffect, useId, useRef, useState, useSyncExternalStore, type ButtonHTMLAttributes, type MouseEvent, type ReactNode } from "react";

import { fr } from "@/i18n/fr";
import { formatDecimalText, formatPnl } from "@/lib/format";
import { signOf } from "@/lib/decimal";

import "./ui.css";

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "go" | "danger" | "ghost"; small?: boolean };
export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button({ variant, small, className = "", ...p }, ref) {
  return <button ref={ref} type="button" {...p} className={`btn ${variant ?? ""} ${small ? "sm" : ""} ${className}`} />;
});

/** A function with no backend yet: visible, inert, and says so on hover. `aria-disabled` (not `disabled`) so the hover preview still shows. */
export function SoonButton({ children, variant, small, className }: { children: ReactNode; variant?: BtnProps["variant"]; small?: boolean; className?: string }) {
  return <Button variant={variant} small={small} className={className} aria-disabled="true" data-tip={fr.soon} onClick={(e) => e.preventDefault()}>{children}</Button>;
}

export type Mode = "test" | "live" | "backtest";
const MODE_KEY = { test: "dryRun", live: "live", backtest: "backtest" } as const;
export function ModeTag({ mode }: { mode: Mode }) {
  const [label, tip] = fr.glossary[MODE_KEY[mode]];
  return <span className={`mode mode-${mode}`} data-tip={tip}>{label}</span>;
}

/** Mandatory mention on every figure of the test mode or of a backtest. */
export function SimTag() {
  return <span className="tag-sim" data-tip={fr.ui.simulatedTip}>{fr.ui.simulated}</span>;
}

/** Technical term on screen (in English when that is the usage), French explanation on hover. */
export function Term({ children, tech, tip }: { children: ReactNode; tech?: string; tip: string }) {
  return <span className="term" tabIndex={0} data-tip={tip} data-tip-tech={tech}>{children}</span>;
}

export type GlossaryKey = keyof typeof fr.glossary;
export function G({ k, children }: { k: GlossaryKey; children?: ReactNode }) {
  return <Term tip={fr.glossary[k][1]}>{children ?? fr.glossary[k][0]}</Term>;
}

// ---------- unit of variations: % or currency, for the whole interface ----------
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

/** Signed variation: arrow, sign and color (green / red, or blue for what is in progress). Both values are decimal strings.
 *  With `amount`, a click switches the whole interface between % and currency; `still` follows the unit without being clickable. */
export function Delta({ pct, amount, currency = "", blue, still }: { pct: string; amount?: string; currency?: string; blue?: boolean; still?: boolean }) {
  const money = useUnit() === "money" && amount !== undefined;
  const v = money ? amount : pct;
  const sign = signOf(v);
  const cls = `delta num ${blue ? "act" : sign === 0 ? "dim" : sign > 0 ? "up" : "dn"}`;
  const body = <>{sign !== 0 && <Arrow up={sign > 0} />}{money ? formatPnl(amount, currency) : `${formatDecimalText(pct, true)}\u00a0%`}</>;
  if (amount === undefined || still) return <span className={cls}>{body}</span>;
  return <button type="button" className={`${cls} unit`} data-tip={money ? fr.ui.showPct : fr.ui.showCurrency(currency)} data-tip-live onClick={(e) => { e.stopPropagation(); toggleUnit(); }}>{body}</button>;
}

/** Value copied on click, with its small icon on the right. */
export function Copy({ value, children, what = "" }: { value: string; children?: ReactNode; what?: string }) {
  const [done, setDone] = useState(false);
  const copy = (e: MouseEvent) => {
    e.stopPropagation();
    void navigator.clipboard?.writeText(value).then(() => { setDone(true); setTimeout(() => setDone(false), 1400); }, () => {});
  };
  return (
    <button type="button" className={`copy ${done ? "is-done" : ""}`} onClick={copy} data-tip={done ? fr.ui.copied : fr.ui.copy(what)} data-tip-live>
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
      <span>{label}{required && <span className="req">{fr.ui.required}</span>}</span>
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

/** Centered modal (native dialog: trapped focus, Escape, focus returned to the trigger). Focus enters the first field, else the main button. */
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
            <Button variant="ghost" className="icon" aria-label={fr.ui.close} onClick={onClose}>
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
