import { go, href } from "../../app/route";
import { selectLog, selectStats, selectTrades, type State } from "../../data/store";
import type { Instance } from "../../data/types";
import { G, SimTag } from "../../ui/ui";
import { signedMoney } from "../../lib/format";
import { Composition } from "./Composition";
import { ObsGrid, Zone, type Dash } from "./dash";
import { EquityChart } from "./EquityChart";
import { Journal } from "./Journal";
import { Strip } from "./Strip";
import { isLive, isStale } from "./shared";

const COLS = "minmax(76px,1fr) minmax(0,1.2fr) 66px 52px 70px 118px 118px";

function Heat({ value, max, tone }: { value: number; max: number; tone: "real" | "progress" }) {
  const w = `${Math.min(100, (Math.abs(value) / max) * 100)}%`;
  return <i className={`heat ${tone === "progress" ? "act" : value < 0 ? "loss" : ""}`} style={{ width: w, left: "auto", right: 0 }} />;
}

export function AllView({ inst, s, dash }: { inst: Instance; s: State; dash: Dash }) {
  const stale = isStale(inst, s.cursor);
  const st = selectStats(s, inst.id);
  const rows = inst.pairs.map((p) => ({ p, st: selectStats(s, inst.id, p.pair), name: s.strategies.find((x) => x.id === p.strategyId)?.name ?? "—" }));
  const max = Math.max(1, ...rows.flatMap((r) => [Math.abs(r.st.realized), Math.abs(r.st.unrealized)]));
  const cur = inst.currency;

  return (
    <div className="dash obs">
      <Strip inst={inst} s={s} stale={stale} />
      <ObsGrid zones={{
        comp: <Composition inst={inst} s={s} />,
        chart: (
          <Zone id="chart" name="Évolution du capital" className="in-eq" actions={inst.mode !== "reel" ? <SimTag /> : undefined}>
            <EquityChart data={st.equity} start={inst.startBalance} currency={cur} stale={stale} />
          </Zone>
        ),
        pairs: (
          <Zone id="pairs" name="Résultats par paire" className="in-pairs"
            actions={<span className="xs faint num">{rows.length} paire{rows.length > 1 ? "s" : ""}</span>}>
            <div className="cols" role="row" style={{ gridTemplateColumns: COLS }}>
              <span role="columnheader">Paire</span><span role="columnheader">Stratégie</span>
              <span role="columnheader" className="right">Trades</span><span role="columnheader" className="right"><G k="wins" /></span><span role="columnheader" className="right"><G k="losses" /></span>
              <span role="columnheader" className="right"><G k="realized">Realized</G></span>
              <span role="columnheader" className="right"><G k="unrealized">Unrealized</G></span>
            </div>
            <div role="table" aria-label="Paires de l'instance" className={`scroll in-pairs-body ${stale ? "stale" : ""}`}>
              {rows.length === 0 && <div className="empty">Aucune paire : en ajouter dans les réglages.</div>}
              {rows.map(({ p, st: r, name }) => (
                <a key={p.pair} role="row" className="r in-link" style={{ gridTemplateColumns: COLS }} href={href({ page: "instance", id: inst.id, tab: p.pair })}>
                  <span role="cell">{p.pair}</span>
                  <span role="cell" className="t">{name}</span>
                  <span role="cell" className="right">{r.trades}</span>
                  <span role="cell" className="right up">{r.wins}</span>
                  <span role="cell" className="right dn">{r.losses}</span>
                  <span role="cell" className={`right ${r.realized > 0 ? "up" : r.realized < 0 ? "dn" : ""}`}><Heat value={r.realized} max={max} tone="real" /><b className="in-above">{signedMoney(r.realized, cur)}</b></span>
                  <span role="cell" className="right act"><Heat value={r.unrealized} max={max} tone="progress" /><b className="in-above">{signedMoney(r.unrealized, cur)}</b></span>
                </a>
              ))}
            </div>
          </Zone>
        ),
        journal: <Journal key="all" trades={selectTrades(s, inst.id)} entries={selectLog(s, inst.id)} showPair currency={cur} live={isLive(inst)} stale={stale} dash={dash}
          onFocusTrade={(t) => { dash.requestFocus(t.id, t.pair); go({ page: "instance", id: inst.id, tab: t.pair }); }} />,
      }} />
    </div>
  );
}
