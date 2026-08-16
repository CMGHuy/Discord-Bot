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
import { AnalyticsPerformance } from '../api/models';
import { AnalyticsStore, RELOCATED_METRICS } from './analytics.store';

/* NG48 — Analytics.
 *
 * Two properties carry most of the weight here and neither is incidental:
 *
 *   1. **The six relocated Dashboard metrics arrive.** Spec v14 Decision 6
 *      accepted the cost of moving them one click away, not of losing them,
 *      so "all six are present" is asserted rather than assumed.
 *   2. **Tuning progress comes from the `jobs` event, not a timer.** The
 *      tests below drive progress purely by raising events; if polling ever
 *      comes back, the assertions about *which* request follows *which*
 *      event are what break.
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
  expectancy_r: 0.42,
  by_confidence: {
    '2': { total: 5, open: 1, closed: 4, wins: 2, losses: 2, win_rate: 50 },
    '1': { total: 3, open: 0, closed: 3, wins: 1, losses: 2, win_rate: 33.3 },
  },
  // SR54. Deliberately a mix of populated and null figures: the store's job
  // is to pass nulls through as nulls, and a fixture where everything has a
  // value cannot catch a `?? 0` creeping into a computed.
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
    { bucket: '0-2d', n: 0, win_rate: null, avg_return_pct: null },
    { bucket: '8-30d', n: 34, win_rate: 61.8, avg_return_pct: 1.8 },
  ],
  calendar: [{ month: '2026-08', return_pct: 3.2, n: 4 }],
  cumulative_by_strategy: {
    MACD: [{ date: '2026-08-02', cum_pct: 4.0 }],
    RSI: [{ date: '2026-08-01', cum_pct: 2.0 }],
  },
  benchmark: { spy_cum: { '2026-08-01': 1.4, '2026-07-01': 0.3 } },
};

const STRATEGIES = {
  strategies: [
    { strategy: 'RSI', status: 'VALIDATED', n: 120, win_rate: 82, expectancy_r: 0.5, decayed: false },
    { strategy: 'MACD', status: 'WEAK', n: 40, win_rate: 61, expectancy_r: 0.1, decayed: true },
  ],
  heatmap: {
    strategies: ['RSI'],
    horizons: ['2w', '1m'],
    cells: [{ strategy: 'RSI', horizon: '2w', n: 12, win_rate: 75 }],
  },
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
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();

  /** The smallest snapshot the store will accept. Deliberately minimal — this
   *  file is about which requests go out for which tab, not about the blob. */
  const SNAPSHOT = {
    built_at: '2026-08-14T06:00:00Z',
    overall: {},
    equity_curve: { points: [] },
    drawdown: [],
    rolling_wr: [],
    by: {},
    calibration: {},
    r_multiples: [],
  };

  /**
   * The Performance tab makes THREE requests, not one.
   *
   * SR50 added `/analytics/snapshot` beside it: the snapshot is a whole
   * pre-built blob with its own endpoint, and folding it into the summary
   * response would make every visit carry the equity curve whether or not the
   * panels reading it are on screen. Both are settled here so the
   * `backend.verify()` assertions below still mean "nothing ELSE went out".
   *
   * The snapshot's own contents are exercised in `analytics.snapshot.spec.ts`.
   */
  const JOURNAL = { digest: ['Two losses, both chased.'], lessons: ['Wait for the retest.'], entries_n: 2 };

  const respondPerformance = (body: Partial<AnalyticsPerformance> = {}) => {
    backend
      .expectOne('/api/v1/analytics/performance')
      .flush({ ...PERFORMANCE, ...body });
    backend.expectOne('/api/v1/analytics/snapshot').flush(SNAPSHOT);
    // SR55 made it THREE. Same reasoning as the snapshot above: the journal
    // is its own module behind its own endpoint, and folding it into the
    // performance response would let a journal read failure empty the KPI
    // cards. Settled here so `backend.verify()` still means "nothing ELSE".
    backend.expectOne('/api/v1/analytics/journal').flush(JOURNAL);
  };

  const respondStrategies = (body: Record<string, unknown> = {}) =>
    backend.expectOne('/api/v1/analytics/strategies').flush({ ...STRATEGIES, ...body });

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

  it('loads Performance on creation, with no separate bootstrap call', () => {
    // The first effect run IS the initial load, so the load path and the
    // refetch path cannot drift apart.
    tick();
    respondPerformance();

    expect(store.winRate()).toBe(61.8);
  });

  it('fetches only the open tab', () => {
    tick();
    respondPerformance();

    // No strategies, calibration or jobs request went out.
    backend.verify();
  });

  it('fetches the next tab when it is opened', () => {
    tick();
    respondPerformance();

    store.setTab('strategies');
    tick();
    respondStrategies();

    expect(store.strategyRows()).toHaveLength(2);
    // The Performance payload is still there -- switching tabs does not
    // discard what was already loaded.
    expect(store.winRate()).toBe(61.8);
  });

  it('fetches calibration for the Calibration tab', () => {
    tick();
    respondPerformance();

    store.setTab('calibration');
    tick();
    backend.expectOne('/api/v1/analytics/calibration').flush({
      deciles: [{ decile: '80-89', n: 12, win_rate: 83.3, expectancy_r: 0.6 }],
      tiers: [{ tier: 'A', n: 4, win_rate: null, expectancy_r: null, expected_band: '>=80', ok: null }],
      drift: [],
    });

    expect(store.deciles()).toHaveLength(1);
    expect(store.tiers()[0].ok).toBeNull();
  });

  /* -- the six relocated metrics -------------------------------------- */

  it('exposes all six metrics relocated from the Dashboard', () => {
    tick();
    respondPerformance();

    const relocated = store.relocated();
    expect(relocated.map((metric) => metric.key)).toEqual([
      'wins',
      'losses',
      'avg_realized_pct',
      'best_trade_pct',
      'worst_trade_pct',
      'avg_holding_days',
    ]);
    expect(relocated.map((metric) => metric.value)).toEqual([
      21, 13, 1.84, 12.5, -6.1, 9.2,
    ]);
    expect(store.missingRelocated()).toEqual([]);
  });

  it('reports a relocated metric the API stopped sending', () => {
    // The whole point of the check: a metric that silently vanished looks
    // exactly like a metric that has no value yet.
    tick();
    respondPerformance({
      relocated: { wins: 21, losses: 13, avg_realized_pct: 1.84 },
    });

    expect(store.missingRelocated()).toEqual([
      'Best trade',
      'Worst trade',
      'Avg holding',
    ]);
    // Still six rows -- the missing ones render as em dashes rather than
    // shortening the list.
    expect(store.relocated()).toHaveLength(RELOCATED_METRICS.length);
  });

  it('treats a null metric as present, not as missing', () => {
    // Null is the server saying "no closed trades yet", which is a real
    // answer; only an absent key means the relocation lost something.
    tick();
    respondPerformance({
      relocated: {
        wins: 0,
        losses: 0,
        avg_realized_pct: null,
        best_trade_pct: null,
        worst_trade_pct: null,
        avg_holding_days: null,
      },
    });

    expect(store.missingRelocated()).toEqual([]);
    expect(store.relocated()[2].value).toBeNull();
  });

  it('marks only the three percentage metrics as P&L', () => {
    // Green and red mean P&L direction and nothing else; a count of wins is
    // not money and must not be coloured.
    tick();
    respondPerformance();

    const pnl = store.relocated().filter((metric) => metric.pnl).map((m) => m.key);
    expect(pnl).toEqual(['avg_realized_pct', 'best_trade_pct', 'worst_trade_pct']);
  });

  it('flattens the confidence breakdown into rows in level order', () => {
    // JSON turns the level keys into strings, where "10" would sort before
    // "2" if a sixth level ever appeared.
    tick();
    respondPerformance();

    expect(store.byConfidence().map((row) => row.level)).toEqual([1, 2]);
    expect(store.byConfidence()[1].win_rate).toBe(50);
  });

  /* -- events, per tab ------------------------------------------------- */

  it('refetches Performance on an analytics event', () => {
    tick();
    respondPerformance();

    events.raise('analytics');
    tick();
    respondPerformance({ win_rate: 70 });

    expect(store.winRate()).toBe(70);
  });

  it('ignores a jobs event while Performance is open', () => {
    tick();
    respondPerformance();

    events.raise('jobs');
    tick();

    backend.verify();
  });

  /* -- tuning ---------------------------------------------------------- */

  it('loads jobs, proposals and the tracked job for the Tuning tab', () => {
    tick();
    respondPerformance();
    openTuning();

    expect(store.job()?.id).toBe('abc123');
    expect(store.job()?.log_tail).toContain('grid 3/12');
    expect(store.jobActive()).toBe(true);
  });

  it('tracks the running job even when a newer finished one exists', () => {
    tick();
    respondPerformance();

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
    respondPerformance();
    openTuning([FINISHED_JOB]);

    expect(store.job()?.id).toBe('old999');
    expect(store.jobActive()).toBe(false);
  });

  it('clears the tracked job when there are none', () => {
    tick();
    respondPerformance();
    openTuning([]);

    expect(store.job()).toBeNull();
  });

  it('refetches job progress on a jobs event, with no timer', () => {
    tick();
    respondPerformance();
    openTuning();

    events.raise('jobs');
    tick();
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
    respondPerformance();
    openTuning();

    events.raise('analytics');
    tick();

    backend.verify();
  });

  it('launches a TRAIN grid and reloads the tuning view', () => {
    tick();
    respondPerformance();
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
    respondPerformance();
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
    respondPerformance();
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

  /* -- strategies, heatmap and failure --------------------------------- */

  it('offers the registry strategies to the launcher', () => {
    // Sourced from the registry rather than hardcoded: the server whitelists
    // the name and 400s on anything it does not know.
    tick();
    respondPerformance();
    openTuning([]);

    expect(store.strategyNames()).toEqual(['RSI', 'MACD']);
  });

  it('treats an axis-less heatmap as absent', () => {
    tick();
    respondPerformance();

    store.setTab('strategies');
    tick();
    respondStrategies({ heatmap: { strategies: [], horizons: [], cells: [] } });

    // A grid with no columns renders as an empty box rather than as nothing.
    expect(store.heatmap()).toBeNull();
  });

  it('keeps the data on screen when a refetch fails', () => {
    tick();
    respondPerformance();

    events.raise('analytics');
    tick();
    backend
      .expectOne('/api/v1/analytics/performance')
      .error(new ProgressEvent('error'), { status: 0 });

    expect(store.winRate()).toBe(61.8);
    expect(store.error()).toContain('not responding');
  });

  it('clears the error once a refetch succeeds', () => {
    tick();
    backend
      .expectOne('/api/v1/analytics/performance')
      .error(new ProgressEvent('error'), { status: 0 });
    // The snapshot goes out alongside it (SR50) and fails with it here. Left
    // outstanding it would still be pending on the refetch below, and the
    // second expectOne would match two requests rather than one.
    backend
      .expectOne('/api/v1/analytics/snapshot')
      .error(new ProgressEvent('error'), { status: 0 });
    // SR55's journal goes out with them and fails the same way, for the same
    // reason: left outstanding it would still be pending on the refetch.
    backend
      .expectOne('/api/v1/analytics/journal')
      .error(new ProgressEvent('error'), { status: 0 });
    expect(store.error()).not.toBeNull();
    expect(store.snapshotError()).not.toBeNull();
    expect(store.journalError()).not.toBeNull();

    events.raise('analytics');
    tick();
    respondPerformance();

    expect(store.error()).toBeNull();
    expect(store.snapshotError()).toBeNull();
    // Three independent failure modes, three independent recoveries.
    expect(store.journalError()).toBeNull();
  });

  /* -- SR54: the date range -------------------------------------------- */

  describe('the analytics date range', () => {
    /** Settle the first load so the assertions below are about the refetch. */
    const openPerformance = () => {
      tick();
      respondPerformance();
    };

    it('sends both bounds as query parameters, not as a client-side filter', () => {
      openPerformance();

      store.setRange('2026-01-01', '2026-06-30');
      tick();

      const request = backend.expectOne(
        (req) => req.url === '/api/v1/analytics/performance',
      );
      expect(request.request.params.get('from')).toBe('2026-01-01');
      expect(request.request.params.get('to')).toBe('2026-06-30');
      request.flush(PERFORMANCE);
      backend.expectOne('/api/v1/analytics/snapshot').flush(SNAPSHOT);
      backend.expectOne('/api/v1/analytics/journal').flush(JOURNAL);
    });

    it('omits an unset bound instead of sending it empty', () => {
      openPerformance();

      store.setRange('2026-01-01', null);
      tick();

      const request = backend.expectOne(
        (req) => req.url === '/api/v1/analytics/performance',
      );
      expect(request.request.params.get('from')).toBe('2026-01-01');
      expect(request.request.params.has('to')).toBe(false);
      request.flush(PERFORMANCE);
      backend.expectOne('/api/v1/analytics/snapshot').flush(SNAPSHOT);
      backend.expectOne('/api/v1/analytics/journal').flush(JOURNAL);
    });

    it('normalises an inverted range rather than rejecting it', () => {
      // A date picker mid-edit legitimately produces from > to; erroring
      // there surfaces a problem the user is one keystroke from fixing.
      openPerformance();

      store.setRange('2026-06-30', '2026-01-01');
      tick();

      expect(store.rangeFrom()).toBe('2026-01-01');
      expect(store.rangeTo()).toBe('2026-06-30');
      backend
        .expectOne((req) => req.url === '/api/v1/analytics/performance')
        .flush(PERFORMANCE);
      backend.expectOne('/api/v1/analytics/snapshot').flush(SNAPSHOT);
      backend.expectOne('/api/v1/analytics/journal').flush(JOURNAL);
    });

    it('makes exactly one performance request per range change', () => {
      // Both bounds move together, so a range pick cannot fire two requests
      // whose responses could land out of order.
      openPerformance();

      store.setRange('2026-01-01', '2026-06-30');
      tick();

      backend
        .expectOne((req) => req.url === '/api/v1/analytics/performance')
        .flush(PERFORMANCE);
      backend.expectOne('/api/v1/analytics/snapshot').flush(SNAPSHOT);
      backend.expectOne('/api/v1/analytics/journal').flush(JOURNAL);
      backend.verify();
    });

    it('clearRange goes back to unbounded', () => {
      openPerformance();
      store.setRange('2026-01-01', '2026-06-30');
      tick();
      backend
        .expectOne((req) => req.url === '/api/v1/analytics/performance')
        .flush(PERFORMANCE);
      backend.expectOne('/api/v1/analytics/snapshot').flush(SNAPSHOT);
      backend.expectOne('/api/v1/analytics/journal').flush(JOURNAL);

      store.clearRange();
      tick();

      const request = backend.expectOne(
        (req) => req.url === '/api/v1/analytics/performance',
      );
      expect(request.request.params.has('from')).toBe(false);
      expect(request.request.params.has('to')).toBe(false);
      expect(store.rangeFrom()).toBeNull();
      request.flush(PERFORMANCE);
      backend.expectOne('/api/v1/analytics/snapshot').flush(SNAPSHOT);
      backend.expectOne('/api/v1/analytics/journal').flush(JOURNAL);
    });

    it('passes null figures through as null rather than zero', () => {
      // The regression this guards: a `?? 0` in a computed turns "not enough
      // trades for a Sortino" into a confident 0.00 on a KPI card.
      openPerformance();

      expect(store.derived().sortino_ann).toBeNull();
      expect(store.derived().calmar).toBe(1.3);
    });

    it('reports an all-null derived block before the first response', () => {
      // No tick, no flush: nothing has arrived yet.
      expect(store.derived().calmar).toBeNull();
      expect(store.derivedMetrics().length).toBeGreaterThan(0);
      expect(store.derivedMetrics().every((m) => m.value === null)).toBe(true);
    });

    it('labels histogram buckets by their lower edge so losses read as losses', () => {
      openPerformance();

      const bins = store.returnsHistogram();
      expect(bins[0].label).toBe('-6.1%');
      // The empty interior bucket survives — dropping it would let the chart
      // silently redraw its own axis.
      expect(bins[1].count).toBe(0);
      expect(bins).toHaveLength(3);
    });

    it('sorts the benchmark and per-strategy series it is handed', () => {
      openPerformance();

      expect(store.benchmarkSeries().map((p) => p.date))
        .toEqual(['2026-07-01', '2026-08-01']);
      expect(store.cumulativeByStrategy().map((s) => s.strategy))
        .toEqual(['MACD', 'RSI']);
    });

    it('exposes a month histogram computed from calendarReturns', () => {
      tick();
      respondPerformance({ calendar: [
        { month: '2026-06', return_pct: 4.2, n: 3 },
        { month: '2026-07', return_pct: -1.8, n: 2 },
      ] });

      expect(store.monthHistogram()).toEqual([
        { label: '2026-06', count: 4.2 },
        { label: '2026-07', count: -1.8 },
      ]);
    });

    it('echoes the applied range back with its sample size', () => {
      openPerformance();

      expect(store.rangeSampleSize()).toBe(34);
      // PERFORMANCE carries no bounds, so the range is not "active" even
      // though the block is present.
      expect(store.rangeActive()).toBe(false);
    });
  });
});
