import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsStore } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { AttributionTab, TAKEN_CAPTION } from './attribution';
import { Hint } from '../../../ui/hint';
import { PERFORMANCE_CAVEAT } from '../../../ui/stat-tile';

/** The text of the sb-hint whose aria label is `label` (A4 audit). */
function hintText(fixture: ComponentFixture<unknown>, label: string): string {
  const hint = fixture.debugElement
    .queryAll(By.directive(Hint))
    .map((debug) => debug.componentInstance as Hint)
    .find((h) => h.label() === label);
  if (!hint) throw new Error(`no sb-hint labelled "${label}"`);
  return hint.text();
}

/** Focus the first hit matching `hitSelector` and return the chart tooltip's text (A4 audit). */
async function tooltipText(fixture: ComponentFixture<unknown>, hitSelector: string): Promise<string> {
  const hit = (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>(hitSelector);
  if (!hit) throw new Error(`no chart hit "${hitSelector}"`);
  hit.dispatchEvent(new FocusEvent('focus'));
  fixture.detectChanges();
  await fixture.whenStable();
  const tip = (fixture.nativeElement as HTMLElement).querySelector('sb-chart-tooltip .tooltip');
  return tip?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

describe('attribution.ts never widens the page (v179 §2.1)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/tabs/attribution.ts'), 'utf8');

  it('sizes its one column to the tab, not to its widest child', () => {
    expect(src).toContain(':host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); }');
  });

  it('keeps the phone panel track shrinkable', () => {
    expect(src).toContain('@media (max-width: 639px) { .panels { grid-template-columns: minmax(0, 1fr); } }');
    expect(src).not.toMatch(/\.panels \{ grid-template-columns: 1fr; \}/);
  });
});

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

  /* -- v152 D2: the followed-vs-paper breakdown ------------------------- */

  it('captions the followed-vs-paper breakdown as paper results, not fills', () => {
    const { el } = render({ breakdown: signal('taken'), breakdownLabel: signal('Followed vs paper') });
    expect(TAKEN_CAPTION).toBe(
      'Paper results, R units, pre-tax. Followed records the plan as followed, not your fill.');
    expect(el.textContent).toContain(TAKEN_CAPTION);
  });

  it('shows no caption for any other breakdown', () => {
    const { el } = render();
    expect(el.textContent).not.toContain(TAKEN_CAPTION);
  });

  it('leads with expectancy for the followed-vs-paper breakdown and keeps N', () => {
    const { fixture } = render({ breakdown: signal('taken') });
    const visible: string[] = fixture.componentInstance['dimensionVisible']();
    expect(visible.slice(0, 4)).toEqual(['key', 'n', 'exp_r', 'win_rate']);
  });

  it('keeps the default column order for every other breakdown', () => {
    const { fixture } = render();
    const visible: string[] = fixture.componentInstance['dimensionVisible']();
    expect(visible.slice(0, 4)).toEqual(['key', 'n', 'win_rate', 'exp_r']);
  });
});

describe('attribution.ts breakpoints', () => {
  it('uses only declared breakpoint values in width queries', () => {
    // A media query at 800px puts this file and ViewportService on
    // different scales -- see breakpoints.ts. v95 A7.
    const src = readFileSync(
      join(process.cwd(), 'src/app/workspaces/analytics/tabs/attribution.ts'),
      'utf8',
    );
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});

describe('AttributionTab hint and tooltip copy (A4 audit)', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('Contribution and Strategy x horizon hints state the paper, gross, pre-tax basis', () => {
    const { fixture } = render();
    expect(hintText(fixture, 'Contribution definition')).toContain(PERFORMANCE_CAVEAT);
    expect(hintText(fixture, 'Strategy x horizon definition')).toContain(PERFORMANCE_CAVEAT);
  });

  it('dot plot hint says a point is one group of the chosen breakdown, not always a strategy', () => {
    const { fixture } = render();
    const text = hintText(fixture, 'ExpR vs sample size definition');
    expect(text).toContain('one group of the breakdown below');
    expect(text).not.toContain('Each point is one strategy');
    expect(text).toContain(PERFORMANCE_CAVEAT);
  });

  it('Contribution tooltip names its unit, R', async () => {
    const { fixture } = render({ strategies: signal({ contribution: [{ strategy: 'RSI', total_r: 2.5, n: 30 }],
      cumulative: {}, strategies: [], scope: {}, n: 30 }) });
    const text = await tooltipText(fixture, 'sb-waterfall rect.hit');
    expect(text).toContain('2.50R');
  });

  it('Strategy x horizon tooltip names its unit, R for ExpR', async () => {
    const { fixture } = render({ heatGrid: signal({ rows: ['RSI'], cols: ['1w'],
      cells: [{ r: 0, c: 0, n: 30, exp_r: 0.25, win_rate: 55 }], folded: { n_strategies: 0, cells: [] },
      min_cell_n: 20, scope: {}, n: 30 }) });
    const text = await tooltipText(fixture, 'sb-heat-grid td.sb-hit');
    expect(text).toContain('0.25R');
  });
});
