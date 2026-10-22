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
import { Button } from '../../../ui/button';
import { BaselinePrimitive } from '../../../ui/chart/primitives/baseline-primitive';
import { LogicalWindow, inWindowCandles, nextTimeframe, rangeStats, shouldLoadOlder } from './equity-range.model';
import { chartOptions, chartPalette, token } from '../../../ui/chart/chart-theme';
import { VLinePrimitive } from '../../../ui/chart/primitives/vline-primitive';
import { EQUITY_BASES, EQUITY_TIMEFRAMES } from '../../../ui/equity-chart-prefs';
import { SegmentOption, Segmented } from '../../../ui/segmented';
import {
  ACCOUNT_LABEL,
  WallSpan,
  chartRangeFor,
  stepDownBlocked,
  wallSpan,
  BASIS_LABEL,
  CHANGE_PCT_TOOLTIP,
  isChangePart,
  SEAM_LABEL,
  approxCaption,
  emptyMessage,
  isIntraday,
  ReadoutPart,
  candleReadout,
  isAtLiveEdge,
  rangeReadoutParts,
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
/** How long a viewport change the component made itself stays flagged.
 *  lightweight-charts reports the new range on its next paint, so the flag
 *  must outlive the call; 100 ms covers several frames and is far shorter
 *  than any deliberate gesture that follows it. */
export const PROGRAMMATIC_SETTLE_MS = 100;

@Component({
  selector: 'sb-equity-candles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Async, Segmented, Button],
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
      @if (state() === 'chart' && !store.atLiveEdge()) {
        <button sb-button type="button" variant="ghost" class="latest" (click)="toLatest()">↦ Latest</button>
      }
    </div>
    @if (readout().length) {
      <p class="readout">
        @for (part of readout(); track $index) {
          <span class="part" [attr.data-tone]="part.tone"
                [attr.title]="isChangePart(part.text) ? changeTooltip : null">{{ part.text }}</span>
        }
      </p>
    }
    <p class="account">{{ accountLabel }}</p>
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
    <div class="stage">
      <div #host class="chart" [class.hidden]="state() !== 'chart'"></div>
      @if (state() === 'chart' && store.pageError()) {
        <p class="page-error" role="status">
          Couldn't load earlier history ·
          <button sb-button type="button" variant="link" (click)="store.loadOlder()">Retry</button>
        </p>
      }
    </div>
    @if (showCaption()) {
      <p class="caption">{{ caption() }}</p>
    }
  `,
  styles: `
    /* Grid areas carry the three-device order (spec v172 § 5): readout above
       the chart on tablet, inline right of the controls on desktop, under the
       chart on phone. minmax(0, 1fr) keeps a long readout from widening the
       panel: it wraps instead, so the page never scrolls sideways. */
    :host {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas: "controls" "readout" "account" "chart" "states" "caption";
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
    .part[data-tone='pos'] { color: var(--pos); }
    .part[data-tone='neg'] { color: var(--neg); }
    .part[data-tone='warn'] { color: var(--warn); }
    .stage { grid-area: chart; position: relative; min-width: 0; }
    .chart { width: 100%; min-width: 0; height: 200px; }
    .chart.hidden { display: none; }
    /* v181 §9: a failed history page never blanks the chart; the note sits
       over its left edge, where the missing history would be. */
    .page-error {
      position: absolute;
      top: var(--space-4);
      left: var(--space-4);
      margin: 0;
      padding: var(--space-4) var(--space-6);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--panel-radius);
      font-size: var(--text-chip);
      color: var(--text-secondary);
    }
    .caption, .account { margin: 0; font-size: var(--text-chip); }
    .caption { grid-area: caption; color: var(--text-muted); }
    .account { grid-area: account; color: var(--text-faint); }

    @media (max-width: 639px) {
      :host { grid-template-areas: "controls" "chart" "states" "readout" "account" "caption"; }
      .controls sb-segmented { flex: 1 1 100%; }
      .chart { height: 160px; }
    }

    @media (min-width: 1024px) {
      :host {
        grid-template-columns: auto minmax(0, 1fr);
        grid-template-areas:
          "controls readout"
          "controls account"
          "chart chart"
          "states states"
          "caption caption";
        column-gap: var(--space-10);
      }
      .readout { align-self: end; justify-self: end; text-align: right; }
      .account { justify-self: end; text-align: right; }
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
    if (!tf) return;
    this.pendingSpan = null;
    this.store.setTimeframe(tf as EquityTimeframe);
  }

  protected onBasis(value: string): void {
    const basis = EQUITY_BASES.find((option) => option === value);
    if (basis) this.store.setBasis(basis as EquityBasis);
  }

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private chart: IChartApi | null = null;
  private series: ISeriesApi<'Candlestick'> | null = null;
  protected seam: VLinePrimitive | null = null;
  protected baseline: BaselinePrimitive | null = null;
  private renderedView = '';
  private pendingView = '';
  /** True while a viewport change made by this component (fit, restore, and
   *  in part 2 a preset move) is still being reported back by the chart. */
  private programmatic = false;
  private releaseTimer: ReturnType<typeof setTimeout> | null = null;
  /** An auto step waiting for its candles: the span to show on them. */
  private pendingSpan: { tf: EquityTimeframe; span: WallSpan } | null = null;

  private resizeObserver: ResizeObserver | null = null;

  /** Read once: chart colours come from the tokens at creation, as in
   *  `TradeChart`. `--text-faint` is the hollow candle's wick. */
  private readonly colors = (() => {
    const palette = chartPalette();
    return { up: palette.up, down: palette.down, faint: token('--text-faint'), muted: palette.textMuted,
             posSoft: palette.posSoft, negSoft: palette.negSoft };
  })();

  private readonly hoverIndex = signal<number | null>(null);
  protected readonly visible = signal<LogicalWindow | null>(null);

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

  /** The whole buckets in view (spec v181 §4): readout, baseline and, in
   *  part 2, the KPI window all read this one list. */
  protected readonly inWindow = computed(() => inWindowCandles(this.visible(), this.candles()));

  private readonly hovered = computed(() => {
    const index = this.hoverIndex();
    return index === null ? null : (this.candles()[index] ?? null);
  });

  /** Hovered candle, else the visible range, else the latest candle. */
  protected readonly readout = computed<ReadoutPart[]>(() => {
    const data = this.store.data();
    if (!data) return [];
    const hovered = this.hovered();
    if (hovered) return candleReadout(hovered, data.basis, this.currency(), data.tf);
    const range = rangeReadoutParts(rangeStats(this.inWindow()), this.currency());
    if (range.length) return range;
    const latest = this.candles().at(-1);
    return latest ? candleReadout(latest, data.basis, this.currency(), data.tf) : [];
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

    effect(() => {
      const first = this.inWindow()[0];
      untracked(() => this.baseline?.setBaseline(first
        ? { value: first.o, line: this.colors.muted, above: this.colors.posSoft, below: this.colors.negSoft }
        : null));
    });

    destroyRef.onDestroy(() => {
      if (this.releaseTimer !== null) clearTimeout(this.releaseTimer);
      this.resizeObserver?.disconnect();
      this.chart?.remove();
      this.chart = null;
      this.series = null;
      this.seam = null;
      this.baseline = null;
    });
  }

  /** Crosshair → candle by bar index; `undefined`/`null` (pointer left the
   *  pane) returns to the visible-range summary. */
  protected onCrosshair(param: { logical?: number | null }): void {
    const logical = param.logical;
    this.hoverIndex.set(logical === undefined || logical === null ? null : Math.round(logical));
  }

  /** Every visible-range change, user or programmatic: remember it, report
   *  the live edge, and page in older history near the left edge. */
  protected onVisibleRange(range: LogicalWindow | null): void {
    this.visible.set(range);
    const atEdge = isAtLiveEdge(range, this.candles().length);
    if (atEdge !== this.store.atLiveEdge()) this.store.setAtLiveEdge(atEdge);
    if (shouldLoadOlder(range, this.store.hasMore(), this.store.pageLoading())) this.store.loadOlder();
    this.autoTimeframe();
  }

  /** v181 §3: more than 250 bars → one step coarser, fewer than 15 → one
   *  step finer, written like a manual pick. The span is kept for the restore. */
  private autoTimeframe(): void {
    const data = this.store.data();
    if (!data || this.pendingSpan) return;
    const window = this.inWindow();
    const next = nextTimeframe(window.length, data.tf,
      stepDownBlocked(data.tf, window[0], data.recording_since));
    const span = wallSpan(window, data.tf);
    if (next === data.tf || !span) return;
    this.pendingSpan = { tf: next, span };
    this.store.setTimeframe(next);
  }

  private moveProgrammatically(fn: () => void): void {
    this.programmatic = true;
    if (this.releaseTimer !== null) clearTimeout(this.releaseTimer);
    try {
      fn();
    } finally {
      this.releaseTimer = setTimeout(() => {
        this.programmatic = false;
        this.releaseTimer = null;
      }, PROGRAMMATIC_SETTLE_MS);
    }
  }

  /** "↦ Latest": back to the newest candle at the current zoom. */
  protected toLatest(): void {
    this.chart?.timeScale().scrollToRealTime();
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
    this.baseline = new BaselinePrimitive();
    series.attachPrimitive(this.baseline);
    this.seam = new VLinePrimitive();
    series.attachPrimitive(this.seam);
    chart.subscribeCrosshairMove((param) => this.onCrosshair(param));
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) =>
      this.onVisibleRange(range ? { from: range.from, to: range.to } : null));
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
    const chart = this.chart;
    if (!view || !chart || this.host().nativeElement.clientWidth === 0) return;
    const restore = this.restorableRange();
    this.moveProgrammatically(() => {
      if (restore) chart.timeScale().setVisibleRange(restore);
      else chart.timeScale().fitContent();
    });
    this.renderedView = view;
    this.pendingView = '';
    this.pendingSpan = null;
  }

  /** The recorded span, once the step's own timeframe has candles to show it on. */
  private restorableRange(): { from: Time; to: Time } | null {
    const pending = this.pendingSpan;
    const data = this.store.data();
    if (!pending || !data || data.tf !== pending.tf || !data.candles.length) return null;
    return chartRangeFor(pending.span, pending.tf);
  }
}
