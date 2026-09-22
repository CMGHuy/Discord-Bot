import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsStore } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { OverviewTab } from './overview';

function storeStub(overrides: Record<string, unknown> = {}) {
  return {
    unit: signal('r'), scopeN: signal(34),
    performance: signal({
      relocated: { wins: 21, losses: 13 }, expectancy_r: 0.42, expectancy_n: 34,
      win_rate: 61.8, win_rate_n: 34, derived: { total_return_pct: 18.4 },
      distributions: { r_multiples: [{ lo: -1, hi: 0, count: 13 }] },
      calendar: [{ month: '2026-08', return_pct: 3.2, n: 4 }],
    }),
    equityCurve: signal({ points: [
      { date: '2026-08-01', cum_r: 1, drawdown_r: 0, cum_pnl: 70, cum_pct: 0.7 },
      { date: '2026-08-02', cum_r: 0.5, drawdown_r: 0.5, cum_pnl: 40, cum_pct: 0.4 },
    ] }),
    ...overrides,
  };
}

function render(overrides: Record<string, unknown> = {}) {
  TestBed.configureTestingModule({ providers: [
    provideZonelessChangeDetection(),
    { provide: AnalyticsStore, useValue: storeStub(overrides) },
    { provide: ConnectionStore, useValue: { currency: signal('$') } },
    { provide: PreferencesStore, useValue: { values: () => ({}) } },
  ] });
  const fixture = TestBed.createComponent(OverviewTab);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('OverviewTab', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('renders scoped KPI, equity and drawdown panes without a view toggle', () => {
    const el = render();
    expect(el.querySelectorAll('sb-stat-tile')).toHaveLength(3);
    expect(el.querySelectorAll('sb-line-chart')).toHaveLength(2);
    expect(el.textContent).toContain('Drawdown');
    expect(el.querySelector('sb-segmented')).toBeNull();
  });

  it('uses a share bar for outcomes and preserves an empty scoped book', () => {
    const el = render({ equityCurve: signal({ points: [] }) });
    expect(el.querySelector('sb-share-bar')).not.toBeNull();
    expect(el.querySelector('sb-empty-state')).not.toBeNull();
    expect(el.querySelector('sb-donut')).toBeNull();
  });
});
