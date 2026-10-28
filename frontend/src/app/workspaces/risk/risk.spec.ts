import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Provider, provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { Risk as RiskData, RiskMetrics } from '../../api/models';
import {
  EXPOSURE_HINT, Risk, UNROUNDED_TOTALS_NOTE, drawdownFxNote, exactRiskText, reconciles, unmappedNote,
  RISK_DRAWDOWN_LABEL, RISK_SHARPE_LABEL,
} from './risk';
import { ConnectionStore } from '../../stores/connection.store';
import { RiskStore } from '../../stores/risk.store';
import { ViewportService } from '../../ui/breakpoints';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { compactKeys, drawerKeys, openRowDrawer, phoneViewport } from '../../ui/data-table/testing/reachability';

/* v85 D37: every metric a {value, n} pair -- a fixture with real, distinct
 * sample sizes across the distributional (n=118) and trade (n=782) families,
 * matching the shape GET /risk (R8-03) actually serves. */
const DEFAULT_METRICS: RiskMetrics = {
  var_95: { value: 0.031, n: 118 },
  expected_shortfall_95: { value: 0.047, n: 118 },
  annualised_vol: { value: 0.148, n: 118 },
  beta_spy: { value: 1.12, n: 118 },
  sharpe_r: { value: 0.96, n: 782 },
  max_drawdown_r: { value: 8.4, n: 782 },
  as_of: '2026-09-10',
  benchmark_symbol: 'SPY',
};

function payload(overrides: Partial<RiskData> = {}): RiskData {
  return {
    heat: { open_pct: 3, cap_pct: 20 },
    positions: [],
    sector_heat: [],
    clusters: [],
    throttle: { multiplier: 1, paused: false },
    killswitch: { on: false },
    scan_health: { latest_s: 1.2, slowdown: false },
    metrics: DEFAULT_METRICS,
    correlation: { labels: [], values: [] },
    ...overrides,
  } as RiskData;
}

function seed(extra: Provider[] = []): { fixture: ComponentFixture<Risk>; backend: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      RiskStore, ...extra,
    ],
  });
  const fixture = TestBed.createComponent(Risk);
  TestBed.inject(RiskStore).load();
  const backend = TestBed.inject(HttpTestingController);
  return { fixture, backend };
}

describe('Risk states', () => {
  it('shows a skeleton while loading, before the first response', () => {
    const { fixture } = seed();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.skeleton')).toBeTruthy();
  });

  it('shows the error state on a first-load failure', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend
      .expectOne('/api/v1/risk')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.failed')).toBeTruthy();
  });

  it('shows the measured-zero empty state, not a spinner, when there are no open positions', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/risk').flush(payload({ positions: [] }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('No open risk');
    expect(el.querySelector('.skeleton')).toBeNull();
  });

  it('keeps the killswitch usable at zero open risk', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/risk').flush(payload({ positions: [] }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const button = [...el.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Engage killswitch'),
    );
    expect(button).toBeTruthy();
    expect(button?.disabled).toBe(false);
  });
});

/* -- v85 R8-04 -- the six risk metric tiles -- */

async function renderWithMetrics(
  metricsOverrides: Partial<RiskMetrics> = {},
): Promise<ComponentFixture<Risk>> {
  const { fixture, backend } = seed();
  fixture.detectChanges();
  backend.expectOne('/api/v1/risk').flush(payload({
    // Risk metrics has its own always-on sb-async now (empty hardcoded
    // false) -- it no longer needs an open position to render, but keeping
    // one here is harmless and these tests aren't about that boundary.
    positions: [{
      trade_id: 't1', ticker: 'AAPL', strategy: 'VWAP',
      shares: 10, entry: 100, stop_loss: 95, risk_pct: 3,
    }],
    metrics: { ...DEFAULT_METRICS, ...metricsOverrides },
  }));
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture;
}

function tileHost(fixture: ComponentFixture<Risk>, label: string): HTMLElement {
  const hosts = [...(fixture.nativeElement as HTMLElement).querySelectorAll('sb-stat-tile')] as HTMLElement[];
  const found = hosts.find((h) => h.querySelector('.label')?.textContent?.trim() === label);
  if (!found) throw new Error(`no tile labelled "${label}"`);
  // sb-stat-tile puts .thin/.value/.sample on its own inner .tile div, not
  // the host element -- callers want that div, not the custom element.
  return found.querySelector('.tile') as HTMLElement;
}

