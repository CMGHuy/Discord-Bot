import { describe, expect, it, vi } from 'vitest';

import { ChartBar, VolumeProfileBin } from '../../api/models';
import { ChartPalette } from './chart-theme';
import {
  BasicOverlays,
  VolumeProfilePrimitive,
  keltnerPoints,
  profileBars,
} from './overlays-basic';

/* SR38 — the Keltner envelope and the volume profile.
 *
 * Both are context rather than readings: they say where price has been calm and
 * where it has traded, and neither is a number anyone takes off the axis. That
 * is why both are drawn faintly and why neither gets a price line.
 *
 * The two decisions the tests pin are the ones that fail silently otherwise: a
 * warm-up bar must be WHITESPACE and not zero (a zero drags the price axis to
 * the floor and draws a line through it), and the profile must scale to its own
 * widest bin (scaling to a constant makes every chart's profile a different
 * meaningless width).
 */

const PALETTE = {
  info: 'info-colour',
  infoSoft: 'info-soft-colour',
  volume: 'volume-colour',
} as ChartPalette;

const BARS: ChartBar[] = [
  { t: 1_700_000_000, o: 1, h: 2, l: 0.5, c: 1.5, v: 100 },
  { t: 1_700_086_400, o: 1.5, h: 2.5, l: 1, c: 2, v: 120 },
  { t: 1_700_172_800, o: 2, h: 3, l: 1.5, c: 2.5, v: 90 },
] as ChartBar[];

const BINS: VolumeProfileBin[] = [
  { price: 10, volume: 50 },
  { price: 11, volume: 200 },
  { price: 12, volume: 100 },
];

function drawTarget(width = 400) {
  const context = {
    fillStyle: '',
    globalAlpha: 1,
    fillRect: vi.fn(),
  };
  return {
    context,
    target: {
      useBitmapCoordinateSpace: (cb: (scope: unknown) => void) =>
        cb({
          context,
          horizontalPixelRatio: 1,
          verticalPixelRatio: 1,
          mediaSize: { width, height: 300 },
          bitmapSize: { width, height: 300 },
        }),
    },
  };
}

/** Prices map to coordinates one-for-one, inverted the way a price axis is, so
 *  the expected pixel numbers below stay readable. */
function attach(primitive: VolumeProfilePrimitive) {
  const series = { priceToCoordinate: vi.fn((price: number) => 200 - price * 10) };
  primitive.attached({ chart: {}, series } as never);
  return series;
}

describe('keltnerPoints', () => {
  it('pairs each value with its own bar time', () => {
    const points = keltnerPoints(BARS, [1, 2, 3]);

    expect(points).toEqual([
      { time: 1_700_000_000, value: 1 },
      { time: 1_700_086_400, value: 2 },
      { time: 1_700_172_800, value: 3 },
    ]);
  });

  it('emits whitespace for a warm-up bar, never zero', () => {
    // A 20-bar envelope has no value on bar one. Zero there is not merely
    // wrong: it rescales the price axis to include 0 and draws a line down to
    // it, which hides the candles entirely.
    const points = keltnerPoints(BARS, [null, null, 3]);

    expect(points[0]).toEqual({ time: 1_700_000_000 });
    expect(points[0]).not.toHaveProperty('value');
    expect(points[2]).toEqual({ time: 1_700_172_800, value: 3 });
  });

  it('stops at the shorter of the two, rather than inventing bars', () => {
    // The server aligns the series to the visible window, so a mismatch means
    // something upstream is wrong -- drawing a value at an undefined time is
    // how that turns into a shape at epoch zero.
    expect(keltnerPoints(BARS, [1])).toHaveLength(1);
    expect(keltnerPoints(BARS.slice(0, 1), [1, 2, 3])).toHaveLength(1);
  });
});

describe('profileBars', () => {
  it('scales every bin to the widest one', () => {
    // Relative, not absolute: the axis is never read, so the only information
    // in a bar's length is how it compares with its neighbours.
    expect(profileBars(BINS).map((b) => b.ratio)).toEqual([0.25, 1, 0.5]);
  });

  it('carries the bin height in price, so the bars tile instead of overlapping', () => {
    expect(profileBars(BINS).every((b) => b.span === 1)).toBe(true);
  });

  it('is empty when the server sent no bins', () => {
    // "Insufficient history" arrives as an empty list, not as an absent key --
    // this is an overlay on the price pane, so there is no pane to omit.
    expect(profileBars([])).toEqual([]);
  });

  it('is empty when every bin is empty, rather than dividing by zero', () => {
    expect(profileBars([{ price: 10, volume: 0 }])).toEqual([]);
  });

  it('survives a single bin, which has no neighbour to measure a span against', () => {
    const bars = profileBars([{ price: 10, volume: 5 }]);

    expect(bars).toHaveLength(1);
    expect(bars[0].ratio).toBe(1);
    expect(bars[0].span).toBeGreaterThan(0);
  });
});

