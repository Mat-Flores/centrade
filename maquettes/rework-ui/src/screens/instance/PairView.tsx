import { useState } from "react";
import { actions, selectCandles, selectLog, selectTrades, type State } from "../../data/store";
import type { Instance, Timeframe } from "../../data/types";
import { TradingChart } from "../../chart/TradingChart";
import { Button, Progress } from "../../ui/ui";
import { tfLabel } from "../../lib/format";
import { Composition } from "./Composition";
import { ObsGrid, Zone, type Dash } from "./dash";
import { Journal } from "./Journal";
import { Strip } from "./Strip";
import { isLive, isStale, startBlock } from "./shared";

function NeverStarted({ inst, s, run }: { inst: Instance; s: State; run: (fn: () => unknown) => void }) {
  const why = startBlock(inst, s.killSwitch);
  return (
    <div className="empty in-empty">
      <b className="subtitle">Instance jamais démarrée</b>
      <span>Aucune transaction pour le moment. Les graphiques et les indicateurs apparaissent après le démarrage.</span>
      <Button variant="go" disabled={!!why} onClick={() => run(() => actions.start(inst.id))}>Démarrer</Button>
      {why && <span className="small warn">{why}</span>}
    </div>
  );
}

function BacktestEmpty({ inst, pair, tf, run }: { inst: Instance; pair: string; tf: Timeframe; run: (fn: () => unknown) => void }) {
  const d = inst.backtest?.data[pair] ?? { status: "absentes" as const, progress: 0 };
  const ready = Object.values(inst.backtest?.data ?? {}).length === inst.pairs.length && inst.pairs.every((p) => inst.backtest?.data[p.pair]?.status === "completes");
  return (
    <div className="empty in-empty">
      <b className="subtitle">Pas encore de résultat</b>
      <ol className="in-steps2">
        <li className={d.status === "completes" ? "done" : ""}><b>1. Importer les données.</b> {d.status === "completes" ? `${pair} en ${tfLabel(tf)} : données complètes.` : d.status === "import" ? "Import en cours…" : `${pair} : données ${d.status === "partielles" ? "partielles" : "absentes"}.`}</li>
        <li><b>2. Démarrer la simulation.</b> {ready ? "Toutes les données sont prêtes : utiliser « Démarrer la simulation » dans la barre ci-dessus." : "Disponible quand les données de toutes les paires sont complètes."}</li>
      </ol>
      {d.status === "import" && <div style={{ width: 240 }}><Progress value={d.progress} label={`Import de ${pair}`} /></div>}
      {d.status !== "completes" && d.status !== "import" && (
        <Button variant="go" onClick={() => run(() => actions.importData(inst.id, pair))}>Importer les données de {pair}</Button>
      )}
    </div>
  );
}

export function PairView({ inst, s, pair, run, dash }: { inst: Instance; s: State; pair: string; run: (fn: () => unknown) => void; dash: Dash }) {
  const pc = inst.pairs.find((p) => p.pair === pair)!;
  const strat = s.strategies.find((x) => x.id === pc.strategyId)!;
  const [tf, setTf] = useState<Timeframe>(strat.timeframe);
  const stale = isStale(inst, s.cursor);
  const trades = selectTrades(s, inst.id, pair);
  const neverStarted = isLive(inst) && inst.startedAt === null;
  const noRun = inst.mode === "backtest" && inst.backtest?.run.status !== "termine";
  const traded: Timeframe[] = [strat.timeframe, ...strat.extraTimeframes];
  const mine = dash.focus?.pair === pair ? dash.focus : null;

  return (
    <div className="dash obs">
      <Strip inst={inst} s={s} pair={pair} stale={stale} dash={dash} />
      <ObsGrid dash={dash}
        left={<Composition inst={inst} s={s} activePair={pair} dash={dash} />}
        center={
          <div className="in-center">
            <Zone id="chart" name={`Graphique ${pair}`} dash={dash} className="fill-chart">
              {neverStarted ? <NeverStarted inst={inst} s={s} run={run} /> : noRun ? <BacktestEmpty inst={inst} pair={pair} tf={strat.timeframe} run={run} /> : (
                <TradingChart candles={selectCandles(s, inst.id, pair, tf)} trades={trades} timeframe={tf} tradedTimeframes={traded} onTimeframe={setTf}
                  currency={inst.currency} simulated={inst.mode !== "reel"} observedAgeSec={isLive(inst) ? s.cursor - inst.observedAt : 0} stale={stale}
                  selectedTradeId={dash.sel} onSelectTrade={dash.setSel} focusTradeId={mine?.id ?? null} focusNonce={mine?.nonce ?? 0} onFocused={dash.clearFocus}
                  emptyMessage="Aucune bougie à afficher pour cette période." />
              )}
            </Zone>
          </div>
        }
        right={<Journal key={pair} trades={trades} entries={selectLog(s, inst.id, pair)} showPair={false} currency={inst.currency} now={s.cursor} live={isLive(inst)} stale={stale} dash={dash}
          onFocusTrade={(t) => dash.requestFocus(t.id, t.pair)} />}
      />
    </div>
  );
}
