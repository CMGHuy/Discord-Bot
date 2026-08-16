import { describe, expect, it } from 'vitest';
import { lineChartXScale, lineChartYScale, seriesPath } from './line-chart';

describe('lineChartXScale', () => {
  it('maps the earliest date to 0 and the latest to 1', () => {
    const scale = lineChartXScale(['2026-01-01', '2026-01-11', '2026-01-21']);
    expect(scale('2026-01-01')).toBeCloseTo(0, 5);
    expect(scale('2026-01-21')).toBeCloseTo(1, 5);
    expect(scale('2026-01-11')).toBeCloseTo(0.5, 5);
  });

  it('is a real time scale, not an index scale', () => {
    // Three dates, unevenly spaced -- an index scale would put the middle
    // one at 0.5. Jan 3 is 2/20 of the way from Jan 1 to Jan 21.
    const scale = lineChartXScale(['2026-01-01', '2026-01-03', '2026-01-21']);
    expect(scale('2026-01-03')).toBeCloseTo(0.1, 5);
  });

  it('a single date does not divide by zero', () => {
    const scale = lineChartXScale(['2026-01-01']);
    expect(scale('2026-01-01')).toBe(0);
    expect(Number.isNaN(scale('2026-01-01'))).toBe(false);
  });
});

describe('lineChartYScale', () => {
  it('maps the lowest value to 0 and the highest to 1', () => {
    const scale = lineChartYScale([10, 30, 20]);
    expect(scale(10)).toBeCloseTo(0, 5);
    expect(scale(30)).toBeCloseTo(1, 5);
  });

  it('a flat series (one distinct value) does not divide by zero', () => {
    const scale = lineChartYScale([5, 5, 5]);
    expect(scale(5)).toBeCloseTo(0.5, 5);
    expect(Number.isNaN(scale(5))).toBe(false);
  });

  it('respects a fixed [min, max] domain when one is given', () => {
    // The Calibration decile chart needs an absolute 0-100 win-rate axis,
    // not one auto-scaled to whichever decile happens to be tallest --
    // see Task 8's own note on why Histogram needed the same fix.
    const scale = lineChartYScale([60, 85], { min: 0, max: 100 });
    expect(scale(0)).toBeCloseTo(0, 5);
    expect(scale(100)).toBeCloseTo(1, 5);
    expect(scale(85)).toBeCloseTo(0.85, 5);
  });
});

describe('seriesPath', () => {
  it('builds one SVG line command per point after the first', () => {
    const series = {
      name: 'ui',
      points: [
        { date: '2026-01-01', value: 0 },
        { date: '2026-01-11', value: 10 },
      ],
    };
    const x = lineChartXScale(['2026-01-01', '2026-01-11']);
    const y = lineChartYScale([0, 10]);
    const path = seriesPath(series, x, y);
    expect(path.startsWith('M ')).toBe(true);
    expect(path.match(/L /g)).toHaveLength(1);
  });

  it('a single point draws nothing rather than throwing', () => {
    const series = { name: 'ui', points: [{ date: '2026-01-01', value: 0 }] };
    const x = lineChartXScale(['2026-01-01']);
    const y = lineChartYScale([0]);
    expect(() => seriesPath(series, x, y)).not.toThrow();
  });
});
