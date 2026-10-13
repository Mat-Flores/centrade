// Contrat de données de la maquette. Tout est fictif, en mémoire, déterministe.
// shortcut: les montants sont des `number` (données inventées, jamais de l'argent réel) ;
// au portage dans apps/web, passer aux chaînes décimales exigées par le SPEC.

export type Mode = "test" | "reel" | "backtest";
export type Timeframe = "5m" | "15m" | "1h" | "4h" | "1j";
export const TIMEFRAMES: Timeframe[] = ["5m", "15m", "1h", "4h", "1j"];

/** Ce que le bot rapporte réellement (état constaté). */
export type ObservedState = "arrete" | "lancement" | "verification" | "actif" | "achats_en_pause" | "erreur" | "inconnu";
/** Ce que l'opérateur a demandé (état demandé). */
export type WantedState = "arrete" | "actif" | "achats_en_pause";

export type ExitCause =
  | "take_profit" | "stop_loss" | "trailing_stop" | "signal" | "timeout" | "manual" | "kill_switch" | "engine_protection" | "unknown";

export interface Candle {
  /** Secondes UTC (début de la bougie). */
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface Trade {
  id: string;
  pair: string;
  strategyId: string;
  entryTime: number;
  entryPrice: number;
  /** Montant engagé, dans la devise du compte. */
  stake: number;
  stopLoss: number;
  takeProfit: number;
  /** Absents tant que la position est ouverte. */
  exitTime?: number;
  exitPrice?: number;
  exitCause?: ExitCause;
  /** Frais payés (achat + vente), devise du compte. */
  fees: number;
  /** Résultat net de frais : encaissé si le trade est terminé, en cours sinon (au dernier prix constaté). */
  pnl: number;
  pnlPct: number;
}

export type LogKind = "achat" | "vente" | "achat_refuse" | "commande" | "alerte";
export interface LogEntry {
  id: string;
  time: number;
  kind: LogKind;
  pair?: string;
  text: string;
  /** Prix pour un achat, résultat pour une vente. */
  amount?: number;
  tradeId?: string;
}

export interface ApiKey {
  id: string;
  name: string;
  exchange: string;
  env: "test" | "production";
  currency: string;
  createdAt: number;
  /** Jamais la valeur de la clé : seulement ses 4 derniers caractères. */
  hint: string;
}

/** Provider : le moteur de trading (l'écosystème) d'une instance. Une stratégie n'existe que pour un provider. */
export type ProviderId = "freqtrade" | "nautilus";

export interface Strategy {
  id: string;
  name: string;
  description: string;
  provider: ProviderId;
  /** Propres au provider. Freqtrade : une classe Python qui hérite de ControlPlaneStrategy. */
  className: string;
  code: string;
  /** Une stratégie modifiée devient une nouvelle version (SPEC §3.3). */
  version: number;
  trailing: boolean;
  timeframe: Timeframe;
  /** Unités de temps complémentaires que la stratégie consulte. */
  extraTimeframes: Timeframe[];
  stopLossPct: number;
  takeProfitPct: number;
  params: Record<string, number>;
}

export type AutomationKind = "alerte" | "protection" | "planification" | "agent";
export interface Automation {
  id: string;
  kind: AutomationKind;
  name: string;
  description: string;
}

export interface PairConfig {
  pair: string;
  strategyId: string;
}

export interface InstanceVersion {
  n: number;
  createdAt: number;
  summary: string;
}

export type DataStatus = "absentes" | "partielles" | "completes" | "import";
export interface BacktestConfig {
  /** Secondes UTC. */
  from: number;
  to: number;
  feePct: number;
  slippagePct: number;
  /** État des données par paire, pour l'unité de temps tradée. */
  data: Record<string, { status: DataStatus; progress: number }>;
  run: { status: "jamais" | "en_cours" | "termine" | "echec"; progress: number };
  /** Curseur de lecture : secondes UTC, ou null quand tout le résultat est affiché. */
  playhead: number | null;
}

export type CommandStep = "lancement" | "verification" | "actif";
export interface Command {
  id: string;
  kind: "demarrer" | "pause_achats" | "reprendre_achats" | "arreter" | "tout_vendre";
  requestedAt: number;
  status: "en_cours" | "constatee" | "echouee";
  /** Étapes du démarrage, cochées seulement quand elles sont constatées. */
  steps?: { step: CommandStep; status: "attente" | "en_cours" | "ok" | "echec"; detail?: string }[];
  error?: string;
}

export interface Instance {
  id: string;
  name: string;
  mode: Mode;
  /** Fixé à la création, comme le mode : seules les stratégies de ce provider sont utilisables. */
  provider: ProviderId;
  /** Instance de test dont celle-ci est la copie réelle. */
  promotedFrom?: string;
  keyId: string | null;
  currency: string;
  pairs: PairConfig[];
  automationIds: string[];
  startBalance: number;
  wanted: WantedState;
  observed: ObservedState;
  /** Secondes UTC de la dernière observation du bot ; sert à afficher l'âge et « périmé ». */
  observedAt: number;
  startedAt: number | null;
  versions: InstanceVersion[];
  command: Command | null;
  backtest?: BacktestConfig;
  /** Ajouté par la couche de données : intervalles où les achats sont fermés (pause, arrêt) ; `to` null = en cours. */
  entryPauses: { from: number; to: number | null }[];
  /** Ajouté : positions fermées à la main (heure, prix) ou laissées ouvertes sans bot (null), par id de trade. */
  manualExits: Record<string, { time: number; price: number } | null>;
  /** Ajouté : commandes et alertes consignées au journal. */
  events: LogEntry[];
}

export interface PairStats {
  trades: number;
  wins: number;
  losses: number;
  winRate: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  expectancy: number;
  best: number;
  worst: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  maxDrawdownPct: number;
  currentDrawdownPct: number;
  exposurePct: number;
  /** Les mêmes, dans la devise du compte. */
  maxDrawdown: number;
  currentDrawdown: number;
  exposure: number;
  openPositions: number;
  avgDurationSec: number;
  fees: number;
  refusedEntries: number;
  exitCauses: Partial<Record<ExitCause, number>>;
  /** Résultat encaissé (trades terminés, net de frais) et en cours (positions ouvertes). */
  realized: number;
  realizedPct: number;
  unrealized: number;
  unrealizedPct: number;
  balance: number;
  /** Courbe du solde, pour l'onglet « Tout ». */
  equity: { time: number; value: number }[];
}

/** Rôles de couleur personnalisables (valeurs CSS). */
export interface ColorRoles {
  gain: string;
  perte: string;
  action: string;
  bougieHausse: string;
  bougieBaisse: string;
  modeTest: string;
  modeReel: string;
  modeBacktest: string;
}
