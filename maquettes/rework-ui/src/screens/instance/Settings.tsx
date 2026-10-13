import { useEffect, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { href } from "../../app/route";
import { actions, type State } from "../../data/store";
import { EPOCH, PAIRS, SERIES_END } from "../../data/sim";
import type { Instance } from "../../data/types";
import { PROVIDERS, providerName } from "../../data/providers";
import type { ProviderId } from "../../data/types";
import { Button, Copy, Field, G } from "../../ui/ui";
import { tfLabel } from "../../lib/format";
import { KIND_LABEL, KIND_ORDER, groupByStrategy } from "./Composition";
import { VersionList } from "./Dialogs";
import { ErrorStrip, plainPct, useRun } from "./shared";

const ease = [0.2, 0.8, 0.2, 1] as const;

/** Section d'une page de réglages classique : titre et description d'une ligne, puis le panneau. */
function Section({ title, desc, extra, children }: { title: string; desc: string; extra?: ReactNode; children: ReactNode }) {
  return (
    <section className="set-sec" aria-label={title}>
      <header className="set-sec-h">
        <h2 className="subtitle">{title}</h2>
        {extra}
        <p className="small dim">{desc}</p>
      </header>
      <div className="panel">{children}</div>
    </section>
  );
}
const day = (t: number) => new Date(t * 1000).toISOString().slice(0, 10);
const parseDay = (v: string) => Date.parse(`${v}T00:00:00Z`) / 1000;

const PCOLS = "minmax(0,1fr) minmax(0,1.6fr) 120px";

function PairsPanel({ inst, s, editable, run }: { inst: Instance; s: State; editable: boolean; run: (fn: () => unknown) => void }) {
  const free = PAIRS.filter((p) => !inst.pairs.some((x) => x.pair === p));
  const [pair, setPair] = useState(free[0] ?? "");
  // Compatibilité : seules les stratégies du provider de l'instance sont proposées.
  const usable = s.strategies.filter((x) => x.provider === inst.provider);
  const [strat, setStrat] = useState(usable[0]?.id ?? "");
  useEffect(() => { if (!free.includes(pair)) setPair(free[0] ?? ""); }, [free.join("|")]);
  useEffect(() => { if (!usable.some((x) => x.id === strat)) setStrat(usable[0]?.id ?? ""); }, [usable.map((x) => x.id).join("|")]);
  const groups = groupByStrategy(inst, s.strategies);
  const opts = usable.map((x) => <option key={x.id} value={x.id}>{x.name}</option>);
  const prov = providerName(inst.provider);

  return (
    <Section title="Paires et stratégies" desc={`Chaque paire suit une stratégie ${prov} ; plusieurs paires peuvent partager la même.`}
      extra={<span className="xs faint num">{inst.pairs.length} paire{inst.pairs.length > 1 ? "s" : ""} · {groups.length} stratégie{groups.length > 1 ? "s" : ""}</span>}>
      <div className="cols" style={{ gridTemplateColumns: PCOLS }}><span>Paire</span><span>Stratégie</span><span /></div>
      <div className="in-rows">
        <AnimatePresence initial={false}>
          {groups.flatMap(({ strategy, pairs }) => [
            <motion.div layout key={`h-${strategy.id}`} className="in-grouph" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2, ease }}>
              <span className="subtitle">{strategy.name}</span>
              <span className="small dim num">{tfLabel(strategy.timeframe)} · <G k="stopLoss" /> {plainPct(strategy.stopLossPct, 1)} · <G k="takeProfit" /> {plainPct(strategy.takeProfitPct, 1)} · {pairs.length} {pairs.length > 1 ? "paires" : "paire"}</span>
            </motion.div>,
            ...pairs.map((p) => (
              <motion.div layout key={p} className="r in-prow" style={{ gridTemplateColumns: PCOLS, fontSize: 14 }}
                initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 56 }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.22, ease }}>
                <span>{p}</span>
                <span><select className="select" aria-label={`Stratégie de ${p}`} disabled={!editable} value={strategy.id} onChange={(e) => run(() => actions.setPairStrategy(inst.id, p, e.target.value))}>{opts}</select></span>
                <span className="right"><Button small variant="ghost" disabled={!editable} aria-label={`Retirer ${p}`} onClick={() => run(() => actions.removePair(inst.id, p))}>Retirer</Button></span>
              </motion.div>
            )),
          ])}
        </AnimatePresence>
        {groups.length === 0 && <div className="empty">Aucune paire : en ajouter une ci-dessous.</div>}
      </div>
      <form className="in-add" onSubmit={(e) => { e.preventDefault(); run(() => actions.addPair(inst.id, pair, strat)); }}>
        <Field label="Paire à ajouter">
          <select className="select" disabled={!editable || !free.length} value={pair} onChange={(e) => setPair(e.target.value)}>{free.map((p) => <option key={p}>{p}</option>)}</select>
        </Field>
        <Field label="Stratégie de la nouvelle paire">
          <select className="select" disabled={!editable} value={strat} onChange={(e) => setStrat(e.target.value)}>{opts}</select>
        </Field>
        <Button type="submit" disabled={!editable || !pair || !strat}>Ajouter la paire</Button>
      </form>
      {usable.length === 0 && (
        <div className="notice in-note-n" role="status">
          Aucune stratégie {prov} dans la bibliothèque : une stratégie ne sert que dans une instance de son provider.{" "}
          <a href={href({ page: "bibliotheque", tab: "strategies" })}>Créer une stratégie {prov}</a>
        </div>
      )}
      {!free.length && <div className="small faint in-note">Toutes les paires disponibles sont déjà dans l'instance.</div>}
    </Section>
  );
}

