import { useEffect, useState, type ReactNode } from "react";
import { actions, selectStats, useStore } from "../data/store";
import { href, useRoute, type Route } from "./route";
import { Button, Dialog, Field, ModeTag } from "../ui/ui";
import { signedPct } from "../lib/format";
import { ageText, ageOf, isRunning, isStale } from "./common";
import { setTheme, useTheme } from "./theme";
import { ColorDialog } from "./ColorDialog";
import { Menu, type MenuItem } from "./Menu";
import "./app.css";

const NAV: { label: string; to: Route; on: (r: Route) => boolean }[] = [
  { label: "Instances", to: { page: "instances" }, on: (r) => r.page === "instances" || r.page === "instance" },
  { label: "Bibliothèque", to: { page: "bibliotheque", tab: "cles" }, on: (r) => r.page === "bibliotheque" },
  { label: "Journal", to: { page: "journal" }, on: (r) => r.page === "journal" },
  { label: "Avancé", to: { page: "avance" }, on: (r) => r.page === "avance" },
];

function DemoDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const demo = useStore((s) => s.demo);
  return (
    <Dialog open={open} onClose={onClose} narrow title="Commandes de démonstration" foot={<Button variant="go" onClick={onClose}>Fermer</Button>}>
      <p className="note-lg">Ces réglages truquent la maquette pour montrer les cas d'échec. Ils n'existent pas dans le produit.</p>
      <label className="check-row"><input type="checkbox" checked={demo.failNextStart} onChange={(e) => actions.setDemo({ failNextStart: e.target.checked })} /><span><b>Faire échouer le prochain démarrage</b><small>Le prochain démarrage d'une instance se termine en erreur.</small></span></label>
      <label className="check-row"><input type="checkbox" checked={demo.frozen} onChange={(e) => actions.setDemo({ frozen: e.target.checked })} /><span><b>Figer les données</b><small>Plus aucune observation n'arrive : l'état devient périmé.</small></span></label>
    </Dialog>
  );
}

function NavLinks({ route }: { route: Route }) {
  return (
    <>
      {NAV.map((n) => (
        <a key={n.label} href={href(n.to)} aria-current={n.on(route) ? "page" : undefined}>{n.label}</a>
      ))}
    </>
  );
}

function KillDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const insts = useStore((s) => s.instances);
  const active = insts.filter((i) => isRunning(i) && i.observed !== "achats_en_pause");
  const n = active.length;
  return (
    <Dialog
      open={open} onClose={onClose} title="Arrêt d'urgence"
      foot={
        <>
          <Button onClick={onClose}>Annuler</Button>
          <Button variant="danger" onClick={() => { actions.setKillSwitch(true); onClose(); }}>Bloquer tous les achats</Button>
        </>
      }
    >
      <p style={{ margin: 0 }}>
        {n === 0 ? "Aucune instance active en ce moment : les démarrages seront refusés tant que l'arrêt d'urgence reste actif." : `${n} instance${n > 1 ? "s" : ""} active${n > 1 ? "s" : ""} : leurs achats seront bloqués.`}{" "}
        Les ventes et les stop-loss continuent.
      </p>
      {n > 0 && <ul style={{ margin: 0, paddingLeft: 20, color: "var(--c-mute)" }}>{active.map((i) => <li key={i.id}>{i.name}</li>)}</ul>}
      <p className="note-lg">Rien ne reprend de soi-même : la levée demande un code TOTP, puis chaque instance se relance à la main.</p>
    </Dialog>
  );
}

function LiftDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [code, setCode] = useState("");
  const [touched, setTouched] = useState(false);
  useEffect(() => { if (open) { setCode(""); setTouched(false); } }, [open]);
  const err = touched && !/^\d{6}$/.test(code) ? "Le code comporte 6 chiffres. Relire l'application d'authentification et réessayer." : undefined;
  const submit = () => {
    setTouched(true);
    if (!/^\d{6}$/.test(code)) return;
    actions.setKillSwitch(false);
    onClose();
  };
  return (
    <Dialog
      open={open} onClose={onClose} title="Lever l'arrêt d'urgence"
      foot={<><Button onClick={onClose}>Annuler</Button><Button variant="go" onClick={submit}>Lever l'arrêt d'urgence</Button></>}
    >
      <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="form-grid">
        <Field label="Code TOTP à 6 chiffres" required error={err} hint="Dans la maquette, n'importe quels 6 chiffres sont acceptés.">
          <input className="input num" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} onBlur={() => setTouched(true)} aria-invalid={!!err} />
        </Field>
      </form>
      <p className="note-lg">Rien ne reprend de soi-même : les instances restent en pause des achats, à reprendre une par une.</p>
    </Dialog>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const route = useRoute();
  const s = useStore((x) => x);
  const theme = useTheme();
  const [colors, setColors] = useState(false);
  const [demo, setDemo] = useState(false);
  const [kill, setKill] = useState(false);
  const [lift, setLift] = useState(false);

  const live = s.instances.filter(isRunning);
  const reachable = live.filter((i) => !isStale(i, s));
  const stale = live.length > 0 && reachable.length < live.length;
  const oldest = live.reduce((m, i) => Math.max(m, ageOf(i, s)), 0);
  const realOn = s.instances.some((i) => i.mode === "reel" && i.observed !== "arrete");

  const navItems: MenuItem[] = NAV.map((n) => ({ label: n.label, href: href(n.to), current: n.on(route) }));
  const settings: MenuItem[] = [
    { label: theme === "dark" ? "Thème clair" : "Thème sombre", hint: "Changer l'apparence", onSelect: () => setTheme(theme === "dark" ? "light" : "dark") },
    { label: "Couleurs", hint: "Personnaliser", onSelect: () => setColors(true) },
    { label: "Démo", hint: "Simuler une panne", onSelect: () => setDemo(true) },
    { label: "Paramètres", hint: "Page complète", href: href({ page: "parametres" }) },
  ];

  return (
    <>
      <a href="#contenu" className="sr" onClick={(e) => { e.preventDefault(); document.getElementById("contenu")?.focus(); }}>Aller au contenu</a>
      <header className="bar">
        <a className="mark" href={href({ page: "instances" })} aria-label="Centrade, accueil"><span className="title">Centrade</span></a>
        <nav className="nav" aria-label="Navigation principale"><NavLinks route={route} /></nav>
        <Menu className="nav-menu" label="Menu" ariaLabel="Navigation principale" align="left" items={navItems} />
        <div className="tape" aria-label="Instances en marche">
          {live.length === 0 && <span>Aucune instance en marche</span>}
          {live.map((i) => {
            const st = selectStats(s, i.id);
            const pct = st.realizedPct + st.unrealizedPct;
            return (
              <span key={i.id}>
                <b>{i.name}</b> <span className={pct > 0 ? "up" : pct < 0 ? "dn" : ""}>{signedPct(pct)}</span>{i.mode === "test" && <span className="sim"> sim.</span>}
              </span>
            );
          })}
        </div>
        <span className="spacer" />
        <ModeTag mode={realOn ? "reel" : "test"} />
        <div className={`bots ${stale ? "stale" : ""}`} role="status">
          <b>Bots {reachable.length} sur {live.length} joignables</b>
          {live.length > 0 ? <>constaté {ageText(oldest)}{stale && <> · périmé</>}</> : <>aucun bot en marche</>}
        </div>
        <Menu label="Réglages" ariaLabel="Réglages" items={settings} />
        {s.killSwitch ? <span className="tag-sim" style={{ color: "var(--c-loss)", borderColor: "var(--c-loss)" }}>Arrêt actif</span> : <Button variant="danger" small onClick={() => setKill(true)}>Arrêt d'urgence</Button>}
      </header>
      {s.killSwitch && (
        <div className="kill hatch" role="alert">
          <strong>Arrêt d'urgence actif : tous les achats sont bloqués. Les ventes continuent.</strong>
          <small>Rien ne reprend de soi-même.</small>
          <span className="sp" />
          <Button small onClick={() => setLift(true)}>Lever l'arrêt d'urgence</Button>
        </div>
      )}
      <main id="contenu" tabIndex={-1} style={{ outline: "none" }}>{children}</main>
      <ColorDialog open={colors} onClose={() => setColors(false)} />
      <DemoDialog open={demo} onClose={() => setDemo(false)} />
      <KillDialog open={kill} onClose={() => setKill(false)} />
      <LiftDialog open={lift} onClose={() => setLift(false)} />
    </>
  );
}
