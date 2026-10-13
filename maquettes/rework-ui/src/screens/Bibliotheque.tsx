import { useEffect, useState, type ReactNode } from "react";
import { actions, useStore } from "../data/store";
import type { ApiKey, Automation, AutomationKind, Strategy, Timeframe } from "../data/types";
import { TIMEFRAMES } from "../data/types";
import type { LibraryTab } from "../app/route";
import { href } from "../app/route";
import { Button, Dialog, Field, Panel } from "../ui/ui";
import { dateTime, tfLabel } from "../lib/format";
import { Empty, PageHead, SectionHead, useAttempt, useTouched } from "../app/common";
import { DataTable } from "../app/table";
import { Menu } from "../app/Menu";

const TABS: { id: LibraryTab; label: string }[] = [
  { id: "cles", label: "Clés" }, { id: "strategies", label: "Stratégies" }, { id: "automatisations", label: "Automatisations" },
];

function Tabs({ tab }: { tab: LibraryTab }) {
  return (
    <nav className="utabs" aria-label="Bibliothèque">
      {TABS.map((t) => (
        <a key={t.id} className="utab" href={href({ page: "bibliotheque", tab: t.id })} aria-current={tab === t.id ? "page" : undefined}>{t.label}</a>
      ))}
    </nav>
  );
}

const userNames = (names: string[]) => (names.length ? names.join(", ") : <span className="dim">Aucune</span>);
const pct1 = (n: number) => `${n.toFixed(1).replace(".", ",")} %`;
const Err = ({ message }: { message: string | null }) => (message ? <div role="alert" className="inline-err">{message}</div> : null);

// ---------- clés ----------

const KEY_INIT = { name: "", exchange: "Binance", env: "test" as ApiKey["env"], currency: "USDT", secret: "" };

function KeyDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [f, setF] = useState(KEY_INIT);
  const v = useTouched();
  const [err, run, clear] = useAttempt();
  useEffect(() => { if (open) { setF(KEY_INIT); v.reset(); clear(); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const bad = { name: !f.name.trim() ? "Le nom est obligatoire." : undefined, secret: f.secret.length < 4 ? "La clé saisie est trop courte. Copier la clé complète depuis l'exchange." : undefined };
  const submit = () => {
    v.all();
    if (bad.name || bad.secret) return;
    if (run(() => actions.addKey(f))) onClose();
  };
  return (
    <Dialog open={open} onClose={onClose} title="Ajouter une clé" foot={<><Button onClick={onClose}>Annuler</Button><Button variant="go" onClick={submit}>Enregistrer la clé</Button></>}>
      <form className="form-grid" onSubmit={(e) => { e.preventDefault(); submit(); }} autoComplete="off" noValidate>
        <Field label="Nom" required error={v.show("name") ? bad.name : undefined} hint="Pour la reconnaître dans les listes.">
          <input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} onBlur={() => v.blur("name")} aria-invalid={v.show("name") && !!bad.name} placeholder="Par exemple : Binance, compte test" />
        </Field>
        <Field label="Exchange"><select className="select" value={f.exchange} onChange={(e) => setF({ ...f, exchange: e.target.value })}>{["Binance", "Kraken", "Coinbase"].map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Environnement" hint="Une clé de test ne touche jamais d'argent réel."><select className="select" value={f.env} onChange={(e) => setF({ ...f, env: e.target.value as ApiKey["env"] })}><option value="test">Test</option><option value="production">Production</option></select></Field>
        <Field label="Devise du compte"><select className="select" value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })}>{["USDT", "USDC", "USD", "CAD"].map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Clé secrète" required error={v.show("secret") ? bad.secret : undefined} hint="La clé n'est jamais ré-affichée après l'enregistrement.">
          <input className="input num" type="password" autoComplete="off" spellCheck={false} value={f.secret} onChange={(e) => setF({ ...f, secret: e.target.value })} onBlur={() => v.blur("secret")} aria-invalid={v.show("secret") && !!bad.secret} />
        </Field>
        <Err message={err} />
      </form>
    </Dialog>
  );
}

