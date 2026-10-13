import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Button } from "../ui/ui";

export interface MenuItem { label: string; hint?: string; href?: string; onSelect?: () => void; current?: boolean; danger?: boolean }

/** Menu déroulant (role="menu") : s'ouvre sous le bouton, flèches / Début / Fin, Échap et clic à côté ferment.
 *  Le panneau est en position fixe pour ne jamais être coupé par un tableau qui défile. */
export function Menu({ label, items, align = "right", ghost, small = true, className = "", ariaLabel, title }: {
  label: ReactNode; items: MenuItem[]; align?: "left" | "right"; ghost?: boolean; small?: boolean; className?: string; ariaLabel?: string; title?: string;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left?: number; right?: number }>({ top: 0 });
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();

  const show = () => {
    const r = btn.current!.getBoundingClientRect();
    setPos({ top: r.bottom + 8, ...(align === "right" ? { right: Math.max(8, innerWidth - r.right) } : { left: Math.max(8, r.left) }) });
    setOpen(true);
  };
  const close = (refocus: boolean) => { setOpen(false); if (refocus) btn.current?.focus(); };
  const entries = () => Array.from(panel.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);

  useEffect(() => {
    if (!open) return;
    entries()[0]?.focus();
    const down = (e: PointerEvent) => !wrap.current?.contains(e.target as Node) && setOpen(false);
    const away = () => setOpen(false);
    addEventListener("pointerdown", down);
    addEventListener("resize", away);
    addEventListener("scroll", away, true);
    return () => { removeEventListener("pointerdown", down); removeEventListener("resize", away); removeEventListener("scroll", away, true); };
  }, [open]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.stopPropagation(); close(true); return; }
    if (e.key === "Tab") { setOpen(false); return; }
    const list = entries();
    const at = list.indexOf(document.activeElement as HTMLElement);
    const to = e.key === "ArrowDown" ? (at + 1) % list.length : e.key === "ArrowUp" ? (at - 1 + list.length) % list.length : e.key === "Home" ? 0 : e.key === "End" ? list.length - 1 : -1;
    if (to >= 0) { e.preventDefault(); list[to].focus(); }
  };

  return (
    <div ref={wrap} className={`menu ${className}`}>
      <Button
        ref={btn} variant={ghost ? "ghost" : undefined} small={small} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} aria-label={ariaLabel} title={title}
        onClick={() => (open ? close(false) : show())}
        onKeyDown={(e) => { if (e.key === "ArrowDown" && !open) { e.preventDefault(); show(); } }}
      >{label}</Button>
      {open && (
        <div ref={panel} id={id} role="menu" aria-label={ariaLabel} className="menu-panel" style={pos} onKeyDown={onKey}>
          {items.map((it) => {
            // setTimeout : sinon l'Entrée qui a validé l'item active aussi le bouton principal de la fenêtre qui s'ouvre aussitôt
            const pick = () => { close(true); setTimeout(() => it.onSelect?.(), 0); };
            const cls = `menu-item ${it.danger ? "danger" : ""}`;
            const inner = <><span className="mi-label">{it.label}</span>{it.hint && <span className="mi-hint">{it.hint}</span>}</>;
            return it.href ? (
              <a key={it.label} role="menuitem" tabIndex={-1} className={cls} href={it.href} aria-current={it.current ? "page" : undefined} onClick={() => setOpen(false)}>{inner}</a>
            ) : (
              <button key={it.label} type="button" role="menuitem" tabIndex={-1} className={cls} onClick={pick}>{inner}</button>
            );
          })}
        </div>
      )}
    </div>
  );
}
