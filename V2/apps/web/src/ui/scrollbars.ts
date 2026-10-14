// Overlay scrollbars: they take no space (nothing shifts when they appear), show only while hovering a scrollable
// area or while scrolling, then fade. Native bars are hidden in tokens.css. One pair of thumbs serves the whole page;
// wheel, keyboard and touch stay native.
const IDLE = 900, MIN = 28, PAD = 2;

export function installScrollbars(): void {
  const mk = (axis: "v" | "h") => {
    const el = Object.assign(document.createElement("div"), { className: `sb sb-${axis}`, popover: "manual" });
    el.setAttribute("aria-hidden", "true");
    document.body.append(el);
    return el;
  };
  const bars = { v: mk("v"), h: mk("h") };
  let host: Element | null = null, timer = 0, dragging = false;

  const root = () => document.scrollingElement ?? document.documentElement;
  const scrolls = (el: Element) => {
    if (el === root()) return true;
    const cs = getComputedStyle(el);
    return (/(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 1) || (/(auto|scroll)/.test(cs.overflowX) && el.scrollWidth > el.clientWidth + 1);
  };
  const scroller = (n: EventTarget | null): Element => {
    for (let el = n instanceof Element ? n : null; el && el !== document.body; el = el.parentElement) if (el !== document.documentElement && scrolls(el)) return el;
    return root();
  };
  const box = (el: Element) => (el === root() ? { top: 0, left: 0, right: innerWidth, bottom: innerHeight, width: innerWidth, height: innerHeight } : el.getBoundingClientRect());

  /** Places a thumb; returns the ratio thumb pixels to content pixels (0 if nothing scrolls on this axis). */
  const place = (axis: "v" | "h"): number => {
    const el = bars[axis], h = host!;
    const size = axis === "v" ? h.clientHeight : h.clientWidth, full = axis === "v" ? h.scrollHeight : h.scrollWidth, at = axis === "v" ? h.scrollTop : h.scrollLeft;
    if (full <= size + 1) { if (el.matches(":popover-open")) el.hidePopover(); return 0; }
    const b = box(h), track = (axis === "v" ? b.height : b.width) - 2 * PAD, len = Math.max(MIN, (track * size) / full), pos = ((track - len) * at) / (full - size);
    if (!el.matches(":popover-open")) el.showPopover();
    Object.assign(el.style, axis === "v"
      ? { top: `${b.top + PAD + pos}px`, left: `${b.right - 8}px`, height: `${len}px` }
      : { left: `${b.left + PAD + pos}px`, top: `${b.bottom - 8}px`, width: `${len}px` });
    return (full - size) / Math.max(1, track - len);
  };

  const hide = () => { if (dragging) return; host = null; for (const el of Object.values(bars)) el.classList.remove("on"); };
  const show = (el: Element) => {
    if (host !== el) for (const b of Object.values(bars)) if (b.matches(":popover-open")) b.hidePopover(); // goes back above a dialog opened in the meantime
    host = el;
    for (const axis of ["v", "h"] as const) bars[axis].classList.toggle("on", place(axis) > 0);
    clearTimeout(timer);
    timer = window.setTimeout(hide, IDLE);
  };

  addEventListener("scroll", (e) => { if (!dragging) show(e.target === document ? root() : (e.target as Element)); }, true);
  addEventListener("pointermove", (e) => {
    if (dragging || e.pointerType === "touch") return;
    if ((e.target as Element).classList?.contains("sb")) { clearTimeout(timer); return; }
    const el = scroller(e.target);
    if (el !== root() || el.scrollHeight > el.clientHeight + 1) show(el);
  }, { passive: true });
  addEventListener("resize", hide);

  for (const axis of ["v", "h"] as const) {
    const el = bars[axis];
    el.addEventListener("pointerdown", (e) => {
      if (!host) return;
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      dragging = true;
      const h = host, ratio = place(axis), p0 = axis === "v" ? e.clientY : e.clientX, s0 = axis === "v" ? h.scrollTop : h.scrollLeft;
      const move = (ev: PointerEvent) => { h[axis === "v" ? "scrollTop" : "scrollLeft"] = s0 + ((axis === "v" ? ev.clientY : ev.clientX) - p0) * ratio; place(axis); };
      const up = () => { dragging = false; el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); el.removeEventListener("pointercancel", up); show(h); };
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
      el.addEventListener("pointercancel", up);
    });
  }
}
