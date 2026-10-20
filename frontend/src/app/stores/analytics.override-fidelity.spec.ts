import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Signal, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../api/event-stream';
import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { OVERRIDE_FIDELITY_FIXTURE } from '../workspaces/analytics/tabs/override-fidelity.fixture';
import { AnalyticsStore } from './analytics.store';

/* v173 — the "Overrides vs engine" slice: global, its own error, loaded with Execution. */

const URL = '/api/v1/analytics/override-fidelity';

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();
  changes(name: string): Signal<number> {
    if (!this.counters.has(name)) this.counters.set(name, signal(0));
    return this.counters.get(name)!.asReadonly();
  }
}

describe('AnalyticsStore — overrideFidelity slice', () => {
  let store: InstanceType<typeof AnalyticsStore>;
  let backend: HttpTestingController;

  const flushOthers = (): void =>
    backend.match((req) => req.url !== URL).forEach((request) => request.flush({}));

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
    expect(store.overrideFidelity()).toBeNull();
    expect(store.overrideFidelityError()).toBeNull();
  });

  it('loads with the Execution tab and is never scoped', () => {
    store.setScope({ strategy: 'RSI', from: '2026-09-01' });
    backend.match(() => true).forEach((request) => request.flush({}));   // the Overview load
    store.setTab('execution');
    const request = backend.expectOne((req) => req.url === URL);
    expect(request.request.params.keys()).toEqual([]);
    request.flush(OVERRIDE_FIDELITY_FIXTURE);
    flushOthers();
    backend.verify();
    const loaded = store.overrideFidelity();
    expect(loaded?.summary.counted_n).toBe(1);
    expect(loaded?.summary.sum_delta_r_gross).toBe(1.207);
    expect(loaded?.verdict.state).toBe('WAITING');
    expect(loaded?.verdict.waiting_on).toEqual(['count', 'weeks', 'excluded']);
    expect(loaded?.rows[0].delta_r_gross).toBe(1.207);
  });

  it('is not fetched by another tab', () => {
    store.setTab('partials');
    expect(backend.match((req) => req.url === URL)).toEqual([]);
    backend.match(() => true).forEach((request) => request.flush({}));
  });

  it('keeps its own error and retries only itself', () => {
    store.setTab('execution');
    backend.expectOne((req) => req.url === URL)
      .flush({ message: 'boom' }, { status: 500, statusText: 'Server Error' });
    flushOthers();
    expect(store.overrideFidelityError()).not.toBeNull();
    store.reload('overrideFidelity');
    backend.expectOne((req) => req.url === URL).flush(OVERRIDE_FIDELITY_FIXTURE);
    backend.verify();                                // nothing else was refetched
    expect(store.overrideFidelityError()).toBeNull();
    expect(store.overrideFidelity()?.rows.length).toBe(4);
  });
});
