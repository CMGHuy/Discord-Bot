import { HttpRequest, provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideLocationMocks } from '@angular/common/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Routes, provideRouter, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { of } from 'rxjs';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../../api/interceptors';
import {
  CalendarDay,
  CalendarDaySparklines,
  CalendarDayTrades,
  CalendarTrade,
  DayContext,
  PnlCalendar,
} from '../../../api/models';
import { CalendarDayStore } from '../../../stores/calendar-day.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { calendarRoutes } from '../calendar.routes';
import {
  CalendarDayPage,
  breakdownWinRate,
  longDate,
  monthLineGeometry,
  weekdayName,
} from './calendar-day';
import { ONE_DAY_CAVEAT, PAPER_CAPTION, R_TOOLTIP } from './day-copy';

const DAY_URL = '/api/v1/calendar/pnl/day';
const MONTH_URL = '/api/v1/calendar/pnl';
const SPARK_URL = '/api/v1/calendar/pnl/day/sparklines';

const cell = (date: string, net: number | null, r: number | null): CalendarDay =>
  ({ date, net_pnl_amount: net, net_r: r, trade_count: 1, win_rate: null });

const monthBody = (month: string, days: CalendarDay[]): PnlCalendar => ({
  as_of: '2026-08-20T12:00:00Z', month, days,
  totals: { net_pnl_amount: null, net_r: null, trade_count: days.length, win_rate: null },
  day_of_week: [], best_day: null, worst_day: null,
  streak: { direction: null, days: 0 }, filters: { strategies: [], horizons: [] },
});

/** Running P&L 30, -60, 60; 2026-08-05 is the worst of three. */
const AUGUST = monthBody('2026-08', [
  cell('2026-08-03', 30, 0.6), cell('2026-08-05', -90, -1.8), cell('2026-08-10', 120, 2.4),
]);

const trade = (over: Partial<CalendarTrade> = {}): CalendarTrade => ({
  trade_id: 'a'.repeat(16), plan_id: null, opened_at: '2026-08-03T14:00:00+00:00',
  ticker: 'AAPL', strategy: 'EMA20', horizon: '4w', direction: 'bullish',
  day: '2026-08-05', closed_at: '2026-08-05T15:00:00+00:00', outcome: 'win',
  pnl_amount: 40, r_multiple: 0.8, mfe_r: null, mae_r: null, exit_efficiency: null,
  tags: [], auto_lesson: null, leg_index: 0, leg_total: 1,
  entry_price: 100, exit_price: 104, stop_price: 95, tp1: 104, tp2: 110,
  shares: 10, held_hours: 49, return_pct: 4, exit_reason: 'tp1',
  ...over,
});

const LEG = trade({ leg_index: 1, leg_total: 2 });
const LOSER = trade({
  trade_id: 'b'.repeat(16), ticker: 'MSFT', strategy: 'VWAP', direction: 'bearish',
  closed_at: '2026-08-05T14:00:00+00:00', outcome: 'loss',
  pnl_amount: -130, r_multiple: -2.6, exit_reason: 'stop',
});

const CONTEXT: DayContext = {
  percentile: 87.3, history_days: 212,
  vs_avg_day: { pnl_amount: 12.5, r: 0.25 },
  vs_weekday_avg: { pnl_amount: -3, r: null },
};

const dayBody = (over: Partial<CalendarDayTrades> = {}): CalendarDayTrades => ({
  as_of: '2026-08-20T12:00:00Z', date: '2026-08-05', trades: [LEG, LOSER], trade_count: 2,
  winners: 1, losers: 1, total_r: -1.8, total_ccy: -90, win_rate: 50,
  avg_trade_r: -0.9, worst_drawdown_r: -2.6,
  contributors: [{ ticker: 'AAPL', r: 0.8 }], detractors: [{ ticker: 'MSFT', r: -2.6 }],
  context: CONTEXT,
  breakdown: {
    strategy: [
      { key: 'EMA20', n: 1, pnl_amount: 40, r: 0.8, win_rate: 100 },
      { key: 'VWAP', n: 1, pnl_amount: -130, r: -2.6, win_rate: 0 },
    ],
    horizon: [{ key: '4w', n: 2, pnl_amount: -90, r: -1.8, win_rate: 50 }],
    direction: [
      { key: 'bullish', n: 1, pnl_amount: 40, r: 0.8, win_rate: 100 },
      { key: 'bearish', n: 1, pnl_amount: -130, r: -2.6, win_rate: 0 },
    ],
    exit_reason: [
      { key: 'tp1', n: 1, pnl_amount: 40, r: 0.8, win_rate: 100 },
      { key: 'stop', n: 1, pnl_amount: -130, r: -2.6, win_rate: 0 },
    ],
  },
  ...over,
});

