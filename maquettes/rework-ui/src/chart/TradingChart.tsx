import { useEffect, useMemo, useRef, useState } from "react";
import {
  type AutoscaleInfoProvider, CandlestickSeries, ColorType, CrosshairMode, TickMarkType, createChart, createSeriesMarkers,
  type IChartApi, type ISeriesApi, type ISeriesMarkersPluginApi, type SeriesMarker, type Time, type UTCTimestamp,
} from "lightweight-charts";
import { TIMEFRAMES, type Candle, type Timeframe, type Trade } from "../data/types";
import { SEEN_TIP, age, clock, dateTime, duration, price, seen, signedMoney, signedPct, tfLabel } from "../lib/format";
import { css, readPalette, watchTheme, type Palette } from "./colors";
import { CAUSE_FR, candleIndexAt, overlaps } from "./geometry";
import { TradeOverlay } from "./overlay";
import "./chart.css";

export interface TradingChartProps {
  candles: Candle[];
  trades: Trade[];
  timeframe: Timeframe;
  tradedTimeframes: Timeframe[];
  onTimeframe: (tf: Timeframe) => void;
  currency: string;
  simulated: boolean;
  observedAgeSec: number;
  stale: boolean;
  selectedTradeId?: string | null;
  onSelectTrade?: (id: string | null) => void;
  emptyMessage?: string;
  /** Centre l'échelle de temps sur ce trade ; `focusNonce` permet de recentrer sur le même trade. */
  focusTradeId?: string | null;
  focusNonce?: number;
  onFocused?: () => void;
}

interface Tip { x: number; y: number; time: number; c: { open: number; high: number; low: number; close: number } | null; trade: Trade | null }

const TZ = "America/Toronto";
const dayFmt = new Intl.DateTimeFormat("fr-CA", { timeZone: TZ, day: "numeric", month: "short" });
const monthFmt = new Intl.DateTimeFormat("fr-CA", { timeZone: TZ, month: "short" });
const yearFmt = new Intl.DateTimeFormat("fr-CA", { timeZone: TZ, year: "numeric" });
const VISIBLE_BARS = 110;

function tick(time: Time, type: TickMarkType): string {
  const d = new Date((time as number) * 1000);
  if (type === TickMarkType.Year) return yearFmt.format(d);
  if (type === TickMarkType.Month) return monthFmt.format(d);
  if (type === TickMarkType.DayOfMonth) return dayFmt.format(d);
  return clock(time as number);
}

function applyPalette(chart: IChartApi, series: ISeriesApi<"Candlestick">, p: Palette): void {
  chart.applyOptions({
    layout: { background: { type: ColorType.Solid, color: css(p.surface) }, textColor: css(p.mute), fontFamily: p.font, fontSize: 11 },
    grid: { vertLines: { color: css(p.line, 0.18) }, horzLines: { color: css(p.line, 0.18) } },
    crosshair: { vertLine: { color: css(p.mute, 0.6), labelBackgroundColor: css(p.line) }, horzLine: { color: css(p.mute, 0.6), labelBackgroundColor: css(p.line) } },
    rightPriceScale: { borderColor: css(p.line) },
    timeScale: { borderColor: css(p.line) },
  });
  series.applyOptions({
    upColor: css(p.up), downColor: css(p.down), wickUpColor: css(p.up), wickDownColor: css(p.down), borderVisible: false,
  });
}

