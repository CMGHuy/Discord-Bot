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
  day_of_week: [], best_day: null, worst_day: null,
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
});