function tileLabels(fixture: ComponentFixture<Risk>): string[] {
  return [...(fixture.nativeElement as HTMLElement).querySelectorAll('sb-stat-tile .label')]
    .map((el) => el.textContent!.trim());
}

describe('Risk metric tiles', () => {
  it('renders the six metrics as stat tiles', async () => {
    const fixture = await renderWithMetrics();
    expect(tileLabels(fixture)).toEqual([
      'VaR 95%', 'Expected shortfall', 'Annualised vol', 'Beta vs SPY',
      RISK_SHARPE_LABEL, RISK_DRAWDOWN_LABEL,
    ]);
  });

  it('renders each metric with the sample it was computed from', async () => {
    const fixture = await renderWithMetrics({ beta_spy: { value: 1.12, n: 118 } });
    expect(tileHost(fixture, 'Beta vs SPY').querySelector('.sample')!.textContent).toContain('N=118');
  });

  it('de-emphasises a metric computed from a thin sample', async () => {
    const fixture = await renderWithMetrics({ sharpe_r: { value: 0.96, n: 7 } });
    expect(tileHost(fixture, RISK_SHARPE_LABEL).classList).toContain('thin');
  });

  it('renders an uncomputable metric as no-value, never as zero', async () => {
    const fixture = await renderWithMetrics({ var_95: { value: null, n: 3 } });
    expect(tileHost(fixture, 'VaR 95%').querySelector('.value')!.textContent!.trim()).toBe('—');
  });

  it('names the basis of Sharpe and max drawdown so neither reads as the Analytics figure', async () => {
    const fixture = await renderWithMetrics();
    const labels = tileLabels(fixture);
    expect(labels).toContain('Sharpe · per-trade R, all closed');
    expect(labels).toContain('Max drawdown · cumulative R, all closed');
    expect(labels).not.toContain('Sharpe (R)');
    expect(labels).not.toContain('Max drawdown (R)');
  });

  it('labels the beta tile with the actual configured benchmark, not a hardcoded SPY', async () => {
    const fixture = await renderWithMetrics({ benchmark_symbol: 'QQQ' });
    expect(tileLabels(fixture)).toContain('Beta vs QQQ');
    expect(tileLabels(fixture)).not.toContain('Beta vs SPY');
  });

  it('does not reuse one sample size across both metric families', async () => {
    const fixture = await renderWithMetrics({
      var_95: { value: 0.03, n: 118 }, sharpe_r: { value: 0.9, n: 782 },
    });
    expect(tileHost(fixture, 'VaR 95%').querySelector('.sample')!.textContent).toContain('118');
    expect(tileHost(fixture, RISK_SHARPE_LABEL).querySelector('.sample')!.textContent).toContain('782');
  });

  it('still shows the six metrics when the book is flat', async () => {
    // Regression: these six are computed from the daily-return/closed-trade
    // series, not from currently open positions, so they used to share the
    // position-count-gated sb-async below and vanish along with Portfolio
    // heat/Exposure/Correlation the moment positions.length was 0 --
    // reported back as "Risk metrics shows nothing".
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/risk').flush(payload({
      positions: [],
      metrics: DEFAULT_METRICS,
    }));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(tileLabels(fixture)).toEqual([
      'VaR 95%', 'Expected shortfall', 'Annualised vol', 'Beta vs SPY',
      RISK_SHARPE_LABEL, RISK_DRAWDOWN_LABEL,
    ]);
  });
});

