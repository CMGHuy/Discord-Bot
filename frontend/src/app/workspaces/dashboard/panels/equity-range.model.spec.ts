import { describe, expect, it } from 'vitest';

import { EquityCandle, EquityTimeframe } from '../../../api/models';
import { EQUITY_TIMEFRAMES } from '../../../ui/equity-chart-prefs';
import {
  TF_RATIO,
  TF_STEP_DOWN_BARS,
  TF_STEP_UP_BARS,
  bucketEndInstant,
  bucketStartInstant,
  inWindowCandles,
  nextTimeframe,
  nyMidnight,
  rangeStats,
  windowBounds,
} from './equity-range.model';

function candle(overrides: Partial<EquityCandle> = {}): EquityCandle {
  return { t: '2026-10-16', o: 10120.5, h: 10210, l: 10090.2, c: 10180.4,
           change: 59.9, change_pct: 0.59, samples: 78, skipped: 0, approx: false, ...overrides };
}

/** Ten daily candles, 1 to 10 Oct 2026, so index i has t 2026-10-(i+1). */
const TEN = Array.from({ length: 10 }, (_, i) =>
  candle({ t: `2026-10-${String(i + 1).padStart(2, '0')}` }));

const iso = (d: Date): string => d.toISOString();

describe('inWindowCandles', () => {
  it('counts a partly visible edge candle whole', () => {
    expect(inWindowCandles({ from: 2.3, to: 5.4 }, TEN).map((c) => c.t))
      .toEqual(['2026-10-03', '2026-10-04', '2026-10-05', '2026-10-06']);
  });

  it('leaves out a candle whose span ends before the range starts', () => {
    expect(inWindowCandles({ from: 2.6, to: 5.6 }, TEN).map((c) => c.t))
      .toEqual(['2026-10-04', '2026-10-05', '2026-10-06', '2026-10-07']);
  });

  it('clamps a range that runs past either end to the loaded candles', () => {
    expect(inWindowCandles({ from: -3, to: 20 }, TEN)).toHaveLength(10);
  });

  it('is empty for a null range, a range past the data, or no candles', () => {
    expect(inWindowCandles(null, TEN)).toEqual([]);
    expect(inWindowCandles({ from: 12, to: 15 }, TEN)).toEqual([]);
    expect(inWindowCandles({ from: 0, to: 5 }, [])).toEqual([]);
  });
});

describe('nyMidnight', () => {
  it('is 04:00Z in summer and 05:00Z in winter', () => {
    expect(iso(nyMidnight('2026-10-16'))).toBe('2026-10-16T04:00:00.000Z');
    expect(iso(nyMidnight('2026-01-01'))).toBe('2026-01-01T05:00:00.000Z');
  });

  it('reads the offset of the night itself on both changeover days', () => {
    expect(iso(nyMidnight('2026-03-08'))).toBe('2026-03-08T05:00:00.000Z');   // still EST
    expect(iso(nyMidnight('2026-03-09'))).toBe('2026-03-09T04:00:00.000Z');   // now EDT
    expect(iso(nyMidnight('2026-11-01'))).toBe('2026-11-01T04:00:00.000Z');   // still EDT
    expect(iso(nyMidnight('2026-11-02'))).toBe('2026-11-02T05:00:00.000Z');   // now EST
  });
});

describe('bucket instants', () => {
  it('reads an intraday start from its offset and a daily start as New York midnight', () => {
    expect(iso(bucketStartInstant('2026-10-16T08:00:00-04:00', '4H'))).toBe('2026-10-16T12:00:00.000Z');
    expect(iso(bucketStartInstant('2026-10-16', '1D'))).toBe('2026-10-16T04:00:00.000Z');
  });

  it('ends a 1H bucket one real hour later, the repeated fall-back hour included', () => {
    expect(iso(bucketEndInstant('2026-11-01T01:00:00-04:00', '1H'))).toBe('2026-11-01T06:00:00.000Z');
    expect(iso(bucketEndInstant('2026-11-01T01:00:00-05:00', '1H'))).toBe('2026-11-01T07:00:00.000Z');
    expect(iso(bucketEndInstant('2026-03-08T01:00:00-05:00', '1H'))).toBe('2026-03-08T07:00:00.000Z');
  });

  it('ends a 4H bucket on the wall clock: 3 real hours at spring forward, 5 at fall back', () => {
    expect(iso(bucketEndInstant('2026-03-08T00:00:00-05:00', '4H'))).toBe('2026-03-08T08:00:00.000Z');
    expect(iso(bucketEndInstant('2026-11-01T00:00:00-04:00', '4H'))).toBe('2026-11-01T09:00:00.000Z');
  });

  it('ends the 20:00 4H bucket at the next New York midnight', () => {
    expect(iso(bucketEndInstant('2026-10-16T20:00:00-04:00', '4H'))).toBe('2026-10-17T04:00:00.000Z');
  });

  it('ends a day at the next New York midnight and a week seven days on', () => {
    expect(iso(bucketEndInstant('2026-10-16', '1D'))).toBe('2026-10-17T04:00:00.000Z');
    expect(iso(bucketEndInstant('2026-10-31', '1D'))).toBe('2026-11-01T04:00:00.000Z');
    expect(iso(bucketEndInstant('2026-11-01', '1D'))).toBe('2026-11-02T05:00:00.000Z');
    expect(iso(bucketEndInstant('2026-10-26', '1W'))).toBe('2026-11-02T05:00:00.000Z');
    expect(iso(bucketEndInstant('2026-12-28', '1W'))).toBe('2027-01-04T05:00:00.000Z');
  });
});

