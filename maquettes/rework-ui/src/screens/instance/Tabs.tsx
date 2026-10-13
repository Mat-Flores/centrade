import { useRef } from "react";
import { motion } from "motion/react";
import { go } from "../../app/route";
import { selectStats, type State } from "../../data/store";
import type { DataStatus, Instance } from "../../data/types";
import { Delta } from "./shared";

function dataTag(inst: Instance, pair: string): { text: string; full: string } | null {
  const d = inst.backtest?.data[pair];
  const st: DataStatus = d?.status ?? "absentes";
  if (inst.mode !== "backtest") return null;
  if (st === "import") return { text: `Import ${Math.round(d!.progress)} %`, full: `Import des données en cours, ${Math.round(d!.progress)} %` };
  const w = { completes: "complètes", partielles: "partielles", absentes: "absentes" }[st];
  return { text: w[0].toUpperCase() + w.slice(1), full: `Données ${w}` };
}

/** Onglets « Tout » puis une paire par onglet ; flèches, Début et Fin déplacent la sélection. */
export function Tabs({ inst, s, tab }: { inst: Instance; s: State; tab: string }) {
  const ids = ["tout", ...inst.pairs.map((p) => p.pair)];
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const open = (t: string) => { go({ page: "instance", id: inst.id, tab: t }); refs.current[t]?.focus(); };
  const onKey = (e: React.KeyboardEvent) => {
    const i = ids.indexOf(tab);
    const next = e.key === "ArrowRight" ? ids[(i + 1) % ids.length] : e.key === "ArrowLeft" ? ids[(i - 1 + ids.length) % ids.length] : e.key === "Home" ? ids[0] : e.key === "End" ? ids[ids.length - 1] : null;
    if (next) { e.preventDefault(); open(next); }
  };
  return (
    <div className="tabs in-tabs" role="tablist" aria-label="Paires de l'instance" onKeyDown={onKey}>
      {ids.map((t) => {
        const on = t === tab;
        const st = t === "tout" ? null : selectStats(s, inst.id, t);
        const tag = t === "tout" ? null : dataTag(inst, t);
        return (
          <button key={t} ref={(el) => { refs.current[t] = el; }} type="button" role="tab" id={`tab-${t}`} aria-selected={on} tabIndex={on ? 0 : -1} className="tab in-tab"
            aria-label={st ? `${t}${tag ? `, ${tag.full}` : ""}` : undefined} onClick={() => open(t)}>
            {on && <motion.i layoutId={`ind-${inst.id}`} className="in-tab-ind" transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }} />}
            <span>{t === "tout" ? "Tout" : t}</span>
            {st && !tag && <Delta value={st.realizedPct + st.unrealizedPct} tone="real" />}
            {tag && <span className="tag" aria-hidden="true">{tag.text}</span>}
          </button>
        );
      })}
    </div>
  );
}
