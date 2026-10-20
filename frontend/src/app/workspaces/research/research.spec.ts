import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, convertToParamMap, provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { LedgerRow, ResearchLedger, StrategyRow } from '../../api/models';
import { ResearchStore, filtersFromParams } from '../../stores/research.store';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { DISCLAIMER, Research, VERDICT_TONE } from './research';

/* The page is a renderer over ResearchStore, so these tests look at what a
 * reader sees: which rows, how a missing figure and a missing record read,
 * what the q-value is said to be, and that the filters are the URL. */

const row = (over: Partial<LedgerRow>): LedgerRow => ({
  id: 'x', date: '2026-10-01', hypothesis: 'A gate', instrument: 'v2', n: 100, exp_r: 0.1,
  p: 0.04, verdict: 'FAIL', record: 'docs/superpowers/results/x.md', q: 0.08,
  record_exists: true, record_kind: 'results', ...over,
});

const LEDGER: ResearchLedger = {
  rows: [
    row({ id: 'e33-avwap', date: '2026-07-26', hypothesis: 'AVWAP levels', instrument: 'v1', n: null, exp_r: null, p: null, q: null, verdict: 'FAIL', record: 'docs/superpowers/plans/implemented/v35.md', record_exists: false, record_kind: 'plans' }),
    row({ id: 'v136-rs', date: '2026-10-06', hypothesis: 'RS gate lift', n: 120, exp_r: 0.12, p: 0.03, q: 0.06, verdict: 'PASS' }),
    row({ id: 'v140-screen', date: '2026-10-08', hypothesis: 'Idea screen', instrument: 'screen-v1', verdict: 'SCREEN-FAIL' }),
  ],
  q_family_m: 2,
  verdicts: ['PASS', 'FAIL', 'SCREEN-FAIL'],
  instruments: ['v1', 'v2', 'screen-v1'],
};

const strategy = (over: Partial<StrategyRow>): StrategyRow => ({
  strategy: 'RSI', status: 'VALIDATED', n: 80, win_rate: 55, expectancy_r: 0.21,
  window: '2024-01..2025-06', run_date: '2026-08-01', live_n: 12, live_wr: 50,
  delta_vs_oos: -5, decayed: false, evidence_decay: 'fresh', gate_description: null,
  win_rate_series: [], ...over,
});

const REGISTRY = [strategy({}), strategy({ strategy: 'EMA', status: 'WEAK', run_date: '2026-07-15', window: '2023-01..2024-06' })];

function create(
  ledger: ResearchLedger = LEDGER,
  registry: StrategyRow[] = REGISTRY,
): { fixture: ComponentFixture<Research>; store: InstanceType<typeof ResearchStore>; router: Router } {
  // The row drawer is a real <dialog>; jsdom has no showModal()/close().
  installDialogPolyfill();
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      ResearchStore,
    ],
  });
  const fixture = TestBed.createComponent(Research);
  const store = TestBed.inject(ResearchStore);
  const http = TestBed.inject(HttpTestingController);
  store.load();
  http.expectOne('/api/v1/research/ledger').flush(ledger);
  http.expectOne('/api/v1/analytics/registry').flush({ registry });
  fixture.detectChanges();
  return { fixture, store, router: TestBed.inject(Router) };
}

const text = (fixture: ComponentFixture<Research>): string =>
  (fixture.nativeElement as HTMLElement).textContent?.replace(/\s+/g, ' ') ?? '';

const tables = (fixture: ComponentFixture<Research>): HTMLElement[] =>
  Array.from((fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>('sb-data-table'));

describe('Research', () => {
  it('lists the ledger newest first, with an em dash for a figure that was not recorded', () => {
    const { fixture } = create();
    const ledger = tables(fixture)[1].textContent ?? '';
    expect(ledger.indexOf('v140-screen')).toBeLessThan(ledger.indexOf('v136-rs'));
    expect(ledger.indexOf('v136-rs')).toBeLessThan(ledger.indexOf('e33-avwap'));
    expect(ledger).toContain('—');
    expect(ledger).not.toContain('null');
  });

  it('shows the registry with the tier, its run date and window, and WEAK muted', () => {
    const { fixture } = create();
    const registry = tables(fixture)[0];
    expect(registry.textContent).toContain('2026-08-01');
    expect(registry.textContent).toContain('2024-01..2025-06');
    const chips = Array.from(registry.querySelectorAll('sb-chip'));
    expect(chips.map((chip) => chip.textContent?.trim())).toEqual(['VALIDATED', 'WEAK']);
    expect(chips[0].innerHTML).not.toEqual(chips[1].innerHTML.replace('WEAK', 'VALIDATED'));
    expect(text(fixture)).toContain('Figures in R, pre-tax.');
  });

  it('says so when no strategy has a registry entry', () => {
    const { fixture } = create(LEDGER, []);
    expect(text(fixture)).toContain('No strategy has a registry entry');
  });

  it('offers one chip per server verdict, each with its count', () => {
    const { fixture } = create();
    const chips = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button.verdict'));
    expect(chips.map((chip) => chip.textContent?.replace(/\s+/g, ' ').trim()))
      .toEqual(['PASS 1', 'FAIL 1', 'SCREEN-FAIL 1']);
  });

  it('writes a verdict toggle to the URL, and the URL filters the rows', async () => {
    const { fixture, store, router } = create();
    const fail = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button.verdict'))
      .find((chip) => chip.textContent?.includes('FAIL') && !chip.textContent.includes('SCREEN'))!;
    fail.click();
    await fixture.whenStable();
    expect(router.url).toContain('verdict=FAIL');

    // What the route resolver does with that URL.
    store.hydrate(filtersFromParams(convertToParamMap({ verdict: 'FAIL', instrument: 'v1', q: 'avwap' })));
    fixture.detectChanges();
    const ledger = tables(fixture)[1].textContent ?? '';
    expect(ledger).toContain('e33-avwap');
    expect(ledger).not.toContain('v136-rs');
    expect(fail.getAttribute('aria-pressed')).toBe('true');
  });

  it('says what the q-value is, and over how many rows, in the drawer', () => {
    const { fixture, store } = create();
    store.select('v136-rs');
    fixture.detectChanges();
    const page = text(fixture);
    expect(page).toContain('reported, never gating — BH over all 2 ledger rows with a p-value, mixing instruments; filters do not change it');
    expect(page).toContain('window and method: see record');
    expect(page).toContain('docs/superpowers/results/x.md');
    expect(page).not.toContain('not in this deploy');
  });

  it('strikes through a record that is not in this deploy', () => {
    const { fixture, store } = create();
    store.select('e33-avwap');
    fixture.detectChanges();
    const record = (fixture.nativeElement as HTMLElement).querySelector('code.record')!;
    expect(record.classList.contains('missing')).toBe(true);
    expect(text(fixture)).toContain('not in this deploy');
  });

  it('carries the fixed footer and the read-only note', () => {
    const { fixture } = create();
    expect(text(fixture)).toContain(DISCLAIMER);
    expect(text(fixture)).toContain('this page never edits it');
  });
});

describe('VERDICT_TONE', () => {
  it('colours the v173 override verdicts by how the measurement came out', () => {
    expect(VERDICT_TONE['SAVED']).toBe('good');
    expect(VERDICT_TONE['COST']).toBe('bad');
    expect(VERDICT_TONE['INCONCLUSIVE']).toBe('neutral');
    expect(VERDICT_TONE['PASS']).toBe('good');          // the existing entries are untouched
    expect(VERDICT_TONE['SCREEN-UNDERPOWERED']).toBe('warn');
  });
});
