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
import { AnalyticsStore, binRMultiples } from './analytics.store';

/* SR50 — the snapshot nothing read.
 *
 * `GET /analytics/snapshot` forwards the whole pre-built blob and has carried
 * profit factor, Sharpe, Sortino, max drawdown, streaks, the equity and
 * drawdown series, R-multiples and a ten-dimension `by` block the entire time.
 * `ApiClient.analyticsSnapshot()` existed; no store called it. Seventeen rows
 * of the parity audit's "missing" analytics gap were data already on the wire.
 *
 * The absent cases carry as much weight here as the present ones. A fresh
 * install has no closed trades, and `metrics.py` is careful to return None
 * rather than 0 for a Sharpe it cannot compute — a store that coerced that to
 * zero would print "0.00" for "not enough data", which is the one reading that
 * would get someone to trust a strategy with no track record.
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
};

const SNAPSHOT = {
  built_at: '2026-08-14T06:00:00Z',
  overall: {
    n: 8,
    wins: 5,
    losses: 3,
    win_rate: 62.5,
    expectancy_r: 0.31,
    profit_factor: 1.85,
    sharpe: 1.2,
    sortino: 1.7,
    max_drawdown_pct: 12.4,
    total_pnl: 430.5,
    streaks: {
      current: 2,
      current_kind: 'win',
      best_win_streak: 4,
      worst_loss_streak: 3,
    },
  },
  equity_curve: {
    points: [
      { date: '2026-07-01', balance: 10000 },
      { date: '2026-07-15', balance: 10250 },
      { date: '2026-08-01', balance: 10430.5 },
    ],
    skipped_n: 0,
  },
  drawdown: [
    { date: '2026-07-01', dd_pct: 0 },
    { date: '2026-07-15', dd_pct: 2.5 },
  ],
  rolling_wr: [],
  by: {
    ticker: [
      { key: 'AAPL', n: 5, wins: 3, losses: 2, win_rate: 60, expectancy_r: 0.2,
        avg_r: 0.2, profit_factor: 1.4, total_pnl: 210 },
      { key: 'MSFT', n: 3, wins: 2, losses: 1, win_rate: 66.7, expectancy_r: 0.5,
        avg_r: 0.5, profit_factor: 2.1, total_pnl: 220.5 },
    ],
    dow: [
      { key: 'Mon', n: 4, wins: 2, losses: 2, win_rate: 50, expectancy_r: 0,
        avg_r: 0, profit_factor: 1, total_pnl: 0 },
    ],
    horizon: [],
  },
  calibration: {},
  r_multiples: [-1, -1, -0.4, 0.6, 1.2, 2.4, 12],
};

/** A fresh install: the snapshot builds fine and every ratio is None. */
const EMPTY_SNAPSHOT = {
  built_at: '2026-08-14T06:00:00Z',
  overall: {
    n: 0,
    wins: 0,
    losses: 0,
    win_rate: null,
    expectancy_r: null,
    profit_factor: null,
    sharpe: null,
    sortino: null,
    max_drawdown_pct: null,
    total_pnl: 0,
    streaks: { current: 0, current_kind: null, best_win_streak: 0, worst_loss_streak: 0 },
  },
  equity_curve: { points: [], skipped_n: 0 },
  drawdown: [],
  rolling_wr: [],
  by: {},
  calibration: {},
  r_multiples: [],
};