const KEY_COLS = "minmax(190px,1.5fr) 110px 130px 80px 100px 160px minmax(150px,1.2fr) 120px";

function KeyRow({ k, users }: { k: ApiKey; users: string[] }) {
  const [err, run] = useAttempt();
  return (
    <div role="row" className="r tall wrap-row" style={{ gridTemplateColumns: KEY_COLS }}>
      <span role="cell" className="t r-name">{k.name}</span>
      <span role="cell" className="t">{k.exchange}</span>
      <span role="cell"><span className="chip" style={{ height: 26 }}>{k.env === "test" ? "Test" : "Production"}</span></span>
      <span role="cell">{k.currency}</span>
      <span role="cell" className="dim" title="Seuls les 4 derniers caractères sont conservés">{k.hint}</span>
      <span role="cell" className="t">{dateTime(k.createdAt)}</span>
      <span role="cell" className="t">{userNames(users)}</span>
      <span role="cell" className="act-cell"><Button small onClick={() => run(() => actions.removeKey(k.id))}>Retirer</Button></span>
      {err && <span className="row-err" role="alert">{err} Retirer d'abord la clé de l'instance.</span>}
    </div>
  );
}

function Keys() {
  const keys = useStore((s) => s.keys);
  const insts = useStore((s) => s.instances);
  const [adding, setAdding] = useState(false);
  return (
    <>
      <section>
        <SectionHead title={<>Clés d'accès aux comptes<span className="count">{keys.length}</span></>} desc="Une clé donne à une instance l'accès à un compte d'exchange. Seuls les 4 derniers caractères sont gardés.">
          <Button variant="go" onClick={() => setAdding(true)}>Ajouter une clé</Button>
        </SectionHead>
        <Panel className="tbl">
          {keys.length === 0 ? (
            <Empty title="Aucune clé enregistrée"><span>Commencer par une clé de test : elle ne touche jamais d'argent réel.</span><Button variant="go" onClick={() => setAdding(true)}>Ajouter une clé</Button></Empty>
          ) : (
            <DataTable label="Clés" cols={KEY_COLS} minW={1040} head={["Nom", "Exchange", "Environnement", "Devise", "Clé", "Créée le", "Utilisée par", ""]}>
              {keys.map((k) => <KeyRow key={k.id} k={k} users={insts.filter((i) => i.keyId === k.id).map((i) => i.name)} />)}
            </DataTable>
          )}
        </Panel>
      </section>
      <p className="quiet">Une clé utilisée par une instance ne se retire pas.</p>
      <KeyDialog open={adding} onClose={() => setAdding(false)} />
    </>
  );
}

// ---------- stratégies ----------

type Draft = { name: string; description: string; timeframe: Timeframe; extra: Timeframe[]; sl: string; tp: string; rapide: string; lente: string };
const toDraft = (s?: Strategy): Draft => ({
  name: s?.name ?? "", description: s?.description ?? "", timeframe: s?.timeframe ?? "1h", extra: s?.extraTimeframes ?? [],
  sl: String(s?.stopLossPct ?? 3), tp: String(s?.takeProfitPct ?? 6), rapide: String(s?.params.rapide ?? 9), lente: String(s?.params.lente ?? 21),
});
const num = (v: string) => Number(v.replace(",", "."));

function StrategyDialog({ strategy, open, onClose }: { strategy: Strategy | null; open: boolean; onClose: () => void }) {
  const [d, setD] = useState<Draft>(toDraft());
  const v = useTouched();
  const [err, run, clear] = useAttempt();
  useEffect(() => { if (open) { setD(toDraft(strategy ?? undefined)); v.reset(); clear(); } }, [open, strategy, clear]); // eslint-disable-line react-hooks/exhaustive-deps
  const bad = {
    name: !d.name.trim() ? "Le nom est obligatoire." : undefined,
    sl: !(num(d.sl) > 0) ? "Un pourcentage supérieur à 0 est attendu." : undefined,
    tp: !(num(d.tp) > 0) ? "Un pourcentage supérieur à 0 est attendu." : undefined,
    rapide: !(num(d.rapide) > 0) ? "Une période supérieure à 0 est attendue." : undefined,
    lente: !(num(d.lente) > num(d.rapide)) ? "La période lente doit dépasser la rapide." : undefined,
  };
  const submit = () => {
    v.all();
    if (Object.values(bad).some(Boolean)) return;
    const body = {
      name: d.name.trim(), description: d.description.trim(), timeframe: d.timeframe, extraTimeframes: d.extra.filter((t) => t !== d.timeframe),
      stopLossPct: num(d.sl), takeProfitPct: num(d.tp), params: { rapide: num(d.rapide), lente: num(d.lente) },
    };
    if (run(() => (strategy ? actions.updateStrategy(strategy.id, body) : actions.addStrategy(body)))) onClose();
  };
  const toggleExtra = (t: Timeframe) => setD({ ...d, extra: d.extra.includes(t) ? d.extra.filter((x) => x !== t) : [...d.extra, t] });
  const text = (k: "name" | "sl" | "tp" | "rapide" | "lente", extra?: object) => ({
    value: d[k], onChange: (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value }), onBlur: () => v.blur(k), "aria-invalid": v.show(k) && !!bad[k], ...extra,
  });
  return (
    <Dialog
      open={open} onClose={onClose} title={strategy ? `Stratégie : ${strategy.name}` : "Ajouter une stratégie"}
      foot={
        <>
          {strategy && <Button variant="danger" style={{ marginRight: "auto" }} onClick={() => run(() => { actions.removeStrategy(strategy.id); onClose(); })}>Retirer</Button>}
          <Button onClick={onClose}>Annuler</Button><Button variant="go" onClick={submit}>{strategy ? "Enregistrer" : "Ajouter"}</Button>
        </>
      }
    >
      <form className="form-grid" onSubmit={(e) => { e.preventDefault(); submit(); }} noValidate>
        <Field label="Nom" required error={v.show("name") ? bad.name : undefined}><input className="input" {...text("name")} /></Field>
        <Field label="Description" hint="Une phrase pour se souvenir de ce que fait la stratégie."><textarea className="input" rows={3} value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} /></Field>
        <Field label="Unité de temps"><select className="select" value={d.timeframe} onChange={(e) => setD({ ...d, timeframe: e.target.value as Timeframe })}>{TIMEFRAMES.map((t) => <option key={t} value={t}>{tfLabel(t)}</option>)}</select></Field>
        <fieldset className="fieldset"><legend>Unités complémentaires</legend>
          <div className="checks">{TIMEFRAMES.filter((t) => t !== d.timeframe).map((t) => <label key={t} className="check"><input type="checkbox" checked={d.extra.includes(t)} onChange={() => toggleExtra(t)} />{tfLabel(t)}</label>)}</div>
        </fieldset>
        <Field label="Stop-loss, %" required error={v.show("sl") ? bad.sl : undefined} hint="Le bot vend si la position perd ce pourcentage."><input className="input num" inputMode="decimal" {...text("sl")} /></Field>
        <Field label="Take-profit, %" required error={v.show("tp") ? bad.tp : undefined} hint="Le bot vend si la position gagne ce pourcentage."><input className="input num" inputMode="decimal" {...text("tp")} /></Field>
        <Field label="Moyenne rapide (périodes)" required error={v.show("rapide") ? bad.rapide : undefined}><input className="input num" inputMode="numeric" {...text("rapide")} /></Field>
        <Field label="Moyenne lente (périodes)" required error={v.show("lente") ? bad.lente : undefined}><input className="input num" inputMode="numeric" {...text("lente")} /></Field>
        <Err message={err} />
      </form>
    </Dialog>
  );
}

