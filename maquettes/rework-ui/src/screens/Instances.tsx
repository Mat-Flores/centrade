import { useEffect, useState } from "react";
import { actions, selectStats, useStore } from "../data/store";
import type { State } from "../data/state";
import type { Instance, Mode, PairStats } from "../data/types";
import { go, href } from "../app/route";
import { Button, Dialog, Field, G, ModeTag, Panel, SimTag } from "../ui/ui";
import { PROVIDERS, providerName } from "../data/providers";
import type { ProviderId } from "../data/types";
import { SEEN_TIP, duration, money, seen } from "../lib/format";
import { ageOf, Arrow, Delta, Empty, isStale, MODE_ORDER, OBSERVED_LABEL, PageHead, SectionHead, useAttempt } from "../app/common";
import { DataTable, fr } from "../app/table";

// Huit colonnes en parts de largeur : le tableau tient toujours dans son cadre (voir app/table.tsx).
const COLS = fr(2.2, 1.2, 1.4, 1.2, 1.2, 0.8, 1, 1.4);
const HEAD = ["Nom", "État", "Solde", <G key="r" k="realized">Realized</G>, <G key="u" k="unrealized">Unrealized</G>, "Trades", "Depuis", ""];
const RIGHT = [2, 3, 4, 5, 6], HIDE = [5, 6];

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
      <span className={`chip ${stale ? "warn" : TONE[i.observed] ?? ""}`} data-tip={i.observed === "arrete" ? undefined : `${seen(ageOf(i, s))}.\n${SEEN_TIP}`}>
        <span className="st-word">{OBSERVED_LABEL[i.observed]}</span>
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
  if (i.observed === "achats_en_pause") return <Button small data-tip="Reprendre les achats" onClick={() => run(() => actions.resumeEntries(i.id))}>Reprendre</Button>;
  if (i.observed === "actif") return <Button small data-tip="Mettre en pause les achats : le bot continue de gérer et de vendre ses positions" onClick={() => run(() => actions.pauseEntries(i.id))}>Pause achats</Button>;
  return <Button small disabled>Démarrage…</Button>;
}

