import { HistogramSeries, LineSeries, LineStyle } from 'lightweight-charts';
import type {
  AutoscaleInfo,
  CreatePriceLineOptions,
  HistogramData,
  IChartApi,
  IPriceLine,
  ISeriesApi,
  LineData,
  SeriesType,
  UTCTimestamp,
  WhitespaceData,
} from 'lightweight-charts';

import { ChartBar, ChartIndicators, ChartSeries } from '../../api/models';
import { ChartPalette } from './chart-theme';

/**
 * The oscillator panes (SR37): MACD with its signal line and a signed
 * histogram, and RSI with its 70/50/30 thresholds.
 *
 * **A pane is omitted entirely when its series is absent, and that is the whole
 * design of this module.** Every `ChartIndicators` key is optional because the
 * server drops an indicator it has too little history for rather than sending a
 * list of nulls; an empty pane with an axis and no line would read as "this
 * indicator is flat", which is a different claim from "there is not enough
 * history" (spec Decision 10's third degraded state).
 *
 * ## The pane index problem
 *
 * lightweight-charts addresses panes by POSITION, and `removePane(index)`
 * renumbers everything below it. So SR35's `PANE_MACD = 1` / `PANE_RSI = 2` are
 * base indices describing the full stack, not addresses: on a frame with no
 * MACD the chart has no pane 2 at all, and `addSeries(..., 2)` would put the
 * RSI somewhere it was not asked for. Three consequences, each pinned by a test:
 *
 *  - **The layout is derived, never patched.** `indicatorPaneLayout` turns the
 *    payload into the ordered list of panes it earns, and
 *    `indicatorPaneIndex` reads the live index off that list. Nothing in this
 *    file writes a pane index as a literal.
 *  - **Panes come down bottom-up and go back in top-down.** Removing top-down
 *    invalidates every index still queued; `addPane` appends, so adding MACD
 *    then RSI puts them in the right order without a single `swapPanes`, which
 *    is the call whose correctness would otherwise depend on how many series
 *    happened to have arrived.
 *  - **This module owns every pane below the price pane.** A shared stack with
 *    two owners is how a pane index becomes unknowable; SR35's two pre-created
 *    panes are torn down and rebuilt on the first render, which costs nothing
 *    and makes the ownership total.
 *
 * The stack is only rebuilt when the LAYOUT changes. The separators are
 * draggable and the store refetches on every `trades` event, so rebuilding on
 * each render would throw away a resize the reader had just made. Series inside
 * a standing pane are redrawn every time, PlanLines-style — they are cheap, the
 * palette is a render argument, and reconciling them by index is how the signal
 * line ends up wearing the MACD line's colour.
 *
 * The layout, colour and data-shape decisions are pure functions of the payload
 * so they are testable without a canvas; only the bookkeeping needs a chart.
 */

/** The panes this module can own, in the order they stack. */
export type IndicatorPane = 'macd' | 'rsi';

/** Mirrors SR35's `PANE_PRICE`, deliberately not imported from it: `trade-chart.ts`
 *  imports this module, and closing that cycle would drag the Angular component
 *  — decorators, the whole framework — into a unit test that needs neither. */
const PRICE_PANE = 0;

/** Every pane this module creates gets the same height, matching SR35's
 *  `STRETCH` for panes 1 and 2. It is set here rather than left to SR35's
 *  one-shot loop because a pane this module re-creates is a NEW pane, and a new
 *  pane comes back at the library's default rather than at the height the
 *  reader last saw. */
const INDICATOR_STRETCH = 2;

/** RSI's thresholds, top to bottom: overbought, the midline the trend is read
 *  against, oversold. */
export const RSI_REFERENCES = [70, 50, 30];

/** MACD's only reference. Zero is where the signal line is crossed and where
 *  the histogram changes sign — the one level in that pane worth drawing. */
export const MACD_REFERENCES = [0];

/**
 * The panes a payload earns, top to bottom.
 *
 * The order is this module's, not the payload's: MACD is read against price and
 * RSI against MACD, so the stack is fixed. `Object.keys` order arrives off the
 * wire and is not a design decision.
 */
export function indicatorPaneLayout(indicators: ChartIndicators): IndicatorPane[] {
  const layout: IndicatorPane[] = [];
  if (indicators.macd) layout.push('macd');
  if (indicators.rsi) layout.push('rsi');
  return layout;
}

/**
 * Where a pane actually sits once the absent ones are gone, or null when it is
 * not drawn at all.
 *
 * This is the renumbering rule in one line: a pane's index is its position in
 * the surviving stack, so dropping MACD moves RSI from 2 up to 1.
 */
export function indicatorPaneIndex(layout: IndicatorPane[], pane: IndicatorPane): number | null {
  const position = layout.indexOf(pane);
  return position === -1 ? null : PRICE_PANE + 1 + position;
}

