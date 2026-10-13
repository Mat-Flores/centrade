import { EPOCH } from "./sim";
import { DEFAULT_INDICATORS, type State } from "./state";
import { ftTemplate } from "./providers";
import type { ApiKey, Automation, BacktestConfig, Instance, Strategy } from "./types";

const DAY = 86400;
export const INITIAL_CURSOR = EPOCH + 24 * DAY;

const keys = (): ApiKey[] => [
  { id: "key-binance-test", name: "Binance, compte test", exchange: "Binance", env: "test", currency: "USDT", createdAt: EPOCH + 2 * DAY, hint: "…k3F9" },
  { id: "key-binance-prod", name: "Binance, compte principal", exchange: "Binance", env: "production", currency: "USDT", createdAt: EPOCH + 3 * DAY, hint: "…q81Z" },
  { id: "key-kraken-test", name: "Kraken, compte test", exchange: "Kraken", env: "test", currency: "USDT", createdAt: EPOCH + 5 * DAY, hint: "…7mWd" },
];

const ft = (className: string) => ({ provider: "freqtrade" as const, className, code: ftTemplate(className), version: 1, trailing: false });

const strategies = (): Strategy[] => [
  {
    ...ft("SmaCross"), version: 3, id: "strat-croisement", name: "Croisement de moyennes", timeframe: "1h", extraTimeframes: ["4h"],
    stopLossPct: 3, takeProfitPct: 6, params: { rapide: 9, lente: 21 },
    description: "Exemple volontairement banal : achète quand la moyenne rapide passe au-dessus de la lente. Ce n'est pas un conseil et rien ne garantit un gain.",
  },
  {
    ...ft("MeanRevert"), id: "strat-retour", name: "Retour à la moyenne", timeframe: "15m", extraTimeframes: ["1h"],
    stopLossPct: 2, takeProfitPct: 3, params: { rapide: 5, lente: 13 },
    description: "Exemple volontairement banal, à unité de temps courte. Il sert à montrer l'interface, pas à gagner de l'argent. Ce n'est pas un conseil.",
  },
  {
    ...ft("SlowTrend"), version: 2, id: "strat-tendance", name: "Suivi de tendance lent", timeframe: "4h", extraTimeframes: ["1j"],
    stopLossPct: 5, takeProfitPct: 12, params: { rapide: 12, lente: 34 },
    description: "Exemple volontairement banal : suit les tendances longues, avec peu de trades. Ce n'est pas un conseil et le passé ne prédit rien.",
  },
];

const automations = (): Automation[] => [
  { id: "auto-alerte-perte", kind: "alerte", name: "Prévenir sur Telegram si la perte du jour dépasse 2 %", description: "Envoie un message sur Telegram. Ne change rien au comportement du bot." },
  { id: "auto-rapport", kind: "alerte", name: "Rapport quotidien à 18 h", description: "Envoie chaque jour un résumé des trades et du solde." },
  { id: "auto-pause-perte", kind: "protection", name: "Mettre en pause les achats si la perte du jour dépasse 3 %", description: "Le bot n'achète plus pour le reste de la journée, mais continue de gérer ses positions." },
  { id: "auto-tout-vendre", kind: "protection", name: "Tout vendre si la plus forte baisse dépasse 10 %", description: "Vend toutes les positions au prix du marché quand le solde recule de 10 % depuis son sommet." },
  { id: "auto-weekend", kind: "planification", name: "Mettre en pause les achats le week-end", description: "Ferme les achats du samedi au dimanche soir. Les ventes continuent." },
  { id: "auto-agent", kind: "agent", name: "Analyse hebdomadaire (propose, ne décide pas)", description: "Un agent relit la semaine et propose des changements. Il n'en applique aucun." },
];

const base = { provider: "freqtrade" as const, automationIds: [] as string[], command: null, entryPauses: [], manualExits: {}, events: [] };

const backtestDefaults = (): BacktestConfig => ({
  from: EPOCH, to: EPOCH + 14 * DAY, feePct: 0.1, slippagePct: 0.05, data: {},
  run: { status: "jamais", progress: 0 }, playhead: null,
});

export const newBacktestConfig = backtestDefaults;

