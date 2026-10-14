import { useCallback, useState, type ReactNode } from "react";

// Pieces shared by the screens that depend on no data. What depends on instances comes with the screens.
export { Arrow, Delta } from "@/ui/ui";

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

/** Section title of a page: title, one-sentence description, and an optional action on the right. */
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

/** Inline validation: an error shows when leaving the field (blur) or after a click on the main button. */
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
