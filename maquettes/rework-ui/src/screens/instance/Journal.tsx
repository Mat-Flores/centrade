import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CAUSE_LABEL } from "../../data/store";
import type { LogEntry, Trade } from "../../data/types";
import { clock, duration, money, price, signedMoney, signedPct } from "../../lib/format";
import { Button } from "../../ui/ui";
import { Chevron, Zone, type Dash } from "./dash";
import { groupJournal, tradeKind, type JFilter, type JItem } from "./journalGroups";
import { Arrow } from "./shared";

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
      <span className="t" title={e.text}>{text}</span>
    </motion.div>
  );
}

function Detail({ t, extra, cur }: { t: Trade; extra: LogEntry[]; cur: string }) {
  const end = t.exitTime ?? null;
  const cause = t.exitCause ? CAUSE_LABEL[t.exitCause] : null;
  const rows: [number | null, string, string, string?][] = [
    [t.entryTime, "Achat", price(t.entryPrice)],
    [t.entryTime, "Mise", money(t.stake, cur)],
    [t.entryTime, "Stop-loss posé", price(t.stopLoss)],
    [t.entryTime, "Take-profit posé", price(t.takeProfit)],
    ...(end !== null ? [[end, `Vente${cause ? `, ${cause[0].toLowerCase()}${cause.slice(1)}` : ""}`, price(t.exitPrice ?? 0)] as [number, string, string]] : []),
    [end, "Frais", signedMoney(-t.fees, cur)],
    [end, "Durée", duration((end ?? t.entryTime) - t.entryTime)],
    [end, end === null ? "En cours" : "Résultat", `${signedMoney(t.pnl, cur)} · ${signedPct(t.pnlPct)}`, end === null ? "act" : t.pnl >= 0 ? "up" : "dn"],
  ];
  return (
    <motion.div className="jg-detail" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2, ease }}>
      {rows.map(([time, label, value, tone], i) => (
        <div key={i} className="r jg-d">
          <span className="faint">{time === null ? "" : clock(time)}</span>
          <span className="t" title={label}>{label}</span>
          <span className={`right ${tone ?? ""}`}>{value}</span>
        </div>
      ))}
      {extra.map((e) => (
        <div key={e.id} className="r jg-d">
          <span className="faint">{clock(e.time)}</span>
          <span className="t" title={e.text}>{e.text}</span>
          <span />
        </div>
      ))}
    </motion.div>
  );
}

function Group({ it, showPair, cur, now, maxDur, sel, open, fresh, onToggle, onFocus }: {
  it: Extract<JItem, { kind: "trade" }>; showPair: boolean; cur: string; now: number; maxDur: number; sel: boolean; open: boolean; fresh: boolean;
  onToggle: () => void; onFocus: () => void;
}) {
  const t = it.trade;
  const kind = tradeKind(t);
  const dur = (t.exitTime ?? now) - t.entryTime;
  const pct = Math.max(6, Math.min(100, (dur / Math.max(1, maxDur)) * 100));
  const tone = kind === "cours" ? "act" : kind === "gain" ? "up" : "dn";
  const amount = kind === "cours" ? signedPct(t.pnlPct) : signedMoney(t.pnl, cur);
  const zero = Math.round(Math.abs(kind === "cours" ? t.pnlPct : t.pnl) * 100) === 0;
  return (
    <motion.div initial={fresh ? { opacity: 0, y: 12 } : false} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.28, ease }} className={`jg ${fresh ? "flash-act" : ""}`}>
      <div className={`jg-h ${sel ? "sel" : ""}`}>
        <button type="button" className="jg-chev" aria-expanded={open} aria-label={`Détails du trade de ${clock(t.entryTime)}`} title={open ? "Replier" : "Déplier"} data-jh onClick={onToggle}>
          <Chevron open={open} dir="side" />
        </button>
        <button type="button" className="jg-main" data-jh aria-pressed={sel} title="Centrer le graphique sur ce trade" onClick={onFocus}>
          <span className="num faint">{clock(t.entryTime)}</span>
          {showPair && <span className="jg-pair num">{t.pair}</span>}
          <span className="jg-track" aria-hidden="true"><i className={`jg-fill ${tone}`} style={{ width: `${pct}%` }} /></span>
          <span className="num dim jg-dur">{kind === "cours" ? "en cours" : duration(dur)}</span>
          <span className={`num jg-res ${zero ? "" : tone}`}>
            {!zero && <Arrow up={(kind === "cours" ? t.pnlPct : t.pnl) > 0} />}
            {amount}
            <span className="sr">{WORD[kind]}</span>
          </span>
        </button>
      </div>
      <AnimatePresence initial={false}>{open && <Detail t={t} extra={it.extra} cur={cur} />}</AnimatePresence>
    </motion.div>
  );
}

