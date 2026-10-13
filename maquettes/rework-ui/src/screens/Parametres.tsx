import { useState } from "react";
import { actions, useStore } from "../data/store";
import { Button, Panel, Term } from "../ui/ui";
import { layout } from "../app/layout";
import { GROUPS, INDICATORS } from "./instance/indicators";
import { PageHead } from "../app/common";
import { ColorDialog } from "../app/ColorDialog";
import { setTheme, useTheme } from "../app/theme";

export function Parametres() {
  const theme = useTheme();
  const colors = useStore((s) => s.colors);
  const on = useStore((s) => s.enabledIndicators);
  const [dlg, setDlg] = useState(false);
  return (
    <div className="page">
      <PageHead title="Paramètres" desc="L'apparence de l'interface, la disposition du tableau de bord et les indicateurs affichés." />
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
      <Panel title="Disposition du tableau de bord">
        <div className="settings-row">
          <p className="note-lg" style={{ maxWidth: "72ch" }}>Dans une instance, chaque zone (Solde, Indicateurs, Composition, Graphique, Journal…) se replie d'un clic sur son en-tête et se déplace en glissant cet en-tête sur une autre zone. Les colonnes se redimensionnent par leurs bords.</p>
          <div><Button onClick={layout.reset}>Réinitialiser la disposition</Button></div>
        </div>
      </Panel>
      <Panel title="Indicateurs affichés" actions={<span className="count">{on.length} actifs</span>}>
        <div className="settings-row" style={{ gap: 24 }}>
          <p className="note-lg" style={{ maxWidth: "72ch" }}>Chaque indicateur s'active un par un. Les plus importants le sont d'office. Le choix vaut pour toutes les instances.</p>
          {GROUPS.map((g) => (
            <section key={g}>
              <h3 className="group-title">{g}</h3>
              <div className="check-grid">
                {INDICATORS.filter((d) => d.group === g).map((d) => (
                  <label key={d.key} className="check-row">
                    <input type="checkbox" checked={on.includes(d.key)} onChange={() => actions.toggleIndicator(d.key)} />
                    <span><b><Term tip={d.tip}>{d.label}</Term></b><small>{d.tip}</small></span>
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
