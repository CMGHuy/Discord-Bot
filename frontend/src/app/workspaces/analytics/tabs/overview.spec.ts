import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsStore, RELOCATED_METRICS } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { ANALYTICS_DRAWDOWN_LABEL, ANALYTICS_EXPR_ABOUT, ANALYTICS_SHARPE_LABEL, OverviewTab } from './overview';
import { BAND_OK } from './variance-band.fixture';
import { Hint } from '../../../ui/hint';
import { PERFORMANCE_CAVEAT, StatTile } from '../../../ui/stat-tile';

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
    varianceBand: signal(null), varianceBandError: signal(null),
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

  it('shows six KPI tiles, all six labelled', () => {
    const { el } = render();
    expect(el.querySelectorAll('sb-stat-tile').length).toBeGreaterThanOrEqual(6);
    const text = el.textContent as string;
    for (const label of ['Total R', 'ExpR', 'Win rate', 'Profit factor', 'Max drawdown', 'Sharpe']) {
      expect(text).toContain(label);
    }
  });

  it('gives the R-multiple tiles a money line, but never one for a unitless metric', () => {
    // Win rate, Profit factor and Sharpe carry no money or R reading at all
    // (`AnalyticsDerivedMetrics.profit_factor`'s own doc comment: "unitless
    // like sharpe_ann/sortino_ann") -- a screenshot pass once caught them
    // rendered as "+3.50R" / "+3.50 €" because they were run through the
    // same R/%/$ tile formatter as Total R and ExpR.
    const { el } = render();
    const tileFor = (label: string) =>
      Array.from(el.querySelectorAll('sb-stat-tile')).find((tile) => tile.textContent?.includes(label));

    for (const label of ['Total R', 'ExpR', 'Max drawdown']) {
      expect(tileFor(label)?.querySelector('.secondary')).not.toBeNull();
    }
    for (const label of ['Win rate', 'Profit factor', 'Sharpe']) {
      const tile = tileFor(label);
      expect(tile?.querySelector('.secondary')).toBeNull();
      expect(tile?.textContent).not.toMatch(/[$€]/);
    }
    // Win rate is a rate, not an R-multiple -- it always reads as a percentage.
    expect(tileFor('Win rate')?.textContent).toContain('53.50%');
    // The figure itself, not the A4 hint beside it (which names ExpR).
    expect(tileFor('Win rate')?.querySelector('.value')?.textContent).not.toContain('R');
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

  it('carries the whole-book Normal bad luck panel across both columns', () => {
    const { el } = render({ varianceBand: signal(BAND_OK) });
    const panel = el.querySelector('sb-variance-band-panel');
    expect(panel).not.toBeNull();
    expect(panel?.classList.contains('wide')).toBe(true);
    expect(panel?.textContent).toContain('Normal bad luck');
    expect(panel?.textContent).toContain("Whole book, closed trades only. Filters don't apply.");
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

describe('OverviewTab hint and tooltip copy (A4 audit)', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('Equity and R distribution hints state the paper, gross, pre-tax basis', () => {
    const { fixture } = render();
    expect(hintText(fixture, 'Equity definition')).toContain('per closed trade, ordered by close date');
    expect(hintText(fixture, 'Equity definition')).toContain(PERFORMANCE_CAVEAT);
    expect(hintText(fixture, 'R distribution definition')).toContain(PERFORMANCE_CAVEAT);
  });

  it('Outcome hint says its bar covers the whole book, counts legs and ignores the scope', () => {
    const { fixture } = render();
    const text = hintText(fixture, 'Outcome definition');
    expect(text).toContain('whole book');
    expect(text).toContain('each realised leg');
    expect(text).toContain('ignores the scope');
  });

  it('Win rate tile says Analytics counts plans, beside ExpR and N', () => {
    const { fixture } = render();
    const text = hintText(fixture, 'About Win rate');
    expect(text).toContain('counts plans');
    expect(text).toContain('ExpR');
    expect(text).toContain('N is');
    expect(text).toContain(PERFORMANCE_CAVEAT);
  });

  it('By month hint names a percent return, not a unit-toggled result', () => {
    const { fixture } = render();
    const text = hintText(fixture, 'By month definition');
    expect(text).toContain("percent of the balance at the month's start");
    expect(text).not.toContain('Realised result');
    expect(text).toContain(PERFORMANCE_CAVEAT);
  });

  it('By month tooltip reads the return in percent whatever the unit toggle says', async () => {
    const { fixture } = render();   // unit 'r'
    const text = await tooltipText(fixture, 'sb-bar-list li.sb-hit');
    expect(text).toContain('+1.20%');
    expect(text).not.toContain('1.20R');
  });
});

describe('overview.ts breakpoints', () => {
  it('uses only declared breakpoint values in width queries', () => {
    // A media query at 800px puts this file and ViewportService on
    // different scales -- see breakpoints.ts. v95 A7.
    const src = readFileSync(
      join(process.cwd(), 'src/app/workspaces/analytics/tabs/overview.ts'),
      'utf8',
    );
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });

  it('names the basis of Sharpe and max drawdown in their labels (v194 B8)', () => {
    const { el } = render();
    const labels = [...el.querySelectorAll('sb-stat-tile .label')].map((n) => n.textContent!.trim());
    expect(labels).toContain('Sharpe · annualised, selected range');
    expect(labels).toContain('Max drawdown · cumulative R, selected range');
    expect(labels).not.toContain('Sharpe');
    expect(labels).not.toContain('Max drawdown');
  });

  it('gives both tiles a hint with definition, population, N and the paper caveat', () => {
    const { el } = render();
    for (const label of [ANALYTICS_SHARPE_LABEL, ANALYTICS_DRAWDOWN_LABEL]) {
      const tile = [...el.querySelectorAll('sb-stat-tile')]
        .find((t) => t.querySelector('.label')?.textContent?.trim() === label)!;
      const hint = tile.querySelector('sb-hint')!;
      expect(hint.querySelector('button')!.getAttribute('aria-label')).toBe(`About ${label}`);
      const text = hint.querySelector('[role="tooltip"]')!.textContent!;
      expect(text).toContain('selected range and filters');
      expect(text).toContain('N is the');
      expect(text).toContain('Paper trades (simulated fills)');
      expect(text).toContain('gross of commissions and slippage');
      expect(text).toContain('pre-tax');
      // The definition moved into the hint: no plain hint line repeats it.
      expect(tile.querySelector('div.hint')).toBeNull();
    }
  });

  it('keeps the money equivalent under the max drawdown tile', () => {
    const { el } = render();
    const tile = [...el.querySelectorAll('sb-stat-tile')]
      .find((t) => t.querySelector('.label')?.textContent?.trim() === ANALYTICS_DRAWDOWN_LABEL)!;
    // cum_pnl 70 -> 40: a 30 fall, in the stubbed '$'.
    const secondary = tile.querySelector('.secondary')!.textContent!;
    expect(secondary).toContain('30');
    expect(secondary).toContain('$');
  });
});

/* -- v195 §5.2 -- the performance strip leads with expectancy --------------- */

describe('OverviewTab performance strip (v195 §5.2)', () => {
  beforeEach(() => TestBed.resetTestingModule());

  const tiles = (fixture: ReturnType<typeof render>['fixture']): StatTile[] =>
    fixture.debugElement.queryAll(By.css('sb-stat-tile')).map((d) => d.componentInstance as StatTile);

  it('leads with ExpR, win rate after it, never in the lead slot', () => {
    const { fixture } = render();
    expect(tiles(fixture).map((tile) => tile.label())).toEqual([
      'ExpR', 'Win rate', 'Total R', 'Profit factor', ANALYTICS_DRAWDOWN_LABEL, ANALYTICS_SHARPE_LABEL,
    ]);
  });

  it('shows N on every tile and states the paper, pre-cost, pre-tax basis in each About hint', () => {
    const { fixture } = render();
    for (const tile of tiles(fixture)) {
      expect(tile.sample(), tile.label()).not.toBeNull();
      expect(tile.about(), tile.label()).toContain(PERFORMANCE_CAVEAT);
      expect(tile.about()!.split(PERFORMANCE_CAVEAT), tile.label()).toHaveLength(2);
    }
    expect(tiles(fixture)[0].about()).toBe(ANALYTICS_EXPR_ABOUT);
  });

  it('marks a thin ExpR sample with the small-N cue', () => {
    const { el } = render();
    // The stub's expectancy_n is 34 (adequate); the equity points_n is 2 (thin).
    const total = Array.from(el.querySelectorAll('sb-stat-tile'))
      .find((tile) => tile.querySelector('.label')?.textContent?.trim() === 'Total R')!;
    expect(total.querySelector('.thin')).not.toBeNull();
    const expr = el.querySelector('sb-stat-tile')!;
    expect(expr.querySelector('.thin')).toBeNull();
  });

  it('rules the tiles as one auto-fit stat strip and declares no grid of its own', () => {
    const { el } = render();
    const strip = el.querySelector('sb-stat-strip.kpis')!;
    expect(strip.querySelectorAll('sb-stat-tile')).toHaveLength(6);
    expect(strip.querySelector('.sb-strip-grid')!.classList).not.toContain('sb-strip-fixed');
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/tabs/overview.ts'), 'utf8');
    expect(src).not.toMatch(/\.kpis\s*\{/);
  });
});
