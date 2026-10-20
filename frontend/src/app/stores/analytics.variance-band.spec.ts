import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Signal, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsVarianceBand } from '../api/models';
import { EventStream } from '../api/event-stream';
import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { AnalyticsStore } from './analytics.store';

/* v175 — the variance-band slice: whole book, unscoped, loaded with Overview,
 * its own error and its own retry. */

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();
  changes(name: string): Signal<number> {
    if (!this.counters.has(name)) this.counters.set(name, signal(0));
    return this.counters.get(name)!.asReadonly();
  }
}

const URL = '/api/v1/analytics/variance-band';

const INSUFFICIENT: AnalyticsVarianceBand = {
  status: 'insufficient', scope: 'whole_book', days: 64, weeks: 15,
};

describe('AnalyticsStore — variance-band slice', () => {
  let store: InstanceType<typeof AnalyticsStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        AnalyticsStore,
      ],
    });
    store = TestBed.inject(AnalyticsStore);
    backend = TestBed.inject(HttpTestingController);
  });

  it('starts empty, with no error', () => {
    expect(store.varianceBand()).toBeNull();
    expect(store.varianceBandError()).toBeNull();
  });

  it('fetches the band with the Overview tab, and never sends the scope', () => {
    store.setScope({ strategy: 'RSI', ledger: 'weak' });
    const band = backend.expectOne((req) => req.url === URL);
    // Whole book: the route answers 400 to any query parameter.
    expect(band.request.params.keys()).toEqual([]);
    expect(band.request.urlWithParams).toBe(URL);
    band.flush(INSUFFICIENT);
    backend.match(() => true).forEach((request) => request.flush({}));   // the rest of the Overview load
    backend.verify();
    expect(store.varianceBand()).toEqual(INSUFFICIENT);
  });

  it('is not fetched by a tab that does not show it', () => {
    store.setTab('partials');
    expect(backend.match((req) => req.url === URL)).toEqual([]);
    backend.match(() => true).forEach((request) => request.flush({}));
    backend.verify();
  });

  it('keeps its own error and retries only itself', () => {
    store.setTab('overview');
    backend.expectOne((req) => req.url === URL)
      .flush({ message: 'boom' }, { status: 500, statusText: 'Server Error' });
    backend.match(() => true).forEach((request) => request.flush({}));
    expect(store.varianceBandError()).not.toBeNull();

    store.reload('varianceBand');
    const retry = backend.match(() => true);
    expect(retry.map((request) => request.request.url)).toEqual([URL]);
    retry[0].flush(INSUFFICIENT);
    backend.verify();
    expect(store.varianceBandError()).toBeNull();
    expect(store.varianceBand()?.status).toBe('insufficient');
  });
});
