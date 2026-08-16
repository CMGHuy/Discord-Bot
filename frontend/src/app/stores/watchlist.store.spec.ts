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
import { WatchlistStore, parseSymbols } from './watchlist.store';

/* NG51 — the watchlist.
 *
 * The add endpoint reports per-symbol outcomes so a batch is never lost to
 * one typo, and most of what is tested here is that the store does not throw
 * that reporting away.
 */

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

const TICKERS = {
  tickers: [
    { symbol: 'AAPL', company_name: 'Apple Inc.', open_trades: 1, closed_trades: 4,
      next_earnings_date: '2026-09-03' },
    { symbol: 'MSFT', company_name: 'Microsoft', open_trades: 0, closed_trades: 2,
      next_earnings_date: null },
  ],
};

describe('parseSymbols', () => {
  it('splits a pasted blob on commas and whitespace, and upper-cases', () => {
    // One add and thirty take the same path, so this is the only place the
    // two shapes are reconciled.
    expect(parseSymbols('aapl, msft\nnvda  goog')).toEqual([
      'AAPL',
      'MSFT',
      'NVDA',
      'GOOG',
    ]);
  });

  it('is empty for whitespace, so an empty box cannot post', () => {
    expect(parseSymbols('   \n ')).toEqual([]);
  });
});

describe('WatchlistStore', () => {
  let store: InstanceType<typeof WatchlistStore>;
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
        WatchlistStore,
      ],
    });
    store = TestBed.inject(WatchlistStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();
  const boot = () => {
    tick();
    backend.expectOne('/api/v1/watchlist/tickers').flush(TICKERS);
  };

  it('reads the list out of the tickers envelope, not a collection', () => {
    // Typed `Collection<Ticker>` this compiled and handed the store
    // undefined at runtime.
    boot();

    expect(store.count()).toBe(2);
    expect(store.tickers()[0].symbol).toBe('AAPL');
    expect(store.empty()).toBe(false);
  });

  it('refetches on a watchlist event', () => {
    boot();

    events.raise('watchlist');
    tick();
    backend.expectOne('/api/v1/watchlist/tickers').flush({ tickers: [] });

    expect(store.count()).toBe(0);
    // Still not "empty" in the loading sense -- the watchlist is genuinely
    // empty, which is a different thing from never having loaded.
    expect(store.empty()).toBe(false);
  });

  it('posts a list even for a single symbol', () => {
    boot();

    store.addTickers('nvda');
    const request = backend.expectOne('/api/v1/watchlist/tickers');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ tickers: ['NVDA'] });

    request.flush({ added: ['NVDA'], already_present: [], invalid: [], total: 3 });
    backend.expectOne('/api/v1/watchlist/tickers').flush(TICKERS);
  });

  it('names what was rejected as well as what was added', () => {
    // The whole reason the endpoint reports per symbol: thirty pasted
    // symbols with one typo add twenty-nine, and the typo is the only part
    // worth reading.
    boot();

    store.addTickers('AAPL, NVDA, not-a-ticker');
    backend.expectOne('/api/v1/watchlist/tickers').flush({
      added: ['NVDA'],
      already_present: ['AAPL'],
      invalid: ['NOT-A-TICKER'],
      total: 3,
    });
    backend.expectOne('/api/v1/watchlist/tickers').flush(TICKERS);

    const message = store.addResult() ?? '';
    expect(message).toContain('NVDA');
    expect(message).toContain('AAPL');
    expect(message).toContain('NOT-A-TICKER');
  });

  it('does not post an empty box', () => {
    boot();

    store.addTickers('   ');

    backend.verify();
    expect(store.adding()).toBe(false);
  });

  it('names the symbol that failed to be removed', () => {
    // The row is still on screen, so "could not remove" without a name is
    // a message about nothing in particular.
    boot();

    store.removeTicker('AAPL');
    backend
      .expectOne('/api/v1/watchlist/tickers/AAPL')
      .error(new ProgressEvent('error'), { status: 0 });

    expect(store.removeError()).toContain('AAPL');
    expect(store.removing()).toBeNull();
  });

  it('reloads after a successful remove rather than splicing the row out', () => {
    boot();

    store.removeTicker('AAPL');
    backend
      .expectOne('/api/v1/watchlist/tickers/AAPL')
      .flush({ removed: 'AAPL', total: 1 });
    backend
      .expectOne('/api/v1/watchlist/tickers')
      .flush({ tickers: [TICKERS.tickers[1]] });

    expect(store.count()).toBe(1);
  });

  it('clears suggestions for an empty query without asking the server', () => {
    boot();

    store.suggest('  ');

    backend.verify();
    expect(store.suggestions()).toEqual([]);
  });
});
