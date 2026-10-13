import { useEffect, useState } from "react";
import type { ColorRoles } from "../data/types";
import { actions, useStore } from "../data/store";
import { Button, Dialog, ModeTag } from "../ui/ui";
import { PRESETS, ROLE_KEYS, ROLE_LABEL, applyColors, checkColors, readRoles, readSurface } from "../theme/colors";
import { Delta } from "./common";

/** Couleurs affichées en ce moment, relues dès que applyColors ou le thème préviennent. */
function useShownColors() {
  const [shown, setShown] = useState(() => ({ roles: readRoles(), surface: readSurface() }));
  useEffect(() => {
    const read = () => setShown({ roles: readRoles(), surface: readSurface() });
    window.addEventListener("centrade:colors", read);
    read();
    return () => window.removeEventListener("centrade:colors", read);
  }, []);
  return shown;
}

export function ColorDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const custom = useStore((s) => s.colors);
  const { roles, surface } = useShownColors();
  const warnings = custom ? checkColors(roles, surface) : [];
  const active = PRESETS.find((p) => p.roles === custom)?.id;

  const edit = (k: keyof ColorRoles, hex: string) => {
    const next = { ...roles, [k]: hex };
    // une couleur de bougie suit son rôle tant qu'elle n'a pas été réglée à part
    if (k === "gain" && roles.bougieHausse === roles.gain) next.bougieHausse = hex;
    if (k === "perte" && roles.bougieBaisse === roles.perte) next.bougieBaisse = hex;
    actions.setColors(next);
  };

  return (
    <Dialog
      open={open} onClose={onClose} title="Couleurs" wide
      foot={
        <>
          <span className="note-sm" style={{ marginRight: "auto" }}>Non enregistré : la maquette ne conserve rien.</span>
          <Button onClick={() => actions.setColors(null)} disabled={!custom}>Réinitialiser</Button>
          <Button variant="go" onClick={onClose}>Terminer</Button>
        </>
      }
    >
      <div className="fieldset" role="group" aria-label="Jeux de couleurs">
        <span className="sec-label">Jeux de couleurs</span>
        <div className="presets">
          {PRESETS.map((p) => (
            <Button key={p.id} small aria-pressed={active === p.id} onClick={() => actions.setColors(p.roles)}>{p.label}</Button>
          ))}
          {!active && <span className="tag-sim" style={{ alignSelf: "center" }}>Réglage libre</span>}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="fieldset" role="group" aria-label="Réglage par rôle">
          <span className="sec-label">Un réglage par rôle</span>
          <div className="role-grid">
            {ROLE_KEYS.map((k) => (
              <label key={k} className="role">
                <span>{ROLE_LABEL[k]}</span>
                <code>{roles[k]}</code>
                <input type="color" value={roles[k]} onChange={(e) => edit(k, e.target.value)} aria-label={`Couleur : ${ROLE_LABEL[k]}`} />
              </label>
            ))}
          </div>
        </div>

        <div className="fieldset">
          <span className="sec-label">Aperçu</span>
          <div className="preview" aria-hidden="true">
            <div className="r"><span className="up">+41,06 USDT</span><span className="dn">−12,40 USDT</span><span className="act">Achat 62 880,00</span></div>
            <div className="r"><span><Delta pct={2.05} /></span><span><Delta pct={-0.62} /></span><span className="act">En cours</span></div>
            <div className="tagrow">
              <ModeTag mode="reel" /><ModeTag mode="test" /><ModeTag mode="backtest" />
              <span className="mini-candles"><i className="u" /><i className="d" /></span>
            </div>
          </div>
          <span className="sec-label" style={{ marginTop: 10 }}>Avertissements</span>
          <ul className="warns" aria-live="polite">
            {!custom && <li className="ok">Couleurs du thème : vérifiées à la conception.</li>}
            {custom && warnings.length === 0 && <li className="ok">Aucun avertissement : contrastes et écarts suffisants.</li>}
            {warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        </div>
      </div>
    </Dialog>
  );
}
