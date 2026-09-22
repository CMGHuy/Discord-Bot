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

import { convertToParamMap } from '@angular/router';

import { EventStream } from '../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { AnalyticsPerformance, Preferences } from '../api/models';
import { scopePatchFromParams } from '../workspaces/analytics/scope-url';
import {
  AnalyticsStore,
  BREAKDOWN_DIMENSIONS,
  presetRange,
  RELOCATED_METRICS,
} from './analytics.store';
import { PreferencesStore } from './preferences.store';

/* NG48, rewritten for v94 — Analytics.
 *
 * Three properties carry most of the weight here and none is incidental:
 *
 *   1. **One scope reaches every scoped request, and its N is reported.**
 *      v94 D2: two panels on one screen may not be answering about
 *      different populations, and a screen that hides how scoped it is has
 *      a correctness bug.
 *   2. **Every panel fails on its own terms.** v94 H4: a failed fetch sets
 *      THAT panel's error and leaves its neighbours' data alone.
 *   3. **Tuning progress comes from the `jobs` event, not a timer.** The
 *      tests below drive progress purely by raising events; if polling ever
 *      comes back, the assertions about *which* request follows *which*
 *      event are what break.
 *
 * The six relocated Dashboard metrics (spec v14 Decision 6 accepted the cost
 * of moving them, not of losing them) are asserted here only as far as the
 * store carries them; they are rendered by the Overview tab's tiles, so the
 * "all six appear" assertion belongs in `workspaces/analytics/tabs/
 * overview.spec.ts` and Task T1 adds it there.
 *
 * `EventStream` is faked down to the one method a store uses, matching
 * `dashboard.store.spec.ts`.
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

const SCOPE = { from: null, to: null, ledger: 'main' as const, strategy: null, horizon: null, direction: null };

const PERFORMANCE: AnalyticsPerformance = {
  totals: { total: 40, open: 6, closed: 34 },
  relocated: {
    wins: 21,
    losses: 13,
    avg_realized_pct: 1.84,
    best_trade_pct: 12.5,
    worst_trade_pct: -6.1,
    avg_holding_days: 9.2,
  },
  win_rate: 61.8,
  win_rate_n: 34,
  expectancy_r: 0.42,
  expectancy_n: 34,
  by_confidence: {
    '2': { total: 5, open: 1, closed: 4, wins: 2, losses: 2, win_rate: 50 },
    '1': { total: 3, open: 0, closed: 3, wins: 1, losses: 2, win_rate: 33.3 },
  },
  // Deliberately a mix of populated and null figures: the store's job is to
  // pass nulls through as nulls, and a fixture where everything has a value
  // cannot catch a `?? 0` creeping into a computed.
  range: { from: null, to: null, span_years: 2.5, n: 34 },
  derived: {
    avg_win_pct: 4.2,
    avg_loss_pct: -2.1,
    total_return_pct: 18.4,
    annualised_return_pct: 7.1,
    calmar: 1.3,
    volatility_ann_pct: 22.6,
    trades_per_month: 1.1,
    pct_in_market: 44.5,
    sharpe_ann: 0.94,
    sortino_ann: null,
    win_rate: 61.8,
    expectancy_r: 0.42,
  },
  distributions: {
    returns: [
      { lo: -6.1, hi: -1.0, count: 13 },
      { lo: -1.0, hi: 4.1, count: 0 },
      { lo: 4.1, hi: 12.5, count: 21 },
    ],
    r_multiples: [{ lo: -1.0, hi: 2.4, count: 34 }],
  },
  rolling_returns: [{ date: '2026-08-01', return_pct: 3.2 }],
  holding_period_split: [
    { bucket: '0h-2h', n: 0, win_rate: null, avg_return_pct: null },
    { bucket: '2d+', n: 34, win_rate: 61.8, avg_return_pct: 1.8 },
  ],
  risk_reward_split: [],
  calendar: [{ month: '2026-08', return_pct: 3.2, n: 4 }],
  cumulative_by_strategy: {
    MACD: [{ date: '2026-08-02', cum_pct: 4.0 }],
    RSI: [{ date: '2026-08-01', cum_pct: 2.0 }],
  },
  benchmark: { spy_cum: { '2026-08-01': 1.4, '2026-07-01': 0.3 } },
  rolling_wr: [],
  rolling_exp_r: [],
  // v94 T1 -- the Overview tab's Streaks row. Not exercised by anything in
  // this file (that assertion lives in `tabs/overview.spec.ts`); present
  // here only so this fixture still satisfies `AnalyticsPerformance`.
  streaks: { current: 0, current_kind: null, best_win_streak: 2, worst_loss_streak: 1 },
  scope: SCOPE,
  n: 34,
};

const STRATEGIES = {
  strategies: [
    { strategy: 'RSI', status: 'VALIDATED', n: 120, win_rate: 82, expectancy_r: 0.5, decayed: false },
    { strategy: 'MACD', status: 'WEAK', n: 40, win_rate: 61, expectancy_r: 0.1, decayed: true },
  ],
  registry_scope: 'all-time',
  contribution: [],
  cumulative: {},
  scope: SCOPE,
  n: 160,
};

const CALIBRATION = {
  deciles: [{ decile: '80-89', n: 12, win_rate: 83.3, expectancy_r: 0.6 }],
  tiers: [{ tier: 'A', n: 4, win_rate: null, expectancy_r: null, expected_band: '>=80', ok: null }],
  drift: [],
};

const RUNNING_JOB = {
  id: 'abc123',
  kind: 'tune',
  state: 'running',
  started_at: '2026-08-10T09:00:00+00:00',
  finished_at: null,
  returncode: null,
};

const FINISHED_JOB = {
  ...RUNNING_JOB,
  id: 'old999',
  state: 'done',
  started_at: '2026-08-09T09:00:00+00:00',
  finished_at: '2026-08-09T09:40:00+00:00',
  returncode: 0,
};

describe('AnalyticsStore', () => {
  let store: InstanceType<typeof AnalyticsStore>;
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
        AnalyticsStore,
      ],
    });
    store = TestBed.inject(AnalyticsStore);
    backend = TestBed.inject(HttpTestingController);
    store.load();
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();

  const JOURNAL = { digest: ['Two losses, both chased.'], lessons: ['Wait for the retest.'], entries_n: 2, scope: SCOPE, n: 2 };
  const EXIT_QUALITY = {
    exit_reasons: [], unmapped_reasons: [], hold_by_outcome: {}, hold_points: [],
    efficiency: { bins: [], n: 0, median: null }, mae: { bins: [], n: 0, median: null },
    scatter: [], coverage: {}, min_cell_n: 20, scope: SCOPE, n: 34,
  };
  const EQUITY_CURVE = {
    points: [{ date: '2026-04-01', cum_r: 1, drawdown_r: 0, cum_pnl: 70, cum_pct: 0.7 }],
    points_n: 1, as_of: '2026-04-01', benchmark: { spy_indexed: [] }, scope: SCOPE, n: 1,
  };
  const BY_DIMENSION = { rows: [], as_of: null, min_cell_n: 20, scope: SCOPE, n: 34 };
  const HEAT_GRID = {
    rows: [], cols: ['2w', '4w'], cells: [], folded: { n_strategies: 0, cells: [] },
    min_cell_n: 20, scope: SCOPE, n: 34,
  };

  /** Overview asks for exactly two payloads: the scoped record and its
   *  curve. Both are settled here so `backend.verify()` still means
   *  "nothing ELSE went out". */
  const respondOverview = (body: Partial<AnalyticsPerformance> = {}) => {
    backend
      .expectOne((req) => req.url === '/api/v1/analytics/performance')
      .flush({ ...PERFORMANCE, ...body });
    backend
      .expectOne((req) => req.url === '/api/v1/analytics/equity-curve')
      .flush(EQUITY_CURVE);
  };

  const respondStrategies = (body: Record<string, unknown> = {}) =>
    backend.expectOne((req) => req.url === '/api/v1/analytics/strategies').flush({ ...STRATEGIES, ...body });

  const respondCalibration = (body: Record<string, unknown> = {}) =>
    backend.expectOne('/api/v1/analytics/calibration').flush({ ...CALIBRATION, ...body });

  /** Edge: the scoped rolling series, the registry, and all-time calibration. */
  const respondEdge = (calibration: Record<string, unknown> = {}) => {
    backend.expectOne((req) => req.url === '/api/v1/analytics/performance').flush(PERFORMANCE);
    respondStrategies();
    respondCalibration(calibration);
  };

  const respondJobs = (jobs: unknown[]) =>
    backend.expectOne('/api/v1/jobs').flush({ jobs });

  const respondProposals = (proposals: unknown[] = []) =>
    backend.expectOne('/api/v1/analytics/tuning/proposals').flush({ proposals });

  /** Everything the Tuning tab asks for on its first visit, in one call. */
  const openTuning = (jobs: unknown[] = [RUNNING_JOB]) => {
    store.setTab('tuning');
    tick();
    respondJobs(jobs);
    respondProposals();
    respondStrategies();
    if (jobs.length) {
      const id = (jobs[0] as { id: string }).id;
      backend
        .expectOne(`/api/v1/jobs/${id}`)
        .flush({ ...(jobs[0] as object), log_tail: 'grid 3/12\n' });
      // SR51 fetches the tracked job's grid alongside its status, so that the
      // results table is populated for a job that finished between the two
      // responses. Settled here so `backend.verify()` below still means
      // "nothing ELSE went out"; the grid's own behaviour is exercised in
      // `analytics.snapshot.spec.ts`.
      backend
        .expectOne(`/api/v1/jobs/${id}/result`)
        .flush({ job_id: id, strategy: null, grid: [] });
    }
  };

  /* -- the open tab decides what is fetched --------------------------- */

  it('loads Overview on creation, with no separate bootstrap call', () => {
    // The load path and the refetch path are the same path, so they cannot
    // drift apart.
    tick();
    respondOverview();

    expect(store.tab()).toBe('overview');
    expect(store.winRate()).toBe(61.8);
  });

  it('fetches only the open tab', () => {
    tick();
    respondOverview();

    // No strategies, calibration, plans or jobs request went out.
    backend.verify();
  });

  it('fetches the next tab when it is opened', () => {
    tick();
    respondOverview();

    store.setTab('edge');
    tick();
    respondEdge();

    expect(store.strategyRows()).toHaveLength(2);
    // The Overview payload is still there -- switching tabs does not
    // discard what was already loaded.
    expect(store.winRate()).toBe(61.8);
  });

  it('fetches the breakdown, heat grid, registry and record for Attribution', () => {
    tick();
    respondOverview();

    store.setTab('attribution');
    tick();
    const breakdown = backend.expectOne((req) => req.url === '/api/v1/analytics/by-dimension');
    // The dimension the store is grouped by, not a hardcoded one.
    expect(breakdown.request.params.get('dim')).toBe('strategy');
    breakdown.flush(BY_DIMENSION);
    backend.expectOne((req) => req.url === '/api/v1/analytics/heat-grid').flush(HEAT_GRID);
    respondStrategies();
    backend.expectOne((req) => req.url === '/api/v1/analytics/performance').flush(PERFORMANCE);

    expect(store.heatGrid()?.cols).toEqual(['2w', '4w']);
    backend.verify();
  });

  it('refetches only the breakdown when its dimension changes', () => {
    // Unlike v85's snapshot-backed table, `/by-dimension` serves one
    // dimension per request, so another dimension is not already on hand --
    // but it is still only ONE panel that has to move.
    tick();
    respondOverview();
    store.setTab('attribution');
    tick();
    backend.expectOne((req) => req.url === '/api/v1/analytics/by-dimension').flush(BY_DIMENSION);
    backend.expectOne((req) => req.url === '/api/v1/analytics/heat-grid').flush(HEAT_GRID);
    respondStrategies();
    backend.expectOne((req) => req.url === '/api/v1/analytics/performance').flush(PERFORMANCE);

    store.setBreakdown('ledger');
    const again = backend.expectOne((req) => req.url === '/api/v1/analytics/by-dimension');
    expect(again.request.params.get('dim')).toBe('ledger');
    again.flush(BY_DIMENSION);
    backend.verify();
  });

  it('fetches exit quality, the journal and the record for Execution', () => {
    tick();
    respondOverview();

    store.setTab('execution');
    tick();
    backend.expectOne((req) => req.url === '/api/v1/analytics/exit-quality').flush(EXIT_QUALITY);
    backend.expectOne((req) => req.url === '/api/v1/analytics/journal').flush(JOURNAL);
    backend.expectOne((req) => req.url === '/api/v1/analytics/performance').flush(PERFORMANCE);

    expect(store.digest()).toEqual(['Two losses, both chased.']);
    expect(store.minCellN()).toBe(20);
    backend.verify();
  });

  it('folds calibration into Edge rather than giving it a tab of its own', () => {
    tick();
    respondOverview();

    store.setTab('edge');
    tick();
    backend.expectOne((req) => req.url === '/api/v1/analytics/performance').flush(PERFORMANCE);
    respondStrategies();
    backend.expectOne('/api/v1/analytics/calibration').flush({
      deciles: [{ decile: '80-89', n: 12, win_rate: 83.3, expectancy_r: 0.6 }],
      levels: [{ level: 3, n: 4, win_rate: null, expectancy_r: null }],
      drift: [],
    });

    expect(store.deciles()).toHaveLength(1);
    expect(store.tiers()[0].level).toBe(3);
  });

  it('exposes deciles as a fixed-0-100 histogram', () => {
    tick();
    respondOverview();
    store.setTab('edge');
    tick();
    respondEdge({ deciles: [
      { decile: 'D1', n: 12, win_rate: 42, expectancy_r: 0.1 },
      { decile: 'D10', n: 15, win_rate: 88, expectancy_r: 0.4 },
    ] });

    expect(store.decileHistogram()).toEqual([
      { label: 'D1', count: 42 }, { label: 'D10', count: 88 },
    ]);
  });

  it('omits a decile with too few trades to have a win rate yet, rather than charting it as 0', () => {
    tick();
    respondOverview();
    store.setTab('edge');
    tick();
    respondEdge({ deciles: [
      { decile: 'D1', n: 12, win_rate: 42, expectancy_r: 0.1 },
      { decile: 'D5', n: 0, win_rate: null, expectancy_r: null },
    ] });

    expect(store.decileHistogram()).toEqual([{ label: 'D1', count: 42 }]);
  });

  it('fetches /analytics/plans when the Pipeline tab opens', () => {
    tick();
    respondOverview();

    store.setTab('pipeline');
    tick();
    backend.expectOne('/api/v1/analytics/plans').flush({
      funnel: { posted: 10, filled: 8, hit_tp1: 5, closed: 4 },
      in_flight: 3,
      fill_rate: { resolved_n: 7, fill_rate_pct: 71.4, median_days_to_fill: 2.5 },
      badges: { VALIDATED: 7, WEAK: 3 },
      tiers: { A: 4, B: 3, C: 3 },
    });
    expect(store.funnelChart()).toEqual([
      { label: 'Posted', count: 10 }, { label: 'Filled', count: 8 },
      { label: 'Hit TP1', count: 5 }, { label: 'Closed', count: 4 },
    ]);
    expect(store.fillRatePct()).toBe(71.4);
    expect(store.medianDaysToFill()).toBe(2.5);
    expect(store.badgeChart()).toEqual([
      { label: 'VALIDATED', count: 7 }, { label: 'WEAK', count: 3 },
    ]);
    expect(store.tierChart()).toEqual([
      { label: 'A', count: 4 }, { label: 'B', count: 3 }, { label: 'C', count: 3 },
    ]);
  });

  it('says how many panels on the open tab ignore the scope bar', () => {
    // v94 D2/H2: Edge's evidence and every Pipeline panel are all-time by
    // construction, and the bar has to say so rather than imply they moved.
    tick();
    respondOverview();
    expect(store.allTimePanelCount()).toBe(0);

    store.setTab('edge', false);
    expect(store.allTimePanelCount()).toBe(3);
    store.setTab('pipeline', false);
    expect(store.allTimePanelCount()).toBe(4);
  });

  /* -- the six relocated metrics -------------------------------------- */

  it('carries all six metrics relocated from the Dashboard', () => {
    // Spec v14 Decision 6 accepted the cost of moving them one click away,
    // not of losing them. The tiles that render them live on the Overview
    // tab now, so `tabs/overview.spec.ts` asserts the render (Task T1);
    // this asserts the store still carries every key they are driven from.
    tick();
    respondOverview();

    const block = store.performance()!.relocated;
    expect(RELOCATED_METRICS.every((metric) => metric.key in block)).toBe(true);
    expect(block['avg_holding_days']).toBe(9.2);
  });

  it('flattens the confidence breakdown into rows in level order', () => {
    // JSON turns the level keys into strings, where "10" would sort before
    // "2" if a sixth level ever appeared.
    tick();
    respondOverview();

    expect(store.byConfidence().map((row) => row.level)).toEqual([1, 2]);
    expect(store.byConfidence()[1].win_rate).toBe(50);
  });

  /* -- events, per tab ------------------------------------------------- */

  it('refetches Overview on an analytics event', () => {
    tick();
    respondOverview();

    events.raise('analytics');
    store.load();
    respondOverview({ win_rate: 70 });

    expect(store.winRate()).toBe(70);
  });

  it('ignores a jobs event while Overview is open', () => {
    tick();
    respondOverview();

    events.raise('jobs');
    tick();

    backend.verify();
  });

  /* -- tuning ---------------------------------------------------------- */

  it('loads jobs, proposals and the tracked job for the Tuning tab', () => {
    tick();
    respondOverview();
    openTuning();

    expect(store.job()?.id).toBe('abc123');
    expect(store.job()?.log_tail).toContain('grid 3/12');
    expect(store.jobActive()).toBe(true);
  });

  it('tracks the running job even when a newer finished one exists', () => {
    tick();
    respondOverview();

    store.setTab('tuning');
    tick();
    // Newest first, as job_manager.all() sorts them -- but the finished one
    // is not the one whose progress matters.
    respondJobs([FINISHED_JOB, RUNNING_JOB]);
    respondProposals();
    respondStrategies();
    backend.expectOne('/api/v1/jobs/abc123').flush({ ...RUNNING_JOB, log_tail: '' });

    expect(store.job()?.id).toBe('abc123');
    expect(store.pastJobs().map((job) => job.id)).toEqual(['old999']);
  });

  it('falls back to the most recent job when nothing is running', () => {
    // The Jinja page reloaded the window the moment a job stopped running,
    // throwing away the log at the moment it became worth reading.
    tick();
    respondOverview();
    openTuning([FINISHED_JOB]);

    expect(store.job()?.id).toBe('old999');
    expect(store.jobActive()).toBe(false);
  });

  it('clears the tracked job when there are none', () => {
    tick();
    respondOverview();
    openTuning([]);

    expect(store.job()).toBeNull();
  });

  it('refetches job progress on a jobs event, with no timer', () => {
    tick();
    respondOverview();
    openTuning();

    events.raise('jobs');
    store.load();
    respondJobs([RUNNING_JOB]);
    respondProposals();
    // NOT strategies: already loaded, and a running grid raises this event
    // per log flush.
    backend
      .expectOne('/api/v1/jobs/abc123')
      .flush({ ...RUNNING_JOB, log_tail: 'grid 9/12\n' });

    expect(store.job()?.log_tail).toContain('9/12');
  });

  it('ignores an analytics event while Tuning is open', () => {
    tick();
    respondOverview();
    openTuning();

    events.raise('analytics');
    tick();

    backend.verify();
  });

  it('launches a TRAIN grid and reloads the tuning view', () => {
    tick();
    respondOverview();
    openTuning([]);

    store.startTune('RSI');
    const posted = backend.expectOne('/api/v1/jobs/tune');
    expect(posted.request.method).toBe('POST');
    // Strategy only. No date argument exists, because the window is TRAIN
    // and the server refuses anything else.
    expect(posted.request.body).toEqual({ strategy: 'RSI' });
    posted.flush({ job_id: 'abc123' });

    respondJobs([RUNNING_JOB]);
    respondProposals();
    backend.expectOne('/api/v1/jobs/abc123').flush({ ...RUNNING_JOB, log_tail: '' });

    expect(store.launching()).toBe(false);
    expect(store.job()?.id).toBe('abc123');
  });

  it('reports a launch conflict separately from a stale-data error', () => {
    tick();
    respondOverview();
    openTuning([]);

    store.startTune('RSI');
    backend
      .expectOne('/api/v1/jobs/tune')
      .flush(
        { error: { code: 'conflict', message: 'Another job is already running.' } },
        { status: 409, statusText: 'Conflict' },
      );

    expect(store.launchError()).toContain('already running');
    // The workspace-level error is untouched: this is about the button that
    // was just pressed, not about the data on screen.
    expect(store.error()).toBeNull();
  });

  it('refetches proposals after deleting one', () => {
    tick();
    respondOverview();
    openTuning([]);

    store.removeProposal('20260810-rsi.json');
    const deleted = backend.expectOne(
      '/api/v1/analytics/tuning/proposals/20260810-rsi.json',
    );
    expect(deleted.request.method).toBe('DELETE');
    deleted.flush(null);

    respondProposals([{ filename: 'other.json', strategy: 'MACD' }]);
    expect(store.proposals()).toHaveLength(1);
  });

  it('offers the registry strategies to the launcher', () => {
    // Sourced from the registry rather than hardcoded: the server whitelists
    // the name and 400s on anything it does not know.
    tick();
    respondOverview();
    openTuning([]);

    expect(store.strategyRows().map((row) => row.strategy)).toEqual(['RSI', 'MACD']);
  });

  /* -- per-panel failure (v94 H4) -------------------------------------- */

  it('keeps a failed panel error out of its neighbours', () => {
    store.setTab('execution', false);
    store.load();
    // The Overview load from `beforeEach` is still outstanding; it is not
    // what this test is about.
    backend.match((req) => req.url === '/api/v1/analytics/equity-curve')
      .forEach((request) => request.flush(EQUITY_CURVE));
    backend.match((req) => req.url === '/api/v1/analytics/performance')
      .forEach((request) => request.flush(PERFORMANCE));

    backend.expectOne((req) => req.url === '/api/v1/analytics/exit-quality')
      .flush({ message: 'boom' }, { status: 500, statusText: 'Server Error' });
    backend.expectOne((req) => req.url === '/api/v1/analytics/journal')
      .flush({ ...JOURNAL, digest: ['ok'], lessons: [], entries_n: 1, n: 1 });

    expect(store.exitQualityError()).not.toBeNull();
    expect(store.journalError()).toBeNull();
    expect(store.digest()).toEqual(['ok']);
  });

  it('keeps the data on screen when a refetch fails', () => {
    tick();
    respondOverview();

    events.raise('analytics');
    store.load();
    backend
      .expectOne((req) => req.url === '/api/v1/analytics/performance')
      .error(new ProgressEvent('error'), { status: 0 });
    backend
      .expectOne((req) => req.url === '/api/v1/analytics/equity-curve')
      .error(new ProgressEvent('error'), { status: 0 });

    expect(store.winRate()).toBe(61.8);
    expect(store.performanceError()).toContain('not responding');
  });

  it('clears each panel error once its own refetch succeeds', () => {
    // Two independent failure modes, two independent recoveries.
    tick();
    backend
      .expectOne((req) => req.url === '/api/v1/analytics/performance')
      .error(new ProgressEvent('error'), { status: 0 });
    backend
      .expectOne((req) => req.url === '/api/v1/analytics/equity-curve')
      .error(new ProgressEvent('error'), { status: 0 });
    expect(store.performanceError()).not.toBeNull();
    expect(store.equityCurveError()).not.toBeNull();

    events.raise('analytics');
    store.load();
    respondOverview();

    expect(store.performanceError()).toBeNull();
    expect(store.equityCurveError()).toBeNull();
  });

  it('retries exactly one panel', () => {
    tick();
    respondOverview();

    store.reload('equityCurve');
    backend.expectOne((req) => req.url === '/api/v1/analytics/equity-curve').flush(EQUITY_CURVE);
    // Nothing else moved: a retry is about the panel that failed.
    backend.verify();
  });

  /* -- the one scope ---------------------------------------------------- */

  describe('the analytics scope', () => {
    it('resolves the range presets inclusively and without local-time drift', () => {
      const today = new Date('2026-09-17T12:00:00Z');
      expect(presetRange('30d', today)).toEqual({ from: '2026-08-19', to: '2026-09-17' });
      expect(presetRange('ytd', today)).toEqual({ from: '2026-01-01', to: '2026-09-17' });
      expect(presetRange('all', today)).toEqual({ from: null, to: null });
    });

    it('carries the unit and offers every server-supported scoped breakdown', () => {
      expect(BREAKDOWN_DIMENSIONS.map((dimension) => dimension.value)).toEqual([
        'strategy', 'horizon', 'direction', 'dow', 'month', 'badge',
        'confidence', 'source', 'ledger', 'ticker',
      ]);
      expect(BREAKDOWN_DIMENSIONS.map((d) => d.value)).toContain('ledger');
      expect(BREAKDOWN_DIMENSIONS.map((d) => d.value)).toContain('strategy');
      expect(store.unit()).toBe('r');
      store.setUnit('money');
      expect(store.unit()).toBe('money');
      // No refetch: every unit is already in the payload (v94 D3).
      backend.match((req) => req.url === '/api/v1/analytics/performance')
        .forEach((request) => request.flush(PERFORMANCE));
      backend.match((req) => req.url === '/api/v1/analytics/equity-curve')
        .forEach((request) => request.flush(EQUITY_CURVE));
      backend.verify();
    });

    /** Settle the first load so the assertions below are about the refetch. */
    const openOverview = () => {
      tick();
      respondOverview();
    };

    it('sends one scope to every Overview request and reports its N', () => {
      openOverview();

      store.setScope({ from: '2026-08-01', ledger: 'both', strategy: 'MACD' });
      tick();

      const perf = backend.expectOne((r) => r.url === '/api/v1/analytics/performance');
      expect(perf.request.params.get('from')).toBe('2026-08-01');
      expect(perf.request.params.get('ledger')).toBe('both');
      expect(perf.request.params.get('strategy')).toBe('MACD');
      perf.flush({
        ...PERFORMANCE, n: 312,
        scope: { from: '2026-08-01', to: null, ledger: 'both', strategy: 'MACD', horizon: null, direction: null },
      });

      const curve = backend.expectOne((r) => r.url === '/api/v1/analytics/equity-curve');
      expect(curve.request.params.get('strategy')).toBe('MACD');
      expect(curve.request.params.get('ledger')).toBe('both');
      curve.flush(EQUITY_CURVE);

      expect(store.scopeN()).toBe(312);
      expect(store.activeFilterCount()).toBe(3);
    });

    it('sends both bounds as query parameters, not as a client-side filter', () => {
      openOverview();

      store.setScope({ from: '2026-01-01', to: '2026-06-30' });
      tick();

      const request = backend.expectOne((req) => req.url === '/api/v1/analytics/performance');
      expect(request.request.params.get('from')).toBe('2026-01-01');
      expect(request.request.params.get('to')).toBe('2026-06-30');
      request.flush(PERFORMANCE);
      backend.expectOne((req) => req.url === '/api/v1/analytics/equity-curve').flush(EQUITY_CURVE);
    });

    it('omits an unset bound instead of sending it empty', () => {
      openOverview();

      store.setScope({ from: '2026-01-01' });
      tick();

      const request = backend.expectOne((req) => req.url === '/api/v1/analytics/performance');
      expect(request.request.params.get('from')).toBe('2026-01-01');
      expect(request.request.params.has('to')).toBe(false);
      request.flush(PERFORMANCE);
      backend.expectOne((req) => req.url === '/api/v1/analytics/equity-curve').flush(EQUITY_CURVE);
    });

    it('normalises an inverted range rather than rejecting it', () => {
      // A date picker mid-edit legitimately produces from > to; erroring
      // there surfaces a problem the user is one keystroke from fixing.
      openOverview();

      store.setScope({ from: '2026-06-30', to: '2026-01-01' });
      tick();

      expect(store.scope().from).toBe('2026-01-01');
      expect(store.scope().to).toBe('2026-06-30');
      respondOverview();
    });

    it('makes exactly one request per panel per scope change', () => {
      // Every field moves together, so a scope pick cannot fire two requests
      // for one panel whose responses could land out of order.
      openOverview();

      store.setScope({ from: '2026-01-01', to: '2026-06-30' });
      tick();

      backend.expectOne((req) => req.url === '/api/v1/analytics/performance').flush(PERFORMANCE);
      backend.expectOne((req) => req.url === '/api/v1/analytics/equity-curve').flush(EQUITY_CURVE);
      backend.verify();
    });

    it('clearScope goes back to the default book, unbounded', () => {
      openOverview();
      store.setScope({ from: '2026-01-01', to: '2026-06-30', ledger: 'both' });
      tick();
      respondOverview();

      store.clearScope();
      tick();

      const request = backend.expectOne((req) => req.url === '/api/v1/analytics/performance');
      expect(request.request.params.has('from')).toBe(false);
      expect(request.request.params.has('to')).toBe(false);
      expect(store.scope().ledger).toBe('main');
      expect(store.activeFilterCount()).toBe(0);
      request.flush(PERFORMANCE);
      backend.expectOne((req) => req.url === '/api/v1/analytics/equity-curve').flush(EQUITY_CURVE);
    });

    it('hydrates from the URL without firing a request', () => {
      openOverview();

      store.hydrate({ ...SCOPE, ledger: 'weak' }, 'pct');

      expect(store.scope().ledger).toBe('weak');
      expect(store.unit()).toBe('pct');
      // The route resolver fetches; hydrate only sets state.
      backend.verify();
    });

    it('passes null figures through as null rather than zero', () => {
      // The regression this guards: a `?? 0` in a computed turns "not enough
      // trades for a Sortino" into a confident 0.00 on a KPI card.
      openOverview();

      expect(store.derived().sortino_ann).toBeNull();
      expect(store.derived().calmar).toBe(1.3);
    });

    it('reports an all-null derived block before the first response', () => {
      // No tick, no flush: nothing has arrived yet.
      expect(store.derived().calmar).toBeNull();
      expect(store.scopeN()).toBeNull();
    });

    it('labels histogram buckets by their lower edge so losses read as losses', () => {
      openOverview();

      const bins = store.returnsHistogram();
      expect(bins[0].label).toBe('-6.1%');
      // The empty interior bucket survives — dropping it would let the chart
      // silently redraw its own axis.
      expect(bins[1].count).toBe(0);
      expect(bins).toHaveLength(3);
    });

    it('exposes month bar rows computed from calendarReturns, sign intact', () => {
      tick();
      respondOverview({ calendar: [
        { month: '2026-06', return_pct: 4.2, n: 3 },
        { month: '2026-07', return_pct: -1.8, n: 2 },
      ] });

      expect(store.monthBars()).toEqual([
        { label: '2026-06', value: 4.2, n: 3 },
        { label: '2026-07', value: -1.8, n: 2 },
      ]);
    });

    it('exposes holding-period and planned-R:R win-rate bar rows with sample sizes', () => {
      tick();
      respondOverview({
        holding_period_split: [{ bucket: '0h-2h', n: 0, win_rate: null, avg_return_pct: null }, { bucket: '2h-4h', n: 3, win_rate: 66.7, avg_return_pct: 1.1 }],
        risk_reward_split: [{ bucket: '<1.5', n: 0, win_rate: null, avg_return_pct: null }, { bucket: '1.5-2', n: 4, win_rate: 50, avg_return_pct: 0.4 }],
      });
      expect(store.holdingPeriodBars()).toEqual([{ label: '0h-2h', value: null, n: 0, withheld: true }, { label: '2h-4h', value: 66.7, n: 3, withheld: false }]);
      expect(store.riskRewardBars()).toEqual([{ label: '<1.5', value: null, n: 0, withheld: true }, { label: '1.5-2', value: 50, n: 4, withheld: false }]);
    });

    it('reports the population the scope produced, and when it was built', () => {
      openOverview();

      expect(store.scopeN()).toBe(34);
      expect(store.asOf()).toBe('2026-04-01');
    });
  });
});