describe('Risk metric tiles in a stat strip (v186 D3)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/risk/risk.ts'), 'utf8');

  it('rules the six tiles with one stat strip, auto-fit at 140px', async () => {
    const fixture = await renderWithMetrics();
    const el = fixture.nativeElement as HTMLElement;
    const strip = el.querySelector<HTMLElement>('sb-stat-strip.metric-grid');
    expect(strip).not.toBeNull();
    expect(strip!.querySelectorAll('sb-stat-tile')).toHaveLength(6);
    expect(el.querySelectorAll('sb-stat-tile')).toHaveLength(6);
    // No cols: the default auto-fit column rule, not the fixed-count one.
    expect(strip!.style.getPropertyValue('--strip-cols')).toBe('');
    expect(strip!.querySelector('.sb-strip-grid')!.classList).not.toContain('sb-strip-fixed');
  });

  it('keeps the thin-sample cues inside the strip', async () => {
    const fixture = await renderWithMetrics({ sharpe_r: { value: 0.96, n: 7 } });
    const tile = tileHost(fixture, RISK_SHARPE_LABEL);
    expect(tile.closest('sb-stat-strip')).not.toBeNull();
    expect(tile.classList).toContain('thin');
    expect(tile.querySelector('.flag')!.textContent).toContain('thin sample');
  });

  it('declares no metric grid of its own', () => {
    expect(src).not.toMatch(/\.metric-grid\s*\{/);
    expect(src).toMatch(/<sb-stat-strip class="metric-grid">/);
  });
});

/* -- v85 R8-05 -- the heat gauge, the risk budget, and the correlation matrix -- */

async function render(overrides: Partial<RiskData> = {}, extra: Provider[] = []): Promise<ComponentFixture<Risk>> {
  const { fixture, backend } = seed(extra);
  fixture.detectChanges();
  backend.expectOne('/api/v1/risk').flush(payload({
    // Non-empty by default, or asyncInputs' isEmpty (positions.length === 0)
    // hides this whole panel set behind the "No open risk" empty state --
    // correct behaviour, but not what these tests are about.
    positions: [{
      trade_id: 't1', ticker: 'AAPL', strategy: 'VWAP',
      shares: 10, entry: 100, stop_loss: 95, risk_pct: 3,
    }],
    ...overrides,
  }));
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture;
}

describe('Risk gauge, budget and correlation matrix', () => {
  it('reports heat once without a gauge', async () => {
    const el = (await render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52 } }))
      .nativeElement as HTMLElement;
    expect(el.querySelector('sb-gauge')).toBeNull();
    expect(el.querySelector('.heat-note')!.textContent).toContain('52% of the risk budget is used');
  });

  it('shows a utilisation past the cap truthfully', async () => {
    const el = (await render({ heat: { open_pct: 7.8, cap_pct: 6, utilisation_pct: 130 } }))
      .nativeElement as HTMLElement;
    expect(el.querySelector('.heat-note')!.textContent).toContain('130% of the cap');
  });

  const gapText = (fixture: ComponentFixture<Risk>) =>
    (fixture.nativeElement as HTMLElement).querySelector('[data-testid="gap-risk"]')!.textContent ?? '';

  it('shows the summed short gap risk inside the heat panel', async () => {
    const fixture = await render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52,
                                           gap_risk_amount: 1234.4, gap_risk_unknown: 0 } });
    const el = (fixture.nativeElement as HTMLElement).querySelector('[data-testid="gap-risk"]')!;
    expect(el.closest('sb-panel')!.getAttribute('heading')).toBe('Portfolio heat');
    expect(gapText(fixture)).toContain('1,234');
    expect(gapText(fixture)).toContain('p99');
    expect(gapText(fixture)).not.toContain('without a gap figure');
  });

  it('counts shorts without a gap figure instead of hiding them', async () => {
    const fixture = await render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52,
                                           gap_risk_amount: null, gap_risk_unknown: 2 } });
    expect(gapText(fixture)).toContain('n/a');
    expect(gapText(fixture)).toContain('2 shorts without a gap figure');
  });

  it('says so when no short is open', async () => {
    const fixture = await render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52,
                                           gap_risk_amount: null, gap_risk_unknown: 0 } });
    expect(gapText(fixture)).toContain('no open shorts');
  });

  it('keeps the heat figure on stop risk', async () => {
    const fixture = await render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52,
                                           gap_risk_amount: 900, gap_risk_unknown: 0 } });
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.heat-figure')!.textContent).toContain('3.10');
    expect(el.querySelector('.heat-note')!.textContent).toContain('52% of the risk budget is used');
  });

  it('breaks the risk budget into cap, used and remaining', async () => {
    const el = (await render({ heat: { open_pct: 3.1, cap_pct: 6, utilisation_pct: 52 } }))
      .nativeElement as HTMLElement;
    const budget = el.querySelector('.risk-budget')!;
    expect(budget.textContent).toContain('6');
    expect(budget.textContent).toContain('3.1');
    expect(budget.textContent).toContain('2.9');
  });

  it('reports no remaining budget rather than a negative one when over the cap', async () => {
    const el = (await render({ heat: { open_pct: 7.8, cap_pct: 6, utilisation_pct: 130 } }))
      .nativeElement as HTMLElement;
    expect(el.querySelector('.risk-budget .remaining')!.textContent).toContain('0');
    expect(el.querySelector('.risk-budget')!.textContent).toContain('over');
  });

  it('renders the correlation matrix with the clusters outlined on it', async () => {
    const el = (await render({
      correlation: { labels: ['AAPL', 'MSFT'], values: [[1, 0.68], [0.68, 1]] },
      clusters: [['AAPL', 'MSFT']],
    })).nativeElement as HTMLElement;
    expect(el.querySelector('sb-matrix .clustered')).not.toBeNull();
  });

  it('keeps the cluster list beside the matrix', async () => {
    const el = (await render({ clusters: [['AAPL', 'MSFT']] })).nativeElement as HTMLElement;
    expect(el.querySelector('sb-panel[heading="Correlated clusters"]')).not.toBeNull();
  });

  it('keeps the killswitch panel', async () => {
    const el = (await render()).nativeElement as HTMLElement;
    expect(el.querySelector('sb-panel[heading="Killswitch"]')).not.toBeNull();
  });
});

