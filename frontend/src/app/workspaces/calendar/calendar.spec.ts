import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { CalendarTrade, PnlCalendar } from '../../api/models';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { Calendar } from './calendar';
import { CalendarStore } from '../../stores/calendar.store';

const RESPONSE: PnlCalendar = {
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

  it('signs the cell class so colour follows the displayed number', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const win = el(fixture).querySelector('.cell[data-date="2026-08-03"]');
    const loss = el(fixture).querySelector('.cell[data-date="2026-08-05"]');
    expect(win?.classList.contains('pos')).toBe(true);
    expect(loss?.classList.contains('neg')).toBe(true);
  });

  it('renders weekend and no-trade cells as inert, and differently', async () => {
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
    // A quiet trading day is not clickable either -- there is nothing to open.
    expect(quiet?.querySelector('button')).toBeNull();
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

  it('reports best day, worst day and the current streak', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const callouts = el(fixture).querySelector('.callouts');
    expect(callouts?.textContent).toContain('2026-08-03');
    expect(callouts?.textContent).toContain('2026-08-05');
    expect(callouts?.textContent).toContain('losing');
    expect(callouts?.textContent).toContain('1');
  });

  it('says so plainly when there is no streak at all', async () => {
    const fixture = seed({
      ...RESPONSE,
      streak: { direction: null, days: 0 },
      best_day: null,
      worst_day: null,
    });
    await fixture.whenStable();
    fixture.detectChanges();

    const callouts = el(fixture).querySelector('.callouts');
    expect(callouts?.textContent).toContain('—');
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
};

describe('Calendar day drawer', () => {
  const openDay = async (fixture: ComponentFixture<Calendar>, trades: CalendarTrade[]) => {
    // `seed()` already pinned the month and flushed both grid requests.
    fixture.componentInstance.store.selectDay('2026-08-03');
    TestBed.inject(HttpTestingController)
      .expectOne((r) => r.url === '/api/v1/calendar/pnl/day')
      .flush({ date: '2026-08-03', trades });
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
});

function seedUnflushed(): { fixture: ComponentFixture<Calendar>; backend: HttpTestingController } {
  installDialogPolyfill();
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
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
