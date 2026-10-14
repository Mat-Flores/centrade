// The single hover preview for the whole interface. It shows for: an element carrying `data-tip`,
// a `title` attribute (taken over, so the browser tooltip is not doubled), and any text cut by an ellipsis.
// Rendered in the top layer (popover): also visible over a modal dialog.
const DELAY = 350;

export function installTips(): void {
  const tip = Object.assign(document.createElement("div"), { id: "tip", className: "tip", popover: "manual" });
  tip.setAttribute("role", "tooltip");
  document.body.append(tip);
  let cur: HTMLElement | null = null, title: string | null = null, timer = 0, warmUntil = 0;

  const clipped = (el: HTMLElement) => el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).textOverflow === "ellipsis";
  const find = (n: EventTarget | null): HTMLElement | null => {
    let el = n instanceof Element ? n.closest<HTMLElement>("[data-tip], [title]") : null;
    if (el) return el;
    for (el = n instanceof HTMLElement ? n : null; el && el !== document.body; el = el.parentElement) if (clipped(el)) return el;
    return null;
  };

  const hide = () => {
    clearTimeout(timer);
    if (!cur) return;
    if (title !== null && !cur.hasAttribute("title")) cur.title = title;
    if (cur.getAttribute("aria-describedby") === "tip") cur.removeAttribute("aria-describedby");
    cur = null; title = null;
    if (tip.matches(":popover-open")) { tip.hidePopover(); warmUntil = Date.now() + 400; }
  };

  const show = (el: HTMLElement) => {
    title = el.hasAttribute("title") ? el.title : null;
    const text = el.dataset.tip ?? title ?? el.innerText;
    if (!text?.trim()) return;
    if (title !== null) el.removeAttribute("title");
    cur = el;
    tip.replaceChildren();
    if (el.dataset.tipTech) tip.append(Object.assign(document.createElement("b"), { textContent: el.dataset.tipTech }));
    tip.append(text.trim());
    if (tip.matches(":popover-open")) tip.hidePopover();
    tip.showPopover(); // reopened each time: goes back above a dialog opened in the meantime
    if (!el.hasAttribute("aria-describedby")) el.setAttribute("aria-describedby", "tip");
    const r = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
    const below = r.bottom + 8 + t.height <= innerHeight - 8 || r.top < t.height + 16;
    tip.style.left = `${Math.max(8, Math.min(r.left, innerWidth - t.width - 8))}px`;
    tip.style.top = `${below ? r.bottom + 8 : r.top - t.height - 8}px`;
  };

  const enter = (target: EventTarget | null, now = false) => {
    const el = find(target);
    if (el === cur) return;
    hide();
    if (!el) return;
    if (now || Date.now() < warmUntil) show(el);
    else timer = window.setTimeout(() => show(el), DELAY);
  };

  addEventListener("pointerover", (e) => e.pointerType !== "touch" && enter(e.target));
  addEventListener("pointerdown", hide, true);
  addEventListener("scroll", hide, true);
  addEventListener("keydown", (e) => e.key === "Escape" && hide(), true);
  addEventListener("focusin", (e) => (e.target as Element).matches?.(":focus-visible") && enter(e.target, true));
  addEventListener("focusout", hide);
  // A `data-tip-live` element changes its text on click ("Copied"): the preview is read again at once.
  addEventListener("click", (e) => { const el = (e.target as Element).closest?.("[data-tip-live]"); if (el) setTimeout(() => { hide(); enter(el, true); }, 0); });
}
