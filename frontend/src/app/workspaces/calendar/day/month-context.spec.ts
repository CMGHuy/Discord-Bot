import { describe, expect, it } from 'vitest';

import { CalendarDay } from '../../../api/models';
import {
  FINAL_STOP_LABEL,
  ONE_DAY_CAVEAT,
  PAPER_CAPTION,
  R_TOOLTIP,
  legsSampleNote,
} from './day-copy';
import {
  PERCENTILE_BAND_DAYS,
  PERCENTILE_MIN_DAYS,
  WIN_RATE_MIN_N,
  adjacentTradingDay,
  isIsoDate,
  monthContext,
  monthOf,
  ordinal,
  percentileView,
} from './month-context';

const day = (
  date: string,
  net: number | null,
  r: number | null,
  count = 1,
): CalendarDay => ({ date, net_pnl_amount: net, net_r: r, trade_count: count, win_rate: null });

/** Deliberately out of date order: the helpers must sort, not trust input. */
const AUGUST: CalendarDay[] = [
  day('2026-08-10', 120, 2.5),
  day('2026-08-03', 30, 1.2, 2),
  day('2026-08-05', -90, -1.8),
  day('2026-08-06', null, null),     // every row unpriced: a trading day with no net
  day('2026-08-07', 0, 0, 0),        // no closes: never a trading day
  day('2026-08-12', 30, 0.4),
];
/** What `/calendar/pnl?month=2026-08` would put in `totals` for AUGUST. */
const AUGUST_TOTALS = { net_pnl_amount: 90, net_r: 2.3 };

describe('isIsoDate', () => {
  it('accepts real calendar dates', () => {
    expect(isIsoDate('2026-08-03')).toBe(true);
    expect(isIsoDate('2024-02-29')).toBe(true);
    expect(isIsoDate('2026-12-31')).toBe(true);
  });

  it('rejects impossible, malformed and missing values', () => {
    for (const bad of ['2026-02-30', '2025-02-29', '2026-13-01', '2026-00-10', '2026-08-00',
                       '2026-8-3', 'abc', '', '2026-08-03T00:00', ' 2026-08-03']) {
      expect(isIsoDate(bad), bad).toBe(false);
    }
    expect(isIsoDate(null)).toBe(false);
    expect(isIsoDate(undefined)).toBe(false);
  });
});

describe('monthOf', () => {
  it('is the YYYY-MM prefix', () => {
    expect(monthOf('2026-08-03')).toBe('2026-08');
  });
});

describe('adjacentTradingDay', () => {
  it('steps to the neighbouring trading day', () => {
    expect(adjacentTradingDay(AUGUST, '2026-08-05', -1)).toBe('2026-08-03');
    expect(adjacentTradingDay(AUGUST, '2026-08-05', 1)).toBe('2026-08-06');
  });

  it('skips a day with no closes', () => {
    expect(adjacentTradingDay(AUGUST, '2026-08-06', 1)).toBe('2026-08-10');
    expect(adjacentTradingDay(AUGUST, '2026-08-10', -1)).toBe('2026-08-06');
  });

  it('works from a date that is not in the month (a 404 day)', () => {
    expect(adjacentTradingDay(AUGUST, '2026-08-04', -1)).toBe('2026-08-03');
    expect(adjacentTradingDay(AUGUST, '2026-08-04', 1)).toBe('2026-08-05');
  });

  it('is null at the month edge, so the store looks one month over', () => {
    expect(adjacentTradingDay(AUGUST, '2026-08-03', -1)).toBeNull();
    expect(adjacentTradingDay(AUGUST, '2026-08-12', 1)).toBeNull();
    expect(adjacentTradingDay([], '2026-08-12', 1)).toBeNull();
  });
});