/* -- the remembered scope --------------------------------------------------
 *
 * v94's promise is "the URL wins where it speaks; the preference answers
 * where it is silent", and the half that is easy to get wrong is the second
 * one. `setScope`/`setUnit` write the preference on every call, so the write
 * path looks healthy whether or not anything ever reads it back -- exactly
 * the failure `PreferencesStore.isLoaded`'s own docstring warns about. These
 * tests drive the real composition the route resolver uses
 * (`scopePatchFromParams` into `hydrate`) rather than `hydrate` alone,
 * because the bug this guards lived in the seam between the two: a
 * `scopeFromParams` that defaults every absent field, handed to a `hydrate`
 * that replaced the whole scope.
 */
describe('AnalyticsStore — the remembered scope', () => {
  const REMEMBERED: Preferences = {
    analyticsScope: { ledger: 'both', strategy: 'MACD' },
    analyticsUnit: 'money',
  };

  /** Only the two methods the store calls, so nothing else can drift. */
  const preferencesStub = (values: Preferences) => ({
    values: () => values,
    update: (mutate: (prefs: Preferences) => Preferences) => { values = mutate(values); },
  });

  const storeWith = (values: Preferences): InstanceType<typeof AnalyticsStore> => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        { provide: PreferencesStore, useValue: preferencesStub(values) },
        AnalyticsStore,
      ],
    });
    return TestBed.inject(AnalyticsStore);
  };

  /** What `analytics.routes.ts`'s resolver does, on one URL. */
  const navigate = (store: InstanceType<typeof AnalyticsStore>, query: Record<string, string>) => {
    const { scope, unit } = scopePatchFromParams(convertToParamMap(query));
    store.hydrate(scope, unit);
  };

  it('seeds the scope and unit from the remembered preference', () => {
    const store = storeWith(REMEMBERED);

    expect(store.scope().ledger).toBe('both');
    expect(store.scope().strategy).toBe('MACD');
    expect(store.unit()).toBe('money');
  });

  it('keeps the remembered scope when the URL says nothing about it', () => {
    // The regression: the resolver runs on EVERY navigation
    // (runGuardsAndResolvers: 'always'), so a hydrate that replaced the
    // whole scope reset the remembered one to the defaults every time --
    // silently, because the write path still worked.
    const store = storeWith(REMEMBERED);

    navigate(store, {});

    expect(store.scope().ledger).toBe('both');
    expect(store.scope().strategy).toBe('MACD');
    expect(store.unit()).toBe('money');
  });

  it('lets the URL override exactly the field it names, and no other', () => {
    const store = storeWith(REMEMBERED);

    navigate(store, { ledger: 'weak', unit: 'pct' });

    expect(store.scope().ledger).toBe('weak');
    // Untouched by this URL, so still the remembered value.
    expect(store.scope().strategy).toBe('MACD');
    expect(store.unit()).toBe('pct');

    navigate(store, { from: '2026-08-01' });

    expect(store.scope().from).toBe('2026-08-01');
    expect(store.scope().ledger).toBe('weak');
    // No `unit=` on this URL, so the one already resolved stands.
    expect(store.unit()).toBe('pct');
  });

  it('falls back to the plain defaults when nothing is remembered', () => {
    const store = storeWith({});

    expect(store.scope()).toEqual(SCOPE);
    expect(store.unit()).toBe('r');
  });
});
