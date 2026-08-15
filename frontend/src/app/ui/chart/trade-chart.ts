import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  untracked,
  viewChild,
} from '@angular/core';
import {
  BarData,
  IChartApi,
  ISeriesApi,
  MouseEventParams,
  Time,
  UTCTimestamp,
  createChart,
} from 'lightweight-charts';

import { ChartIndicators, ChartLevels, ChartResponse } from '../../api/models';
import { ChartLayer, ChartPrefs } from './chart-prefs';
import { chartOptions, chartPalette } from './chart-theme';
import { IndicatorPanes } from './indicator-panes';
import { BasicOverlays } from './overlays-basic';
import { LegendPrimitive } from './primitives/legend-primitive';
import { PlanLines } from './plan-lines';
import { createPricePane } from './price-pane';
import { StrategyOverlay } from './strategy-overlay';

/**
 * The interactive chart — the scaffold (SR35).
 *
 * Three panes, candles and the volume histogram. The plan lines (SR36), the
 * MACD and RSI series (SR37), the Keltner channels and volume profile (SR38)
 * and the strategy overlay (SR39) are added on top of this frame; every one of
 * them draws into a pane this file has already created.
 *
 * **This component owns pane 0 and nothing else.** SR35 created all three panes
 * here so that later tasks would not have to restructure; SR37 replaced that
 * with something better and this file was trimmed to match. The oscillator
 * panes cannot be pre-created, because a pane is omitted entirely when its
 * indicator is missing and `removePane` renumbers everything below it — so the
 * stack has to be derived from the payload, by one owner, which is
 * `IndicatorPanes`. Two owners of one pane stack is how a pane index becomes
 * unknowable.
 *
 * `PANE_PRICE` survives as an export because the overlays that draw on the
 * price pane pass it to `addSeries`; there are deliberately no constants for
 * the panes below it, since their indices are a property of the payload rather
 * than of the design.
 *
 * **This is the only chart component.** It used to have a twin, `PriceChart`,
 * which drew the ticker detail's candles from `/market/ohlcv` — a different
 * endpoint with a different time type (`YYYY-MM-DD` strings, not epochs) and a
 * separate implementation of the same canvas discipline. The two were kept
 * looking alike by hand. The chart endpoint no longer needs a trade, so the
 * twin was deleted rather than maintained: the plan layer is conditional on
 * the payload, and a ticker with no position simply has no lines to draw.
 *
 *  - **The chart is created once**, in an effect that never re-runs. Rebuilding
 *    it on a data change would throw away pan and zoom on every `trades` event,
 *    and this store refetches on all of them.
 *  - **Data updates go through `setData`** in a separate effect. Angular never
 *    touches the canvas.
 *  - **Disposal is explicit.** The library holds a `ResizeObserver` and canvas
 *    handles that dropping the reference does not release.
 *
 * The loading, error and empty chrome is `ChartContainer`'s, which this is
 * projected into — see `ui/chart-container.ts`. Nothing here renders a state.
 */

/** The price pane, exported because every overlay that draws on it passes this
 *  to `addSeries`. The oscillator panes have no constant on purpose — see the
 *  component's docstring, and `indicator-panes.ts`. */
export const PANE_PRICE = 0;

@Component({
  selector: 'sb-trade-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div #host class="host"></div>`,
  styles: `
    :host {
      display: block;
      height: 100%;
    }
    .host {
      width: 100%;
      height: 100%;
    }
  `,
})
export class TradeChart {
  /** The whole payload, not the bars alone: the panes below are slices of one
   *  frame computed at one window, and passing them separately would let a
   *  caller hand this component an RSI from a different request. */
  readonly data = input<ChartResponse | null>(null);

  /** Task 11 (v25) — which panes and overlays are hidden, remembered across a
   *  reload. Injected rather than passed in: every chart on the page reads the
   *  one instance, so hiding RSI in one tab hides it everywhere at once. */
  private readonly prefs = inject(ChartPrefs);

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');