describe('AnalyticsStore — the snapshot', () => {
  let store: InstanceType<typeof AnalyticsStore>;
  let backend: HttpTestingController;

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

  /** The Performance tab loads on init; settle all THREE of its requests.
   *  SR55 added `/analytics/journal` beside the other two. */
  function open(snapshot: object | null = SNAPSHOT) {
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne('/api/v1/analytics/performance').flush(PERFORMANCE);
    const request = backend.expectOne('/api/v1/analytics/snapshot');
    if (snapshot === null) {
      request.flush({ error: { code: 'unavailable', message: 'down' } },
                    { status: 503, statusText: 'Service Unavailable' });
    } else {
      request.flush(snapshot);
    }
    backend
      .expectOne('/api/v1/analytics/journal')
      .flush({ digest: [], lessons: [], entries_n: 0 });
  }

  it('asks for the snapshot at all — the whole point of this task', () => {
    open();
    expect(store.snapshot()).not.toBeNull();
  });

  it('reads the risk-adjusted figures', () => {
    open();
    expect(store.profitFactor()).toBe(1.85);
    expect(store.sharpe()).toBe(1.2);
    expect(store.sortino()).toBe(1.7);
    expect(store.maxDrawdownPct()).toBe(12.4);
    expect(store.totalPnl()).toBe(430.5);
  });

  it('reads the streaks, which even the Jinja page never rendered', () => {
    open();
    expect(store.streaks()).toEqual({
      current: 2,
      currentKind: 'win',
      bestWin: 4,
      worstLoss: 3,
    });
  });


  it('groups by ticker out of the box, busiest first', () => {
    open();
    expect(store.breakdown()).toBe('ticker');
    expect(store.breakdownRows().map((r) => r.key)).toEqual(['AAPL', 'MSFT']);
    expect(store.breakdownLabel()).toBe('Ticker');
  });

  it('switches dimension without another request', () => {
    open();
    store.setBreakdown('dow');
    expect(store.breakdownRows().map((r) => r.key)).toEqual(['Mon']);
    // Every dimension is in the one blob, so there is nothing to fetch.
    backend.verify();
  });

  it('gives an empty table for a dimension the snapshot has no rows for', () => {
    open();
    store.setBreakdown('month');
    expect(store.breakdownRows()).toEqual([]);
  });

  it('reports every ratio as absent, not as zero, on a fresh install', () => {
    open(EMPTY_SNAPSHOT);
    expect(store.profitFactor()).toBeNull();
    expect(store.sharpe()).toBeNull();
    expect(store.sortino()).toBeNull();
    expect(store.maxDrawdownPct()).toBeNull();
    expect(store.rMultipleBins()).toEqual([]);
  });

  it('keeps a snapshot failure out of the tab-wide error', () => {
    // The snapshot self-heals server-side and can rebuild on the request. A
    // failure here says nothing about /analytics/performance, which came from
    // a different endpoint and may be perfectly fine.
    open(null);
    expect(store.snapshotError()).toBeTruthy();
    expect(store.error()).toBeNull();
    expect(store.winRate()).toBe(62.5);
  });

  it('reports when the blob was built', () => {
    open();
    expect(store.snapshotBuiltAt()).toBe('2026-08-14T06:00:00Z');
  });



  it('exposes ordered zero-filled direction and day-of-week win-rate histograms', () => {
    open({ ...SNAPSHOT, by: { ...SNAPSHOT.by,
      direction: [{ key: 'bullish', n: 6, wins: 4, losses: 2, win_rate: 66.7, expectancy_r: 0.3, avg_r: 0.3, profit_factor: 1.8, total_pnl: 300 }],
      dow: [
        { key: 'Wednesday', n: 5, wins: 3, losses: 2, win_rate: 60, expectancy_r: 0.2, avg_r: 0.2, profit_factor: 1.5, total_pnl: 150 },
        { key: 'Monday', n: 2, wins: 1, losses: 1, win_rate: 50, expectancy_r: 0.1, avg_r: 0.1, profit_factor: 1.1, total_pnl: 20 },
      ],
    } });
    expect(store.directionHistogram()).toEqual([{ label: 'Long (n=6)', count: 66.7 }, { label: 'Short (n=0)', count: 0 }]);
    expect(store.dowHistogram().map((bin) => bin.label)).toEqual(['Monday (n=2)', 'Tuesday (n=0)', 'Wednesday (n=5)', 'Thursday (n=0)', 'Friday (n=0)', 'Saturday (n=0)', 'Sunday (n=0)']);
  });
});

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
    const tick = () => TestBed.inject(ApplicationRef).tick();
    tick();
    backend.expectOne('/api/v1/analytics/performance').flush(PERFORMANCE);
    backend.expectOne('/api/v1/analytics/snapshot').flush(SNAPSHOT);
    backend
      .expectOne('/api/v1/analytics/journal')
      .flush({ digest: [], lessons: [], entries_n: 0 });

    store.setTab('tuning');
    tick();
    backend.expectOne('/api/v1/jobs').flush(JOBS);
    backend.expectOne('/api/v1/jobs/job1').flush({
      id: 'job1', state: 'done', log_tail: 'grid 12/12',
    });
    backend.expectOne('/api/v1/jobs/job1/result').flush(grid);
    backend.expectOne('/api/v1/analytics/tuning/proposals').flush({ proposals: [] });
    backend.expectOne('/api/v1/analytics/strategies').flush({ strategies: [], heatmap: null });
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

describe('binRMultiples', () => {
  it('bins at half an R, labelling each bin by its lower edge', () => {
    // The label is the edge, not a value, so the bin starting at zero is
    // "0.0R" -- "+0.0R" would claim a gain of nothing.
    expect(binRMultiples([0.1, 0.4, 0.6])).toEqual([
      { label: '0.0R', count: 2 },
      { label: '+0.5R', count: 1 },
    ]);
  });

  it('signs the losing bins', () => {
    expect(binRMultiples([-1, -0.7]).map((b) => b.label)).toEqual(['-1.0R']);
  });

  it('clamps outliers so one lottery ticket cannot flatten the chart', () => {
    // A +12R trade is real and worth knowing about, but given its own bin it
    // makes every other bar one pixel tall.
    const bins = binRMultiples([0.1, 12, -30]);
    expect(bins[0].label).toBe('-5.0R');
    expect(bins[bins.length - 1].label).toBe('+5.0R');
  });

  it('has no bins at all when there are no trades', () => {
    expect(binRMultiples([])).toEqual([]);
  });
});
