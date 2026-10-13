import { useState } from "react";
import { go } from "../../app/route";
import { actions, type State } from "../../data/store";
import type { Instance } from "../../data/types";
import { Button, Dialog, Field } from "../../ui/ui";
import { duration } from "../../lib/format";
import { useRun } from "./shared";

const MIN_DAYS = 14;
interface Item { label: string; ok: boolean; detail: string; demoSkippable?: boolean }

function checklist(inst: Instance, s: State): Item[] {
  const age = inst.startedAt === null ? 0 : s.cursor - inst.startedAt;
  const strategies = inst.pairs.map((p) => s.strategies.find((x) => x.id === p.strategyId));
  const alerts = inst.events.filter((e) => e.kind === "alerte");
  return [
    { label: "Durée minimale en mode test", ok: age >= MIN_DAYS * 86400, demoSkippable: true, detail: inst.startedAt === null ? `Jamais démarrée : ${MIN_DAYS} jours exigés` : `${duration(age)} constatés sur ${MIN_DAYS} jours exigés` },
    { label: "Limites définies", ok: s.automations.some((a) => a.kind === "protection" && inst.automationIds.includes(a.id)), detail: "Au moins une règle de protection rattachée" },
    { label: "Clé de production vérifiée", ok: s.keys.some((k) => k.env === "production"), detail: "Une clé de production existe dans la bibliothèque" },
    { label: "Stop-loss défini", ok: inst.pairs.length > 0 && strategies.every((x) => !!x && x.stopLossPct > 0), detail: "Chaque paire a une stratégie avec un stop-loss" },
    { label: "Aucune alerte critique", ok: alerts.length === 0, detail: alerts.length ? `${alerts.length} alerte(s) au journal` : "Aucune alerte au journal" },
  ];
}

export function PromoteDialog({ inst, s, open, onClose }: { inst: Instance; s: State; open: boolean; onClose: () => void }) {
  const [demo, setDemo] = useState(false);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [err, run] = useRun();
  const items = checklist(inst, s).map((i) => (demo && i.demoSkippable ? { ...i, ok: true, detail: `${i.detail} (ignorée pour la démo)` } : i));
  const failing = items.filter((i) => !i.ok);
  const codeOk = /^\d{6}$/.test(code);
  const nameOk = name.trim() === inst.name;
  const block = failing.length ? `Contrôle en échec : ${failing.map((i) => i.label.toLowerCase()).join(", ")}.` : !codeOk ? "Saisir le code TOTP à 6 chiffres." : !nameOk ? "Saisir le nom exact de l'instance." : null;
  const close = () => { setCode(""); setName(""); setDemo(false); onClose(); };
  const confirm = () => run(() => { const n = actions.promote(inst.id); close(); go({ page: "instance", id: n.id, tab: "tout" }); });

  return (
    <Dialog open={open} onClose={close} title="Passer en réel"
      foot={
        <>
          {block && <span className="small dim" style={{ marginRight: "auto" }} role="status">{block}</span>}
          <Button onClick={close}>Annuler</Button>
          <Button variant="danger" disabled={!!block} onClick={confirm}>Créer la copie réelle</Button>
        </>
      }>
      <p className="small dim" style={{ margin: 0 }}>Une copie réelle de « {inst.name} » est créée, sans clé : il faudra lui choisir une clé de production avant de la démarrer. L'instance de test reste intacte.</p>
      <ul className="in-check" aria-label="Liste de contrôles">
        {items.map((i) => (
          <li key={i.label} className={i.ok ? "up" : "dn"}>
            <b className="num">{i.ok ? "Réussi" : "Échec"}</b>
            <span className="in-check-t"><span style={{ color: "var(--c-ink)" }}>{i.label}</span><span className="xs dim">{i.detail}</span></span>
          </li>
        ))}
      </ul>
      <label className="check"><input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} /> <span className="tag-sim">Démo</span> ignorer la durée minimale</label>
      <Field label="Code TOTP" hint="Maquette : tout code à 6 chiffres est accepté.">
        <input className="input num" inputMode="numeric" autoComplete="off" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="000000" />
      </Field>
      <Field label={`Taper le nom de l'instance pour confirmer : ${inst.name}`} error={err ?? undefined}>
        <input className="input" autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
    </Dialog>
  );
}
