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
import { AnalyticsStore } from './analytics.store';

/* SR51 — the tuning grid and Propose.
 *
 * SR50's own block lived here too: `GET /analytics/snapshot`, the pre-built
 * all-time blob that profit factor, Sharpe, Sortino, max drawdown, streaks
 * and the ten-dimension `by` table were read from. v94 retired it as this
 * store's source — every panel now reads a SCOPED endpoint instead, because
 * an all-time blob cannot answer a question about a filtered book, and a
 * screen that silently answers about a different population than the one on
 * its bar is the failure v94 exists to remove. Those eleven tests went with
 * the surface they tested; the scoped replacements live in
 * `analytics.store.spec.ts`.
 *
 * What is left here is untouched by that: the grid results the Tuning tab
 * stages proposals from. `binRMultiples`, the R-multiple binning pure
 * function this file used to also test, went with T7's removal of its last
 * caller.
 */

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();

  changes(name: string): Signal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter.asReadonly();
  }
}

const SCOPE = { from: null, to: null, ledger: 'main' as const, strategy: null, horizon: null, direction: null };

const PERFORMANCE = {
  totals: { total: 10, open: 2, closed: 8 },
  relocated: {
    wins: 5,
    losses: 3,
    avg_realized_pct: 1.2,
    best_trade_pct: 8,
    worst_trade_pct: -4,
    avg_holding_days: 6,
  },
  win_rate: 62.5,
  expectancy_r: 0.31,
  by_confidence: {},
  scope: SCOPE,
  n: 8,
};

const EQUITY_CURVE = {
  points: [], points_n: 0, as_of: null, benchmark: { spy_indexed: [] }, scope: SCOPE, n: 0,
};

/* SR51 — the grid results and Propose.
 *
 * Before this the Tuning tab could launch a grid and delete proposals, but
 * nothing could create one: the Propose button lived in the results table that
 * never migrated. POST /analytics/tuning/proposals already existed and took a
 * job_id and a row_index; what was missing was any way to see the rows.
 */
describe('AnalyticsStore — the tuning grid', () => {
  let store: InstanceType<typeof AnalyticsStore>;
  let backend: HttpTestingController;

  const JOBS = {
    jobs: [{ id: 'job1', state: 'done', started_at: '2026-08-14T05:00:00Z' }],
  };

  const GRID = {
    job_id: 'job1',
    strategy: 'RSI Divergence',
    grid: [
      { row_index: 0, params: { rsi_reclaim: 30, atr_mult: 1.5 }, n_eval: 40,
        win_rate: 82, expectancy_r: 0.4, excluded_share: 0.2, passes: true },
      { row_index: 1, params: { rsi_reclaim: 35 }, n_eval: 12,
        win_rate: 90, expectancy_r: 0.6, excluded_share: 0.1, passes: false },
    ],
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        AnalyticsStore,
      ],
    });
    store = TestBed.inject(AnalyticsStore);
    backend = TestBed.inject(HttpTestingController);
  });

  /** Open Tuning and settle every request it makes. */
  function openTuning(grid: object = GRID) {
    store.load();
    const tick = () => TestBed.inject(ApplicationRef).tick();
    tick();
    // Overview is the tab the store opens on; settle its two payloads first.
    backend.expectOne((req) => req.url === '/api/v1/analytics/performance').flush(PERFORMANCE);
    backend.expectOne((req) => req.url === '/api/v1/analytics/equity-curve').flush(EQUITY_CURVE);

    store.setTab('tuning');
    tick();
    backend.expectOne('/api/v1/jobs').flush(JOBS);
    backend.expectOne('/api/v1/jobs/job1').flush({
      id: 'job1', state: 'done', log_tail: 'grid 12/12',
    });
    backend.expectOne('/api/v1/jobs/job1/result').flush(grid);
    backend.expectOne('/api/v1/analytics/tuning/proposals').flush({ proposals: [] });
    backend.expectOne((req) => req.url === '/api/v1/analytics/strategies')
      .flush({ strategies: [], registry_scope: 'all-time', contribution: [], cumulative: {}, scope: SCOPE, n: 0 });
  }

  it('fetches the tracked job result and reads its rows', () => {
    openTuning();
    expect(store.gridStrategy()).toBe('RSI Divergence');
    expect(store.grid()).toHaveLength(2);
  });

  it('flattens the parameters into one label', () => {
    // Done in the store because a template that iterated the object would be
    // asserting the wire format of something the Python side owns.
    openTuning();
    expect(store.grid()[0].paramLabel).toBe('rsi_reclaim=30, atr_mult=1.5');
  });

  it('trusts the server on which rows cleared the bar', () => {
    // The bar is four conditions and the same one tune_strategy.py prints. A
    // second copy in TypeScript is how the two come to disagree.
    openTuning();
    expect(store.grid().map((row) => row.passes)).toEqual([true, false]);
  });

  it('keeps each row own index for Propose to post', () => {
    openTuning();
    expect(store.grid().map((row) => row.row_index)).toEqual([0, 1]);
  });
  it('shows no grid while a job is still running', () => {
    // The endpoint answers 200 with an empty grid rather than 404ing, so this
    // is not an error state and must not read as one.
    openTuning({ job_id: 'job1', strategy: null, grid: [] });
    expect(store.grid()).toEqual([]);
    expect(store.error()).toBeNull();
  });

  it('proposes a row against the tracked job, then refetches the list', () => {
    openTuning();
    store.propose(1);

    const posted = backend.expectOne('/api/v1/analytics/tuning/proposals');
    expect(posted.request.method).toBe('POST');
    expect(posted.request.body).toEqual({ job_id: 'job1', row_index: 1 });
    posted.flush({ filename: '20260814-rsi.json', proposal: {} });

    // Refetched rather than spliced in locally: the store holds one server
    // response and derives everything else.
    backend.expectOne('/api/v1/analytics/tuning/proposals').flush({ proposals: [] });
    expect(store.proposeResult()).toContain('20260814-rsi.json');
    expect(store.proposing()).toBeNull();
  });

  it('marks only the row being proposed as pending', () => {
    openTuning();
    store.propose(1);
    expect(store.proposing()).toBe(1);
    backend.expectOne('/api/v1/analytics/tuning/proposals')
      .flush({ filename: 'x.json', proposal: {} });
    backend.expectOne('/api/v1/analytics/tuning/proposals').flush({ proposals: [] });
  });

  it('reports a stale job or row in words someone can act on', () => {
    openTuning();
    store.propose(9);
    backend.expectOne('/api/v1/analytics/tuning/proposals').flush(
      { error: { code: 'not_found', message: 'Could not find that job/row.' } },
      { status: 404, statusText: 'Not Found' },
    );

    expect(store.proposeError()).toContain('reload');
    expect(store.proposing()).toBeNull();
  });

  it('does nothing when there is no tracked job to propose against', () => {
    // No job means no job_id, and posting without one would 404 on the server
    // for a reason the user could do nothing about.
    store.propose(0);
    backend.verify();
  });
});