/** Le provider est l'écosystème de l'instance : il fixe le format des stratégies. Modifiable seulement sur une instance vierge. */
function ProviderPanel({ inst, editable, run }: { inst: Instance; editable: boolean; run: (fn: () => unknown) => void }) {
  const locked = !editable ? "Le provider ne change pas tant que l'instance tourne ou qu'elle est en mode réel."
    : inst.startedAt !== null ? "Fixé depuis le premier démarrage. Pour en changer, créer une nouvelle instance."
    : inst.pairs.length ? "Retirer d'abord les paires : leurs stratégies ne valent que pour ce provider." : null;
  return (
    <Section title="Provider" desc="Le moteur de trading qui fait tourner l'instance. Il détermine les stratégies utilisables : une stratégie Freqtrade ne sert que dans une instance Freqtrade.">
      <div className="in-note in-prov">
        <Field label="Provider de l'instance" hint={locked ?? "Modifiable tant que l'instance n'a ni paire ni démarrage."}>
          <select className="select" disabled={!!locked} value={inst.provider} onChange={(e) => run(() => actions.setProvider(inst.id, e.target.value as ProviderId))}>
            {PROVIDERS.map((p) => <option key={p.id} value={p.id} disabled={!p.ready}>{p.name}{p.ready ? "" : " (pas encore pris en charge)"}</option>)}
          </select>
        </Field>
        <dl className="kv in-prov-kv">
          <dt>Identifiant de l'instance</dt><dd><Copy value={inst.id} what="l'identifiant" /></dd>
          <dt>Stratégies compatibles</dt><dd><a href={href({ page: "bibliotheque", tab: "strategies" })}>Voir dans la bibliothèque</a></dd>
        </dl>
      </div>
    </Section>
  );
}

