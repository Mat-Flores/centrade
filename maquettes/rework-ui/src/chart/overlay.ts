// Primitive de série : zones, trajets, niveaux de sortie et étiquettes de résultat, dessinés sur le canvas.
// API vérifiée dans lightweight-charts@5.2.1 typings.d.ts : ISeriesPrimitive, IPrimitivePaneView (zOrder, renderer),
// SeriesAttachedParameter (chart, series, requestUpdate), timeScale().timeToCoordinate, series.priceToCoordinate.
import gsap from "gsap";
import type { IChartApi, ISeriesApi, ISeriesPrimitive, IPrimitivePaneView, IPrimitivePaneRenderer, SeriesAttachedParameter, Time, UTCTimestamp } from "lightweight-charts";
import type { Candle, Trade } from "../data/types";
import { css, type Palette } from "./colors";
import { pathPoints, pickRect, type Rect } from "./geometry";
import { price, signedMoney, signedPct } from "../lib/format";

interface Laid {
  id: string; trade: Trade; open: boolean; rect: Rect; xr: number; // xr : fin des niveaux (bord droit si ouvert)
  path: { x: number; y: number }[]; tp: number; sl: number; label: string;
}
type Tone = "gain" | "loss" | "action";
type Target = Parameters<IPrimitivePaneRenderer["draw"]>[0];

