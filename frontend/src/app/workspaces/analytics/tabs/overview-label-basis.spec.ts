import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsStore } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { OverviewTab, winRateHint } from './overview';

/* v189 D6: scaled-out closes are labelled by net R from the deploy date and
 * not backfilled, so the win rate steps at deploy. The tile says so, and
 * shows the closes the rate leaves out. */

const BASIS = { label_basis_since: '2026-10-24', scratch_n: 3, unscored_n: 1 };

describe('winRateHint', () => {
  it('names the label basis date and the excluded counts', () => {
    expect(winRateHint(BASIS)).toBe(
      'Scaled-out trades are labelled by net R from 2026-10-24; earlier ones by TP1 touch. '
      + 'Not in the rate: 3 scratch, 1 unscored.');
  });

  it('shows zero counts as zero once the basis date exists', () => {
    expect(winRateHint({ ...BASIS, scratch_n: 0, unscored_n: 0 })).toBe(
      'Scaled-out trades are labelled by net R from 2026-10-24; earlier ones by TP1 touch. '
      + 'Not in the rate: 0 scratch, 0 unscored.');
  });

  it('keeps the counts without a basis date (before the release sets it)', () => {
    expect(winRateHint({ ...BASIS, label_basis_since: null })).toBe('Not in the rate: 3 scratch, 1 unscored.');
  });

  it('adds no hint for a payload without the fields (an older server)', () => {
    expect(winRateHint({})).toBeUndefined();
    expect(winRateHint(null)).toBeUndefined();
  });
});

describe('OverviewTab win-rate tile', () => {
  beforeEach(() => TestBed.resetTestingModule());

  function tileText(performanceOver: Record<string, unknown>): string {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: AnalyticsStore, useValue: {
          unit: signal('r'), scopeN: signal(34), tableOpen: signal({}),
          performance: signal({
            totals: {}, win_rate: 53.5, win_rate_n: 34, expectancy_r: -0.136, expectancy_n: 34,
            derived: {}, distributions: { returns: [], r_multiples: [] }, calendar: [],
            rolling_wr: [], rolling_exp_r: [], relocated: {}, by_confidence: {}, scope: {}, n: 34,
            ...performanceOver,
          }),
          performanceError: signal(null), equityCurve: signal(null), equityCurveError: signal(null),
          varianceBand: signal(null), varianceBandError: signal(null),
          setTableOpen: () => {}, reload: () => {},
        } },
        { provide: ConnectionStore, useValue: { currency: signal('$') } },
        { provide: PreferencesStore, useValue: { values: () => ({}), update: () => {} } },
      ],
    });
    const fixture = TestBed.createComponent(OverviewTab);
    fixture.detectChanges();
    const tile = [...(fixture.nativeElement as HTMLElement).querySelectorAll('sb-stat-tile')]
      .find((el) => el.textContent?.includes('Win rate'))!;
    return tile.textContent!.replace(/\s+/g, ' ');
  }

  it('carries the label-basis hint and the counts under the rate', () => {
    const text = tileText(BASIS);
    expect(text).toContain('53.50%');
    expect(text).toContain('labelled by net R from 2026-10-24');
    expect(text).toContain('3 scratch, 1 unscored');
  });

  it('renders as before when the payload has no label-basis fields', () => {
    expect(tileText({})).not.toContain('scratch');
  });
});
