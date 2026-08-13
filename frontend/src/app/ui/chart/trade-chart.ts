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
import {
  CandlestickSeries,
  HistogramSeries,
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
  createChart,
} from 'lightweight-charts';

import { ChartResponse } from '../../api/models';
import { ChartPalette, chartOptions, chartPalette } from './chart-theme';

/**
 * The interactive trade chart — the scaffold (SR35).
 *
 * Three panes, candles and the volume histogram. The plan lines (SR36), the
 * MACD and RSI series (SR37), the Keltner channels and volume profile (SR38)
 * and the strategy overlay (SR39) are added on top of this frame; every one of
 * them draws into a pane this file has already created.
 *
 * **The panes are created empty at mount, and that is the whole point of doing
 * it here.** `addPane` appends, so a pane created later is a pane at the
 * bottom — an RSI pane built before MACD would leave the two in the wrong
 * order, and re-ordering panes after the fact means `swapPanes` calls whose
 * correctness depends on how many series happened to have arrived. Creating
 * all three up front makes the later tasks pure `addSeries(..., PANE_MACD)`
 * with no restructuring, which is what "blocked by SR35" is supposed to buy
 * them. `addPane(true)` — `preserveEmptyPane` — is what keeps a pane alive
 * while it holds no series; without it the library is free to drop it, and
 * SR37's pane would silently become pane 1 on a frame with no MACD.
 *
 * **An indicator absent from the payload leaves its pane empty rather than
 * absent** at this stage. SR37 owns the decision to omit a pane entirely when
 * its series is missing — that is its test, not this one's.
 *
 * The imperative-canvas discipline is `PriceChart`'s, for the same three
 * reasons, and this component does not replace it: `PriceChart` draws the
 * ticker-detail sparkline chart from `/market/ohlcv`, which is a different
 * endpoint with a different time type (`YYYY-MM-DD` strings, not epochs).
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

/** Pane indices, exported because SR36–SR39 add series into these panes and a
 *  bare `1` at four call sites is how the RSI ends up in the MACD pane. */
export const PANE_PRICE = 0;
export const PANE_MACD = 1;
export const PANE_RSI = 2;

/** Relative pane heights. The price pane carries the candles, the volume, the
 *  plan lines and the overlay; the two oscillators are read for shape and sign
 *  rather than for a value, so they get a strip each. */
const STRETCH = [6, 2, 2];

/** The volume histogram's own price scale. An overlay scale (a non-empty id
 *  that is neither `left` nor `right`) rather than the price scale: volume in
 *  shares and price in dollars on one axis makes the candles a flat line. */
const VOLUME_SCALE = 'volume';

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
    });
  }

  private create(element: HTMLElement): void {
    if (this.chart) return;

    const palette = chartPalette();
    const chart = createChart(element, chartOptions(palette));
    this.chart = chart;

    // Pane 0 exists already; the other two do not. `true` preserves them while
    // they are empty, which they are until SR37 fills them.
    chart.addPane(true);
    chart.addPane(true);
    chart.panes().forEach((pane, index) => pane.setStretchFactor(STRETCH[index] ?? 1));

    this.candles = chart.addSeries(
      CandlestickSeries,
      {
        upColor: palette.up,
        downColor: palette.down,
        // Bodies, borders and wicks share their side's colour: a candle is one
        // object, and outlining it in a third colour only adds edges to read.
        borderUpColor: palette.up,
        borderDownColor: palette.down,
        wickUpColor: palette.up,
        wickDownColor: palette.down,
      },
      PANE_PRICE,
    );
    // Room at the bottom for the volume histogram to sit under the candles
    // rather than through them. The volume's own margins do the other half.
    this.candles.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.26 } });

    this.volume = this.createVolume(chart, palette);
  }

  /** One colour for every bar, not green-up/red-down.
   *
   *  Under the token palette a hue carries a MEANING — `--pos` is profit,
   *  `--neg` is loss — and volume has no valence: a heavy down day is
   *  information, not a loss, and painting its bar red says otherwise. It also
   *  has to sit behind the candles without competing with them, which the same
   *  greyscale choice buys. */
  private createVolume(chart: IChartApi, palette: ChartPalette): ISeriesApi<'Histogram'> {
    const volume = chart.addSeries(
      HistogramSeries,
      {
        color: palette.volume,
        priceFormat: { type: 'volume' },
        priceScaleId: VOLUME_SCALE,
        // The volume axis is never read as a number — the bars are read against
        // each other — and a second set of tick labels on the price pane would
        // cost more than it tells.
        lastValueVisible: false,
        priceLineVisible: false,
      },
      PANE_PRICE,
    );
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    return volume;
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
      return;
    }

    // `t` is an epoch in SECONDS, the one time type across this payload — the
    // overlay anchors SR39 draws are epochs too, and mixing them with the
    // `YYYY-MM-DD` strings `/market/ohlcv` returns is how a shape lands a year
    // from its candle while rendering perfectly happily.
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

    this.chart?.timeScale().fitContent();
  }
}
