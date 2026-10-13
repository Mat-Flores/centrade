import { CAUSE_LABEL } from "../../data/store";
import type { ExitCause, PairStats, Trade } from "../../data/types";
import { duration, signedMoney, signedPct } from "../../lib/format";
import { plainNum, plainPct } from "./shared";

export type Group = "Performance" | "Risque" | "Activité" | "Causes de vente";
export interface Ctx { st: PairStats; trades: Trade[]; cur: string }
export interface Shown { text: string; tone?: "up" | "dn" | "act" }
export interface IndDef { key: string; group: Group; label: string; tech?: string; tip: string; show: (c: Ctx) => Shown }

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
  key: `cause:${k}`, group: "Causes de vente", label: CAUSE_LABEL[k], tech: k,
  tip: "Nombre de trades vendus pour cette raison.",
  show: (c) => ({ text: String(c.st.exitCauses[k] ?? 0) }),
}));

export const INDICATORS: IndDef[] = [
  { key: "winRate", group: "Performance", label: "Taux de réussite", tech: "win rate", tip: "Part des trades terminés en gain.", show: (c) => ({ text: plainPct(c.st.winRate * 100) }) },
  { key: "avgWin", group: "Performance", label: "Gain moyen", tech: "average win", tip: "Résultat moyen des trades terminés en gain.", show: (c) => money(c.st.avgWin, c) },
  { key: "avgLoss", group: "Performance", label: "Perte moyenne", tech: "average loss", tip: "Résultat moyen des trades terminés en perte.", show: (c) => money(c.st.avgLoss, c) },
  { key: "profitFactor", group: "Performance", label: "Rapport gains/pertes", tech: "profit factor", tip: "Somme des gains divisée par la somme des pertes.", show: (c) => ({ text: Number.isFinite(c.st.profitFactor) ? plainNum(c.st.profitFactor) : "∞" }) },
  { key: "best", group: "Performance", label: "Meilleur trade", tech: "best trade", tip: "Plus grand gain d'un trade terminé.", show: (c) => money(c.st.best, c) },
  { key: "worst", group: "Performance", label: "Pire trade", tech: "worst trade", tip: "Plus grande perte d'un trade terminé.", show: (c) => money(c.st.worst, c) },
  { key: "expectancy", group: "Performance", label: "Gain moyen par trade", tech: "espérance", tip: "Résultat moyen d'un trade, gains et pertes confondus.", show: (c) => money(c.st.expectancy, c) },
  { key: "sharpe", group: "Performance", label: "Ratio de Sharpe", tech: "Sharpe", tip: "Rendement rapporté à la variabilité du solde.", show: (c) => ({ text: plainNum(c.st.sharpe) }) },
  { key: "sortino", group: "Performance", label: "Ratio de Sortino", tech: "Sortino", tip: "Comme Sharpe, mais ne compte que les baisses du solde.", show: (c) => ({ text: plainNum(c.st.sortino) }) },
  { key: "calmar", group: "Performance", label: "Ratio de Calmar", tech: "Calmar", tip: "Rendement rapporté à la plus forte baisse.", show: (c) => ({ text: plainNum(c.st.calmar) }) },
  { key: "maxDrawdownPct", group: "Risque", label: "Plus forte baisse", tech: "drawdown maximal", tip: "Plus grand recul du solde depuis un sommet.", show: (c) => ({ text: signedPct(c.st.maxDrawdownPct), tone: sign(c.st.maxDrawdownPct) }) },
  { key: "currentDrawdownPct", group: "Risque", label: "Baisse en cours", tech: "drawdown courant", tip: "Recul actuel du solde depuis son dernier sommet.", show: (c) => ({ text: signedPct(c.st.currentDrawdownPct), tone: sign(c.st.currentDrawdownPct) }) },
  { key: "exposurePct", group: "Risque", label: "Capital engagé", tech: "exposition", tip: "Part du solde placée dans des positions ouvertes.", show: (c) => ({ text: plainPct(c.st.exposurePct, 1) }) },
  {
    key: "stopDistance", group: "Risque", label: "Distance au stop", tech: "stop-loss", tip: "Écart entre le prix actuel et le stop-loss de la position ouverte la plus proche.",
    show: (c) => { const d = stopDistance(c.trades); return { text: d === null ? "—" : plainPct(d, 2) }; },
  },
  { key: "openPositions", group: "Activité", label: "Positions ouvertes", tech: "open positions", tip: "Trades achetés et pas encore vendus.", show: (c) => ({ text: String(c.st.openPositions), tone: c.st.openPositions ? "act" : undefined }) },
  { key: "avgDurationSec", group: "Activité", label: "Durée moyenne d'un trade", tech: "average duration", tip: "Temps moyen entre l'achat et la vente.", show: (c) => ({ text: c.st.trades ? duration(c.st.avgDurationSec) : "—" }) },
  { key: "fees", group: "Activité", label: "Frais payés", tech: "fees", tip: "Frais d'exchange payés, achats et ventes.", show: (c) => ({ text: signedMoney(-c.st.fees, c.cur) }) },
  { key: "refusedEntries", group: "Activité", label: "Achats refusés", tech: "rejet de risque", tip: "Une protection a refusé l'achat.", show: (c) => ({ text: String(c.st.refusedEntries) }) },
  ...causes,
];

export const GROUPS: Group[] = ["Performance", "Risque", "Activité", "Causes de vente"];
