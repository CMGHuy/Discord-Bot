import { describe, expect, it, vi } from 'vitest';

import { ChartOverlay, ChartShape } from '../../api/models';
import { ChartPalette } from './chart-theme';
import { BoxPrimitive } from './primitives/box-primitive';
import { MarkerPrimitive } from './primitives/marker-primitive';
import { PolylinePrimitive } from './primitives/polyline-primitive';
import { StrategyOverlay, overlayPrimitives } from './strategy-overlay';

/* SR39 — the layer that explains why the trade exists.
 *
 * Every number here was computed by `swingbot/core/charts/chart_geometry.py`,
 * the same module that draws the PNG posted to Discord. So these tests assert
 * that the geometry arrives on the canvas UNCHANGED — no re-fitting, no
 * re-deriving a price from a ratio — because the moment the browser recomputes
 * one of these numbers there are two implementations of it and they will
 * disagree.
 *
 * The other rule under test is degradation: an unknown `kind` draws nothing and
 * does not throw. The Python side is free to grow a seventh shape, and a client
 * that has not learned it yet must render a chart without an overlay rather
 * than no chart at all.
 */

const PALETTE = { up: 'up-colour', down: 'down-colour' } as ChartPalette;

const wrap = (shape: ChartShape, side: 'target' | 'stop' = 'target'): ChartOverlay => ({
  side,
  source: 'EMA20',
  shape,
});

function fakeSeries() {
  const primitives: unknown[] = [];
  return {
    primitives,
    attachPrimitive: vi.fn((primitive: unknown) => primitives.push(primitive)),
    detachPrimitive: vi.fn((primitive: unknown) => {
      primitives.splice(primitives.indexOf(primitive), 1);
    }),
  };
}