/**
 * An indicator series as line data, aligned to the bars by index.
 *
 * **A null is whitespace, never zero.** The head of every one of these series is
 * warm-up — a 26-bar EMA has no value over its first 25 bars — and the server
 * carries that as null. Drawn as zero it becomes a line diving to the bottom of
 * the pane and back, which is indistinguishable from a real reading.
 *
 * Iterating the BARS rather than the values is what guarantees the time axis:
 * `t` is the epoch in seconds and the only time source in this payload. A
 * series shorter than the frame gets whitespace past its end rather than a
 * value read off the wrong bar.
 */
export function seriesPoints(
  values: ChartSeries,
  bars: ChartBar[],
): (LineData<UTCTimestamp> | WhitespaceData<UTCTimestamp>)[] {
  return bars.map((bar, index) => {
    const time = bar.t as UTCTimestamp;
    const value = values[index];
    return value === null || value === undefined || !Number.isFinite(value)
      ? { time }
      : { time, value };
  });
}

/**
 * The MACD histogram, one colour per bar.
 *
 * **Here the hue IS a valence**, which is the opposite of the volume histogram's
 * rule: a bar above zero is momentum running with the trade and one below it is
 * momentum running against, so `--pos`/`--neg` say exactly what the tokens mean.
 * Colouring the series as a whole would hide the crossover, which is the only
 * thing the histogram is drawn for.
 *
 * Exactly zero counts as positive. That bar has no height so it never renders,
 * but the tie has to break somewhere and this keeps the crossover bar on the
 * side momentum is heading towards.
 */
export function histogramPoints(
  values: ChartSeries,
  bars: ChartBar[],
  palette: ChartPalette,
): (HistogramData<UTCTimestamp> | WhitespaceData<UTCTimestamp>)[] {
  return bars.map((bar, index) => {
    const time = bar.t as UTCTimestamp;
    const value = values[index];
    if (value === null || value === undefined || !Number.isFinite(value)) return { time };
    return { time, value, color: value >= 0 ? palette.up : palette.down };
  });
}

/**
 * Fixed reference levels as price lines.
 *
 * Muted and dashed, with no axis tag — the opposite of SR36's plan lines, and
 * for the opposite reason. A plan level is a number the reader has to be able to
 * take off the axis; 70, 50, 30 and 0 are constants they already know, and four
 * permanent tags on a two-unit strip would bury the one label that changes,
 * which is the series' own last value. `--text-muted` rather than `--border`
 * because `--border` is the grid hairline, and a threshold indistinguishable
 * from a grid line is not a threshold.
 */
export function referenceLineSpecs(
  prices: number[],
  palette: ChartPalette,
): CreatePriceLineOptions[] {
  return prices.map((price) => ({
    price,
    color: palette.textMuted,
    lineWidth: 1 as const,
    lineStyle: LineStyle.Dashed,
    axisLabelVisible: false,
  }));
}

/**
 * Widen a pane's autoscale so its reference lines stay on screen.
 *
 * Price lines take no part in the library's autoscale, so an RSI that spends
 * the whole frame between 40 and 60 would render with its 70 and 30 lines above
 * and below the visible pane — thresholds that are only drawn when the series
 * has already crossed them are worse than none.
 *
 * A pane with no range of its own is left alone rather than pinned to the
 * references: a frame of pure warm-up nulls widened to `MACD_REFERENCES` would
 * get the degenerate range 0..0.
 */
export function paneAutoscale(
  base: AutoscaleInfo | null,
  references: number[],
): AutoscaleInfo | null {
  const range = base?.priceRange;
  if (!range || references.length === 0) return base;
  return {
    priceRange: {
      minValue: Math.min(range.minValue, ...references),
      maxValue: Math.max(range.maxValue, ...references),
    },
    margins: base?.margins,
  };
}

/**
 * The oscillator panes currently on a chart.
 *
 * Holds the panes below the price pane and every series in them. See the module
 * comment for why the stack is rebuilt rather than patched, and why that rebuild
 * is gated on the layout changing.
 */
export class IndicatorPanes {
  /** Null until the first render — which is also what `detach()` restores, so
   *  the render after a teardown always rebuilds rather than trusting a stack
   *  that is no longer there. */
  private layout: IndicatorPane[] | null = null;
  private series: ISeriesApi<SeriesType>[] = [];
  private lines: { series: ISeriesApi<SeriesType>; line: IPriceLine }[] = [];

  constructor(private readonly chart: IChartApi) {}

  render(indicators: ChartIndicators, bars: ChartBar[], palette: ChartPalette): void {
    const layout = indicatorPaneLayout(indicators);

    // Before the pane teardown, not after: a series outlives its pane only as a
    // dangling handle, and removing it then is a call into a pane index that no
    // longer means anything.
    this.clearSeries();
    if (!sameLayout(layout, this.layout)) this.rebuildPanes(layout);

    const macd = indicators.macd;
    const macdPane = indicatorPaneIndex(layout, 'macd');
    if (macd && macdPane !== null) this.renderMacd(macd, bars, palette, macdPane);

    const rsi = indicators.rsi;
    const rsiPane = indicatorPaneIndex(layout, 'rsi');
    if (rsi && rsiPane !== null) this.renderRsi(rsi, bars, palette, rsiPane);
  }

