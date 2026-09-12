import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { Risk as RiskData, RiskMetrics } from '../../api/models';
import { Risk } from './risk';
import { RiskStore } from '../../stores/risk.store';

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

function seed(): { fixture: ComponentFixture<Risk>; backend: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      RiskStore,
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
    // At least one open position, or the empty-book state (D31/asyncInputs'
    // isEmpty) hides this panel along with heat and exposure -- correct
    // behaviour, but not what these tiles-in-isolation tests are about.
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
      'Sharpe (R)', 'Max drawdown (R)',
    ]);
  });

  it('renders each metric with the sample it was computed from', async () => {
    const fixture = await renderWithMetrics({ beta_spy: { value: 1.12, n: 118 } });
    expect(tileHost(fixture, 'Beta vs SPY').querySelector('.sample')!.textContent).toContain('N=118');
  });

  it('de-emphasises a metric computed from a thin sample', async () => {
    const fixture = await renderWithMetrics({ sharpe_r: { value: 0.96, n: 7 } });
    expect(tileHost(fixture, 'Sharpe (R)').classList).toContain('thin');
  });

  it('renders an uncomputable metric as no-value, never as zero', async () => {
    const fixture = await renderWithMetrics({ var_95: { value: null, n: 3 } });
    expect(tileHost(fixture, 'VaR 95%').querySelector('.value')!.textContent!.trim()).toBe('—');
  });

  it('labels Sharpe as an R measure so it is not read as annualised', async () => {
    const fixture = await renderWithMetrics();
    expect(tileLabels(fixture)).toContain('Sharpe (R)');
  });

  it('does not reuse one sample size across both metric families', async () => {
    const fixture = await renderWithMetrics({
      var_95: { value: 0.03, n: 118 }, sharpe_r: { value: 0.9, n: 782 },
    });
    expect(tileHost(fixture, 'VaR 95%').querySelector('.sample')!.textContent).toContain('118');
    expect(tileHost(fixture, 'Sharpe (R)').querySelector('.sample')!.textContent).toContain('782');
  });
});
