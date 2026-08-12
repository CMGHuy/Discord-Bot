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
import { Collection, TradeRow } from '../api/models';
import { TradesStore, fromSortParam, toSortParam } from './trades.store';

/* NG42 — the Trades list store. */

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

const ROW: TradeRow = {
  id: 'plan-1',
  origin: 'plan',
  status: 'open',
  ticker: 'AAPL',
  direction: 'bullish',
  strategy: 'RSI',
  horizon: '2w',
  tier: 'A',
  badge: null,
  confidence_level: 4,
  confidence_score: 78,
  quality_score: null,
  entry: 100,
  stop_loss: 94,
  target: 112,
  target2: null,
  risk_reward: 2,
  shares: 10,
  position_value: 1000,
  current_price: 104,
  exit_price: null,
  realized_pnl_amount: null,
  pnl_pct: 4,
  r_multiple: null,
  held_hours: 30,
  opened_at: '2026-01-03T14:30:00Z',
  closed_at: null,
  has_note: false,
};

const COLLECTION: Collection<TradeRow> = {
  items: [ROW],
  total: 90,
  page: 1,
  per_page: 25,
};

describe('sort parameter translation', () => {
  it('spells descending with a leading minus, the way the API does', () => {
    expect(toSortParam({ key: 'pnl_pct', direction: 'desc' })).toBe('-pnl_pct');
    expect(toSortParam({ key: 'pnl_pct', direction: 'asc' })).toBe('pnl_pct');
  });

  it('leaves the parameter off entirely when nothing is sorted', () => {
    // Not an empty string: `sort=` is a parameter the endpoint would have to
    // interpret, and an unsortable field there is a 400.
    expect(toSortParam(null)).toBeUndefined();
  });

  it('round-trips', () => {
    for (const param of ['ticker', '-pnl_pct', 'opened_at']) {
      expect(toSortParam(fromSortParam(param))).toBe(param);
    }
  });

  it('reads nothing as no sort', () => {
    expect(fromSortParam(undefined)).toBeNull();
    expect(fromSortParam('')).toBeNull();
  });
});

describe('TradesStore', () => {
  let store: InstanceType<typeof TradesStore>;
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
        TradesStore,
      ],
    });
    store = TestBed.inject(TradesStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();
  const expectRequest = () => backend.expectOne((r) => r.url === '/api/v1/trades');
  const respond = (body: Partial<Collection<TradeRow>> = {}) =>
    expectRequest().flush({ ...COLLECTION, ...body });

  it('loads on creation, with no separate bootstrap call', () => {
    tick();
    respond();

    expect(store.rows()).toHaveLength(1);
    expect(store.empty()).toBe(false);
  });

  it('sends the query it was given', () => {
    store.setQuery({ page: 2, per_page: 25, status: 'open', sort: '-pnl_pct' });
    tick();

    const request = expectRequest();
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.get('status')).toBe('open');
    expect(request.request.params.get('sort')).toBe('-pnl_pct');
    request.flush(COLLECTION);
  });

  it('refetches when the query changes', () => {
    tick();
    respond();

    store.setQuery({ page: 1, per_page: 25, status: 'win' });
    tick();
    expect(expectRequest().request.params.get('status')).toBe('win');
  });

  it('reissues the current query on a trades event', () => {
    // Events are thin -- they say "trades changed", not what changed. A store
    // that patched a row would be a second, drifting copy of the server data.
    store.setQuery({ page: 3, per_page: 25, status: 'open' });
    tick();
    respond();

    events.raise('trades');
    tick();

    const request = expectRequest();
    expect(request.request.params.get('page')).toBe('3');
    expect(request.request.params.get('status')).toBe('open');
    request.flush(COLLECTION);
  });

  it('does not refetch on an unrelated event', () => {
    tick();
    respond();

    events.raise('universe');
    tick();

    backend.verify();
  });

  it('maps the envelope to the table pagination contract', () => {
    tick();
    respond({ total: 90, page: 2, per_page: 25 });

    expect(store.pagination()).toEqual({ total: 90, page: 2, perPage: 25 });
  });

  it('has no pagination before anything has loaded', () => {
    // Otherwise the table shows a pager claiming one page of nothing.
    expect(store.pagination()).toBeNull();
    expect(store.empty()).toBe(true);
  });

  it('counts filters, but not paging or sorting', () => {
    // Paging and sorting hide nothing, so counting them would report a
    // filtered list that is not filtered.
    store.setQuery({ page: 4, per_page: 25, sort: '-pnl_pct' });
    expect(store.activeFilterCount()).toBe(0);

    store.setQuery({ page: 1, per_page: 25, status: 'open', ticker: 'AAPL' });
    expect(store.activeFilterCount()).toBe(2);
  });

  it('ignores empty filter values in the count', () => {
    store.setQuery({ page: 1, per_page: 25, status: '', ticker: undefined });
    expect(store.activeFilterCount()).toBe(0);
  });

  it('keeps the rows on screen when a refetch fails', () => {
    tick();
    respond();

    events.raise('trades');
    tick();
    expectRequest().error(new ProgressEvent('error'), { status: 0 });

    expect(store.rows()).toHaveLength(1);
    expect(store.error()).toContain('not responding');
  });

  it('clears the error once a refetch succeeds', () => {
    tick();
    expectRequest().error(new ProgressEvent('error'), { status: 0 });
    expect(store.error()).not.toBeNull();

    events.raise('trades');
    tick();
    respond();

    expect(store.error()).toBeNull();
  });

  it('exposes the sort as the table understands it', () => {
    store.setQuery({ page: 1, per_page: 25, sort: '-held' });
    expect(store.sort()).toEqual({ key: 'held', direction: 'desc' });
  });
});