function Row({ i, s }: { i: Instance; s: State }) {
  const [err, run] = useAttempt();
  const st: PairStats = selectStats(s, i.id);
  const shown = hasResult(i);
  const figs = isStale(i, s) ? "dim-stale" : "";
  const short = i.pairs.map((p) => p.pair.split("/")[0]);
  return (
    <div role="row" className={`r tall ${needsAttention(i) ? "warn-row" : ""}`}>
      <span role="cell" className="r-name">
        <a className="cover" href={href({ page: "instance", id: i.id, tab: "tout" })}>{i.name}</a>
        <span className="sec" data-tip={`${providerName(i.provider)} · ${i.pairs.map((p) => p.pair).join(", ") || "aucune paire"}`}>
          {providerName(i.provider)} · {i.pairs.length === 0 ? "aucune paire" : <>{short.slice(0, 3).join(" ")}{short.length > 3 ? ` +${short.length - 3}` : ""}</>}
        </span>
      </span>
      <span role="cell" className="t">{statusCell(i, s)}</span>
      <span role="cell" className={`right ${figs}`}>{shown ? money(st.balance, i.currency) : "—"}</span>
      <span role="cell" className={`right ${figs}`}>{shown ? <Delta pct={st.realizedPct} amount={st.realized} currency={i.currency} /> : "—"}</span>
      <span role="cell" className={`right ${figs}`}>{shown ? <Delta pct={st.unrealizedPct} amount={st.unrealized} currency={i.currency} blue /> : "—"}</span>
      <span role="cell" className={`right hide-sm ${figs}`} data-tip={shown && st.openPositions ? `${st.trades} trades terminés, ${st.openPositions} position${st.openPositions > 1 ? "s" : ""} ouverte${st.openPositions > 1 ? "s" : ""}` : undefined}>{shown ? st.trades + (st.openPositions ? ` +${st.openPositions}` : "") : "—"}</span>
      <span role="cell" className="right hide-sm" data-tip={i.startedAt ? `En marche depuis ${duration(s.cursor - i.startedAt)}` : undefined}>{i.startedAt ? duration(s.cursor - i.startedAt).split(" ").slice(0, 4).join(" ") : "—"}</span>
      <span role="cell" className="act-cell"><RowAction i={i} run={run} /></span>
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
  const sum = (f: (x: PairStats) => number) => stats.reduce((a, x) => a + f(x.st), 0);
  const delta = (f: (x: PairStats) => number, blue?: boolean) => (one && start > 0 ? <Delta pct={(sum(f) / start) * 100} amount={sum(f)} currency={cur[0]} blue={blue} /> : "—");
  return (
    <div role="row" className="foot-row">
      <span role="cell" className="label" style={{ gridColumn: "1 / 3" }}>Total, ce mode seulement</span>
      <span role="cell" className="right">{stats.length === 0 ? "—" : cur.map((c) => money(stats.filter((x) => x.i.currency === c).reduce((a, x) => a + x.st.balance, 0), c)).join(" + ")}</span>
      <span role="cell" className="right">{delta((x) => x.realized)}</span>
      <span role="cell" className="right">{delta((x) => x.unrealized, true)}</span>
      <span role="cell" className="right hide-sm">{stats.length ? sum((x) => x.trades) : "—"}</span>
      <span role="cell" className="hide-sm" />
      <span role="cell" />
    </div>
  );
}

const MODE_TITLE: Record<Mode, string> = { reel: "Live", test: "Dry-run", backtest: "Backtest" };
const MODE_KEY = { reel: "live", test: "dryRun", backtest: "backtest" } as const;

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
        title={<><G k={MODE_KEY[mode]} />{mode !== "reel" && <SimTag />}<span className="count">{total}</span></>}
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
          <DataTable label={`Instances, ${MODE_TITLE[mode]}`} cols={COLS} head={HEAD} right={RIGHT} hideNarrow={HIDE} foot={<Totals rows={rows} s={s} />}>
            {rows.map((i) => <Row key={i.id} i={i} s={s} />)}
          </DataTable>
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
  const [provider, setProvider] = useState<ProviderId>("freqtrade");
  const [touched, setTouched] = useState(false);
  const [err, run, clear] = useAttempt();
  useEffect(() => { if (open) { setName(""); setMode("test"); setKeyId(""); setProvider("freqtrade"); setTouched(false); clear(); } }, [open, clear]);
  const nameErr = !name.trim() ? "Le nom est obligatoire." : names.includes(name.trim().toLowerCase()) ? "Une instance porte déjà ce nom. En choisir un autre." : undefined;

  const submit = () => {
    setTouched(true);
    if (nameErr) return;
    let id = "";
    if (run(() => { id = actions.createInstance({ name, mode, provider, keyId: mode === "test" && keyId ? keyId : null }).id; })) {
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
        <Field label="Provider" hint="Le moteur de trading de l'instance. Il fixe les stratégies utilisables : une stratégie Freqtrade ne sert que dans une instance Freqtrade.">
          <select className="select" value={provider} onChange={(e) => setProvider(e.target.value as ProviderId)}>
            {PROVIDERS.map((p) => <option key={p.id} value={p.id} disabled={!p.ready}>{p.name}{p.ready ? "" : " (pas encore pris en charge)"}</option>)}
          </select>
        </Field>
        <fieldset className="opt-group">
          <legend>Mode</legend>
          <label className="opt">
            <input type="radio" name="mode" checked={mode === "test"} onChange={() => setMode("test")} />
            <b>Dry-run (mode test) <SimTag /></b>
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
      <PageHead title="Instances" desc="Chaque instance est un environnement de trading : un provider, un mode, un compte, des paires et une stratégie par paire.">
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
      <p className="quiet">Les trois tableaux ne s'additionnent jamais : live, dry-run et backtest restent séparés. Les montants sont dans la devise de chaque compte, sans conversion. Un clic sur une variation l'affiche en devise plutôt qu'en %.</p>
      <CreateDialog open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