const STRAT_COLS = "minmax(220px,1.6fr) 150px 170px 130px minmax(140px,1fr) 190px";

function Strategies() {
  const strategies = useStore((s) => s.strategies);
  const insts = useStore((s) => s.instances);
  const [edit, setEdit] = useState<Strategy | null>(null);
  const [adding, setAdding] = useState(false);
  const [err, run] = useAttempt();
  return (
    <>
      <section>
        <SectionHead title={<>Stratégies<span className="count">{strategies.length}</span></>} desc="Une stratégie décide quand un bot achète. On l'affecte ensuite à chaque paire d'une instance.">
          <Button variant="go" onClick={() => setAdding(true)}>Ajouter une stratégie</Button>
        </SectionHead>
        <Panel className="tbl">
          {strategies.length === 0 ? (
            <Empty title="Aucune stratégie"><span>Ajouter la première pour l'affecter à une paire.</span><Button variant="go" onClick={() => setAdding(true)}>Ajouter une stratégie</Button></Empty>
          ) : (
            <DataTable label="Stratégies" cols={STRAT_COLS} minW={1000} head={["Nom", "Unité de temps", "Seuils", "Paramètres", "Utilisée par", ""]}>
              {strategies.map((st) => (
                <div role="row" className="r tall wrap-row" key={st.id} style={{ gridTemplateColumns: STRAT_COLS }}>
                  <span role="cell" className="t"><button type="button" className="link-btn" onClick={() => setEdit(st)}>{st.name}</button>{st.description && <span className="sec">{st.description}</span>}</span>
                  <span role="cell" className="t">{tfLabel(st.timeframe)}{st.extraTimeframes.length > 0 && <span className="dim"> + {st.extraTimeframes.map(tfLabel).join(", ")}</span>}</span>
                  <span role="cell" className="t"><span className="dn">Stop-loss</span> <span className="num">{pct1(st.stopLossPct)}</span><span className="sec" style={{ fontSize: "inherit" }}><span className="up">Take-profit</span> <span className="num">{pct1(st.takeProfitPct)}</span></span></span>
                  <span role="cell" className="num small">{Object.entries(st.params).map(([k, v]) => `${k} ${v}`).join(" · ")}</span>
                  <span role="cell" className="t">{userNames(insts.filter((i) => i.pairs.some((p) => p.strategyId === st.id)).map((i) => i.name))}</span>
                  <span role="cell" className="act-cell">
                    <Button small onClick={() => setEdit(st)}>Modifier</Button>
                    <Menu small ariaLabel={`Autres actions, ${st.name}`} label="Autres actions" items={[{ label: "Retirer", hint: "Supprimer la stratégie", danger: true, onSelect: () => run(() => actions.removeStrategy(st.id)) }]} />
                  </span>
                </div>
              ))}
            </DataTable>
          )}
        </Panel>
        {err && <div role="alert" className="inline-err" style={{ marginTop: 12 }}>{err}</div>}
      </section>
      <p className="quiet">Exemples triviaux : Centrade ne conçoit pas de stratégie et ne donne aucun conseil.</p>
      <StrategyDialog strategy={edit} open={edit !== null || adding} onClose={() => { setEdit(null); setAdding(false); }} />
    </>
  );
}

