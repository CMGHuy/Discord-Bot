import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import {
  AnalyticsByDimensionRow,
  AnalyticsPerformance,
  AnalyticsPlans,
  AnalyticsSnapshot,
  AnalyticsStrategies,
} from '../../api/models';
import { AnalyticsStore } from '../../stores/analytics.store';
import { ConnectionStore } from '../../stores/connection.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { Analytics } from './analytics';

const connectionStub = { currency: signal('$') };

function performancePayload(
  overrides: Partial<AnalyticsPerformance> = {},
): AnalyticsPerformance {
  return {
    totals: { total: 12, open: 2, closed: 10 },
    relocated: {},
    win_rate: 55,
    expectancy_r: 0.2,
    by_confidence: {},
    range: { from: null, to: null, span_years: null, n: 10 },
    derived: {} as never,
    distributions: { returns: [], r_multiples: [] },
    rolling_returns: [],
    holding_period_split: [],
    risk_reward_split: [],
    calendar: [],
    cumulative_by_strategy: {},
    benchmark: { spy_cum: {} },
    ...overrides,
  } as AnalyticsPerformance;
}

function strategiesPayload(
  overrides: Partial<AnalyticsStrategies> = {},
): AnalyticsStrategies {
  return { strategies: [{ name: 'RSI' }], heatmap: {}, ...overrides };
}

function plansPayload(overrides: Partial<AnalyticsPlans> = {}): AnalyticsPlans {
  return {
    funnel: { posted: 4, filled: 3, hit_tp1: 1, closed: 2 },
    in_flight: 1,
    fill_rate: { resolved_n: 2, fill_rate_pct: 50, median_days_to_fill: 3 },
    badges: {},
    tiers: {},
    ...overrides,
  };
}

function snapshotPayload(overrides: Partial<AnalyticsSnapshot> = {}): AnalyticsSnapshot {
  return {
    built_at: null,
    overall: {},
    equity_curve: null,
    drawdown: [],
    rolling_wr: [],
    by: {},
    calibration: {},
    r_multiples: [],
    ...overrides,
  };
}

function riskPayload(metricsOverrides: Record<string, unknown> = {}) {
  return {
    heat: {},
    positions: [],
    sector_heat: [],
    clusters: [],
    throttle: {},
    killswitch: {},
    scan_health: {},
    metrics: {
      var_95: { value: null, n: 0 },
      expected_shortfall_95: { value: null, n: 0 },
      annualised_vol: { value: null, n: 0 },
      beta_spy: { value: null, n: 0 },
      sharpe_r: { value: 1.2, n: 100 },
      max_drawdown_r: { value: 3.4, n: 100 },
      as_of: null,
      benchmark_symbol: 'SPY',
      ...metricsOverrides,
    },
    correlation: { labels: [], values: [] },
  };
}

function seed(): { fixture: ComponentFixture<Analytics>; backend: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      { provide: ConnectionStore, useValue: connectionStub },
      AnalyticsStore,
    ],
  });
  TestBed.inject(AnalyticsStore).load();
  const fixture = TestBed.createComponent(Analytics);
  const backend = TestBed.inject(HttpTestingController);
  return { fixture, backend };
}

/** Performance mounts three independent fetches at once (performance,
 *  journal, snapshot — analytics.store.ts loadPerformance). A test scoped to
 *  one of the three flushes the other two empty so it doesn't hang on
 *  pending requests it does not care about. */
function flushJournalAndSnapshot(backend: HttpTestingController): void {
  backend.expectOne('/api/v1/analytics/journal').flush({ digest: [], lessons: [], entries_n: 0 });
  backend.expectOne('/api/v1/analytics/snapshot').flush(snapshotPayload());
}

/** Renders the Performance tab with all four of its fetches
 * (performance/journal/snapshot/risk) landed, every population that backs a
 * KPI tile set to the SAME `n` unless `profitFactor` is overridden -- so a
 * test can assert every tile independently without caring which of the four
 * responses it actually reads from (see analytics.store.ts's own comments on
 * where each of the six figures comes from). */
