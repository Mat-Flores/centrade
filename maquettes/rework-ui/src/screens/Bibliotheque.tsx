import { useEffect, useState, type ReactNode } from "react";
import { actions, useStore } from "../data/store";
import type { ApiKey, Automation, AutomationKind, ProviderId, Strategy, Timeframe } from "../data/types";
import { PROVIDERS, ftChecks, ftClassName, ftTemplate, providerName } from "../data/providers";
import { TIMEFRAMES } from "../data/types";
import type { LibraryTab } from "../app/route";
import { href } from "../app/route";
import { Button, Copy, Dialog, Field, G, Panel } from "../ui/ui";
import { dateTime, tfLabel } from "../lib/format";
import { Empty, PageHead, SectionHead, useAttempt, useTouched } from "../app/common";
import { DataTable, fr } from "../app/table";
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

const KEY_COLS = fr(1.7, 0.9, 1.1, 0.7, 0.9, 1.2, 1.4, 0.9);

function KeyRow({ k, users }: { k: ApiKey; users: string[] }) {
  const [err, run] = useAttempt();
  return (
    <div role="row" className="r tall wrap-row">
      <span role="cell" className="t r-name">{k.name}</span>
      <span role="cell" className="t">{k.exchange}</span>
      <span role="cell"><span className="chip" style={{ height: 26 }}>{k.env === "test" ? "Test" : "Production"}</span></span>
      <span role="cell">{k.currency}</span>
      <span role="cell" className="dim"><Copy value={k.hint} what="la fin de la clé (seuls les 4 derniers caractères sont conservés)" /></span>
      <span role="cell" className="t hide-sm">{dateTime(k.createdAt)}</span>
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
            <DataTable label="Clés" cols={KEY_COLS} hideNarrow={[5]} head={["Nom", "Exchange", "Environnement", "Devise", "Clé", "Créée le", "Utilisée par", ""]}>
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

// Chaque provider a son propre format de stratégie, donc sa propre fenêtre de création. Seule celle de Freqtrade existe.

type Draft = { name: string; description: string; code: string; timeframe: Timeframe; extra: Timeframe[]; sl: string; tp: string; trailing: boolean; rapide: string; lente: string };
const toDraft = (s?: Strategy): Draft => ({
  name: s?.name ?? "", description: s?.description ?? "", code: s?.code ?? ftTemplate("MaStrategie"), timeframe: s?.timeframe ?? "1h", extra: s?.extraTimeframes ?? [],
  sl: String(s?.stopLossPct ?? 3), tp: String(s?.takeProfitPct ?? 6), trailing: s?.trailing ?? false, rapide: String(s?.params.rapide ?? 9), lente: String(s?.params.lente ?? 21),
});
const num = (v: string) => Number(v.replace(",", "."));

/** Création et modification d'une stratégie Freqtrade : identité, code (une classe Python), politique de sortie, paramètres.
 *  Le code passe les contrôles statiques du registre avant tout enregistrement (SPEC §3.3 et §7). */
function FreqtradeStrategyDialog({ strategy, open, onClose }: { strategy: Strategy | null; open: boolean; onClose: () => void }) {
  const [d, setD] = useState<Draft>(toDraft());
  const v = useTouched();
  const [err, run, clear] = useAttempt();
  useEffect(() => { if (open) { setD(toDraft(strategy ?? undefined)); v.reset(); clear(); } }, [open, strategy, clear]); // eslint-disable-line react-hooks/exhaustive-deps
  const checks = ftChecks(d.code);
  const className = ftClassName(d.code);
  const bad = {
    name: !d.name.trim() ? "Le nom est obligatoire." : undefined,
    code: !className ? "Aucune classe trouvée : le code doit déclarer une classe Python." : checks.some((c) => !c.ok) ? "Le code ne passe pas les contrôles ci-dessous." : undefined,
    sl: !(num(d.sl) > 0) ? "Un pourcentage supérieur à 0 est attendu." : undefined,
    tp: !(num(d.tp) > 0) ? "Un pourcentage supérieur à 0 est attendu." : undefined,
    rapide: !(num(d.rapide) >= 2) ? "Un entier d'au moins 2 est attendu." : undefined,
    lente: !(num(d.lente) > num(d.rapide)) ? "La période lente doit dépasser la rapide." : undefined,
  };
  const submit = () => {
    v.all();
    if (Object.values(bad).some(Boolean)) return;
    const body = {
      provider: "freqtrade" as const, name: d.name.trim(), description: d.description.trim(), className: className!, code: d.code,
      timeframe: d.timeframe, extraTimeframes: d.extra.filter((t) => t !== d.timeframe),
      stopLossPct: num(d.sl), takeProfitPct: num(d.tp), trailing: d.trailing, params: { rapide: num(d.rapide), lente: num(d.lente) },
    };
    if (run(() => (strategy ? actions.updateStrategy(strategy.id, body) : actions.addStrategy(body)))) onClose();
  };
  const toggleExtra = (t: Timeframe) => setD({ ...d, extra: d.extra.includes(t) ? d.extra.filter((x) => x !== t) : [...d.extra, t] });
  const text = (k: "name" | "sl" | "tp" | "rapide" | "lente", extra?: object) => ({
    value: d[k], onChange: (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value }), onBlur: () => v.blur(k), "aria-invalid": v.show(k) && !!bad[k], ...extra,
  });
  return (
    <Dialog
      open={open} onClose={onClose} wide title={strategy ? `Stratégie Freqtrade : ${strategy.name}` : "Nouvelle stratégie Freqtrade"}
      foot={
        <>
          {strategy && <Button variant="danger" onClick={() => run(() => { actions.removeStrategy(strategy.id); onClose(); })}>Retirer</Button>}
          <span className="note-sm" style={{ marginRight: "auto" }}>{strategy ? `Enregistrer crée la version ${strategy.version + 1}.` : "Utilisable seulement dans une instance Freqtrade."}</span>
          <Button onClick={onClose}>Annuler</Button><Button variant="go" onClick={submit}>{strategy ? "Enregistrer" : "Créer la stratégie"}</Button>
        </>
      }
    >
      <form className="form-grid" onSubmit={(e) => { e.preventDefault(); submit(); }} noValidate>
        <Field label="Nom" required error={v.show("name") ? bad.name : undefined}><input className="input" {...text("name")} placeholder="Par exemple : Croisement de moyennes" /></Field>
        <Field label="Description" hint="Une phrase pour se souvenir de ce que fait la stratégie."><textarea className="input" rows={2} value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} /></Field>

        <Field label="Code de la stratégie (Python)" required error={v.show("code") ? bad.code : undefined}
          hint={className ? `Classe détectée : ${className}. Fichier déposé : user_data/strategies/${className}.py` : "Une classe Python qui hérite de ControlPlaneStrategy."}>
          <textarea className="input num code" rows={12} spellCheck={false} autoCapitalize="off" autoCorrect="off" value={d.code}
            onChange={(e) => setD({ ...d, code: e.target.value })} onBlur={() => v.blur("code")} aria-invalid={v.show("code") && !!bad.code} />
        </Field>
        <ul className="ft-checks" aria-label="Contrôles du code">
          {checks.map((c) => (
            <li key={c.label} className={c.ok ? "up" : "dn"}><b className="num">{c.ok ? "Réussi" : "Échec"}</b><span>{c.label[0].toUpperCase() + c.label.slice(1)}</span></li>
          ))}
        </ul>
        <p className="note-sm" style={{ margin: 0 }}>Maquette : contrôles simplifiés. Dans le produit, le registre relit le code côté serveur avant de l'accepter.</p>

        <div className="form-grid two">
          <Field label="Timeframe" hint="Durée d'une bougie tradée par le bot."><select className="select" value={d.timeframe} onChange={(e) => setD({ ...d, timeframe: e.target.value as Timeframe })}>{TIMEFRAMES.map((t) => <option key={t} value={t}>{tfLabel(t)}</option>)}</select></Field>
          <fieldset className="fieldset"><legend>Timeframes complémentaires</legend>
            <div className="checks">{TIMEFRAMES.filter((t) => t !== d.timeframe).map((t) => <label key={t} className="check"><input type="checkbox" checked={d.extra.includes(t)} onChange={() => toggleExtra(t)} />{tfLabel(t)}</label>)}</div>
          </fieldset>
        </div>

        <fieldset className="fieldset">
          <legend>Politique de sortie : écrite dans la configuration générée, elle l'emporte sur le code</legend>
          <div className="form-grid two">
            <Field label="Stop-loss, %" required error={v.show("sl") ? bad.sl : undefined} hint="Obligatoire. Le bot vend si la position perd ce pourcentage."><input className="input num" inputMode="decimal" {...text("sl")} /></Field>
            <Field label="Take-profit, %" required error={v.show("tp") ? bad.tp : undefined} hint="Le bot vend si la position gagne ce pourcentage."><input className="input num" inputMode="decimal" {...text("tp")} /></Field>
          </div>
          <label className="check"><input type="checkbox" checked={d.trailing} onChange={(e) => setD({ ...d, trailing: e.target.checked })} /><G k="trailing" /> : le stop-loss remonte avec le prix</label>
        </fieldset>

        <fieldset className="fieldset">
          <legend>Paramètres lus par le code</legend>
          <div className="form-grid two">
            <Field label="fast : moyenne rapide (périodes)" required error={v.show("rapide") ? bad.rapide : undefined}><input className="input num" inputMode="numeric" {...text("rapide")} /></Field>
            <Field label="slow : moyenne lente (périodes)" required error={v.show("lente") ? bad.lente : undefined}><input className="input num" inputMode="numeric" {...text("lente")} /></Field>
          </div>
        </fieldset>
        <Err message={err} />
      </form>
    </Dialog>
  );
}

