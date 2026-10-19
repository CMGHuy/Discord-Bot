import { HttpRequest, provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  TestRequest,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideLocationMocks } from '@angular/common/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { Router, provideRouter, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { of } from 'rxjs';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { CalendarTrade, PnlCalendar } from '../../api/models';
import { BACKGROUND_REFRESH_INFO } from '../../routing/route-loading.service';
import { PreferencesStore } from '../../stores/preferences.store';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { Calendar } from './calendar';
import { calendarRoutes } from './calendar.routes';
import { CalendarStore } from '../../stores/calendar.store';
import { PAPER_CAPTION } from './day/day-copy';

const RESPONSE: PnlCalendar = {
  as_of: '2026-08-10T12:00:00Z',
  month: '2026-08',
  days: [
    { date: '2026-08-03', net_pnl_amount: 30, net_r: 1.2, trade_count: 2, win_rate: 50 },
    { date: '2026-08-05', net_pnl_amount: -90, net_r: -1.8, trade_count: 1, win_rate: 0 },
  ],
  totals: { net_pnl_amount: -60, net_r: -0.6, trade_count: 3, win_rate: 33.33 },
  day_of_week: [
    { weekday: 'Mon', avg_pnl_amount: 15, avg_r: 0.6, win_rate: 50, trade_count: 2 },
    { weekday: 'Tue', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
    { weekday: 'Wed', avg_pnl_amount: -90, avg_r: -1.8, win_rate: 0, trade_count: 1 },
    { weekday: 'Thu', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
    { weekday: 'Fri', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
  ],
  best_day: { date: '2026-08-03', net_pnl_amount: 30, net_r: 1.2, trade_count: 2, win_rate: 50 },
  worst_day: { date: '2026-08-05', net_pnl_amount: -90, net_r: -1.8, trade_count: 1, win_rate: 0 },
  streak: { direction: 'losing', days: 1 },
  filters: { strategies: ['EMA20', 'VWAP'], horizons: ['3m', '4w'] },
};

/**
 * Stand the component up and pin it to August 2026.
 *
 * The store's first load asks for whatever month the machine clock is in,
 * so it is answered and then followed by an explicit `setMonth('2026-08')`.
 * Without that second step the grid geometry would be laid out for the
 * current month while `dayIndex` held August dates, and every
 * `[data-date]` lookup below would miss for reasons that have nothing to
 * do with the code under test.
 */
export function seed(payload: PnlCalendar = RESPONSE): ComponentFixture<Calendar> {
  // The day drawer is a real `<dialog>`, and jsdom implements neither
  // showModal() nor close(); see the polyfill for why `<dialog>` stays.
  installDialogPolyfill();
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(
        withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor]),
      ),
      provideHttpClientTesting(),
      CalendarStore,
    ],
  });
  const fixture = TestBed.createComponent(Calendar);
  TestBed.inject(CalendarStore).load();
  fixture.detectChanges();

  const backend = TestBed.inject(HttpTestingController);
  backend.expectOne((r) => r.url === '/api/v1/calendar/pnl').flush(payload);

  fixture.componentInstance.store.setMonth('2026-08');
  backend.expectOne((r) => r.params.get('month') === '2026-08').flush(payload);
  fixture.detectChanges();
  return fixture;
}

const el = (fixture: ComponentFixture<Calendar>) =>
  fixture.nativeElement as HTMLElement;

