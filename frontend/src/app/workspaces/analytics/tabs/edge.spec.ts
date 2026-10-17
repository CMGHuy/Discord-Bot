import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { LIVE_LOSS_LOOKS_CAVEAT, LIVE_LOSS_MEANING } from '../analytics.columns';
import { EdgeTab } from './edge';

const LOSS_ROW = {
  source: 'confluence', strategy: 'ALL', horizon: '4w', live_n: 24, live_wr: 41.7, live_expr: -0.25,
  bound_upper: -0.04, alert: true, registry_status: 'WEAK', registry_window_kind: 'VALIDATION',
  registry_run_date: '2026-05-01', registry_expr: -0.05,
};
const DRIFT_ROW = { strategy: 'MACD', oos_n: 20, oos_wr: 65, live_n: 8, live_wr: 40, delta_wr: -25, drift_alert: true };

function stub(overrides: Record<string, unknown> = {}) {
  return {
    scopeN: signal(30),
    performance: signal({ win_rate: 55, rolling_wr: [], rolling_exp_r: [] }),
    strategies: signal({ cumulative: {} }),
    calibration: signal({ deciles: [] }),
    liveLossWatch: signal([]),
    liveLossCounts: signal({}),
    drift: signal([]),
    ...overrides,
  };
}

function render(store: Record<string, unknown>) {
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), { provide: AnalyticsStore, useValue: store }],
  });
  const fixture = TestBed.createComponent(EdgeTab);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('EdgeTab', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('shows scoped rolling measures and all-time calibration', () => {
    const { el } = render(stub({
      performance: signal({ win_rate: 55, rolling_wr: [{ date: '2026-08-01', win_rate: 55 }], rolling_exp_r: [{ date: '2026-08-01', exp_r: .2 }] }),
      strategies: signal({ cumulative: { RSI: [{ date: '2026-08-01', cum_r: 1 }] } }),
      calibration: signal({ deciles: [{ decile: '80-89', win_rate: 83 }] }),
    }));
    expect(el.querySelectorAll('sb-line-chart').length).toBeGreaterThanOrEqual(2);
    expect(el.querySelector('sb-small-multiples')).not.toBeNull();
    expect(el.textContent).toContain('all-time');
  });

  // A screenshot pass (v94 V2) once caught 2/3 * 100 = 66.66666... rendered
  // raw in the Calibration deciles panel, overflowing its container -- the
  // fix rounds a decile's win rate to one decimal before it reaches the bar.
  it('rounds a decile win rate instead of overflowing the panel with a raw float', () => {
    const { fixture, el } = render(stub({ calibration: signal({ deciles: [{ decile: '60-69', win_rate: 200 / 3 }] }) }));
    expect(fixture.componentInstance.decileBins()).toEqual([{ label: '60-69', count: 66.7 }]);
    expect(el.textContent).not.toContain('66.66666');
  });

  // v164 D4: the live loss watch, with its meaning, the registry-context
  // label, the counts and the correlated-looks caveat, on the Edge tab.
  it('renders the live loss watch with its meaning, registry label, counts and caveat', () => {
    const { el } = render(stub({
      liveLossWatch: signal([LOSS_ROW]),
      liveLossCounts: signal({ no_source: 2, unknown_strategy: 0, no_r: 1, manual_close: 3, no_entry_date: 0 }),
    }));
    const text = el.textContent ?? '';
    expect(text).toContain('Live loss watch');
    expect(text).toContain(LIVE_LOSS_MEANING);
    expect(text).toContain('Registry columns: backtest context — not comparable.');
    expect(text).toContain(LIVE_LOSS_LOOKS_CAVEAT);
    expect(text).toContain('confluence / ALL / 4w');
    expect(text).toContain('BELOW ZERO');
    expect(text).toContain('no source 2');
    expect(text).toContain('Manual closes included: 3.');
  });

  // DRIFT_COLUMNS and store.drift() existed for a long time with no
  // component rendering them; v164 puts the table under the live loss watch.
  it('renders the win-rate drift table under the live loss watch', () => {
    const { el } = render(stub({ liveLossWatch: signal([LOSS_ROW]), drift: signal([DRIFT_ROW]) }));
    const text = el.textContent ?? '';
    expect(el.querySelectorAll('sb-data-table').length).toBe(2);
    expect(text).toContain('Win-rate drift');
    expect(text).toContain('MACD');
    expect(text).toContain('DECAY');
    expect(text.indexOf('Live loss watch')).toBeLessThan(text.indexOf('Win-rate drift'));
  });

  it('shows an empty state, and no counts line, when the snapshot predates the watch', () => {
    const { el } = render(stub());
    const text = el.textContent ?? '';
    expect(text).toContain('No live loss watch rows yet');
    expect(text).not.toContain('Manual closes included');
    expect(text).toContain(LIVE_LOSS_MEANING);
  });
});

describe('edge.ts breakpoints', () => {
  it('uses only declared breakpoint values in width queries', () => {
    // A media query at 800px puts this file and ViewportService on
    // different scales -- see breakpoints.ts. v95 A7.
    const src = readFileSync(
      join(process.cwd(), 'src/app/workspaces/analytics/tabs/edge.ts'),
      'utf8',
    );
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