// ---------- automatisations ----------

const KINDS: { kind: AutomationKind; title: string; line: ReactNode }[] = [
  { kind: "alerte", title: "Alertes et notifications", line: "Préviennent l'opérateur. Elles ne changent rien au comportement du bot." },
  { kind: "protection", title: "Règles de protection", line: <>Une règle de protection <b>ne peut que réduire le risque</b> : pause des achats, vente, jamais l'inverse.</> },
  { kind: "planification", title: "Planification", line: "Programment un démarrage ou une pause. Un démarrage planifié repasse par la vérification." },
  { kind: "agent", title: "Agents IA", line: <>Un agent <b>propose, un humain valide</b> : il n'applique aucun changement lui-même.</> },
];
const AUTO_COLS = "minmax(300px,2.4fr) minmax(160px,1fr) 120px";

function AutoRow({ a, users }: { a: Automation; users: string[] }) {
  const [err, run] = useAttempt();
  return (
    <div role="row" className="r tall wrap-row" style={{ gridTemplateColumns: AUTO_COLS }}>
      <span role="cell" className="t r-name">{a.name}{a.description && <span className="sec" style={{ fontWeight: 400 }}>{a.description}</span>}</span>
      <span role="cell" className="t">{userNames(users)}</span>
      <span role="cell" className="act-cell"><Button small onClick={() => run(() => actions.removeAutomation(a.id))}>Retirer</Button></span>
      {err && <span className="row-err" role="alert">{err}</span>}
    </div>
  );
}

function AutoDialog({ open, onClose, kind }: { open: boolean; onClose: () => void; kind: AutomationKind }) {
  const [f, setF] = useState({ kind, name: "", description: "" });
  const v = useTouched();
  const [err, run] = useAttempt();
  useEffect(() => { if (open) { setF({ kind, name: "", description: "" }); v.reset(); } }, [open, kind]); // eslint-disable-line react-hooks/exhaustive-deps
  const nameErr = !f.name.trim() ? "Le nom est obligatoire." : undefined;
  const submit = () => {
    v.all();
    if (nameErr) return;
    if (run(() => actions.addAutomation({ ...f, name: f.name.trim(), description: f.description.trim() }))) onClose();
  };
  return (
    <Dialog open={open} onClose={onClose} title="Ajouter une automatisation" foot={<><Button onClick={onClose}>Annuler</Button><Button variant="go" onClick={submit}>Ajouter</Button></>}>
      <form className="form-grid" onSubmit={(e) => { e.preventDefault(); submit(); }} noValidate>
        <Field label="Type" hint={f.kind === "protection" ? "Une règle de protection ne peut que réduire le risque." : f.kind === "agent" ? "Un agent propose, un humain valide." : "Rattachée ensuite à une instance, depuis son paramétrage."}>
          <select className="select" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as AutomationKind })}>{KINDS.map((k) => <option key={k.kind} value={k.kind}>{k.title}</option>)}</select>
        </Field>
        <Field label="Nom" required error={v.show("name") ? nameErr : undefined}><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} onBlur={() => v.blur("name")} aria-invalid={v.show("name") && !!nameErr} /></Field>
        <Field label="Description"><textarea className="input" rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Err message={err} />
      </form>
    </Dialog>
  );
}