  private chart: IChartApi | null = null;
  private candles: ISeriesApi<'Candlestick'> | null = null;
  private volume: ISeriesApi<'Histogram'> | null = null;
  private planLines: PlanLines | null = null;
  private overlays: BasicOverlays | null = null;
  private panes: IndicatorPanes | null = null;
  private strategy: StrategyOverlay | null = null;
  private legend: LegendPrimitive | null = null;
  /** The levels the price pane's autoscale has to make room for. Held on the
   *  instance because the provider above is installed once, at creation, and
   *  asked again on every frame. `null` both when the payload has no plan and
   *  when the plan layer is toggled off — a hidden band still widening the
   *  autoscale would be a level the reader cannot see reserving room anyway. */
  private levels: ChartLevels | null = null;

  /** Which panes this payload and the current prefs actually produce — the
   *  template's toggle control reads this, and it is what the tests assert
   *  against instead of the canvas, which jsdom never paints. Ordered to match
   *  the stack `IndicatorPanes` builds, then the two price-pane overlays, then
   *  the plan. */
  protected readonly activeLayers = computed<ChartLayer[]>(() => {
    const data = this.data();
    if (!data) return [];
    const visible = this.prefs.visible();
    const layers: ChartLayer[] = [];
    if (data.indicators.macd && visible.macd) layers.push('macd');
    if (data.indicators.rsi && visible.rsi) layers.push('rsi');
    if (data.indicators.kc && visible.keltner) layers.push('keltner');
    if (data.volume_profile.length > 0 && visible.volumeProfile) layers.push('volumeProfile');
    if (data.levels && visible.plan) layers.push('plan');
    return layers;
  });

  /** Exactly the strings handed to `LegendPrimitive`'s base state: the fit
   *  notes verbatim from the payload, then the confirming method behind every
   *  drawn overlay. The crosshair readout is layered on top of this in
   *  `updateCrosshairLegend` — a mouse position is not part of the payload and
   *  has no business in a computed the store can read. */
  protected readonly legendLines = computed<string[]>(() => {
    const data = this.data();
    if (!data) return [];
    return [...data.notes, ...data.overlays.map((overlay) => overlay.source)];
  });

  constructor() {
    const destroyRef = inject(DestroyRef);

    effect(() => {
      const element = this.host().nativeElement;
      // untracked: creating the chart must not subscribe to `data`, or the next
      // refetch would rebuild the chart and reset the viewport.
      untracked(() => this.create(element));
    });

    effect(() => {
      const data = this.data();
      // Tracked, not read inside `render()`: toggling a layer must re-run this
      // effect the same way a refetched `data` does, or a hidden pane would
      // only disappear on the next trade change rather than immediately.
      const visible = this.prefs.visible();
      untracked(() => this.render(data, visible));
    });

    destroyRef.onDestroy(() => {
      this.chart?.remove();
      this.chart = null;
      this.candles = null;
      this.volume = null;
      this.planLines = null;
      this.overlays = null;
      this.panes = null;
      this.strategy = null;
      this.legend = null;
    });
  }

  private create(element: HTMLElement): void {
    if (this.chart) return;

    const palette = chartPalette();
    const chart = createChart(element, chartOptions(palette));
    this.chart = chart;

    // The pane's two series come from a shared factory rather than from here,
    // so that anything else drawing this chart — SR40's comparison harness —
    // gets the same options rather than a copy that drifts.
    const pane = createPricePane(chart, palette, () => this.levels, PANE_PRICE);
    this.candles = pane.candles;
    this.volume = pane.volume;

    this.planLines = new PlanLines(this.candles);
    this.overlays = new BasicOverlays(chart, this.candles);
    this.panes = new IndicatorPanes(chart);
    this.strategy = new StrategyOverlay(this.candles);

    // Task 9's legend, attached to the price series like every other primitive
    // here. It starts empty; `render()` fills it the moment data arrives.
    this.legend = new LegendPrimitive(palette, []);
    this.candles.attachPrimitive(this.legend);

    chart.subscribeCrosshairMove((param) => this.updateCrosshairLegend(param));
  }

