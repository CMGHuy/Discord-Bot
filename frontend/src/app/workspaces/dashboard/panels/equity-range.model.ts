import { EquityCandle, EquityTimeframe } from '../../../api/models';
import { EQUITY_TIMEFRAMES } from '../../../ui/equity-chart-prefs';
import { isIntraday } from './equity-candles.model';

/**
 * Pure helpers for the range-aware equity chart — spec v181 § 7. The chart
 * component, `EquityCandlesStore` and `DashboardStore` only wire chart events
 * and responses to these, so every rule is testable without a canvas.
 *
 * **One clock.** Equity candles are bucketed on the New York wall clock
 * (`swingbot/core/tracking/equity_candles.py`), so every time window here is
 * a run of whole New York buckets.
 */

/** A lightweight-charts logical range: bar `i` is centred on `i`. */
export interface LogicalWindow {
  from: number;
  to: number;
}

/** ISO UTC instants (`Date.toISOString()`), half-open `[from, to)`. */
export interface TimeWindow {
  from: string;
  to: string;
}

/** The no-hover readout of the visible range (§ 4). `maxDrawdownPct` is a
 *  non-negative magnitude: 3.2 means closes fell 3.2 % below their running
 *  peak; null when that peak is not above zero. */
export interface RangeStats {
  change: number;
  changePct: number | null;
  high: number;
  low: number;
  maxDrawdownPct: number | null;
}

/* -- in-window candles ---------------------------------------------------- */

/** Every candle whose bucket overlaps the visible logical range. Candle `i`
 *  spans `[i - 0.5, i + 0.5]`, so a partly visible edge candle counts whole;
 *  the readout, the baseline and the KPI window all use these same buckets. */
export function inWindowCandles(
  range: LogicalWindow | null,
  candles: readonly EquityCandle[],
): EquityCandle[] {
  if (range === null || candles.length === 0) return [];
  const first = Math.max(0, Math.floor(range.from + 0.5));
  const last = Math.min(candles.length - 1, Math.ceil(range.to - 0.5));
  return first > last ? [] : candles.slice(first, last + 1);
}

/* -- New York bucket edges ----------------------------------------------- */

const HOUR_MS = 3_600_000;
const NY_PARTS = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', hourCycle: 'h23',
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
});

/** New York's offset from UTC at `instantMs`, in ms (-4 h in summer). */
function nyOffsetMs(instantMs: number): number {
  const parts: Record<string, number> = {};
  for (const p of NY_PARTS.formatToParts(new Date(instantMs))) parts[p.type] = Number(p.value);
  const wallAsUtc = Date.UTC(parts['year'], parts['month'] - 1, parts['day'],
                             parts['hour'], parts['minute'], parts['second']);
  return wallAsUtc - Math.floor(instantMs / 1000) * 1000;
}

/** The instant of New York wall time `isoDate` `hour`:00 (`hour` may be 24).
 *  Two passes: the offset at a first guess, then at the candidate itself.
 *  Only called for 00/04/08/12/16/20, which are never skipped or repeated. */
function nyWallInstant(isoDate: string, hour: number): Date {
  const [y, m, d] = isoDate.split('-').map(Number);
  const wall = Date.UTC(y, m - 1, d, hour);
  const guess = wall - nyOffsetMs(wall + 5 * HOUR_MS);
  return new Date(wall - nyOffsetMs(guess));
}

