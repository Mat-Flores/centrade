import { Panel } from "../ui/ui";
import { PageHead } from "../app/common";

const BLOCKS = [
  ["Flux des événements", "Ici figurera le trajet de chaque évènement, de l'exchange à l'écran : réception, déduplication, traitement. Utile pour comprendre pourquoi une valeur est affichée comme périmée."],
  ["Agents", "Ici figureront les agents IA : leurs propositions en attente de validation, ce qu'ils ont lu et l'historique de leurs décisions. Un agent propose, un humain valide."],
];

export function Avance() {
  return (
    <div className="page">
      <PageHead title="Avancé" desc="Les outils de diagnostic et les agents. Hors du chemin quotidien." />
      {BLOCKS.map(([title, text]) => (
        <Panel key={title} title={title}>
          <div className="settings-row">
            <p style={{ margin: 0, maxWidth: "72ch" }}>{text}</p>
            <p className="note-sm" style={{ margin: 0 }}>Hors périmètre de cette maquette : cet écran n'est pas dessiné.</p>
          </div>
        </Panel>
      ))}
    </div>
  );
}
