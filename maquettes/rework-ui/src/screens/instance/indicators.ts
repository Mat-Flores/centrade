import { CAUSE_LABEL } from "../../data/store";
import type { ExitCause, PairStats, Trade } from "../../data/types";
import { duration, money as plainMoney, signedMoney, signedPct } from "../../lib/format";
import { plainNum, plainPct } from "./shared";

export type Group = "Performance" | "Risque" | "Activité" | "Causes de vente";
export interface Ctx { st: PairStats; trades: Trade[]; cur: string }
export interface Shown { text: string; tone?: "up" | "dn" | "act" }
/** `label` : terme technique, en anglais quand c'est l'usage. `tip` : son explication en français.
 *  `alt` : la même valeur en devise (ou en nombre), montrée quand l'interface est basculée de % vers la devise. */
export interface IndDef { key: string; group: Group; label: string; tip: string; show: (c: Ctx) => Shown; alt?: (c: Ctx) => string }

const sign = (n: number): "up" | "dn" | undefined => (Math.round(Math.abs(n) * 100) === 0 ? undefined : n > 0 ? "up" : "dn");
const money = (n: number, c: Ctx): Shown => ({ text: signedMoney(n, c.cur), tone: sign(n) });

/** Distance au stop-loss de la position ouverte la plus proche (prix actuel déduit du résultat en cours). */
function stopDistance(trades: Trade[]): number | null {
  const d = trades.filter((t) => t.exitTime === undefined).map((t) => {
    const last = t.entryPrice * (1 + (t.pnl + t.fees) / t.stake);
    return ((last - t.stopLoss) / last) * 100;
  });
  return d.length ? Math.min(...d) : null;
}

const causes = (Object.keys(CAUSE_LABEL) as ExitCause[]).map<IndDef>((k) => ({
  key: `cause:${k}`, group: "Causes de vente", label: CAUSE_LABEL[k],
  tip: "Nombre de trades vendus pour cette raison.",
  show: (c) => ({ text: String(c.st.exitCauses[k] ?? 0) }),
}));

export const INDICATORS: IndDef[] = [
  { key: "winRate", group: "Performance", label: "Win rate", tip: "Taux de réussite : la part des trades terminés en gain.", show: (c) => ({ text: plainPct(c.st.winRate * 100) }), alt: (c) => `${c.st.wins} sur ${c.st.trades}` },
  { key: "avgWin", group: "Performance", label: "Average win", tip: "Gain moyen : le résultat moyen des trades terminés en gain.", show: (c) => money(c.st.avgWin, c) },
  { key: "avgLoss", group: "Performance", label: "Average loss", tip: "Perte moyenne : le résultat moyen des trades terminés en perte.", show: (c) => money(c.st.avgLoss, c) },
  { key: "profitFactor", group: "Performance", label: "Profit factor", tip: "Rapport gains/pertes : la somme des gains divisée par la somme des pertes.", show: (c) => ({ text: Number.isFinite(c.st.profitFactor) ? plainNum(c.st.profitFactor) : "∞" }) },
  { key: "best", group: "Performance", label: "Best trade", tip: "Le plus grand gain d'un trade terminé.", show: (c) => money(c.st.best, c) },
  { key: "worst", group: "Performance", label: "Worst trade", tip: "La plus grande perte d'un trade terminé.", show: (c) => money(c.st.worst, c) },
  { key: "expectancy", group: "Performance", label: "Expectancy", tip: "Espérance : le résultat moyen d'un trade, gains et pertes confondus.", show: (c) => money(c.st.expectancy, c) },
  { key: "sharpe", group: "Performance", label: "Sharpe ratio", tip: "Rendement rapporté à la variabilité du solde.", show: (c) => ({ text: plainNum(c.st.sharpe) }) },
  { key: "sortino", group: "Performance", label: "Sortino ratio", tip: "Comme le Sharpe ratio, mais ne compte que les baisses du solde.", show: (c) => ({ text: plainNum(c.st.sortino) }) },
  { key: "calmar", group: "Performance", label: "Calmar ratio", tip: "Rendement rapporté au max drawdown.", show: (c) => ({ text: plainNum(c.st.calmar) }) },
  { key: "maxDrawdownPct", group: "Risque", label: "Max drawdown", tip: "Plus forte baisse : le plus grand recul du solde depuis un sommet.", show: (c) => ({ text: signedPct(c.st.maxDrawdownPct), tone: sign(c.st.maxDrawdownPct) }), alt: (c) => signedMoney(c.st.maxDrawdown, c.cur) },
  { key: "currentDrawdownPct", group: "Risque", label: "Drawdown", tip: "Baisse en cours : le recul actuel du solde depuis son dernier sommet.", show: (c) => ({ text: signedPct(c.st.currentDrawdownPct), tone: sign(c.st.currentDrawdownPct) }), alt: (c) => signedMoney(c.st.currentDrawdown, c.cur) },
  { key: "exposurePct", group: "Risque", label: "Exposure", tip: "Capital engagé : la part du solde placée dans des positions ouvertes.", show: (c) => ({ text: plainPct(c.st.exposurePct, 1) }), alt: (c) => plainMoney(c.st.exposure, c.cur) },
  {
    key: "stopDistance", group: "Risque", label: "Stop distance", tip: "Écart entre le prix actuel et le stop-loss de la position ouverte la plus proche.",
    show: (c) => { const d = stopDistance(c.trades); return { text: d === null ? "—" : plainPct(d, 2) }; },
  },
  { key: "openPositions", group: "Activité", label: "Open positions", tip: "Positions ouvertes : les trades achetés et pas encore vendus.", show: (c) => ({ text: String(c.st.openPositions), tone: c.st.openPositions ? "act" : undefined }) },
  { key: "avgDurationSec", group: "Activité", label: "Durée moyenne", tip: "Temps moyen entre l'achat et la vente d'un trade.", show: (c) => ({ text: c.st.trades ? duration(c.st.avgDurationSec) : "—" }) },
  { key: "fees", group: "Activité", label: "Fees", tip: "Frais d'exchange payés, achats et ventes.", show: (c) => ({ text: signedMoney(-c.st.fees, c.cur) }) },
  { key: "refusedEntries", group: "Activité", label: "Achats refusés", tip: "Achats refusés par une protection (rejet de risque).", show: (c) => ({ text: String(c.st.refusedEntries) }) },
  ...causes,
];

export const GROUPS: Group[] = ["Performance", "Risque", "Activité", "Causes de vente"];
