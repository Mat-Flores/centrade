import { useEffect, useState } from "react";
import { actions, selectStats, useStore } from "../data/store";
import type { State } from "../data/state";
import type { Instance, Mode, PairStats } from "../data/types";
import { go, href } from "../app/route";
import { Button, Dialog, Field, ModeTag, Panel, SimTag, Term } from "../ui/ui";
import { duration, money } from "../lib/format";
import { ageOf, ageText, Arrow, Chevron, Delta, Empty, isStale, MODE_ORDER, OBSERVED_LABEL, PageHead, SectionHead, useAttempt } from "../app/common";

const COLS = "minmax(140px,1.2fr) 230px minmax(110px,0.9fr) 140px 104px 104px 124px 76px 150px 28px";
const MIN_W = "1200px";
const HEAD = ["Nom", "État constaté", "Paires", "Solde", "Encaissé", "En cours", "Transactions", "Depuis", "", ""];

const needsAttention = (i: Instance) => i.observed === "erreur" || i.command?.status === "echouee";
const hasResult = (i: Instance) => i.mode !== "backtest" || i.backtest?.run.status === "termine";

type Tone = "ok" | "warn" | "err" | "info" | "";
const TONE: Record<string, Tone> = { actif: "ok", achats_en_pause: "warn", erreur: "err", lancement: "info", verification: "info", arrete: "", inconnu: "warn" };

function statusCell(i: Instance, s: State) {
  if (i.mode === "backtest") {
    const run = i.backtest?.run.status ?? "jamais";
    const tone: Tone = run === "echec" ? "err" : run === "en_cours" ? "info" : "";
    return <span className={`chip ${tone}`}>{{ jamais: "Jamais lancé", en_cours: "Simulation en cours", termine: "Terminé", echec: "Échec" }[run]}</span>;
  }
  const stale = isStale(i, s);
  const pending = i.command?.status === "en_cours";
  const failed = i.command?.status === "echouee";
  return (
    <>
      <span className={`chip ${stale ? "warn" : TONE[i.observed] ?? ""}`}>
        <span className="st-word">{OBSERVED_LABEL[i.observed]}</span>
        {i.observed !== "arrete" && <span className="age">{ageText(ageOf(i, s))}</span>}
      </span>
      {stale && <span className="warn small" style={{ marginLeft: 8 }}>périmé</span>}
      {failed ? <span className="dn small" style={{ marginLeft: 8 }}>échec</span> : pending && <span className="dim small" style={{ marginLeft: 8 }}>demandé</span>}
    </>
  );
}

function RowAction({ i, run }: { i: Instance; run: (fn: () => unknown) => boolean }) {
  const open = () => go({ page: "instance", id: i.id, tab: "tout" });
  if (i.mode === "backtest" || i.observed === "erreur" || i.observed === "inconnu") return <Button small onClick={open}>Ouvrir</Button>;
  if (i.observed === "arrete") return <Button small onClick={() => run(() => actions.start(i.id))}>Démarrer</Button>;
  if (i.observed === "achats_en_pause") return <Button small onClick={() => run(() => actions.resumeEntries(i.id))}>Reprendre les achats</Button>;
  if (i.observed === "actif") return <Button small onClick={() => run(() => actions.pauseEntries(i.id))}>Pause des achats</Button>;
  return <Button small disabled>Démarrage…</Button>;
}

function Row({ i, s }: { i: Instance; s: State }) {
  const [err, run] = useAttempt();
  const st: PairStats = selectStats(s, i.id);
  const shown = hasResult(i);
  const stale = isStale(i, s);
  const figs = stale ? "dim-stale" : "";
  const short = i.pairs.map((p) => p.pair.split("/")[0]);
  return (
    <div role="row" className={`r tall ${needsAttention(i) ? "warn-row" : ""}`} style={{ gridTemplateColumns: COLS }}>
      <span role="cell" className="r-name"><a className="cover" href={href({ page: "instance", id: i.id, tab: "tout" })}>{i.name}</a></span>
      <span role="cell" className="t" style={{ overflow: "visible" }}>{statusCell(i, s)}</span>
      <span role="cell" className="t" title={i.pairs.map((p) => p.pair).join(", ")}>
        {i.pairs.length === 0 ? <span className="dim">Aucune paire</span> : <>{i.pairs.length} <span className="dim">· {short.slice(0, 3).join(" ")}{short.length > 3 ? ` +${short.length - 3}` : ""}</span></>}
      </span>
      <span role="cell" className={`right ${figs}`}>{shown ? money(st.balance, i.currency) : "—"}</span>
      <span role="cell" className={`right ${figs}`} title={shown ? `${money(st.realized, i.currency)} encaissés, frais déduits` : undefined}>{shown ? <Delta pct={st.realizedPct} /> : "—"}</span>
      <span role="cell" className={`right ${figs}`} title={shown ? `${money(st.unrealized, i.currency)} sur les positions ouvertes` : undefined}>{shown ? <Delta pct={st.unrealizedPct} blue /> : "—"}</span>
      <span role="cell" className={`right ${figs}`}>{shown ? st.trades + (st.openPositions ? ` (+${st.openPositions} ouv.)` : "") : "—"}</span>
      <span role="cell" className="right">{i.startedAt ? duration(s.cursor - i.startedAt) : "—"}</span>
      <span role="cell" className="act-cell"><RowAction i={i} run={run} /></span>
      <span role="cell" className="right"><Chevron /></span>
      {err && <span className="row-err" role="alert">{err}</span>}
    </div>
  );
}

