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
import { OhlcvResponse } from '../api/models';
import { OhlcvStore } from './ohlcv.store';

/* NG45 — the Chart tab's data path.
 *
 * The two things worth pinning here are the ones that were actually wrong
 * before: the response is an ENVELOPE rather than a bare array (the client
 * was typed `Candle[]`, which compiled and would have handed the chart
 * `undefined` at runtime), and the refetch policy is `scan`-only. A test that
 * merely asserted "bars arrive" would have passed against the broken typing.
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

const BAR = { time: '2026-01-02', open: 1, high: 2, low: 0.5, close: 1.5, volume: 100 };

const RESPONSE: OhlcvResponse = {
  ticker: 'AAPL',
  bars: [BAR],
};

describe('OhlcvStore', () => {
  let store: InstanceType<typeof OhlcvStore>;
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
        OhlcvStore,
      ],
    });
    store = TestBed.inject(OhlcvStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();

  it('issues no request until it has a ticker', () => {
    // The chart tab is constructed before the trade has loaded, so the store
    // exists for a moment with nothing to fetch. A request for `/null` would
    // be a 404 the user sees as "no price history".
    tick();
    backend.verify();
    expect(store.bars()).toEqual([]);
  });

  it('loads once a target is set', () => {
    store.setTarget('AAPL');
    tick();
    backend.expectOne('/api/v1/market/ohlcv/AAPL').flush(RESPONSE);

    expect(store.bars()).toEqual([BAR]);
  });

  it('reads bars out of the envelope, not the body', () => {
    // Regression guard: the client was typed `Candle[]`. Against a real
    // server that types as a non-empty array and reads as `undefined`.
    store.setTarget('AAPL');
    tick();
    backend.expectOne('/api/v1/market/ohlcv/AAPL').flush(RESPONSE);

    expect(Array.isArray(store.bars())).toBe(true);
    expect(store.bars()[0].close).toBe(1.5);
  });

  it('sends trade_id when one was given, so the plan lines come back', () => {
    store.setTarget('AAPL', 't1');
    tick();
    const request = backend.expectOne(
      (req) => req.url === '/api/v1/market/ohlcv/AAPL',
    );
    expect(request.request.params.get('trade_id')).toBe('t1');

    request.flush({
      ...RESPONSE,
      levels: { entry: 100, stop_loss: 95, tp1: 108, tp2: null, direction: 'long' },
    });
    expect(store.levels()?.entry).toBe(100);
  });

  it('omits trade_id entirely when there is none', () => {
    // The endpoint 404s an unresolvable id, so sending an empty one would
    // turn a plain price chart into an error.
    store.setTarget('AAPL');
    tick();
    const request = backend.expectOne(
      (req) => req.url === '/api/v1/market/ohlcv/AAPL',
    );
    expect(request.request.params.has('trade_id')).toBe(false);

    request.flush(RESPONSE);
    expect(store.levels()).toBeNull();
  });

  it('treats re-setting the same target as a no-op', () => {
    store.setTarget('AAPL', 't1');
    tick();
    // Matched WITH the query string: `expectOne(string)` compares against the
    // url-with-params, so the bare path silently matches nothing here.
    backend.expectOne('/api/v1/market/ohlcv/AAPL?trade_id=t1').flush(RESPONSE);

    // The detail component sets the target from an effect on the trade, which
    // re-runs on every unrelated trade field change.
    store.setTarget('AAPL', 't1');
    tick();
    backend.verify();
  });

  it('refetches on a scan, which is when new bars exist', () => {
    store.setTarget('AAPL');
    tick();
    backend.expectOne('/api/v1/market/ohlcv/AAPL').flush(RESPONSE);

    events.raise('scan');
    tick();
    backend
      .expectOne('/api/v1/market/ohlcv/AAPL')
      .flush({ ...RESPONSE, bars: [BAR, { ...BAR, time: '2026-01-03' }] });

    expect(store.bars().length).toBe(2);
  });

  it('does not refetch on a trades event', () => {
    // Deliberate: the levels do come from the trade, but refetching a year of
    // candles on every trade event to pick up four horizontal lines is the
    // wrong trade.
    store.setTarget('AAPL', 't1');
    tick();
    backend.expectOne('/api/v1/market/ohlcv/AAPL?trade_id=t1').flush(RESPONSE);

    events.raise('trades');
    tick();
    backend.verify();
  });

  it('clears the previous ticker on retarget rather than showing its bars', () => {
    // Navigating between two trades must not paint AAPL's candles under
    // MSFT's heading while the second request is in flight.
    store.setTarget('AAPL');
    tick();
    backend.expectOne('/api/v1/market/ohlcv/AAPL').flush(RESPONSE);

    store.setTarget('MSFT');
    expect(store.bars()).toEqual([]);

    tick();
    backend.expectOne('/api/v1/market/ohlcv/MSFT').flush({ ...RESPONSE, ticker: 'MSFT' });
  });

  it('names the ticker when there is no history for it', () => {
    store.setTarget('ZZZZ');
    tick();
    backend
      .expectOne('/api/v1/market/ohlcv/ZZZZ')
      .flush({ error: { code: 'not_found', message: 'no data' } }, { status: 404, statusText: 'Not Found' });

    expect(store.error()).toContain('ZZZZ');
  });

  it('reports a dead server as the server, not as a missing ticker', () => {
    store.setTarget('AAPL');
    tick();
    backend
      .expectOne('/api/v1/market/ohlcv/AAPL')
      .error(new ProgressEvent('error'), { status: 0 });

    expect(store.error()).toContain('not responding');
  });

  it('is not "empty" before it has been given anything to load', () => {
    // Regression guard. `isEmpty` fed `hasData` on the chart container, and
    // at rest with no ticker nothing is in flight -- so an ungated `isEmpty`
    // is true and the Chart tab renders "no price history" during the wait
    // for the trade. That is a claim about the data made while the data has
    // not been asked for.
    tick();
    expect(store.isEmpty()).toBe(false);
  });

  it('is not "empty" while the first request is still in flight', () => {
    store.setTarget('AAPL');
    tick();
    backend.expectOne('/api/v1/market/ohlcv/AAPL');

    expect(store.isEmpty()).toBe(false);
  });

  it('separates "no bars" from loading and from failure', () => {
    // All three render differently, and an empty chart that means "still
    // loading" is how a reader concludes the ticker has no history.
    store.setTarget('AAPL');
    tick();
    backend.expectOne('/api/v1/market/ohlcv/AAPL').flush({ ...RESPONSE, bars: [] });

    expect(store.isEmpty()).toBe(true);
    expect(store.error()).toBeNull();
  });
});
