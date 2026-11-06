import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ApplicationRef, Signal, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../api/event-stream';
import { LiveSnapshot } from '../api/models';
import { LIVE_REFRESH_DEBOUNCE_MS, LIVE_REFRESH_EVENTS, LiveStore } from './live.store';

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();
  readonly lastSeq = signal(0);
  private counterFor(name: string): WritableSignal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter;
  }
  changes(name: string): Signal<number> { return this.counterFor(name).asReadonly(); }
  state(): 'live' { return 'live'; }
  connect(): void { /* no-op */ }
  raise(name: string): void { this.counterFor(name).update((n) => n + 1); }
}

const AS_OF = '2026-10-29T13:32:00+00:00';
const SNAPSHOT: LiveSnapshot = {
  heat: { availability: 'ok', as_of: AS_OF, reason: null, open_pct: 4.2, cap_pct: 6, utilisation_pct: 70,
    open_amount: 2010, cap_amount: 2893, headroom_pct: 1.8, headroom_amount: 883, balance: 48210, includes_resting: true },
  awaiting: { availability: 'ok', as_of: AS_OF, reason: null, count: 3, next_expiry: '2026-10-30T20:00:00+00:00' },
  killswitch: { availability: 'ok', as_of: AS_OF, reason: null, engaged: false, since: null, detail: null },
  events: [{ at: AS_OF, kind: 'trade_closed', text: 'NVDA closed · TP2', tone: 'positive', ref: '812', pnl: { r: 2.1, amount: 441 } }],
  events_meta: { availability: 'ok', as_of: AS_OF, missing: [] },
};

describe('LiveStore (v203)', () => {
  let store: InstanceType<typeof LiveStore>;
  let backend: HttpTestingController;
  let events: FakeEventStream;
  const tick = () => TestBed.inject(ApplicationRef).tick();
  const pending = () => backend.match((r) => r.url === '/api/v1/live');

  beforeEach(() => {
    vi.useFakeTimers();
    events = new FakeEventStream();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: events },
      ],
    });
    store = TestBed.inject(LiveStore);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    backend.verify();
    vi.useRealTimers();
  });

  it('refreshes on exactly the trades, bot and risk events, 2 s apart (v206: never scan)', () => {
    expect(LIVE_REFRESH_EVENTS).toEqual(['trades', 'bot', 'risk']);
    expect(LIVE_REFRESH_DEBOUNCE_MS).toBe(2000);
  });

  it('sends no /live request for a scan event, however many arrive', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    for (let second = 0; second < 10; second += 1) {
      events.raise('scan');
      tick();
      vi.advanceTimersByTime(1000);
    }
    expect(pending()).toHaveLength(0);
  });

  it('reads nothing before the first answer, and says it is loading', () => {
    expect(store.snapshot()).toBeNull();
    expect(store.loading()).toBe(true);
    expect(store.heat()).toBeNull();
    expect(store.awaiting()).toBeNull();
    expect(store.killswitch()).toBeNull();
    expect(store.eventsMeta()).toBeNull();
    expect(store.events()).toEqual([]);
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
  });

  it('loads once on init and exposes each section', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    expect(store.loading()).toBe(false);
    expect(store.failed()).toBe(false);
    expect(store.heat()?.open_amount).toBe(2010);
    expect(store.awaiting()?.count).toBe(3);
    expect(store.killswitch()?.engaged).toBe(false);
    expect(store.events()).toHaveLength(1);
    expect(store.eventsMeta()?.availability).toBe('ok');
  });

  it('folds a burst of events into one request, 2 s after the first', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    events.raise('trades');
    tick();
    vi.advanceTimersByTime(1000);
    events.raise('bot');
    events.raise('risk');
    tick();
    vi.advanceTimersByTime(999);
    expect(pending()).toHaveLength(0);
    vi.advanceTimersByTime(1);
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    vi.advanceTimersByTime(5000);
    expect(pending()).toHaveLength(0);
  });

  it('still refreshes every 2 s while trades events arrive every second', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    for (let second = 0; second < 4; second += 1) {
      events.raise('trades');
      tick();
      vi.advanceTimersByTime(1000);
    }
    // A resetting debounce would still be waiting. The fixed window fired at
    // 2 s and at 4 s, and the second load cancelled the first, unanswered one.
    const requests = pending();
    expect(requests.map((r) => r.cancelled)).toEqual([true, false]);
    requests[1].flush(SNAPSHOT);
  });

  it('ignores every other event', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    events.raise('jobs');
    events.raise('watchlist');
    events.raise('scan');
    tick();
    vi.advanceTimersByTime(LIVE_REFRESH_DEBOUNCE_MS * 2);
    expect(pending()).toHaveLength(0);
  });

  it('keeps the last answer on a failed refresh and says so, until a later success', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    events.raise('bot');
    tick();
    vi.advanceTimersByTime(LIVE_REFRESH_DEBOUNCE_MS);
    backend.expectOne('/api/v1/live').flush({ error: 'boom' }, { status: 503, statusText: 'down' });
    expect(store.failed()).toBe(true);
    expect(store.loading()).toBe(false);
    expect(store.heat()?.open_amount).toBe(2010);
    store.retry();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    expect(store.failed()).toBe(false);
  });

  it('fails cleanly when the very first read fails: no snapshot, not loading', () => {
    tick();
    backend.expectOne('/api/v1/live').error(new ProgressEvent('error'), { status: 0 });
    expect(store.snapshot()).toBeNull();
    expect(store.failed()).toBe(true);
    expect(store.loading()).toBe(false);
  });

  it('retries at once, drops the pending refresh, and lets no older answer land last', () => {
    tick();
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    events.raise('trades');
    tick();
    store.retry();
    const [first] = pending();
    store.retry();
    expect(first.cancelled).toBe(true);
    // match() already removed the first request, so only the second is open.
    backend.expectOne('/api/v1/live').flush(SNAPSHOT);
    vi.advanceTimersByTime(LIVE_REFRESH_DEBOUNCE_MS * 2);
    expect(pending()).toHaveLength(0);
  });
});
