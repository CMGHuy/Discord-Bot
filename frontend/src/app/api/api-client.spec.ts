import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ApiClient } from './api-client';
import { authInterceptor, errorInterceptor, loadingInterceptor, routeRefreshInterceptor } from './interceptors';
import { RouteRefreshService } from '../routing/route-refresh.service';

describe('ApiClient — scope and analytics', () => {
  let api: ApiClient;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor, routeRefreshInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: RouteRefreshService, useValue: { requestMutationRefresh: () => undefined } },
      ],
    });
    api = TestBed.inject(ApiClient);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('sends only the set scope fields, and never an empty value', () => {
    api.analyticsPerformance({ from: '2026-08-01', to: null, ledger: 'both', strategy: 'MACD',
                               horizon: null, direction: null }).subscribe();
    const req = http
      .expectOne((r) => r.url.endsWith('/analytics/performance'));
    expect(req.request.params.get('from')).toBe('2026-08-01');
    expect(req.request.params.get('ledger')).toBe('both');
    expect(req.request.params.get('strategy')).toBe('MACD');
    expect(req.request.params.has('to')).toBe(false);
    expect(req.request.params.has('direction')).toBe(false);
    expect(req.request.params.has('horizon')).toBe(false);
  });

  it('by-dimension and heat-grid carry the same scope', () => {
    api.analyticsByDimension('horizon', { direction: 'bearish' }).subscribe();
    const a = http.expectOne((r) => r.url.endsWith('/analytics/by-dimension'));
    expect(a.request.params.get('dim')).toBe('horizon');
    expect(a.request.params.get('direction')).toBe('bearish');
    api.analyticsHeatGrid({ direction: 'bearish' }).subscribe();
    expect(http.expectOne((r) => r.url.endsWith('/analytics/heat-grid'))
      .request.params.get('direction')).toBe('bearish');
  });

  it('analyticsJournal sends lessons only when provided, and scope fields alongside', () => {
    // First call: with lessons
    api.analyticsJournal({ from: '2026-08-01', strategy: 'RSI' }, 10).subscribe();
    const withLessons = http.expectOne((r) => r.url.endsWith('/analytics/journal'));
    expect(withLessons.request.params.get('from')).toBe('2026-08-01');
    expect(withLessons.request.params.get('strategy')).toBe('RSI');
    expect(withLessons.request.params.get('lessons')).toBe('10');

    // Second call: without lessons
    api.analyticsJournal({ ledger: 'main' }).subscribe();
    const withoutLessons = http.expectOne((r) => r.url.endsWith('/analytics/journal'));
    expect(withoutLessons.request.params.get('ledger')).toBe('main');
    expect(withoutLessons.request.params.has('lessons')).toBe(false);

    // Third call: with scope and no lessons param
    api.analyticsJournal({ direction: 'bullish' }).subscribe();
    const noLessonsSpecified = http.expectOne((r) => r.url.endsWith('/analytics/journal'));
    expect(noLessonsSpecified.request.params.get('direction')).toBe('bullish');
    expect(noLessonsSpecified.request.params.has('lessons')).toBe(false);
  });

  it('researchLedger GETs /research/ledger and returns the body untouched', () => {
    let got: unknown;
    api.researchLedger().subscribe((r) => (got = r));
    const req = http.expectOne((r) => r.url.endsWith('/research/ledger'));
    expect(req.request.method).toBe('GET');
    const body = { rows: [], q_family_m: 0, verdicts: [], instruments: [] };
    req.flush(body);
    expect(got).toEqual(body);
  });

  it('reportExpectancyAttribution GETs /reports/expectancy-attribution and returns the envelope untouched', () => {
    let got: unknown;
    api.reportExpectancyAttribution().subscribe((r) => (got = r));
    const req = http.expectOne((r) => r.url.endsWith('/reports/expectancy-attribution'));
    expect(req.request.method).toBe('GET');
    const body = { status: 'not_run', generated_at: null, result: null };
    req.flush(body);
    expect(got).toEqual(body);
  });

  it('reportGateCounterfactual GETs /reports/gate-counterfactual and returns the envelope untouched', () => {
    let got: unknown;
    api.reportGateCounterfactual().subscribe((r) => (got = r));
    const req = http.expectOne((r) => r.url.endsWith('/reports/gate-counterfactual'));
    expect(req.request.method).toBe('GET');
    const body = { status: 'ok', generated_at: '2026-10-20T21:45:00+00:00', result: { cells: [], rows: [] } };
    req.flush(body);
    expect(got).toEqual(body);
  });
});
