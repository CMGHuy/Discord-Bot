import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import {
  ApplicationRef,
  Signal,
  WritableSignal,
  computed,
  provideZonelessChangeDetection,
  signal,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { MarketMeta, PnlCalendar, Preferences, SnapshotUpdate } from '../api/models';
import { CalendarStore } from './calendar.store';
import { LiveValuesStore } from './live-values.store';
import { PreferencesStore } from './preferences.store';

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

function fakeLive(snaps = signal<Record<string, SnapshotUpdate>>({})) {
  const live = {
    snaps,
    status: signal(null),
    snapshot: (k: string) => computed(() => snaps()[k] ?? null),
    quote: () => signal(null),
    requestRefresh: vi.fn(),
  };
  return { live, provider: { provide: LiveValuesStore, useValue: live } };
}

const RESPONSE: PnlCalendar = {
  as_of: '2026-08-10T12:00:00Z',
  month: '2026-08',
  days: [
    { date: '2026-08-03', net_pnl_amount: 30, net_r: 1.2, trade_count: 2, win_rate: 50 },
    { date: '2026-08-05', net_pnl_amount: -90, net_r: -1.8, trade_count: 1, win_rate: 0 },
  ],
  totals: { net_pnl_amount: -60, net_r: -0.6, trade_count: 3, win_rate: 33.33 },
  longest_hold: null,
  day_of_week: [
    { weekday: 'Mon', avg_pnl_amount: 15, avg_r: 0.6, win_rate: 50, trade_count: 2 },
    { weekday: 'Tue', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
    { weekday: 'Wed', avg_pnl_amount: -90, avg_r: -1.8, win_rate: 0, trade_count: 1 },
    { weekday: 'Thu', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
    { weekday: 'Fri', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
  ],
  month_day_of_week: [
    { weekday: 'Mon', avg_pnl_amount: 15, avg_r: 0.6, win_rate: 50, trade_count: 2 },
    { weekday: 'Tue', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
    { weekday: 'Wed', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
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
  let preferences: WritableSignal<Preferences>;

  beforeEach(() => {
    events = new FakeEventStream();
    preferences = signal<Preferences>({});
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: events },
        fakeLive().provider,
        { provide: PreferencesStore, useValue: {
          values: () => preferences(),
          update: (mutate: (current: Preferences) => Preferences) => preferences.set(mutate(preferences())),
        } },
        CalendarStore,
      ],
    });
    store = TestBed.inject(CalendarStore);
    store.load();
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

  it('exposes the longest hold of the month, or null when none is measurable', () => {
    tick();
    respond({
      longest_hold: {
        ticker: 'AAPL', trade_id: 't1', plan_id: null,
        opened_at: '2026-08-01T14:00:00Z', closed_at: '2026-08-13T18:00:00Z', held_hours: 292,
      },
    });
    expect(store.longestHold()?.ticker).toBe('AAPL');
    store.load();
    respond({ longest_hold: null });
    expect(store.longestHold()).toBeNull();
  });

  it('defaults to the account-currency metric, not R', () => {
    tick();
    respond();

    expect(store.metric()).toBe('currency');
    expect(store.valueFor(RESPONSE.days[0])).toBe(30);
  });

  it('valueFor follows the metric toggle', () => {
    tick();
    respond();

    store.setMetric('r');
    expect(store.valueFor(RESPONSE.days[0])).toBe(1.2);
    expect(preferences()['calendarMetric']).toBe('r');
  });

  it('restores a valid persisted metric when preferences arrive', () => {
    preferences.set({ calendarMetric: 'win_rate' });
    tick();

    expect(store.metric()).toBe('win_rate');
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

    store.load();
    respond({ totals: { ...RESPONSE.totals, trade_count: 9 } });

    expect(store.totals()?.trade_count).toBe(9);
  });

  it('applyUrl takes month and filters from the URL without a request', () => {
    tick();
    respond();

    store.applyUrl({ month: '2026-03', strategy: 'VWAP', horizon: null });
    expect(store.month()).toBe('2026-03');
    expect(store.strategy()).toBe('VWAP');
    expect(store.horizon()).toBe('');
    backend.expectNone((r) => r.url === '/api/v1/calendar/pnl');
  });

  it('matchesUrl reads absent and malformed params as the defaults', () => {
    tick();
    respond();

    const month = store.month();               // the current month on a fresh store
    expect(store.matchesUrl({ month: null, strategy: null, horizon: null })).toBe(true);
    expect(store.matchesUrl({ month, strategy: null, horizon: null })).toBe(true);
    expect(store.matchesUrl({ month: '2026-13', strategy: null, horizon: null })).toBe(true);
    expect(store.matchesUrl({ month: 'abc', strategy: null, horizon: null })).toBe(true);
    expect(store.matchesUrl({ month: '1999-01', strategy: null, horizon: null })).toBe(false);
    expect(store.matchesUrl({ month, strategy: 'EMA20', horizon: null })).toBe(false);
  });

  it('applyUrl with the state it already has leaves the open day alone', () => {
    tick();
    respond();
    store.selectDay('2026-08-03');
    backend.expectOne((r) => r.url === '/api/v1/calendar/pnl/day').flush({ date: '2026-08-03', trades: [] });

    store.applyUrl({ month: store.month(), strategy: null, horizon: null });
    expect(store.selectedDay()).toBe('2026-08-03');

    store.applyUrl({ month: '2026-01', strategy: null, horizon: null });
    expect(store.selectedDay()).toBeNull();
  });

  it('every setter writes month and filters to the URL, replacing history', () => {
    tick();
    respond();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);

    store.setMonth('2026-08');
    backend.expectOne((r) => r.params.get('month') === '2026-08').flush(RESPONSE);
    store.setStrategy('EMA20');
    backend.expectOne((r) => r.params.get('strategy') === 'EMA20').flush(RESPONSE);
    store.setHorizon('4w');
    backend.expectOne((r) => r.params.get('horizon') === '4w').flush(RESPONSE);
    store.stepMonth(1);
    backend.expectOne((r) => r.params.get('month') === '2026-09').flush(RESPONSE);

    expect(navigate).toHaveBeenCalledTimes(4);
    expect(navigate).toHaveBeenLastCalledWith([], {
      queryParams: { month: '2026-09', strategy: 'EMA20', horizon: '4w' },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
    store.setStrategy('');
    backend.expectOne((r) => r.url === '/api/v1/calendar/pnl').flush(RESPONSE);
    // "Any strategy" is a null, which `merge` drops from the URL.
    expect(navigate).toHaveBeenLastCalledWith([], expect.objectContaining({
      queryParams: { month: '2026-09', strategy: null, horizon: '4w' },
    }));
  });
});

describe('CalendarStore snapshots (v204)', () => {
  const SNAP_META: MarketMeta = {
    as_of: '2026-10-29', refreshing: false, stale_count: 0, missing_count: 0, incomplete: false,
    computed_at: '2026-10-29T14:00:00Z', stale_inputs: false, source: 'snapshot', error: null,
  };
  const upd = (key: string, computed_at: string | null, refreshing = false): SnapshotUpdate =>
    ({ key, computed_at, stale_inputs: false, refreshing, error: null });
  const CAL_URL = (r: { url: string }) => r.url === '/api/v1/calendar/pnl';
  const KEY = 'calendar.pnl:2026-10';

  let live: ReturnType<typeof fakeLive>['live'];
  let backend: HttpTestingController;
  let store: InstanceType<typeof CalendarStore>;
  const tick = () => TestBed.inject(ApplicationRef).tick();

  const setup = () => {
    const fake = fakeLive();
    live = fake.live;
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        { provide: PreferencesStore, useValue: { values: () => ({}), update: () => undefined } },
        fake.provider,
        CalendarStore,
      ],
    });
    store = TestBed.inject(CalendarStore);
    backend = TestBed.inject(HttpTestingController);
  };
  const loadMonth = () => {
    store.setMonth('2026-10');
    tick();
    backend.match(CAL_URL).forEach((r) => r.flush({ ...RESPONSE, month: '2026-10', market_meta: SNAP_META }));
  };

  it('follows the shown month snapshot key', () => {
    setup();
    loadMonth();
    expect(store.snapshotKey()).toBe(KEY);
    live.snaps.set({ [KEY]: upd(KEY, '2026-10-29T14:05:00Z') });
    tick();
    expect(backend.match(CAL_URL)).toHaveLength(1);
  });

  it('a filtered month follows nothing', () => {
    setup();
    store.setStrategy('VWAP');
    expect(store.snapshotKey()).toBeNull();
    store.setStrategy('');
    store.setHorizon('4w');
    expect(store.snapshotKey()).toBeNull();
  });

  it('no reload before data loads', () => {
    setup();
    store.setMonth('2026-10');
    backend.match(CAL_URL);
    live.snaps.set({ [KEY]: upd(KEY, '2026-10-29T14:05:00Z') });
    tick();
    expect(backend.match(CAL_URL)).toHaveLength(0);
    expect(store.data()).toBeNull();
  });

  it('meta ORs refreshing from the live snapshot on the unfiltered month', () => {
    setup();
    loadMonth();
    live.snaps.set({ [KEY]: upd(KEY, null, true) });
    expect(store.meta()?.refreshing).toBe(true);
  });
});
