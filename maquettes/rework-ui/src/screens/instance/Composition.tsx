import { go } from "../../app/route";
import type { State } from "../../data/store";
import type { AutomationKind, Instance, Strategy } from "../../data/types";
import { tfLabel } from "../../lib/format";
import { Term } from "../../ui/ui";
import { Zone, type Dash } from "./dash";
import { plainPct } from "./shared";

export const KIND_LABEL: Record<AutomationKind, string> = { alerte: "Alertes", protection: "Règles de protection", planification: "Planification", agent: "Agents IA" };
export const KIND_ORDER: AutomationKind[] = ["alerte", "protection", "planification", "agent"];

/** Paires de l'instance regroupées par stratégie, dans l'ordre d'apparition. */
export function groupByStrategy(inst: Instance, strategies: Strategy[]): { strategy: Strategy; pairs: string[] }[] {
  const out: { strategy: Strategy; pairs: string[] }[] = [];
  for (const p of inst.pairs) {
    const strategy = strategies.find((x) => x.id === p.strategyId);
    if (!strategy) continue;
    const g = out.find((x) => x.strategy.id === strategy.id);
    if (g) g.pairs.push(p.pair); else out.push({ strategy, pairs: [p.pair] });
  }
  return out;
}

export function StrategyFacts({ st }: { st: Strategy }) {
  return (
    <dl className="kv in-facts">
      <dt>Unité de temps</dt><dd>{tfLabel(st.timeframe)}</dd>
      <dt><Term tech="stop-loss" tip="Prix auquel la position est vendue pour limiter la perte.">Stop-loss</Term></dt><dd>{plainPct(st.stopLossPct, 1)}</dd>
      <dt><Term tech="take-profit" tip="Prix auquel la position est vendue pour encaisser le gain.">Take-profit</Term></dt><dd>{plainPct(st.takeProfitPct, 1)}</dd>
    </dl>
  );
}

/** Compte, stratégies (avec les paires qui les partagent) et automatisations de l'instance. */
export function Composition({ inst, s, activePair, dash }: { inst: Instance; s: State; activePair?: string; dash: Dash }) {
  const key = s.keys.find((k) => k.id === inst.keyId);
  const groups = groupByStrategy(inst, s.strategies);
  const autos = s.automations.filter((a) => inst.automationIds.includes(a.id));

  return (
    <Zone id="comp" name="Composition" side dash={dash} className="in-comp" label="Composition de l'instance">
      <div className="in-comp-body scroll">
        <div className="in-sec">
          <span className="label">Compte</span>
          {key && inst.mode !== "backtest" ? (
            <>
              <div className="subtitle">{key.name}</div>
              <div className="xs dim num">{key.exchange} · <span className="tag">{key.env === "production" ? "production" : "test"}</span> · {key.hint}</div>
            </>
          ) : (
            <div className="small dim">{inst.mode === "reel" ? "Clé de production à choisir dans les réglages" : "Aucune clé transmise"}</div>
          )}
        </div>

        <div className="in-sec-h label">Stratégies</div>
        {groups.length === 0 && <div className="in-sec small dim">Aucune paire pour le moment.</div>}
        {groups.map(({ strategy, pairs }) => (
          <div key={strategy.id} className="in-strat">
            <div className="in-strat-h">
              <span className="subtitle">{strategy.name}</span>
              <span className="xs dim num">{pairs.length} {pairs.length > 1 ? "paires" : "paire"}</span>
            </div>
            <StrategyFacts st={strategy} />
            {pairs.map((p) => (
              <button key={p} type="button" className={`r in-pair ${p === activePair ? "sel" : ""}`} aria-current={p === activePair ? "true" : undefined}
                onClick={() => go({ page: "instance", id: inst.id, tab: p })}>
                <span>{p}</span>
                <span className="right faint">{p === activePair ? "affichée" : "ouvrir"}</span>
              </button>
            ))}
          </div>
        ))}

        <div className="in-sec-h label">Automatisations</div>
        {autos.length === 0 && <div className="in-sec small dim">Aucune automatisation rattachée.</div>}
        {KIND_ORDER.map((k) => {
          const list = autos.filter((a) => a.kind === k);
          return list.length ? (
            <div key={k} className="in-auto">
              <span className="xs faint">{KIND_LABEL[k]}</span>
              {list.map((a) => <div key={a.id} className="in-auto-i" title={a.description}>{a.name}</div>)}
            </div>
          ) : null;
        })}
      </div>
    </Zone>
  );
}
