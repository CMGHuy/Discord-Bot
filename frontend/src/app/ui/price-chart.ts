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
  IChartApi,
  ISeriesApi,
  createChart,
} from 'lightweight-charts';

import { Candle, TradeLevels } from '../api/models';
import { chartOptions, chartPalette } from './chart-theme';

/**
 * The candlestick chart itself — lightweight-charts **5.x**, imperative state
 * inside an `OnPush` component.
 *
 * **v5, not the 4.2.3 vendored for the Jinja UI**, and the API difference is
 * real rather than cosmetic: v4's `chart.addCandlestickSeries()` is gone, and
 * v5 takes `chart.addSeries(CandlestickSeries, options)` with the series type
 * imported as a value. Every pre-v5 example — which is most of them — will
 * mislead you into the old call and a runtime "not a function".
 *
 * Three things make imperative canvas state safe under `OnPush`:
 *
 *  - **The chart is created once**, in an effect that runs on the host
 *    element and never re-runs. Re-creating it on a data change would throw
 *    away zoom and pan on every one of the pushes this app receives
 *    constantly.
 *  - **Data updates go through `setData`**, in a separate effect that reads
 *    only the inputs. Angular never touches the canvas.
 *  - **Disposal is explicit.** `chart.remove()` on destroy, because the
 *    library holds a `ResizeObserver` and canvas handles that garbage
 *    collection alone will not release — a workspace navigated in and out of
 *    twenty times would otherwise leak twenty charts.
 *
 * Resizing is the library's own `autoSize`, which installs a `ResizeObserver`
 * on the container. That is strictly better than a window resize listener,
 * which misses the sidebar collapsing and the drawer opening.
 */
@Component({
  selector: 'sb-price-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div #host class="host"></div>`,
  styles: `
    :host { display: block; height: 100%; }
    .host { width: 100%; height: 100%; }
  `,
})
export class PriceChart {
  readonly bars = input.required<Candle[]>();
  readonly levels = input<TradeLevels | null>(null);

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');

  private chart: IChartApi | null = null;
  private series: ISeriesApi<'Candlestick'> | null = null;

  constructor() {
    const destroyRef = inject(DestroyRef);

    effect(() => {
      const element = this.host().nativeElement;
      // untracked: creating the chart must not subscribe to the data signals,
      // or the next price tick would rebuild the chart and reset the viewport.
      untracked(() => this.create(element));
    });

    effect(() => {
      const bars = this.bars();
      const levels = this.levels();
      untracked(() => this.render(bars, levels));
    });

    destroyRef.onDestroy(() => {
      // The library owns a ResizeObserver and canvas handles; dropping the
      // reference alone does not release them.
      this.chart?.remove();
      this.chart = null;
      this.series = null;
    });
  }

  private create(element: HTMLElement): void {
    if (this.chart) return;

    const palette = chartPalette();
    this.chart = createChart(element, chartOptions(palette));
    this.series = this.chart.addSeries(CandlestickSeries, {
      upColor: palette.up,
      downColor: palette.down,
      // Bodies, borders and wicks share their side's colour: a candle is one
      // object, and outlining it in a third colour only adds edges to read.
      borderUpColor: palette.up,
      borderDownColor: palette.down,
      wickUpColor: palette.up,
      wickDownColor: palette.down,
    });
  }

  private render(bars: Candle[], levels: TradeLevels | null): void {
    const series = this.series;
    if (!series) return;

    series.setData(
      bars.map((bar) => ({
        // The API already emits `YYYY-MM-DD`, which is a valid `Time`. No
        // parsing, so no timezone to get wrong on a daily bar.
        time: bar.time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
    );

    this.drawLevels(levels);
    this.chart?.timeScale().fitContent();
  }

  private priceLines: ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']>[] = [];

  private drawLevels(levels: TradeLevels | null): void {
    const series = this.series;
    if (!series) return;

    // Removed and redrawn rather than updated: the set of levels changes with
    // the trade (a plan with no TP2 has four lines, not five), and reconciling
    // them by index is how a take-profit line ends up labelled as a stop.
    for (const line of this.priceLines) series.removePriceLine(line);
    this.priceLines = [];

    if (!levels) return;
    const palette = chartPalette();

    const definitions: [number | null, string, string][] = [
      [levels.entry, 'Entry', palette.accent],
      [levels.stop_loss, 'Stop', palette.down],
      [levels.tp1, 'TP1', palette.up],
      [levels.tp2, 'TP2', palette.up],
    ];

    for (const [price, title, color] of definitions) {
      if (price === null || price === undefined) continue;
      this.priceLines.push(
        series.createPriceLine({
          price,
          color,
          title,
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
        }),
      );
    }
  }
}