/* -- v85 R8-06 -- control bar, freshness, and the narrow-width pass -- */

describe('Risk freshness and chrome', () => {
  it('marks the metrics panel with the bar date they were computed from', async () => {
    const el = (await render({ metrics: { ...DEFAULT_METRICS, as_of: '2026-09-10' } }))
      .nativeElement as HTMLElement;
    expect(el.querySelector('.metrics sb-freshness')).not.toBeNull();
  });

  it('shows the metrics panel marker as a real date, not a bogus midnight time', async () => {
    // I1: `as_of` is a date-only string ("2026-09-10", a daily bar has no
    // time-of-day). Rendering it as a full timestamp always read
    // "as of 00:00:00" regardless of actual freshness.
    const el = (await render({ metrics: { ...DEFAULT_METRICS, as_of: '2026-09-10' } }))
      .nativeElement as HTMLElement;
    const marker = el.querySelector('.metrics sb-freshness .freshness')!;
    expect(marker.textContent).toContain('as of 2026-09-10');
    expect(marker.textContent).not.toContain('00:00:00');
  });

  it('dates each metrics panel by its own bar, not one stamp for the page', async () => {
    const el = (await render()).nativeElement as HTMLElement;
    expect(el.querySelectorAll('sb-freshness').length).toBeGreaterThan(1);
  });

  it('renders no in-page heading', async () => {
    expect((await render()).nativeElement.querySelector('h1')).toBeNull();
  });
});

/* -- v95 D1 -- grid tracks that survive a 320px phone ----------------------- */

describe('Risk grid floors', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/risk/risk.ts'), 'utf8');

  it('never declares a fixed px floor a 320px phone cannot meet', () => {
    // minmax(300px, 1fr) overflows its container below ~330px of content
    // box. min(100%, 300px) collapses instead, which is the whole point.
    const bare = [...src.matchAll(/minmax\(\s*(\d+)px/g)].map((m) => Number(m[1]));
    expect(bare.filter((px) => px > 260)).toEqual([]);
  });
});

/* -- v195 §5.1 -- scan health and the data source moved to System → Providers.
 * Their v106 cases moved with them, to system/providers-tab.spec.ts. -- */

