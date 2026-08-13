import { HistogramSeries, LineSeries, LineStyle } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';

import { ChartBar, ChartIndicators } from '../../api/models';
import { ChartPalette } from './chart-theme';
import {
  IndicatorPanes,
  MACD_REFERENCES,
  RSI_REFERENCES,
  histogramPoints,
  indicatorPaneIndex,
  indicatorPaneLayout,
  paneAutoscale,
  referenceLineSpecs,
  seriesPoints,
} from './indicator-panes';

/* SR37 — the MACD and RSI panes.
 *
 * The two decisions worth pinning hardest, because both are silently wrong
 * rather than visibly broken:
 *
 *  - **A pane is omitted, and omitting it RENUMBERS the panes below it.**
 *    `removePane(1)` makes the old pane 2 the new pane 1, so SR35's
 *    `PANE_RSI = 2` is a base index and not an address. A payload with no MACD
 *    must put the RSI in pane 1, and the pane teardown must run bottom-up or
 *    the second `removePane` targets a pane that has already moved.
 *  - **A warm-up bar is whitespace, not zero.** An RSI of 0 is a real reading
 *    at the bottom of the scale; a MACD histogram bar of 0 is a real crossover.
 *    Either one drawn where the server said `null` is a chart that lies about
 *    the first twenty bars of every frame.
 *
 * Layout, colour and data-shape decisions are pure functions of the payload, so
 * they are tested as such; only the pane and series bookkeeping needs a chart,
 * and that is a hand-rolled fake — there is no canvas in jsdom.
 */

const PALETTE: ChartPalette = {
  up: 'up-colour',
  down: 'down-colour',
  accent: 'accent-colour',
  warn: 'warn-colour',
  text: 'text-colour',
  textMuted: 'muted-colour',
  border: 'border-colour',
  surface: 'surface-colour',
  volume: 'volume-colour',
  separator: 'separator-colour',
  separatorHover: 'separator-hover-colour',
  posSoft: 'pos-soft-colour',
  negSoft: 'neg-soft-colour',
  info: 'info-colour',
  infoSoft: 'info-soft-colour',
};

/** Four daily bars. `t` is an epoch in SECONDS, as `/market/chart` sends it. */
const BARS: ChartBar[] = [0, 1, 2, 3].map((i) => ({
  t: 1_700_000_000 + i * 86_400,
  o: 10,
  h: 11,
  l: 9,
  c: 10.5,
  v: 1_000,
}));

/* Both series lead with a `null`: every one of these is a rolling calculation,
 * so the head of a frame is warm-up and the server sends it as null. */
const MACD = {
  line: [null, 1, 2, -1],
  signal: [null, 0.5, 1.5, 0],
  hist: [null, 0.5, 0.5, -1],
};
const RSI = [null, 55, 72, 28];

const BOTH: ChartIndicators = { macd: MACD, rsi: RSI };

interface FakeSeries {
  definition: unknown;
  options: Record<string, unknown>;
  pane: number;
  data: unknown[];
  priceLines: unknown[];
  setData: (data: unknown[]) => void;
  createPriceLine: (options: unknown) => unknown;
  removePriceLine: (handle: unknown) => void;
}

/**
 * A chart that models the one behaviour under test: panes are an ARRAY, and
 * `removePane` splices it, so every index below the removed one shifts up.
 *
 * Seeded with three panes by default because that is what SR35's `create()`
 * hands this module — price plus the two it pre-creates.
 */
function fakeChart(initialPanes = 3) {
  const panes = Array.from({ length: initialPanes }, () => fakePane());
  const series: FakeSeries[] = [];
  const removed: number[] = [];

  const chart = {
    panes: vi.fn(() => panes),
    addPane: vi.fn(() => {
      const pane = fakePane();
      panes.push(pane);
      return pane;
    }),
    removePane: vi.fn((index: number) => {
      removed.push(index);
      panes.splice(index, 1);
    }),
    addSeries: vi.fn((definition: unknown, options: Record<string, unknown>, pane: number) => {
      const handle: FakeSeries = {
        definition,
        options,
        pane,
        data: [],
        priceLines: [],
        setData: vi.fn((data: unknown[]) => {
          handle.data = data;
        }),
        createPriceLine: vi.fn((lineOptions: unknown) => {
          handle.priceLines.push(lineOptions);
          return lineOptions;
        }),
        removePriceLine: vi.fn((line: unknown) => {
          handle.priceLines.splice(handle.priceLines.indexOf(line), 1);
        }),
      };
      series.push(handle);
      return handle;
    }),
    removeSeries: vi.fn((handle: FakeSeries) => {
      series.splice(series.indexOf(handle), 1);
    }),
  };

  return { chart, panes, series, removed };
}

