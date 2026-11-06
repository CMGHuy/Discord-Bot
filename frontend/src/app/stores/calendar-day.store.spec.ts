import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { CalendarDay, CalendarDayTrades, CalendarTrade, PnlCalendar } from '../api/models';
import { CalendarDayStore, sortTrades } from './calendar-day.store';

const DAY_URL = '/api/v1/calendar/pnl/day';
const MONTH_URL = '/api/v1/calendar/pnl';
const SPARK_URL = '/api/v1/calendar/pnl/day/sparklines';

const cell = (date: string, net: number | null, count = 1): CalendarDay =>
  ({ date, net_pnl_amount: net, net_r: net === null ? null : net / 50, trade_count: count, win_rate: null });

const monthBody = (month: string, days: CalendarDay[]): PnlCalendar => ({
  as_of: '2026-08-20T12:00:00Z', month, days,
  totals: { net_pnl_amount: null, net_r: null, trade_count: days.length, win_rate: null },
  longest_hold: null, day_of_week: [], best_day: null, worst_day: null,
  streak: { direction: null, days: 0 }, filters: { strategies: [], horizons: [] },
});

const AUGUST = monthBody('2026-08', [cell('2026-08-03', 30), cell('2026-08-05', -90), cell('2026-08-10', 120)]);

const trade = (over: Partial<CalendarTrade> = {}): CalendarTrade => ({
  trade_id: 'a'.repeat(16), plan_id: null, opened_at: '2026-08-03T14:00:00+00:00',
  ticker: 'AAPL', strategy: 'EMA20', horizon: '4w', direction: 'bullish',
  day: '2026-08-05', closed_at: '2026-08-05T20:00:00+00:00', outcome: 'win',
  pnl_amount: 50, r_multiple: 1, mfe_r: null, mae_r: null, exit_efficiency: null,
  tags: [], auto_lesson: null, leg_index: 0, leg_total: 1,
  entry_price: 100, exit_price: 105, stop_price: 95, tp1: 110, tp2: null,
  shares: 10, held_hours: 54, return_pct: 5, exit_reason: 'tp1',
  ...over,
});

const dayBody = (trades: CalendarTrade[]): CalendarDayTrades => ({
  as_of: '2026-08-20T12:00:00Z', date: '2026-08-05', trades, trade_count: trades.length,
  winners: 0, losers: 0, total_r: null, total_ccy: null, win_rate: null,
  avg_trade_r: null, worst_drawdown_r: null, contributors: [], detractors: [],
  context: { percentile: null, history_days: 0,
    vs_avg_day: { pnl_amount: null, r: null }, vs_weekday_avg: { pnl_amount: null, r: null } },
  breakdown: { strategy: [], horizon: [], direction: [], exit_reason: [] },
});

describe('sortTrades', () => {
  const rows = [
    trade({ trade_id: 'a', ticker: 'MSFT', pnl_amount: 10, r_multiple: null, closed_at: '2026-08-05T15:00:00Z' }),
    trade({ trade_id: 'b', ticker: 'AAPL', pnl_amount: null, r_multiple: 2, closed_at: '2026-08-05T13:00:00Z' }),
    trade({ trade_id: 'c', ticker: 'NVDA', pnl_amount: 50, r_multiple: -1, closed_at: '2026-08-05T14:00:00Z' }),
  ];
  const ids = (sorted: CalendarTrade[]) => sorted.map((t) => t.trade_id);

  it('sorts P&L and R descending with nulls last, close time ascending, ticker A-Z', () => {
    expect(ids(sortTrades(rows, 'pnl'))).toEqual(['c', 'a', 'b']);
    expect(ids(sortTrades(rows, 'r'))).toEqual(['b', 'c', 'a']);
    expect(ids(sortTrades(rows, 'closed'))).toEqual(['b', 'c', 'a']);
    expect(ids(sortTrades(rows, 'ticker'))).toEqual(['b', 'a', 'c']);
  });

  it('never mutates its input', () => {
    sortTrades(rows, 'ticker');
    expect(ids(rows)).toEqual(['a', 'b', 'c']);
  });
});