describe('Risk keeps only risk (v195 §5.1)', () => {
  it('shows no Scan health or Data source panel, whatever the payload carries', async () => {
    const el = (await render({
      scan_health: {
        durations_s: [12, 14], latest_s: 14, slowdown: true,
        data_sources: {
          enabled: true, feed: 'iex', breaker_open: true, fallback_rate: 0.4, scans: 20,
        },
      },
    } as Partial<RiskData>)).nativeElement as HTMLElement;
    const headings = [...el.querySelectorAll('sb-panel h2')].map((h) => h.textContent!.trim());

    expect(headings).not.toContain('Scan health');
    expect(headings).not.toContain('Data source');
    expect(el.querySelector('sb-sparkline')).toBeNull();
    expect(el.textContent).not.toContain('Alpaca');
    expect(el.textContent).not.toContain('Scans are running slower');
  });
});

describe('Risk exposure on a phone (v179 §3.1)', () => {
  async function phoneTable(): Promise<{ fixture: ComponentFixture<Risk>; table: HTMLElement }> {
    installDialogPolyfill();
    const fixture = await render({}, [phoneViewport()]);
    return { fixture, table: (fixture.nativeElement as HTMLElement).querySelector('sb-data-table') as HTMLElement };
  }

  it('keeps the risk and the stop on the compact row (money floor)', async () => {
    const { table } = await phoneTable();
    expect(compactKeys(table)).toEqual(['ticker', 'risk_pct', 'stop_loss', 'entry']);
  });

  it('keeps the shares and Risk % totals as a compact totals line', async () => {
    const { table } = await phoneTable();
    expect(table.querySelector('.compact-footer [data-col="shares"]')!.textContent).toContain('10');
    expect(table.querySelector('.compact-footer [data-col="risk_pct"]')!.textContent).toContain('3.00');
  });

  it('reaches every column and keeps the link to the trade the ticker cell had', async () => {
    const { fixture, table } = await phoneTable();
    openRowDrawer(table);
    fixture.detectChanges();
    expect([...new Set([...compactKeys(table), ...drawerKeys(table)])].sort())
      .toEqual(['entry', 'risk_pct', 'shares', 'stop_loss', 'strategy', 'ticker']);
    expect(table.querySelector('a.drawer-detail-link')!.getAttribute('href')).toBe('/trades/t1');
  });
});

/* -- v194 B4/B5 -- shares and risk percentages that are true -- */

const FRACTIONAL_BOOK = [
  { trade_id: 'a', ticker: 'AAA', strategy: 'VWAP', shares: 2.72, entry: 100, stop_loss: 95, risk_pct: 0.004 },
  { trade_id: 'b', ticker: 'BBB', strategy: 'VWAP', shares: 3, entry: 50, stop_loss: 49, risk_pct: 0.004 },
  { trade_id: 'c', ticker: 'CCC', strategy: 'VWAP', shares: 0.5, entry: 10, stop_loss: 9, risk_pct: 0.004 },
];

