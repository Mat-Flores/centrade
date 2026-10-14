import { useEffect, useState } from "react";

import { fr } from "@/i18n/fr";
import { Button, Dialog, ModeTag } from "@/ui/ui";

import { Delta } from "./common";
import { PRESETS, ROLE_KEYS, checkColors, readRoles, readSurface, sameRoles, type ColorRoles } from "./theme/colors";
import { setColors, useColors } from "./theme/theme";

/** Colors shown right now, read again as soon as applyColors or the theme tells. */
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
  const custom = useColors();
  const { roles, surface } = useShownColors();
  const warnings = custom ? checkColors(roles, surface) : [];
  const active = PRESETS.find((p) => sameRoles(p.roles, custom))?.id;

  const edit = (k: keyof ColorRoles, hex: string) => {
    const next = { ...roles, [k]: hex };
    // a candle color follows its role until it has been set apart
    if (k === "gain" && roles.candleUp === roles.gain) next.candleUp = hex;
    if (k === "loss" && roles.candleDown === roles.loss) next.candleDown = hex;
    setColors(next);
  };

  return (
    <Dialog
      open={open} onClose={onClose} title={fr.colors.title} wide
      foot={
        <>
          <span className="note-sm" style={{ marginRight: "auto" }}>{fr.colors.storedLocally}</span>
          <Button onClick={() => setColors(null)} disabled={!custom}>{fr.colors.reset}</Button>
          <Button variant="go" onClick={onClose}>{fr.colors.done}</Button>
        </>
      }
    >
      <div className="fieldset" role="group" aria-label={fr.colors.presetsLabel}>
        <span className="sec-label">{fr.colors.presetsLabel}</span>
        <div className="presets">
          {PRESETS.map((p) => (
            <Button key={p.id} small aria-pressed={active === p.id} onClick={() => setColors(p.roles)}>{p.label}</Button>
          ))}
          {!active && <span className="tag-sim" style={{ alignSelf: "center" }}>{fr.colors.free}</span>}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="fieldset" role="group" aria-label={fr.colors.perRoleGroup}>
          <span className="sec-label">{fr.colors.perRole}</span>
          <div className="role-grid">
            {ROLE_KEYS.map((k) => (
              <label key={k} className="role">
                <span>{fr.colors.roles[k]}</span>
                <code>{roles[k]}</code>
                <input type="color" value={roles[k]} onChange={(e) => edit(k, e.target.value)} aria-label={fr.colors.colorOf(fr.colors.roles[k])} />
              </label>
            ))}
          </div>
        </div>

        <div className="fieldset">
          <span className="sec-label">{fr.colors.preview}</span>
          {/* Sample values only, to show the colors: they are data of nothing. */}
          <div className="preview" aria-hidden="true">
            <div className="r"><span className="up">{fr.colors.previewGain}</span><span className="dn">{fr.colors.previewLoss}</span><span className="act">{fr.colors.previewBuy}</span></div>
            <div className="r"><span><Delta pct="2.05" /></span><span><Delta pct="-0.62" /></span><span className="act">{fr.colors.previewInProgress}</span></div>
            <div className="tagrow">
              <ModeTag mode="live" /><ModeTag mode="test" /><ModeTag mode="backtest" />
              <span className="mini-candles"><i className="u" /><i className="d" /></span>
            </div>
          </div>
          <span className="sec-label" style={{ marginTop: 10 }}>{fr.colors.warnings}</span>
          <ul className="warns" aria-live="polite">
            {!custom && <li className="ok">{fr.colors.themeChecked}</li>}
            {custom && warnings.length === 0 && <li className="ok">{fr.colors.noWarning}</li>}
            {warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        </div>
      </div>
    </Dialog>
  );
}
