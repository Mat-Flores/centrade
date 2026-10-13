import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CAUSE_LABEL } from "../../data/store";
import type { LogEntry, Trade } from "../../data/types";
import { clock, dateTime, dayOffset, duration, money, price, signedMoney, signedPct } from "../../lib/format";
import { ContextMenu, type ContextAt } from "../../app/Menu";
import { Arrow, Button, Delta } from "../../ui/ui";
import { Chevron, Zone, type Dash } from "./dash";
import { groupJournal, tradeKind, type JFilter, type JItem } from "./journalGroups";

const PAGE = 60;
const ease = [0.2, 0.8, 0.2, 1] as const;
const TABS: { id: JFilter; label: string }[] = [{ id: "tous", label: "Tous" }, { id: "gain", label: "Gain" }, { id: "perte", label: "Perte" }, { id: "cours", label: "En cours" }];
const WORD = { gain: "gain", perte: "perte", cours: "en cours" } as const;

function Line({ e, showPair, fresh }: { e: LogEntry; showPair: boolean; fresh: boolean }) {
  const text = !showPair && e.pair ? e.text.replace(` ${e.pair}`, "") : e.text;
  return (
    <motion.div initial={fresh ? { opacity: 0, y: 12 } : false} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.28, ease }}
      className={`r jl ${e.kind === "achat_refuse" ? "hatch faint" : ""} ${e.kind === "alerte" ? "warn" : ""} ${fresh ? "flash-act" : ""}`}>
      <span className="faint">{clock(e.time)}</span>
      <span className="t" data-tip={e.text}>{text}</span>
    </motion.div>
  );
}

function Detail({ t, extra, cur }: { t: Trade; extra: LogEntry[]; cur: string }) {
  const end = t.exitTime ?? null;
  const cause = t.exitCause ? CAUSE_LABEL[t.exitCause] : null;
  const rows: [number | null, string, string, string?][] = [
    [t.entryTime, "Achat", price(t.entryPrice)],
    [t.entryTime, "Stake", money(t.stake, cur)],
    [t.entryTime, "Stop-loss posé", price(t.stopLoss)],
    [t.entryTime, "Take-profit posé", price(t.takeProfit)],
    ...(end !== null ? [[end, `Vente${cause ? `, ${cause[0].toLowerCase()}${cause.slice(1)}` : ""}`, price(t.exitPrice ?? 0)] as [number, string, string]] : []),
    [end, "Fees", signedMoney(-t.fees, cur)],
    [end, "Durée", duration((end ?? t.entryTime) - t.entryTime)],
    [end, end === null ? "En cours" : "Résultat", `${signedMoney(t.pnl, cur)} · ${signedPct(t.pnlPct)}`, end === null ? "act" : t.pnl >= 0 ? "up" : "dn"],
  ];
  return (
    <motion.div className="jg-detail" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2, ease }}>
      {rows.map(([time, label, value, tone], i) => (
        <div key={i} className="r jg-d">
          <span className="faint">{time === null ? "" : clock(time)}</span>
          <span className="t">{label}</span>
          <span className={`right ${tone ?? ""}`}>{value}</span>
        </div>
      ))}
      {extra.map((e) => (
        <div key={e.id} className="r jg-d">
          <span className="faint">{clock(e.time)}</span>
          <span className="t">{e.text}</span>
          <span />
        </div>
      ))}
    </motion.div>
  );
}

