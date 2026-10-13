import { href } from "../../app/route";
import { actions, type State } from "../../data/store";
import type { Instance } from "../../data/types";
import { Button, ModeTag, SimTag } from "../../ui/ui";
import { providerName } from "../../data/providers";
import { SEEN_TIP, age, duration, seen } from "../../lib/format";
import { STATE_LABEL, WANTED_LABEL, startBlock, type Face } from "./shared";

const CMD_LABEL = { demarrer: "Démarrer", pause_achats: "Mettre en pause les achats", reprendre_achats: "Reprendre les achats", arreter: "Arrêter", tout_vendre: "Tout vendre" } as const;

function StateBlock({ inst, cursor, stale }: { inst: Instance; cursor: number; stale: boolean }) {
  if (inst.mode === "backtest") {
    const r = inst.backtest?.run;
    return (
      <div className="in-state" aria-live="polite">
        <b>Backtest</b>
        <span className="xs dim">{r?.status === "en_cours" ? `Calcul en cours, ${Math.round(r.progress)} %` : r?.status === "termine" ? "Résultat calculé" : "Aucun résultat"} · <span className="warn">un backtest n'est pas une prévision</span></span>
      </div>
    );
  }
  const pending = inst.command?.status === "en_cours" ? inst.command : null;
  const differs = inst.wanted !== inst.observed;
  return (
    <div className="in-state" aria-live="polite">
      <b className={stale ? "stale" : ""}>
        {differs ? <>Demandé : {WANTED_LABEL[inst.wanted]} <span className="faint">·</span> État réel : {STATE_LABEL[inst.observed]}</> : STATE_LABEL[inst.observed]}
      </b>
      <span className="xs dim">
        {stale
          ? <span className="tag-sim" data-tip={SEEN_TIP}>Périmé : aucune réponse du bot depuis {age(cursor - inst.observedAt).replace("il y a ", "")}</span>
          : <span data-tip={SEEN_TIP}>{seen(cursor - inst.observedAt)}</span>}
        {pending && <> · commande « {CMD_LABEL[pending.kind]} » en cours, demandée {age(cursor - pending.requestedAt)}</>}
        {!pending && inst.startedAt !== null && inst.observed !== "arrete" && <> · depuis {duration(cursor - inst.startedAt)}</>}
      </span>
    </div>
  );
}

export function InstanceBar({ inst, s, stale, face, setFace, run, onVersions, onPromote, onDialog }: {
  inst: Instance; s: State; stale: boolean; face: Face; setFace: (f: Face) => void; run: (fn: () => unknown) => void;
  onVersions: () => void; onPromote: () => void; onDialog: (k: "stop" | "sell") => void;
}) {
  const pend = inst.command?.status === "en_cours" ? inst.command.kind : null;
  const running = inst.mode !== "backtest" && inst.observed !== "arrete";
  const why = startBlock(inst, s.killSwitch);
  const paused = inst.observed === "achats_en_pause";
  const resumeWhy = s.killSwitch ? "Arrêt d'urgence actif" : stale ? "État périmé" : null;
  const pb = (kind: keyof typeof CMD_LABEL, text: string) => (pend === kind ? { "aria-busy": true, className: "pending" } : {});

  return (
    <div className="in-bar">
      <a className="in-crumb" href={href({ page: "instances" })}>Instances</a>
      <span className="faint" aria-hidden="true">/</span>
      <h1 className="title in-name">{inst.name}</h1>
      <ModeTag mode={inst.mode} />
      {inst.mode !== "reel" && <SimTag />}
      <span className="tag tag-provider" data-tip={`Provider de l'instance : ${providerName(inst.provider)}. Seules ses stratégies sont utilisables.`}>{providerName(inst.provider)}</span>
      <StateBlock inst={inst} cursor={s.cursor} stale={stale} />
      <button type="button" className="btn ghost sm" onClick={onVersions} data-tip="Ouvrir l'historique des versions">Version {inst.versions[inst.versions.length - 1].n}</button>
      <span className="sp" />
      <div className="in-seg" role="group" aria-label="Face de l'instance">
        {(["observation", "reglages"] as const).map((f) => (
          <button key={f} type="button" aria-pressed={face === f} onClick={() => setFace(f)}>{f === "observation" ? "Observation" : "Réglages"}</button>
        ))}
      </div>
      {inst.mode !== "backtest" && (
        <div className="in-cmds">
          {!running && (
            <>
              {why && <span className="xs warn in-why" role="status">{why}</span>}
              <Button variant="go" small disabled={!!why} {...pb("demarrer", "")} onClick={() => run(() => actions.start(inst.id))}>{pend === "demarrer" ? "Démarrage demandé…" : "Démarrer"}</Button>
              {inst.mode === "test" && inst.startedAt !== null && <Button small onClick={onPromote}>Passer en réel</Button>}
            </>
          )}
          {running && (
            <>
              {paused
                ? <Button small disabled={!!resumeWhy || pend === "reprendre_achats"} title={resumeWhy ?? undefined} {...pb("reprendre_achats", "")} onClick={() => run(() => actions.resumeEntries(inst.id))}>{pend === "reprendre_achats" ? "Reprise demandée…" : "Reprendre les achats"}</Button>
                : <Button small {...pb("pause_achats", "")} onClick={() => run(() => actions.pauseEntries(inst.id))}>{pend === "pause_achats" ? "Pause demandée…" : "Mettre en pause les achats"}</Button>}
              {paused && resumeWhy && <span className="xs warn">{resumeWhy}</span>}
              <Button small variant="danger" {...pb("tout_vendre", "")} onClick={() => onDialog("sell")}>{pend === "tout_vendre" ? "Vente demandée…" : "Tout vendre"}</Button>
              <Button small variant="danger" {...pb("arreter", "")} onClick={() => onDialog("stop")}>{pend === "arreter" ? "Arrêt demandé…" : "Arrêter"}</Button>
              {inst.mode === "test" && inst.startedAt !== null && <Button small onClick={onPromote}>Passer en réel</Button>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
