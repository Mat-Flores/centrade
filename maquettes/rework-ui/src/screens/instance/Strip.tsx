import { useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { actions, selectStats, selectTrades, type State } from "../../data/store";
import { DEFAULT_INDICATORS } from "../../data/state";
import type { Instance } from "../../data/types";
import { SIDE, layout, useLayout, type ZoneId } from "../../app/layout";
import { AnimatedNumber, Button, Delta, Dialog, G, Term, toggleUnit, useUnit } from "../../ui/ui";
import { duration, money, signedMoney } from "../../lib/format";
import { Separator, Zone } from "./dash";
import { GROUPS, INDICATORS, type Ctx, type IndDef } from "./indicators";
import { Money } from "./shared";

const FIXED = 4; // Durée, Trades, Wins, Losses : toujours affichés

/** Fenêtre centrée : détail du solde (départ, gains encaissés, gains en cours, frais, total). */
function BalanceDialog({ inst, s, pair, open, onClose }: { inst: Instance; s: State; pair?: string; open: boolean; onClose: () => void }) {
  const st = selectStats(s, inst.id, pair);
  const cur = inst.currency;
  const start = pair ? inst.startBalance / Math.max(1, inst.pairs.length) : inst.startBalance;
  return (
    <Dialog open={open} onClose={onClose} title="Détail du solde" foot={<Button onClick={onClose}>Fermer</Button>}>
      <div>
        {([
          ["Départ", money(start, cur)],
          [<G key="r" k="realized" />, <Money key="r" value={st.realized} currency={cur} />],
          [<G key="u" k="unrealized" />, <span key="u" className="num act">{signedMoney(st.unrealized, cur)}</span>],
          [<><G k="fees" /> (déjà déduits)</>, signedMoney(-st.fees, cur)],
        ] as [ReactNode, ReactNode][]).map(([k, v], n) => (
          <dl key={n} className="spec" style={{ margin: 0 }}><dt>{k}</dt><i /><dd>{v}</dd></dl>
        ))}
        <dl className="spec" style={{ margin: 0, borderBottom: 0 }}><dt><b>Total</b></dt><i /><dd><b>{money(st.balance, cur)}</b></dd></dl>
      </div>
      <p className="small faint" style={{ margin: 0 }}>Montants dans la devise du compte, jamais convertis.</p>
    </Dialog>
  );
}

/** Fenêtre centrée : choix des indicateurs, avec recherche, description sous chaque libellé, tout activer et réinitialiser. */
function IndicatorsDialog({ enabled, open, onClose }: { enabled: string[]; open: boolean; onClose: () => void }) {
  const [q, setQ] = useState("");
  const norm = (x: string) => x.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const needle = norm(q.trim());
  const list = INDICATORS.filter((d) => !needle || norm(`${d.label} ${d.tip}`).includes(needle));
  const sync = (want: (key: string) => boolean) => INDICATORS.forEach((d) => { if (enabled.includes(d.key) !== want(d.key)) actions.toggleIndicator(d.key); });
  const close = () => { setQ(""); onClose(); };
  return (
    <Dialog open={open} onClose={close} title="Indicateurs" wide
      foot={
        <>
          <span className="small dim num" style={{ marginRight: "auto" }} role="status">{enabled.length + FIXED} indicateurs affichés ({FIXED} fixes)</span>
          <Button onClick={() => sync(() => true)}>Tout activer</Button>
          <Button onClick={() => sync((k) => (DEFAULT_INDICATORS as string[]).includes(k))}>Réinitialiser</Button>
          <Button variant="go" onClick={close}>Terminé</Button>
        </>
      }>
      <label className="field"><span>Rechercher un indicateur</span>
        <input className="input" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Win rate, drawdown, frais…" autoComplete="off" />
      </label>
      {list.length === 0 && <p className="empty" role="status">Aucun indicateur ne correspond à « {q} ».</p>}
      {GROUPS.map((g) => {
        const items = list.filter((d) => d.group === g);
        return items.length ? (
          <fieldset key={g} className="in-igrp">
            <legend className="subtitle">{g}</legend>
            {items.map((d) => (
              <label key={d.key} className="in-irow">
                <input type="checkbox" checked={enabled.includes(d.key)} onChange={() => actions.toggleIndicator(d.key)} />
                <span className="in-itxt"><b>{d.label}</b><small>{d.tip}</small></span>
              </label>
            ))}
          </fieldset>
        ) : null;
      })}
    </Dialog>
  );
}

function Stat({ label, tip, children }: { label: string; tip?: string; children: ReactNode }) {
  return (
    <div className="ind">
      <dt>{tip ? <Term tip={tip}>{label}</Term> : label}</dt>
      <dd className="num">{children}</dd>
    </div>
  );
}

/** Un indicateur. Exprimé en % avec un équivalent en devise : un clic bascule l'unité, pour toute l'interface. */
function Ind({ d, c }: { d: IndDef; c: Ctx }) {
  const unit = useUnit();
  const v = d.show(c);
  const alt = d.alt?.(c);
  return (
    <Stat label={d.label} tip={d.tip}>
      {alt === undefined
        ? <span className={v.tone ?? ""}>{v.text}</span>
        : <button type="button" className={`unit ${v.tone ?? ""}`} data-tip={unit === "pct" ? "Afficher en devise" : "Afficher en %"} data-tip-live onClick={toggleUnit}>{unit === "pct" ? v.text : alt}</button>}
    </Stat>
  );
}

/** Zone « Solde » : le montant (seul élément qui ouvre le détail) et ses deux variations, cliquables pour passer de % à la devise. */
function Balance({ inst, s, pair, stale }: { inst: Instance; s: State; pair?: string; stale: boolean }) {
  const st = selectStats(s, inst.id, pair);
  const cur = inst.currency;
  const [open, setOpen] = useState(false);
  const fmt = (n: number) => money(n, cur);
  const vars = (
    <span className={`bal-vars ${stale ? "stale" : ""}`}>
      <span><Delta pct={st.realizedPct} amount={st.realized} currency={cur} /> <span className="xs dim"><G k="realized">realized</G></span></span>
      <span><Delta pct={st.unrealizedPct} amount={st.unrealized} currency={cur} blue /> <span className="xs dim"><G k="unrealized">unrealized</G></span></span>
    </span>
  );
  return (
    <Zone id="balance" name="Solde" className="zone-top"
      summary={<span className={`num bal-sum ${stale ? "stale" : ""}`}>{fmt(st.balance)} <Delta pct={st.realizedPct} amount={st.realized} currency={cur} /></span>}>
      <div className="bal">
        <button type="button" className={`bal-amount ${stale ? "stale" : ""}`} aria-haspopup="dialog" onClick={() => setOpen(true)} data-tip="Ouvrir le détail du solde">
          <AnimatedNumber value={st.balance} format={fmt} />
        </button>
        {vars}
      </div>
      {createPortal(<BalanceDialog inst={inst} s={s} pair={pair} open={open} onClose={() => setOpen(false)} />, document.body)}
    </Zone>
  );
}

/** Zone « Indicateurs » : un bloc par famille (résumé, performance, risque, activité, causes de vente), chacun avec son titre. */
function Indicators({ inst, s, pair, stale }: { inst: Instance; s: State; pair?: string; stale: boolean }) {
  const st = selectStats(s, inst.id, pair);
  const trades = selectTrades(s, inst.id, pair);
  const [open, setOpen] = useState(false);
  const c: Ctx = { st, trades, cur: inst.currency };
  const bt = inst.backtest;
  const view = inst.mode === "backtest" ? (bt?.run.status === "termine" ? (bt.playhead ?? bt.to) - bt.from : 0) : inst.startedAt ? s.cursor - inst.startedAt : 0;
  const enabled = INDICATORS.filter((d) => s.enabledIndicators.includes(d.key));
  const total = st.wins + st.losses;

  return (
    <Zone id="ind" name="Indicateurs" className="zone-top"
      summary={<span className="xs dim num">{st.trades} trades · {st.wins} wins · {st.losses} losses</span>}
      actions={<button type="button" className="btn ghost xs-btn" aria-haspopup="dialog" onClick={(e) => { e.stopPropagation(); setOpen(true); }}>Choisir <span className="num dim">{enabled.length + FIXED}</span></button>}>
      {/* défile en largeur : la molette verticale y est convertie, faute de hauteur à faire défiler */}
      <div className={`ind-groups ${stale ? "stale" : ""}`} tabIndex={0} aria-label="Indicateurs, défilement horizontal" onWheel={(e) => { if (!e.deltaX) e.currentTarget.scrollLeft += e.deltaY; }}>
        <section className="ind-group" aria-label="Résumé">
          <h3 className="label">Résumé</h3>
          <dl className="ind-items">
            <Stat label="Durée">{view > 0 ? duration(view) : "—"}</Stat>
            <Stat label="Trades" tip="Trades terminés : achetés puis vendus.">{st.trades}</Stat>
            <Stat label="Wins" tip="Trades terminés en gain."><span className="up">{st.wins}</span></Stat>
            <Stat label="Losses" tip="Trades terminés en perte."><span className="dn">{st.losses}</span></Stat>
          </dl>
          <div className="ind-ratio" role="img" aria-label={total ? `${st.wins} wins pour ${st.losses} losses` : "Aucun trade terminé"}>
            {total > 0 && <><i className="w" style={{ flexGrow: st.wins }} /><i className="l" style={{ flexGrow: st.losses }} /></>}
          </div>
        </section>
        {GROUPS.map((g) => {
          const items = enabled.filter((d) => d.group === g);
          return items.length ? (
            <section key={g} className="ind-group" aria-label={g}>
              <h3 className="label">{g}</h3>
              <dl className="ind-items">{items.map((d) => <Ind key={d.key} d={d} c={c} />)}</dl>
            </section>
          ) : null;
        })}
      </div>
      {createPortal(<IndicatorsDialog enabled={s.enabledIndicators} open={open} onClose={() => setOpen(false)} />, document.body)}
    </Zone>
  );
}

/** Rangée du haut : Solde et Indicateurs, deux zones séparées, repliables et échangeables. La première a une largeur réglable,
 *  y compris repliée (une zone repliée en hauteur garde sa largeur) ; la seconde prend le reste. */
export function Strip({ inst, s, pair, stale }: { inst: Instance; s: State; pair?: string; stale: boolean }) {
  const l = useLayout();
  const [first, second] = l.slots;
  const zone = (id: ZoneId) => (id === "balance"
    ? <Balance inst={inst} s={s} pair={pair} stale={stale} />
    : <Indicators inst={inst} s={s} pair={pair} stale={stale} />);
  return (
    <div className="top-row" style={{ "--top-w": `${l.width[first]}px` } as CSSProperties}>
      {zone(first)}
      <Separator orientation="vertical" value={l.width[first]} min={SIDE.min} max={SIDE.max + 240} onChange={(n) => layout.setWidth(first, n)} reset={layout.defaults().width[first]} dir={1} label="Largeur de la zone" />
      {zone(second)}
    </div>
  );
}
