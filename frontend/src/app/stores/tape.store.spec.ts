import { ApplicationRef, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Subject, of } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { TapeResponse } from '../api/models';
import { PreferencesStore } from './preferences.store';
import { TapeStore } from './tape.store';

describe('TapeStore', () => {
  function setup(rows: unknown[], symbols: string[] = ['NVDA']) {
    const api = { tape: vi.fn().mockReturnValue(
      of({ as_of: '2026-09-09T14:35:00+00:00', rows })) };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApiClient, useValue: api },
        { provide: PreferencesStore, useValue: {
            values: () => ({ 'tape.symbols': symbols }),
            update: () => undefined,
            isLoaded: () => true,
          } },
      ],
    });
    return { api, store: TestBed.inject(TapeStore) };
  }

  it('is not visible when nothing is flagged', () => {
    const { store } = setup([], []);
    store.load();
    expect(store.visible()).toBe(false);
  });

  it('sorts positions before plans before the rest', () => {
    const { store } = setup([
      { symbol: 'C', sort_rank: 2, price: 1, change_pct: 0, context_kind: null, context_label: null },
      { symbol: 'A', sort_rank: 0, price: 1, change_pct: 0, context_kind: 'position', context_label: '+1R' },
      { symbol: 'B', sort_rank: 1, price: 1, change_pct: 0, context_kind: 'plan', context_label: '2w 1% to entry' },
    ]);
    store.load();
    expect(store.rows().map((r) => r.symbol)).toEqual(['A', 'B', 'C']);
  });

  it('keeps the previous rows when a refetch fails', () => {
    const { api, store } = setup([
      { symbol: 'A', sort_rank: 0, price: 1, change_pct: 0, context_kind: null, context_label: null },
    ]);
    store.load();
    api.tape.mockReturnValue(of(null as never));
    store.load();
    expect(store.rows().length).toBe(1);
  });

  it('exposes the as-of instant', () => {
    const { store } = setup([]);
    store.load();
    expect(store.asOf()).toBe('2026-09-09T14:35:00+00:00');
  });

  it('applies only the later of two overlapping loads, however they resolve', () => {
    // Each call to `tape()` gets its own Subject, so the test controls when
    // (and in what order) each request "resolves" -- rather than `of(...)`,
    // which would resolve synchronously and could never race.
    const pending: Subject<TapeResponse>[] = [];
    const api = { tape: vi.fn().mockImplementation(() => {
      const subject = new Subject<TapeResponse>();
      pending.push(subject);
      return subject;
    }) };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApiClient, useValue: api },
        { provide: PreferencesStore, useValue: {
            values: () => ({ 'tape.symbols': ['NVDA'] }),
            update: () => undefined,
            isLoaded: () => true,
          } },
      ],
    });
    const store = TestBed.inject(TapeStore);
    // The store's onInit effect already issued one request on injection;
    // only the two below are the "overlapping loads" under test.
    const before = pending.length;

    store.load(); // e.g. a quick toggle()
    store.load(); // e.g. a scan-triggered refetch, fired before the first settles
    const stale = pending[before];
    const fresh = pending[before + 1];

    // Resolve OUT OF ORDER: the newer request lands first, and the older,
    // now-stale request's response arrives after it -- the exact scenario
    // where "whichever response lands last wins" would be wrong.
    fresh.next({
      as_of: 'fresh',
      rows: [{ symbol: 'B', sort_rank: 0, price: 1, change_pct: 0, context_kind: null, context_label: null }],
    });
    stale.next({
      as_of: 'stale',
      rows: [{ symbol: 'A', sort_rank: 0, price: 1, change_pct: 0, context_kind: null, context_label: null }],
    });

    expect(store.rows().map((r) => r.symbol)).toEqual(['B']);
    expect(store.asOf()).toBe('fresh');
  });

  it('refetches when a scan event arrives', () => {
    // The class comment's central claim -- "this store subscribes to the
    // `scan` event... and refetches" -- gets its own regression here. Every
    // other test in this file drives `load()` directly and never proves the
    // `withHooks.onInit` effect reacts to a *second* `scan` beyond the one
    // it fires on construction, so a real EventStream fake is needed: one
    // whose `changes('scan')` signal this test can bump itself.
    const scanCounter = signal(0);
    const api = { tape: vi.fn().mockReturnValue(
      of({ as_of: '2026-09-09T14:35:00+00:00', rows: [] })) };
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: ApiClient, useValue: api },
        { provide: EventStream, useValue: { changes: () => scanCounter.asReadonly() } },
        { provide: PreferencesStore, useValue: {
            values: () => ({ 'tape.symbols': ['NVDA'] }),
            update: () => undefined,
            isLoaded: () => true,
          } },
      ],
    });

    TestBed.inject(TapeStore);
    TestBed.inject(ApplicationRef).tick();
    // The onInit effect's first run is the initial load -- same as every
    // other test in this file implicitly relies on. Zoneless change
    // detection (needed below, to flush the effect a second time on the
    // `scan` bump) does not auto-flush the first run either, hence the
    // explicit `tick()` here too.
    expect(api.tape).toHaveBeenCalledTimes(1);

    scanCounter.update((n) => n + 1);
    TestBed.inject(ApplicationRef).tick();

    // The real assertion: a SECOND call, caused by nothing but the `scan`
    // counter moving -- no `store.load()` call anywhere in this test.
    expect(api.tape).toHaveBeenCalledTimes(2);
  });
});
