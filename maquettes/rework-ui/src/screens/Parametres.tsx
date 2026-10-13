import { useState } from "react";
import { actions, useStore } from "../data/store";
import { Button, Panel, Term } from "../ui/ui";
import { PageHead } from "../app/common";
import { ColorDialog } from "../app/ColorDialog";
import { setTheme, useTheme } from "../app/theme";

const GROUPS: { title: string; items: [key: string, label: string, tip?: string][] }[] = [
  { title: "Performance", items: [
    ["winRate", "Taux de réussite", "Part des trades terminés en gain."], ["avgWin", "Gain moyen"], ["avgLoss", "Perte moyenne"],
    ["profitFactor", "Rapport gains/pertes", "Somme des gains divisée par la somme des pertes."], ["best", "Meilleur trade"], ["worst", "Pire trade"],
    ["expectancy", "Gain moyen par trade", "Résultat moyen d'un trade, gains et pertes confondus."], ["sharpe", "Ratio de Sharpe"], ["sortino", "Ratio de Sortino"], ["calmar", "Ratio de Calmar"],
  ] },
  { title: "Risque", items: [
    ["maxDrawdownPct", "Plus forte baisse", "Plus grand recul du solde depuis un sommet."], ["currentDrawdownPct", "Baisse en cours"],
    ["exposurePct", "Capital engagé", "Part du solde placée dans des positions ouvertes."],
  ] },
  { title: "Activité", items: [
    ["openPositions", "Positions ouvertes"], ["avgDurationSec", "Durée moyenne d'un trade"], ["fees", "Frais payés"],
    ["refusedEntries", "Achats refusés par les protections", "Une protection a refusé l'achat."],
  ] },
  { title: "Causes de vente", items: [["exitCauses", "Répartition des causes de vente"]] },
];

export function Parametres() {
  const theme = useTheme();
  const colors = useStore((s) => s.colors);
  const on = useStore((s) => s.enabledIndicators);
  const [dlg, setDlg] = useState(false);
  return (
    <div className="page">
      <PageHead title="Paramètres" desc="L'apparence de l'interface et les indicateurs affichés par défaut." />
      <Panel title="Apparence">
        <div className="settings-row">
          <fieldset className="opt-group" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <legend>Thème</legend>
            <label className="opt"><input type="radio" name="theme" checked={theme === "dark"} onChange={() => setTheme("dark")} /><b>Sombre</b><span>Fond sombre, pour les longues séances et le soir.</span></label>
            <label className="opt"><input type="radio" name="theme" checked={theme === "light"} onChange={() => setTheme("light")} /><b>Clair</b><span>Fond clair, pour une pièce éclairée ou une tablette.</span></label>
          </fieldset>
          <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
            <Button onClick={() => setDlg(true)}>Personnaliser les couleurs</Button>
            <span className="note-sm">{colors ? "Couleurs personnalisées." : "Couleurs du thème."} Non enregistré : la maquette ne conserve rien.</span>
          </div>
        </div>
      </Panel>
      <Panel title="Indicateurs affichés par défaut" actions={<span className="count">{on.length} actifs</span>}>
        <div className="settings-row" style={{ gap: 24 }}>
          <p className="note-lg" style={{ maxWidth: "72ch" }}>Chaque indicateur s'active un par un. Les plus importants le sont d'office. Le choix vaut pour toutes les instances.</p>
          {GROUPS.map((g) => (
            <section key={g.title}>
              <h3 className="group-title">{g.title}</h3>
              <div className="check-grid">
                {g.items.map(([key, label, tip]) => (
                  <label key={key} className="check-row">
                    <input type="checkbox" checked={on.includes(key)} onChange={() => actions.toggleIndicator(key)} />
                    <span><b>{tip ? <Term tip={tip}>{label}</Term> : label}</b><small>{tip ?? "Affiché dans le tableau de bord de chaque instance."}</small></span>
                  </label>
                ))}
              </div>
            </section>
          ))}
        </div>
      </Panel>
      <ColorDialog open={dlg} onClose={() => setDlg(false)} />
    </div>
  );
}
