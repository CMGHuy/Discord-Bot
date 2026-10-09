import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Signal, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { convertToParamMap } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../api/event-stream';
import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { PARTIALS_FIXTURE } from '../workspaces/analytics/tabs/partials.fixture';
import { scopeFromParams } from '../workspaces/analytics/scope-url';
import { ANALYTICS_TABS, AnalyticsStore } from './analytics.store';

/* v142 — the Partials slice: one payload, its own error, the one scope. */

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();
  changes(name: string): Signal<number> {
    if (!this.counters.has(name)) this.counters.set(name, signal(0));
    return this.counters.get(name)!.asReadonly();
  }
}

describe('AnalyticsStore — partials slice', () => {
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

  it('is the seventh tab and routes from ?tab=partials', () => {
    expect(ANALYTICS_TABS.at(-1)).toBe('partials');
    expect(scopeFromParams(convertToParamMap({ tab: 'partials' })).tab).toBe('partials');
  });

  it('fetches only /partials, against the one scope', () => {
    store.setScope({ strategy: 'RSI' });
    backend.match(() => true).forEach((request) => request.flush({}));   // the Overview load
    store.setTab('partials');
    const request = backend.expectOne((req) => req.url === '/api/v1/analytics/partials');
    expect(request.request.params.get('strategy')).toBe('RSI');
    request.flush(PARTIALS_FIXTURE);
    backend.verify();
    expect(store.partials()?.n).toBe(8);
    // The scope bar's N counts CLOSED TRADES; a filled-plan count would
    // mislabel it, so the Partials payload never feeds scopeN.
    expect(store.scopeN()).toBeNull();
  });

  it('keeps its own error and retries only itself', () => {
    store.setTab('partials');
    backend.expectOne((req) => req.url === '/api/v1/analytics/partials')
      .flush({ message: 'boom' }, { status: 500, statusText: 'Server Error' });
    expect(store.partialsError()).not.toBeNull();
    store.reload('partials');
    backend.expectOne((req) => req.url === '/api/v1/analytics/partials').flush(PARTIALS_FIXTURE);
    expect(store.partialsError()).toBeNull();
    backend.verify();
  });
});