describe('Calendar grid', () => {
  it('renders the month grid', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el(fixture).querySelector('.grid')).not.toBeNull();
  });

  it('drops the day-detail side pane -- the drawer already covers it', async () => {
    // It used to sit beside the grid and, unselected, only ever said
    // "Select a day to inspect its trades" -- a permanently half-empty box
    // duplicating what clicking a day already opens in the drawer.
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el(fixture).querySelector('.day-pane')).toBeNull();
    expect(el(fixture).textContent).not.toContain('Select a day to inspect its trades');
  });

  it('renders full weeks of seven cells', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    // August 2026 starts on a Saturday and runs 31 days, so the grid is six
    // rows: 5 leading cells + 31 + 6 trailing = 42.
    const rows = el(fixture).querySelectorAll('.week');
    expect(rows).toHaveLength(6);
    rows.forEach((row) => expect(row.querySelectorAll('.cell')).toHaveLength(7));
    // The first cell is the Monday before the 1st.
    expect(rows[0].querySelector('.cell')?.getAttribute('data-date')).toBe('2026-07-27');
  });

  it('shows money by default, not R', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const cell = el(fixture).querySelector('.cell[data-date="2026-08-03"] .value');
    expect(cell?.textContent).toContain('30');
    expect(cell?.textContent).not.toContain('R');
  });

  it('switches every cell to R when the metric toggles', async () => {
    const fixture = seed();
    await fixture.whenStable();

    fixture.componentInstance.store.setMetric('r');
    fixture.detectChanges();

    const cell = el(fixture).querySelector('.cell[data-date="2026-08-03"] .value');
    expect(cell?.textContent).toContain('R');
  });

  it('marks a selected calendar day with an accessible pressed state', async () => {
    const fixture = seed();
    await fixture.whenStable();
    const cell = el(fixture).querySelector('.cell[data-date="2026-08-03"]')!;
    (cell.querySelector('button') as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(fixture.componentInstance.store.selectedDay()).toBe('2026-08-03');
    expect(cell.classList.contains('selected')).toBe(true);
    expect(cell.querySelector('button')?.getAttribute('aria-pressed')).toBe('true');
  });

  it('signs the cell class so colour follows the displayed number', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const win = el(fixture).querySelector('.cell[data-date="2026-08-03"]');
    const loss = el(fixture).querySelector('.cell[data-date="2026-08-05"]');
    expect(win?.classList.contains('pos')).toBe(true);
    expect(loss?.classList.contains('neg')).toBe(true);
  });

  it('renders the weekend as inert but a quiet trading day as a clickable "0"', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    // 2026-08-01 is a Saturday; 2026-08-04 is a Tuesday with no closes.
    const weekend = el(fixture).querySelector('.cell[data-date="2026-08-01"]');
    const quiet = el(fixture).querySelector('.cell[data-date="2026-08-04"]');
    expect(weekend?.classList.contains('weekend')).toBe(true);
    expect(weekend?.querySelector('button')).toBeNull();
    expect(quiet?.classList.contains('weekend')).toBe(false);
    expect(quiet?.classList.contains('pos')).toBe(false);
    expect(quiet?.classList.contains('neg')).toBe(false);
    // A quiet trading day IS clickable (2026-09-14): "0" beats a blank cell,
    // and the drawer already reads correctly for a day with nothing in it.
    const button = quiet?.querySelector('button');
    expect(button).not.toBeNull();
    expect(button?.textContent).toContain('0');
  });

  it('offers the strategy and horizon vocabularies from the payload', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.componentInstance.store.strategyOptions()).toEqual([
      { value: 'EMA20', label: 'EMA20' },
      { value: 'VWAP', label: 'VWAP' },
    ]);
  });
});

describe('Calendar summary strip', () => {
  it("shows the visible month's pooled totals", async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const strip = el(fixture).querySelector('.totals');
    expect(strip?.textContent).toContain('60');   // net -60
    expect(strip?.textContent).toContain('3');    // 3 trades
    expect(strip?.textContent).toContain('33');   // 33.33% WR
  });

  it('lists all five weekdays even where there is no data', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const rows = el(fixture).querySelectorAll('.dow-row');
    expect(rows).toHaveLength(5);
    expect(rows[0].textContent).toContain('Mon');
    // Tuesday has n=0 and must read as absent, never as 0.00.
    expect(rows[1].textContent).toContain('—');
  });

  it('reports the month-summary figures from the visible trading days', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    // Month-over-month stats share one row (.totals) with the live-month
    // totals now, rather than a separate .month-summary row of their own.
    const summary = el(fixture).querySelector('.totals');
    // "Month total" was the same number as "Net this month" -- one tile.
    expect(summary?.textContent).not.toContain('Month total');
    expect(summary?.textContent).toContain('Net this month');
    expect(summary?.textContent).toContain('Winning days');
    expect(summary?.textContent).toContain('1 (50%)');
    expect(summary?.textContent).toContain('Average day');
    expect(summary?.textContent).toContain('Best day');
    expect(summary?.textContent).toContain('Worst day');
  });

  it('does not turn a no-trade month into invented summary values', async () => {
    const fixture = seed({
      ...RESPONSE,
      days: [],
      totals: { net_pnl_amount: 0, net_r: 0, trade_count: 0, win_rate: null },
      streak: { direction: null, days: 0 },
      best_day: null,
      worst_day: null,
    });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el(fixture).querySelector('.totals')).toBeNull();
  });

  it('switches the weekday table to R with the metric toggle', async () => {
    const fixture = seed();
    await fixture.whenStable();

    fixture.componentInstance.store.setMetric('r');
    fixture.detectChanges();

    const monday = el(fixture).querySelectorAll('.dow-row')[0];
    expect(monday.textContent).toContain('R');
  });
});

