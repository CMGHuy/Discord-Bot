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
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { Dashboard } from '../api/models';
import { DashboardStore, RANGE_DEBOUNCE_MS } from './dashboard.store';

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
  open_pnl_amount: 150,
  risk_used_pct: 4,
  risk_cap_pct: 10,
  open_trades: 3,
  avg_confidence: 4.2,
  win_rate: 55,
  win_rate_n: 20,
  expectancy_r: 0.3,
  expectancy_n: 21,
  payoff_ratio: 1.8,
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

  // Vitest's fake timers, not Angular's zone-based fakeAsync/tick: this app
  // is zoneless (provideZonelessChangeDetection everywhere), and fakeAsync
  // requires zone.js/testing, which a zoneless app does not load -- it
  // throws "zone-testing.js is needed" instead of running. debounceTime's
  // RxJS asyncScheduler uses the global setTimeout, which vi.useFakeTimers
  // intercepts directly, no zone involved.
  it('refetches on an account event', () => {
    vi.useFakeTimers();
    try {
      tick();
      respond();

      events.raise('account');
      // Post-initial refetches are coalesced (debounceTime(300) -- see
      // dashboard.store.ts's onInit) so a compound account+trades event
      // from one scan tick reloads once, not twice. tick() FIRST flushes
      // the effect (zoneless Angular runs it during change detection, not
      // synchronously on signal write) so it actually calls refresh.next()
      // and starts the debounce timer; only THEN is there anything for
      // advanceTimersByTime to resolve.
      tick();
      vi.advanceTimersByTime(300);
      tick();
      respond({ account_balance: 12_000 });

      expect(store.balance()).toBe(12_000);
    } finally {
      vi.useRealTimers();
    }
  });

  it('refetches on a trades event', () => {
    // Open P&L, open count and risk used all move when a position does.
    vi.useFakeTimers();
    try {
      tick();
      respond();

      events.raise('trades');
      tick();
      vi.advanceTimersByTime(300);
      tick();
      respond({ open_pnl_pct: -3 });

      expect(store.openPnlPct()).toBe(-3);
    } finally {
      vi.useRealTimers();
    }
  });

  it('coalesces an account+trades event from the same tick into one refetch', () => {
    // Regression test (2026-09-14): closing a trade raises BOTH events from
    // the same scan tick, and effect() re-runs on either one, reading both
    // every time -- without debouncing, that used to fire store.load()
    // twice for one logical update. backend.expectOne (not expectMatchOne
    // and not a manual count) is itself the assertion: it throws if more
    // than one matching request is pending.
    vi.useFakeTimers();
    try {
      tick();
      respond();

      events.raise('trades');
      events.raise('account');
      tick();
      vi.advanceTimersByTime(300);
      tick();
      respond({ open_pnl_pct: -3, account_balance: 12_000 });

      expect(store.openPnlPct()).toBe(-3);
      expect(store.balance()).toBe(12_000);
    } finally {
      vi.useRealTimers();
    }
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

  it('exposes payoff ratio', () => {
    tick();
    respond({ payoff_ratio: 2.5 });
    expect(store.payoffRatio()).toBe(2.5);
  });

  it('keeps a null payoff ratio distinct from zero', () => {
    tick();
    respond({ payoff_ratio: null });
    expect(store.payoffRatio()).toBeNull();
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
  /* -- v181: presets, Range, stale -------------------------------------- */

  describe('the v181 scope selection', () => {
    // Wed 21 Oct 2026, 10:00 New York. Presets snap to New York midnights.
    const NOW = new Date('2026-10-21T14:00:00Z');
    const TO = '2026-10-22T04:00:00.000Z';
    const W1 = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
    const W2 = { from: '2026-09-10T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
    // The today-only fetch (mode=today, the Realised today card) is covered by its own describe below;
    // these helpers see the scoped requests only.
    const scoped = (req: { url: string; params: { get(k: string): string | null; has(k: string): boolean } }) =>
      req.url === '/api/v1/dashboard' && !(req.params.get('mode') === 'today' && !req.params.has('from') && lastIsWider());
    const lastIsWider = () => store.selection().kind === 'range' || store.preset() !== '1D';
    const dashboardRequests = () => backend.match(scoped);
    const one = () => backend.expectOne(scoped);

    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(NOW);
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('starts on 1D with no window and no chart move', () => {
      tick();
      expect(one().request.params.get('mode')).toBe('today');
      expect(store.selection()).toEqual({ kind: 'preset', preset: '1D' });
      expect(store.preset()).toBe('1D');
      expect(store.chartTarget().seq).toBe(0);
      expect(store.stale()).toBe(false);
    });

    it('opens on 1D on every visit: one today request, nothing else', () => {
      tick();
      const all = backend.match((req) => req.url === '/api/v1/dashboard');
      expect(all.map((req) => req.request.params.get('mode'))).toEqual(['today']);
      all[0].flush(RESPONSE);
      expect(store.preset()).toBe('1D');
      backend.verify();
    });

    it('setPreset refetches with the window and moves the chart', () => {
      tick();
      respond();
      store.setPreset('5D');
      const request = one();
      expect(request.request.params.get('from')).toBe('2026-10-15T04:00:00.000Z');
      expect(request.request.params.get('to')).toBe(TO);
      expect(store.chartTarget().seq).toBe(1);
    });

    it('maps 1D and All onto today and all, with no window', () => {
      tick();
      respond();
      store.setPreset('All');
      const request = one();
      expect(request.request.params.get('mode')).toBe('all');
      expect(request.request.params.has('from')).toBe(false);
      expect(store.chartTarget().window).toBeNull();
    });

    it('re-choosing the current preset recentres the chart without a refetch', () => {
      tick();
      respond();
      store.setPreset('1D');
      expect(store.chartTarget().seq).toBe(1);
      backend.verify();
    });

    it('setRange waits 300 ms of quiet, then selects the Range without moving the chart', () => {
      expect(RANGE_DEBOUNCE_MS).toBe(300);
      tick();
      respond();
      store.setRange(W1);
      vi.advanceTimersByTime(200);
      store.setRange(W2);
      vi.advanceTimersByTime(299);
      expect(dashboardRequests()).toHaveLength(0);
      vi.advanceTimersByTime(1);
      const request = one();
      expect(request.request.params.get('mode')).toBe('range');
      expect(request.request.params.get('from')).toBe(W2.from);
      expect(store.selection()).toEqual({ kind: 'range', window: W2 });
      expect(store.preset()).toBeNull();
      expect(store.chartTarget()).toEqual({ window: W2, seq: 0 });
    });

    it('ignores a Range equal to the one already selected', () => {
      tick();
      respond();
      store.setRange(W1);
      vi.advanceTimersByTime(RANGE_DEBOUNCE_MS);
      one().flush(RESPONSE);
      store.setRange({ ...W1 });
      vi.advanceTimersByTime(RANGE_DEBOUNCE_MS);
      backend.verify();
    });

    it('a preset click cancels a Range still settling', () => {
      tick();
      respond();
      store.setRange(W1);
      store.setPreset('1M');
      one().flush(RESPONSE);
      vi.advanceTimersByTime(RANGE_DEBOUNCE_MS);
      backend.verify();
      expect(store.preset()).toBe('1M');
    });

    it('drops the response of a superseded request', () => {
      tick();
      respond();
      store.setPreset('All');
      store.setPreset('5D');
      const [first, second] = dashboardRequests();
      second.flush({ ...RESPONSE, account_balance: 2 });
      first.flush({ ...RESPONSE, account_balance: 1 });
      expect(store.balance()).toBe(2);
    });

    it('recomputes a rolling preset on every refresh, so it follows the New York day', () => {
      tick();
      respond();
      store.setPreset('1M');
      one().flush(RESPONSE);
      vi.setSystemTime(new Date('2026-10-22T05:00:00Z'));   // 01:00 New York, 22 Oct
      store.load();
      const request = one();
      expect(request.request.params.get('from')).toBe('2026-09-22T04:00:00.000Z');
      expect(request.request.params.get('to')).toBe('2026-10-23T04:00:00.000Z');
    });

    it('keeps the last figures, marked stale, when a range refetch fails; a success clears it', () => {
      tick();
      respond();
      store.setPreset('3M');
      one().error(new ProgressEvent('error'), { status: 0 });
      expect(store.balance()).toBe(10_000);
      expect(store.stale()).toBe(true);
      expect(store.preset()).toBe('3M');

      store.load();
      one().flush(RESPONSE);
      expect(store.stale()).toBe(false);
      expect(store.error()).toBeNull();
    });

    it('a failed first load is an error, not stale', () => {
      tick();
      one().error(new ProgressEvent('error'), { status: 0 });
      expect(store.stale()).toBe(false);
      expect(store.error()).not.toBeNull();
    });

    it('keeps setScope for the Today / All days toggle', () => {
      tick();
      respond();
      store.setScope('all');
      one().flush({ ...RESPONSE, scope: { mode: 'all' } });
      expect(store.preset()).toBe('All');
      expect(store.scope()).toBe('all');
    });
    it('does not refetch again when a selection change reaches the init effect', () => {
      tick();
      respond();
      store.setPreset('5D');
      one().flush(RESPONSE);
      tick();
      vi.advanceTimersByTime(RANGE_DEBOUNCE_MS);
      backend.verify();
    });

    it('ignores a superseded failure after the latest figures arrived', () => {
      tick();
      respond();
      store.setPreset('All');
      store.setPreset('5D');
      const [older, latest] = dashboardRequests();
      latest.flush({ ...RESPONSE, account_balance: 20_000 });
      older.error(new ProgressEvent('error'), { status: 0 });
      expect(store.balance()).toBe(20_000);
      expect(store.stale()).toBe(false);
      expect(store.loading()).toBe(false);
      expect(store.error()).toBeNull();
    });
  });

  describe("today's figures and the chart's Latest button", () => {
    const NOW = new Date('2026-10-21T14:00:00Z');
    const TODAY = { amount: 12.5, pct: 0.4, n: 2, wins: 1, losses: 1 };
    const SCOPED = { amount: 480, pct: 3.1, n: 18, wins: 11, losses: 7 };
    const requests = () => backend.match((req) => req.url === '/api/v1/dashboard');
    const modeOf = (req: { request: { params: { get(k: string): string | null } } }) => req.request.params.get('mode');
    const flushScoped = (reqs: ReturnType<typeof requests>) => {
      reqs.filter((r) => modeOf(r) !== 'today').forEach((r) => r.flush({ ...RESPONSE, scope: { mode: 'range' }, realized: SCOPED }));
    };
    const flushToday = (reqs: ReturnType<typeof requests>, realized = TODAY) => {
      reqs.filter((r) => modeOf(r) === 'today').forEach((r) => r.flush({ ...RESPONSE, realized }));
    };

    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(NOW);
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('is the scoped block itself under 1D, with no second request', () => {
      tick();
      const reqs = requests();
      expect(reqs).toHaveLength(1);
      reqs[0].flush({ ...RESPONSE, realized: TODAY });
      expect(store.todayRealized()).toEqual(TODAY);
      expect(store.realized()).toEqual(TODAY);
      expect(store.todayLoading()).toBe(false);
    });

    it('keeps today, fetching nothing extra, when a wider preset is picked after a 1D load', () => {
      tick();
      requests()[0].flush({ ...RESPONSE, realized: TODAY });
      store.setPreset('1M');
      const reqs = requests();
      expect(reqs.map(modeOf)).toEqual(['range']);
      flushScoped(reqs);
      expect(store.realized()).toEqual(SCOPED);
      expect(store.todayRealized()).toEqual(TODAY);
    });

    /** 1D first (today lands), then a wider preset, then a trades push. */
    const widenThenPush = () => {
      tick();
      requests()[0].flush({ ...RESPONSE, realized: TODAY });
      store.setPreset('1M');
      flushScoped(requests());
      events.raise('trades');
      tick();
      vi.advanceTimersByTime(300);
      return requests();
    };

    it('fetches today beside the scoped figures when the scope is wider', () => {
      const reqs = widenThenPush();
      expect(reqs.map(modeOf).sort()).toEqual(['range', 'today']);
      expect(store.todayLoading()).toBe(true);
      expect(store.loading()).toBe(true);
      flushScoped(reqs);
      expect(store.todayLoading()).toBe(true);
      flushToday(reqs, { amount: 30, pct: 1, n: 3, wins: 2, losses: 1 });
      expect(store.todayLoading()).toBe(false);
      expect(store.todayRealized()).toEqual({ amount: 30, pct: 1, n: 3, wins: 2, losses: 1 });
      expect(store.realized()).toEqual(SCOPED);
    });

    it('keeps the previous today figures and stops loading when the today fetch fails', () => {
      const reqs = widenThenPush();
      flushScoped(reqs);
      reqs.filter((r) => modeOf(r) === 'today').forEach((r) => r.flush('boom', { status: 500, statusText: 'Server Error' }));
      expect(store.todayLoading()).toBe(false);
      expect(store.todayRealized()).toEqual(TODAY);
    });

    it("keeps today's lifecycle counts while a wider scope's counts differ", () => {
      tick();
      requests()[0].flush(RESPONSE);
      store.setPreset('1M');
      requests().forEach((r) => r.flush({ ...RESPONSE, lifecycle: { PENDING: 4, ACTIVE: 2, PARTIAL: 1, CLOSED: 40, CANCELLED: 9 } }));
      const closed = (rows: { status: string; count: number }[]) => rows.find((row) => row.status === 'CLOSED')?.count;
      expect(closed(store.lifecycle())).toBe(40);
      expect(closed(store.todayLifecycle())).toBe(3);
      expect(store.todayLifecycle().map((row) => row.status)).toEqual(['PENDING', 'ACTIVE', 'PARTIAL', 'CLOSED', 'CANCELLED']);
    });

    it('reports no today counts before a today response, and none when the collector failed', () => {
      expect(store.todayLifecycle()).toEqual([]);
      tick();
      requests()[0].flush({ ...RESPONSE, lifecycle: {} });
      expect(store.todayLifecycle()).toEqual([]);
    });

    it('tolerates a response with no realised block', () => {
      tick();
      const bare: Partial<Dashboard> = { ...RESPONSE };
      delete bare.realized;
      requests()[0].flush(bare);
      expect(store.todayRealized()).toBeNull();
      expect(store.realized()).toBeNull();
    });

    it('resetView returns a Range to 1D: the 1D request, the chart moved, the pending range dropped', () => {
      tick();
      requests()[0].flush(RESPONSE);
      store.setRange({ from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' });
      vi.advanceTimersByTime(300);
      flushScoped(requests());
      expect(store.selection().kind).toBe('range');
      const seq = store.chartTarget().seq;

      store.resetView();
      const reqs = requests();
      expect(reqs.map(modeOf)).toEqual(['today']);
      expect(store.selection()).toEqual({ kind: 'preset', preset: '1D' });
      expect(store.chartTarget().seq).toBe(seq + 1);
      expect(store.chartTarget().window).not.toBeNull();
    });

    it('resetView returns a wider preset to 1D as well', () => {
      tick();
      requests()[0].flush(RESPONSE);
      store.setPreset('3M');
      flushScoped(requests());
      store.resetView();
      expect(store.preset()).toBe('1D');
      expect(requests().map(modeOf)).toEqual(['today']);
    });

    it('resetView on 1D only recentres the chart: no refetch', () => {
      tick();
      requests()[0].flush(RESPONSE);
      const seq = store.chartTarget().seq;
      store.resetView();
      expect(requests()).toHaveLength(0);
      expect(store.chartTarget().seq).toBe(seq + 1);
    });

    it('resetView cancels a Range still settling, so it never lands on top of Today', () => {
      tick();
      requests()[0].flush(RESPONSE);
      store.setRange({ from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' });
      store.resetView();
      vi.advanceTimersByTime(300);
      expect(requests()).toHaveLength(0);
      expect(store.selection()).toEqual({ kind: 'preset', preset: '1D' });
    });

    /* -- v194 B1: today's figures never go missing for good ----------- */

    const fail = (req: { flush(body: unknown, opts: { status: number; statusText: string }): void }) =>
      req.flush('boom', { status: 500, statusText: 'Server Error' });

    it("lands a 1D answer as today's figures even after a wider pick superseded it", () => {
      tick();
      const [first] = requests();
      // Picked before the 1D load answered: the 1D request is no longer
      // current for the scoped figures, but its answer is still today's.
      store.setPreset('1M');
      first.flush({ ...RESPONSE, realized: TODAY });
      const closed = store.todayLifecycle().find((row) => row.status === 'CLOSED')?.count;
      expect(closed).toBe(3);
      expect(store.todayRealized()).toEqual(TODAY);
      expect(store.data()).toBeNull();
    });

    it('keeps the newest today answer when an older one lands after it', () => {
      const older = widenThenPush();
      // A second push issues a newer today fetch while the older is in flight.
      events.raise('trades');
      tick();
      vi.advanceTimersByTime(300);
      const newer = requests();
      expect(older.filter((r) => modeOf(r) === 'today')).toHaveLength(1);
      expect(newer.filter((r) => modeOf(r) === 'today')).toHaveLength(1);
      const newerFigures = { amount: 45, pct: 1.5, n: 4, wins: 3, losses: 1 };
      flushToday(newer, newerFigures);
      flushToday(older, { amount: 30, pct: 1, n: 3, wins: 2, losses: 1 });
      flushScoped(older);
      flushScoped(newer);
      expect(store.todayRealized()).toEqual(newerFigures);
      expect(store.todayLoading()).toBe(false);
    });

    it('reports a failed today fetch instead of loading forever', () => {
      tick();
      const [first] = requests();
      store.setPreset('1M');
      fail(first);
      const reqs = requests();
      reqs.filter((r) => modeOf(r) === 'today').forEach(fail);
      flushScoped(reqs);
      expect(store.todayLoading()).toBe(false);
      expect(store.todayError()).not.toBeNull();
      expect(store.todayLifecycle()).toEqual([]);
      expect(store.realized()).toEqual(SCOPED);
    });

    it('clears the today error once a today answer lands', () => {
      const reqs = widenThenPush();
      flushScoped(reqs);
      reqs.filter((r) => modeOf(r) === 'today').forEach(fail);
      expect(store.todayError()).not.toBeNull();
      events.raise('trades');
      tick();
      vi.advanceTimersByTime(300);
      const again = requests();
      flushScoped(again);
      flushToday(again);
      expect(store.todayError()).toBeNull();
      expect(store.todayLoading()).toBe(false);
    });

    it('ends a request cancelled before it answered with an error, never an endless skeleton', () => {
      // No tick(): the onInit effect has not issued its own load, so this
      // subscription is the only, and current, request.
      const subscription = store.resolve().subscribe();
      expect(store.loading()).toBe(true);
      subscription.unsubscribe();
      expect(store.loading()).toBe(false);
      expect(store.error()).toBe('The dashboard request did not finish.');
      expect(store.todayLoading()).toBe(false);
    });

    it('lets a superseded request go quietly: the newer one owns loading', () => {
      const older = store.resolve().subscribe();
      store.resolve().subscribe();
      older.unsubscribe();
      expect(store.loading()).toBe(true);
      expect(store.error()).toBeNull();
    });
  });
});
