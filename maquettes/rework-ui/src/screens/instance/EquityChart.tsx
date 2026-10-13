import { useEffect, useRef, useState } from "react";
import { BaselineSeries, ColorType, CrosshairMode, createChart, type IChartApi, type IPriceLine, type ISeriesApi, type Time, type UTCTimestamp } from "lightweight-charts";
import { css, readPalette, watchTheme, type Palette } from "../../chart/colors";
import { dateTime, money, price, signedMoney, signedPct } from "../../lib/format";

interface Props { data: { time: number; value: number }[]; start: number; currency: string; stale: boolean }
interface Tip { x: number; time: number; value: number }

function paint(chart: IChartApi, series: ISeriesApi<"Baseline">, p: Palette) {
  chart.applyOptions({
    layout: { background: { type: ColorType.Solid, color: css(p.surface) }, textColor: css(p.mute), fontFamily: p.font, fontSize: 11 },
    grid: { vertLines: { color: css(p.line, 0.18) }, horzLines: { color: css(p.line, 0.18) } },
    crosshair: { vertLine: { color: css(p.mute, 0.6), labelBackgroundColor: css(p.line) }, horzLine: { color: css(p.mute, 0.6), labelBackgroundColor: css(p.line) } },
    rightPriceScale: { borderColor: css(p.line) }, timeScale: { borderColor: css(p.line) },
  });
  // Aplat (pas de dégradé) : au-dessus du départ en couleur de gain, en dessous en couleur de perte.
  series.applyOptions({
    topLineColor: css(p.gain), topFillColor1: css(p.gain, 0.16), topFillColor2: css(p.gain, 0.16),
    bottomLineColor: css(p.loss), bottomFillColor1: css(p.loss, 0.16), bottomFillColor2: css(p.loss, 0.16),
  });
}

/** Courbe du solde de l'instance, avec la base au solde de départ. API vérifiée dans lightweight-charts 5.2.1 (BaselineSeries, baseValue). */
export function EquityChart({ data, start, currency, stale }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<{ chart: IChartApi; series: ISeriesApi<"Baseline">; line: IPriceLine | null } | null>(null);
  const [tip, setTip] = useState<Tip | null>(null);

  useEffect(() => {
    const el = host.current!;
    const chart = createChart(el, {
      autoSize: false, width: el.clientWidth, height: el.clientHeight, crosshair: { mode: CrosshairMode.Magnet },
      localization: { locale: "fr-CA", timeFormatter: (t: Time) => dateTime(t as number), priceFormatter: price },
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    const series = chart.addSeries(BaselineSeries, { baseValue: { type: "price", price: start }, lineWidth: 2, priceLineVisible: false });
    api.current = { chart, series, line: null };
    paint(chart, series, readPalette(el));
    const ro = new ResizeObserver(() => chart.resize(el.clientWidth, el.clientHeight));
    ro.observe(el);
    const stop = watchTheme(() => paint(chart, series, readPalette(el)));
    chart.subscribeCrosshairMove((e) => {
      const v = e.seriesData.get(series);
      if (!e.point || e.time === undefined || !v || !("value" in v)) { setTip(null); return; }
      setTip({ x: e.point.x, time: e.time as number, value: v.value });
    });
    return () => { stop(); ro.disconnect(); chart.remove(); api.current = null; };
  }, []);

  useEffect(() => {
    const a = api.current;
    if (!a) return;
    a.series.applyOptions({ baseValue: { type: "price", price: start } });
    if (a.line) a.series.removePriceLine(a.line);
    a.line = a.series.createPriceLine({ price: start, color: css(readPalette(host.current!).mute, 0.7), lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "Départ" });
    a.series.setData(data.map((d) => ({ time: d.time as UTCTimestamp, value: d.value })));
    a.chart.timeScale().fitContent();
  }, [data, start]);

  const w = host.current?.clientWidth ?? 0;
  const diff = tip ? tip.value - start : 0;
  return (
    <div className={`in-eq-plot ${stale ? "stale" : ""}`}>
      <div ref={host} className="in-eq-canvas" role="img" aria-label="Courbe du solde de l'instance" />
      {(data.length < 2 || data.every((d) => d.value === start)) && <div className="empty in-eq-empty" role="status">Pas encore de courbe : aucune transaction encore constatée.</div>}
      {tip && (
        <div className="tc-tip" style={{ top: 12, ...(tip.x > w - 240 ? { right: w - tip.x + 14 } : { left: tip.x + 14 }) }} role="presentation">
          <div className="tc-tip-time">{dateTime(tip.time)}</div>
          <dl className="tc-kv">
            <dt>Solde</dt><dd>{money(tip.value, currency)}</dd>
            <dt>Depuis le départ</dt>
            <dd className={Math.round(Math.abs(diff) * 100) === 0 ? "" : diff > 0 ? "up" : "dn"}>{signedMoney(diff, currency)} · {signedPct((diff / start) * 100)}</dd>
          </dl>
        </div>
      )}
    </div>
  );
}