const STRAT_COLS = fr(2.4, 1, 1.1, 1.3, 0.7, 1.4, 1.5);
type Filter = ProviderId | "tout";

function Strategies() {
  const strategies = useStore((s) => s.strategies);
  const insts = useStore((s) => s.instances);
  const [filter, setFilter] = useState<Filter>("tout");
  const [edit, setEdit] = useState<Strategy | null>(null);
  const [adding, setAdding] = useState(false);
  const [err, run] = useAttempt();
  const list = strategies.filter((st) => filter === "tout" || st.provider === filter);
  const count = (f: Filter) => strategies.filter((st) => f === "tout" || st.provider === f).length;
  const provider = PROVIDERS.find((p) => p.id === filter);
  // La création dépend du provider : sur « Tout », on crée pour Freqtrade, seul provider pris en charge.
  const canCreate = !provider || provider.ready;
  const create = canCreate ? <Button variant="go" onClick={() => setAdding(true)}>Créer une stratégie Freqtrade</Button> : <Button disabled data-tip={provider!.note}>Création indisponible</Button>;
  return (
    <>
      <section>
        <SectionHead title={<>Stratégies<span className="count">{strategies.length}</span></>} desc={<>Une stratégie décide quand un bot achète. Elle appartient à un <G k="provider">provider</G> et ne sert que dans une instance de ce provider.</>}>
          {create}
        </SectionHead>
        <div className="pills prov-pills" role="tablist" aria-label="Filtrer par provider">
          {(["tout", ...PROVIDERS.map((p) => p.id)] as Filter[]).map((f) => (
            <button key={f} type="button" role="tab" className="pill" aria-selected={filter === f} onClick={() => setFilter(f)}>
              {f === "tout" ? "Tout" : providerName(f)} <span className="num">{count(f)}</span>
            </button>
          ))}
        </div>
        <Panel className="tbl">
          {list.length === 0 ? (
            provider && !provider.ready
              ? <Empty title={`${provider.name} n'est pas encore pris en charge`}><span>{provider.note} Aucune stratégie ne peut être créée pour ce provider, et aucune instance ne peut l'utiliser.</span></Empty>
              : <Empty title="Aucune stratégie"><span>Créer la première pour l'affecter à une paire d'une instance Freqtrade.</span>{create}</Empty>
          ) : (
            <DataTable label="Stratégies" cols={STRAT_COLS} hideNarrow={[4]} head={["Nom", <G key="p" k="provider" />, <G key="t" k="timeframe" />, "Sorties", "Version", "Utilisée par", ""]}>
              {list.map((st) => (
                <div role="row" className="r tall wrap-row" key={st.id}>
                  <span role="cell" className="t">
                    <button type="button" className="link-btn" onClick={() => setEdit(st)}>{st.name}</button>
                    <span className="sec num"><Copy value={`${st.className}.py`} what="le nom du fichier" /></span>
                    {st.description && <span className="sec clamp2" data-tip={st.description}>{st.description}</span>}
                  </span>
                  <span role="cell"><span className="chip" style={{ height: 26 }}>{providerName(st.provider)}</span></span>
                  <span role="cell" className="t">{tfLabel(st.timeframe)}{st.extraTimeframes.length > 0 && <span className="dim"> + {st.extraTimeframes.map(tfLabel).join(", ")}</span>}</span>
                  <span role="cell" className="t">
                    <span className="dn">Stop-loss</span> <span className="num">{pct1(st.stopLossPct)}</span>
                    <span className="sec" style={{ fontSize: "inherit" }}><span className="up">Take-profit</span> <span className="num">{pct1(st.takeProfitPct)}</span></span>
                    {st.trailing && <span className="sec">Trailing stop actif</span>}
                  </span>
                  <span role="cell" className="num hide-sm">v{st.version}</span>
                  <span role="cell" className="t">{userNames(insts.filter((i) => i.pairs.some((p) => p.strategyId === st.id)).map((i) => i.name))}</span>
                  <span role="cell" className="act-cell">
                    <Button small onClick={() => setEdit(st)}>Modifier</Button>
                    <Menu small ariaLabel={`Autres actions, ${st.name}`} label="…" items={[{ label: "Retirer", hint: "Supprimer la stratégie", danger: true, onSelect: () => run(() => actions.removeStrategy(st.id)) }]} />
                  </span>
                </div>
              ))}
            </DataTable>
          )}
        </Panel>
        {err && <div role="alert" className="inline-err" style={{ marginTop: 12 }}>{err}</div>}
      </section>
      <p className="quiet">Exemples triviaux : Centrade ne conçoit pas de stratégie et ne donne aucun conseil. Une stratégie modifiée devient une nouvelle version.</p>
      <FreqtradeStrategyDialog strategy={edit} open={edit !== null || adding} onClose={() => { setEdit(null); setAdding(false); }} />
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
const AUTO_COLS = fr(3, 1.3, 0.8);

function AutoRow({ a, users }: { a: Automation; users: string[] }) {
  const [err, run] = useAttempt();
  return (
    <div role="row" className="r tall wrap-row">
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
                <DataTable label={title} cols={AUTO_COLS} head={["Nom", "Rattachée à", ""]}>
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