const SPARKS: CalendarDaySparklines = {
  as_of: '2026-08-20T12:00:00Z', date: '2026-08-05', truncated: false,
  series: {
    [`${'a'.repeat(16)}:1`]: {
      closes: [{ date: '2026-08-03', close: 100 }, { date: '2026-08-05', close: 104 }],
      exit_bar: 1, last_bar: '2026-08-28', stale: false,
      entry: 100, stop: 95, tp1: 104, tp2: 110, exit: 104, exit_date: '2026-08-05',
    },
    [`${'b'.repeat(16)}:0`]: null,
  },
};

const PREFERENCES = { resolve: () => of(undefined), values: () => ({}), update: () => undefined };

function configure(routes: Routes = []): void {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(routes, withComponentInputBinding()),
      provideLocationMocks(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      { provide: ConnectionStore, useValue: { currency: () => '€' } },
      { provide: PreferencesStore, useValue: PREFERENCES },
      ...(routes.length ? [] : [CalendarDayStore]),
    ],
  });
}

/** Answers whatever the store asked for: the day (or a 404), the month,
 *  any edge month (from `edges`, else empty) and the sparklines. */
function answer(day: CalendarDayTrades | 404, edges: Record<string, CalendarDay[]> = {}): void {
  const backend = TestBed.inject(HttpTestingController);
  const dayReq = backend.expectOne((r) => r.url === DAY_URL);
  if (day === 404) {
    dayReq.flush({ error: { code: 'not_found', message: 'no closed trades' } },
                 { status: 404, statusText: 'Not Found' });
  } else {
    dayReq.flush(day);
  }
  for (const req of backend.match((r) => r.url === MONTH_URL)) {
    const month = req.request.params.get('month')!;
    req.flush(month === '2026-08' ? AUGUST : monthBody(month, edges[month] ?? []));
  }
  for (const req of backend.match((r) => r.url === MONTH_URL)) {   // edge lookups made after the month
    const month = req.request.params.get('month')!;
    req.flush(monthBody(month, edges[month] ?? []));
  }
  for (const req of backend.match((r) => r.url === SPARK_URL)) req.flush(SPARKS);
}

