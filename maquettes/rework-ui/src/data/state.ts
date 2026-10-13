import type { Automation, ApiKey, ColorRoles, Instance, PairStats, Strategy } from "./types";

export interface State {
  /** « Maintenant » simulé, secondes UTC. */
  cursor: number;
  instances: Instance[];
  keys: ApiKey[];
  strategies: Strategy[];
  automations: Automation[];
  killSwitch: boolean;
  /** null = couleurs du thème. */
  colors: ColorRoles | null;
  enabledIndicators: string[];
  demo: { failNextStart: boolean; frozen: boolean };
}

export const DEFAULT_INDICATORS: (keyof PairStats)[] = [
  "winRate", "profitFactor", "maxDrawdownPct", "openPositions", "fees", "avgDurationSec",
];