function addDays(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

/** 00:00 New York on `isoDate` (`YYYY-MM-DD`), as an instant. */
export function nyMidnight(isoDate: string): Date {
  return nyWallInstant(isoDate, 0);
}

/** The instant a candle's bucket starts: its offset-carrying `t` for 1H/4H,
 *  New York midnight of its date for 1D/1W. */
export function bucketStartInstant(t: string, tf: EquityTimeframe): Date {
  return isIntraday(tf) ? new Date(Date.parse(t)) : nyMidnight(t.slice(0, 10));
}

const BUCKET_END: Record<EquityTimeframe, (t: string) => Date> = {
  // One real hour: the two fall-back 01:00 hours are two buckets.
  '1H': (t) => new Date(Date.parse(t) + HOUR_MS),
  // Wall clock: 3 real hours at spring forward, 5 at fall back.
  '4H': (t) => nyWallInstant(t.slice(0, 10), Number(t.slice(11, 13)) + 4),
  '1D': (t) => nyMidnight(addDays(t.slice(0, 10), 1)),
  '1W': (t) => nyMidnight(addDays(t.slice(0, 10), 7)),
};

/** The instant a candle's bucket ends: the next bucket's start. */
export function bucketEndInstant(t: string, tf: EquityTimeframe): Date {
  return BUCKET_END[tf](t);
}

/** `[first bucket start, last bucket end)` of in-order candles; null when
 *  there are none. */
export function windowBounds(
  candles: readonly EquityCandle[],
  tf: EquityTimeframe,
): TimeWindow | null {
  if (candles.length === 0) return null;
  return {
    from: bucketStartInstant(candles[0].t, tf).toISOString(),
    to: bucketEndInstant(candles[candles.length - 1].t, tf).toISOString(),
  };
}

/* -- range stats ---------------------------------------------------------- */

/** Peak-to-trough of closes as % of the running peak; null once the running
 *  peak is not above zero (a percentage of it would be meaningless). */
function maxDrawdownPct(candles: readonly EquityCandle[]): number | null {
  let peak = Number.NEGATIVE_INFINITY;
  let worst = 0;
  for (const { c } of candles) {
    peak = Math.max(peak, c);
    if (peak <= 0) return null;
    worst = Math.max(worst, ((peak - c) / peak) * 100);
  }
  return worst;
}

/** Equity change (first `o` to last `c`), high, low and max drawdown over
 *  the in-window candles; null when there are none. */
export function rangeStats(candles: readonly EquityCandle[]): RangeStats | null {
  if (candles.length === 0) return null;
  const first = candles[0];
  const change = candles[candles.length - 1].c - first.o;
  return {
    change,
    changePct: first.o === 0 ? null : (change / first.o) * 100,
    high: candles.reduce((max, c) => Math.max(max, c.h), Number.NEGATIVE_INFINITY),
    low: candles.reduce((min, c) => Math.min(min, c.l), Number.POSITIVE_INFINITY),
    maxDrawdownPct: maxDrawdownPct(candles),
  };
}

/* -- auto timeframe ------------------------------------------------------- */

export const TF_STEP_UP_BARS = 250;
export const TF_STEP_DOWN_BARS = 15;

/** How many buckets of the next finer timeframe one bucket holds at most:
 *  a 4H bucket holds 4 hours, a day 6 4H buckets, a week 7 sampled days.
 *  `TF_STEP_UP_BARS / ratio > TF_STEP_DOWN_BARS` for every adjacent pair is
 *  what stops a step from bouncing straight back (§ 3). */
export const TF_RATIO: Record<EquityTimeframe, number> = { '1H': 1, '4H': 4, '1D': 6, '1W': 7 };

/** The timeframe to show for `barCount` visible candles: one step coarser
 *  above 250, one finer below 15, else unchanged. Never steps down at the
 *  edge of history (`atHistoryEdge`, decided by the chart) or with no bars
 *  in view. */
export function nextTimeframe(
  barCount: number,
  tf: EquityTimeframe,
  atHistoryEdge: boolean,
): EquityTimeframe {
  const index = EQUITY_TIMEFRAMES.indexOf(tf);
  if (barCount > TF_STEP_UP_BARS) {
    return EQUITY_TIMEFRAMES[Math.min(index + 1, EQUITY_TIMEFRAMES.length - 1)];
  }
  if (barCount > 0 && barCount < TF_STEP_DOWN_BARS && !atHistoryEdge) {
    return EQUITY_TIMEFRAMES[Math.max(index - 1, 0)];
  }
  return tf;
}

/* -- history paging (§ 2) ------------------------------------------------- */

/** Candles asked for per older page. */
export const HISTORY_PAGE_LIMIT = 200;
/** Page once the view's left edge is within this many candles of the oldest. */
export const PAGE_TRIGGER_CANDLES = 20;

/** True when the view nears the oldest loaded candle (logical index 0), the
 *  last answer said older history exists, and no page is in flight. */
export function shouldLoadOlder(
  range: LogicalWindow | null,
  hasMore: boolean,
  busy: boolean,
): boolean {
  return range !== null && hasMore && !busy && range.from < PAGE_TRIGGER_CANDLES;
}

/** An older page in front of the loaded candles. A candle already loaded is
 *  not repeated; `t` is unique per bucket (the fall-back hours differ by
 *  offset), so it is the key. */
export function prependPage(
  loaded: readonly EquityCandle[],
  page: readonly EquityCandle[],
): EquityCandle[] {
  const known = new Set(loaded.map((c) => c.t));
  return [...page.filter((c) => !known.has(c.t)), ...loaded];
}

/** A refresh of the newest candles over paged history: loaded candles before
 *  the refresh's first one stay, everything from it on is replaced (the last
 *  candle grows between scans). When that first candle is not loaded, the
 *  refresh replaces everything, so no gap is ever bridged silently. */
export function mergeLatest(
  loaded: readonly EquityCandle[],
  latest: readonly EquityCandle[],
): EquityCandle[] {
  if (latest.length === 0) return [];
  const at = loaded.findIndex((c) => c.t === latest[0].t);
  return at < 0 ? [...latest] : [...loaded.slice(0, at), ...latest];
}
