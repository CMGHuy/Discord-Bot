import { Signal, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Observable, Subject, of, throwError } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../api/api-client';
import { EventStream, MARKET_DATA_MIN_INTERVAL_MS } from '../api/event-stream';
import { MarketStatus, MarketUpdates, QuoteUpdate, RowQuoteFields, SnapshotUpdate } from '../api/models';
import { LOCAL_REFRESH_TIMEOUT_MS, LiveValuesStore, STATUS_POLL_MS, overlayQuote } from './live-values.store';

interface FakeThrottle {
  readonly name: string;
  readonly interval: number;
  readonly out: WritableSignal<number>;
  last: number;
  timer: ReturnType<typeof setTimeout> | null;
}

class FakeEventStream {
  readonly state = signal<'connecting' | 'live' | 'degraded'>('connecting');
  /** Every `changes()` call the store made, with its interval or null. */
  readonly requested: Array<{ name: string; minIntervalMs: number | null }> = [];
  private readonly counters = new Map<string, WritableSignal<number>>();
  private readonly throttles: FakeThrottle[] = [];

  private counterFor(name: string): WritableSignal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter;
  }

  changes(name: string, options?: { minIntervalMs: number }): Signal<number> {
    this.requested.push({ name, minIntervalMs: options?.minIntervalMs ?? null });
    if (!options) return this.counterFor(name).asReadonly();
    const throttle: FakeThrottle = { name, interval: options.minIntervalMs, out: signal(0), last: -Infinity, timer: null };
    this.throttles.push(throttle);
    return throttle.out.asReadonly();
  }

  /** Same rule as EventStream.pass(): the leading bump at once, the rest of
   *  a burst as one trailing bump when the interval has run out. */
  raise(name: string): void {
    this.counterFor(name).update((n) => n + 1);
    for (const throttle of this.throttles) {
      if (throttle.name !== name) continue;
      const wait = throttle.last + throttle.interval - Date.now();
      if (wait <= 0) {
        if (throttle.timer !== null) clearTimeout(throttle.timer);
        this.release(throttle);
      } else if (throttle.timer === null) {
        throttle.timer = setTimeout(() => this.release(throttle), wait);
      }
    }
  }

  private release(throttle: FakeThrottle): void {
    throttle.timer = null;
    throttle.last = Date.now();
    throttle.out.update((n) => n + 1);
  }
}

const A = '2026-10-30T15:00:00Z';
const B = '2026-10-30T15:05:00Z';
const status = (stalled = false): MarketStatus => ({
  session: 'regular', last_close_at: null, stale_price_s: 120,
  heartbeat: { beat_at: null, cadence_s: 30, stalled },
});
const reply = (cursor: string, quotes: QuoteUpdate[] = [], stalled = false): MarketUpdates =>
  ({ cursor, quotes, status: status(stalled) });
const q = (symbol: string, price: number | null, as_of: string | null, refreshing = false, error: string | null = null): QuoteUpdate =>
  ({ symbol, price, as_of, refreshing, error });

