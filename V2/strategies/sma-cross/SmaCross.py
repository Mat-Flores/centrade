"""Crossover of two simple moving averages. Integration example, with no claim of
profitability (SPEC §0.6): it serves to exercise the registry, deployment and exits."""

from control_plane import ControlPlaneStrategy
from pandas import DataFrame


class SmaCross(ControlPlaneStrategy):
    timeframe = "5m"
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
