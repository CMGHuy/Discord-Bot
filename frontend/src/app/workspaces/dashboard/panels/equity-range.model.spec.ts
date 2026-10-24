import { describe, expect, it } from 'vitest';

import { EquityCandle, EquityTimeframe } from '../../../api/models';
import { EQUITY_TIMEFRAMES } from '../../../ui/equity-chart-prefs';
import {
  SCOPE_PRESETS, ScopeSelection, chartWindowFor, presetBounds, rangeChipLabel, scopeToRequest, showsNowLabel,
  BREAKEVEN_BAND_PP,
  MIN_CLOSES_FOR_TONE,
  breakevenPairTone,
  drawdownTone,
  signTone,
  HISTORY_PAGE_LIMIT,
  PAGE_TRIGGER_CANDLES,
  mergeLatest,
  prependPage,
  shouldLoadOlder,
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

describe('history paging', () => {
  const day = (t: string, c = 100): EquityCandle => candle({ t, c });

  it('pages 200 candles and triggers within 20 candles of the oldest', () => {
    expect([HISTORY_PAGE_LIMIT, PAGE_TRIGGER_CANDLES]).toEqual([200, 20]);
    expect(shouldLoadOlder({ from: 19.5, to: 80 }, true, false)).toBe(true);
    expect(shouldLoadOlder({ from: 20, to: 80 }, true, false)).toBe(false);
  });

  it('never triggers without more history, while busy, or before the chart reports a range', () => {
    expect(shouldLoadOlder({ from: 2, to: 80 }, false, false)).toBe(false);
    expect(shouldLoadOlder({ from: 2, to: 80 }, true, true)).toBe(false);
    expect(shouldLoadOlder(null, true, false)).toBe(false);
  });

  it('prepends an older page and drops any candle already loaded', () => {
    const loaded = [day('2026-10-15'), day('2026-10-16')];
    const page = [day('2026-10-13'), day('2026-10-14'), day('2026-10-15', 999)];
    expect(prependPage(loaded, page).map((c) => [c.t, c.c])).toEqual([
      ['2026-10-13', 100], ['2026-10-14', 100], ['2026-10-15', 100], ['2026-10-16', 100]]);
  });

  it('keeps the two fall-back 01:00 hours apart: their t differs by offset', () => {
    const loaded = [day('2026-11-01T01:00:00-05:00')];
    const page = [day('2026-11-01T01:00:00-04:00')];
    expect(prependPage(loaded, page)).toHaveLength(2);
  });

  it('merges a refresh over the paged history, replacing from its first candle on', () => {
    const loaded = [day('2026-10-13'), day('2026-10-14'), day('2026-10-15'), day('2026-10-16', 1)];
    const latest = [day('2026-10-15'), day('2026-10-16', 2), day('2026-10-17')];
    expect(mergeLatest(loaded, latest).map((c) => [c.t, c.c])).toEqual([
      ['2026-10-13', 100], ['2026-10-14', 100], ['2026-10-15', 100],
      ['2026-10-16', 2], ['2026-10-17', 100]]);
  });

  it('takes the refresh whole when its first candle is not loaded', () => {
    const latest = [day('2026-10-20'), day('2026-10-21')];
    expect(mergeLatest([day('2026-10-13')], latest)).toEqual(latest);
    expect(mergeLatest([], latest)).toEqual(latest);
    expect(mergeLatest([day('2026-10-13')], [])).toEqual([]);
  });
});

describe('profit/loss tones', () => {
  it('colours by sign, and never a zero or a missing figure', () => {
    expect([signTone(12.5), signTone(-0.01), signTone(0), signTone(null)])
      .toEqual(['pos', 'neg', 'neutral', 'neutral']);
  });

  it('colours any non-zero drawdown as a loss', () => {
    expect([drawdownTone(3.2), drawdownTone(-3.2), drawdownTone(0), drawdownTone(null)])
      .toEqual(['neg', 'neg', 'neutral', 'neutral']);
  });

  it('judges win rate against the breakeven its payoff implies, with a 0.5 pp band', () => {
    expect(BREAKEVEN_BAND_PP).toBe(0.5);
    // payoff 1 -> breakeven 50 %
    expect([50.6, 50.5, 50.4, 49.6, 49.5, 49.4].map((wr) => breakevenPairTone(wr, 1, 20)))
      .toEqual(['pos', 'neutral', 'neutral', 'neutral', 'neutral', 'neg']);
  });

  it('reads a low payoff on a high win rate as profitable: the pair, not each alone', () => {
    // payoff 0.8 -> breakeven 55.6 %; 65 % clears it
    expect(breakevenPairTone(65, 0.8, 30)).toBe('pos');
    // payoff 2.34 -> breakeven 29.9 %; 49.1 % clears it
    expect(breakevenPairTone(49.1, 2.34, 30)).toBe('pos');
    // payoff 0.5 -> breakeven 66.7 %; 60 % misses it
    expect(breakevenPairTone(60, 0.5, 30)).toBe('neg');
  });

  it('stays neutral with a missing figure, a payoff of zero or less, or fewer than 5 closes', () => {
    expect(MIN_CLOSES_FOR_TONE).toBe(5);
    expect([breakevenPairTone(null, 1.2, 20), breakevenPairTone(60, null, 20),
            breakevenPairTone(60, 1.2, null)]).toEqual(['neutral', 'neutral', 'neutral']);
    expect([breakevenPairTone(60, 0, 20), breakevenPairTone(60, -1, 20)])
      .toEqual(['neutral', 'neutral']);
    expect([breakevenPairTone(90, 3, 4), breakevenPairTone(90, 3, 5)]).toEqual(['neutral', 'pos']);
  });
});

describe('scope presets (§ 1, § 6)', () => {
  const at = (s: string) => new Date(s);
  /** New York wall clock of an ISO instant, `YYYY-MM-DD HH:mm`. */
  const nyWall = (s: string) => new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(s)).replace(',', '');

  // Wed 21 Oct 2026, 10:00 in New York.
  const NOW = at('2026-10-21T14:00:00Z');

  it('re-exports the presets from the prefs module', () => {
    expect(SCOPE_PRESETS).toHaveLength(8);
  });

  it('reaches back per preset, to 00:00 New York, and ends at the next New York midnight', () => {
    const to = '2026-10-22T04:00:00.000Z';
    expect(presetBounds('5D', NOW)).toEqual({ from: '2026-10-15T04:00:00.000Z', to });
    expect(presetBounds('1M', NOW)).toEqual({ from: '2026-09-21T04:00:00.000Z', to });
    expect(presetBounds('3M', NOW)).toEqual({ from: '2026-07-21T04:00:00.000Z', to });
    expect(presetBounds('6M', NOW)).toEqual({ from: '2026-04-21T04:00:00.000Z', to });
    expect(presetBounds('YTD', NOW)).toEqual({ from: '2026-01-01T05:00:00.000Z', to });
    expect(presetBounds('1Y', NOW)).toEqual({ from: '2025-10-21T04:00:00.000Z', to });
  });

  it('puts every bound on a New York midnight, across both DST changeovers', () => {
    const nows = ['2026-03-09T15:00:00Z', '2026-11-02T15:00:00Z', '2026-01-01T12:00:00Z', NOW.toISOString()];
    for (const now of nows) {
      for (const preset of ['5D', '1M', '3M', '6M', 'YTD', '1Y'] as const) {
        const { from, to } = presetBounds(preset, at(now));
        expect(nyWall(from).endsWith('00:00')).toBe(true);
        expect(nyWall(to).endsWith('00:00')).toBe(true);
      }
    }
    // Monday after the November fall-back: from is EDT, to is EST.
    expect(presetBounds('5D', at('2026-11-02T15:00:00Z')))
      .toEqual({ from: '2026-10-27T04:00:00.000Z', to: '2026-11-03T05:00:00.000Z' });
    // Monday after the March spring-forward: from is EST, to is EDT.
    expect(presetBounds('1M', at('2026-03-09T15:00:00Z')))
      .toEqual({ from: '2026-02-09T05:00:00.000Z', to: '2026-03-10T04:00:00.000Z' });
  });

  it('skips the weekend for 5D', () => {
    // Sun 25 Oct: the five weekdays are Fri 23 back to Mon 19.
    expect(presetBounds('5D', at('2026-10-25T15:00:00Z')).from).toBe('2026-10-19T04:00:00.000Z');
  });

  it('clamps a month back to the shorter month', () => {
    expect(presetBounds('1M', at('2026-03-31T15:00:00Z')).from).toBe('2026-02-28T05:00:00.000Z');
  });

  it('reads YTD on the New York calendar, 1 Jan included', () => {
    // 07:00 New York on 1 Jan: the year just began.
    expect(presetBounds('YTD', at('2026-01-01T12:00:00Z')))
      .toEqual({ from: '2026-01-01T05:00:00.000Z', to: '2026-01-02T05:00:00.000Z' });
    // 22:00 New York on 31 Dec (already 1 Jan in Berlin): still last year.
    expect(presetBounds('YTD', at('2026-01-01T03:00:00Z')))
      .toEqual({ from: '2025-01-01T05:00:00.000Z', to: '2026-01-01T05:00:00.000Z' });
  });

  it('keeps `to` stable within a New York day and moves it when the next one opens', () => {
    const to = (s: string) => presetBounds('3M', at(s)).to;
    expect(to('2026-10-21T04:00:00Z')).toBe('2026-10-22T04:00:00.000Z');
    expect(to('2026-10-22T03:59:59Z')).toBe('2026-10-22T04:00:00.000Z');
    expect(to('2026-10-22T04:00:00Z')).toBe('2026-10-23T04:00:00.000Z');
  });

  it('gives the chart today’s New York day for 1D, all history for All, the bounds otherwise', () => {
    expect(chartWindowFor('1D', NOW))
      .toEqual({ from: '2026-10-21T04:00:00.000Z', to: '2026-10-22T04:00:00.000Z' });
    expect(chartWindowFor('All', NOW)).toBeNull();
    expect(chartWindowFor('6M', NOW)).toEqual(presetBounds('6M', NOW));
  });

  it('maps a scope to its request: 1D stays the Berlin today, All is all, the rest are ranges', () => {
    const preset = (p: '1D' | 'All' | '3M'): ScopeSelection => ({ kind: 'preset', preset: p });
    const window = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
    expect(scopeToRequest(preset('1D'), NOW)).toEqual({ mode: 'today', window: null });
    expect(scopeToRequest(preset('All'), NOW)).toEqual({ mode: 'all', window: null });
    expect(scopeToRequest(preset('3M'), NOW)).toEqual({ mode: 'range', window: presetBounds('3M', NOW) });
    expect(scopeToRequest({ kind: 'range', window }, NOW)).toEqual({ mode: 'range', window });
  });

  it('labels a Range chip with its New York dates, `to` exclusive', () => {
    expect(rangeChipLabel({ from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' }))
      .toBe('3 Sep – 18 Oct');
    expect(rangeChipLabel({ from: '2025-12-29T05:00:00.000Z', to: '2026-01-03T05:00:00.000Z' }))
      .toBe('29 Dec 2025 – 2 Jan 2026');
    expect(rangeChipLabel({ from: '2026-10-16T04:00:00.000Z', to: '2026-10-17T04:00:00.000Z' }))
      .toBe('16 Oct');
    // Four 1H candles inside one day, and an empty window.
    expect(rangeChipLabel({ from: '2026-10-16T14:00:00.000Z', to: '2026-10-16T18:00:00.000Z' }))
      .toBe('16 Oct');
    expect(rangeChipLabel({ from: '2026-10-16T14:00:00.000Z', to: '2026-10-16T14:00:00.000Z' }))
      .toBe('16 Oct');
  });

  it('shows the "now" sub-label everywhere but 1D', () => {
    expect(showsNowLabel({ kind: 'preset', preset: '1D' })).toBe(false);
    expect(showsNowLabel({ kind: 'preset', preset: '5D' })).toBe(true);
    expect(showsNowLabel({ kind: 'preset', preset: 'All' })).toBe(true);
    expect(showsNowLabel({ kind: 'range', window: { from: 'a', to: 'b' } })).toBe(true);
  });
});
