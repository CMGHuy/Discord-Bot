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
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { TradeRow } from '../../api/models';
import { TradeGroup } from './trade-group';

/**
 * Reproduction for the "all three Dashboard panels show the same trades"
 * report: each `sb-trade-group` declares its own `providers: [TradesStore]`,
 * which should give PENDING/ACTIVE/PARTIAL each an isolated store and an
 * isolated query. This test mounts three sibling instances -- the actual
 * runtime shape on the Dashboard -- and asserts each issues its OWN request
 * with its OWN status filter, rather than three requests for the same status
 * (or three requests with no status filter at all).
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
}

describe('TradeGroup — sibling isolation', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: EventStream, useValue: new FakeEventStream() },
        // Deliberately NOT providing TradesStore here -- each TradeGroup
        // provides its own, and root-providing it here would mask exactly
        // the bug this test exists to catch.
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();
  const rowKey = (row: TradeRow) => row.id;

  function mount(status: string) {
    const fixture = TestBed.createComponent(TradeGroup);
    fixture.componentRef.setInput('status', status);
    fixture.componentRef.setInput('heading', status);
    fixture.componentRef.setInput('columns', []);
    fixture.componentRef.setInput('visible', []);
    fixture.componentRef.setInput('rowKey', rowKey);
    fixture.detectChanges();
    return fixture;
  }

  it('gives PENDING, ACTIVE and PARTIAL one request each, not a racing unfiltered one first', () => {
    // Regression: before the queryReady gate (trades.store.ts), each mount
    // fired TWO requests -- an unfiltered `status=null` one from
    // TradesStore's onInit effect (which reads the store's placeholder
    // default query, since injection runs before this component's own
    // constructor effect can call setQuery), THEN the real filtered one.
    // Whichever response landed last won, which is how three panels could
    // all end up showing the same unfiltered (CLOSED-included) trades.
    mount('PENDING');
    mount('ACTIVE');
    mount('PARTIAL');
    tick();

    const requests = backend.match((r) => r.url === '/api/v1/trades');
    expect(requests).toHaveLength(3);

    const statuses = requests
      .map((r) => r.request.params.get('status'))
      .sort();
    expect(statuses).toEqual(['ACTIVE', 'PARTIAL', 'PENDING']);

    for (const r of requests) {
      r.flush({ items: [], total: 0, page: 1, per_page: 6 });
    }
  });
});
