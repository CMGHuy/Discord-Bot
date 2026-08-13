import { UTCTimestamp } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';

import { ChartLevels } from '../../api/models';
import { ChartPalette } from './chart-theme';
import { PlanLines, planBands, planLevelPrices, planLineSpecs } from './plan-lines';

/* SR36 — the plan levels and the risk/reward bands.
 *
 * The geometry and the colour choices are pure functions of the payload, so
 * they are tested as such; only the attach/detach bookkeeping needs a series.
 * Whether the bands actually PAINT is SR34's question, answered in
 * docs/superpowers/results/2026-08-13-chart-primitive-spike.md.
 *
 * The rule worth pinning hardest: a null level must be UNDRAWN, never drawn at
 * zero. A stop line at 0 rescales the whole price axis and reads as a real
 * level — the plan says a missing level is missing, not free.
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
  info: 'info-colour',
  posSoft: 'pos-soft-colour',
  negSoft: 'neg-soft-colour',
  infoSoft: 'info-soft-colour',
};

const FULL: ChartLevels = {
  entry: 100,
  stop: 90,
  target1: 120,
  target2: 140,
  working_stop: 104,
};

/** `Time` is a branded number in this library, so a bare epoch does not type
 *  as one — the cast is the same one every real caller makes. */
const SPAN = {
  from: 1_700_000_000 as UTCTimestamp,
  to: 1_700_864_000 as UTCTimestamp,
};

/** A band's two prices, low first. Numeric sort explicitly — the default is
 *  lexicographic, which puts 100 before 90. */
const prices = (band: { price1: number; price2: number } | undefined) =>
  band ? [band.price1, band.price2].sort((a, b) => a - b) : [];

const titles = (levels: ChartLevels) => planLineSpecs(levels, PALETTE).map((s) => s.title);
const byTitle = (levels: ChartLevels, title: string) =>
  planLineSpecs(levels, PALETTE).find((s) => s.title === title);

function fakeSeries() {
  const lines: unknown[] = [];
  const primitives: unknown[] = [];
  return {
    lines,
    primitives,
    createPriceLine: vi.fn((options: unknown) => {
      const handle = { options };
      lines.push(handle);
      return handle;
    }),
    removePriceLine: vi.fn((handle: unknown) => {
      lines.splice(lines.indexOf(handle), 1);
    }),
    attachPrimitive: vi.fn((primitive: unknown) => {
      primitives.push(primitive);
    }),
    detachPrimitive: vi.fn((primitive: unknown) => {
      primitives.splice(primitives.indexOf(primitive), 1);
    }),
  };
}

describe('planLineSpecs', () => {
  it('draws all five levels when the plan has them', () => {
    expect(titles(FULL)).toEqual(['Entry', 'Stop', 'Target 1', 'Target 2', 'Working stop']);
  });

  it('colours each level by what it means', () => {
    // Entry is the interactive/neutral token, not a valence: it is neither
    // profit nor loss, it is where the position started.
    expect(byTitle(FULL, 'Entry')?.color).toBe(PALETTE.accent);
    expect(byTitle(FULL, 'Stop')?.color).toBe(PALETTE.down);
    expect(byTitle(FULL, 'Target 1')?.color).toBe(PALETTE.up);
    expect(byTitle(FULL, 'Target 2')?.color).toBe(PALETTE.up);
    // The working stop is a stop that MOVES. Drawing it in `--neg` beside the
    // hard stop would make two different promises look like one.
    expect(byTitle(FULL, 'Working stop')?.color).toBe(PALETTE.warn);
  });

  it('puts every level on the price axis', () => {
    // The TradingView-style right-axis tag is the whole reason these are price
    // lines rather than primitives — a level you cannot read a number off is
    // decoration.
    for (const spec of planLineSpecs(FULL, PALETTE)) expect(spec.axisLabelVisible).toBe(true);
  });

  it('omits target2 when it is null rather than drawing it at zero', () => {
    const specs = planLineSpecs({ ...FULL, target2: null }, PALETTE);
    expect(specs.map((s) => s.title)).not.toContain('Target 2');
    expect(specs.every((s) => s.price !== 0)).toBe(true);
  });

  it('omits the working stop when the trade has not trailed yet', () => {
    expect(titles({ ...FULL, working_stop: null })).not.toContain('Working stop');
  });

  it('omits every null level, including entry', () => {
    expect(
      titles({ entry: null, stop: null, target1: null, target2: null, working_stop: null }),
    ).toEqual([]);
  });
});