const instances = (): Instance[] => {
  const swingStart = INITIAL_CURSOR - (3 * DAY + 4 * 3600);
  const prodStart = INITIAL_CURSOR - 9 * DAY;
  const doneStart = (at: number) => ({
    id: "cmd-seed", kind: "demarrer" as const, requestedAt: at, status: "constatee" as const,
    steps: (["lancement", "verification", "actif"] as const).map((step) => ({ step, status: "ok" as const })),
  });
  return [
    {
      ...base, id: "inst-swing", name: "Swing majors", mode: "test", keyId: "key-binance-test", currency: "USDT",
      pairs: [
        { pair: "BTC/USDT", strategyId: "strat-croisement" }, { pair: "ETH/USDT", strategyId: "strat-croisement" },
        { pair: "SOL/USDT", strategyId: "strat-retour" }, { pair: "ADA/USDT", strategyId: "strat-retour" },
      ],
      automationIds: ["auto-alerte-perte", "auto-pause-perte"],
      startBalance: 2000, wanted: "actif", observed: "actif", observedAt: INITIAL_CURSOR, startedAt: swingStart,
      versions: [
        { n: 1, createdAt: swingStart - 6 * 3600, summary: "Création de l'instance" },
        { n: 2, createdAt: swingStart - 5 * 3600, summary: "Ajout de BTC/USDT avec Croisement de moyennes" },
        { n: 3, createdAt: swingStart - 4 * 3600, summary: "Ajout de ETH/USDT avec Croisement de moyennes" },
        { n: 4, createdAt: swingStart - 3 * 3600, summary: "Ajout de SOL/USDT et ADA/USDT avec Retour à la moyenne" },
      ],
      command: doneStart(swingStart),
      events: [{ id: "ev-swing-start", time: swingStart + 4, kind: "commande", text: "Démarrage constaté, le bot est actif" }],
    },
    {
      ...base, id: "inst-prod", name: "Prod prudente", mode: "reel", promotedFrom: "inst-swing", keyId: "key-binance-prod", currency: "USDT",
      pairs: [{ pair: "BTC/USDT", strategyId: "strat-croisement" }, { pair: "ETH/USDT", strategyId: "strat-croisement" }],
      automationIds: ["auto-pause-perte", "auto-tout-vendre"],
      startBalance: 5000, wanted: "actif", observed: "actif", observedAt: INITIAL_CURSOR, startedAt: prodStart,
      versions: [{ n: 1, createdAt: prodStart - 3600, summary: "Copie réelle de Swing majors (version 4)" }],
      command: doneStart(prodStart),
      events: [{ id: "ev-prod-start", time: prodStart + 4, kind: "commande", text: "Démarrage constaté, le bot est actif" }],
    },
    {
      ...base, id: "inst-essai", name: "Essai tendance", mode: "backtest", keyId: null, currency: "USDT",
      pairs: [
        { pair: "BTC/USDT", strategyId: "strat-croisement" }, { pair: "ETH/USDT", strategyId: "strat-croisement" },
        { pair: "LINK/USDT", strategyId: "strat-croisement" },
      ],
      startBalance: 2000, wanted: "arrete", observed: "arrete", observedAt: INITIAL_CURSOR, startedAt: null,
      versions: [{ n: 1, createdAt: INITIAL_CURSOR - 2 * DAY, summary: "Création de l'instance" }],
      backtest: {
        ...backtestDefaults(), to: EPOCH + 21 * DAY,
        data: {
          "BTC/USDT": { status: "completes", progress: 100 },
          "ETH/USDT": { status: "partielles", progress: 60 },
          "LINK/USDT": { status: "absentes", progress: 0 },
        },
      },
    },
    {
      ...base, id: "inst-brouillon", name: "Brouillon altcoins", mode: "test", keyId: null, currency: "USDT",
      pairs: [{ pair: "DOGE/USDT", strategyId: "strat-retour" }],
      startBalance: 1000, wanted: "arrete", observed: "arrete", observedAt: INITIAL_CURSOR, startedAt: null,
      versions: [{ n: 1, createdAt: INITIAL_CURSOR - DAY, summary: "Création de l'instance" }],
    },
  ];
};

export function seedState(): State {
  return {
    cursor: INITIAL_CURSOR, instances: instances(), keys: keys(), strategies: strategies(), automations: automations(),
    killSwitch: false, colors: null, enabledIndicators: [...DEFAULT_INDICATORS],
    demo: { failNextStart: false, frozen: false },
  };
}
