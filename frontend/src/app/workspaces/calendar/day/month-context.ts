import { CalendarDay } from '../../../api/models';

/* v165 D5 -- everything the day page derives from the month response it
 * already holds (`/calendar/pnl?month=`), so rank, month-to-date and the
 * month line can never disagree with the grid. Pure and string-dated, the
 * `calendar.helpers.ts` rule: no Date round trip for a calendar date. */

/** Below this many other trading days the percentile is hidden (D2/D7). */
export const PERCENTILE_MIN_DAYS = 20;
/** Below this many the percentile shows only as a third, "small sample". */
export const PERCENTILE_BAND_DAYS = 60;
/** Breakdown rows with fewer rows than this grey out win% as `—`. */
export const WIN_RATE_MIN_N = 5;

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** A real calendar date in `YYYY-MM-DD`. `2026-02-30`, `2026-8-3` and
 *  `abc` are all false, so the page shows its empty state without asking. */
export function isIsoDate(value: string | null | undefined): value is string {
  const match = ISO_DATE.exec(value ?? '');
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const dayOfMonth = Number(match[3]);
  if (month < 1 || month > 12 || dayOfMonth < 1) return false;
  // Day 0 of the next month is this month's last day; UTC, so no DST edge.
  return dayOfMonth <= new Date(Date.UTC(year, month, 0)).getUTCDate();
}

export function monthOf(date: string): string {
  return date.slice(0, 7);
}

/** Days with at least one close, in date order. */
function tradingDays(days: CalendarDay[]): CalendarDay[] {
  return days
    .filter((d) => d.trade_count > 0)
    .sort((a, b) => a.date.localeCompare(b.date));
}

/** The previous (`-1`) or next (`1`) trading day in `days`, or null at the
 *  month's edge. Comparison-based, so `date` need not be in `days`. */
export function adjacentTradingDay(
  days: CalendarDay[],
  date: string,
  step: 1 | -1,
): string | null {
  const dates = tradingDays(days).map((d) => d.date);
  if (step === 1) return dates.find((d) => d > date) ?? null;
  const before = dates.filter((d) => d < date);
  return before.length ? before[before.length - 1] : null;
}

export interface MonthContext {
  /** 1 = best day of the month; tied days share a rank. Null for a null-net day. */
  rank: number | null;
  /** Trading days with a non-null net -- the "of 14 days". */
  rankOf: number;
  mtdPnl: number | null;
  mtdR: number | null;
  /** Running month P&L per trading day with a net. */
  curve: { date: string; value: number }[];
  /** This day's index in `curve`, -1 when it is not on it. */
  dayIndex: number;
}

const round2 = (value: number): number => Math.round(value * 100) / 100;

function sumOrNull(values: Array<number | null>): number | null {
  const present = values.filter((v): v is number => v !== null);
  return present.length ? round2(present.reduce((a, b) => a + b, 0)) : null;
}

function rankOfDay(measured: CalendarDay[], date: string): number | null {
  const own = measured.find((d) => d.date === date);
  if (!own) return null;
  const net = own.net_pnl_amount as number;
  return 1 + measured.filter((d) => (d.net_pnl_amount as number) > net).length;
}

export function monthContext(days: CalendarDay[], date: string): MonthContext {
  const trading = tradingDays(days);
  const measured = trading.filter((d) => d.net_pnl_amount !== null);
  const upTo = trading.filter((d) => d.date <= date);
  let running = 0;
  const curve = measured.map((d) => {
    running = round2(running + (d.net_pnl_amount as number));
    return { date: d.date, value: running };
  });
  return {
    rank: rankOfDay(measured, date),
    rankOf: measured.length,
    mtdPnl: sumOrNull(upTo.map((d) => d.net_pnl_amount)),
    mtdR: sumOrNull(upTo.map((d) => d.net_r)),
    curve,
    dayIndex: curve.findIndex((p) => p.date === date),
  };
}

/** 1st, 2nd, 3rd, 4th, 11th, 12th, 13th, 21st ... */
export function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  const suffix = ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th';
  return `${n}${suffix}`;
}

export type PercentileView = { kind: 'hidden' | 'band' | 'exact'; text: string };

const THIRDS = ['Bottom third', 'Middle third', 'Top third'] as const;

/** D2/D7: N always beside the figure; a band below 60 days; hidden below 20. */
export function percentileView(percentile: number | null, historyDays: number): PercentileView {
  if (historyDays < PERCENTILE_MIN_DAYS) {
    return { kind: 'hidden', text: `Only ${historyDays} trading days so far — percentile hidden` };
  }
  if (percentile === null) return { kind: 'hidden', text: '—' };
  if (historyDays < PERCENTILE_BAND_DAYS) {
    const third = THIRDS[Math.min(2, Math.floor(percentile / (100 / 3)))];
    return { kind: 'band', text: `${third} of ${historyDays} other trading days · small sample` };
  }
  return {
    kind: 'exact',
    text: `${ordinal(Math.round(percentile))} percentile of ${historyDays} other trading days`,
  };
}
