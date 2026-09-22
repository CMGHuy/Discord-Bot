import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsStore } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { AttributionTab } from './attribution';

/* The store is stubbed down to the signals this tab reads: a tab component
 * owns no HTTP (spec v94 D12), so its spec asserts rendering, not fetching. */
function storeStub(over: Record<string, unknown> = {}) {
  const base = {
    scopeN: signal(360),
    measure: signal('exp_r'),
    heatCell: signal('exp_r'),
    breakdown: signal('strategy'),
    breakdownLabel: signal('Strategy'),
    unit: signal('r'),
    monthBars: signal([]),
    strategies: signal({
      contribution: [], cumulative: {}, strategies: [], registry_scope: 'all-time', scope: {}, n: 0,
    }),
    strategiesError: signal(null),
    byDimension: signal({ rows: [], as_of: null, min_cell_n: 20, scope: {}, n: 0 }),
    byDimensionError: signal(null),
    heatGrid: signal({
      rows: [], cols: [], cells: [], folded: { n_strategies: 0, cells: [] }, min_cell_n: 20, scope: {}, n: 0,
    }),
    heatGridError: signal(null),
    byHorizon: signal({ rows: [], as_of: null, min_cell_n: 20, scope: {}, n: 0 }),
    byHorizonError: signal(null),
    byDirection: signal({ rows: [], as_of: null, min_cell_n: 20, scope: {}, n: 0 }),
    byDirectionError: signal(null),
    byDow: signal({ rows: [], as_of: null, min_cell_n: 20, scope: {}, n: 0 }),
    byDowError: signal(null),
    performance: signal(null),
    performanceError: signal(null),
    setMeasure: () => {}, setBreakdown: () => {}, setHeatCell: () => {}, reload: () => {},
  };
  return { ...base, ...over };
}

function render(over: Record<string, unknown> = {}) {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: AnalyticsStore, useValue: storeStub(over) },
      { provide: ConnectionStore, useValue: { currency: signal('$') } },
    ],
  });
  const fixture = TestBed.createComponent(AttributionTab);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('AttributionTab', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('folds past the top eight into Other and never invents a ninth hue', () => {
    const { fixture } = render({ strategies: signal({ contribution: Array.from({ length: 12 },
      (_, i) => ({ strategy: `S${i}`, total_r: 12 - i, n: 30 })), cumulative: {}, strategies: [], scope: {}, n: 360 }) });
    const steps = fixture.componentInstance['waterfallSteps']();
    expect(steps.length).toBe(9);
    expect(steps.at(-1)!.label).toBe('Other (4)');
    expect(steps.at(-1)!.value).toBe(12 - 8 + (12 - 9) + (12 - 10) + (12 - 11));
  });

  it('draws withheld cells blank and passes the floor to the dot plot', () => {
    const { el, fixture } = render({
      byDimension: signal({ rows: [{ key: 'MACD', n: 9, exp_r: null, win_rate: null, total_r: 1.2,
                                     total_pnl: 100, wins: 5, losses: 4, avg_win_r: null, avg_loss_r: null }],
                            min_cell_n: 20, as_of: null, scope: {}, n: 9 }),
    });
    expect(fixture.componentInstance['dotPoints']()[0].value).toBeNull();
    expect(el.querySelector('sb-dot-plot')).not.toBeNull();
    const table = el.textContent as string;
    expect(table).not.toMatch(/\b\d+\.\d%/);            // no rate printed for a withheld row
  });

  it('one measure toggle drives every panel', () => {
    const { el } = render({ measure: signal('total_r') });
    expect(el.querySelectorAll('sb-segmented').length).toBe(1);
  });

  /* -- H4: each panel's own error, never a neighbour's ------------------ */

  it('replaces only the failed panel with a retry surface', () => {
    const { el } = render({ heatGridError: signal('The admin is not responding.') });
    expect(el.querySelectorAll('sb-panel-error').length).toBe(1);
    expect(el.querySelector('sb-waterfall')).not.toBeNull();
    expect(el.querySelector('sb-dot-plot')).not.toBeNull();
    expect(el.querySelector('sb-heat-grid')).toBeNull();
  });

  /* -- badge/soak columns appear only when a row actually carries one ---- */

  it('shows the badge column only when the breakdown rows carry one', () => {
    const rowWithBadge = { key: 'RSI', n: 40, exp_r: 0.3, win_rate: 55, total_r: 12, total_pnl: 500,
                            wins: 22, losses: 18, avg_win_r: 0.9, avg_loss_r: -0.5, badge: 'VALIDATED' };
    const { fixture } = render({ byDimension: signal({ rows: [rowWithBadge], min_cell_n: 20, as_of: null, scope: {}, n: 40 }) });
    expect(fixture.componentInstance['dimensionVisible']()).toContain('badge');
  });

  it('omits the badge column when no row carries one', () => {
    const { fixture } = render();
    expect(fixture.componentInstance['dimensionVisible']()).not.toContain('badge');
  });
});