describe('LiveValuesStore (v201)', () => {
  let events: FakeEventStream;
  let api: { marketUpdates: ReturnType<typeof vi.fn>; refreshMarket: ReturnType<typeof vi.fn> };

  /** Replies in order; the last one repeats. */
  function make(replies: Array<Observable<MarketUpdates>>): LiveValuesStore {
    let n = 0;
    api.marketUpdates.mockImplementation(() => replies[Math.min(n++, replies.length - 1)]);
    const store = TestBed.inject(LiveValuesStore);
    TestBed.tick();
    return store;
  }

  /** One market event, a full throttle window after the last: each call is
   *  a separate, spaced event that the throttle lets through. */
  function raiseMarket(): void {
    vi.advanceTimersByTime(MARKET_DATA_MIN_INTERVAL_MS);
    TestBed.tick();
    raiseMarketNow();
  }

  /** One market event at the current fake time, no spacing. */
  function raiseMarketNow(): void {
    events.raise('market');
    TestBed.tick();
  }

  /** Move fake time on and let any trailing throttle bump reach the effect. */
  function advance(ms: number): void {
    vi.advanceTimersByTime(ms);
    TestBed.tick();
  }

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse('2026-10-29T14:00:00Z'));
    events = new FakeEventStream();
    api = { marketUpdates: vi.fn(), refreshMarket: vi.fn(() => of({ queued: 1 })) };
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: EventStream, useValue: events },
        { provide: ApiClient, useValue: api },
      ],
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('syncs once at start with no cursor, then with the returned cursor', () => {
    make([of(reply('c1'))]);
    expect(api.marketUpdates.mock.calls.map((c) => c[0])).toEqual([null]);
    raiseMarket();
    expect(api.marketUpdates.mock.calls.map((c) => c[0])).toEqual([null, 'c1']);
  });

  it('refetches on each market event spaced past the throttle window', () => {
    make([of(reply('c1'))]);
    raiseMarket();
    raiseMarket();
    expect(api.marketUpdates).toHaveBeenCalledTimes(3);
  });

  it('shows refreshing from marks the refresher set on its own', () => {
    const store = make([
      of(reply('c0')),
      of(reply('c1', [q('MSFT', 410, A, true)])),
      of(reply('c2', [q('MSFT', 412, B, false)])),
    ]);
    raiseMarket();
    expect(store.quote('msft')()?.refreshing).toBe(true);
    raiseMarket();
    expect(store.quote('msft')()?.price).toBe(412);
    expect(store.quote('MSFT')()?.refreshing).toBe(false);
  });

  it('an event during an in-flight sync runs one more sync after it', () => {
    const pending = new Subject<MarketUpdates>();
    make([of(reply('c0')), pending, of(reply('c2'))]);
    raiseMarket();
    raiseMarket();
    raiseMarket();
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
    pending.next(reply('c1'));
    pending.complete();
    expect(api.marketUpdates).toHaveBeenCalledTimes(3);
  });

  it('requestRefresh marks the keys refreshing at once and posts them', () => {
    const store = make([of(reply('c0'))]);
    store.requestRefresh(['NVDA']);
    expect(store.quote('NVDA')()).toEqual({ symbol: 'NVDA', price: null, as_of: null, refreshing: true, error: null });
    expect(api.refreshMarket).toHaveBeenCalledWith({ symbols: ['NVDA'] });
  });

  it('a local refresh mark clears after LOCAL_REFRESH_TIMEOUT_MS', () => {
    const store = make([of(reply('c0'))]);
    store.requestRefresh(['NVDA']);
    vi.advanceTimersByTime(LOCAL_REFRESH_TIMEOUT_MS);
    expect(store.quote('NVDA')()).toBeNull();
  });

  it('a failed refresh post clears the mark', () => {
    const store = make([of(reply('c0'))]);
    api.refreshMarket.mockReturnValue(throwError(() => new Error('boom')));
    store.requestRefresh(['NVDA']);
    expect(store.quote('NVDA')()).toBeNull();
  });

  it('a server update with refreshing false clears the local mark', () => {
    const store = make([of(reply('c0')), of(reply('c1', [q('NVDA', 100, A, false)]))]);
    store.requestRefresh(['NVDA']);
    expect(store.quote('NVDA')()?.refreshing).toBe(true);
    raiseMarket();
    expect(store.quote('NVDA')()?.refreshing).toBe(false);
  });

  it('an update carrying an error clears the local mark, and the overlay stops the spinner', () => {
    const store = make([of(reply('c0')), of(reply('c1', [q('NVDA', null, null, true, 'no quote')]))]);
    store.requestRefresh(['NVDA']);
    raiseMarket();
    const update = store.quote('NVDA')();
    expect(update?.error).toBe('no quote');
    const row = overlayQuote<RowQuoteFields>({ price_refreshing: true }, { ...update!, refreshing: false });
    expect(row.price_refreshing).toBe(false);
    expect(row.price_error).toBe('no quote');
  });

  const olderSnapshot: SnapshotUpdate = {
    key: 'risk', computed_at: '2026-10-29T13:55:00Z',
    stale_inputs: false, refreshing: false, error: null,
  };
  const snapshotReply = (snapshots: SnapshotUpdate[]): MarketUpdates =>
    ({ ...reply('c1'), snapshots });

  it('merges snapshot updates by key with the last entry winning', () => {
    const next = { ...olderSnapshot, stale_inputs: true };
    const month = { ...olderSnapshot, key: 'calendar:2026-10' };
    const store = make([of(reply('c0')), of(snapshotReply([olderSnapshot, month, next]))]);
    const risk = store.snapshot('risk');
    raiseMarket();
    expect(risk()).toEqual(next);
    expect(store.snapshot('risk')).toBe(risk);
    expect(store.snapshot('calendar:2026-10')()).toEqual(month);
  });

  it('handles a reply without snapshots from an older server', () => {
    const store = make([of(reply('c0')), of(reply('c1'))]);
    raiseMarket();
    expect(store.snapshot('risk')()).toBeNull();
  });

  it('marks snapshots immediately and posts both refresh lists', () => {
    const store = make([of(reply('c0'))]);
    store.requestRefresh([], ['risk']);
    expect(store.snapshot('risk')()).toEqual({
      key: 'risk', computed_at: null, stale_inputs: false, refreshing: true, error: null,
    });
    expect(api.refreshMarket).toHaveBeenCalledWith({ symbols: [], snapshots: ['risk'] });
  });

  it('keeps the snapshot spinner on when an older row arrives', () => {
    const store = make([of(reply('c0')), of(snapshotReply([olderSnapshot]))]);
    store.requestRefresh([], ['risk']);
    raiseMarket();
    expect(store.snapshot('risk')()).toEqual({ ...olderSnapshot, refreshing: true });
  });

  it('clears the snapshot spinner when a newer build finishes', () => {
    const newer = { ...olderSnapshot, computed_at: '2026-10-29T14:01:00Z' };
    const store = make([of(reply('c0')), of(snapshotReply([newer]))]);
    store.requestRefresh([], ['risk']);
    raiseMarket();
    expect(store.snapshot('risk')()?.refreshing).toBe(false);
  });

  it('clears the snapshot spinner when a build errors', () => {
    const error = 'budget exceeded after 90s';
    const store = make([of(reply('c0')), of(snapshotReply([{ ...olderSnapshot, error }]))]);
    store.requestRefresh([], ['risk']);
    raiseMarket();
    expect(store.snapshot('risk')()).toEqual({ ...olderSnapshot, error });
  });

  it('clears the local snapshot mark after LOCAL_REFRESH_TIMEOUT_MS', () => {
    const store = make([of(reply('c0'))]);
    store.requestRefresh([], ['risk']);
    vi.advanceTimersByTime(LOCAL_REFRESH_TIMEOUT_MS);
    expect(store.snapshot('risk')()).toBeNull();
  });

  it('clears the local snapshot mark when the POST errors', () => {
    const store = make([of(reply('c0'))]);
    api.refreshMarket.mockReturnValue(throwError(() => new Error('down')));
    store.requestRefresh([], ['risk']);
    expect(store.snapshot('risk')()).toBeNull();
  });

  it('a failed sync keeps every value and the cursor', () => {
    const store = make([of(reply('c1', [q('MSFT', 410, A)])), throwError(() => new Error('down')), of(reply('c2'))]);
    raiseMarket();
    expect(store.quote('MSFT')()?.price).toBe(410);
    raiseMarket();
    expect(api.marketUpdates.mock.calls.map((c) => c[0])).toEqual([null, 'c1', 'c1']);
  });

  it('polls status every 60 s', () => {
    make([of(reply('c0'))]);
    expect(api.marketUpdates).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(STATUS_POLL_MS);
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
  });

  it('syncs when the stream goes live', () => {
    make([of(reply('c0'))]);
    const before = api.marketUpdates.mock.calls.length;
    events.state.set('live');
    TestBed.tick();
    expect(api.marketUpdates.mock.calls.length).toBe(before + 1);
  });

  it('stalled follows status.heartbeat.stalled', () => {
    const store = make([of(reply('c0', [], false)), of(reply('c1', [], true))]);
    expect(store.stalled()).toBe(false);
    raiseMarket();
    expect(store.stalled()).toBe(true);
  });

  it('patchRows overlays the stored quote onto each row', () => {
    const store = make([of(reply('c1', [q('MSFT', 410, B)]))]);
    const rows = store.patchRows([{ sym: 'msft', current_price: 400, price_as_of: A }], (r) => r.sym);
    expect(rows[0].current_price).toBe(410);
  });

  /* -- v218: the idle tab ---------------------------------------------- */

  it('asks for market events only through the shared 30 s throttle', () => {
    make([of(reply('c0'))]);
    const market = events.requested.filter((r) => r.name === 'market');
    expect(market).toEqual([{ name: 'market', minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS }]);
  });

  it('a burst of five market events in 30 s sends one leading and one trailing request', () => {
    make([of(reply('c0'))]);
    expect(api.marketUpdates).toHaveBeenCalledTimes(1);
    for (const gapMs of [1_000, 4_000, 5_000, 5_000, 5_000]) {
      advance(gapMs);
      raiseMarketNow();
    }
    // t = 20 s: the start-up sync and the leading request only.
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
    advance(11_000);
    // t = 31 s: the trailing request, 30 s after the leading one.
    expect(api.marketUpdates).toHaveBeenCalledTimes(3);
    advance(29_000);
    // t = 60 s: the poll finds a sync 29 s old and stays quiet.
    expect(api.marketUpdates).toHaveBeenCalledTimes(3);
  });

  it('a market event at 50 s keeps the 60 s poll from firing', () => {
    make([of(reply('c0'))]);
    advance(50_000);
    raiseMarketNow();
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
    advance(10_000);
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
    advance(STATUS_POLL_MS);
    // t = 120 s: the last sync is 70 s old, so the poll reads.
    expect(api.marketUpdates).toHaveBeenCalledTimes(3);
  });

  it('with no events the poll still fires every 60 s (a dead refresher raises none)', () => {
    make([of(reply('c0'))]);
    advance(STATUS_POLL_MS);
    advance(STATUS_POLL_MS);
    advance(STATUS_POLL_MS);
    expect(api.marketUpdates).toHaveBeenCalledTimes(4);
  });

  it('a hidden tab skips the poll', () => {
    make([of(reply('c0'))]);
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    try {
      advance(STATUS_POLL_MS);
      expect(api.marketUpdates).toHaveBeenCalledTimes(1);
    } finally {
      delete (document as unknown as { hidden?: boolean }).hidden;
    }
    advance(STATUS_POLL_MS);
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
  });

  it('a stream going live still syncs at once, inside the throttle window', () => {
    make([of(reply('c0'))]);
    raiseMarketNow();
    expect(api.marketUpdates).toHaveBeenCalledTimes(2);
    events.state.set('live');
    TestBed.tick();
    expect(api.marketUpdates).toHaveBeenCalledTimes(3);
  });
});

