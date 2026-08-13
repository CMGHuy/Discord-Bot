import {
  AutoscaleInfo,
  CandlestickSeries,
  HistogramSeries,
  IChartApi,
  ISeriesApi,
} from 'lightweight-charts';

import { ChartLevels } from '../../api/models';
import { ChartPalette } from './chart-theme';
import { paneAutoscale } from './indicator-panes';
import { planLevelPrices } from './plan-lines';

/**
 * The price pane's two series — candles and the volume histogram.
 *
 * Framework-free and separate from `TradeChart` so that anything drawing this
 * chart builds the same pane. That is not hypothetical: SR40's comparison
 * harness reproduced these options by hand, and when the autoscale provider
 * below was added to the component the harness silently kept the old
 * behaviour — the same "second implementation" failure the whole phase is
 * arranged to prevent, in miniature.
 */

/** The price pane's share of the chart height. `IndicatorPanes` gives each of
 *  its own panes 2, so a full stack is 6:2:2. */
export const PRICE_STRETCH = 6;

/** The volume histogram's own price scale. An overlay scale rather than the
 *  price scale: volume in shares and price in dollars on one axis makes the
 *  candles a flat line. */
const VOLUME_SCALE = 'volume';

export interface PricePane {
  candles: ISeriesApi<'Candlestick'>;
  volume: ISeriesApi<'Histogram'>;
}

/**
 * @param levels a getter, not a value — the library asks the autoscale
 *   provider on every frame and the plan changes with the trade.
 */
export function createPricePane(
  chart: IChartApi,
  palette: ChartPalette,
  levels: () => ChartLevels | null,
  paneIndex = 0,
): PricePane {
  chart.panes()[paneIndex]?.setStretchFactor(PRICE_STRETCH);

  const candles = chart.addSeries(
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
      // The plan levels are price LINES, which take no part in autoscale — so a
      // target above the frame's high draws off the top of the pane, correct
      // and invisible. SR40's walk against the PNG is what found it: matplotlib
      // widens its ylim to include the levels, so without this the two
      // renderers disagree about the one thing this phase keeps identical.
      // Same helper the oscillator panes use for their thresholds.
      autoscaleInfoProvider: (base: () => AutoscaleInfo | null) =>
        paneAutoscale(base(), planLevelPrices(levels())),
    },
    paneIndex,
  );
  // Room at the bottom for the volume histogram to sit under the candles rather
  // than through them. The volume's own margins do the other half.
  candles.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.26 } });

  const volume = chart.addSeries(
    HistogramSeries,
    {
      // One colour for every bar, not green-up/red-down. Under the token
      // palette a hue carries a MEANING — `--pos` is profit, `--neg` is loss —
      // and volume has no valence: a heavy down day is information, not a loss.
      color: palette.volume,
      priceFormat: { type: 'volume' },
      priceScaleId: VOLUME_SCALE,
      // The volume axis is never read as a number — the bars are read against
      // each other — and a second set of tick labels on the price pane would
      // cost more than it tells.
      lastValueVisible: false,
      priceLineVisible: false,
    },
    paneIndex,
  );
  volume.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

  return { candles, volume };
}