describe('monthContext', () => {
  it('ranks the day among the month and accumulates month-to-date', () => {
    const ctx = monthContext(AUGUST, '2026-08-10');
    expect(ctx.rank).toBe(1);
    expect(ctx.rankOf).toBe(4);
    expect(ctx.mtdPnl).toBe(60);
    expect(ctx.mtdR).toBe(1.9);
    expect(ctx.curve).toEqual([
      { date: '2026-08-03', value: 30 },
      { date: '2026-08-05', value: -60 },
      { date: '2026-08-10', value: 60 },
      { date: '2026-08-12', value: 90 },
    ]);
    expect(ctx.dayIndex).toBe(2);
  });

  it('gives tied days the same rank', () => {
    expect(monthContext(AUGUST, '2026-08-03').rank).toBe(2);
    expect(monthContext(AUGUST, '2026-08-12').rank).toBe(2);
    expect(monthContext(AUGUST, '2026-08-05').rank).toBe(4);
  });

  it('MTD on the last trading day equals the month totals', () => {
    const ctx = monthContext(AUGUST, '2026-08-12');
    expect(ctx.mtdPnl).toBe(AUGUST_TOTALS.net_pnl_amount);
    expect(ctx.mtdR).toBe(AUGUST_TOTALS.net_r);
    expect(ctx.curve.at(-1)?.value).toBe(AUGUST_TOTALS.net_pnl_amount);
  });

  it('leaves a null-net day unranked and off the curve, never counted as 0', () => {
    const ctx = monthContext(AUGUST, '2026-08-06');
    expect(ctx.rank).toBeNull();
    expect(ctx.dayIndex).toBe(-1);
    expect(ctx.rankOf).toBe(4);
    expect(ctx.mtdPnl).toBe(-60);
  });

  it('is all-null on an empty month', () => {
    expect(monthContext([], '2026-08-03')).toEqual({
      rank: null, rankOf: 0, mtdPnl: null, mtdR: null, curve: [], dayIndex: -1,
    });
  });
});

describe('ordinal', () => {
  it('suffixes like English, teens included', () => {
    const cases: Array<[number, string]> = [
      [1, '1st'], [2, '2nd'], [3, '3rd'], [4, '4th'], [11, '11th'], [12, '12th'],
      [13, '13th'], [21, '21st'], [22, '22nd'], [23, '23rd'], [87, '87th'],
      [100, '100th'], [101, '101st'], [111, '111th'],
    ];
    for (const [n, text] of cases) expect(ordinal(n)).toBe(text);
  });
});

describe('percentileView', () => {
  it('shows the exact percentile with its N from 60 other days', () => {
    expect(percentileView(87.3, 212)).toEqual({
      kind: 'exact', text: '87th percentile of 212 other trading days',
    });
    expect(percentileView(50, PERCENTILE_BAND_DAYS).kind).toBe('exact');
  });

  it('shows only a third, flagged small sample, below 60 days', () => {
    expect(percentileView(50, 59)).toEqual({
      kind: 'band', text: 'Middle third of 59 other trading days · small sample',
    });
    expect(percentileView(10, PERCENTILE_MIN_DAYS).text).toContain('Bottom third');
    expect(percentileView(90, 30).text).toContain('Top third');
    expect(percentileView(100, 30).text).toContain('Top third');
  });

  it('hides the percentile below 20 days and says why', () => {
    expect(percentileView(null, 19)).toEqual({
      kind: 'hidden', text: 'Only 19 trading days so far — percentile hidden',
    });
    // Even if a figure arrived, the page never shows one on 19 days.
    expect(percentileView(55, 19).kind).toBe('hidden');
  });

  it('renders a dash when the day itself has no net', () => {
    expect(percentileView(null, 100)).toEqual({ kind: 'hidden', text: '—' });
  });

  it('pins the thresholds', () => {
    expect([PERCENTILE_MIN_DAYS, PERCENTILE_BAND_DAYS, WIN_RATE_MIN_N]).toEqual([20, 60, 5]);
  });
});

describe('D7 copy', () => {
  it('is the spec text, verbatim', () => {
    expect(PAPER_CAPTION).toBe('Paper trades · P&L before commissions, fees and tax');
    expect(ONE_DAY_CAVEAT).toBe('One day is not evidence of edge.');
    expect(R_TOOLTIP).toBe("R = the trade's initial risk (entry to stop). +1R made what was risked.");
    expect(FINAL_STOP_LABEL).toBe('final stop');
    expect(legsSampleNote(7)).toBe('7 rows · scale-out legs count separately');
  });
});