function Totals({ rows, s }: { rows: Instance[]; s: State }) {
  const withRes = rows.filter(hasResult);
  const stats = withRes.map((i) => ({ i, st: selectStats(s, i.id) }));
  const cur = [...new Set(stats.map((x) => x.i.currency))];
  const one = cur.length === 1;
  const start = stats.reduce((a, x) => a + x.i.startBalance, 0);
  const pct = (f: (x: PairStats) => number) => (one && start > 0 ? (stats.reduce((a, x) => a + f(x.st), 0) / start) * 100 : NaN);
  const realized = pct((x) => x.realized), open = pct((x) => x.unrealized);
  return (
    <div role="row" className="foot-row" style={{ gridTemplateColumns: COLS, minWidth: MIN_W }}>
      <span role="cell" className="label" style={{ gridColumn: "1 / 4" }}>Total, ce mode seulement</span>
      <span role="cell" className="right">{stats.length === 0 ? "—" : cur.map((c) => money(stats.filter((x) => x.i.currency === c).reduce((a, x) => a + x.st.balance, 0), c)).join(" + ")}</span>
      <span role="cell" className="right">{Number.isNaN(realized) ? "—" : <Delta pct={realized} />}</span>
      <span role="cell" className="right">{Number.isNaN(open) ? "—" : <Delta pct={open} blue />}</span>
      <span role="cell" className="right">{stats.length ? stats.reduce((a, x) => a + x.st.trades, 0) : "—"}</span>
      <span role="cell" />
      <span role="cell" />
      <span role="cell" />
    </div>
  );
}

const MODE_TITLE: Record<Mode, string> = { reel: "Mode réel", test: "Mode test", backtest: "Backtest" };
const MODE_TIP: Record<Mode, string> = {
  reel: "Le bot trade avec l'argent du compte.",
  test: "Le bot trade avec de l'argent fictif. Tous les chiffres sont simulés.",
  backtest: "Le bot rejoue une période passée. Un backtest n'est pas une prévision.",
};

const MODE_DESC: Record<Mode, string> = {
  reel: "Les bots qui tradent avec l'argent d'un vrai compte.",
  test: "Les bots qui tradent avec de l'argent fictif, sur un compte de test.",
  backtest: "Les simulations qui rejouent une période passée.",
};

function ModeTable({ mode, s, q, onCreate }: { mode: Mode; s: State; q: string; onCreate: () => void }) {
  const rows = s.instances.filter((i) => i.mode === mode && i.name.toLowerCase().includes(q.trim().toLowerCase())).sort((a, b) => +needsAttention(b) - +needsAttention(a));
  const total = s.instances.filter((i) => i.mode === mode).length;
  return (
    <section aria-label={MODE_TITLE[mode]}>
      <SectionHead
        title={<><Term tip={MODE_TIP[mode]} tech={mode === "reel" ? "live" : mode === "test" ? "paper, dry-run" : undefined}>{MODE_TITLE[mode]}</Term>{mode !== "reel" && <SimTag />}<span className="count">{total}</span></>}
        desc={MODE_DESC[mode]}
      />
      <Panel className="tbl">
        {rows.length === 0 ? (
          total > 0 ? (
            <Empty title="Aucune instance ne correspond"><span>Aucun nom de ce mode ne contient « {q} ». Effacer le filtre pour tout revoir.</span></Empty>
          ) : mode === "reel" ? (
            <Empty title="Aucune instance en mode réel">
              <span>Le mode réel s'obtient depuis une instance de test, avec « Passer en réel » (liste de contrôles, puis code TOTP).</span>
            </Empty>
          ) : (
            <Empty title={mode === "test" ? "Aucune instance en mode test" : "Aucun backtest"}>
              <span>{mode === "test" ? "Une instance de test trade avec de l'argent fictif sur un compte de test." : "Un backtest rejoue une période passée avec des données importées."}</span>
              <Button variant="go" onClick={onCreate}>Créer une instance</Button>
            </Empty>
          )
        ) : (
          <div className="scroll-x" tabIndex={0} aria-label={`Instances, ${MODE_TITLE[mode]}`}>
            <div role="table" aria-label={MODE_TITLE[mode]} style={{ minWidth: MIN_W }}>
              <div role="rowgroup">
                <div role="row" className="cols" style={{ gridTemplateColumns: COLS }}>
                  {HEAD.map((h, n) => <span key={n} role="columnheader" className={n >= 3 && n <= 7 ? "right" : ""}>{h || <span className="sr">{n === 8 ? "Action" : "Ouvrir"}</span>}</span>)}
                </div>
              </div>
              <div role="rowgroup">{rows.map((i) => <Row key={i.id} i={i} s={s} />)}</div>
              <div role="rowgroup"><Totals rows={rows} s={s} /></div>
            </div>
          </div>
        )}
      </Panel>
    </section>
  );
}

function CreateDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const allKeys = useStore((s) => s.keys);
  const insts = useStore((s) => s.instances);
  const keys = allKeys.filter((k) => k.env === "test");
  const names = insts.map((i) => i.name.trim().toLowerCase());
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"test" | "backtest">("test");
  const [keyId, setKeyId] = useState("");
  const [touched, setTouched] = useState(false);
  const [err, run, clear] = useAttempt();
  useEffect(() => { if (open) { setName(""); setMode("test"); setKeyId(""); setTouched(false); clear(); } }, [open, clear]);
  const nameErr = !name.trim() ? "Le nom est obligatoire." : names.includes(name.trim().toLowerCase()) ? "Une instance porte déjà ce nom. En choisir un autre." : undefined;

  const submit = () => {
    setTouched(true);
    if (nameErr) return;
    let id = "";
    if (run(() => { id = actions.createInstance({ name, mode, keyId: mode === "test" && keyId ? keyId : null }).id; })) {
      onClose();
      go({ page: "instance", id, tab: "tout" });
    }
  };

  return (
    <Dialog
      open={open} onClose={onClose} title="Créer une instance"
      foot={<><Button onClick={onClose}>Annuler</Button><Button variant="go" onClick={submit}>Créer l'instance</Button></>}
    >
      <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="form-grid" noValidate>
        <Field label="Nom" required error={touched ? nameErr : undefined} hint="Visible dans la liste, le journal et la barre du haut.">
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} onBlur={() => name && setTouched(true)} aria-invalid={touched && !!nameErr} placeholder="Par exemple : Swing majors" />
        </Field>
        <fieldset className="opt-group">
          <legend>Mode</legend>
          <label className="opt">
            <input type="radio" name="mode" checked={mode === "test"} onChange={() => setMode("test")} />
            <b>Mode test <SimTag /></b>
            <span>Argent fictif sur un compte de test. Tous les chiffres sont simulés.</span>
          </label>
          <label className="opt">
            <input type="radio" name="mode" checked={mode === "backtest"} onChange={() => setMode("backtest")} />
            <b>Backtest <SimTag /></b>
            <span>Rejoue une période passée avec des données importées. Un backtest n'est pas une prévision.</span>
          </label>
          <div className="opt off" aria-disabled="true" role="note">
            <svg className="lock" viewBox="0 0 14 14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2.5" y="6.5" width="9" height="6" rx="1.5" /><path d="M4.5 6.5V4.5a2.5 2.5 0 0 1 5 0v2" /></svg>
            <b>Mode réel <ModeTag mode="reel" /></b>
            <span>Le mode réel ne se choisit pas à la création : créer une instance en mode test, puis utiliser « Passer en réel ».</span>
          </div>
        </fieldset>
        {mode === "test" && (
          <Field label="Compte (clé de test)" hint={keys.length ? "Facultatif. Modifiable plus tard, tant que l'instance est arrêtée." : undefined}>
            {keys.length ? (
              <select className="select" value={keyId} onChange={(e) => setKeyId(e.target.value)}>
                <option value="">Choisir plus tard</option>
                {keys.map((k) => <option key={k.id} value={k.id}>{k.name} ({k.currency})</option>)}
              </select>
            ) : (
              <span className="notice">Aucune clé de test enregistrée. <a href={href({ page: "bibliotheque", tab: "cles" })} onClick={onClose}>Ajouter une clé dans la Bibliothèque</a></span>
            )}
          </Field>
        )}
        {err && <div role="alert" className="inline-err">{err}</div>}
      </form>
    </Dialog>
  );
}

export function Instances() {
  const s = useStore((x) => x);
  const [creating, setCreating] = useState(false);
  const [q, setQ] = useState("");
  const attention = s.instances.filter(needsAttention);
  return (
    <div className="page">
      <PageHead title="Instances" desc="Chaque instance est un environnement de trading : un mode, un compte, des paires et une stratégie par paire.">
        <Button variant="go" onClick={() => setCreating(true)}>Créer une instance</Button>
      </PageHead>
      {attention.length > 0 && (
        <div className="notice loss" role="alert">
          <Arrow up={false} />
          <span>À traiter : {attention.map((i, n) => <span key={i.id}>{n > 0 && ", "}<a href={href({ page: "instance", id: i.id, tab: "tout" })}>{i.name}</a></span>)}. Ouvrir l'instance pour voir la cause.</span>
        </div>
      )}
      {s.instances.length > 6 && (
        <input className="input filter" type="search" aria-label="Filtrer les instances par nom" placeholder="Filtrer par nom" value={q} onChange={(e) => setQ(e.target.value)} />
      )}
      {MODE_ORDER.map((m) => <ModeTable key={m} mode={m} s={s} q={q} onCreate={() => setCreating(true)} />)}
      <p className="quiet">Les trois tableaux ne s'additionnent jamais : réel, test et backtest restent séparés. Les montants sont dans la devise de chaque compte, sans conversion.</p>
      <CreateDialog open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