const TRADE: CalendarTrade = {
  trade_id: 'a'.repeat(16),
  ticker: 'AAPL',
  strategy: 'EMA20',
  horizon: '4w',
  direction: 'bullish',
  day: '2026-08-03',
  closed_at: '2026-08-03T20:00:00+00:00',
  outcome: 'win',
  pnl_amount: 50,
  r_multiple: 2,
  mfe_r: 2.4,
  mae_r: -0.3,
  exit_efficiency: 83,
  tags: ['clean-exit'],
  auto_lesson: 'Held to target.',
  plan_id: null,
  opened_at: '2026-08-01T14:30:00+00:00',
  leg_index: 0,
  leg_total: 1,
  entry_price: 100,
  exit_price: 110,
  stop_price: 95,
  tp1: 120,
  tp2: null,
  shares: 10,
  held_hours: 53.5,
  return_pct: 10,
  exit_reason: 'tp1',
};

describe('Calendar day drawer', () => {
  const openDay = async (fixture: ComponentFixture<Calendar>, trades: CalendarTrade[]) => {
    // `seed()` already pinned the month and flushed both grid requests.
    fixture.componentInstance.store.selectDay('2026-08-03');
    TestBed.inject(HttpTestingController)
      .expectOne((r) => r.url === '/api/v1/calendar/pnl/day')
      .flush({ as_of: '2026-08-10T12:00:00Z', date: '2026-08-03', trades, trade_count: trades.length,
        winners: 0, losers: 0, total_r: null, total_ccy: null,
        win_rate: null, avg_trade_r: null, worst_drawdown_r: null,
        contributors: [], detractors: [],
        context: { percentile: null, history_days: 0,
          vs_avg_day: { pnl_amount: null, r: null },
          vs_weekday_avg: { pnl_amount: null, r: null } },
        breakdown: { strategy: [], horizon: [], direction: [], exit_reason: [] } });
    await fixture.whenStable();
    fixture.detectChanges();
  };

  it('stays closed until a day is chosen', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el(fixture).querySelector('.day-row')).toBeNull();
  });

  it('lists every trade closed that day', async () => {
    const fixture = seed();
    await openDay(fixture, [TRADE, { ...TRADE, trade_id: 'b'.repeat(16), ticker: 'MSFT' }]);

    const rows = el(fixture).querySelectorAll('.day-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('AAPL');
    expect(rows[1].textContent).toContain('MSFT');
  });

  it('lists both legs of a scaled-out trade closed that day, each labelled', async () => {
    const fixture = seed();
    await openDay(fixture, [
      { ...TRADE, leg_index: 0, leg_total: 2 },
      { ...TRADE, leg_index: 1, leg_total: 2 },
    ]);

    const rows = el(fixture).querySelectorAll('.day-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].querySelector('.leg')?.textContent).toContain('Leg 1 of 2');
    expect(rows[1].querySelector('.leg')?.textContent).toContain('Leg 2 of 2');
  });

  it('does not label an unsplit trade as a leg', async () => {
    const fixture = seed();
    await openDay(fixture, [TRADE]);

    expect(el(fixture).querySelector('.day-row .leg')).toBeNull();
  });

  it('shows the journal half when the join found one', async () => {
    const fixture = seed();
    await openDay(fixture, [TRADE]);

    const row = el(fixture).querySelector('.day-row');
    expect(row?.textContent).toContain('Held to target.');
    expect(row?.textContent).toContain('clean-exit');
  });

  it('omits the journal half for an unjournaled trade rather than showing blanks', async () => {
    const fixture = seed();
    await openDay(fixture, [
      { ...TRADE, tags: [], auto_lesson: null, mfe_r: null, mae_r: null, exit_efficiency: null },
    ]);

    const row = el(fixture).querySelector('.day-row');
    expect(row?.textContent).toContain('AAPL');
    expect(row?.querySelector('.lesson')).toBeNull();
    expect(row?.querySelector('.tags')).toBeNull();
  });

  it('says so when a day comes back with nothing under the current filter', async () => {
    const fixture = seed();
    await openDay(fixture, []);

    expect(el(fixture).querySelector('.day-empty')).not.toBeNull();
    expect(el(fixture).querySelectorAll('.day-row')).toHaveLength(0);
  });

  it('clears the selection when the drawer is dismissed', async () => {
    const fixture = seed();
    await openDay(fixture, [TRADE]);

    fixture.componentInstance.store.closeDay();
    fixture.detectChanges();

    expect(fixture.componentInstance.store.selectedDay()).toBeNull();
    expect(el(fixture).querySelector('.day-row')).toBeNull();
  });

  it('offers the full day page, carrying the active filters', async () => {
    const fixture = seed();
    fixture.componentInstance.store.setStrategy('EMA20');
    TestBed.inject(HttpTestingController)
      .expectOne((r) => r.params.get('strategy') === 'EMA20')
      .flush(RESPONSE);
    await openDay(fixture, [TRADE]);

    const link = el(fixture).querySelector('a.open-day');
    expect(link?.textContent?.trim()).toBe('Open full day →');
    expect(link?.getAttribute('href')).toBe('/calendar/2026-08-03?strategy=EMA20');
  });

  it('links the bare day when no filter is set, even on an empty day', async () => {
    const fixture = seed();
    await openDay(fixture, []);
    expect(el(fixture).querySelector('a.open-day')?.getAttribute('href')).toBe('/calendar/2026-08-03');
  });

  it('captions the drawer summary as paper, before costs', async () => {
    const fixture = seed();
    await openDay(fixture, [TRADE]);
    expect(el(fixture).querySelector('.day-caption')?.textContent?.trim()).toBe(PAPER_CAPTION);
  });

  it('says once that scale-out legs count separately', async () => {
    const fixture = seed();
    await openDay(fixture, [
      { ...TRADE, leg_index: 0, leg_total: 2 },
      { ...TRADE, leg_index: 1, leg_total: 2 },
    ]);
    expect(el(fixture).querySelector('.day-sample-note')?.textContent?.trim())
      .toBe('2 rows · scale-out legs count separately');

    const whole = seed();
    await openDay(whole, [TRADE]);
    expect(el(whole).querySelector('.day-sample-note')).toBeNull();
  });
});