describe('Risk exposure figures (v194 B4/B5)', () => {
  async function phone(): Promise<{ fixture: ComponentFixture<Risk>; table: HTMLElement }> {
    installDialogPolyfill();
    const fixture = await render({ positions: FRACTIONAL_BOOK }, [phoneViewport()]);
    return { fixture, table: (fixture.nativeElement as HTMLElement).querySelector('sb-data-table') as HTMLElement };
  }
  const drawerField = (table: HTMLElement, key: string) =>
    table.querySelector(`sb-drawer.row-drawer dl.drawer-fields > [data-col="${key}"]`)!;
  const exposureTip = (fixture: ComponentFixture<Risk>) =>
    (fixture.nativeElement as HTMLElement)
      .querySelector('sb-panel[heading="Exposure by position"] header sb-hint [role="tooltip"]')!.textContent ?? '';

  it('renders fractional shares in the drawer and totals the unrounded values', async () => {
    const { fixture, table } = await phone();
    // 2.72 + 3 + 0.5 = 6.22 -- not 3 + 3 + 1 = 7.
    expect(table.querySelector('.compact-footer [data-col="shares"]')!.textContent).toContain('6.22');
    openRowDrawer(table);
    fixture.detectChanges();
    expect(drawerField(table, 'shares').textContent).toContain('2.72');
  });

  it('renders a tiny non-zero risk as <0.01%, never 0.00%, and the total with its unit', async () => {
    const { table } = await phone();
    const cell = table.querySelector('.compact-cell[data-col="risk_pct"]')!;
    expect(cell.textContent).toContain('<0.01%');
    expect(cell.textContent).not.toContain('0.00%');
    // 3 x 0.004 = 0.012 -> "0.01%", with the "%" the old footer dropped.
    expect(table.querySelector('.compact-footer [data-col="risk_pct"]')!.textContent).toContain('0.01%');
  });

  it('puts the exact tiny value in an sb-hint, reachable in the row drawer', async () => {
    const { fixture, table } = await phone();
    openRowDrawer(table);
    fixture.detectChanges();
    const hint = drawerField(table, 'risk_pct').querySelector('sb-hint')!;
    expect(hint.querySelector('[role="tooltip"]')!.textContent).toContain('0.004%');
    expect(hint.querySelector('button')!.getAttribute('aria-label')).toBe('Exact risk for AAA');
    hint.querySelector('button')!.click();
    fixture.detectChanges();
    expect(hint.querySelector('[role="tooltip"]')!.hasAttribute('data-popover-open')).toBe(true);
  });

  it('says totals use unrounded values only when the rounded rows do not add up', async () => {
    const mismatch = exposureTip(await render({ positions: FRACTIONAL_BOOK }));
    expect(mismatch).toContain('paper book');
    expect(mismatch).toContain('2% dollar-risk cap');
    expect(mismatch).toContain(UNROUNDED_TOTALS_NOTE);
    const reconciled = exposureTip(await render());
    expect(reconciled.trim()).toBe(EXPOSURE_HINT);
  });

  it('formats the heat figure, the budget and sector heat through the same formatter', async () => {
    const el = (await render({
      heat: { open_pct: 0.003, cap_pct: 6, utilisation_pct: 0.1 },
      sector_heat: [{ sector: 'Technology', heat_pct: 0.003 }],
    })).nativeElement as HTMLElement;
    expect(el.querySelector('.heat-figure')!.textContent).toContain('<0.01%');
    expect(el.querySelector('.risk-budget')!.textContent).toContain('<0.01%');
    expect(el.querySelector('.sectors dd > span')!.textContent!.trim()).toBe('<0.01%');
  });
});

describe('Risk exposure helpers (v194 B4/B5)', () => {
  it('reconciles when the rounded rows add up to the rounded total', () => {
    expect(reconciles([2.72, 3.5], 2)).toBe(true);
    expect(reconciles([], 2)).toBe(true);
    expect(reconciles([null, 1], 2)).toBe(true);
    expect(reconciles([0.004, 0.004, 0.004], 2)).toBe(false);
    // The Intl display is 1.01 + 0.01, while the unrounded total displays 1.01.
    expect(reconciles([1.005, 0.005], 2)).toBe(false);
    expect(reconciles([1.005, 0.004], 2)).toBe(true);
  });

  it('gives an exact value only for a tiny non-zero risk', () => {
    expect(exactRiskText(0.002)).toContain('0.002%');
    expect(exactRiskText(-0.002)).toContain('-0.002%');
    for (const shown of [0, 0.01, 3, null]) expect(exactRiskText(shown)).toBeNull();
  });
});
describe('Risk exact tiny figures across device classes (v194 B5)', () => {
  const devices = ['lg', 'sm', 'xs'] as const;

  for (const device of devices) {
    it(`opens exact heat, budget, sector and total hints at ${device}`, async () => {
      const fixture = await render({
        heat: { open_pct: 0.002, cap_pct: 0.006, utilisation_pct: 33.3333333333 },
        sector_heat: [{ sector: 'Technology', heat_pct: 0.003 }],
        positions: [{ ...FRACTIONAL_BOOK[0], risk_pct: 0.002 }],
      }, [{
        provide: ViewportService,
        useValue: { viewport: signal(device), isPhone: signal(device === 'xs'), isNarrow: signal(device !== 'lg') },
      }]);
      const root = fixture.nativeElement as HTMLElement;
      const cases = [
        ['Exact portfolio heat', '0.002%'],
        ['Exact budget cap', '0.006%'],
        ['Exact budget used', '0.002%'],
        ['Exact budget remaining', '0.004%'],
        ['Exact sector heat for Technology', '0.003%'],
        ['Exact Risk % total', '0.002%'],
      ];
      for (const [label, value] of cases) {
        const trigger = root.querySelector<HTMLButtonElement>(`sb-hint > button[aria-label="${label}"]`);
        expect(trigger, label).not.toBeNull();
        expect(trigger!.closest('[inert]'), label).toBeNull();
        const tip = root.querySelector<HTMLElement>(`[id="${trigger!.getAttribute('aria-describedby')}"]`)!;
        expect(tip.textContent, label).toContain(value);
        trigger!.click();
        fixture.detectChanges();
        expect(tip.hasAttribute('data-popover-open'), label).toBe(true);
        trigger!.click();
        fixture.detectChanges();
      }
      const footer = root.querySelector(device === 'xs' ? '.compact-footer [data-col="risk_pct"]' : 'tfoot td:last-child')!;
      expect(footer.textContent).toContain('<0.01%');
      expect(footer.querySelector('sb-hint button')!.getAttribute('aria-label')).toBe('Exact Risk % total');
    });
  }

  it('does not add exact-value controls to zero or fully displayed figures', async () => {
    const root = (await render({
      heat: { open_pct: 0, cap_pct: 6, utilisation_pct: 0 },
      sector_heat: [{ sector: 'Technology', heat_pct: 0.01 }],
      positions: [{ ...FRACTIONAL_BOOK[0], risk_pct: 0 }],
    })).nativeElement as HTMLElement;
    expect(root.querySelector('sb-hint button[aria-label^="Exact"]')).toBeNull();
  });
});