describe('windowBounds', () => {
  it('runs from the first bucket start to the last bucket end', () => {
    const days = [candle({ t: '2026-10-14' }), candle({ t: '2026-10-15' })];
    expect(windowBounds(days, '1D'))
      .toEqual({ from: '2026-10-14T04:00:00.000Z', to: '2026-10-16T04:00:00.000Z' });
  });

  it('sits on bucket edges for intraday candles', () => {
    const hours = [candle({ t: '2026-10-16T10:00:00-04:00' }), candle({ t: '2026-10-16T15:00:00-04:00' })];
    expect(windowBounds(hours, '1H'))
      .toEqual({ from: '2026-10-16T14:00:00.000Z', to: '2026-10-16T20:00:00.000Z' });
  });

  it('agrees with inWindowCandles: a partly visible edge candle widens the bounds by its whole bucket', () => {
    const visible = inWindowCandles({ from: 2.3, to: 5.4 }, TEN);
    expect(windowBounds(visible, '1D'))
      .toEqual({ from: '2026-10-03T04:00:00.000Z', to: '2026-10-07T04:00:00.000Z' });
  });

  it('is null with no candles', () => {
    expect(windowBounds([], '1D')).toBeNull();
  });
});

describe('rangeStats', () => {
  const window = [
    candle({ t: '2026-10-14', o: 100, h: 110, l: 95, c: 105 }),
    candle({ t: '2026-10-15', o: 105, h: 108, l: 90, c: 92 }),
    candle({ t: '2026-10-16', o: 92, h: 120, l: 91, c: 118 }),
  ];

  it('measures the change from the first open to the last close', () => {
    const stats = rangeStats(window)!;
    expect(stats.change).toBeCloseTo(18, 9);
    expect(stats.changePct).toBeCloseTo(18, 9);
  });

  it('takes high and low from every in-window candle', () => {
    const stats = rangeStats(window)!;
    expect([stats.high, stats.low]).toEqual([120, 90]);
  });

  it('measures drawdown on closes against the running peak, as a positive magnitude', () => {
    expect(rangeStats(window)!.maxDrawdownPct).toBeCloseTo((13 / 105) * 100, 9);
  });

  it('ignores an intra-candle low: drawdown is within range on closes only', () => {
    const one = [candle({ o: 100, h: 101, l: 50, c: 100 })];
    expect(rangeStats(one)!.maxDrawdownPct).toBe(0);
    expect(rangeStats(one)!.low).toBe(50);
  });

  it('gives a flat window zero change and zero drawdown', () => {
    const flat = [candle({ o: 100, h: 100, l: 100, c: 100 }), candle({ o: 100, h: 100, l: 100, c: 100 })];
    expect(rangeStats(flat)).toEqual({ change: 0, changePct: 0, high: 100, low: 100, maxDrawdownPct: 0 });
  });

  it('gives a null drawdown when the running peak is not above zero', () => {
    const underwater = [candle({ o: -10, h: -2, l: -12, c: -5 }), candle({ o: -5, h: -1, l: -6, c: -3 })];
    expect(rangeStats(underwater)!.maxDrawdownPct).toBeNull();
  });

  it('gives a null change % on a zero opening equity', () => {
    expect(rangeStats([candle({ o: 0, h: 5, l: 0, c: 5 })])!.changePct).toBeNull();
  });

  it('is null with no candles', () => {
    expect(rangeStats([])).toBeNull();
  });
});

describe('nextTimeframe', () => {
  const pairs: [EquityTimeframe, EquityTimeframe][] = EQUITY_TIMEFRAMES.slice(0, -1)
    .map((finer, i) => [finer, EQUITY_TIMEFRAMES[i + 1]]);

  it('keeps 250 / ratio above 15 for every adjacent pair, so a step never bounces', () => {
    for (const [finer, coarser] of pairs) {
      const ratio = TF_RATIO[coarser];
      expect(TF_STEP_UP_BARS / ratio).toBeGreaterThan(TF_STEP_DOWN_BARS);
      // a step up at 251 bars lands near 251 / ratio bars and stays there
      expect(nextTimeframe(Math.floor((TF_STEP_UP_BARS + 1) / ratio), coarser, false)).toBe(coarser);
      // a step down at 14 bars lands near 14 x ratio bars and stays there
      expect(nextTimeframe((TF_STEP_DOWN_BARS - 1) * ratio, finer, false)).toBe(finer);
    }
  });

  it('steps up one timeframe above 250 bars and holds at 250', () => {
    expect(nextTimeframe(251, '1H', false)).toBe('4H');
    expect(nextTimeframe(251, '4H', false)).toBe('1D');
    expect(nextTimeframe(251, '1D', false)).toBe('1W');
    expect(nextTimeframe(250, '1H', false)).toBe('1H');
  });

  it('steps down one timeframe below 15 bars and holds at 15', () => {
    expect(nextTimeframe(14, '1W', false)).toBe('1D');
    expect(nextTimeframe(14, '1D', false)).toBe('4H');
    expect(nextTimeframe(14, '4H', false)).toBe('1H');
    expect(nextTimeframe(15, '1D', false)).toBe('1D');
  });

  it('stays put at the ends of the timeframe ladder', () => {
    expect(nextTimeframe(400, '1W', false)).toBe('1W');
    expect(nextTimeframe(3, '1H', false)).toBe('1H');
  });

  it('never steps down at the edge of history or with no bars in view', () => {
    expect(nextTimeframe(5, '1D', true)).toBe('1D');
    expect(nextTimeframe(0, '1D', false)).toBe('1D');
  });

  it('still steps up at the edge of history', () => {
    expect(nextTimeframe(300, '1H', true)).toBe('4H');
  });
});