function seedUnflushed(): { fixture: ComponentFixture<Calendar>; backend: HttpTestingController } {
  installDialogPolyfill();
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      CalendarStore,
    ],
  });
  const fixture = TestBed.createComponent(Calendar);
  TestBed.inject(CalendarStore).load();
  const backend = TestBed.inject(HttpTestingController);
  return { fixture, backend };
}

describe('Calendar states', () => {
  it('shows a skeleton while loading, before the first response', () => {
    const { fixture } = seedUnflushed();
    fixture.detectChanges();

    expect(el(fixture).querySelector('.skeleton')).toBeTruthy();
  });

  it('shows the error state on a first-load failure', async () => {
    const { fixture, backend } = seedUnflushed();
    fixture.detectChanges();
    backend
      .expectOne((r) => r.url === '/api/v1/calendar/pnl')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el(fixture).querySelector('.failed')).toBeTruthy();
  });

  it('shows the measured-zero empty state, not a spinner, for a month with no closed trades — and does not hide the all-history weekday table', async () => {
    const { fixture, backend } = seedUnflushed();
    fixture.detectChanges();
    backend
      .expectOne((r) => r.url === '/api/v1/calendar/pnl')
      .flush({
        ...RESPONSE,
        days: [],
        totals: { net_pnl_amount: 0, net_r: 0, trade_count: 0, win_rate: null },
        best_day: null,
        worst_day: null,
        streak: { direction: 'none', days: 0 },
      } satisfies PnlCalendar);
    await fixture.whenStable();
    fixture.detectChanges();

    const host = el(fixture);
    expect(host.textContent).toContain('No closed trades this month');
    expect(host.querySelector('.skeleton')).toBeNull();
    // All-time, deliberately outside the this-month empty gate.
    expect(host.textContent).toContain('By weekday (all history)');
    expect(host.querySelectorAll('.dow-row').length).toBe(RESPONSE.day_of_week.length);
  });
});