  /** Also the trade-change path: the chart's own `remove()` drops all of this
   *  with it, but a null payload has to clear the previous position's
   *  oscillators while the chart lives on. */
  detach(): void {
    this.clearSeries();
    this.removeOwnedPanes();
    this.layout = null;
  }

  /**
   * MACD, signal, and the histogram between them.
   *
   * `--accent` and `--warn` for the two lines: they have to be told apart at a
   * glance, and neither is a valence — the crossover's meaning is carried by the
   * histogram's sign, which is where `--pos`/`--neg` belong. Painting the signal
   * line red would say the slower average is a loss.
   */
  private renderMacd(
    macd: NonNullable<ChartIndicators['macd']>,
    bars: ChartBar[],
    palette: ChartPalette,
    pane: number,
  ): void {
    const line = this.addLine(pane, palette.accent, MACD_REFERENCES);
    const signal = this.addLine(pane, palette.warn, []);
    const histogram = this.track(
      this.chart.addSeries(
        HistogramSeries,
        {
          // Never rendered — every point carries its own colour — but the
          // library's default here is a hex from its own theme, and leaving it
          // in place is one whitespace bar away from breaking the palette rule.
          color: palette.textMuted,
          // The last bar's height is a difference of two moving averages; as an
          // axis tag it is a number with no unit and no reading.
          lastValueVisible: false,
          priceLineVisible: false,
        },
        pane,
      ),
    );

    line.setData(seriesPoints(macd.line, bars));
    signal.setData(seriesPoints(macd.signal, bars));
    histogram.setData(histogramPoints(macd.hist, bars, palette));
    this.addReferences(line, MACD_REFERENCES, palette);
  }

  private renderRsi(rsi: ChartSeries, bars: ChartBar[], palette: ChartPalette, pane: number): void {
    const line = this.addLine(pane, palette.accent, RSI_REFERENCES);
    line.setData(seriesPoints(rsi, bars));
    this.addReferences(line, RSI_REFERENCES, palette);
  }

  /** One line series, carrying the pane's autoscale floor. The provider goes on
   *  a line rather than on the histogram because a pane's scale is the union of
   *  its series' — one widened series widens the pane. */
  private addLine(pane: number, color: string, references: number[]): ISeriesApi<'Line'> {
    return this.track(
      this.chart.addSeries(
        LineSeries,
        {
          color,
          lineWidth: 1,
          // The oscillators are read for shape and for which side of a
          // threshold they are on, never for a price. A price line and a
          // last-value tag would only crowd a strip two units tall.
          priceLineVisible: false,
          autoscaleInfoProvider: (base: () => AutoscaleInfo | null) =>
            paneAutoscale(base(), references),
        },
        pane,
      ),
    );
  }

  private track<T extends SeriesType>(series: ISeriesApi<T>): ISeriesApi<T> {
    this.series.push(series as ISeriesApi<SeriesType>);
    return series;
  }

  private addReferences(
    series: ISeriesApi<SeriesType>,
    prices: number[],
    palette: ChartPalette,
  ): void {
    for (const spec of referenceLineSpecs(prices, palette)) {
      this.lines.push({ series, line: series.createPriceLine(spec) });
    }
  }

  /** Rebuild the whole stack below the price pane. Only ever reached on a
   *  layout change — see the module comment for why a resize survives a
   *  refetch. */
  private rebuildPanes(layout: IndicatorPane[]): void {
    this.removeOwnedPanes();
    // `addPane` appends, so appending in layout order IS the ordering rule.
    // `true` is `preserveEmptyPane`: a pane holds no series between this loop
    // and the `addSeries` calls that follow, and without it the library is free
    // to drop the pane in between.
    for (const _pane of layout) this.chart.addPane(true).setStretchFactor(INDICATOR_STRETCH);
    this.layout = layout;
  }

  /** Bottom-up, because `removePane` renumbers: walking down from the last pane
   *  keeps each index valid at the moment it is used, where walking up would
   *  have the second call target a pane that had already shifted. */
  private removeOwnedPanes(): void {
    for (let index = this.chart.panes().length - 1; index > PRICE_PANE; index--) {
      this.chart.removePane(index);
    }
  }

  private clearSeries(): void {
    for (const { series, line } of this.lines) series.removePriceLine(line);
    for (const series of this.series) this.chart.removeSeries(series);
    this.lines = [];
    this.series = [];
  }
}

function sameLayout(next: IndicatorPane[], current: IndicatorPane[] | null): boolean {
  return (
    current !== null &&
    next.length === current.length &&
    next.every((pane, index) => pane === current[index])
  );
}
