import { actions, selectTrades, type State } from "../../data/store";
import type { Instance } from "../../data/types";
import { Button, Dialog } from "../../ui/ui";
import { dateTime } from "../../lib/format";
import { openTradeCount } from "./shared";

export function VersionList({ inst }: { inst: Instance }) {
  return (
    <ol className="in-versions" aria-label="Historique des versions">
      {[...inst.versions].reverse().map((v) => (
        <li key={v.n} className="r tall in-ver">
          <span className="num">Version {v.n}</span>
          <span className="faint num">{dateTime(v.createdAt)}</span>
          <span className="t">{v.summary}</span>
        </li>
      ))}
    </ol>
  );
}

export function VersionsDialog({ inst, open, onClose }: { inst: Instance; open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="Historique des versions" wide>
      <p className="small dim" style={{ margin: 0 }}>Chaque modification de l'instance crée une nouvelle version.</p>
      <VersionList inst={inst} />
    </Dialog>
  );
}

/** Arrêter ou tout vendre : annonce les conséquences d'après l'état constaté, jamais d'après une supposition. */
export function StopDialog({ inst, s, kind, onClose, run }: { inst: Instance; s: State; kind: "stop" | "sell" | null; onClose: () => void; run: (fn: () => unknown) => void }) {
  const n = openTradeCount(selectTrades(s, inst.id));
  const go = (fn: () => void) => { onClose(); run(fn); };
  const count = n === 0 ? "Aucune position ouverte" : `${n} position${n > 1 ? "s" : ""} ouverte${n > 1 ? "s" : ""}`;
  return (
    <Dialog open={kind !== null} onClose={onClose} title={kind === "sell" ? "Tout vendre" : "Arrêter l'instance"}
      foot={
        <>
          <Button onClick={onClose}>Annuler</Button>
          {kind === "sell" && <Button variant="danger" disabled={n === 0} onClick={() => go(() => actions.sellAll(inst.id))}>Tout vendre</Button>}
          {kind === "stop" && n > 0 && <Button onClick={() => go(() => actions.stop(inst.id, { sellAll: false }))}>Arrêter en laissant les positions ouvertes</Button>}
          {kind === "stop" && <Button variant={n > 0 ? "danger" : "go"} onClick={() => go(() => actions.stop(inst.id, { sellAll: n > 0 }))}>{n > 0 ? "Tout vendre puis arrêter" : "Arrêter"}</Button>}
        </>
      }>
      <p style={{ margin: 0 }}><b className="num">{count}</b> d'après le dernier état constaté du bot.</p>
      {kind === "sell" && <p className="small dim" style={{ margin: 0 }}>Toutes les positions sont vendues au prix du marché. Le bot continue de tourner et peut racheter si les achats restent ouverts : mettre les achats en pause d'abord pour l'éviter.</p>}
      {kind === "stop" && n > 0 && <p className="small dim" style={{ margin: 0 }}>Sans vente, les positions restent ouvertes sans bot pour les surveiller : plus aucun stop-loss ni take-profit ne s'applique.</p>}
      <p className="small dim" style={{ margin: 0 }}>La demande n'est « faite » que lorsque l'arrêt est constaté sur le bot.</p>
    </Dialog>
  );
}