function Automations() {
  const autos = useStore((s) => s.automations);
  const insts = useStore((s) => s.instances);
  const [adding, setAdding] = useState<AutomationKind | null>(null);
  return (
    <>
      {KINDS.map(({ kind, title, line }) => {
        const list = autos.filter((a) => a.kind === kind);
        return (
          <section key={kind}>
            <SectionHead title={<>{title}<span className="count">{list.length}</span></>} desc={line}>
              <Button variant="go" onClick={() => setAdding(kind)}>Ajouter</Button>
            </SectionHead>
            <Panel className="tbl">
              {list.length === 0 ? (
                <Empty title="Aucune pour l'instant"><span>Aucune automatisation de ce type. L'ajouter, puis la rattacher à une instance.</span></Empty>
              ) : (
                <DataTable label={title} cols={AUTO_COLS} minW={720} head={["Nom", "Rattachée à", ""]}>
                  {list.map((a) => <AutoRow key={a.id} a={a} users={insts.filter((i) => i.automationIds.includes(a.id)).map((i) => i.name)} />)}
                </DataTable>
              )}
            </Panel>
          </section>
        );
      })}
      <AutoDialog open={adding !== null} kind={adding ?? "alerte"} onClose={() => setAdding(null)} />
    </>
  );
}

export function Bibliotheque({ tab }: { tab: LibraryTab }) {
  return (
    <div className="page">
      <PageHead title="Bibliothèque" desc="Ce que les instances utilisent : les clés d'accès aux comptes, les stratégies et les automatisations." />
      <Tabs tab={tab} />
      {tab === "cles" ? <Keys /> : tab === "strategies" ? <Strategies /> : <Automations />}
    </div>
  );
}
