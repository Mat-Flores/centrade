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

  return (
    <div className="in-bt dash">
      <div className="in-bt-row">
        <Button small variant={allReady ? undefined : "go"} disabled={importing || allReady || !names.length} onClick={() => run(() => actions.importData(inst.id))}>
          {importing ? "Import en cours…" : allReady ? "Données complètes" : "Importer les données"}
        </Button>
        <Button small variant={allReady ? "go" : undefined} disabled={!!why || running} onClick={() => run(() => actions.runBacktest(inst.id))}>
          {finished ? "Relancer la simulation" : "Démarrer la simulation"}
        </Button>
        {why && !running && <span className="xs warn" role="status">{why}</span>}
        {running && (
          <div className="in-bt-prog">
            <Progress value={bt.run.progress} label="Progression de la simulation" />
            <span className="num xs">{Math.round(bt.run.progress)} %</span>
          </div>
        )}
        <span className="sp" />
        <span className="small warn">Un backtest n'est pas une prévision.</span>
      </div>
      {finished && (
        <div className="in-bt-row in-play" role="group" aria-label="Lecture de la période">
          <Button small onClick={() => (isPlaying ? pause() : startPlay(speed))} aria-pressed={isPlaying}>{isPlaying ? "Pause" : "Lecture"}</Button>
          <div className="in-seg" role="group" aria-label="Vitesse de lecture">
            {SPEEDS.map((sp) => (
              <button key={sp} type="button" aria-pressed={speed === sp} onClick={() => { setSpeed(sp); if (isPlaying) startPlay(sp); }}>×{sp}</button>
            ))}
          </div>
          <input type="range" className="in-range" aria-label="Instant affiché" min={bt.from} max={bt.to} step={300} value={at}
            onChange={(e) => { pause(); run(() => actions.setPlayhead(inst.id, Number(e.target.value))); }} />
          <span className="num xs in-play-t">{bt.playhead === null ? "Période complète" : dateTime(at)}</span>
          <Button small disabled={bt.playhead === null} onClick={() => { pause(); run(() => actions.setPlayhead(inst.id, null)); }}>Tout afficher</Button>
        </div>
      )}
    </div>
  );
}
