// Providers : le moteur de trading d'une instance. Chaque provider a son propre format de stratégie ;
// seul Freqtrade est pris en charge (SPEC §7, annexes B et C). Les suivants sont nommés au SPEC §13.
import type { ProviderId } from "./types";

export interface Provider { id: ProviderId; name: string; ready: boolean; note: string }
export const PROVIDERS: Provider[] = [
  { id: "freqtrade", name: "Freqtrade", ready: true, note: "Bot open source, crypto au comptant (spot)." },
  { id: "nautilus", name: "NautilusTrader", ready: false, note: "Prévu après la V1 : pas encore pris en charge." },
];
export const providerName = (id: ProviderId): string => PROVIDERS.find((p) => p.id === id)?.name ?? id;

/** Gabarit repris de strategies/sma-cross/SmaCross.py : exemple d'intégration, sans prétention de rentabilité. */
export const ftTemplate = (className: string): string => `from control_plane import ControlPlaneStrategy
from pandas import DataFrame


class ${className}(ControlPlaneStrategy):
    startup_candle_count = 30

    def _param(self, name: str, default: int) -> int:
        return int(self.config.get("centrade_params", {}).get(name, default))

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["fast"] = dataframe["close"].rolling(self._param("fast", 10)).mean()
        dataframe["slow"] = dataframe["close"].rolling(self._param("slow", 30)).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        crossed_up = (dataframe["fast"] > dataframe["slow"]) & (
            dataframe["fast"].shift(1) <= dataframe["slow"].shift(1)
        )
        dataframe.loc[crossed_up, "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        crossed_down = (dataframe["fast"] < dataframe["slow"]) & (
            dataframe["fast"].shift(1) >= dataframe["slow"].shift(1)
        )
        dataframe.loc[crossed_down, "exit_long"] = 1
        return dataframe
`;

export const ftClassName = (code: string): string | null => /^class\s+([A-Za-z_]\w*)\s*\(/m.exec(code)?.[1] ?? null;

// Listes reprises de packages/adapters/freqtrade/centrade_freqtrade/checks.py.
const HOOKS = "confirm_trade_entry|confirm_trade_exit|adjust_trade_position|adjust_entry_price|adjust_order_price|adjust_exit_price|leverage";
const IMPOSED = "stoploss|trailing_stop|minimal_roi|order_types|stake_currency|stake_amount|max_open_trades|position_adjustment_enable|unfilledtimeout";
const ALLOWED_IMPORT = /^(control_plane|pandas|numpy|talib|math|datetime|typing|functools|freqtrade\.strategy|freqtrade\.vendor\.qtpylib)(\.|$)/;

/** Contrôles statiques du registre, rejoués en clair pour l'opérateur.
 *  shortcut: expressions régulières, pas d'AST ; le vrai contrôle est checks.py côté serveur, à brancher au portage. */
export function ftChecks(code: string): { label: string; ok: boolean }[] {
  const src = code.replace(/#.*$/gm, "");
  const imports = [...src.matchAll(/^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))/gm)].map((m) => m[1] ?? m[2]);
  return [
    { label: "la classe hérite de ControlPlaneStrategy", ok: /^from\s+control_plane\s+import\s+ControlPlaneStrategy\s*$/m.test(src) && /^class\s+\w+\s*\(\s*ControlPlaneStrategy\s*\)\s*:/m.test(src) },
    { label: "aucun hook de la plateforme n'est redéfini", ok: !new RegExp(`\\bdef\\s+(${HOOKS})\\b`).test(src) },
    { label: "aucun import hors de la liste admise (ni réseau, ni processus)", ok: imports.every((m) => ALLOWED_IMPORT.test(m)) && !/\b(__import__|eval|exec|open)\s*\(/.test(src) },
    { label: "les sorties et les mises ne sont pas fixées dans le code", ok: !new RegExp(`^\\s*(self\\.)?(${IMPOSED})\\w*\\s*=`, "m").test(src) },
  ];
}
