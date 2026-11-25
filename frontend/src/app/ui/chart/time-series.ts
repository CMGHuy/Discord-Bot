import {
  ChangeDetectionStrategy, Component, DestroyRef, ElementRef, effect, inject, input, untracked, viewChild,
} from '@angular/core';
import { AreaSeries, BaselineSeries, CandlestickSeries, LineStyle, createChart } from 'lightweight-charts';
import type {
  AreaSeriesPartialOptions, BaselineSeriesPartialOptions, CandlestickData, CandlestickSeriesPartialOptions,
  IChartApi, IPriceLine, ISeriesApi, SeriesType, SingleValueData, Time,
} from 'lightweight-charts';

import { ThemeService } from '../theme.service';
import { ChartPalette, applyChartTheme, chartPalette, pctFormat, priceFormat, rFormat, themedToken } from './chart-theme';
import { TimeScaleSync } from './time-scale-sync';

export type TimeSeriesKind = 'area' | 'baseline' | 'candles';
export type TimeSeriesFormat = 'price' | 'r' | 'pct';
export interface TimeSeriesPoint { time: string; value: number }
export interface TimeSeriesCandle { time: string; open: number; high: number; low: number; close: number }
export type TimeSeriesDatum = TimeSeriesPoint | TimeSeriesCandle;

const FORMATS = { price: priceFormat, r: rFormat, pct: pctFormat } as const;

type Row = SingleValueData<Time> | CandlestickData<Time>;
type KindOptions = AreaSeriesPartialOptions | BaselineSeriesPartialOptions | CandlestickSeriesPartialOptions;

/** One row per day (`time.slice(0, 10)`), the last in input order winning, sorted by day:
 *  lightweight-charts rejects two rows with one time. */
export function collapseByDay<T extends { time: string }>(points: readonly T[]): T[] {
  const byDay = new Map<string, T>();
  for (const point of points) {
    const day = point.time.slice(0, 10);
    byDay.set(day, { ...point, time: day });
  }
  return [...byDay.values()].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
}

const isCandle = (datum: TimeSeriesDatum): datum is TimeSeriesCandle => 'open' in datum;

/** The right shape for `kind`, every value finite; anything else is dropped, never thrown on. */
function plottable(kind: TimeSeriesKind, datum: TimeSeriesDatum): boolean {
  if (kind === 'candles') return isCandle(datum) && [datum.open, datum.high, datum.low, datum.close].every(Number.isFinite);
  return !isCandle(datum) && Number.isFinite(datum.value);
}

function rows(kind: TimeSeriesKind, points: readonly TimeSeriesDatum[]): Row[] {
  return collapseByDay(points.filter((datum) => plottable(kind, datum))).map((datum) => isCandle(datum)
    ? { time: datum.time as Time, open: datum.open, high: datum.high, low: datum.low, close: datum.close }
    : { time: datum.time as Time, value: datum.value });
}

/** One point is a marker with no line (v246 edge states); two or more draw the line. */
function areaOptions(palette: ChartPalette, single: boolean): AreaSeriesPartialOptions {
  return { lineWidth: 2, lineVisible: !single, pointMarkersVisible: single, priceLineVisible: false,
    lineColor: palette.accent, topColor: themedToken('--accent-soft'), bottomColor: 'transparent' };
}

function baselineOptions(palette: ChartPalette, single: boolean): BaselineSeriesPartialOptions {
  return { lineWidth: 2, lineVisible: !single, pointMarkersVisible: single, priceLineVisible: false,
    baseValue: { type: 'price', price: 0 },
    topLineColor: palette.down, topFillColor1: 'transparent', topFillColor2: 'transparent',
    bottomLineColor: palette.down, bottomFillColor1: palette.negSoft, bottomFillColor2: palette.negSoft };
}

function seriesOptions(kind: TimeSeriesKind, palette: ChartPalette, single: boolean): KindOptions {
  if (kind === 'area') return areaOptions(palette, single);
  if (kind === 'baseline') return baselineOptions(palette, single);
  return candleOptions(palette);
}

function candleOptions(palette: ChartPalette): CandlestickSeriesPartialOptions {
  return { priceLineVisible: false, borderVisible: false,
    upColor: palette.up, downColor: palette.down, wickUpColor: palette.up, wickDownColor: palette.down };
}

function addSeries(chart: IChartApi, kind: TimeSeriesKind): ISeriesApi<SeriesType> {
  if (kind === 'area') return chart.addSeries(AreaSeries);
  if (kind === 'baseline') return chart.addSeries(BaselineSeries);
  return chart.addSeries(CandlestickSeries);
}