/* -- v194 B6 -- no sector data is not no exposure -- */

const openPositions = (count: number) => Array.from({ length: count }, (_, i) => ({
  trade_id: `t${i}`, ticker: `T${i}`, strategy: 'VWAP', shares: 1, entry: 10, stop_loss: 9, risk_pct: 0.1,
}));

describe('Risk sector heat: no data vs no exposure (v194 B6)', () => {
  const sectorPanel = (fixture: ComponentFixture<Risk>) =>
    (fixture.nativeElement as HTMLElement).querySelector('sb-panel[heading="Sector heat"]') as HTMLElement;
  const squash = (text: string | null | undefined) => (text ?? '').replace(/\s+/g, ' ').trim();

  it('shows the cannot-be-assessed banner, never "No sector exposure", when no position has sector data', async () => {
    const panel = sectorPanel(await render({ positions: openPositions(8), sector_heat: [], unmapped_count: 8 }));
    const banner = panel.querySelector('.panel-problem[role="status"]');
    expect(squash(banner?.textContent))
      .toBe('Sector concentration cannot be assessed: no sector data for 8 of 8 open positions.');
    expect(panel.textContent).not.toContain('No sector exposure');
    expect(panel.querySelector('.sectors')).toBeNull();
  });

  it('keeps the mapped sectors beside the banner when only some positions lack data', async () => {
    const panel = sectorPanel(await render({
      positions: openPositions(2),
      sector_heat: [{ sector: 'Technology', heat_pct: 0.1 }],
      unmapped_count: 1,
    }));
    expect(squash(panel.querySelector('.panel-problem')?.textContent))
      .toBe('Sector concentration cannot be assessed: no sector data for 1 of 2 open positions.');
    expect(panel.querySelector('.sectors dt')!.textContent).toContain('Technology');
  });

  it('shows the true-zero state, and no banner, when every position is mapped', async () => {
    const panel = sectorPanel(await render({ sector_heat: [], unmapped_count: 0 }));
    expect(panel.querySelector('.panel-problem')).toBeNull();
    expect(squash(panel.querySelector('.none')?.textContent)).toBe('No sector exposure.');
  });

  it('reads a response without the field as fully mapped', async () => {
    const panel = sectorPanel(await render({ sector_heat: [] }));
    expect(panel.querySelector('.panel-problem')).toBeNull();
    expect(squash(panel.querySelector('.none')?.textContent)).toBe('No sector exposure.');
  });

  it('exposes the count through the store', async () => {
    await render({ positions: openPositions(3), unmapped_count: 3 });
    expect(TestBed.inject(RiskStore).unmappedCount()).toBe(3);
  });
});

