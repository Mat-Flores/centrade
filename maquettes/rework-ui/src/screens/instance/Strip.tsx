import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { motion, useReducedMotion } from "motion/react";
import { actions, selectStats, selectTrades, type State } from "../../data/store";
import { DEFAULT_INDICATORS } from "../../data/state";
import type { Instance } from "../../data/types";
import { AnimatedNumber, Button, Dialog } from "../../ui/ui";
import { duration, money, signedMoney } from "../../lib/format";
import { ToggleBtn, type Dash } from "./dash";
import { GROUPS, INDICATORS } from "./indicators";
import { Delta, Money } from "./shared";

function Cell({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="in-cell">
      <span className="label">{label}</span>
      <span className="num in-val">{children}</span>
    </div>
  );
}

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
          ["Gains encaissés", <Money key="r" value={st.realized} currency={cur} />],
          ["Gains en cours", <span key="u" className="num act">{signedMoney(st.unrealized, cur)}</span>],
          ["Frais (déjà déduits)", signedMoney(-st.fees, cur)],
        ] as [string, ReactNode][]).map(([k, v]) => (
          <dl key={k} className="spec" style={{ margin: 0 }}><dt>{k}</dt><i /><dd>{v}</dd></dl>
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
  const norm = (x: string) => x.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const needle = norm(q.trim());
  const list = INDICATORS.filter((d) => !needle || norm(`${d.label} ${d.tech ?? ""} ${d.tip}`).includes(needle));
  const sync = (want: (key: string) => boolean) => INDICATORS.forEach((d) => { if (enabled.includes(d.key) !== want(d.key)) actions.toggleIndicator(d.key); });
  const close = () => { setQ(""); onClose(); };
  return (
    <Dialog open={open} onClose={close} title="Indicateurs" wide
      foot={
        <>
          <span className="small dim num" style={{ marginRight: "auto" }} role="status">{enabled.length + 4} indicateurs actifs (4 fixes)</span>
          <Button onClick={() => sync(() => true)}>Tout activer</Button>
          <Button onClick={() => sync((k) => (DEFAULT_INDICATORS as string[]).includes(k))}>Réinitialiser</Button>
          <Button variant="go" onClick={close}>Terminé</Button>
        </>
      }>
      <label className="field"><span>Rechercher un indicateur</span>
        <input className="input" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Taux de réussite, stop, frais…" autoComplete="off" />
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
                <span className="in-itxt"><b>{d.label}</b>{d.tech && <span className="xs faint num"> · {d.tech}</span>}<small>{d.tip}</small></span>
              </label>
            ))}
          </fieldset>
        ) : null;
      })}
    </Dialog>
  );
}

/** Bande d'indicateurs : solde et ses deux variations, puis les indicateurs activés. Repliée : une ligne de 36 px. */
export function Strip({ inst, s, pair, stale, dash }: { inst: Instance; s: State; pair?: string; stale: boolean; dash: Dash }) {
  const st = selectStats(s, inst.id, pair);
  const trades = selectTrades(s, inst.id, pair);
  const cur = inst.currency;
  const [open, setOpen] = useState<"bal" | "ind" | null>(null);
  const reduce = useReducedMotion();
  const closed = dash.collapsed.strip;

  const bt = inst.backtest;
  const view = inst.mode === "backtest" ? (bt?.run.status === "termine" ? (bt.playhead ?? bt.to) - bt.from : 0) : inst.startedAt ? s.cursor - inst.startedAt : 0;
  const enabled = INDICATORS.filter((d) => s.enabledIndicators.includes(d.key));
  const fmt = (n: number) => money(n, cur);

  const balance = (
    <button type="button" className="in-cell in-bal" aria-haspopup="dialog" onClick={() => setOpen("bal")} title="Ouvrir le détail du solde">
      <span className="label">Solde</span>
      <span className="in-balrow">
        <span className={stale ? "stale" : ""} style={{ fontSize: closed ? 14 : 21 }}><AnimatedNumber value={st.balance} format={fmt} /></span>
        <span className={`in-vars ${stale ? "stale" : ""} ${closed ? "is-row" : ""}`}>
          <span><Delta value={st.realizedPct} tone="real" /> <span className="xs dim">encaissé</span></span>
          <span><Delta value={st.unrealizedPct} tone="progress" /> <span className="xs dim">en cours</span></span>
        </span>
      </span>
    </button>
  );

  return (
    <section className={`panel zone in-strip ${closed ? "is-closed" : ""}`} aria-label="Indicateurs">
      {balance}
      <motion.div className={`in-cells ${stale ? "stale" : ""}`} initial={false} animate={{ opacity: closed ? 0 : 1 }} transition={{ duration: reduce ? 0 : 0.18 }} hidden={closed}>
        <Cell label="Durée">{view > 0 ? duration(view) : "—"}</Cell>
        <Cell label="Transactions">{st.trades}</Cell>
        <Cell label="Réussites"><span className="up">{st.wins}</span></Cell>
        <Cell label="Échecs"><span className="dn">{st.losses}</span></Cell>
        {enabled.map((d) => {
          const v = d.show({ st, trades, cur });
          return <Cell key={d.key} label={d.label}><span className={v.tone ?? ""}>{v.text}</span></Cell>;
        })}
      </motion.div>
      <div className="in-strip-end">
        {!closed && (
          <button type="button" className="in-cell in-ind" aria-haspopup="dialog" onClick={() => setOpen("ind")}>
            <span className="label">Indicateurs</span>
            <span className="in-val num">{enabled.length + 4} <span className="xs dim">actifs</span></span>
          </button>
        )}
        <ToggleBtn open={!closed} onClick={() => dash.toggle("strip")} name="Indicateurs" />
      </div>
      {createPortal(
        <>
          <BalanceDialog inst={inst} s={s} pair={pair} open={open === "bal"} onClose={() => setOpen(null)} />
          <IndicatorsDialog enabled={s.enabledIndicators} open={open === "ind"} onClose={() => setOpen(null)} />
        </>,
        document.body,
      )}
    </section>
  );
}