export function TradingChart(props: TradingChartProps): JSX.Element {
  const { candles, trades, timeframe, tradedTimeframes, onTimeframe, currency, simulated, observedAgeSec, stale, selectedTradeId, emptyMessage, focusTradeId, focusNonce } = props;
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<{ chart: IChartApi; series: ISeriesApi<"Candlestick">; overlay: TradeOverlay; markers: ISeriesMarkersPluginApi<Time> } | null>(null);
  const live = useRef(props); live.current = props; // callbacks et sélection lus par les abonnements du graphique
  const hover = useRef<string | null>(null);
  const prev = useRef<{ candles: Candle[]; tf: Timeframe } | null>(null);
  const [palette, setPalette] = useState<Palette | null>(null);
  const [tip, setTip] = useState<Tip | null>(null);

  // Création unique, nettoyage au démontage.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const pal = readPalette(el);
    const chart = createChart(el, {
      autoSize: false, width: el.clientWidth, height: el.clientHeight,
      crosshair: { mode: CrosshairMode.Magnet }, // attributionLogo : laissé à true (licence Apache-2.0 + NOTICE TradingView)
      layout: { attributionLogo: true },
      localization: { locale: "fr-CA", timeFormatter: (t: Time) => dateTime(t as number), priceFormatter: price },
      timeScale: { timeVisible: true, secondsVisible: false, rightOffset: 6, tickMarkFormatter: (t: Time, ty: TickMarkType) => tick(t, ty) },
    });
    // Les niveaux de stop-loss et de take-profit des positions ouvertes (et du trade choisi) restent dans l'échelle.
    const series = chart.addSeries(CandlestickSeries, {
      autoscaleInfoProvider: ((base) => {
        const r = base();
        if (!r || !r.priceRange) return r;
        const { trades: ts, selectedTradeId: sel } = live.current;
        let { minValue, maxValue } = r.priceRange;
        for (const t of ts) {
          if (t.exitTime !== undefined && t.id !== sel) continue;
          minValue = Math.min(minValue, t.stopLoss, t.takeProfit);
          maxValue = Math.max(maxValue, t.stopLoss, t.takeProfit);
        }
        return { ...r, priceRange: { minValue, maxValue } };
      }) as AutoscaleInfoProvider,
    });
    const overlay = new TradeOverlay();
    series.attachPrimitive(overlay);
    const markers = createSeriesMarkers(series, []);
    api.current = { chart, series, overlay, markers };
    applyPalette(chart, series, pal); overlay.setPalette(pal); setPalette(pal);

    const ro = new ResizeObserver(() => chart.resize(el.clientWidth, el.clientHeight));
    ro.observe(el);
    const stopTheme = watchTheme(() => { const p = readPalette(el); applyPalette(chart, series, p); overlay.setPalette(p); setPalette(p); });

    chart.subscribeCrosshairMove((e) => {
      const pt = e.point;
      const t = pt ? overlay.hit(pt.x, pt.y) : null;
      if (hover.current !== (t?.id ?? null)) { hover.current = t?.id ?? null; overlay.setHighlight(live.current.selectedTradeId ?? null, hover.current); }
      el.style.cursor = t ? "pointer" : "";
      if (!pt || e.time === undefined) { setTip(null); return; }
      const c = e.seriesData.get(series);
      setTip({ x: pt.x, y: pt.y, time: e.time as number, trade: t, c: c && "open" in c ? c : null });
    });
    chart.subscribeClick((e) => {
      const t = e.point ? overlay.hit(e.point.x, e.point.y) : null;
      live.current.onSelectTrade?.(t?.id ?? null);
    });
    return () => { stopTheme(); ro.disconnect(); markers.detach(); chart.remove(); api.current = null; };
  }, []);

  // Données : mise à jour incrémentale, ou setData quand l'unité de temps ou la série change.
  useEffect(() => {
    const a = api.current;
    if (!a) return;
    const old = prev.current;
    const n = candles.length;
    const grew = old && old.tf === timeframe && n > 0 && old.candles.length > 0 && old.candles[0].time === candles[0].time;
    const data = (c: Candle) => ({ ...c, time: c.time as UTCTimestamp });
    if (grew && (n === old.candles.length || n === old.candles.length + 1)) {
      if (n > old.candles.length) a.series.update(data(candles[n - 2]));
      a.series.update(data(candles[n - 1]));
    } else {
      a.series.setData(candles.map(data));
      if (n > 0) a.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - VISIBLE_BARS), to: n + 6 });
    }
    prev.current = { candles, tf: timeframe };
  }, [candles, timeframe]);

  // Repères d'achat et de vente (forme + texte), et zones.
  useEffect(() => {
    const a = api.current;
    if (!a || !palette) return;
    const col = css(palette.action);
    const at = (t: number) => (candles.length ? (candles[candleIndexAt(candles, t)].time as UTCTimestamp) : (t as UTCTimestamp));
    const m: SeriesMarker<Time>[] = [];
    for (const t of trades.filter((x) => overlaps(candles, x))) {
      const size = t.id === selectedTradeId ? 2 : 1.2;
      m.push({ time: at(t.entryTime), position: "belowBar", shape: "arrowUp", color: col, text: "Achat", size, id: `${t.id}:in` });
      if (t.exitTime !== undefined) m.push({ time: at(t.exitTime), position: "aboveBar", shape: "arrowDown", color: col, text: "Vente", size, id: `${t.id}:out` });
    }
    a.markers.setMarkers(m.sort((x, y) => (x.time as number) - (y.time as number)));
    a.overlay.set(trades, candles, currency);
    a.overlay.setHighlight(selectedTradeId ?? null, hover.current);
    a.chart.priceScale("right").applyOptions({ autoScale: true }); // relit l'échelle avec les nouveaux niveaux
  }, [trades, candles, currency, selectedTradeId, palette]);

  // Centrage sur un trade : sa durée occupe ~40 % de la largeur visible, soit ~30 % de marge de chaque côté.
  useEffect(() => {
    const a = api.current;
    if (!a || !focusTradeId || !focusNonce || candles.length === 0) return;
    const t = trades.find((x) => x.id === focusTradeId);
    if (!t) return;
    const i0 = candleIndexAt(candles, t.entryTime);
    const i1 = t.exitTime !== undefined ? candleIndexAt(candles, t.exitTime) : candles.length - 1;
    const total = Math.max(14, (i1 - i0) / 0.4), mid = (i0 + i1) / 2;
    a.chart.timeScale().setVisibleLogicalRange({ from: mid - total / 2, to: mid + total / 2 });
    a.overlay.pulse(t.id);
    live.current.onFocused?.();
  }, [focusNonce, focusTradeId]);

  const shown = useMemo(() => trades.filter((t) => overlaps(candles, t)), [trades, candles]);
  const ageText = stale ? `Périmé : aucune réponse depuis ${age(observedAgeSec).replace("il y a ", "")}` : seen(observedAgeSec);

  return (
    <div className="tc">
      <div className="tc-head">
        <div className="tc-tfs pills" role="group" aria-label="Timeframe">
          {TIMEFRAMES.map((tf) => {
            const traded = tradedTimeframes.includes(tf);
            return (
              <button key={tf} type="button" aria-pressed={tf === timeframe} className="pill" data-tip={traded ? "Timeframe tradé par le bot" : undefined} onClick={() => onTimeframe(tf)}>
                {traded && <i className="pill-dot" aria-hidden="true" />}
                {tfLabel(tf)}
                {traded && <span className="tc-sr"> tradée par le bot</span>}
              </button>
            );
          })}
        </div>
        <div className="tc-tags">
          {simulated && <span className="tag-sim">Simulé</span>}
          <span className={`xs ${stale ? "dn" : "dim"}`} data-tip={SEEN_TIP}>{ageText}</span>
        </div>
      </div>
      <div className={`tc-plot${stale ? " is-stale" : ""}`}>
        <div ref={host} className="tc-canvas" role="img" aria-label={`Graphique en bougies, ${shown.length} trade(s) visible(s)`} />
        {candles.length === 0 && <div className="tc-empty" role="status">{emptyMessage ?? "Aucune donnée à afficher."}</div>}
        {tip && candles.length > 0 && <Tooltip tip={tip} currency={currency} host={host.current} />}
      </div>
      <table className="tc-sr">
        <caption>Trades visibles sur le graphique</caption>
        <thead><tr><th>Achat</th><th>Prix d'achat</th><th>Vente</th><th>Prix de vente</th><th>Résultat</th></tr></thead>
        <tbody>
          {shown.map((t) => (
            <tr key={t.id}>
              <td>{dateTime(t.entryTime)}</td><td>{price(t.entryPrice)}</td>
              <td>{t.exitTime !== undefined ? dateTime(t.exitTime) : "En cours"}</td><td>{t.exitPrice !== undefined ? price(t.exitPrice) : "—"}</td>
              <td>{signedPct(t.pnlPct)} · {signedMoney(t.pnl, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Tooltip({ tip, currency, host }: { tip: Tip; currency: string; host: HTMLDivElement | null }): JSX.Element {
  const w = host?.clientWidth ?? 0;
  const t = tip.trade;
  const style = { top: tip.y + 14, ...(tip.x > w - 260 ? { right: w - tip.x + 14 } : { left: tip.x + 14 }) };
  return (
    <div className="tc-tip" style={style} role="presentation">
      <div className="tc-tip-time">{dateTime(tip.time)}</div>
      {tip.c && (
        <dl className="tc-ohlc">
          <dt>O</dt><dd>{price(tip.c.open)}</dd><dt>H</dt><dd>{price(tip.c.high)}</dd>
          <dt>B</dt><dd>{price(tip.c.low)}</dd><dt>F</dt><dd>{price(tip.c.close)}</dd>
        </dl>
      )}
      {t && (
        <div className="tc-tip-trade">
          <strong>{t.exitTime === undefined ? "Trade en cours" : "Trade terminé"}</strong>
          <dl className="tc-kv">
            <dt>Achat</dt><dd>{price(t.entryPrice)}</dd>
            {t.exitPrice !== undefined && t.exitTime !== undefined && (<><dt>Vente</dt><dd>{price(t.exitPrice)}</dd></>)}
            <dt>{t.exitTime === undefined ? "En cours" : "Résultat"}</dt><dd>{signedPct(t.pnlPct)} · {signedMoney(t.pnl, currency)}</dd>
            {t.exitCause && (<><dt>Cause</dt><dd>{CAUSE_FR[t.exitCause]}</dd></>)}
            <dt>Durée</dt><dd>{duration((t.exitTime ?? tip.time) - t.entryTime)}</dd>
          </dl>
        </div>
      )}
    </div>
  );
}
