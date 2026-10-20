import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import {
  CandlestickData,
  CandlestickSeries,
  IChartApi,
  ISeriesApi,
  Time,
  createChart,
} from 'lightweight-charts';

import { EquityBasis, EquityCandlesResponse, EquityTimeframe } from '../../../api/models';
import { EquityCandlesStore } from '../../../stores/equity-candles.store';
import { Async } from '../../../ui/async';
import { chartOptions, chartPalette, token } from '../../../ui/chart/chart-theme';
import { VLinePrimitive } from '../../../ui/chart/primitives/vline-primitive';
import { EQUITY_BASES, EQUITY_TIMEFRAMES } from '../../../ui/equity-chart-prefs';
import { SegmentOption, Segmented } from '../../../ui/segmented';
import {
  ACCOUNT_LABEL,
  BASIS_LABEL,
  CHANGE_PCT_TOOLTIP,
  isChangePart,
  SEAM_LABEL,
  approxCaption,
  emptyMessage,
  isIntraday,
  readoutParts,
  seamIndex,
  toSeriesData,
} from './equity-candles.model';

type ChartState = 'loading' | 'error' | 'empty' | 'chart';

/**
 * The account as candles — spec v172 § 5. Replaces the 30-point sparkline
 * inside `sb-portfolio-value`.
 *
 * The chart is created once (untracked, like `TradeChart`) and fed by
 * `setData` on every refetch: candles never animate or flash, and the
 * viewport is reset (`fitContent`) only when the timeframe or basis changes.
 * Backfilled candles are hollow, a caption states their range is an outer
 * bound while one is in view, and a vertical line marks where recording
 * started. Currency comes from the `currency` input (`connection.currency()`
 * upstream), never the API's `currency_symbol`.
 */
@Component({
  selector: 'sb-equity-candles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Async, Segmented],
  template: `
    <div class="controls">
      <sb-segmented
        class="timeframe"
        label="Candle timeframe"
        [options]="timeframeOptions"
        [value]="store.tf()"
        (valueChange)="onTimeframe($event)"
      />
      <sb-segmented
        class="basis"
        label="Equity basis"
        [options]="basisOptions"
        [value]="store.basis()"
        (valueChange)="onBasis($event)"
      />
    </div>
    @if (readout().length) {
      <p class="readout">
        @for (part of readout(); track $index) {
          <span class="part" [attr.title]="isChangePart(part) ? changeTooltip : null">{{ part }}</span>
        }
      </p>
    }
    @if (state() !== 'chart') {
      <sb-async
        class="states"
        [loading]="state() === 'loading'"
        [error]="store.error()"
        [empty]="state() === 'empty'"
        emptyReason="no-data-yet"
        [emptyTitle]="emptyTitle()"
        [skeletonRows]="3"
        [skeletonCols]="1"
        (retry)="store.load()"
      />
    }
    <div #host class="chart" [class.hidden]="state() !== 'chart'"></div>
    @if (showCaption()) {
      <p class="caption">{{ caption() }}</p>
    }
    <p class="account">{{ accountLabel }}</p>
  `,
  styles: `
    /* Grid areas carry the three-device order (spec v172 § 5): readout above
       the chart on tablet, inline right of the controls on desktop, under the
       chart on phone. minmax(0, 1fr) keeps a long readout from widening the
       panel: it wraps instead, so the page never scrolls sideways. */
    :host {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas: "controls" "readout" "chart" "states" "caption" "account";
      row-gap: var(--space-6);
      min-width: 0;
    }
    .controls {
      grid-area: controls;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-6) var(--space-10);
      min-width: 0;
    }
    .readout {
      grid-area: readout;
      margin: 0;
      min-width: 0;
      font-size: var(--text-table);
      color: var(--text-secondary);
      font-variant-numeric: tabular-nums;
      overflow-wrap: anywhere;
    }
    .part + .part::before { content: '·'; margin: 0 var(--space-4); color: var(--text-faint); }
    .part[title] { text-decoration: underline dotted; cursor: help; }
    .states { grid-area: states; }
    .chart { grid-area: chart; width: 100%; min-width: 0; height: 200px; }
    .chart.hidden { display: none; }
    .caption, .account { margin: 0; font-size: var(--text-chip); }
    .caption { grid-area: caption; color: var(--text-muted); }
    .account { grid-area: account; color: var(--text-faint); }

    /* Phone: the two controls on their own lines (44px targets come from
       --control-h in tokens.css), readout and caption under the chart. */
    @media (max-width: 639px) {
      :host { grid-template-areas: "controls" "chart" "states" "readout" "caption" "account"; }
      .controls sb-segmented { flex: 1 1 100%; }
      .chart { height: 160px; }
    }

    /* Desktop: the readout sits inline at the right of the controls. */
    @media (min-width: 1024px) {
      :host {
        grid-template-columns: auto minmax(0, 1fr);
        grid-template-areas:
          "controls readout"
          "chart chart"
          "states states"
          "caption caption"
          "account account";
        column-gap: var(--space-10);
      }
      .readout { align-self: center; justify-self: end; text-align: right; }
    }
  `,
})
export class EquityCandles {
  readonly currency = input('€');

  protected readonly store = inject(EquityCandlesStore);
  protected readonly accountLabel = ACCOUNT_LABEL;
  protected readonly changeTooltip = CHANGE_PCT_TOOLTIP;
  protected readonly isChangePart = isChangePart;
  protected readonly timeframeOptions: SegmentOption[] =
    EQUITY_TIMEFRAMES.map((tf) => ({ value: tf, label: tf }));
  protected readonly basisOptions: SegmentOption[] =
    EQUITY_BASES.map((basis) => ({ value: basis, label: BASIS_LABEL[basis] }));