describe('overlayQuote (v201)', () => {
  const row: RowQuoteFields = { current_price: 100, price_as_of: B, price_age_s: 5, price_refreshing: false, price_error: null };

  it('returns the row itself when there is no update', () => expect(overlayQuote(row, null)).toBe(row));
  it('keeps the row price when the update is older', () => {
    const out = overlayQuote(row, q('X', 90, A));
    expect(out.current_price).toBe(100);
    expect(out.price_as_of).toBe(B);
  });
  it('takes price and as-of when the update is newer', () => {
    const out = overlayQuote({ ...row, price_as_of: A }, q('X', 105, B));
    expect(out).toMatchObject({ current_price: 105, price_as_of: B, price_age_s: null });
  });
  it('takes a price when the row never had a time', () => {
    expect(overlayQuote<RowQuoteFields>({}, q('X', 7, A)).current_price).toBe(7);
  });
  it('keeps the last price when the update has price null', () => {
    const out = overlayQuote(row, q('X', null, null, true));
    expect(out.current_price).toBe(100);
    expect(out.price_refreshing).toBe(true);
  });
  it('carries refreshing and error always', () => {
    expect(overlayQuote(row, q('X', null, null, false, 'no quote'))).toMatchObject({ price_refreshing: false, price_error: 'no quote' });
  });
  it('returns the same object when nothing changed', () => {
    expect(overlayQuote(row, q('X', 90, A))).toBe(row);
  });
});
