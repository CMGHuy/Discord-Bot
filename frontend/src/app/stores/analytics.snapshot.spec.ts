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

  /** The Performance tab loads on init; settle both of its requests. */
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

  it('flattens the equity curve and the drawdown series to one point shape', () => {
    open();
    expect(store.equitySeries()).toEqual([
      { date: '2026-07-01', value: 10000 },
      { date: '2026-07-15', value: 10250 },
      { date: '2026-08-01', value: 10430.5 },
    ]);
    expect(store.drawdownSeries()).toEqual([
      { date: '2026-07-01', value: 0 },
      { date: '2026-07-15', value: 2.5 },
    ]);
  });

  it('drops a series point that is missing a date or a value', () => {
    // A gap is not a zero. Drawing it as one invents a crash.
    open({
      ...SNAPSHOT,
      equity_curve: {
        points: [
          { date: '2026-07-01', balance: 10000 },
          { date: '2026-07-02' },
          { balance: 10100 },
        ],
      },
    });
    expect(store.equitySeries()).toEqual([{ date: '2026-07-01', value: 10000 }]);
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
    expect(store.equitySeries()).toEqual([]);
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
