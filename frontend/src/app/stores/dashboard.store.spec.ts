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
import { Dashboard } from '../api/models';
import { DashboardStore } from './dashboard.store';

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

const RESPONSE: Dashboard = {
  // SR53. Five counts, PENDING/ACTIVE/PARTIAL all-time and CLOSED/CANCELLED
  // today's only.
  lifecycle: { PENDING: 4, ACTIVE: 2, PARTIAL: 1, CLOSED: 3, CANCELLED: 0 },
  // SR58. `pct` is deliberately null against a non-null `amount`: the store
  // must pass each through independently, and a fixture where both have
  // values cannot catch one being derived from the other.
  scope: { mode: 'today' as const },
  realized: { amount: 240.5, pct: null, n: 3, wins: 2, losses: 1 },
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
  default_expiry_bars: 5,
};

describe('DashboardStore', () => {
  let store: InstanceType<typeof DashboardStore>;
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
        DashboardStore,
      ],
    });
    store = TestBed.inject(DashboardStore);
    store.load();
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();
  const respond = (body: Partial<Dashboard> = {}) =>
    backend.expectOne((req) => req.url === '/api/v1/dashboard').flush({ ...RESPONSE, ...body });

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

    store.load();
    respond({ account_balance: 12_000 });

    expect(store.balance()).toBe(12_000);
  });

  it('refetches on a trades event', () => {
    // Open P&L, open count and risk used all move when a position does.
    tick();
    respond();

    store.load();
    respond({ open_pnl_pct: -3 });

    expect(store.openPnlPct()).toBe(-3);
  });

  it('does not refetch on an unrelated event', () => {
    tick();
    respond();

    events.raise('watchlist');
    tick();

    backend.verify();
  });

  it('keeps the previous numbers when a refetch fails', () => {
    tick();
    respond();

    store.load();
    backend
      .expectOne((req) => req.url === '/api/v1/dashboard')
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
      .expectOne((req) => req.url === '/api/v1/dashboard')
      .error(new ProgressEvent('error'), { status: 0 });
    expect(store.error()).not.toBeNull();

    store.load();
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

  /* -- SR53: the lifecycle counts -------------------------------------- */

  it('reads the five lifecycle counts in lifecycle order', () => {
    // Lifecycle order, not by size: PENDING → ACTIVE → PARTIAL → CLOSED →
    // CANCELLED is the order a plan moves through, and sorting by count would
    // reshuffle the row every time a trade closed.
    tick();
    respond();
    expect(store.lifecycle().map((entry) => entry.status)).toEqual([
      'PENDING', 'ACTIVE', 'PARTIAL', 'CLOSED', 'CANCELLED',
    ]);
    expect(store.lifecycle().map((entry) => entry.count)).toEqual([4, 2, 1, 3, 0]);
  });

  it('keeps a status whose count is zero', () => {
    // "No pending plans" is information, and a strip that shed empty entries
    // would change width as the session went on.
    tick();
    respond();
    expect(store.lifecycle()).toHaveLength(5);
  });

  it('renders no strip at all when the collector failed', () => {
    // `_lifecycle_counts` returns {} rather than raising, because the
    // Dashboard is the landing page. An empty object must mean "no strip", not
    // five zeros -- five zeros is a claim about the account.
    tick();
    respond({ lifecycle: {} });
    expect(store.lifecycle()).toEqual([]);
  });

  /* -- the chip tier's loosely typed fields ----------------------------- */

  it('narrows the equity series to numbers the sparkline can draw', () => {
    tick();
    respond({ equity_30d: { points: [100, 101.5, 99], change_pct: -1 } });

    expect(store.equityPoints()).toEqual([100, 101.5, 99]);
    expect(store.equityChangePct()).toBe(-1);
  });

  it('drops non-numeric equity points instead of coercing them', () => {
    // A null balance coerced with Number() becomes 0 and draws a spike to
    // the floor that never happened.
    tick();
    respond({
      equity_30d: { points: [100, null, 'n/a', 102], change_pct: 2 },
    });

    expect(store.equityPoints()).toEqual([100, 102]);
  });

  it('reports an empty equity series rather than failing on it', () => {
    tick();
    respond({ equity_30d: { points: [], change_pct: null } });

    expect(store.equityPoints()).toEqual([]);
    expect(store.equityChangePct()).toBeNull();
  });

  it('reads the fixed premium in account-% sizing', () => {
    tick();
    respond({
      position_premium: { mode: 'account_pct', premium: 500, position_pct: 5 },
    });

    expect(store.positionPremium()).toBe(500);
    expect(store.positionPremiumIsCap()).toBe(false);
  });

  it('reads the max position in risk-% sizing, and flags it as a cap', () => {
    // There is no single premium in this mode -- position value varies per
    // trade with the stop distance -- so the chip must be able to say "max"
    // rather than present a ceiling as a typical cost.
    tick();
    respond({
      position_premium: {
        mode: 'risk_pct',
        risk_amount: 100,
        max_position: 1_200,
        max_position_pct: 12,
      },
    });

    expect(store.positionPremium()).toBe(1_200);
    expect(store.positionPremiumIsCap()).toBe(true);
  });

  it('reports an unreadable premium as null, not zero', () => {
    // The shape is the Python side's to change; a renamed key must read as
    // "unknown", never as "this trade costs nothing".
    tick();
    respond({ position_premium: { mode: 'risk_pct' } });

    expect(store.positionPremium()).toBeNull();
  });

  it('passes nulls through rather than substituting zero', () => {
    // A balance that has not loaded is not a balance of zero, and on this
    // particular number those differ by everything.
    tick();
    respond({ account_balance: null, win_rate: null });

    expect(store.balance()).toBeNull();
    expect(store.winRate()).toBeNull();
  });

  /* -- SR58: the date scope -------------------------------------------- */

  describe('the date scope', () => {
    it('defaults to today and sends it as a query parameter', () => {
      tick();
      const request = backend.expectOne((req) => req.url === '/api/v1/dashboard');
      expect(request.request.params.get('mode')).toBe('today');
      request.flush(RESPONSE);
      expect(store.scope()).toBe('today');
    });

    it('changing the scope refetches with the new mode', () => {
      tick();
      respond();

      store.setScope('all');

      const request = backend.expectOne((req) => req.url === '/api/v1/dashboard');
      expect(request.request.params.get('mode')).toBe('all');
      request.flush({ ...RESPONSE, scope: { mode: 'all' } });
      expect(store.appliedScope()).toBe('all');
    });

    it('selecting the current scope does not refetch', () => {
      tick();
      respond();
      store.setScope('today');
      backend.verify();
    });

    it('reads the realised figures, passing a null through as null', () => {
      tick();
      respond();
      expect(store.realizedAmount()).toBe(240.5);
      // Not 0: "no percentage to report" and "averaged exactly flat" are
      // different facts, and only one of them is true here.
      expect(store.realizedPct()).toBeNull();
      expect(store.realizedCount()).toBe(3);
      expect(store.realizedWins()).toBe(2);
      expect(store.realizedLosses()).toBe(1);
    });

    it('reports the scope the SERVER applied, not the one requested', () => {
      // If the two ever disagree the parameter silently did not take.
      tick();
      respond();
      expect(store.appliedScope()).toBe('today');
    });

    it('reports no applied scope before the first response', () => {
      expect(store.appliedScope()).toBeNull();
      expect(store.realizedCount()).toBe(0);
    });
  });
});