describe('overlayPrimitives', () => {
  it('draws a curve as one polyline through the points it was given', () => {
    const shape: ChartShape = {
      kind: 'curve',
      label: 'EMA20',
      points: [
        [100, 10],
        [200, 11],
        [300, 12],
      ],
    };

    const [line, ...rest] = overlayPrimitives(wrap(shape), PALETTE);

    expect(line).toBeInstanceOf(PolylinePrimitive);
    expect(rest).toEqual([]);
    expect((line as PolylinePrimitive).spec.points).toEqual([
      [100, 10],
      [200, 11],
      [300, 12],
    ]);
  });

  it('drops a curve point with no price rather than drawing it at zero', () => {
    // A rolling window's warm-up bars have no value; the server sends null
    // rather than NaN because JSON.parse rejects the latter outright.
    const shape: ChartShape = {
      kind: 'curve',
      label: 'Donchian',
      points: [
        [100, null],
        [200, 11],
        [300, 12],
      ],
    };

    const [line] = overlayPrimitives(wrap(shape), PALETTE);

    expect((line as PolylinePrimitive).spec.points).toEqual([
      [200, 11],
      [300, 12],
    ]);
  });

  it('draws nothing when only one point of a curve survives', () => {
    // One point is not a line, and a lone dot on the price pane reads as a
    // level the trade was confirmed against — which is precisely what a
    // warm-up bar is not.
    const shape: ChartShape = {
      kind: 'curve',
      label: 'Donchian',
      points: [
        [100, null],
        [200, 11],
      ],
    };

    expect(overlayPrimitives(wrap(shape), PALETTE)).toEqual([]);
  });

  it('draws a trendline as its two points plus a diamond at each pivot', () => {
    const shape: ChartShape = {
      kind: 'trendline',
      p1: [100, 10],
      p2: [400, 16],
      pivots: [
        [150, 11],
        [300, 14],
      ],
      label: 'Trendline',
    };

    const drawn = overlayPrimitives(wrap(shape), PALETTE);

    const line = drawn.find((p) => p instanceof PolylinePrimitive) as PolylinePrimitive;
    const markers = drawn.filter((p) => p instanceof MarkerPrimitive) as MarkerPrimitive[];
    expect(line.spec.points).toEqual([
      [100, 10],
      [400, 16],
    ]);
    // The fit is the server's. The pivots say which touches produced it, and
    // re-deriving the line from them here would be the second implementation
    // chart_geometry.py exists to prevent.
    expect(markers.map((m) => [m.spec.time, m.spec.price])).toEqual([
      [150, 11],
      [300, 14],
    ]);
  });

  it('draws a fib fan as one ray per ratio from the shared origin', () => {
    const shape: ChartShape = {
      kind: 'fib_fan',
      origin: [100, 10],
      anchor: [400, 20],
      ratios: [
        [0.382, 13.82, false],
        [0.618, 16.18, true],
      ],
      matched: 'Fib 61.8%',
      matched_price: 16.18,
    };

    const rays = overlayPrimitives(wrap(shape), PALETTE) as PolylinePrimitive[];

    expect(rays).toHaveLength(2);
    // Each ray ends at the PRICE THE SERVER COMPUTED for its ratio, never at a
    // price re-derived from origin and anchor here.
    expect(rays.map((r) => r.spec.points)).toEqual([
      [
        [100, 10],
        [400, 13.82],
      ],
      [
        [100, 10],
        [400, 16.18],
      ],
    ]);
  });

  it('draws the matching fib ray bolder than the rest of the fan', () => {
    // A lone line at 61.8% says nothing about the swing it was measured from,
    // so the whole fan is drawn — but the reader still has to see which member
    // the trade was confirmed against.
    const shape: ChartShape = {
      kind: 'fib_fan',
      origin: [100, 10],
      anchor: [400, 20],
      ratios: [
        [0.382, 13.82, false],
        [0.618, 16.18, true],
      ],
      matched: 'Fib 61.8%',
      matched_price: 16.18,
    };

    const [faint, bold] = overlayPrimitives(wrap(shape), PALETTE) as PolylinePrimitive[];

    expect(bold.spec.lineWidth).toBeGreaterThan(faint.spec.lineWidth ?? 1);
  });

  it('skips a fib ratio with no price', () => {
    const shape: ChartShape = {
      kind: 'fib_fan',
      origin: [100, 10],
      anchor: [400, 20],
      ratios: [
        [0.382, null, false],
        [0.618, 16.18, true],
      ],
      matched: null,
      matched_price: null,
    };

    expect(overlayPrimitives(wrap(shape), PALETTE)).toHaveLength(1);
  });

  it('draws an fvg zone as a box between its two times and two prices', () => {
    const shape: ChartShape = {
      kind: 'fvg_zone',
      t_from: 100,
      t_to: 400,
      price_low: 10,
      price_high: 12,
      mid: 11,
      label: 'FVG',
    };

    const [box, ...rest] = overlayPrimitives(wrap(shape), PALETTE);

    expect(box).toBeInstanceOf(BoxPrimitive);
    expect(rest).toEqual([]);
    expect((box as BoxPrimitive).spec).toMatchObject({
      time1: 100,
      time2: 400,
      price1: 10,
      price2: 12,
    });
  });

  it('draws nothing for an fvg zone with no prices', () => {
    const shape: ChartShape = {
      kind: 'fvg_zone',
      t_from: 100,
      t_to: 400,
      price_low: null,
      price_high: null,
      mid: null,
      label: 'FVG',
    };

    expect(overlayPrimitives(wrap(shape), PALETTE)).toEqual([]);
  });

  it('draws a horizontal as a BOUNDED segment, not a full-width price line', () => {
    // A rolling S/R level is only meaningful over the bars it was measured
    // across; running it edge to edge claims history it never described.
    const shape: ChartShape = {
      kind: 'horizontal',
      price: 15,
      t_from: 100,
      t_to: 400,
      label: 'S/R',
      full_width: false,
    };

    const [line] = overlayPrimitives(wrap(shape), PALETTE) as PolylinePrimitive[];

    expect(line.spec.points).toEqual([
      [100, 15],
      [400, 15],
    ]);
  });

  it('draws a marker as a lone diamond', () => {
    const shape: ChartShape = {
      kind: 'marker',
      t: 250,
      price: 14,
      label: 'Pivot high',
      pivot_kind: 'high',
    };

    const [marker, ...rest] = overlayPrimitives(wrap(shape), PALETTE);

    expect(marker).toBeInstanceOf(MarkerPrimitive);
    expect(rest).toEqual([]);
    expect((marker as MarkerPrimitive).spec).toMatchObject({ time: 250, price: 14 });
  });

  it('colours by side: the target hue for a target, the stop hue for a stop', () => {
    // The PNG's fixed accent-per-side rule. The overlay explains one side of
    // the plan, and which side it explains is the first thing to read off it.
    const shape: ChartShape = {
      kind: 'horizontal',
      price: 15,
      t_from: 1,
      t_to: 2,
      label: 'L',
      full_width: true,
    };

    const [target] = overlayPrimitives(wrap(shape, 'target'), PALETTE) as PolylinePrimitive[];
    const [stop] = overlayPrimitives(wrap(shape, 'stop'), PALETTE) as PolylinePrimitive[];

    expect(target.spec.color).toBe(PALETTE.up);
    expect(stop.spec.color).toBe(PALETTE.down);
  });

  it('draws nothing, and does not throw, for a kind it has never heard of', () => {
    // The server may grow a seventh shape. A client that has not learned it
    // renders a chart without an overlay, never no chart.
    const shape = { kind: 'supernova', whatever: true } as unknown as ChartShape;

    expect(() => overlayPrimitives(wrap(shape), PALETTE)).not.toThrow();
    expect(overlayPrimitives(wrap(shape), PALETTE)).toEqual([]);
  });
});

describe('StrategyOverlay', () => {
  const CURVE: ChartShape = {
    kind: 'curve',
    label: 'EMA20',
    points: [
      [100, 10],
      [200, 11],
    ],
  };

  it('attaches what the dispatcher produced', () => {
    const series = fakeSeries();
    new StrategyOverlay(series as never).render(wrap(CURVE), PALETTE);

    expect(series.primitives).toHaveLength(1);
  });

  it('clears the previous overlay before drawing the next', () => {
    const series = fakeSeries();
    const overlay = new StrategyOverlay(series as never);

    overlay.render(wrap(CURVE), PALETTE);
    overlay.render(
      wrap({ kind: 'marker', t: 1, price: 2, label: 'P', pivot_kind: 'low' }),
      PALETTE,
    );

    expect(series.primitives).toHaveLength(1);
    expect(series.primitives[0]).toBeInstanceOf(MarkerPrimitive);
  });

  it('draws nothing at all for a trade with no confirming source', () => {
    // `overlay: null` is spec Decision 10's second degraded state: an older
    // trade with no recorded sources renders candles, indicators and plan
    // lines, and nothing else.
    const series = fakeSeries();
    const overlay = new StrategyOverlay(series as never);

    overlay.render(wrap(CURVE), PALETTE);
    overlay.render(null, PALETTE);

    expect(series.primitives).toEqual([]);
  });
});
