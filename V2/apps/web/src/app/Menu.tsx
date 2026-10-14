import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from "react";
import { Button } from "@/ui/ui";

import { onLinkClick } from "./router";

/** `sep`: separator line above the entry. */
export interface MenuItem { label: string; hint?: string; href?: string; onSelect?: () => void; current?: boolean; danger?: boolean; sep?: boolean }

/** Menu panel (role="menu"): arrows / Home / End, Escape, Tab and a click outside close it.
 *  Fixed position so a scrolling area never cuts it; moved back if it overflows the window. */
function MenuPanel({ id, items, head, style, ariaLabel, onClose, anchor }: {
  id?: string; items: MenuItem[]; head?: ReactNode; style: CSSProperties; ariaLabel?: string; onClose: (refocus: boolean) => void; anchor?: RefObject<HTMLElement>;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const entries = () => Array.from(panel.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);

  useLayoutEffect(() => {
    const el = panel.current!, r = el.getBoundingClientRect();
    if (r.right > innerWidth - 8) el.style.left = `${Math.max(8, innerWidth - r.width - 8)}px`;
    if (r.bottom > innerHeight - 8) el.style.top = `${Math.max(8, innerHeight - r.height - 8)}px`;
    entries()[0]?.focus();
  }, []);
  useEffect(() => {
    const down = (e: PointerEvent) => { const t = e.target as Node; if (!panel.current?.contains(t) && !anchor?.current?.contains(t)) onClose(false); };
    const away = () => onClose(false);
    addEventListener("pointerdown", down);
    addEventListener("resize", away);
    addEventListener("scroll", away, true);
    return () => { removeEventListener("pointerdown", down); removeEventListener("resize", away); removeEventListener("scroll", away, true); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.stopPropagation(); onClose(true); return; }
    if (e.key === "Tab") { onClose(false); return; }
    const list = entries();
    const at = list.indexOf(document.activeElement as HTMLElement);
    const to = e.key === "ArrowDown" ? (at + 1) % list.length : e.key === "ArrowUp" ? (at - 1 + list.length) % list.length : e.key === "Home" ? 0 : e.key === "End" ? list.length - 1 : -1;
    if (to >= 0) { e.preventDefault(); list[to]?.focus(); }
  };

  return (
    <div ref={panel} id={id} role="menu" aria-label={ariaLabel} className="menu-panel" style={style} onKeyDown={onKey} onContextMenu={(e) => e.preventDefault()}>
      {head && <div className="menu-head" role="presentation">{head}</div>}
      {items.map((it) => {
        // setTimeout: otherwise the Enter that picked the item also triggers the main button of the dialog that opens at once
        const pick = () => { onClose(true); setTimeout(() => it.onSelect?.(), 0); };
        const cls = `menu-item ${it.danger ? "danger" : ""} ${it.sep ? "sep" : ""}`;
        const inner = <><span className="mi-label">{it.label}</span>{it.hint && <span className="mi-hint">{it.hint}</span>}</>;
        return it.href ? (
          <a key={it.label} role="menuitem" tabIndex={-1} className={cls} href={it.href} aria-current={it.current ? "page" : undefined} onClick={(e) => { onLinkClick(e, it.href!); onClose(false); }}>{inner}</a>
        ) : (
          <button key={it.label} type="button" role="menuitem" tabIndex={-1} className={cls} onClick={pick}>{inner}</button>
        );
      })}
    </div>
  );
}

/** Drop-down menu: opens under its button. `head`: non-clickable header block (account identity, for example). */
export function Menu({ label, items, head, align = "right", ghost, small = true, className = "", btnClassName, ariaLabel, panelLabel, title }: {
  label: ReactNode; items: MenuItem[]; head?: ReactNode; align?: "left" | "right"; ghost?: boolean; small?: boolean; className?: string; btnClassName?: string; ariaLabel?: string; panelLabel?: string; title?: string;
}) {
  const [pos, setPos] = useState<CSSProperties | null>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const id = useId();
  const open = pos !== null;

  const show = () => {
    const r = btn.current!.getBoundingClientRect();
    setPos({ top: r.bottom + 8, ...(align === "right" ? { right: Math.max(8, innerWidth - r.right) } : { left: Math.max(8, r.left) }) });
  };
  const close = (refocus: boolean) => { setPos(null); if (refocus) btn.current?.focus(); };

  return (
    <div ref={wrap} className={`menu ${className}`}>
      <Button
        ref={btn} variant={ghost ? "ghost" : undefined} small={small} className={btnClassName} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} aria-label={ariaLabel} title={title}
        onClick={() => (open ? close(false) : show())}
        onKeyDown={(e) => { if (e.key === "ArrowDown" && !open) { e.preventDefault(); show(); } }}
      >{label}</Button>
      {pos && <MenuPanel id={id} items={items} head={head} style={pos} ariaLabel={panelLabel ?? ariaLabel} onClose={close} anchor={wrap} />}
    </div>
  );
}

export interface ContextAt { x: number; y: number; items: MenuItem[]; label: string; from: HTMLElement | null }

/** Context menu (right click, Menu key, "..." button): opens at the requested point, returns focus to the row on close. */
export function ContextMenu({ at, onClose }: { at: ContextAt | null; onClose: () => void }) {
  if (!at) return null;
  return <MenuPanel key={`${at.x}-${at.y}`} items={at.items} ariaLabel={at.label} style={{ left: at.x, top: at.y, transformOrigin: "top left" }} onClose={(refocus) => { onClose(); if (refocus) at.from?.focus(); }} />;
}