  /** `sb-segmented` speaks strings; only a known value reaches the store,
   *  which writes it to the server-backed preferences. */
  protected onTimeframe(value: string): void {
    const tf = EQUITY_TIMEFRAMES.find((option) => option === value);
    if (tf) this.store.setTimeframe(tf as EquityTimeframe);
  }

  protected onBasis(value: string): void {
    const basis = EQUITY_BASES.find((option) => option === value);
    if (basis) this.store.setBasis(basis as EquityBasis);
  }

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private chart: IChartApi | null = null;
  private series: ISeriesApi<'Candlestick'> | null = null;
  protected seam: VLinePrimitive | null = null;
  private renderedView = '';
  private pendingView = '';
  private resizeObserver: ResizeObserver | null = null;

  /** Read once: chart colours come from the tokens at creation, as in
   *  `TradeChart`. `--text-faint` is the hollow candle's wick. */
  private readonly colors = (() => {
    const palette = chartPalette();
    return { up: palette.up, down: palette.down, faint: token('--text-faint'), muted: palette.textMuted };
  })();

  private readonly hoverIndex = signal<number | null>(null);
  protected readonly visible = signal<{ from: number; to: number } | null>(null);

  protected readonly candles = computed(() => this.store.data()?.candles ?? []);

  protected readonly state = computed<ChartState>(() => {
    if (this.store.error()) return 'error';
    const data = this.store.data();
    if (!data) return 'loading';
    return data.candles.length ? 'chart' : 'empty';
  });

  protected readonly seriesData = computed<CandlestickData<Time>[]>(() => {
    const data = this.store.data();
    return data ? toSeriesData(data.candles, data.tf, this.colors) : [];
  });

  /** The hovered candle, or the latest one with no crosshair. */
  private readonly shown = computed(() => {
    const candles = this.candles();
    const index = this.hoverIndex();
    return (index !== null ? candles[index] : undefined) ?? candles.at(-1) ?? null;
  });

  protected readonly readout = computed<string[]>(() => {
    const data = this.store.data();
    const candle = this.shown();
    return data && candle ? readoutParts(candle, data.basis, this.currency(), data.tf) : [];
  });

  protected readonly emptyTitle = computed(() =>
    emptyMessage(this.store.data()?.tf ?? this.store.tf(), this.store.data()?.recording_since ?? null));

  protected readonly caption = computed(() => approxCaption(this.store.data()?.recording_since ?? null));

  /** True while an approx candle is inside the visible range (the whole
   *  series before the chart reports its first range). */
  protected readonly showCaption = computed(() => {
    const candles = this.candles();
    const range = this.visible();
    const from = range ? Math.max(0, Math.floor(range.from)) : 0;
    const to = range ? Math.min(candles.length - 1, Math.ceil(range.to)) : candles.length - 1;
    return candles.slice(from, to + 1).some((candle) => candle.approx);
  });

  constructor() {
    const destroyRef = inject(DestroyRef);

    effect(() => {
      const element = this.host().nativeElement;
      // untracked: creating the chart must not subscribe to the data.
      untracked(() => this.create(element));
    });

    effect(() => {
      const data = this.store.data();
      const points = this.seriesData();
      untracked(() => this.render(data, points));
    });

    destroyRef.onDestroy(() => {
      this.resizeObserver?.disconnect();
      this.chart?.remove();
      this.chart = null;
      this.series = null;
      this.seam = null;
    });
  }

  /** Crosshair → candle by bar index; `undefined`/`null` (pointer left the
   *  pane) falls back to the latest candle. */
  protected onCrosshair(param: { logical?: number | null }): void {
    const logical = param.logical;
    this.hoverIndex.set(logical === undefined || logical === null ? null : Math.round(logical));
  }

  private create(element: HTMLElement): void {
    if (this.chart) return;
    const palette = chartPalette();
    const chart = createChart(element, chartOptions(palette));
    const series = chart.addSeries(CandlestickSeries, {
      upColor: palette.up,
      downColor: palette.down,
      borderUpColor: palette.up,
      borderDownColor: palette.down,
      wickUpColor: palette.up,
      wickDownColor: palette.down,
      priceLineVisible: false,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });
    this.seam = new VLinePrimitive();
    series.attachPrimitive(this.seam);
    chart.subscribeCrosshairMove((param) => this.onCrosshair(param));
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) =>
      this.visible.set(range ? { from: range.from, to: range.to } : null));
    this.chart = chart;
    this.series = series;
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(() => this.fitWhenVisible());
      this.resizeObserver.observe(element);
    }
  }

  private render(data: EquityCandlesResponse | null, points: CandlestickData<Time>[]): void {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return;
    this.hoverIndex.set(null);
    series.setData(points);
    chart.applyOptions({ timeScale: { timeVisible: data ? isIntraday(data.tf) : false, secondsVisible: false } });
    const seam = data ? seamIndex(data.candles) : -1;
    this.seam?.setLine(seam >= 0
      ? { time: points[seam].time, label: SEAM_LABEL, color: this.colors.faint, textColor: this.colors.muted }
      : null);
    const view = data ? `${data.tf}/${data.basis}` : '';
    if (view && view !== this.renderedView) this.pendingView = view;
    this.fitWhenVisible();
  }

  /** The host is display:none while the first answer loads, so a fit run
   *  then would measure a 0-width chart and never repeat. The fit waits
   *  until the host has a width; the ResizeObserver retries it on unhide. */
  private fitWhenVisible(): void {
    const view = this.pendingView;
    if (!view || !this.chart || this.host().nativeElement.clientWidth === 0) return;
    this.chart.timeScale().fitContent();
    this.renderedView = view;
    this.pendingView = '';
  }
}
