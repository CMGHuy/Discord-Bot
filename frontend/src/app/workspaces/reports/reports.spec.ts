import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { ReportTab, ReportsStore } from '../../stores/reports.store';
import { ATTRIBUTION, GATES, NOT_RUN, ok } from '../../testing/report-fixtures';
import { DISCLAIMER as RESEARCH_DISCLAIMER } from '../research/research';
import { DISCLAIMER, Reports } from './reports';

const URLS: Record<ReportTab, string> = {
  attribution: '/api/v1/reports/expectancy-attribution',
  gates: '/api/v1/reports/gate-counterfactual',
};

function create(): {
  fixture: ComponentFixture<Reports>;
  store: InstanceType<typeof ReportsStore>;
  http: HttpTestingController;
  router: Router;
} {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      ReportsStore,
    ],
  });
  return {
    fixture: TestBed.createComponent(Reports),
    store: TestBed.inject(ReportsStore),
    http: TestBed.inject(HttpTestingController),
    router: TestBed.inject(Router),
  };
}

const host = (fixture: ComponentFixture<Reports>): HTMLElement => fixture.nativeElement;
const text = (fixture: ComponentFixture<Reports>): string =>
  host(fixture).textContent?.replace(/\s+/g, ' ') ?? '';

describe('Reports', () => {
  it('opens on Expectancy attribution and fetches only that report', () => {
    const { fixture, store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(ok(ATTRIBUTION));
    http.expectNone(URLS.gates);
    fixture.detectChanges();
    expect(host(fixture).querySelector('sb-expectancy-attribution-tab')).not.toBeNull();
    expect(host(fixture).querySelector('sb-gates-tab')).toBeNull();
    expect(text(fixture)).toContain('Expectancy attribution');
  });

  it('shows the other tab once the store is on it', () => {
    const { fixture, store, http } = create();
    store.resolveTab('gates').subscribe();
    http.expectOne(URLS.gates).flush(ok(GATES));
    http.expectNone(URLS.attribution);
    fixture.detectChanges();
    expect(host(fixture).querySelector('sb-gates-tab')).not.toBeNull();
    expect(host(fixture).querySelector('sb-expectancy-attribution-tab')).toBeNull();
  });

  it('writes a tab switch to the URL, and leaves no ?tab= for the default', async () => {
    const { fixture, store, http, router } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(ok(ATTRIBUTION));
    fixture.detectChanges();
    const tabs = Array.from(host(fixture).querySelectorAll<HTMLElement>('sb-tab-bar [role="tab"]'));
    tabs.find((tab) => tab.textContent?.includes('Gate counterfactual'))!.click();
    await fixture.whenStable();
    expect(router.url).toContain('tab=gates');
    tabs.find((tab) => tab.textContent?.includes('Expectancy attribution'))!.click();
    await fixture.whenStable();
    expect(router.url).not.toContain('tab=');
  });

  it('says "Not yet run" with the production command, and draws no figures', () => {
    const { fixture, store, http } = create();
    store.resolveTab('gates').subscribe();
    http.expectOne(URLS.gates).flush(NOT_RUN);
    fixture.detectChanges();
    expect(text(fixture)).toContain('Not yet run');
    expect(text(fixture)).toContain('scripts/ops/ssh-hetzner.sh');
    expect(text(fixture)).toContain('scripts/reports/gate_counterfactual_report.py');
    expect(host(fixture).querySelector('sb-gates-tab')).toBeNull();
    expect(host(fixture).querySelector('sb-data-table')).toBeNull();
  });

  it('names the attribution script on the attribution tab', () => {
    const { fixture, store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(NOT_RUN);
    fixture.detectChanges();
    expect(text(fixture)).toContain('scripts/reports/expectancy_attribution.py');
  });

  it('shows the error state, not "Not yet run", when the report is unreadable', () => {
    const { fixture, store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(
      { error: { code: 'report_unreadable', message: 'ValueError: Expecting value' } },
      { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();
    expect(text(fixture)).not.toContain('Not yet run');
    expect(host(fixture).querySelector('sb-expectancy-attribution-tab')).toBeNull();
  });

  it('marks when the result was generated', () => {
    const { fixture, store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(ok(ATTRIBUTION));
    fixture.detectChanges();
    const freshness = host(fixture).querySelector('sb-freshness')!;
    expect(freshness.textContent).toContain('as of');
    expect(freshness.textContent).not.toContain('stale');
  });

  it('carries the fixed footer, the same one Research carries', () => {
    const { fixture, store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(URLS.attribution).flush(ok(ATTRIBUTION));
    fixture.detectChanges();
    expect(text(fixture)).toContain(DISCLAIMER);
    expect(DISCLAIMER).toBe(RESEARCH_DISCLAIMER);
  });
});
