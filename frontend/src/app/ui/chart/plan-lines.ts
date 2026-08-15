import {
  CreatePriceLineOptions,
  IPriceLine,
  ISeriesApi,
  LineStyle,
  SeriesType,
  Time,
} from 'lightweight-charts';

import { ChartLevels } from '../../api/models';
import { ChartPalette } from './chart-theme';
import { BoxPrimitive, BoxSpec } from './primitives/box-primitive';

/**
 * The plan on the price pane (SR36): five levels as price lines, and the risk
 * and reward shaded between them.
 *
 * **Price lines for the levels, a primitive for the bands**, and the split is
 * not arbitrary. `createPriceLine` gives the TradingView-style tag on the right
 * axis for free, and a level a reader cannot take a number off is decoration —
 * that tag is most of the value of drawing the line at all. The bands are
 * regions rather than levels, which the library has no notion of, so they are
 * SR34's box primitive with the frame's own time span as their width.
 *
 * **A null level is undrawn, never drawn at zero.** A stop line at 0 rescales
 * the entire price axis and reads as a real level — a plan with no second
 * target has four lines, not five and one lie. Same for the bands: both are
 * measured from entry, so a payload without one has neither.
 *
 * The geometry and the colours are pure functions of the payload
 * (`planLineSpecs`, `planBands`) with the series bookkeeping kept separate in
 * `PlanLines`, so the decisions above are testable without a canvas.
 */

/** A level and how it is drawn. `title` is what the axis tag prints. */
export type PlanLineSpec = CreatePriceLineOptions;

/**
 * The plan's levels, in reading order: where it started, where it is wrong,
 * where it is right, and where the stop has since moved to.
 *
 * Colours carry the meaning the tokens assign them. Entry is `--accent` rather
 * than a valence colour because it is neither profit nor loss — it is the
 * datum both bands are measured from. The working stop is `--warn`, not
 * `--neg`: it is a stop that MOVES, and painting it the same red as the hard
 * stop would make a floor that trails up look like the line that ends the
 * trade.
 */
export function planLineSpecs(levels: ChartLevels, palette: ChartPalette): PlanLineSpec[] {
  const definitions: [number | null, string, string, LineStyle][] = [
    [levels.entry, 'Entry', palette.accent, LineStyle.Solid],
    [levels.stop, 'Stop', palette.down, LineStyle.Dashed],
    [levels.target1, 'Target 1', palette.up, LineStyle.Dashed],
    [levels.target2, 'Target 2', palette.up, LineStyle.Dashed],
    // Dotted, because it is the one level that is provisional: it moves on
    // every breakeven and trail step while the position is open.
    [levels.working_stop, 'Working stop', palette.warn, LineStyle.Dotted],
  ];

  return definitions
    .filter(([price]) => price !== null && Number.isFinite(price))
    .map(([price, title, color, lineStyle]) => ({
      price: price as number,
      title,
      color,
      lineStyle,
      lineWidth: 1,
      axisLabelVisible: true,
    }));
}

/**
 * Every level the plan draws, for widening the price pane's autoscale.
 *
 * **Price lines take no part in the library's autoscale**, and SR40's walk
 * against the PNG is what caught it: a plan whose targets sit above the
 * frame's high — which is every plan that has not hit its target, i.e. most of
 * them — drew TP1 and TP2 off the top of the pane. They were there, correct,
 * and invisible. matplotlib widens its ylim to include the levels, so the two
 * renderers disagreed about the one thing this phase exists to keep identical.
 *
 * The candles do get squashed when a target is far away. That is what the PNG
 * does too, and a target you cannot see is worse than a candle body that is
 * three pixels shorter.
 */
export function planLevelPrices(levels: ChartLevels | null): number[] {
  if (!levels) return [];
  return [levels.entry, levels.stop, levels.target1, levels.target2, levels.working_stop].filter(
    (price): price is number => price !== null && Number.isFinite(price),
  );
}

/**
 * The risk and reward bands, spanning the frame from `from` to `to`.
 *
 * **Reward is measured to the FIRST target**, falling back to the second when a
 * plan has no first. Shading to the runner instead would flatter every plan
 * that has one, and the ratio a reader compares against risk is the one they
 * take profit at.
 *
 * Edgeless on purpose — `border` matches `fill`. The plan lines already draw
 * both boundaries of each band, and a second outline under them reads as a
 * fourth level.
 */
export function planBands(
  levels: ChartLevels,
  palette: ChartPalette,
  from: Time,
  to: Time,
): BoxSpec[] {
  const entry = levels.entry;
  if (entry === null || !Number.isFinite(entry)) return [];

  const target = usable(levels.target1) ?? usable(levels.target2);
  const stop = usable(levels.stop);

  const band = (price: number, colour: string): BoxSpec => ({
    time1: from,
    time2: to,
    price1: entry,
    price2: price,
    fill: colour,
    border: colour,
  });

  return [
    ...(stop === null ? [] : [band(stop, palette.negSoft)]),
    ...(target === null ? [] : [band(target, palette.posSoft)]),
  ];
}

function usable(price: number | null): number | null {
  return price !== null && Number.isFinite(price) ? price : null;
}

/**
 * The lines and bands currently on a series.
 *
 * **Removed and redrawn on every render, never reconciled.** The set of levels
 * changes with the trade — a plan with no second target has four lines — so
 * matching old to new by index is how a target ends up wearing a stop's label.
 * There are at most seven objects here; rebuilding them costs nothing worth
 * the bug.
 */
export class PlanLines {
  private lines: IPriceLine[] = [];
  private bands: BoxPrimitive[] = [];

  constructor(private readonly series: ISeriesApi<SeriesType>) {}

  render(levels: ChartLevels | null, palette: ChartPalette, from: Time, to: Time): void {
    this.detach();
    // `null` is a chart with no plan at all -- a watchlist ticker rather than
    // a position. Distinct from a plan whose individual levels are null,
    // which `planLineSpecs` already drops one by one.
    if (!levels) return;
    for (const spec of planLineSpecs(levels, palette)) {
      this.lines.push(this.series.createPriceLine(spec));
    }
    for (const spec of planBands(levels, palette, from, to)) {
      const band = new BoxPrimitive(spec);
      this.series.attachPrimitive(band);
      this.bands.push(band);
    }
  }

  /** Also the teardown path: the chart's own `remove()` drops these with it,
   *  but a trade change has to clear them while the chart lives on. */
  detach(): void {
    for (const line of this.lines) this.series.removePriceLine(line);
    for (const band of this.bands) this.series.detachPrimitive(band);
    this.lines = [];
    this.bands = [];
  }
}
