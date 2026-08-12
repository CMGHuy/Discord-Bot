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
import { Cockpit } from '../api/models';
import { CockpitStore } from './cockpit.store';

/* NG35/NG36 — the reference store, and the tracer bullet's data path.
 *
 * EventStream is faked down to the one method a store uses. The real one is
 * covered by its own spec; what matters here is that reading a counter
 * subscribes, and that bumping it refetches.
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

  /** Raise an event, the way a frame arriving on the real stream would. */
  raise(name: string): void {
    this.counterFor(name).update((n) => n + 1);
  }
}

const RESPONSE: Cockpit = {
  account_balance: 10_000,
  open_pnl_pct: 1.5,
  risk_used_pct: 4,
  risk_cap_pct: 10,
  open_trades: 3,
  avg_confidence: 4.2,
  win_rate: 55,
  expectancy_r: 0.3,
  equity_30d: { points: [], change_pct: 2 },
  position_premium: {},
};

describe('CockpitStore', () => {
  let store: InstanceType<typeof CockpitStore>;
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
        CockpitStore,
      ],
    });
    store = TestBed.inject(CockpitStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();
  const respond = (body: Partial<Cockpit> = {}) =>
    backend.expectOne('/api/v1/cockpit').flush({ ...RESPONSE, ...body });

  it('loads on creation, with no separate bootstrap call', () => {
    // The first effect run IS the initial load, so the load path and the
    // refetch path cannot drift apart.
    tick();
    respond();

    expect(store.balance()).toBe(10_000);
    expect(store.empty()).toBe(false);
  });

  it('refetches on an account event', () => {
    tick();
    respond();

    events.raise('account');
    tick();
    respond({ account_balance: 12_000 });

    expect(store.balance()).toBe(12_000);
  });

  it('refetches on a trades event', () => {
    // Open P&L, open count and risk used all move when a position does.
    tick();
    respond();

    events.raise('trades');
    tick();
    respond({ open_pnl_pct: -3 });

    expect(store.openPnlPct()).toBe(-3);
  });

  it('does not refetch on an unrelated event', () => {
    tick();
    respond();

    events.raise('universe');
    tick();

    backend.verify();
  });

  it('keeps the previous numbers when a refetch fails', () => {
    tick();
    respond();

    events.raise('account');
    tick();
    backend
      .expectOne('/api/v1/cockpit')
      .error(new ProgressEvent('error'), { status: 0 });

    // Replacing nine live figures with an error panel because one poll
    // failed is worse than showing them slightly stale beside a warning --
    // especially when the stream reconnects seconds later.
    expect(store.balance()).toBe(10_000);
    expect(store.error()).toContain('not responding');
  });

  it('clears the error once a refetch succeeds', () => {
    tick();
    backend
      .expectOne('/api/v1/cockpit')
      .error(new ProgressEvent('error'), { status: 0 });
    expect(store.error()).not.toBeNull();

    events.raise('account');
    tick();
    respond();

    expect(store.error()).toBeNull();
  });

  it('distinguishes never-loaded from loaded', () => {
    // A skeleton belongs on the first, and nothing at all on a refetch.
    expect(store.empty()).toBe(true);
    tick();
    respond();
    expect(store.empty()).toBe(false);
  });

  it('computes risk utilisation as a fraction of the cap', () => {
    tick();
    respond({ risk_used_pct: 8, risk_cap_pct: 10 });

    expect(store.riskUtilisation()).toBeCloseTo(0.8);
  });

  it('reports unknown utilisation as null, not zero', () => {
    // An empty meter and a meter at zero look identical and mean opposite
    // things.
    tick();
    respond({ risk_used_pct: null, risk_cap_pct: 10 });

    expect(store.riskUtilisation()).toBeNull();
  });

  it('survives a zero cap without dividing by it', () => {
    tick();
    respond({ risk_used_pct: 4, risk_cap_pct: 0 });

    expect(store.riskUtilisation()).toBeNull();
  });

  it('passes nulls through rather than substituting zero', () => {
    // A balance that has not loaded is not a balance of zero, and on this
    // particular number those differ by everything.
    tick();
    respond({ account_balance: null, win_rate: null });

    expect(store.balance()).toBeNull();
    expect(store.winRate()).toBeNull();
  });
});
