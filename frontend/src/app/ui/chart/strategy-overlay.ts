import type { ISeriesApi, ISeriesPrimitive, SeriesType, Time } from 'lightweight-charts';

import { ChartOverlay, ChartPoint, ChartShape } from '../../api/models';
import { ChartPalette } from './chart-theme';
import { BoxPrimitive } from './primitives/box-primitive';
import { MarkerPrimitive } from './primitives/marker-primitive';
import { PolylinePrimitive, PolylineSpec } from './primitives/polyline-primitive';

/**
 * The layer that explains why the trade exists (SR39): the one confirming
 * method, drawn as the geometry the server computed for it.
 *
 * **Every number here comes off the wire and is drawn unchanged.** The shapes
 * are `swingbot/core/charts/chart_geometry.py`'s output — the same module that
 * draws the PNG posted to Discord — so a fib ray ends at the price the server
 * computed for its ratio rather than at one re-derived from `origin` and
 * `anchor`, and a trendline is the pair of points it was fitted to rather than
 * a fit recomputed here. The moment the browser recomputes one of these
 * numbers there are two implementations of it, and the chart and the image
 * start disagreeing about where a level sits.
 *
 * **An unknown `kind` draws nothing and does not throw.** The Python side is
 * free to grow a seventh shape — it grew the sixth, `marker`, during SR32 —
 * and a client that has not learned it must render a chart without an overlay,
 * never no chart.
 *
 * **No text.** The PNG labels its overlay in the plot; here the method's name
 * is `overlay.source`, which the chart's own chrome prints (SR40). Drawing
 * text on the canvas would mean re-solving font tokens, DPR scaling and label
 * collision inside a primitive, for a string the page can render in HTML.
 */

/** The fixed accent-per-side rule the PNG uses: the overlay explains one side
 *  of the plan, and which side is the first thing to read off it. */
export function overlayColor(side: ChartOverlay['side'], palette: ChartPalette): string {
  return side === 'target' ? palette.up : palette.down;
}

/** The faint members of a fan; the matching one is drawn at `MATCH_WIDTH`. */
const FAN_WIDTH = 1;
const MATCH_WIDTH = 2;

/**
 * The primitives one overlay draws, in the order they should be attached.
 *
 * A list rather than a single primitive because two of the shapes are more than
 * one drawing: a trendline is a line plus a diamond per pivot, and a fan is one
 * ray per ratio.
 */
export function overlayPrimitives(
  overlay: ChartOverlay,
  palette: ChartPalette,
): ISeriesPrimitive<Time>[] {
  const color = overlayColor(overlay.side, palette);
  const shape: ChartShape = overlay.shape;

  switch (shape.kind) {
    case 'curve':
      return line(drawable(shape.points), color);

    case 'trendline':
      return [
        ...line(drawable([shape.p1, shape.p2]), color),
        // The pivots say which touches produced the fit. Re-deriving the line
        // from them here would be the second implementation chart_geometry.py
        // exists to prevent.
        ...shape.pivots
          .filter((point) => point[1] !== null)
          .map(
            (point) => new MarkerPrimitive({ time: point[0], price: point[1] as number, color }),
          ),
      ];

    case 'fib_fan': {
      // Every ray starts at the 0% anchor, so without its price there is no
      // fan to draw rather than a fan drawn from zero.
      const origin = shape.origin[1];
      if (origin === null) return [];

      // The whole fan, not just the matching member: a lone line at 61.8% says
      // nothing about the swing it was measured from. The match is drawn
      // bolder and solid so the reader still sees which one confirmed.
      return shape.ratios
        .filter(([, price]) => price !== null)
        .map(
          ([, price, isMatch]) =>
            new PolylinePrimitive({
              points: [
                [shape.origin[0], origin],
                [shape.anchor[0], price as number],
              ],
              color,
              lineWidth: isMatch ? MATCH_WIDTH : FAN_WIDTH,
              dashed: !isMatch,
            }),
        );
    }

    case 'fvg_zone':
      if (shape.price_low === null || shape.price_high === null) return [];
      return [
        new BoxPrimitive({
          time1: shape.t_from as Time,
          time2: shape.t_to as Time,
          price1: shape.price_low,
          price2: shape.price_high,
          // A gap is context — where price left a hole — so it is a tint under
          // the candles with the side's colour as its edge.
          fill: overlay.side === 'target' ? palette.posSoft : palette.negSoft,
          border: color,
        }),
      ];

    case 'horizontal':
      // A BOUNDED segment even when `full_width` is set: the geometry already
      // carries `t_from`/`t_to` spanning the frame in that case, so honouring
      // the span is both simpler and truthful. A rolling S/R level drawn edge
      // to edge would claim history it never described.
      return line(
        [
          [shape.t_from, shape.price],
          [shape.t_to, shape.price],
        ],
        color,
      );

    case 'marker':
      return [new MarkerPrimitive({ time: shape.t, price: shape.price, color })];

    default:
      // A kind this client has never heard of. Nothing drawn, nothing thrown.
      return [];
  }
}

/** Points whose price survived: a rolling window's warm-up bars have none, and
 *  the server sends null rather than NaN because `JSON.parse` rejects the
 *  latter outright. Zero would be a line diving to the bottom of the pane. */
function drawable(points: ChartPoint[]): [number, number][] {
  return points
    .filter((point) => point[1] !== null && Number.isFinite(point[1]))
    .map((point) => [point[0], point[1] as number]);
}

function line(points: [number, number][], color: string, extra?: Partial<PolylineSpec>) {
  // One point is not a line. Two are the minimum the renderer can stroke, and
  // a single surviving point of a curve is not worth a dot the reader would
  // read as a level.
  if (points.length < 2) return [];
  return [new PolylinePrimitive({ points, color, ...extra })];
}

/**
 * The overlay currently attached to the price series.
 *
 * Cleared and redrawn on every render, like `PlanLines` and `BasicOverlays`:
 * which shape a trade draws is a property of the payload, so there is no stable
 * set of objects to reconcile.
 */
export class StrategyOverlay {
  private attached: ISeriesPrimitive<Time>[] = [];

  constructor(private readonly series: ISeriesApi<SeriesType>) {}

  render(overlay: ChartOverlay | null, palette: ChartPalette): void {
    this.detach();
    // `overlay: null` is spec Decision 10's second degraded state -- an older
    // trade with no recorded sources. Candles, indicators and plan lines only.
    if (!overlay) return;

    for (const primitive of overlayPrimitives(overlay, palette)) {
      this.series.attachPrimitive(primitive);
      this.attached.push(primitive);
    }
  }

  detach(): void {
    for (const primitive of this.attached) this.series.detachPrimitive(primitive);
    this.attached = [];
  }
}
