import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsStore, RELOCATED_METRICS } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { OverviewTab } from './overview';

/* The store is stubbed down to the signals this tab reads: a tab component
 * owns no HTTP (spec v94 D12), so its spec asserts rendering, not fetching. */
function storeStub(over: Record<string, unknown> = {}) {
  const base = {
    unit: signal('r'), scopeN: signal(312), tableOpen: signal({}),
    performance: signal({
      totals: { total: 40, open: 6, closed: 34 }, win_rate: 53.5, win_rate_n: 34,
      expectancy_r: -0.136, expectancy_n: 34, derived: { total_return_pct: 4.2 },
      distributions: { returns: [], r_multiples: [{ lo: -1, hi: 0, count: 12 }] },
      calendar: [{ month: '2026-08', return_pct: 1.2, pnl: 240, n: 20 }],
      rolling_wr: [], rolling_exp_r: [], relocated: {}, by_confidence: {},
      scope: {}, n: 312,
    }),
    performanceError: signal(null),
    equityCurve: signal({
      points: [{ date: '2026-08-01', cum_r: 1, drawdown_r: 0, cum_pnl: 70, cum_pct: 0.7 },
               { date: '2026-08-02', cum_r: 0.5, drawdown_r: 0.5, cum_pnl: 40, cum_pct: 0.4 }],
      points_n: 2, as_of: '2026-08-02', benchmark: { spy_indexed: [] }, scope: {}, n: 2,
    }),
    equityCurveError: signal(null),
    setTableOpen: () => {}, reload: () => {},
  };
  return { ...base, ...over };
}

function render(over: Record<string, unknown> = {}) {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      { provide: AnalyticsStore, useValue: storeStub(over) },
      { provide: ConnectionStore, useValue: { currency: signal('$') } },
      { provide: PreferencesStore, useValue: { values: () => ({}), update: () => {} } },
    ],
  });
  const fixture = TestBed.createComponent(OverviewTab);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('OverviewTab', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('shows six KPI tiles, each with the money line whatever the unit', () => {
    const { el } = render();
    expect(el.querySelectorAll('sb-stat-tile').length).toBeGreaterThanOrEqual(6);
    const text = el.textContent as string;
    for (const label of ['Total R', 'ExpR', 'Win rate', 'Profit factor', 'Max drawdown', 'Sharpe']) {
      expect(text).toContain(label);
    }
    expect(el.querySelectorAll('.secondary').length).toBeGreaterThan(0);
  });

  it('draws equity and drawdown as two panes, not a toggle', () => {
    const { el } = render();
    expect(el.querySelectorAll('sb-line-chart').length).toBeGreaterThanOrEqual(2);
    expect(el.textContent).toContain('Drawdown');
    expect(el.querySelector('sb-segmented[aria-label="Equity view"]')).toBeNull();
  });

  it('renders outcome as one share bar, never a donut', () => {
    const { el } = render();
    expect(el.querySelector('sb-share-bar')).not.toBeNull();
    expect(el.querySelector('sb-donut')).toBeNull();
  });

  it('replaces a failed panel with a retry surface, not an empty chart', () => {
    const { el } = render({ equityCurve: signal(null), equityCurveError: signal('The admin is not responding.') });
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
    expect(el.textContent).toContain('Could not load');
  });

  /* -- the six relocated metrics (Task T1 gap 6) ------------------------ */
  /* Moved here from `analytics.store.spec.ts`'s comment pointer (S4 Step 8):
   * the tiles/rows that render the six relocated metrics now live on this
   * tab, so the "all six appear" assertion belongs here, not at the store
   * level -- and so does the store's own retired distinction between an
   * absent key (a lost metric) and a present `null` (a real "not yet"
   * answer), which a plain "all six appear" check would not catch. */

  it('surfaces all six metrics relocated from the Dashboard in the Outcome panel', () => {
    const { el } = render({
      performance: signal({
        totals: { total: 40, open: 6, closed: 34 }, win_rate: 53.5, win_rate_n: 34,
        expectancy_r: -0.136, expectancy_n: 34,
        derived: { total_return_pct: 4.2, avg_win_r: 1.5, avg_loss_r: -0.8, payoff_r: 1.875 },
        distributions: { returns: [], r_multiples: [{ lo: -1, hi: 0, count: 12 }] },
        calendar: [{ month: '2026-08', return_pct: 1.2, pnl: 240, n: 20 }],
        rolling_wr: [], rolling_exp_r: [], by_confidence: {}, scope: {}, n: 312,
        relocated: {
          wins: 21, losses: 13, avg_realized_pct: 1.84, best_trade_pct: 12.5,
          worst_trade_pct: -6.1, avg_holding_days: 9.2,
        },
      }),
    });
    const text = el.textContent as string;
    for (const metric of RELOCATED_METRICS) {
      expect(text).toContain(metric.label);
    }
    // None of them should read as missing when the payload actually carries them.
    expect(el.querySelector('.pairs .missing')).toBeNull();
  });

  it('flags a relocated metric the payload stopped sending as missing, distinct from a real null', () => {
    const { el } = render({
      performance: signal({
        totals: { total: 40, open: 6, closed: 34 }, win_rate: 53.5, win_rate_n: 34,
        expectancy_r: -0.136, expectancy_n: 34, derived: { total_return_pct: 4.2 },
        distributions: { returns: [], r_multiples: [] },
        calendar: [], rolling_wr: [], rolling_exp_r: [], by_confidence: {}, scope: {}, n: 312,
        relocated: {
          wins: 0, losses: 0,
          avg_realized_pct: null, best_trade_pct: null, worst_trade_pct: null,
          // avg_holding_days deliberately absent -- the API stopped sending it.
        },
      }),
    });

    const missingRow = el.querySelector('.pairs .missing');
    expect(missingRow).not.toBeNull();
    expect(missingRow?.textContent).toContain('Avg holding');
    expect(missingRow?.textContent?.toLowerCase()).toContain('missing');

    // A present-but-null metric is a real answer, not a flagged omission.
    const rows = Array.from(el.querySelectorAll('.pairs > div'));
    const avgRealised = rows.find((row) => row.textContent?.includes('Avg realised'));
    expect(avgRealised).toBeDefined();
    expect(avgRealised?.classList.contains('missing')).toBe(false);
    expect(avgRealised?.textContent?.toLowerCase()).not.toContain('missing');
  });
});
