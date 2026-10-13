import { useMemo, useState } from "react";
import { selectLog, useStore } from "../data/store";
import { href } from "../app/route";
import { ModeTag, Panel } from "../ui/ui";
import { dateTime } from "../lib/format";
import { Empty, PageHead } from "../app/common";
import { DataTable } from "../app/table";

const COLS = "170px minmax(220px,1fr) minmax(320px,3fr) 130px";
interface Line { id: string; time: number; instId: string; text: string; by: "Opérateur" | "Automatisme"; alert: boolean }

export function Journal() {
  const s = useStore((x) => x);
  const [only, setOnly] = useState("");
  const lines = useMemo<Line[]>(() => {
    const out: Line[] = [];
    for (const i of s.instances) {
      for (const e of selectLog(s, i.id)) {
        if (e.kind === "commande" || e.kind === "alerte") out.push({ id: `${i.id}-${e.id}`, time: e.time, instId: i.id, text: e.text, by: e.kind === "alerte" ? "Automatisme" : "Opérateur", alert: e.kind === "alerte" });
      }
      for (const v of i.versions) out.push({ id: `${i.id}-v${v.n}`, time: v.createdAt, instId: i.id, text: `Version ${v.n} créée : ${v.summary}`, by: "Opérateur", alert: false });
    }
    return out.sort((a, b) => b.time - a.time);
  }, [s]);
  const shown = lines.filter((l) => !only || l.instId === only).slice(0, 300);
  const name = (id: string) => s.instances.find((i) => i.id === id)!;
  return (
    <div className="page">
      <PageHead title="Journal" desc="Les commandes, les alertes et les nouvelles versions de toutes les instances, de la plus récente à la plus ancienne.">
        <label className="check" style={{ gap: 12, fontSize: 14 }}>
          <span className="dim">Instance</span>
          <select className="select" style={{ width: "auto", minWidth: 220 }} value={only} onChange={(e) => setOnly(e.target.value)}>
            <option value="">Toutes les instances</option>
            {s.instances.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
          </select>
        </label>
      </PageHead>
      <Panel className="tbl" title={<>Évènements<span className="count">{shown.length}</span></>}>
        {shown.length === 0 ? (
          <Empty title="Aucun évènement"><span>Les commandes, les alertes et les nouvelles versions apparaîtront ici.</span></Empty>
        ) : (
          <DataTable label="Journal" cols={COLS} minW={860} head={["Heure (Toronto)", "Instance", "Évènement", "Auteur"]}>
            {shown.map((l) => {
              const i = name(l.instId);
              return (
                <div role="row" className="r tall wrap-row" key={l.id} style={{ gridTemplateColumns: COLS }}>
                  <span role="cell" className="small">{dateTime(l.time)}</span>
                  <span role="cell" className="t"><a href={href({ page: "instance", id: i.id, tab: "tout" })} style={{ marginRight: 8 }}>{i.name}</a><ModeTag mode={i.mode} /></span>
                  <span role="cell" className="t">{l.alert ? <span className="warn">Alerte · </span> : null}{l.text}</span>
                  <span role="cell" className="t dim">{l.by}</span>
                </div>
              );
            })}
          </DataTable>
        )}
      </Panel>
      <p className="quiet">Heures de Toronto. Seuls les évènements constatés sont consignés ; une commande demandée mais pas encore constatée n'y figure pas.</p>
    </div>
  );
}