async function open(
  date: string,
  day: CalendarDayTrades | 404 = dayBody(),
  edges: Record<string, CalendarDay[]> = {},
): Promise<ComponentFixture<CalendarDayPage>> {
  configure();
  const store = TestBed.inject(CalendarDayStore);
  store.setRoute(date, 'EMA20', null);
  store.resolve().subscribe();
  answer(day, edges);
  const fixture = TestBed.createComponent(CalendarDayPage);
  fixture.componentRef.setInput('date', date);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

const el = (fixture: ComponentFixture<unknown>) => fixture.nativeElement as HTMLElement;
const text = (root: HTMLElement, selector: string) =>
  root.querySelector(selector)?.textContent?.replace(/\s+/g, ' ').trim();
const click = async (fixture: ComponentFixture<unknown>, selector: string, label: string) => {
  const button = [...el(fixture).querySelectorAll<HTMLElement>(selector)]
    .find((b) => b.textContent?.trim().startsWith(label));
  button!.click();
  fixture.detectChanges();
  await fixture.whenStable();
};

describe('calendar-day helpers', () => {
  it('formats the long date and weekday in UTC', () => {
    expect(longDate('2026-08-05')).toBe('Wednesday, August 5, 2026');
    expect(weekdayName('2026-08-03')).toBe('Monday');
  });

  it('draws the month line through zero with the day marked', () => {
    const curve = [
      { date: '2026-08-03', value: 30 },
      { date: '2026-08-05', value: -60 },
      { date: '2026-08-10', value: 60 },
    ];
    expect(monthLineGeometry(curve, 1)).toEqual({
      path: 'M 0.00 15.50 L 120.00 53.00 L 240.00 3.00',
      marker: { x: 120, y: 53 },
      zeroY: 28,
    });
    expect(monthLineGeometry(curve, -1).marker).toBeNull();
    expect(monthLineGeometry([], -1)).toEqual({ path: '', marker: null, zeroY: null });
  });

  it('withholds win% below five rows', () => {
    const row = { key: 'EMA20', n: 4, pnl_amount: 10, r: 0.2, win_rate: 75 };
    expect(breakdownWinRate(row)).toBe('—');
    expect(breakdownWinRate({ ...row, n: 5, win_rate: 60 })).toBe('60%');
    expect(breakdownWinRate({ ...row, n: 9, win_rate: null })).toBe('—');
  });
});

describe('CalendarDayPage', () => {
  it('shows the paper caption, the long date and the seven tiles, R explained', async () => {
    const fixture = await open('2026-08-05');
    expect(text(el(fixture), '.caption')).toBe(PAPER_CAPTION);
    expect(text(el(fixture), '.long-date')).toBe('Wednesday, August 5, 2026');
    expect(el(fixture).querySelectorAll('.tiles sb-stat-tile')).toHaveLength(7);
    const explained = [...el(fixture).querySelectorAll('.tiles sb-stat-tile')]
      .filter((tile) => tile.getAttribute('title') === R_TOOLTIP);
    expect(explained).toHaveLength(3);
  });

  it('says once that scale-out legs count separately, only when there are legs', async () => {
    const legs = await open('2026-08-05');
    expect(text(el(legs), '.sample-note')).toBe('2 rows · scale-out legs count separately');
    const whole = await open('2026-08-05', dayBody({ trades: [trade(), LOSER] }));
    expect(el(whole).querySelector('.sample-note')).toBeNull();
  });

  it('compares the day with its N beside it, in neutral text, with the caveat', async () => {
    const root = el(await open('2026-08-05'));
    expect(text(root, '.percentile')).toBe('87th percentile of 212 other trading days');
    expect(text(root, '.compare .rank')).toBe('3rd best of 3 days in August 2026');
    expect(text(root, '.vs-day')).toBe('+12.50 € · +0.25R');
    expect(text(root, '.vs-weekday-label')).toBe('vs average Wednesday');
    expect(text(root, '.vs-weekday')).toBe('-3.00 € · —');
    expect(root.querySelectorAll('.compare .pos, .compare .neg')).toHaveLength(0);
    expect(text(root, '.caveat')).toBe(ONE_DAY_CAVEAT);
  });

  it('bands the percentile below 60 days and hides it below 20', async () => {
    const band = el(await open('2026-08-05', dayBody({
      context: { ...CONTEXT, percentile: 70, history_days: 40 },
    })));
    expect(text(band, '.percentile')).toBe('Top third of 40 other trading days · small sample');
    const hidden = el(await open('2026-08-05', dayBody({
      context: { ...CONTEXT, percentile: null, history_days: 12 },
    })));
    expect(text(hidden, '.percentile')).toBe('Only 12 trading days so far — percentile hidden');
  });

  it('renders a day with no net figure as dashes, never 0', async () => {
    const root = el(await open('2026-08-05', dayBody({
      context: {
        percentile: null, history_days: 100,
        vs_avg_day: { pnl_amount: null, r: null },
        vs_weekday_avg: { pnl_amount: null, r: null },
      },
    })));
    expect(text(root, '.percentile')).toBe('—');
    expect(text(root, '.vs-day')).toBe('—');
    expect(text(root, '.vs-weekday')).toBe('—');
  });

  it('draws the month so far with this day marked and month-to-date figures', async () => {
    const root = el(await open('2026-08-05'));
    expect(root.querySelector('svg.month-line circle.marker')).not.toBeNull();
    expect(text(root, '.mtd-pnl')).toBe('-60.00 €');
    expect(text(root, '.mtd-r')).toBe('-1.20R');
    expect(root.querySelector('.mtd-r')?.getAttribute('title')).toBe(R_TOOLTIP);
    expect(text(root, '.month-panel .rank')).toBe('3rd best of 3 days in August 2026');
  });

  it('breaks the day down by strategy first, P&L and R before win%, and switches tab', async () => {
    const fixture = await open('2026-08-05');
    const heads = [...el(fixture).querySelectorAll('.breakdown thead th')].map((th) => th.textContent?.trim());
    expect(heads).toEqual(['Strategy', 'n', 'P&L', 'R', 'Win %', '']);
    expect(el(fixture).querySelector('.breakdown thead th.r-head')?.getAttribute('title')).toBe(R_TOOLTIP);
    const keys = () => [...el(fixture).querySelectorAll('.breakdown-row .key')].map((k) => k.textContent?.trim());
    expect(keys()).toEqual(['EMA20', 'VWAP']);
    await click(fixture, 'sb-tab-bar button', 'Horizon');
    expect(keys()).toEqual(['4w']);
    expect(text(el(fixture), '.breakdown thead th')).toBe('Horizon');
  });

  it('greys win% out below five rows and shows it from five', async () => {
    const thin = el(await open('2026-08-05'));
    const cellOf = (root: HTMLElement) => root.querySelector('.breakdown-row .win');
    expect(cellOf(thin)?.textContent?.trim()).toBe('—');
    expect(cellOf(thin)?.classList.contains('withheld')).toBe(true);
    const wide = el(await open('2026-08-05', dayBody({
      breakdown: { ...dayBody().breakdown,
        strategy: [{ key: 'EMA20', n: 5, pnl_amount: 40, r: 0.8, win_rate: 60 }] },
    })));
    expect(cellOf(wide)?.textContent?.trim()).toBe('60%');
    expect(cellOf(wide)?.classList.contains('withheld')).toBe(false);
  });

  it('lists one card per row, sorted by P&L, and re-sorts by close time', async () => {
    const fixture = await open('2026-08-05');
    const tickers = () => [...el(fixture).querySelectorAll('sb-day-trade-card .ticker')]
      .map((t) => t.textContent?.trim());
    expect(text(el(fixture), '.trades-panel h2')).toBe('Trades (2)');
    expect(tickers()).toEqual(['AAPL', 'MSFT']);
    await click(fixture, 'sb-segmented button', 'Close time');
    expect(tickers()).toEqual(['MSFT', 'AAPL']);
    expect(el(fixture).querySelector('sb-day-trade-card a.open')?.getAttribute('href'))
      .toBe('/trades/' + 'b'.repeat(16));
  });

  it('gives each card its own sparkline, and a dash where there is none', async () => {
    const cards = el(await open('2026-08-05')).querySelectorAll('sb-day-trade-card');
    expect(cards[0].querySelector('sb-trade-sparkline svg')).not.toBeNull();
    expect(cards[1].querySelector('sb-trade-sparkline .spark-empty')).not.toBeNull();
  });

  it('shows a 404 day as the empty state, with working prev/next and the caption', async () => {
    const root = el(await open('2026-08-04', 404));
    expect(text(root, 'sb-empty-state .empty-title')).toBe('No closed trades on 2026-08-04 under this filter');
    expect(root.querySelector('a.prev')?.getAttribute('href')).toBe('/calendar/2026-08-03?strategy=EMA20');
    expect(root.querySelector('a.next')?.getAttribute('href')).toBe('/calendar/2026-08-05?strategy=EMA20');
    expect(root.querySelector('.tiles')).toBeNull();
    expect(text(root, '.caption')).toBe(PAPER_CAPTION);
  });

  it('steps to the next month at the month edge, skipping its empty days', async () => {
    const root = el(await open('2026-08-10', dayBody({ date: '2026-08-10' }), {
      '2026-09': [{ ...cell('2026-09-01', 0, 0), trade_count: 0 }, cell('2026-09-02', 15, 0.3)],
    }));
    expect(root.querySelector('a.prev')?.getAttribute('href')).toBe('/calendar/2026-08-05?strategy=EMA20');
    expect(root.querySelector('a.next')?.getAttribute('href')).toBe('/calendar/2026-09-02?strategy=EMA20');
  });

  it('disables a step with nowhere to go', async () => {
    const root = el(await open('2026-08-10', dayBody({ date: '2026-08-10' })));
    expect(root.querySelector('a.next')).toBeNull();
    expect(text(root, '.next.off')).toBe('next day ›');
  });

  it('goes back to the same filtered month', async () => {
    const root = el(await open('2026-08-05'));
    expect(text(root, 'a.back')).toBe('← Calendar · August 2026');
    expect(root.querySelector('a.back')?.getAttribute('href')).toBe('/calendar?month=2026-08&strategy=EMA20');
  });
});

describe('calendar/:date route', () => {
  const ROUTES: Routes = [{ path: 'calendar', children: calendarRoutes }];

  async function take(predicate: (r: HttpRequest<unknown>) => boolean): Promise<TestRequest> {
    const backend = TestBed.inject(HttpTestingController);
    for (let i = 0; i < 50; i++) {
      const [found] = backend.match(predicate);
      if (found) return found;
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    throw new Error('the expected request was never made');
  }

  it('keeps the list route first and the day route after it', () => {
    expect(calendarRoutes.map((r) => r.path)).toEqual(['', ':date']);
    expect(calendarRoutes[0].pathMatch).toBe('full');
  });

  it('hands the date and the filters from the URL to the day store', async () => {
    configure(ROUTES);
    const harness = await RouterTestingHarness.create();
    const navigation = harness.navigateByUrl('/calendar/2026-08-05?strategy=EMA20&horizon=4w');
    const day = await take((r) => r.url === DAY_URL);
    expect(day.request.params.get('date')).toBe('2026-08-05');
    expect(day.request.params.get('strategy')).toBe('EMA20');
    expect(day.request.params.get('horizon')).toBe('4w');
    day.flush(dayBody());
    (await take((r) => r.url === MONTH_URL)).flush(AUGUST);
    await navigation;
    (await take((r) => r.url === SPARK_URL)).flush(SPARKS);
    harness.detectChanges();
    expect(harness.routeDebugElement?.componentInstance).toBeInstanceOf(CalendarDayPage);
    expect(text(harness.routeNativeElement!, '.long-date')).toBe('Wednesday, August 5, 2026');
  });

  it('shows the empty state for an impossible date without a single request', async () => {
    configure(ROUTES);
    const harness = await RouterTestingHarness.create('/calendar/2026-02-30');
    TestBed.inject(HttpTestingController).verify();
    expect(text(harness.routeNativeElement!, 'sb-empty-state .empty-title'))
      .toBe('No closed trades on 2026-02-30 under this filter');
  });
});