function Group({ it, showPair, cur, sel, open, fresh, onToggle, onFocus, onMenu }: {
  it: Extract<JItem, { kind: "trade" }>; showPair: boolean; cur: string; sel: boolean; open: boolean; fresh: boolean;
  onToggle: () => void; onFocus: () => void; onMenu: (x: number, y: number, from: HTMLElement) => void;
}) {
  const t = it.trade;
  const kind = tradeKind(t);
  const end = t.exitTime ?? null;
  const days = end === null ? 0 : dayOffset(t.entryTime, end);
  const zero = Math.round(Math.abs(t.pnl) * 100) === 0;
  const key = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle(); }
  };
  return (
    <motion.div initial={fresh ? { opacity: 0, y: 12 } : false} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.28, ease }} className={`jg ${fresh ? "flash-act" : ""}`}>
      <div className={`jg-h ${sel ? "sel" : ""}`} role="button" tabIndex={0} aria-expanded={open}
        aria-label={`Trade ${showPair ? `${t.pair} ` : ""}de ${clock(t.entryTime)}, ${WORD[kind]} : détails`}
        onClick={onToggle} onDoubleClick={onFocus} onKeyDown={key}
        onContextMenu={(e) => { e.preventDefault(); onMenu(e.clientX, e.clientY, e.currentTarget); }}>
        <span className="jg-chev"><Chevron open={open} dir="side" /></span>
        <span className="num jg-time">
          {clock(t.entryTime)}<span className="faint"> – </span>
          {end === null ? <span className="act">En cours</span> : <>{clock(end)}{days > 0 && <sup className="jg-days" data-tip={`Vendu ${days === 1 ? "le lendemain" : `${days} jours plus tard`}`}>+{days}</sup>}</>}
        </span>
        {showPair && <span className="jg-pair num">{t.pair}</span>}
        <span className="sp" />
        <span className="num dim jg-dur">{end === null ? "" : duration(end - t.entryTime)}</span>
        <span className={`num jg-res ${kind === "cours" || zero ? "" : kind === "gain" ? "up" : "dn"}`}>
          {kind === "cours"
            ? <Delta pct={t.pnlPct} amount={t.pnl} currency={cur} blue still />
            : <>{!zero && <Arrow up={t.pnl > 0} />}{signedMoney(t.pnl, cur)}</>}
          <span className="sr">{WORD[kind]}</span>
        </span>
        <button type="button" className="jg-more" aria-label="Actions sur ce trade" aria-haspopup="menu" tabIndex={-1}
          onClick={(e) => { e.stopPropagation(); const r = e.currentTarget.getBoundingClientRect(); onMenu(r.left, r.bottom + 4, e.currentTarget.parentElement!); }} onDoubleClick={(e) => e.stopPropagation()}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" fill="currentColor"><circle cx="2.5" cy="7" r="1.3" /><circle cx="7" cy="7" r="1.3" /><circle cx="11.5" cy="7" r="1.3" /></svg>
        </button>
      </div>
      <AnimatePresence initial={false}>{open && <Detail t={t} extra={it.extra} cur={cur} />}</AnimatePresence>
    </motion.div>
  );
}

/** Journal groupé par trade. Sur un groupe : clic = déplier, double clic = voir le trade sur le graphique,
 *  clic droit (ou « … ») = menu des actions. Filtres Tous / Gain / Perte / En cours. */
