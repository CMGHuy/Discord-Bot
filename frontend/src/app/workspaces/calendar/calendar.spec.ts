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
import { PnlCalendar } from '../../api/models';
import { Calendar } from './calendar';

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
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(
        withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor]),
      ),
      provideHttpClientTesting(),
    ],
  });
  const fixture = TestBed.createComponent(Calendar);
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