function AccountPanel({ inst, s, editable, run }: { inst: Instance; s: State; editable: boolean; run: (fn: () => unknown) => void }) {
  if (inst.mode === "backtest") return <Section title="Compte" desc="Le compte d'exchange utilisé par l'instance."><p className="in-note small dim" style={{ margin: 0 }}>Un backtest n'utilise aucun compte : aucune clé n'est transmise.</p></Section>;
  const env = inst.mode === "reel" ? "production" : "test";
  const keys = s.keys.filter((k) => k.env === env);
  const lockedReal = inst.mode === "reel" && inst.keyId !== null;
  return (
    <Section title="Compte" desc="Le compte d'exchange utilisé par l'instance. Une clé n'est jamais ré-affichée.">
      <div className="in-note">
        <Field label="Compte de l'instance">
        <select className="select" disabled={!editable || lockedReal} value={inst.keyId ?? ""} onChange={(e) => run(() => actions.setKey(inst.id, e.target.value))}>
          <option value="" disabled>{inst.mode === "reel" ? "Choisir une clé de production" : "Choisir un compte"}</option>
          {keys.map((k) => <option key={k.id} value={k.id}>{k.name} · {k.exchange} · {k.hint}</option>)}
        </select>
        </Field>
        {inst.mode === "reel" && inst.keyId === null && <p className="small warn" style={{ margin: "10px 0 0" }}>Cette copie réelle n'a pas encore de clé. Choisir une clé de production pour pouvoir la démarrer.</p>}
        {lockedReal && (
          <p className="small dim" style={{ margin: "10px 0 0" }}>
            Une instance en mode réel ne se modifie pas.{" "}
            {inst.promotedFrom ? <>Modifier l'<a href={href({ page: "instance", id: inst.promotedFrom, tab: "tout" })}>instance de test d'origine</a>, puis repasser en réel.</> : "Créer une instance de test, puis la passer en réel."}
          </p>
        )}
        {inst.mode === "test" && <p className="small faint" style={{ margin: "10px 0 0" }}>Seuls les comptes de test sont proposés : une instance de test ne touche jamais au compte principal.</p>}
      </div>
    </Section>
  );
}

function AutomationsPanel({ inst, s, editable, run }: { inst: Instance; s: State; editable: boolean; run: (fn: () => unknown) => void }) {
  return (
    <Section title="Automatisations" desc="Alertes, règles de protection, planification et agents rattachés à cette instance.">
      <div className="in-note in-autos">
        {KIND_ORDER.map((k) => {
          const list = s.automations.filter((a) => a.kind === k);
          return (
            <fieldset key={k} className="in-igrp" disabled={!editable}>
              <legend className="subtitle">{KIND_LABEL[k]}</legend>
              {list.length === 0 && <span className="small faint">Aucune dans la bibliothèque.</span>}
              {list.map((a) => (
                <label key={a.id} className="in-irow">
                  <input type="checkbox" checked={inst.automationIds.includes(a.id)} onChange={() => run(() => actions.toggleAutomation(inst.id, a.id))} />
                  <span className="in-itxt"><b>{a.name}</b><small>{a.description}</small></span>
                </label>
              ))}
            </fieldset>
          );
        })}
      </div>
    </Section>
  );
}

function NumField({ label, tip, value, onCommit, editable }: { label: string; tip: string; value: number; onCommit: (n: number) => void; editable: boolean }) {
  const [v, setV] = useState(String(value));
  useEffect(() => setV(String(value)), [value]);
  const commit = () => { const n = Number(v.replace(",", ".")); if (Number.isFinite(n) && n !== value) onCommit(n); else setV(String(value)); };
  return (
    <Field label={label} hint={tip}>
      <input className="input num" inputMode="decimal" disabled={!editable} value={v} onChange={(e) => setV(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && commit()} />
    </Field>
  );
}

function BacktestPanel({ inst, editable, run }: { inst: Instance; editable: boolean; run: (fn: () => unknown) => void }) {
  const bt = inst.backtest!;
  const bounds = { min: day(EPOCH), max: day(SERIES_END) };
  return (
    <Section title="Période et coûts" desc="Une période et un jeu de coûts pour toute l'instance. Un backtest n'est pas une prévision.">
      <div className="in-note in-bt-form">
        <Field label="Du"><input type="date" className="input num" {...bounds} disabled={!editable} value={day(bt.from)} onChange={(e) => e.target.value && run(() => actions.setBacktestConfig(inst.id, { from: parseDay(e.target.value) }))} /></Field>
        <Field label="Au"><input type="date" className="input num" {...bounds} disabled={!editable} value={day(bt.to)} onChange={(e) => e.target.value && run(() => actions.setBacktestConfig(inst.id, { to: parseDay(e.target.value) }))} /></Field>
        <NumField label="Fees (%)" tip="Frais de l'exchange, appliqués à chaque achat et à chaque vente." value={bt.feePct} editable={editable} onCommit={(n) => run(() => actions.setBacktestConfig(inst.id, { feePct: n }))} />
        <NumField label="Slippage (%)" tip="Glissement : l'écart entre le prix attendu et le prix d'exécution." value={bt.slippagePct} editable={editable} onCommit={(n) => run(() => actions.setBacktestConfig(inst.id, { slippagePct: n }))} />
      </div>
      <p className="small faint in-note" style={{ paddingTop: 0, margin: 0 }}>Les dates tiennent dans les 30 jours de données disponibles. Toute modification efface le résultat précédent.</p>
    </Section>
  );
}

/** Face « Réglages » : chaque modification réussie crée une version. Lecture seule tant que le bot tourne. */
export function Settings({ inst, s }: { inst: Instance; s: State }) {
  const [err, run, clear] = useRun();
  const running = inst.mode !== "backtest" && inst.observed !== "arrete";
  const editable = !running && inst.mode !== "reel";
  const keyEditable = !running && (inst.mode !== "reel" || inst.keyId === null);
  const notice: ReactNode = running ? "Arrêter l'instance pour modifier ses réglages" : null;

  return (
    <div className="in-settings scroll">
      <div className="in-set-page">
        {notice && <div className="notice" role="status">{notice}</div>}
        {inst.mode === "reel" && !running && <div className="notice" role="status">Une instance en mode réel ne se modifie pas. Pour changer un réglage : modifier l'instance de test d'origine, puis repasser en réel.</div>}
        <ErrorStrip message={err} onClose={clear} />
        <ProviderPanel inst={inst} editable={editable} run={run} />
        <PairsPanel inst={inst} s={s} editable={editable} run={run} />
        {inst.backtest && <BacktestPanel inst={inst} editable={!running} run={run} />}
        <AccountPanel inst={inst} s={s} editable={keyEditable} run={run} />
        <AutomationsPanel inst={inst} s={s} editable={editable} run={run} />
        <Section title="Versions" desc="Chaque modification de l'instance crée une nouvelle version." extra={<span className="xs faint num">{inst.versions.length}</span>}>
          <VersionList inst={inst} />
        </Section>
      </div>
    </div>
  );
}
