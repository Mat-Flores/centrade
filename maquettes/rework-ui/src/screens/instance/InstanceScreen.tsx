// Écran d'une instance : barre, séquence de démarrage, onglets, puis la face Observation ou Réglages.
import { useEffect, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { href } from "../../app/route";
import { selectTrades, useStore, type State } from "../../data/store";
import type { Instance } from "../../data/types";
import { AllView } from "./AllView";
import { BacktestBar } from "./BacktestBar";
import { VersionsDialog, StopDialog } from "./Dialogs";
import { useDash } from "./dash";
import { InstanceBar } from "./InstanceBar";
import { PairView } from "./PairView";
import { PromoteDialog } from "./Promote";
import { Settings } from "./Settings";
import { StartStepper } from "./StartStepper";
import { Tabs } from "./Tabs";
import { ErrorStrip, isStale, openTradeCount, useRun, type Face } from "./shared";
import "./instance.css";

function Missing({ id }: { id: string }) {
  return (
    <div className="empty" role="status" style={{ minHeight: 320 }}>
      <b className="subtitle">Instance introuvable</b>
      <span>Aucune instance ne porte l'identifiant « {id} ». Elle a peut-être été supprimée.</span>
      <a className="btn" href={href({ page: "instances" })}>Retour aux instances</a>
    </div>
  );
}

function Loaded({ inst, s, tab }: { inst: Instance; s: State; tab: string }) {
  const [err, run, clear] = useRun();
  const [choice, setChoice] = useState<Face | null>(null);
  const [dialog, setDialog] = useState<"stop" | "sell" | "versions" | "promote" | null>(null);
  const [seen, setSeen] = useState<string | null>(null);
  const dash = useDash();
  const stale = isStale(inst, s.cursor);
  const hasOpen = openTradeCount(selectTrades(s, inst.id)) > 0;
  const auto: Face = inst.mode === "backtest" ? "observation" : inst.observed === "arrete" && !hasOpen ? "reglages" : "observation";
  const face = choice ?? auto;
  const cmd = inst.command;
  // Un démarrage déjà réussi depuis longtemps n'a plus rien à montrer ; un échec reste jusqu'à « Vu ».
  const showSteps = cmd?.kind === "demarrer" && !!cmd.steps && seen !== cmd.id && (cmd.status !== "constatee" || s.cursor - cmd.requestedAt < 600);
  const activeTab = tab !== "tout" && inst.pairs.some((p) => p.pair === tab) ? tab : "tout";

  // Une demande de démarrage ou d'arrêt rend la main à la face automatique.
  useEffect(() => setChoice(null), [inst.observed]);
  // Un démarrage réussi s'efface seul ; un échec reste affiché jusqu'à « Vu ».
  useEffect(() => {
    if (cmd?.kind !== "demarrer" || cmd.status !== "constatee") return;
    const t = setTimeout(() => setSeen(cmd.id), 3500);
    return () => clearTimeout(t);
  }, [cmd?.id, cmd?.status]);

  return (
    <div className="in">
      <InstanceBar inst={inst} s={s} stale={stale} face={face} setFace={setChoice} run={run} onVersions={() => setDialog("versions")} onPromote={() => setDialog("promote")} onDialog={setDialog} />
      <ErrorStrip message={err} onClose={clear} />
      {inst.mode === "backtest" && <BacktestBar inst={inst} run={run} />}
      {showSteps && <StartStepper key={cmd!.id} cmd={cmd!} onSeen={() => setSeen(cmd!.id)} />}
      {face === "observation" && <Tabs inst={inst} s={s} tab={activeTab} />}
      <div className="in-body">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={face} className="in-face" initial={{ opacity: 0, x: face === "reglages" ? 24 : -24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: face === "reglages" ? -24 : 24 }} transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}>
            {face === "reglages"
              ? <Settings inst={inst} s={s} />
              : activeTab === "tout" ? <AllView inst={inst} s={s} dash={dash} /> : <PairView key={activeTab} inst={inst} s={s} pair={activeTab} run={run} dash={dash} />}
          </motion.div>
        </AnimatePresence>
      </div>
      <VersionsDialog inst={inst} open={dialog === "versions"} onClose={() => setDialog(null)} />
      <StopDialog inst={inst} s={s} kind={dialog === "stop" || dialog === "sell" ? dialog : null} onClose={() => setDialog(null)} run={run} />
      <PromoteDialog inst={inst} s={s} open={dialog === "promote"} onClose={() => setDialog(null)} />
    </div>
  );
}

export function InstanceScreen({ id, tab }: { id: string; tab: string }) {
  const s = useStore((x) => x);
  const inst = s.instances.find((i) => i.id === id);
  return <MotionConfig reducedMotion="user">{inst ? <Loaded key={id} inst={inst} s={s} tab={tab} /> : <Missing id={id} />}</MotionConfig>;
}