/**
 * v246 §A3: a time series on lightweight-charts, themed by `chart-theme.ts`.
 * `area` is an equity curve, `baseline` (base 0) a drawdown shaded below
 * zero, `candles` OHLC by day. The chart is created once; a `kind` change
 * rebuilds only the series. A ResizeObserver sizes the plot, the theme signal
 * repaints it, and teardown releases the observer and chart.
 */
@Component({
  selector: 'sb-time-series',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { role: 'img', '[attr.aria-label]': 'label()', '[style.height.px]': 'height()' },
  template: `<div class="plot" #plot></div>`,
  styles: `
    :host { display: block; position: relative; min-width: 0; }
    .plot { position: absolute; inset: 0; }
  `,
})
export class TimeSeries {
  readonly kind = input.required<TimeSeriesKind>();
  readonly points = input.required<readonly TimeSeriesDatum[]>();
  readonly valueFormat = input<TimeSeriesFormat>('price');
  readonly height = input<number>(220);
  readonly label = input.required<string>();

  /** v246 §A3: charts bound to one TimeScaleSync scroll together (Overview's equity and drawdown). */
  readonly sync = input<TimeScaleSync | null>(null);

  private readonly plot = viewChild.required<ElementRef<HTMLDivElement>>('plot');
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private zeroLine: IPriceLine | null = null;
  private readonly theme = inject(ThemeService);
  private resizeObserver: ResizeObserver | null = null;
  private count = 0;
  private pendingFit = false;
  private linked: TimeScaleSync | null = null;
  private releaseSync: (() => void) | null = null;

  constructor() {
    effect(() => {
      const element = this.plot().nativeElement;
      const kind = this.kind();
      untracked(() => this.build(element, kind));
    });
    effect(() => {
      const sync = this.sync();
      untracked(() => this.link(sync));
    });
    effect(() => {
      const data = rows(this.kind(), this.points());
      untracked(() => this.render(data));
    });
    // ThemeService is a signal: reading it here is the subscription, destroyed with the view.
    effect(() => {
      this.theme.theme();
      this.valueFormat();
      untracked(() => this.restyle());
    });
    effect(() => {
      const height = this.height();
      untracked(() => this.resize(height));
    });
    inject(DestroyRef).onDestroy(() => this.teardown());
  }

  private build(element: HTMLElement, kind: TimeSeriesKind): void {
    if (!this.chart) {
      this.chart = createChart(element, { width: element.clientWidth, height: this.height() });
      this.observe(element);
      this.link(this.sync());
    }
    if (this.series) this.chart.removeSeries(this.series);
    this.series = addSeries(this.chart, kind);
    this.zeroLine = kind === 'candles' ? null : this.series.createPriceLine({
      price: 0, color: chartPalette().axis, lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: false, title: '',
    });
    this.count = 0;
  }

  /** jsdom has no ResizeObserver; without one the chart still sizes on data and height changes. */
  private observe(element: HTMLElement): void {
    if (typeof ResizeObserver === 'undefined') return;
    this.resizeObserver = new ResizeObserver(() => this.resize(this.height()));
    this.resizeObserver.observe(element);
  }

  /** Joins `sync`, leaving the previous group first; a no-op when nothing changed or before the chart exists. */
  private link(sync: TimeScaleSync | null): void {
    if (!this.chart || sync === this.linked) return;
    this.releaseSync?.();
    this.linked = sync;
    this.releaseSync = sync ? sync.register(this.chart) : null;
  }

  private render(data: Row[]): void {
    if (!this.chart || !this.series) return;
    this.series.setData(data);
    this.count = data.length;
    this.restyle();
    this.pendingFit = true;
    this.resize(this.height());
  }

  private restyle(): void {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return;
    const palette = chartPalette();
    applyChartTheme(chart, palette);
    series.applyOptions({ ...seriesOptions(this.kind(), palette, this.count === 1), priceFormat: FORMATS[this.valueFormat()] });
    this.zeroLine?.applyOptions({ color: palette.axis });
  }

  /** Width from the plot box, height from the input; the first non-zero width after new data fits it. */
  private resize(height: number): void {
    const chart = this.chart;
    if (!chart) return;
    const width = this.plot().nativeElement.clientWidth;
    chart.resize(width, height);
    if (this.pendingFit && width > 0) {
      this.pendingFit = false;
      chart.timeScale().fitContent();
    }
  }

  /** Observer, then the sync group, then the chart: nothing may call into a removed chart. */
  private teardown(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.releaseSync?.();
    this.releaseSync = null;
    this.linked = null;
    this.chart?.remove();
    this.chart = null;
    this.series = null;
    this.zeroLine = null;
  }
}
