import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import {
  ApplicationRef,
  Signal,
  WritableSignal,
  provideZonelessChangeDetection,
  signal,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { PnlCalendar } from '../api/models';
import { CalendarStore } from './calendar.store';

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();

  private counterFor(name: string): WritableSignal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter;
  }

  changes(name: string): Signal<number> {
    return this.counterFor(name).asReadonly();
  }

  raise(name: string): void {
    this.counterFor(name).update((n) => n + 1);
  }
}

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

describe('CalendarStore', () => {
  let store: InstanceType<typeof CalendarStore>;
  let backend: HttpTestingController;
  let events: FakeEventStream;

  beforeEach(() => {
    events = new FakeEventStream();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: events },
        CalendarStore,
      ],
    });
    store = TestBed.inject(CalendarStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();
  const respond = (body: Partial<PnlCalendar> = {}) =>
    backend
      .expectOne((r) => r.url === '/api/v1/calendar/pnl')
      .flush({ ...RESPONSE, ...body });

  it('loads the current month on creation', () => {
    tick();
    respond();

    expect(store.days()).toHaveLength(2);
    expect(store.empty()).toBe(false);
    expect(store.strategyOptions().map((o) => o.value)).toEqual(['EMA20', 'VWAP']);
  });

  it('defaults to the money metric, not R', () => {
    tick();
    respond();

    expect(store.metric()).toBe('money');
    expect(store.valueFor(RESPONSE.days[0])).toBe(30);
  });

  it('valueFor follows the metric toggle', () => {
    tick();
    respond();

    store.setMetric('r');
    expect(store.valueFor(RESPONSE.days[0])).toBe(1.2);
  });

  it('scales intensity against the largest magnitude in the month', () => {
    tick();
    respond();

    // |-90| is the month's largest, so it saturates and +30 is a third of it.
    expect(store.signedIntensity(RESPONSE.days[1])).toBeCloseTo(-1);
    expect(store.signedIntensity(RESPONSE.days[0])).toBeCloseTo(1 / 3);
  });

  it('gives a null-valued day zero intensity, not a faint tint', () => {
    tick();
    respond();

    expect(
      store.signedIntensity({
        date: '2026-08-09',
        net_pnl_amount: null,
        net_r: null,
        trade_count: 1,
        win_rate: null,
      }),
    ).toBe(0);
  });

  it('stepMonth refetches the neighbouring month, crossing a year', () => {
    tick();
    respond({ month: '2026-01' });

    store.setMonth('2026-01');
    tick();
    backend.expectOne((r) => r.params.get('month') === '2026-01').flush(RESPONSE);

    store.stepMonth(-1);
    tick();
    backend.expectOne((r) => r.params.get('month') === '2025-12').flush(RESPONSE);
    expect(store.month()).toBe('2025-12');
  });

  it('sends the strategy filter and refetches', () => {
    tick();
    respond();

    store.setStrategy('EMA20');
    tick();
    backend.expectOne((r) => r.params.get('strategy') === 'EMA20').flush(RESPONSE);
  });

  it('fetches a day lazily, only once selected', () => {
    tick();
    respond();

    expect(store.dayTrades()).toBeNull();

    store.selectDay('2026-08-03');
    tick();
    backend
      .expectOne((r) => r.url === '/api/v1/calendar/pnl/day')
      .flush({ date: '2026-08-03', trades: [] });

    expect(store.selectedDay()).toBe('2026-08-03');
    expect(store.dayTrades()).toEqual([]);
  });

  it('closeDay clears the selection and the fetched rows', () => {
    tick();
    respond();
    store.selectDay('2026-08-03');
    tick();
    backend
      .expectOne((r) => r.url === '/api/v1/calendar/pnl/day')
      .flush({ date: '2026-08-03', trades: [] });

    store.closeDay();
    expect(store.selectedDay()).toBeNull();
    expect(store.dayTrades()).toBeNull();
  });

  it('keeps the grid and shows a message when a refetch fails', () => {
    tick();
    respond();

    store.setStrategy('VWAP');
    tick();
    backend
      .expectOne((r) => r.params.get('strategy') === 'VWAP')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });

    // Stale numbers beside a warning beat an error panel where the grid was.
    expect(store.days()).toHaveLength(2);
    expect(store.error()).toBeTruthy();
  });

  it('refetches on a trades event', () => {
    tick();
    respond();

    events.raise('trades');
    tick();
    respond({ totals: { ...RESPONSE.totals, trade_count: 9 } });

    expect(store.totals()?.trade_count).toBe(9);
  });
});
