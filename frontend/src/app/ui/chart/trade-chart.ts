import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  effect,
  inject,
  input,
  untracked,
  viewChild,
} from '@angular/core';
import { IChartApi, ISeriesApi, UTCTimestamp, createChart } from 'lightweight-charts';

import { ChartLevels, ChartResponse } from '../../api/models';
import { chartOptions, chartPalette } from './chart-theme';
import { IndicatorPanes } from './indicator-panes';
import { BasicOverlays } from './overlays-basic';
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

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');

  private chart: IChartApi | null = null;
  private candles: ISeriesApi<'Candlestick'> | null = null;
  private volume: ISeriesApi<'Histogram'> | null = null;
  private planLines: PlanLines | null = null;
  private overlays: BasicOverlays | null = null;
  private panes: IndicatorPanes | null = null;
  private strategy: StrategyOverlay | null = null;
  /** The levels the price pane's autoscale has to make room for. Held on the
   *  instance because the provider above is installed once, at creation, and
   *  asked again on every frame. */
  private levels: ChartLevels | null = null;

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
      untracked(() => this.render(data));
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
  }

  private render(data: ChartResponse | null): void {
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

    this.panes?.render(data.indicators, data.ohlcv, chartPalette());
    this.overlays?.render(data, chartPalette());
    this.strategy?.render(data.overlays, chartPalette());
    this.renderPlan(data);
    this.chart?.timeScale().fitContent();
  }

  /** The bands span the whole loaded frame, first bar to last, because risk and
   *  reward apply for as long as the position does — a band bounded by
   *  something narrower would claim the plan only held over those bars.
   *
   *  `levels: null` is a chart with no plan — a watchlist ticker rather than a
   *  position. The whole layer is then absent, which is not the same thing as
   *  a plan whose individual levels happen to be unset. */
  private renderPlan(data: ChartResponse): void {
    // Before the early return: an empty frame still has levels, and the field
    // is what the autoscale provider reads.
    this.levels = data.levels;

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
      data.levels,
      chartPalette(),
      first.t as UTCTimestamp,
      last.t as UTCTimestamp,
    );
  }
}
