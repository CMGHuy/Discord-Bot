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
  AnalyticsPerformance,
  AnalyticsPlans,
  AnalyticsStrategies,
} from '../../api/models';
import { AnalyticsStore } from '../../stores/analytics.store';
import { ConnectionStore } from '../../stores/connection.store';
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