function fakePane() {
  return { setStretchFactor: vi.fn() };
}

/** The series drawn into one pane, in creation order. */
const inPane = (series: FakeSeries[], pane: number) => series.filter((s) => s.pane === pane);

describe('indicatorPaneLayout', () => {
  it('lists the panes a full payload earns, MACD above RSI', () => {
    expect(indicatorPaneLayout(BOTH)).toEqual(['macd', 'rsi']);
  });

  it('drops the pane whose series the server omitted', () => {
    // Every `ChartIndicators` key is optional precisely so that an indicator
    // the frame is too short for is absent rather than a list of nulls.
    expect(indicatorPaneLayout({ rsi: RSI })).toEqual(['rsi']);
    expect(indicatorPaneLayout({ macd: MACD })).toEqual(['macd']);
  });

  it('is empty when the frame was too short for either', () => {
    expect(indicatorPaneLayout({})).toEqual([]);
  });

  it('orders the panes itself rather than following the payload key order', () => {
    // MACD is read against price and RSI against MACD, so the stack is fixed.
    // `Object.keys` order comes off the wire and is not a design decision.
    const reversed: ChartIndicators = {};
    reversed.rsi = RSI;
    reversed.macd = MACD;
    expect(indicatorPaneLayout(reversed)).toEqual(['macd', 'rsi']);
  });
});

describe('indicatorPaneIndex', () => {
  it('puts MACD directly under the price pane and RSI under MACD', () => {
    const layout = indicatorPaneLayout(BOTH);
    expect(indicatorPaneIndex(layout, 'macd')).toBe(1);
    expect(indicatorPaneIndex(layout, 'rsi')).toBe(2);
  });

  it('moves RSI up into index 1 when there is no MACD pane above it', () => {
    // The renumbering rule, and the reason SR35's `PANE_RSI = 2` is a base
    // index rather than an address: with pane 1 gone the chart HAS no pane 2,
    // and addressing one would put the RSI series back in the price pane.
    const layout = indicatorPaneLayout({ rsi: RSI });
    expect(indicatorPaneIndex(layout, 'rsi')).toBe(1);
    expect(indicatorPaneIndex(layout, 'macd')).toBeNull();
  });

  it('has no index for a pane that is not in the layout', () => {
    expect(indicatorPaneIndex([], 'rsi')).toBeNull();
    expect(indicatorPaneIndex(['macd'], 'rsi')).toBeNull();
  });
});

describe('seriesPoints', () => {
  it('anchors every value to its own bar', () => {
    expect(seriesPoints([1, 2, 3, 4], BARS)).toEqual([
      { time: BARS[0].t, value: 1 },
      { time: BARS[1].t, value: 2 },
      { time: BARS[2].t, value: 3 },
      { time: BARS[3].t, value: 4 },
    ]);
  });

  it('writes a warm-up bar as whitespace rather than zero', () => {
    // Whitespace keeps the bar on the time scale without claiming a reading.
    // Zero would draw a line down to the bottom of the pane and back.
    expect(seriesPoints(MACD.line, BARS)[0]).toEqual({ time: BARS[0].t });
    expect(seriesPoints(MACD.line, BARS)[0]).not.toHaveProperty('value');
  });

  it('treats a bar past the end of a short series as whitespace', () => {
    // The server aligns these to `ohlcv` by index; if it ever does not, the
    // failure should be a gap in one line, not a crash or a value read off
    // the wrong bar.
    expect(seriesPoints([1], BARS)).toHaveLength(4);
    expect(seriesPoints([1], BARS)[3]).toEqual({ time: BARS[3].t });
  });
});