describe('VolumeProfilePrimitive', () => {
  it('draws from the left edge, widest bar first in length', () => {
    const primitive = new VolumeProfilePrimitive(profileBars(BINS), PALETTE.volume);
    attach(primitive);
    const { context, target } = drawTarget(400);

    (primitive.paneViews()[0].renderer() as { draw(t: unknown): void }).draw(target);

    const rects = context.fillRect.mock.calls;
    expect(rects).toHaveLength(3);
    // Every bar starts at x = 0: the profile hangs off the left edge, which is
    // the one place on the pane no series occupies.
    expect(rects.every((call) => call[0] === 0)).toBe(true);
    // Widths are the ratios against the same maximum width.
    const widths = rects.map((call) => call[2]);
    expect(widths[1]).toBeGreaterThan(widths[2]);
    expect(widths[2]).toBeGreaterThan(widths[0]);
  });

  it('never spans more than a fraction of the pane', () => {
    // A profile that reaches the candles stops being a margin annotation and
    // starts hiding the thing it annotates.
    const primitive = new VolumeProfilePrimitive(profileBars(BINS), PALETTE.volume);
    attach(primitive);
    const { context, target } = drawTarget(400);

    (primitive.paneViews()[0].renderer() as { draw(t: unknown): void }).draw(target);

    for (const call of context.fillRect.mock.calls) expect(call[2]).toBeLessThanOrEqual(100);
  });

  it('draws nothing when a bin is off screen', () => {
    const primitive = new VolumeProfilePrimitive(profileBars(BINS), PALETTE.volume);
    primitive.attached({ chart: {}, series: { priceToCoordinate: () => null } } as never);
    const { context, target } = drawTarget();

    (primitive.paneViews()[0].renderer() as { draw(t: unknown): void }).draw(target);

    expect(context.fillRect).not.toHaveBeenCalled();
  });

  it('sits behind the candles', () => {
    const view = new VolumeProfilePrimitive(profileBars(BINS), PALETTE.volume).paneViews()[0] as {
      zOrder(): string;
    };
    expect(view.zOrder()).toBe('bottom');
  });

  it('draws nothing once detached', () => {
    const primitive = new VolumeProfilePrimitive(profileBars(BINS), PALETTE.volume);
    attach(primitive);
    primitive.detached();
    const { context, target } = drawTarget();

    (primitive.paneViews()[0].renderer() as { draw(t: unknown): void }).draw(target);

    expect(context.fillRect).not.toHaveBeenCalled();
  });
});

describe('BasicOverlays', () => {
  it('draws two Keltner lines in the info token, visibly', () => {
    // `--info-soft` was tried first and SR40's walk against the PNG found it
    // invisible: 12% alpha is a fill's opacity, not a line's.
    const chart = fakeChart();

    new BasicOverlays(chart.api as never, chart.priceSeries as never).render(
      {
        ohlcv: BARS,
        indicators: { kc: { upper: [2, 3, 4], lower: [0, 1, 2] } },
        volume_profile: [],
      } as never,
      PALETTE,
    );

    expect(chart.series).toHaveLength(2);
    expect(chart.series.every((s) => s.options['color'] === PALETTE.info)).toBe(true);
  });

  it('draws no line series at all when the frame was too short for Keltner', () => {
    // The server omits the key rather than sending nulls. Two empty line series
    // would put two legend entries and a price-scale contribution on the pane
    // for something that does not exist.
    const chart = fakeChart();

    new BasicOverlays(chart.api as never, chart.priceSeries as never).render(
      { ohlcv: BARS, indicators: {}, volume_profile: [] } as never,
      PALETTE,
    );

    expect(chart.series).toHaveLength(0);
  });

  it('attaches the profile only when there are bins', () => {
    const withBins = fakeChart();
    const without = fakeChart();

    new BasicOverlays(withBins.api as never, withBins.priceSeries as never).render(
      { ohlcv: BARS, indicators: {}, volume_profile: BINS } as never,
      PALETTE,
    );
    new BasicOverlays(without.api as never, without.priceSeries as never).render(
      { ohlcv: BARS, indicators: {}, volume_profile: [] } as never,
      PALETTE,
    );

    expect(withBins.primitives).toHaveLength(1);
    expect(without.primitives).toHaveLength(0);
  });

  it('replaces rather than accumulates across renders, and clears on detach', () => {
    const chart = fakeChart();
    const overlays = new BasicOverlays(chart.api as never, chart.priceSeries as never);
    const payload = {
      ohlcv: BARS,
      indicators: { kc: { upper: [2, 3, 4], lower: [0, 1, 2] } },
      volume_profile: BINS,
    } as never;

    overlays.render(payload, PALETTE);
    overlays.render(payload, PALETTE);
    expect(chart.series).toHaveLength(2);
    expect(chart.primitives).toHaveLength(1);

    overlays.detach();
    expect(chart.series).toHaveLength(0);
    expect(chart.primitives).toHaveLength(0);
  });
});

function fakeChart() {
  const series: { options: Record<string, unknown>; data: unknown[] }[] = [];
  const primitives: unknown[] = [];
  const api = {
    addSeries: vi.fn((_definition: unknown, options: Record<string, unknown>) => {
      const handle = { options, data: [] as unknown[], setData: vi.fn() };
      series.push(handle);
      return handle;
    }),
    removeSeries: vi.fn((handle: unknown) => {
      series.splice(series.indexOf(handle as never), 1);
    }),
  };
  const priceSeries = {
    attachPrimitive: vi.fn((primitive: unknown) => primitives.push(primitive)),
    detachPrimitive: vi.fn((primitive: unknown) => {
      primitives.splice(primitives.indexOf(primitive), 1);
    }),
  };
  return { api, priceSeries, series, primitives };
}
