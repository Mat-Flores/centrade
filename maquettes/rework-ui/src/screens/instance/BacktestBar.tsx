import { useState } from "react";
import { actions } from "../../data/store";
import type { Instance } from "../../data/types";
import { Button, Progress } from "../../ui/ui";
import { dateTime } from "../../lib/format";

const SPEEDS = [1, 10, 100] as const;

/** Barre du backtest : import des données, simulation, puis lecture de la période. */
export function BacktestBar({ inst, run }: { inst: Instance; run: (fn: () => unknown) => void }) {
  const bt = inst.backtest!;
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(10);
  const names = inst.pairs.map((p) => p.pair);
  const importing = names.some((p) => bt.data[p]?.status === "import");
  const allReady = names.length > 0 && names.every((p) => bt.data[p]?.status === "completes");
  const running = bt.run.status === "en_cours";
  const finished = bt.run.status === "termine";
  const isPlaying = playing && bt.playhead !== null;
  const why = !names.length ? "Ajouter au moins une paire." : importing ? "Import en cours." : !allReady ? "Importer les données de toutes les paires d'abord." : null;
  const at = bt.playhead ?? bt.to;

  const startPlay = (sp: number) => run(() => { actions.play(inst.id, sp); setPlaying(true); });
  const pause = () => { actions.pausePlayback(inst.id); setPlaying(false); };

  const ready = names.filter((p) => bt.data[p]?.status === "completes").length;

  return (
    <div className="in-bt dash" role="group" aria-label="Actions du backtest">
      <div className="in-bt-step">
        <span className="label">1 · Données</span>
        <span className={`num xs ${allReady ? "up" : "dim"}`}>{ready}/{names.length} paires prêtes</span>
        {!allReady && (
          <Button small variant="go" disabled={importing || !names.length} onClick={() => run(() => actions.importData(inst.id))}>
            {importing ? "Import en cours…" : "Importer les données"}
          </Button>
        )}
      </div>
      <div className="in-bt-step">
        <span className="label">2 · Simulation</span>
        {running ? (
          <div className="in-bt-prog">
            <Progress value={bt.run.progress} label="Progression de la simulation" />
            <span className="num xs">{Math.round(bt.run.progress)} %</span>
          </div>
        ) : (
          <Button small variant={allReady && !finished ? "go" : undefined} disabled={!!why} data-tip={why ?? undefined} onClick={() => run(() => actions.runBacktest(inst.id))}>
            {finished ? "Relancer" : "Démarrer la simulation"}
          </Button>
        )}
      </div>
      {finished && (
        <div className="in-bt-step in-play" role="group" aria-label="Lecture de la période">
          <span className="label">3 · Lecture</span>
          <Button small onClick={() => (isPlaying ? pause() : startPlay(speed))} aria-pressed={isPlaying}>{isPlaying ? "Pause" : "Lecture"}</Button>
          <div className="pills" role="group" aria-label="Vitesse de lecture">
            {SPEEDS.map((sp) => (
              <button key={sp} type="button" className="pill" aria-pressed={speed === sp} onClick={() => { setSpeed(sp); if (isPlaying) startPlay(sp); }}>×{sp}</button>
            ))}
          </div>
          <input type="range" className="in-range" aria-label="Instant affiché" min={bt.from} max={bt.to} step={300} value={at}
            onChange={(e) => { pause(); run(() => actions.setPlayhead(inst.id, Number(e.target.value))); }} />
          <span className="num xs in-play-t">{bt.playhead === null ? "Période complète" : dateTime(at)}</span>
          {bt.playhead !== null && <Button small variant="ghost" onClick={() => { pause(); run(() => actions.setPlayhead(inst.id, null)); }}>Tout afficher</Button>}
        </div>
      )}
    </div>
  );
}