describe('histogramPoints', () => {
  it('colours each bar by the sign of its own value', () => {
    // Per bar, not per series: the histogram's whole job is showing where
    // momentum flipped, and one colour for the lot hides exactly that. Unlike
    // volume, the hue here IS a valence — above zero is momentum with the
    // trade, below it is against.
    const points = histogramPoints(MACD.hist, BARS, PALETTE);
    expect(points[1]).toEqual({ time: BARS[1].t, value: 0.5, color: PALETTE.up });
    expect(points[3]).toEqual({ time: BARS[3].t, value: -1, color: PALETTE.down });
  });

  it('leaves a warm-up bar as uncoloured whitespace', () => {
    expect(histogramPoints(MACD.hist, BARS, PALETTE)[0]).toEqual({ time: BARS[0].t });
  });

  it('counts an exactly-zero bar as positive', () => {
    // A tie-break that never renders — a zero bar has no height — but it has
    // to be decided somewhere, and `>= 0` keeps the crossover bar on the side
    // momentum is heading towards.
    expect(histogramPoints([0], BARS, PALETTE)[0]).toMatchObject({ color: PALETTE.up });
  });
});

describe('referenceLineSpecs', () => {
  it('draws the RSI thresholds at 70, 50 and 30', () => {
    expect(referenceLineSpecs(RSI_REFERENCES, PALETTE).map((s) => s.price)).toEqual([70, 50, 30]);
  });

  it('draws the MACD reference at zero', () => {
    expect(referenceLineSpecs(MACD_REFERENCES, PALETTE).map((s) => s.price)).toEqual([0]);
  });

  it('draws every reference in the muted token, dashed', () => {
    // Never a hex literal, and never `--border`: that is the grid hairline,
    // and a threshold the reader cannot tell from a grid line is not a
    // threshold. Dashed says "fixed reference" rather than "measurement".
    for (const spec of referenceLineSpecs(RSI_REFERENCES, PALETTE)) {
      expect(spec.color).toBe(PALETTE.textMuted);
      expect(spec.lineStyle).toBe(LineStyle.Dashed);
    }
  });

  it('suppresses the axis tags', () => {
    // The opposite of SR36's plan lines, deliberately. 70/50/30 are constants
    // the reader already knows; three permanent tags on a two-unit strip would
    // bury the one label that changes, which is the RSI's own last value.
    for (const spec of referenceLineSpecs(RSI_REFERENCES, PALETTE)) {
      expect(spec.axisLabelVisible).toBe(false);
    }
  });
});

describe('paneAutoscale', () => {
  it('widens the range so the references stay on screen', () => {
    // Price lines do not participate in the library's autoscale. Without this
    // an RSI that spends the frame between 40 and 60 renders with its 70 and
    // 30 lines off the top and bottom of the pane.
    expect(paneAutoscale({ priceRange: { minValue: 41, maxValue: 59 } }, RSI_REFERENCES)).toEqual({
      priceRange: { minValue: 30, maxValue: 70 },
    });
  });

  it('leaves a range that already contains the references alone', () => {
    expect(paneAutoscale({ priceRange: { minValue: 12, maxValue: 88 } }, RSI_REFERENCES)).toEqual({
      priceRange: { minValue: 12, maxValue: 88 },
    });
  });

  it('leaves a pane with no range of its own alone', () => {
    // A frame of pure warm-up nulls has no range. Widening nothing to the
    // references alone would pin the MACD pane to the degenerate range 0..0,
    // which is worse than the library's own handling of an empty series.
    expect(paneAutoscale(null, MACD_REFERENCES)).toBeNull();
    expect(paneAutoscale({ priceRange: null }, RSI_REFERENCES)).toEqual({ priceRange: null });
  });

  it('keeps the margins the base implementation asked for', () => {
    expect(
      paneAutoscale(
        { priceRange: { minValue: 41, maxValue: 59 }, margins: { above: 4, below: 4 } },
        RSI_REFERENCES,
      )?.margins,
    ).toEqual({ above: 4, below: 4 });
  });
});

