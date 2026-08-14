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
   * The Performance tab makes TWO requests, not one.
   *
   * SR50 added `/analytics/snapshot` beside it: the snapshot is a whole
   * pre-built blob with its own endpoint, and folding it into the summary
   * response would make every visit carry the equity curve whether or not the
   * panels reading it are on screen. Both are settled here so the
   * `backend.verify()` assertions below still mean "nothing ELSE went out".
   *
   * The snapshot's own contents are exercised in `analytics.snapshot.spec.ts`.
   */
  const respondPerformance = (body: Partial<AnalyticsPerformance> = {}) => {
    backend
      .expectOne('/api/v1/analytics/performance')
      .flush({ ...PERFORMANCE, ...body });
    backend.expectOne('/api/v1/analytics/snapshot').flush(SNAPSHOT);
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
      backend
        .expectOne(`/api/v1/jobs/${(jobs[0] as { id: string }).id}`)
        .flush({ ...(jobs[0] as object), log_tail: 'grid 3/12\n' });
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
    expect(store.error()).not.toBeNull();
    expect(store.snapshotError()).not.toBeNull();

    events.raise('analytics');
    tick();
    respondPerformance();

    expect(store.error()).toBeNull();
    expect(store.snapshotError()).toBeNull();
  });
});