  private render(data: ChartResponse | null, visible: Record<ChartLayer, boolean>): void {
    const candles = this.candles;
    const volume = this.volume;
    if (!candles || !volume) return;

    // A null payload is the state between two trades — the store drops `data`
    // the moment the trade id changes, deliberately, so that the previous
    // position's chart never sits under the new position's header. Clearing
    // both series is what makes that visible instead of stale.
    if (!data) {
      candles.setData([]);
      volume.setData([]);
      this.planLines?.detach();
      this.overlays?.detach();
      this.panes?.detach();
      this.strategy?.detach();
      this.legend?.setLines([]);
      this.levels = null;
      return;
    }

    // `t` is an epoch in SECONDS, the one time type across this payload — the
    // overlay anchors SR39 draws are epochs too, and mixing them with
    // `YYYY-MM-DD` strings is how a shape lands a year from its candle while
    // rendering perfectly happily.
    candles.setData(
      data.ohlcv.map((bar) => ({
        time: bar.t as UTCTimestamp,
        open: bar.o,
        high: bar.h,
        low: bar.l,
        close: bar.c,
      })),
    );
    volume.setData(data.ohlcv.map((bar) => ({ time: bar.t as UTCTimestamp, value: bar.v })));

    // Each gate below hides a whole layer rather than dimming it: `indicators`
    // feeds `IndicatorPanes`, which omits a pane entirely when its key is
    // absent (the same path an indicator with too little history already
    // takes), so toggling a layer off reuses that "not drawn" behaviour
    // instead of inventing a second one.
    const indicators: ChartIndicators = {
      ...data.indicators,
      macd: visible.macd ? data.indicators.macd : undefined,
      rsi: visible.rsi ? data.indicators.rsi : undefined,
    };
    this.panes?.render(indicators, data.ohlcv, chartPalette());

    // `BasicOverlays` draws both the Keltner envelope and the volume profile
    // straight off `data`, so the same gate has to travel through a payload
    // rather than a parameter this module never took.
    const overlayData: ChartResponse = {
      ...data,
      indicators: { ...data.indicators, kc: visible.keltner ? data.indicators.kc : undefined },
      volume_profile: visible.volumeProfile ? data.volume_profile : [],
    };
    this.overlays?.render(overlayData, chartPalette());

    // The confirming-method overlays are not a `ChartLayer` — Decision 10's
    // toggle list is panes and context overlays, not the trade's own case for
    // existing — so they always draw, stop side dimmed by `overlayColor`.
    this.strategy?.render(data.overlays, chartPalette());
    this.renderPlan(data, visible.plan);
    this.legend?.setLines(this.legendLines());
    this.chart?.timeScale().fitContent();
  }

  /** The bands span the whole loaded frame, first bar to last, because risk and
   *  reward apply for as long as the position does — a band bounded by
   *  something narrower would claim the plan only held over those bars.
   *
   *  `levels: null` is a chart with no plan — a watchlist ticker rather than a
   *  position. The whole layer is then absent, which is not the same thing as
   *  a plan whose individual levels happen to be unset. Toggling the plan
   *  layer off takes the same path: `planVisible` folds into the same
   *  null-levels branch every other reason for "no plan" already uses. */
  private renderPlan(data: ChartResponse, planVisible: boolean): void {
    // Before the early return: an empty frame still has levels, and the field
    // is what the autoscale provider reads.
    this.levels = planVisible ? data.levels : null;

    const first = data.ohlcv[0];
    const last = data.ohlcv[data.ohlcv.length - 1];
    if (!first || !last) {
      this.planLines?.detach();
      this.overlays?.detach();
      this.panes?.detach();
      this.strategy?.detach();
      this.levels = null;
      return;
    }
    this.planLines?.render(
      this.levels,
      chartPalette(),
      first.t as UTCTimestamp,
      last.t as UTCTimestamp,
    );
  }

  /** TradingView's own behaviour: the legend's base lines (notes and drawn
   *  methods) plus a live OHLC readout for the bar under the crosshair, or
   *  none at all once the mouse leaves the pane. Cheap enough to call on every
   *  move — `LegendPrimitive.setLines` says so — so there is no debouncing. */
  private updateCrosshairLegend(param: MouseEventParams<Time>): void {
    const legend = this.legend;
    const candles = this.candles;
    if (!legend || !candles) return;

    const base = this.legendLines();
    const point = param.seriesData.get(candles) as BarData<Time> | undefined;
    if (!point || point.open === undefined) {
      legend.setLines(base);
      return;
    }
    const readout = `O ${point.open} H ${point.high} L ${point.low} C ${point.close}`;
    legend.setLines([readout, ...base]);
  }
}