describe('IndicatorPanes', () => {
  it('rebuilds the pane stack it owns, one pane per present indicator', () => {
    const { chart, panes } = fakeChart();
    new IndicatorPanes(chart as never).render(BOTH, BARS, PALETTE);

    // Price pane plus MACD plus RSI. SR35's two pre-created panes were torn
    // down and replaced, which is what makes the layout derived rather than
    // patched.
    expect(panes).toHaveLength(3);
    expect(chart.addPane).toHaveBeenCalledTimes(2);
  });

  it('removes the panes it owns from the bottom up', () => {
    // Descending is not cosmetic. `removePane(1)` renumbers, so removing top
    // down would make the next call target the price pane's new neighbour —
    // or throw, once the index runs past the end.
    const { chart, removed } = fakeChart();
    new IndicatorPanes(chart as never).render({}, BARS, PALETTE);

    expect(removed).toEqual([2, 1]);
  });

  it('draws the MACD line, signal and histogram into the MACD pane', () => {
    const { chart, series } = fakeChart();
    new IndicatorPanes(chart as never).render(BOTH, BARS, PALETTE);

    const macd = inPane(series, 1);
    expect(macd.map((s) => s.definition)).toEqual([LineSeries, LineSeries, HistogramSeries]);
    expect(macd[0].options['color']).toBe(PALETTE.accent);
    expect(macd[1].options['color']).toBe(PALETTE.warn);
    expect(macd[2].data).toEqual(histogramPoints(MACD.hist, BARS, PALETTE));
  });

  it('hangs the zero line off the MACD pane', () => {
    const { chart, series } = fakeChart();
    new IndicatorPanes(chart as never).render(BOTH, BARS, PALETTE);

    expect(inPane(series, 1).flatMap((s) => s.priceLines)).toEqual(
      referenceLineSpecs(MACD_REFERENCES, PALETTE),
    );
  });

  it('draws the RSI and its three references into the RSI pane', () => {
    const { chart, series } = fakeChart();
    new IndicatorPanes(chart as never).render(BOTH, BARS, PALETTE);

    const rsi = inPane(series, 2);
    expect(rsi).toHaveLength(1);
    expect(rsi[0].data).toEqual(seriesPoints(RSI, BARS));
    expect(rsi[0].priceLines).toEqual(referenceLineSpecs(RSI_REFERENCES, PALETTE));
  });

  it('omits an absent pane entirely rather than drawing it empty', () => {
    const { chart, panes, series } = fakeChart();
    new IndicatorPanes(chart as never).render({ macd: MACD }, BARS, PALETTE);

    // An empty pane with an axis and no line reads as "this indicator is
    // flat", which is a different claim from "there is not enough history".
    expect(panes).toHaveLength(2);
    expect(inPane(series, 2)).toEqual([]);
  });

  it('draws the RSI into pane 1 when the MACD pane is absent', () => {
    const { chart, panes, series } = fakeChart();
    new IndicatorPanes(chart as never).render({ rsi: RSI }, BARS, PALETTE);

    expect(panes).toHaveLength(2);
    expect(series).toHaveLength(1);
    expect(series[0].pane).toBe(1);
  });

  it('leaves the chart with the price pane alone when neither indicator arrived', () => {
    const { chart, panes, series } = fakeChart();
    new IndicatorPanes(chart as never).render({}, BARS, PALETTE);

    expect(panes).toHaveLength(1);
    expect(series).toEqual([]);
  });

  it('keeps the panes across a re-render with the same layout', () => {
    // The store refetches on every `trades` event, so this is the common path,
    // and the pane separators are draggable. Tearing the stack down each time
    // would throw away a resize the reader had just made.
    const { chart } = fakeChart();
    const indicators = new IndicatorPanes(chart as never);

    indicators.render(BOTH, BARS, PALETTE);
    indicators.render(BOTH, BARS, PALETTE);

    expect(chart.addPane).toHaveBeenCalledTimes(2);
    expect(chart.removePane).toHaveBeenCalledTimes(2);
  });

  it('redraws the series on every render even when the panes stand', () => {
    // Series are cheap and the palette is a render argument; reconciling them
    // by index is how a signal line ends up wearing the MACD line's colour
    // after a theme change.
    const { chart, series } = fakeChart();
    const indicators = new IndicatorPanes(chart as never);

    indicators.render(BOTH, BARS, PALETTE);
    indicators.render(BOTH, BARS, PALETTE);

    expect(series).toHaveLength(4);
  });

  it('rebuilds the stack when an indicator appears', () => {
    const { chart, panes, series } = fakeChart();
    const indicators = new IndicatorPanes(chart as never);

    indicators.render({ rsi: RSI }, BARS, PALETTE);
    indicators.render(BOTH, BARS, PALETTE);

    expect(panes).toHaveLength(3);
    // And the RSI has moved back down to pane 2 rather than staying at 1.
    expect(inPane(series, 2).map((s) => s.definition)).toEqual([LineSeries]);
  });

  it('clears the series and its panes on detach', () => {
    const { chart, panes, series } = fakeChart();
    const indicators = new IndicatorPanes(chart as never);
    indicators.render(BOTH, BARS, PALETTE);

    indicators.detach();

    expect(panes).toHaveLength(1);
    expect(series).toEqual([]);
  });
});