describe('CalendarDayStore', () => {
  let store: InstanceType<typeof CalendarDayStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        CalendarDayStore,
      ],
    });
    store = TestBed.inject(CalendarDayStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const open = (date: string | null, strategy: string | null = null, horizon: string | null = null) => {
    store.setRoute(date, strategy, horizon);
    store.resolve().subscribe();
  };
  const monthReq = (month: string) =>
    backend.expectOne((r) => r.url === MONTH_URL && r.params.get('month') === month);

  it('asks for the day and its month together, with the filters, and the sparklines only after the day', () => {
    open('2026-08-05', 'VWAP', null);
    const day = backend.expectOne((r) => r.url === DAY_URL);
    const month = monthReq('2026-08');                 // both open at once: parallel
    expect(day.request.params.get('date')).toBe('2026-08-05');
    expect(day.request.params.get('strategy')).toBe('VWAP');
    expect(day.request.params.has('horizon')).toBe(false);
    expect(month.request.params.get('strategy')).toBe('VWAP');
    backend.expectNone((r) => r.url === SPARK_URL);

    day.flush(dayBody([trade()]));
    month.flush(AUGUST);
    expect(store.loading()).toBe(false);
    expect(store.empty()).toBe(false);
    expect(store.trades()).toHaveLength(1);
    expect(store.sparklines()).toBeNull();             // the page renders before them

    const spark = backend.expectOne((r) => r.url === SPARK_URL);
    expect(spark.request.params.get('date')).toBe('2026-08-05');
    expect(spark.request.params.get('strategy')).toBe('VWAP');
    spark.flush({ as_of: 'x', date: '2026-08-05', truncated: false, series: { ['a'.repeat(16) + ':0']: null } });
    expect(store.sparklines()?.truncated).toBe(false);
    backend.verify();
  });

  it('treats a 404 day as the empty state with working prev/next, and asks for no sparklines', () => {
    open('2026-08-04');
    backend.expectOne((r) => r.url === DAY_URL)
      .flush({ error: { code: 'not_found', message: 'no closed trades on 2026-08-04' } },
             { status: 404, statusText: 'Not Found' });
    monthReq('2026-08').flush(AUGUST);
    expect(store.empty()).toBe(true);
    expect(store.error()).toBeNull();
    expect(store.day()).toBeNull();
    expect(store.prevDay()).toBe('2026-08-03');
    expect(store.nextDay()).toBe('2026-08-05');
    backend.verify();
  });

  it('makes no request at all for a malformed or impossible date', () => {
    for (const bad of ['2026-02-30', 'abc', '2026-8-3', null]) {
      open(bad);
      backend.verify();
      expect(store.date()).toBeNull();
      expect(store.empty()).toBe(true);
    }
  });

  it('looks one month back for prev at the first trading day of a month', () => {
    open('2026-08-03');
    backend.expectOne((r) => r.url === DAY_URL).flush(dayBody([trade()]));
    monthReq('2026-08').flush(AUGUST);
    monthReq('2026-07').flush(monthBody('2026-07', [
      cell('2026-07-28', 10), cell('2026-07-30', 0, 0),     // the 30th had no closes
    ]));
    expect(store.prevDay()).toBe('2026-07-28');
    expect(store.nextDay()).toBe('2026-08-05');
    backend.expectNone((r) => r.url === MONTH_URL && r.params.get('month') === '2026-09');
  });

  it('looks one month ahead for next at the last trading day, and is null when that month is empty', () => {
    open('2026-08-10');
    backend.expectOne((r) => r.url === DAY_URL).flush(dayBody([trade()]));
    monthReq('2026-08').flush(AUGUST);
    monthReq('2026-09').flush(monthBody('2026-09', []));
    expect(store.prevDay()).toBe('2026-08-05');
    expect(store.nextDay()).toBeNull();
  });

  it('shows an error, not the empty state, when the day route fails for another reason', () => {
    open('2026-08-05');
    monthReq('2026-08').flush(AUGUST);
    backend.expectOne((r) => r.url === DAY_URL)
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    expect(store.error()).toBe('The admin is not responding -- these figures may be stale.');
    expect(store.empty()).toBe(false);
    expect(store.loading()).toBe(false);
  });

  it('derives sort, month context, filter params and the legs flag', () => {
    open('2026-08-05', null, '4w');
    backend.expectOne((r) => r.url === DAY_URL).flush(dayBody([
      trade({ trade_id: 'x', ticker: 'MSFT', pnl_amount: 5 }),
      trade({ trade_id: 'y', ticker: 'AAPL', pnl_amount: 40, leg_index: 1, leg_total: 2 }),
    ]));
    monthReq('2026-08').flush(AUGUST);
    expect(store.trades().map((t) => t.trade_id)).toEqual(['y', 'x']);   // default: P&L
    store.setSort('ticker');
    expect(store.trades().map((t) => t.ticker)).toEqual(['AAPL', 'MSFT']);
    expect(store.monthCtx()?.rank).toBe(3);
    expect(store.monthCtx()?.rankOf).toBe(3);
    expect(store.filterParams()).toEqual({ horizon: '4w' });
    expect(store.hasLegs()).toBe(true);
  });

  it('drops a sparklines answer for a date the page has already left', () => {
    open('2026-08-05');
    backend.expectOne((r) => r.url === DAY_URL).flush(dayBody([trade()]));
    monthReq('2026-08').flush(AUGUST);
    const late = backend.expectOne((r) => r.url === SPARK_URL);
    store.setRoute('2026-08-10', null, null);
    late.flush({ as_of: 'x', date: '2026-08-05', truncated: false, series: {} });
    expect(store.sparklines()).toBeNull();
  });

  it('leaves the new route untouched when a superseded request answers late', () => {
    open('2026-08-05');
    const oldDay = backend.expectOne((r) => r.url === DAY_URL);
    const oldMonth = monthReq('2026-08');
    store.setRoute('2026-09-02', null, null);
    oldDay.flush(dayBody([trade()]));
    oldMonth.flush(AUGUST);
    expect(store.date()).toBe('2026-09-02');
    expect(store.day()).toBeNull();
    expect(store.month()).toBeNull();
    expect(store.empty()).toBe(false);
    backend.expectNone((r) => r.url === SPARK_URL);
  });

  it('drops an old sparklines answer when only the filter changed', () => {
    open('2026-08-05', 'VWAP', null);
    backend.expectOne((r) => r.url === DAY_URL).flush(dayBody([trade()]));
    monthReq('2026-08').flush(AUGUST);
    const late = backend.expectOne((r) => r.url === SPARK_URL);
    store.setRoute('2026-08-05', 'EMA20', null);
    late.flush({ as_of: 'x', date: '2026-08-05', truncated: false, series: {} });
    expect(store.sparklines()).toBeNull();
  });

  it('shows the error and not the empty state when a 404 day is followed by a failing month', () => {
    open('2026-08-04');
    backend.expectOne((r) => r.url === DAY_URL)
      .flush({ error: { code: 'not_found', message: 'none' } }, { status: 404, statusText: 'Not Found' });
    monthReq('2026-08')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    expect(store.error()).toBe('The admin is not responding -- these figures may be stale.');
    expect(store.empty()).toBe(false);
    expect(store.loading()).toBe(false);
  });

  it('keeps the figures through a same-URL refresh, and keeps them when that refresh fails', () => {
    open('2026-08-05', 'VWAP', null);
    backend.expectOne((r) => r.url === DAY_URL).flush(dayBody([trade()]));
    monthReq('2026-08').flush(AUGUST);
    backend.expectOne((r) => r.url === SPARK_URL).flush(
      { as_of: 'x', date: '2026-08-05', truncated: false, series: {} });
    const before = store.day();

    open('2026-08-05', 'VWAP', null);                  // RouteRefreshService: same URL again
    expect(store.day()).toBe(before);
    expect(store.month()).not.toBeNull();
    expect(store.sparklines()).not.toBeNull();
    expect(store.prevDay()).toBe('2026-08-03');

    backend.expectOne((r) => r.url === DAY_URL)
      .flush({ error: { code: 'unavailable', message: 'x' } }, { status: 503, statusText: 'x' });
    expect(store.day()).toBe(before);
    expect(store.error()).not.toBeNull();
    expect(store.empty()).toBe(false);
  });

  it('still clears the figures when the date or a filter changes', () => {
    open('2026-08-05', 'VWAP', null);
    backend.expectOne((r) => r.url === DAY_URL).flush(dayBody([trade()]));
    monthReq('2026-08').flush(AUGUST);
    store.setRoute('2026-08-05', 'EMA20', null);
    expect(store.day()).toBeNull();
    store.setRoute('2026-08-10', 'EMA20', null);
    expect(store.month()).toBeNull();
  });
});

