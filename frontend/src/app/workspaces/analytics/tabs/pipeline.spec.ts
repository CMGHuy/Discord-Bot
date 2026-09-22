import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { PipelineTab } from './pipeline';

describe('PipelineTab', () => {
  beforeEach(() => TestBed.resetTestingModule());
  it('renders funnel and both distributions as explicitly all-time panels', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), { provide: AnalyticsStore, useValue: { plans: signal({ funnel: { posted: 10, filled: 8, hit_tp1: 5, closed: 4 }, fill_rate: { resolved_n: 7, fill_rate_pct: 71.4, median_days_to_fill: 2.5 }, badges: { VALIDATED: 7 }, tiers: { A: 4 } }) } }] });
    const fixture = TestBed.createComponent(PipelineTab); fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('sb-histogram')).toHaveLength(3);
    expect(el.textContent).toContain('all-time');
    expect(el.textContent).toContain('Posted');
  });

  // A screenshot pass (v94 V2) once caught the Tiers panel rendering as a
  // blank box -- no bars, no message -- when no strategy carries a tier yet.
  it('shows an empty state instead of a blank box when no strategy is tiered', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), { provide: AnalyticsStore, useValue: { plans: signal({ funnel: { posted: 8, filled: 0, hit_tp1: 0, closed: 1 }, fill_rate: { resolved_n: 2, fill_rate_pct: 0, median_days_to_fill: null }, badges: { UNPROVEN: 1, VALIDATED: 7 }, tiers: {} }) } }] });
    const fixture = TestBed.createComponent(PipelineTab); fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('sb-histogram')).toHaveLength(2);
    expect(el.querySelector('sb-empty-state')).not.toBeNull();
    expect(el.textContent).toContain('No tiered strategies yet');
  });
});