const reducedMotion = (): boolean => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export class TradeOverlay implements ISeriesPrimitive<Time> {
  private p: SeriesAttachedParameter<Time> | null = null;
  private trades: Trade[] = [];
  private candles: Candle[] = [];
  private pal: Palette | null = null;
  private laid: Laid[] = [];
  private prevOpen: Set<string> | null = null;
  private reveal = new Map<string, number>();
  private pulses = new Map<string, number>();
  private currency = "";
  selectedId: string | null = null;
  hoverId: string | null = null;

  attached(param: SeriesAttachedParameter<Time>): void { this.p = param; }
  detached(): void { gsap.killTweensOf(this.reveal); this.pulses.clear(); this.p = null; }

  set(trades: Trade[], candles: Candle[], currency: string): void {
    // Un trade qui passe d'ouvert à fermé : sa zone et son étiquette apparaissent en douceur.
    const closedNow = trades.filter((t) => t.exitTime !== undefined && this.prevOpen?.has(t.id));
    this.prevOpen = new Set(trades.filter((t) => t.exitTime === undefined).map((t) => t.id));
    this.trades = trades; this.candles = candles; this.currency = currency;
    for (const t of closedNow) this.animateIn(t.id);
    this.p?.requestUpdate();
  }
  setPalette(pal: Palette): void { this.pal = pal; this.p?.requestUpdate(); }
  setHighlight(selected: string | null, hover: string | null): void {
    this.selectedId = selected; this.hoverId = hover; this.p?.requestUpdate();
  }

  /** Pulsation brève de l'étiquette d'un trade (≤ 400 ms). */
  pulse(id: string): void {
    if (reducedMotion()) return;
    const state = { v: 1 };
    this.pulses.set(id, 1);
    gsap.to(state, {
      v: 0, duration: 0.4, ease: "power2.out",
      onUpdate: () => { this.pulses.set(id, state.v); this.p?.requestUpdate(); },
      onComplete: () => { this.pulses.delete(id); this.p?.requestUpdate(); },
    });
  }

  private animateIn(id: string): void {
    if (reducedMotion()) return;
    const state = { v: 0 };
    this.reveal.set(id, 0);
    gsap.to(state, {
      v: 1, duration: 0.35, ease: "power2.out",
      onUpdate: () => { this.reveal.set(id, state.v); this.p?.requestUpdate(); },
      onComplete: () => { this.reveal.delete(id); this.p?.requestUpdate(); },
    });
  }

  /** Trade sous le point (px du panneau) : zone, ou repère d'achat/vente proche. */
  hit(x: number, y: number): Trade | null {
    return pickRect(this.laid, x, y, 6)?.trade ?? null;
  }

  updateAllViews(): void {
    const p = this.p;
    if (!p) return;
    const ts = (p.chart as IChartApi).timeScale();
    const s = p.series as ISeriesApi<"Candlestick", Time>;
    const width = ts.width();
    const laid: Laid[] = [];
    for (const trade of this.trades) {
      const pts = pathPoints(this.candles, trade);
      if (pts.length === 0) continue;
      const path: { x: number; y: number }[] = [];
      for (const q of pts) {
        const x = ts.timeToCoordinate(q.time as UTCTimestamp), y = s.priceToCoordinate(q.price);
        if (x !== null && y !== null) path.push({ x, y });
      }
      if (path.length === 0) continue;
      const first = path[0], last = path[path.length - 1];
      if (Math.max(first.x, last.x) < 0 || Math.min(first.x, last.x) > width) continue; // hors de la fenêtre
      const open = trade.exitTime === undefined;
      const yTp = s.priceToCoordinate(trade.takeProfit), ySl = s.priceToCoordinate(trade.stopLoss);
      const label = open ? `En cours ${signedPct(trade.pnlPct)}` : `${signedPct(trade.pnlPct)} · ${signedMoney(trade.pnl, this.currency)}`;
      laid.push({
        id: trade.id, trade, open, path, label, tp: yTp ?? NaN, sl: ySl ?? NaN, xr: open ? width : last.x,
        rect: { x1: first.x, x2: last.x, y1: s.priceToCoordinate(trade.entryPrice) ?? first.y, y2: last.y },
      });
    }
    this.laid = laid;
  }

  private tone(l: Laid): Tone { return l.open ? "action" : l.trade.pnl >= 0 ? "gain" : "loss"; }

  private view(layer: "zone" | "top"): IPrimitivePaneView {
    return {
      zOrder: () => (layer === "zone" ? "bottom" : "top"),
      renderer: () => ({
        draw: (target: Target) => {
          if (!this.pal) return;
          const pal = this.pal;
          target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
            for (const l of this.laid) {
              const k = this.reveal.get(l.id) ?? 1;
              ctx.save();
              if (layer === "zone") this.zone(ctx, l, pal, k);
              else this.top(ctx, l, pal, k, mediaSize.width);
              ctx.restore();
            }
          });
        },
      }),
    };
  }
  private views = [this.view("zone"), this.view("top")];
  paneViews(): readonly IPrimitivePaneView[] { return this.views; }

  private zone(ctx: CanvasRenderingContext2D, l: Laid, pal: Palette, k: number): void {
    const c = pal[this.tone(l)];
    const strong = l.id === this.selectedId || l.id === this.hoverId;
    const { x1, x2, y1, y2 } = l.rect;
    ctx.globalAlpha = k;
    ctx.fillStyle = css(c, strong ? 0.26 : 0.15);
    ctx.fillRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1));
    if (l.id === this.selectedId) {
      ctx.strokeStyle = css(c, 0.8); ctx.lineWidth = 1;
      ctx.strokeRect(Math.min(x1, x2) + 0.5, Math.min(y1, y2) + 0.5, Math.abs(x2 - x1), Math.abs(y2 - y1));
    }
  }

  private top(ctx: CanvasRenderingContext2D, l: Laid, pal: Palette, k: number, paneW: number): void {
    const named = l.open || l.id === this.selectedId || l.id === this.hoverId;
    const x0 = l.path[0].x;
    // Niveaux de sortie, limités à la durée du trade.
    ctx.font = `11px ${pal.font}`; ctx.textBaseline = "bottom"; ctx.textAlign = "right";
    ctx.setLineDash([5, 4]); ctx.lineWidth = 1;
    ([["gain", l.tp, "Take-profit", l.trade.takeProfit], ["loss", l.sl, "Stop-loss", l.trade.stopLoss]] as const).forEach(([t, y, text, v]) => {
      if (Number.isNaN(y)) return;
      ctx.globalAlpha = named ? 0.9 : 0.5;
      ctx.strokeStyle = css(pal[t]);
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(l.xr, y); ctx.stroke();
      if (named) {
        const txt = `${text} ${price(v)}`, tx = Math.min(l.xr, paneW) - 4, tw = ctx.measureText(txt).width;
        ctx.globalAlpha = 0.85; ctx.fillStyle = css(pal.surface);
        ctx.fillRect(tx - tw - 3, y - 17, tw + 6, 15);
        ctx.globalAlpha = 1; ctx.fillStyle = css(pal[t]); ctx.fillText(txt, tx, y - 4);
      }
    });
    ctx.setLineDash([]);
    // Trajet des clôtures, en bleu par-dessus les bougies.
    ctx.globalAlpha = k;
    // Un liseré de la couleur du fond sous le trait bleu : le trajet reste lisible par-dessus les bougies.
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    const trace = () => { ctx.beginPath(); l.path.forEach((q, i) => (i ? ctx.lineTo(q.x, q.y) : ctx.moveTo(q.x, q.y))); ctx.stroke(); };
    ctx.strokeStyle = css(pal.surface); ctx.lineWidth = 7; trace();
    ctx.strokeStyle = css(pal.action); ctx.lineWidth = 4; trace();
    this.label(ctx, l, pal, k, paneW);
  }

  /** Étiquette détachée : trait de rappel jusqu'à une boîte au-dessus de la zone. */
  private label(ctx: CanvasRenderingContext2D, l: Laid, pal: Palette, k: number, paneW: number): void {
    const tone = this.tone(l), c = pal[tone];
    ctx.font = `${l.open ? "italic " : ""}600 12px ${pal.font}`; ctx.textBaseline = "middle"; ctx.textAlign = "center";
    const w = ctx.measureText(l.label).width + 14, h = 22;
    const ax = (l.rect.x1 + l.rect.x2) / 2, ay = Math.min(l.rect.y1, l.rect.y2, ...l.path.map((q) => q.y));
    const cx = Math.max(w / 2 + 2, Math.min(paneW - w / 2 - 2, ax));
    const top = Math.max(2, ay - 30 + (1 - k) * 6); // petite montée à l'apparition
    ctx.globalAlpha = k;
    ctx.strokeStyle = css(c, 0.8); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(cx, top + h); ctx.stroke();
    ctx.fillStyle = css(pal.surface, 0.94); ctx.strokeStyle = css(c);
    ctx.beginPath(); ctx.roundRect(cx - w / 2, top, w, h, 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = css(l.open ? pal.action : pal.ink);
    ctx.fillText(l.label, cx, top + h / 2 + 0.5);
    const pu = this.pulses.get(l.id);
    if (pu) {
      ctx.globalAlpha = pu; ctx.strokeStyle = css(pal.action); ctx.lineWidth = 2 + 4 * pu;
      ctx.beginPath(); ctx.roundRect(cx - w / 2 - 3 * pu, top - 3 * pu, w + 6 * pu, h + 6 * pu, 4); ctx.stroke();
    }
  }
}