describe('planLevelPrices', () => {
  it('lists every level the pane has to make room for', () => {
    // SR40's walk found TP1 and TP2 drawn off the top of the pane: price lines
    // take no part in the library's autoscale, and a plan that has not hit its
    // target — most of them — has targets above the frame's high. The PNG
    // widens its ylim to include them, so this is the two renderers disagreeing
    // about the one thing the phase exists to keep identical.
    expect(planLevelPrices(FULL).sort((a, b) => a - b)).toEqual([90, 100, 104, 120, 140]);
  });

  it('skips the levels a plan does not have', () => {
    expect(planLevelPrices({ ...FULL, target2: null, working_stop: null })).toEqual([100, 90, 120]);
  });

  it('is empty without levels at all, so the pane scales to the candles', () => {
    expect(planLevelPrices(null)).toEqual([]);
  });
});

describe('planBands', () => {
  it('shades risk from entry to stop and reward from entry to target', () => {
    const bands = planBands(FULL, PALETTE, SPAN.from, SPAN.to);

    expect(prices(bands.find((b) => b.fill === PALETTE.negSoft))).toEqual([90, 100]);
    expect(prices(bands.find((b) => b.fill === PALETTE.posSoft))).toEqual([100, 120]);
  });

  it('spans the frame it was given', () => {
    for (const band of planBands(FULL, PALETTE, SPAN.from, SPAN.to)) {
      expect(band.time1).toBe(SPAN.from);
      expect(band.time2).toBe(SPAN.to);
    }
  });

  it('shades to the first target, not the runner', () => {
    // Reward measured to target2 would flatter every plan that has one, and
    // R:R is read against the target the plan actually takes profit at.
    const reward = planBands(FULL, PALETTE, SPAN.from, SPAN.to).find(
      (b) => b.fill === PALETTE.posSoft,
    );
    expect(prices(reward)).toEqual([100, 120]);
  });

  it('falls back to target2 when there is no first target', () => {
    const reward = planBands({ ...FULL, target1: null }, PALETTE, SPAN.from, SPAN.to).find(
      (b) => b.fill === PALETTE.posSoft,
    );
    expect(prices(reward)).toEqual([100, 140]);
  });

  it('draws no band when the level it would span to is missing', () => {
    const noStop = planBands({ ...FULL, stop: null }, PALETTE, SPAN.from, SPAN.to);
    expect(noStop.map((b) => b.fill)).toEqual([PALETTE.posSoft]);

    const noTargets = planBands(
      { ...FULL, target1: null, target2: null },
      PALETTE,
      SPAN.from,
      SPAN.to,
    );
    expect(noTargets.map((b) => b.fill)).toEqual([PALETTE.negSoft]);
  });

  it('draws no bands at all without an entry', () => {
    // Both bands are measured FROM entry. Without one there is no risk and no
    // reward to shade, and anchoring them at 0 would flood the pane.
    expect(planBands({ ...FULL, entry: null }, PALETTE, SPAN.from, SPAN.to)).toEqual([]);
  });

  it('sits behind the candles', () => {
    for (const band of planBands(FULL, PALETTE, SPAN.from, SPAN.to)) {
      expect(band.background).not.toBe(false);
    }
  });
});

describe('PlanLines', () => {
  it('attaches the lines and the bands to the series', () => {
    const series = fakeSeries();
    new PlanLines(series as never).render(FULL, PALETTE, SPAN.from, SPAN.to);

    expect(series.lines).toHaveLength(5);
    expect(series.primitives).toHaveLength(2);
  });

  it('replaces rather than accumulates when the plan changes', () => {
    // The set of levels changes with the trade — a plan with no TP2 has four
    // lines, not five — so reconciling by index is how a target ends up
    // labelled as a stop. Removed and redrawn instead.
    const series = fakeSeries();
    const lines = new PlanLines(series as never);

    lines.render(FULL, PALETTE, SPAN.from, SPAN.to);
    lines.render({ ...FULL, target2: null, working_stop: null }, PALETTE, SPAN.from, SPAN.to);

    expect(series.lines).toHaveLength(3);
    expect(series.primitives).toHaveLength(2);
  });

  it('clears everything on detach', () => {
    const series = fakeSeries();
    const lines = new PlanLines(series as never);
    lines.render(FULL, PALETTE, SPAN.from, SPAN.to);

    lines.detach();

    expect(series.lines).toHaveLength(0);
    expect(series.primitives).toHaveLength(0);
  });
});