export function Journal({ trades, entries, showPair, currency, live, stale, dash, onFocusTrade }: {
  trades: Trade[]; entries: LogEntry[]; showPair: boolean; currency: string; live: boolean; stale: boolean; dash: Dash; onFocusTrade: (t: Trade) => void;
}) {
  const [filter, setFilter] = useState<JFilter>("tous");
  const [shown, setShown] = useState(PAGE);
  const [pending, setPending] = useState(0);
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());
  const [menu, setMenu] = useState<ContextAt | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const prev = useRef<{ n: number; filter: JFilter }>({ n: -1, filter });
  const anchor = useRef<number | null>(null);
  const known = useRef<{ ids: Set<string>; last: number } | null>(null);

  const g = useMemo(() => groupJournal(trades, entries, filter, shown), [trades, entries, filter, shown]);
  const rows = g.items.filter((i) => i.kind !== "day");
  const fresh = (i: JItem) => i.kind !== "day" && !!known.current && !known.current.ids.has(i.id) && i.time >= known.current.last;
  const freshIds = new Set(rows.filter(fresh).map((i) => i.id));
  useEffect(() => { known.current = { ids: new Set(rows.map((i) => i.id)), last: rows.length ? Math.max(...rows.map((i) => (i as { time: number }).time)) : 0 }; });

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    if (anchor.current !== null) { el.scrollTop += el.scrollHeight - anchor.current; anchor.current = null; prev.current = { n: rows.length, filter }; return; }
    const p = prev.current;
    const first = p.n < 0 || p.filter !== filter;
    const added = rows.length - p.n;
    prev.current = { n: rows.length, filter };
    if (first || (added > 0 && atBottom.current)) { el.scrollTop = el.scrollHeight; setPending(0); }
    else if (added > 0) setPending((n) => n + added);
  }, [rows.length, shown, filter]);

  // La zone change de hauteur avec le défilement de la page : un journal lu en bas reste en bas.
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => { if (atBottom.current) el.scrollTop = el.scrollHeight; });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const onScroll = () => {
    const el = box.current;
    if (!el) return;
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    if (atBottom.current) setPending(0);
    if (el.scrollTop < 40 && shown < g.total && anchor.current === null) { anchor.current = el.scrollHeight; setShown((n) => n + PAGE); }
  };
  const toBottom = () => { const el = box.current; if (el) { el.scrollTop = el.scrollHeight; setPending(0); } };
  const toggle = (id: string) => setOpenIds((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const onListKey = (e: KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const all = Array.from(box.current?.querySelectorAll<HTMLElement>(".jg-h") ?? []);
    const cur = (e.target as HTMLElement).closest<HTMLElement>(".jg-h");
    const i = cur ? all.indexOf(cur) : -1;
    const next = all[i + (e.key === "ArrowDown" ? 1 : -1)];
    if (next) { e.preventDefault(); next.focus(); }
  };
  const openMenu = (t: Trade, isOpen: boolean) => (x: number, y: number, from: HTMLElement) => setMenu({
    x, y, from, label: `Actions sur le trade ${t.pair} de ${clock(t.entryTime)}`,
    items: [
      { label: isOpen ? "Replier les détails" : "Déplier les détails", hint: "Clic", onSelect: () => toggle(t.id) },
      { label: showPair ? `Ouvrir ${t.pair} sur ce trade` : "Centrer le graphique sur ce trade", hint: "Double clic", onSelect: () => onFocusTrade(t) },
      { label: "Copier le résumé", sep: true, onSelect: () => void navigator.clipboard?.writeText(`${t.pair} · ${dateTime(t.entryTime)} → ${t.exitTime === undefined ? "en cours" : dateTime(t.exitTime)} · ${signedMoney(t.pnl, currency)} (${signedPct(t.pnlPct)})`) },
    ],
  });
  const onTabKey = (e: KeyboardEvent) => {
    const i = TABS.findIndex((t) => t.id === filter);
    const j = e.key === "ArrowRight" ? (i + 1) % TABS.length : e.key === "ArrowLeft" ? (i - 1 + TABS.length) % TABS.length : -1;
    if (j < 0) return;
    e.preventDefault();
    setFilter(TABS[j].id);
    (e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')[j])?.focus();
  };

  return (
    <Zone id="journal" name="Journal des transactions" className="in-journal"
      actions={<span className="xs faint num">{g.total} trade{g.total > 1 ? "s" : ""}</span>}>
      <div className="jf-tabs pills" role="tablist" aria-label="Filtrer les trades" onKeyDown={onTabKey}>
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`jf-${t.id}`} aria-selected={filter === t.id} tabIndex={filter === t.id ? 0 : -1} aria-controls="jf-panel" className="pill" onClick={() => setFilter(t.id)}>
            {t.label} <span className="num xs">{g.counts[t.id]}</span>
          </button>
        ))}
      </div>
      <div className={`in-jbox ${stale ? "stale" : ""}`}>
        <div id="jf-panel" role="tabpanel" aria-labelledby={`jf-${filter}`} className="scroll in-jscroll" ref={box} onScroll={onScroll} onKeyDown={onListKey} tabIndex={-1}>
          {rows.length === 0 && <div className="empty" role="status">{filter === "tous" ? "Aucune transaction" : `Aucun trade ${filter === "cours" ? "en cours" : filter === "gain" ? "en gain" : "en perte"} pour le moment.`}</div>}
          {shown < g.total && <div className="xs faint in-jmore">Faire défiler vers le haut pour charger les trades plus anciens</div>}
          {g.items.map((i) => {
            if (i.kind === "day") return <div key={i.id} className="jg-day num" role="presentation">{i.label}</div>;
            if (i.kind === "line") return <Line key={i.id} e={i.entry} showPair={showPair} fresh={freshIds.has(i.id)} />;
            return (
              <Group key={i.id} it={i} showPair={showPair} cur={currency} sel={i.id === dash.sel} open={openIds.has(i.id)} fresh={freshIds.has(i.id)}
                onToggle={() => toggle(i.id)} onFocus={() => onFocusTrade(i.trade)} onMenu={openMenu(i.trade, openIds.has(i.id))} />
            );
          })}
        </div>
        {pending > 0 && <Button small className="in-jnew" onClick={toBottom}>Nouvelles lignes ({pending})</Button>}
      </div>
      <ContextMenu at={menu} onClose={() => setMenu(null)} />
      <footer className="panel-foot in-jfoot">
        <span>Heure de Toronto</span>
        {live && <span className="tag-sim">Démo : temps accéléré, 5 min par 1,5 s</span>}
      </footer>
    </Zone>
  );
}