/* -- v95 C5 -- the stat digest --------------------------------------------- */

describe('Calendar stat digest', () => {
  it('summarises the month in one line', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    // RESPONSE.totals: net_pnl_amount -60, trade_count 3, win_rate 33.33.
    // ConnectionStore's default currency (no stub here) is '€'.
    const component = fixture.componentInstance as unknown as {
      calendarDigest: () => string;
    };
    expect(component.calendarDigest()).toBe('-60.00 € · 3 trades · 33.3% win');
  });

  it('carries the thin-sample warning into the digest rather than losing it', async () => {
    // Guard 2: RESPONSE has only 2 trading days, far below MIN_SAMPLE_N (30).
    // A digest that dropped that would present a thin number as a settled one.
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      calendarProblem: () => string | null;
    };
    expect(component.calendarProblem()).toContain('thin sample');
    expect(component.calendarProblem()).toContain('N=2');
  });

  it('reports no problem once the sample is adequate', async () => {
    const days = Array.from({ length: 30 }, (_, i) => ({
      date: `2026-08-${String(i + 1).padStart(2, '0')}`,
      net_pnl_amount: 10, net_r: 0.5, trade_count: 1, win_rate: 100,
    }));
    const fixture = seed({ ...RESPONSE, days });
    await fixture.whenStable();
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      calendarProblem: () => string | null;
    };
    expect(component.calendarProblem()).toBeNull();
  });
});

/* -- v95 C6 -- the phone agenda --------------------------------------------- */

describe('Calendar phone agenda', () => {
  it('renders an agenda, not a 7-column grid, below sm', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.componentRef.setInput('viewportAt', 'xs');
    fixture.detectChanges();

    expect(el(fixture).querySelector('.week')).toBeNull();
    expect(el(fixture).querySelector('.agenda')).not.toBeNull();
  });

  it('lists only days that traded', async () => {
    // RESPONSE.days has exactly two entries, both trade_count > 0.
    const fixture = seed();
    await fixture.whenStable();
    fixture.componentRef.setInput('viewportAt', 'xs');
    fixture.detectChanges();

    expect(el(fixture).querySelectorAll('.agenda-day')).toHaveLength(RESPONSE.days.length);
  });

  it('separates the value from the count', async () => {
    // At 390px the grid ran "+71 10" together with no separator; two
    // numbers touching read as one.
    const fixture = seed();
    await fixture.whenStable();
    fixture.componentRef.setInput('viewportAt', 'xs');
    fixture.detectChanges();

    const day = el(fixture).querySelector('.agenda-day')!;
    expect(day.querySelector('.agenda-value')).not.toBeNull();
    expect(day.querySelector('.agenda-count')).not.toBeNull();
  });

  it('opens the day drawer when an agenda row is tapped', async () => {
    // The agenda replaced the grid on phones without carrying its click
    // target, so a phone could not open a day's trades at all.
    const fixture = seed();
    await fixture.whenStable();
    fixture.componentRef.setInput('viewportAt', 'xs');
    fixture.detectChanges();

    const row = el(fixture).querySelector('.agenda-day button') as HTMLButtonElement;
    expect(row).not.toBeNull();
    row.click();
    fixture.detectChanges();

    expect(fixture.componentInstance.store.selectedDay()).toBe(RESPONSE.days[0].date);
  });

  it('keeps the grid at sm and above', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.componentRef.setInput('viewportAt', 'sm');
    fixture.detectChanges();

    expect(el(fixture).querySelector('.week')).not.toBeNull();
    expect(el(fixture).querySelector('.agenda')).toBeNull();
  });
});