/* v217 V217-4 (v205 P3-b): the day route carries prev_day / next_day, so the
 * day page asks for no neighbouring month. The month lookup (`loadEdge`) is
 * kept only for a field the route did not send (an older backend) and for a
 * 404 day, whose body carries no fields. The existing edge specs above use
 * `dayBody()` without the fields and stay as the fallback path. */
describe('CalendarDayStore server neighbours (v217)', () => {
  let store: InstanceType<typeof CalendarDayStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        CalendarDayStore,
      ],
    });
    store = TestBed.inject(CalendarDayStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const open = (date: string) => {
    store.setRoute(date, null, null);
    store.resolve().subscribe();
  };
  const dayReq = () => backend.expectOne((r) => r.url === DAY_URL);
  const monthReq = (month: string) =>
    backend.expectOne((r) => r.url === MONTH_URL && r.params.get('month') === month);
  const noMonth = (month: string) =>
    backend.expectNone((r) => r.url === MONTH_URL && r.params.get('month') === month);
  const withEdges = (prev: string | null, next: string | null): CalendarDayTrades =>
    ({ ...dayBody([trade()]), prev_day: prev, next_day: next });
  const NOT_FOUND = { error: { code: 'not_found', message: 'no closed trades' } };

  it('takes both neighbours from the day response and asks for no adjacent month', () => {
    open('2026-08-03');                                // first trading day of AUGUST
    dayReq().flush(withEdges('2026-07-28', '2026-08-05'));
    monthReq('2026-08').flush(AUGUST);
    expect(store.prevDay()).toBe('2026-07-28');
    expect(store.nextDay()).toBe('2026-08-05');
    noMonth('2026-07');
    noMonth('2026-09');
    backend.expectOne((r) => r.url === SPARK_URL);     // the day still gets its sparklines
    backend.verify();
  });

  it('finds a neighbour more than a month away from the server field alone', () => {
    open('2026-08-10');                                // last trading day of AUGUST
    dayReq().flush(withEdges('2026-08-05', '2026-11-02'));
    monthReq('2026-08').flush(AUGUST);
    expect(store.nextDay()).toBe('2026-11-02');        // the one-month lookup would have said null
    expect(store.prevDay()).toBe('2026-08-05');
    noMonth('2026-09');
    noMonth('2026-07');
  });

  it('treats null at both ends as measured: no month lookup, no neighbour', () => {
    open('2026-08-05');
    dayReq().flush(withEdges(null, null));
    monthReq('2026-08').flush(monthBody('2026-08', [cell('2026-08-05', 30)]));
    expect(store.prevDay()).toBeNull();
    expect(store.nextDay()).toBeNull();
    expect(store.prevEdge()).toBeNull();
    expect(store.nextEdge()).toBeNull();
    noMonth('2026-07');
    noMonth('2026-09');
  });

  it('lets the month grid neighbour win over the server field, as before', () => {
    open('2026-08-05');
    dayReq().flush(withEdges('2026-07-01', '2026-09-30'));
    monthReq('2026-08').flush(AUGUST);
    expect(store.prevDay()).toBe('2026-08-03');
    expect(store.nextDay()).toBe('2026-08-10');
    noMonth('2026-07');
    noMonth('2026-09');
  });

  it('looks up the adjacent month only for the side the response did not send', () => {
    open('2026-08-10');
    dayReq().flush({ ...dayBody([trade()]), prev_day: '2026-08-05' });   // no next_day: older backend
    monthReq('2026-08').flush(AUGUST);
    monthReq('2026-09').flush(monthBody('2026-09', [cell('2026-09-02', 15)]));
    expect(store.nextDay()).toBe('2026-09-02');
    expect(store.prevDay()).toBe('2026-08-05');
    noMonth('2026-07');
  });

  it('decides after both answers when the month answers first: fields present, no lookup', () => {
    open('2026-08-03');
    monthReq('2026-08').flush(AUGUST);
    noMonth('2026-07');                                // nothing decided before the day answers
    dayReq().flush(withEdges('2026-07-28', '2026-08-05'));
    noMonth('2026-07');
    expect(store.prevDay()).toBe('2026-07-28');
  });

  it('decides after both answers when the month answers first: fields missing, one lookup', () => {
    open('2026-08-03');
    monthReq('2026-08').flush(AUGUST);
    noMonth('2026-07');
    dayReq().flush(dayBody([trade()]));                // no fields at all
    monthReq('2026-07').flush(monthBody('2026-07', [cell('2026-07-28', 10)]));
    expect(store.prevDay()).toBe('2026-07-28');
    noMonth('2026-09');
  });

  it('keeps the month lookup for a 404 day at a month edge', () => {
    open('2026-08-01');
    dayReq().flush(NOT_FOUND, { status: 404, statusText: 'Not Found' });
    monthReq('2026-08').flush(AUGUST);
    monthReq('2026-07').flush(monthBody('2026-07', [cell('2026-07-28', 10)]));
    expect(store.empty()).toBe(true);
    expect(store.prevDay()).toBe('2026-07-28');
    expect(store.nextDay()).toBe('2026-08-03');
    noMonth('2026-09');
  });

  it('decides nothing for a route the page has already left', () => {
    open('2026-08-03');
    const day = dayReq();
    const month = monthReq('2026-08');
    store.setRoute('2026-09-02', null, null);
    day.flush(dayBody([trade()]));                     // would have needed a July lookup
    month.flush(AUGUST);
    noMonth('2026-07');
    expect(store.prevEdge()).toBeNull();
  });
});