/** Journal groupé par trade : frise avec barre de durée, détail repliable, filtres Tous / Gain / Perte / En cours. */
export function Journal({ trades, entries, showPair, currency, now, live, stale, dash, onFocusTrade }: {
  trades: Trade[]; entries: LogEntry[]; showPair: boolean; currency: string; now: number; live: boolean; stale: boolean; dash: Dash; onFocusTrade: (t: Trade) => void;
}) {
  const [filter, setFilter] = useState<JFilter>("tous");
  const [shown, setShown] = useState(PAGE);
  const [pending, setPending] = useState(0);
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());
  const box = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const prev = useRef<{ n: number; filter: JFilter }>({ n: -1, filter });
  const anchor = useRef<number | null>(null);
  const known = useRef<{ ids: Set<string>; last: number } | null>(null);

  const g = useMemo(() => groupJournal(trades, entries, filter, shown), [trades, entries, filter, shown]);
  const rows = g.items.filter((i) => i.kind !== "day");
  const maxDur = Math.max(1, ...g.items.map((i) => (i.kind === "trade" ? (i.trade.exitTime ?? now) - i.trade.entryTime : 0)));
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
    const all = Array.from(box.current?.querySelectorAll<HTMLElement>(".jg-main") ?? []);
    const cur = (e.target as HTMLElement).closest(".jg-h")?.querySelector<HTMLElement>(".jg-main");
    const i = cur ? all.indexOf(cur) : -1;
    const next = all[i + (e.key === "ArrowDown" ? 1 : -1)];
    if (next) { e.preventDefault(); next.focus(); }
  };
  const onTabKey = (e: KeyboardEvent) => {
    const i = TABS.findIndex((t) => t.id === filter);
    const j = e.key === "ArrowRight" ? (i + 1) % TABS.length : e.key === "ArrowLeft" ? (i - 1 + TABS.length) % TABS.length : -1;
    if (j < 0) return;
    e.preventDefault();
    setFilter(TABS[j].id);
    (e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')[j])?.focus();
  };

  return (
    <Zone id="journal" name="Journal des transactions" side dash={dash} className="in-journal" label="Journal des transactions"
      actions={<span className="xs faint num">{g.total} trade{g.total > 1 ? "s" : ""}</span>}>
      <div className="jf-tabs" role="tablist" aria-label="Filtrer les trades" onKeyDown={onTabKey}>
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`jf-${t.id}`} aria-selected={filter === t.id} tabIndex={filter === t.id ? 0 : -1} aria-controls="jf-panel" className="jf-tab" onClick={() => setFilter(t.id)}>
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
              <Group key={i.id} it={i} showPair={showPair} cur={currency} now={now} maxDur={maxDur} sel={i.id === dash.sel} open={openIds.has(i.id)} fresh={freshIds.has(i.id)}
                onToggle={() => toggle(i.id)} onFocus={() => onFocusTrade(i.trade)} />
            );
          })}
        </div>
        {pending > 0 && <Button small className="in-jnew" onClick={toBottom}>Nouvelles lignes ({pending})</Button>}
      </div>
      <footer className="panel-foot in-jfoot">
        <span>Heure de Toronto</span>
        {live && <span className="tag-sim">Démo : temps accéléré, 5 min par 1,5 s</span>}
      </footer>
    </Zone>
  );
}