describe('unmappedNote (v194 B6)', () => {
  it('says nothing when every position is mapped', () => {
    expect(unmappedNote(0, 5)).toBeNull();
    expect(unmappedNote(0, 0)).toBeNull();
  });

  it('names N of M, singular for one position', () => {
    expect(unmappedNote(8, 8)).toBe('Sector concentration cannot be assessed: no sector data for 8 of 8 open positions.');
    expect(unmappedNote(1, 1)).toBe('Sector concentration cannot be assessed: no sector data for 1 of 1 open position.');
  });

  it('never claims fewer open positions than unmapped ones', () => {
    // positions and the collector read the book separately; a failed read on
    // one side must not print "3 of 0".
    expect(unmappedNote(3, 0)).toBe('Sector concentration cannot be assessed: no sector data for 3 of 3 open positions.');
  });
});

describe('Risk metric basis and money drawdown (v194 B8)', () => {
  it('gives the Sharpe and drawdown tiles a hint with definition, population, N and caveat', async () => {
    const fixture = await renderWithMetrics();
    for (const label of [RISK_SHARPE_LABEL, RISK_DRAWDOWN_LABEL]) {
      const hint = tileHost(fixture, label).querySelector('sb-hint')!;
      expect(hint.querySelector('button')!.getAttribute('aria-label')).toBe(`About ${label}`);
      const text = hint.querySelector('[role="tooltip"]')!.textContent!;
      expect(text).toContain('every closed main-ledger trade, all time');
      expect(text).toContain('N is the closed-trade count');
      expect(text).toContain('Paper trades (simulated fills)');
      expect(text).toContain('gross of commissions and slippage');
      expect(text).toContain('pre-tax');
    }
  });

  it('says the Risk Sharpe is not annualised', async () => {
    const fixture = await renderWithMetrics();
    const text = tileHost(fixture, RISK_SHARPE_LABEL).querySelector('[role="tooltip"]')!.textContent!;
    expect(text).toContain('Not annualised');
  });

  it('shows the money drawdown under the R figure, negative, in the account currency', async () => {
    const fixture = await renderWithMetrics({
      max_drawdown_amount: { value: 412.5, n: 782, fx_missing_count: 0 },
    });
    const tile = tileHost(fixture, RISK_DRAWDOWN_LABEL);
    const secondary = tile.querySelector('.secondary')!.textContent!.trim();
    expect(secondary).toContain('412.50');
    expect(secondary).toMatch(/^[-−]/);
    expect(secondary).toContain(TestBed.inject(ConnectionStore).currency());
    expect(tile.querySelector('div.hint')).toBeNull();
  });

  it('shows no money line when the payload carries none', async () => {
    const fixture = await renderWithMetrics();
    expect(tileHost(fixture, RISK_DRAWDOWN_LABEL).querySelector('.secondary')).toBeNull();
  });

  it('shows no money line for an uncomputable money drawdown', async () => {
    const fixture = await renderWithMetrics({
      max_drawdown_amount: { value: null, n: 0, fx_missing_count: 0 },
    });
    expect(tileHost(fixture, RISK_DRAWDOWN_LABEL).querySelector('.secondary')).toBeNull();
  });

  it('says how many trades the money figure left out for want of an FX rate', async () => {
    const fixture = await renderWithMetrics({
      max_drawdown_amount: { value: 100, n: 779, fx_missing_count: 3 },
    });
    expect(tileHost(fixture, RISK_DRAWDOWN_LABEL).querySelector('div.hint')!.textContent)
      .toContain('3 closed trades without an FX rate for the exit day left out of the amount.');
  });

  it('drops the scope footnote now the labels carry the basis', async () => {
    const fixture = await renderWithMetrics();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.metrics-scope')).toBeNull();
    expect(el.textContent).not.toContain('Sharpe and max drawdown are per-trade R over all closed trades');
  });

  it('words the FX gap note in the singular and is silent at zero', () => {
    expect(drawdownFxNote(0)).toBeUndefined();
    expect(drawdownFxNote(1)).toBe('1 closed trade without an FX rate for the exit day left out of the amount.');
  });
});