async function renderKpis(
  overrides: { n?: number; profitFactor?: number | null } = {},
): Promise<HTMLElement> {
  const { fixture, backend } = seed();
  fixture.detectChanges();

  const n = overrides.n ?? 782;
  const profitFactor = overrides.profitFactor === undefined ? 1.8 : overrides.profitFactor;

  backend.expectOne('/api/v1/analytics/journal').flush({ digest: [], lessons: [], entries_n: 0 });
  backend.expectOne('/api/v1/analytics/snapshot').flush(snapshotPayload({
    overall: { n, profit_factor: profitFactor },
    equity_curve: {
      points: [
        { date: '2026-01-01', balance: 10_000, pnl: 0 },
        { date: '2026-07-01', balance: 11_000, pnl: 1_000 },
      ],
      skipped_n: 0,
    },
    r_multiples: Array.from({ length: n }, (_, i) => (i % 2 === 0 ? 1 : -0.5)),
  }));
  backend.expectOne('/api/v1/analytics/performance').flush(performancePayload({
    totals: { total: n, open: 0, closed: n },
    win_rate: 55,
  }));
  backend.expectOne('/api/v1/risk').flush(riskPayload({
    sharpe_r: { value: 1.2, n },
    max_drawdown_r: { value: 3.4, n },
  }));

  await fixture.whenStable();
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

function kpiTiles(el: HTMLElement): HTMLElement[] {
  return Array.from(el.querySelectorAll<HTMLElement>('.kpi-row .tile'));
}

function kpiLabels(el: HTMLElement): string[] {
  return kpiTiles(el).map((tile) => tile.querySelector('.label')!.textContent!.trim());
}

function kpiTile(el: HTMLElement, label: string): HTMLElement {
  const tile = kpiTiles(el).find(
    (t) => t.querySelector('.label')!.textContent!.trim() === label,
  );
  if (!tile) throw new Error(`no KPI tile labelled ${label}`);
  return tile;
}

describe('Analytics — performance tab', () => {
  it('shows a skeleton while loading, before the first response', () => {
    const { fixture } = seed();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.skeleton')).toBeTruthy();
  });

  it('shows the error state on a first-load failure of the main performance fetch', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flushJournalAndSnapshot(backend);
    backend
      .expectOne('/api/v1/analytics/performance')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.failed')).toBeTruthy();
  });

  it('a snapshot-only failure does not blank the record/overall panels', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/analytics/journal').flush({ digest: [], lessons: [], entries_n: 0 });
    backend
      .expectOne('/api/v1/analytics/snapshot')
      .flush({ error: { code: 'internal', message: 'snapshot down' } }, { status: 500, statusText: 'x' });
    backend.expectOne('/api/v1/analytics/performance').flush(performancePayload());
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Record');
    expect(el.textContent).toContain('snapshot down');
  });

  it('shows the measured-zero empty state, not a spinner, when there are no closed trades', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flushJournalAndSnapshot(backend);
    backend
      .expectOne('/api/v1/analytics/performance')
      .flush(performancePayload({ totals: { total: 0, open: 0, closed: 0 } }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('No closed trades in this range');
    expect(el.querySelector('.skeleton')).toBeNull();
  });

  it('shows the journal empty state distinctly from the performance one', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/analytics/snapshot').flush({
      built_at: null,
      overall: {},
      equity_curve: null,
      drawdown: [],
      rolling_wr: [],
      by: {},
      calibration: {},
      r_multiples: [],
    });
    backend.expectOne('/api/v1/analytics/journal').flush({ digest: [], lessons: [], entries_n: 0 });
    backend.expectOne('/api/v1/analytics/performance').flush(performancePayload());
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('No journal entries yet');
  });
});