describe('Calendar URL (v165 D6)', () => {
  const MONTH_URL = '/api/v1/calendar/pnl';

  function mount(): void {
    installDialogPolyfill();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: 'calendar', children: calendarRoutes }], withComponentInputBinding()),
        provideLocationMocks(),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
        // The real one would first ask /api/v1/preferences inside resolveRoute.
        { provide: PreferencesStore, useValue: {
          resolve: () => of(undefined), values: () => ({}), update: () => undefined,
        } },
      ],
    });
  }

  const settle = async () => {
    for (let i = 0; i < 10; i++) await new Promise((resolve) => setTimeout(resolve, 0));
  };

  async function take(predicate: (r: HttpRequest<unknown>) => boolean): Promise<TestRequest> {
    const backend = TestBed.inject(HttpTestingController);
    for (let i = 0; i < 50; i++) {
      const [found] = backend.match(predicate);
      if (found) return found;
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    throw new Error('the expected request was never made');
  }

  async function openAt(url: string): Promise<{ harness: RouterTestingHarness; store: InstanceType<typeof CalendarStore> }> {
    mount();
    const harness = await RouterTestingHarness.create();
    const navigation = harness.navigateByUrl(url);
    (await take((r) => r.url === MONTH_URL)).flush(RESPONSE);
    await navigation;
    const store = (harness.routeDebugElement!.componentInstance as Calendar).store;
    return { harness, store };
  }

  it('restores the month and the filters from the URL in its first request', async () => {
    mount();
    const harness = await RouterTestingHarness.create();
    const navigation = harness.navigateByUrl('/calendar?month=2026-08&strategy=EMA20');
    const first = await take((r) => r.url === MONTH_URL);
    expect(first.request.params.get('month')).toBe('2026-08');
    expect(first.request.params.get('strategy')).toBe('EMA20');
    expect(first.request.params.has('horizon')).toBe(false);
    first.flush(RESPONSE);
    await navigation;

    const store = (harness.routeDebugElement!.componentInstance as Calendar).store;
    expect([store.month(), store.strategy(), store.horizon()]).toEqual(['2026-08', 'EMA20', '']);
  });

  it('makes exactly one request per filter change and writes it to the URL', async () => {
    const { store } = await openAt('/calendar?month=2026-08&strategy=EMA20');
    const backend = TestBed.inject(HttpTestingController);

    store.setHorizon('4w');
    await settle();
    const calls = backend.match((r) => r.url === MONTH_URL);
    expect(calls).toHaveLength(1);
    expect(calls[0].request.params.get('horizon')).toBe('4w');
    calls[0].flush(RESPONSE);

    await settle();
    backend.expectNone((r) => r.url === MONTH_URL);       // the URL write did not reload
    const url = TestBed.inject(Router).url;
    expect(url.startsWith('/calendar?')).toBe(true);
    expect(url).toContain('month=2026-08');
    expect(url).toContain('strategy=EMA20');
    expect(url).toContain('horizon=4w');

    store.stepMonth(-1);
    await settle();
    const stepped = backend.match((r) => r.url === MONTH_URL);
    expect(stepped).toHaveLength(1);
    expect(stepped[0].request.params.get('month')).toBe('2026-07');
    stepped[0].flush(RESPONSE);
    await settle();
    expect(TestBed.inject(Router).url).toContain('month=2026-07');
  });

  it('still reloads on a background refresh of the same URL', async () => {
    await openAt('/calendar?month=2026-08');
    const router = TestBed.inject(Router);
    void router.navigateByUrl(router.url, {
      onSameUrlNavigation: 'reload', replaceUrl: true, info: BACKGROUND_REFRESH_INFO,
    });
    const refresh = await take((r) => r.url === MONTH_URL);
    expect(refresh.request.params.get('month')).toBe('2026-08');
    refresh.flush(RESPONSE);
  });

  it('loads a URL edited by hand, filters it does not name included', async () => {
    const { harness, store } = await openAt('/calendar?month=2026-08&strategy=EMA20');
    const navigation = harness.navigateByUrl('/calendar?month=2026-07');
    const edited = await take((r) => r.url === MONTH_URL);
    expect(edited.request.params.get('month')).toBe('2026-07');
    expect(edited.request.params.has('strategy')).toBe(false);
    edited.flush(RESPONSE);
    await navigation;
    expect([store.month(), store.strategy()]).toEqual(['2026-07', '']);
  });
});
