import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
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
import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { ChartResponse } from '../api/models';
import { ChartStore } from './chart.store';

/* SR35 — the trade chart's data path, `GET /api/v1/market/chart/:tradeId`.
 *
 * One request carries the bars, the indicator panes, the volume profile, the
 * plan lines and the overlay, because the panes must agree: they are all
 * slices of one frame at one window. So the store has one loading flag and
 * one error, not five.
 *
 * The refetch policy is the part worth pinning. OhlcvStore deliberately does
 * NOT refetch on `trades` — refetching a year of candles to pick up four
 * horizontal lines is the wrong trade. This store must, and for a reason that
 * does not apply there: its payload carries `working_stop`, which moves on
 * every breakeven and trail step, and an overlay derived from the trade's own
 * confirming sources. A stale chart here shows the wrong stop.
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

const RESPONSE: ChartResponse = {
  ohlcv: [
    { t: 1_767_312_000, o: 1, h: 2, l: 0.5, c: 1.5, v: 100 },
    { t: 1_767_398_400, o: 1.5, h: 2.5, l: 1, c: 2, v: 120 },
  ],
  indicators: {
    rsi: [null, 55],
    macd: { line: [null, 0.4], signal: [null, 0.2], hist: [null, 0.2] },
    kc: { upper: [null, 2.4], lower: [null, 0.6] },
  },
  volume_profile: [{ price: 1.5, volume: 220 }],
  levels: { entry: 1.4, stop: 1.1, target1: 2.2, target2: null, working_stop: 1.2 },
  overlay: {
    side: 'target',
    source: 'EMA20',
    shape: { kind: 'curve', label: 'EMA20', points: [[1_767_312_000, 1.2]] },
  },
  currency: '$',
};

describe('ChartStore', () => {
  let store: InstanceType<typeof ChartStore>;
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
        ChartStore,
      ],
    });
    store = TestBed.inject(ChartStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();

  const load = (tradeId = 't1') => {
    store.setTrade(tradeId);
    tick();
    return backend.expectOne((req) => req.url === `/api/v1/market/chart/${tradeId}`);
  };

  it('issues no request until it has a trade', () => {
    // The Chart tab is built before the trade has loaded. A request for
    // `/chart/null` is a 404 the user would read as "this chart is broken".
    tick();
    backend.verify();
    expect(store.data()).toBeNull();
  });

  it('loads once a trade is set', () => {
    load().flush(RESPONSE);

    expect(store.data()?.ohlcv.length).toBe(2);
    expect(store.data()?.currency).toBe('$');
  });

  it('is loading while the request is in flight, and not after', () => {
    const request = load();
    expect(store.loading()).toBe(true);

    request.flush(RESPONSE);
    expect(store.loading()).toBe(false);
    expect(store.error()).toBeNull();
  });

  it('setting the same trade twice does not refetch', () => {
    load().flush(RESPONSE);

    store.setTrade('t1');
    tick();
    backend.verify();
  });

  it('refetches when the trade changes, and drops the previous payload', () => {
    load('t1').flush(RESPONSE);
    store.setTrade('t2');
    tick();

    // The old chart must not linger under the new trade's header while the
    // request is out -- that is a chart of the wrong position.
    expect(store.data()).toBeNull();
    backend.expectOne((req) => req.url === '/api/v1/market/chart/t2').flush(RESPONSE);
    expect(store.data()?.ohlcv.length).toBe(2);
  });

  it('sends the window when one is set', () => {
    store.setTrade('t1');
    store.setWindow(200);
    tick();
    const request = backend.expectOne((req) => req.url === '/api/v1/market/chart/t1');
    expect(request.request.params.get('window')).toBe('200');
  });

  it('refetches on a trades event', () => {
    load().flush(RESPONSE);

    events.raise('trades');
    tick();
    backend.expectOne((req) => req.url === '/api/v1/market/chart/t1').flush(RESPONSE);
  });

  it('does not refetch on unrelated events', () => {
    load().flush(RESPONSE);

    events.raise('watchlist');
    events.raise('journal');
    tick();
    backend.verify();
  });

  it('surfaces a not_found as a sentence naming the reason', () => {
    // Spec Decision 10's first degraded state: an empty state naming the
    // reason, with a retry -- never a blank pane. The component can only
    // name it if the store kept it.
    load().flush(
      { error: { code: 'not_found', message: 'No trade with id t1' } },
      { status: 404, statusText: 'Not Found' },
    );

    expect(store.loading()).toBe(false);
    expect(store.data()).toBeNull();
    expect(store.error()).toContain('t1');
  });

  it('reports an unreachable admin distinctly from a missing trade', () => {
    load().flush(
      { error: { code: 'unavailable', message: 'upstream down' } },
      { status: 503, statusText: 'Service Unavailable' },
    );

    expect(store.error()).toBe('The admin is not responding.');
  });

  it('retry re-issues the request that failed', () => {
    load().flush(
      { error: { code: 'unavailable', message: 'upstream down' } },
      { status: 503, statusText: 'Service Unavailable' },
    );
    expect(store.error()).not.toBeNull();

    store.retry();
    tick();
    backend.expectOne((req) => req.url === '/api/v1/market/chart/t1').flush(RESPONSE);
    expect(store.error()).toBeNull();
    expect(store.data()?.ohlcv.length).toBe(2);
  });
});