describe('Analytics — performance tab — KPI row (v85 D39)', () => {
  it('renders the six KPI tiles in the specified order', async () => {
    const el = await renderKpis();
    expect(kpiLabels(el)).toEqual([
      'Total R', 'R per month', 'Sharpe (R)', 'Max drawdown (R)',
      'Win rate', 'Profit factor',
    ]);
  });

  it('gives every KPI the sample it was computed from', async () => {
    const el = await renderKpis({ n: 782 });
    const tiles = kpiTiles(el);
    expect(tiles.length).toBe(6);
    expect(tiles.every((t) => t.querySelector('.sample')!.textContent!.includes('782'))).toBe(true);
  });

  it('de-emphasises every KPI when the book is thin', async () => {
    const el = await renderKpis({ n: 12 });
    const tiles = kpiTiles(el);
    expect(tiles.length).toBe(6);
    expect(tiles.every((t) => t.classList.contains('thin'))).toBe(true);
  });

  it('renders a null profit factor as no-value rather than zero', async () => {
    const el = await renderKpis({ profitFactor: null });
    expect(kpiTile(el, 'Profit factor').querySelector('.value')!.textContent!.trim()).toBe('—');
  });

  it('labels Sharpe as an R measure', async () => {
    const el = await renderKpis();
    expect(kpiLabels(el)).toContain('Sharpe (R)');
  });

  // Fix round 1: five of the six tiles read snapshot()/riskMetrics(), not
  // performance() -- only Win rate does. The row used to sit inside the
  // sb-async gated on performanceAsync alone, so a /performance-only
  // failure blanked all six, including the five that had nothing to do
  // with it. These two tests pin the row's own combined gate (kpiAsync).
  it('a /performance-only failure leaves the snapshot/risk-backed tiles rendering real data', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();

    backend.expectOne('/api/v1/analytics/journal').flush({ digest: [], lessons: [], entries_n: 0 });
    backend.expectOne('/api/v1/analytics/snapshot').flush(snapshotPayload({
      overall: { n: 100, profit_factor: 1.8 },
      equity_curve: {
        points: [
          { date: '2026-01-01', balance: 10_000, pnl: 0 },
          { date: '2026-07-01', balance: 11_000, pnl: 1_000 },
        ],
        skipped_n: 0,
      },
      r_multiples: Array.from({ length: 100 }, (_, i) => (i % 2 === 0 ? 1 : -0.5)),
    }));
    backend.expectOne('/api/v1/risk').flush(riskPayload({
      sharpe_r: { value: 1.2, n: 100 },
      max_drawdown_r: { value: 3.4, n: 100 },
    }));
    backend
      .expectOne('/api/v1/analytics/performance')
      .flush({ error: { code: 'internal', message: 'performance down' } }, { status: 500, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    // The row itself must not be replaced by an error banner over a fetch
    // it does not (mostly) depend on.
    expect(el.querySelector('.kpi-row')).toBeTruthy();
    expect(kpiTile(el, 'Total R').querySelector('.value')!.textContent!.trim()).not.toBe('—');
    expect(kpiTile(el, 'Sharpe (R)').querySelector('.value')!.textContent!.trim()).not.toBe('—');
    expect(kpiTile(el, 'Max drawdown (R)').querySelector('.value')!.textContent!.trim()).not.toBe('—');
    expect(kpiTile(el, 'Profit factor').querySelector('.value')!.textContent!.trim()).not.toBe('—');
    // Win rate genuinely depends on the fetch that failed, so it degrades.
    expect(kpiTile(el, 'Win rate').querySelector('.value')!.textContent!.trim()).toBe('—');
  });

  it('a /snapshot-only failure leaves Win rate (a /performance figure) rendering real data', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();

    backend.expectOne('/api/v1/analytics/journal').flush({ digest: [], lessons: [], entries_n: 0 });
    backend
      .expectOne('/api/v1/analytics/snapshot')
      .flush({ error: { code: 'internal', message: 'snapshot down' } }, { status: 500, statusText: 'x' });
    backend.expectOne('/api/v1/analytics/performance').flush(performancePayload({
      totals: { total: 100, open: 0, closed: 100 },
      win_rate: 55,
    }));
    backend.expectOne('/api/v1/risk').flush(riskPayload({
      sharpe_r: { value: 1.2, n: 100 },
      max_drawdown_r: { value: 3.4, n: 100 },
    }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.kpi-row')).toBeTruthy();
    expect(kpiTile(el, 'Win rate').querySelector('.value')!.textContent!.trim()).not.toBe('—');
    // Total R and Profit factor genuinely depend on the fetch that failed.
    expect(kpiTile(el, 'Total R').querySelector('.value')!.textContent!.trim()).toBe('—');
    expect(kpiTile(el, 'Profit factor').querySelector('.value')!.textContent!.trim()).toBe('—');
  });
});

/* -- v85 R9-04 -- equity curve, win/loss donut, control bar, freshness -- */

interface EquityPoint { date: string; cum_r: number; drawdown_r: number; }

/** Renders the Performance tab with journal/snapshot/performance/risk
 *  settled minimally (none of R9-04's own tests read them) and the equity
 *  curve flushed with `points`. */
async function renderEquity(
  points: EquityPoint[] = [],
): Promise<{ el: HTMLElement; fixture: ComponentFixture<Analytics>; backend: HttpTestingController }> {
  const { fixture, backend } = seed();
  fixture.detectChanges();
  backend.expectOne('/api/v1/analytics/journal').flush({ digest: [], lessons: [], entries_n: 0 });
  backend.expectOne('/api/v1/analytics/snapshot').flush(snapshotPayload());
  backend.expectOne('/api/v1/analytics/performance').flush(performancePayload());
  backend.expectOne('/api/v1/risk').flush(riskPayload());
  backend
    .expectOne((req) => req.url === '/api/v1/analytics/equity-curve')
    .flush({ points, n: points.length, as_of: points.at(-1)?.date ?? null });
  await fixture.whenStable();
  fixture.detectChanges();
  return { el: fixture.nativeElement as HTMLElement, fixture, backend };
}

describe('Analytics — performance tab — equity curve (v85 D39, R9-04)', () => {
  it('draws the equity curve from the endpoint series', async () => {
    const { el } = await renderEquity([{ date: '2026-04-01', cum_r: 1, drawdown_r: 0 }]);
    expect(el.querySelector('.equity sb-line-chart')).not.toBeNull();
  });

  it('switches the same series to drawdown without refetching', async () => {
    const { el, fixture, backend } = await renderEquity([
      { date: '2026-04-01', cum_r: 1, drawdown_r: 0.4 },
    ]);

    const drawdownButton = [...el.querySelectorAll<HTMLButtonElement>('.equity-toggle .segment')]
      .find((b) => b.textContent?.trim().startsWith('Drawdown'))!;
    drawdownButton.click();
    fixture.detectChanges();

    // No second request -- the toggle only swaps which field of the ALREADY
    // fetched points is plotted (spec D39: "one request, two views").
    backend.expectNone((req) => req.url === '/api/v1/analytics/equity-curve');
    expect(drawdownButton.getAttribute('aria-pressed')).toBe('true');
  });

  it('renders the win/loss donut with both average R figures', async () => {
    // AAPL's own win (cum_r 0 -> 1.24) then a loss (1.24 -> 0.55) -- the
    // avg-R captions are derived from these per-trade deltas, not a
    // separate payload field (there is none: R9-01's endpoint gives only
    // the running total).
    const { el } = await renderEquity([
      { date: '2026-01-01', cum_r: 1.24, drawdown_r: 0 },
      { date: '2026-01-02', cum_r: 0.55, drawdown_r: 0.69 },
    ]);
    expect(el.querySelector('.winloss')!.textContent).toContain('1.24');
    expect(el.querySelector('.winloss')!.textContent).toContain('-0.69');
  });

  it('shows an empty curve as measured-empty rather than a flat line', async () => {
    // sb-async replaces its whole projected content with the empty state,
    // so .equity itself is gone too -- same pattern the existing
    // "measured-zero" test above asserts against the whole page.
    const { el } = await renderEquity([]);
    expect(el.querySelector('.equity sb-line-chart')).toBeNull();
    expect(el.textContent).toContain('No closed trades in this range');
  });

  it('puts the range and strategy pickers in the control bar', async () => {
    const { el } = await renderEquity();
    expect(el.querySelector('sb-control-bar sb-date-range')).not.toBeNull();
    // sb-select's own template owns the inner <select>; class="strategy" is
    // a host attribute of the custom element, not forwarded onto it.
    expect(el.querySelector('sb-control-bar sb-select.strategy')).not.toBeNull();
  });

  it('marks the curve panel with its own data age', async () => {
    const { el } = await renderEquity([{ date: '2026-09-10', cum_r: 1, drawdown_r: 0 }]);
    expect(el.querySelector('.equity sb-freshness')).not.toBeNull();
  });
});

/* -- v85 R9-05 -- strategy table and horizon bars, with the measure toggle -- */

/** Renders the Performance tab with journal/snapshot/performance/risk/
 *  equity-curve settled minimally (none of R9-05's own tests read them)
 *  and both `/by-dimension` fetches flushed with `rows`/`horizons`. */
async function renderAgg(overrides: {
  rows?: AnalyticsByDimensionRow[]; horizons?: AnalyticsByDimensionRow[];
} = {}): Promise<{ el: HTMLElement; fixture: ComponentFixture<Analytics> }> {
  const { fixture, backend } = seed();
  fixture.detectChanges();
  backend.expectOne('/api/v1/analytics/journal').flush({ digest: [], lessons: [], entries_n: 0 });
  backend.expectOne('/api/v1/analytics/snapshot').flush(snapshotPayload());
  backend.expectOne('/api/v1/analytics/performance').flush(performancePayload());
  backend.expectOne('/api/v1/risk').flush(riskPayload());
  backend
    .expectOne((req) => req.url === '/api/v1/analytics/equity-curve')
    .flush({ points: [], n: 0, as_of: null });
  backend
    .expectOne((req) => req.url === '/api/v1/analytics/by-dimension' && req.params.get('dim') === 'strategy')
    .flush({ rows: overrides.rows ?? [], as_of: null });
  backend
    .expectOne((req) => req.url === '/api/v1/analytics/by-dimension' && req.params.get('dim') === 'horizon')
    .flush({ rows: overrides.horizons ?? [], as_of: null });
  await fixture.whenStable();
  fixture.detectChanges();
  return { el: fixture.nativeElement as HTMLElement, fixture };
}

function rowKeys(el: HTMLElement): string[] {
  // DataTable pads a short page with blank filler rows up to perPage (see
  // Risk's own exposure table) -- filter those out rather than assert
  // against an implementation detail unrelated to this test.
  return [...el.querySelectorAll('tbody tr')]
    .map((tr) => tr.querySelector('td')!.textContent!.split(' — ')[0].trim())
    .filter((key) => key !== '');
}

function firstRow(el: HTMLElement): HTMLElement {
  return el.querySelector('tbody tr') as HTMLElement;
}

function measureToggle(el: HTMLElement, label: string): HTMLButtonElement {
  const found = [...el.querySelectorAll<HTMLButtonElement>('.measure-toggle .segment')]
    .find((b) => b.textContent?.trim().startsWith(label));
  if (!found) throw new Error(`no measure toggle labelled ${label}`);
  return found;
}

function bar(el: HTMLElement, key: string): HTMLElement {
  const found = [...el.querySelectorAll<HTMLElement>('.horizon-row')]
    .find((r) => r.querySelector('.horizon-key')?.textContent?.trim() === key);
  if (!found) throw new Error(`no horizon bar for ${key}`);
  return found;
}

function prefs(): Record<string, unknown> {
  return TestBed.inject(PreferencesStore).values();
}

describe('Analytics — performance tab — strategy/horizon aggregates (v85 D40, R9-05)', () => {
  it('sorts the strategy table by the active measure', async () => {
    const { el, fixture } = await renderAgg({
      rows: [
        { key: 'A', exp_r: 0.1, total_r: 90, win_rate: null, profit_factor: null, max_drawdown_r: null, n: 900 },
        { key: 'B', exp_r: 0.5, total_r: 20, win_rate: null, profit_factor: null, max_drawdown_r: null, n: 40 },
      ],
    });
    expect(rowKeys(el)).toEqual(['B', 'A']);

    measureToggle(el, 'Total R').click();
    fixture.detectChanges();
    expect(rowKeys(el)).toEqual(['A', 'B']);
  });

  it('renders the registry badge as a rail beside each strategy', async () => {
    const { el } = await renderAgg({
      rows: [{ key: 'RSI', exp_r: 0.2, total_r: 10, win_rate: null, profit_factor: null, max_drawdown_r: null, n: 238, badge: 'WEAK' }],
    });
    const row = firstRow(el);
    expect(row.classList).toContain('badge-weak');
    expect(row.textContent).toContain('WEAK');
  });

  it('de-emphasises a strategy row computed from a thin sample', async () => {
    const { el } = await renderAgg({
      rows: [{ key: 'New', exp_r: 0.9, total_r: 6, win_rate: null, profit_factor: null, max_drawdown_r: null, n: 7 }],
    });
    expect(firstRow(el).classList).toContain('thin');
  });

  it('renders the horizon bars diverging around zero', async () => {
    const { el } = await renderAgg({
      horizons: [{ key: '2w', exp_r: -0.2, total_r: -8, win_rate: null, profit_factor: null, max_drawdown_r: null, n: 40 }],
    });
    expect(bar(el, '2w').classList).toContain('neg');
  });

  it('labels each horizon bar with its sample size', async () => {
    const { el } = await renderAgg({
      horizons: [{ key: '2w', exp_r: 0.2, total_r: 8, win_rate: null, profit_factor: null, max_drawdown_r: null, n: 40 }],
    });
    expect(bar(el, '2w').textContent).toContain('40');
  });

  it('drives both panels from one toggle', async () => {
    const { el, fixture } = await renderAgg({
      rows: [{ key: 'A', exp_r: 0.1, total_r: 90, win_rate: null, profit_factor: null, max_drawdown_r: null, n: 900 }],
      horizons: [{ key: '2w', exp_r: 0.1, total_r: 90, win_rate: null, profit_factor: null, max_drawdown_r: null, n: 900 }],
    });
    measureToggle(el, 'Total R').click();
    fixture.detectChanges();
    expect(bar(el, '2w').textContent).toContain('90');
  });

  it('remembers the chosen measure as a preference', async () => {
    const { el, fixture } = await renderAgg({
      rows: [{ key: 'A', exp_r: 0.1, total_r: 90, win_rate: null, profit_factor: null, max_drawdown_r: null, n: 900 }],
    });
    measureToggle(el, 'Total R').click();
    fixture.detectChanges();
    expect(prefs()['analyticsMeasure']).toBe('total_r');
  });
});

describe('Analytics — strategies tab', () => {
  it('shows the measured-zero empty state when no strategy has a closed trade', async () => {
    const { fixture, backend } = seed();
    fixture.componentRef.setInput('tab', 'strategies');
    TestBed.inject(AnalyticsStore).setTab('strategies');
    fixture.detectChanges();
    backend.expectOne('/api/v1/analytics/strategies').flush(strategiesPayload({ strategies: [] }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('No strategy has a closed trade in this range');
  });
});

describe('Analytics — plans tab', () => {
  it('shows the measured-zero empty state when no plan has ever posted', async () => {
    const { fixture, backend } = seed();
    fixture.componentRef.setInput('tab', 'plans');
    TestBed.inject(AnalyticsStore).setTab('plans');
    fixture.detectChanges();
    backend
      .expectOne('/api/v1/analytics/plans')
      .flush(plansPayload({ funnel: { posted: 0, filled: 0, hit_tp1: 0, closed: 0 } }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('No plans posted yet');
  });
});
