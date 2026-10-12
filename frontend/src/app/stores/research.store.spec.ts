import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { convertToParamMap } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { LedgerRow, ResearchLedger, StrategyRow } from '../api/models';
import {
  LEDGER_PAGE_SIZE,
  ResearchStore,
  filterLedger,
  filtersFromParams,
  filtersToParams,
  sortLedger,
} from './research.store';

/* What earns tests here: a null figure is "not recorded" and must sort last
 * in BOTH directions; the verdict chip counts must not collapse to the active
 * selection; and the filters round-trip the URL exactly. */

const row = (over: Partial<LedgerRow>): LedgerRow => ({
  id: 'x', date: '2026-10-01', hypothesis: 'A gate', instrument: 'v2', n: 100, exp_r: 0.1,
  p: 0.04, verdict: 'FAIL', record: 'docs/superpowers/results/x.md', q: 0.08,
  record_exists: true, record_kind: 'results', ...over,
});

const ROWS: LedgerRow[] = [
  row({ id: 'e33-avwap', date: '2026-07-26', hypothesis: 'AVWAP levels', instrument: 'v1', n: null, exp_r: null, p: null, q: null, verdict: 'FAIL' }),
  row({ id: 'v136-rs', date: '2026-10-06', hypothesis: 'RS gate lift', instrument: 'v2', n: 120, exp_r: 0.12, p: 0.03, q: 0.06, verdict: 'PASS' }),
  row({ id: 'v140-screen', date: '2026-10-08', hypothesis: 'Idea screen', instrument: 'screen-v1', n: 40, exp_r: -0.05, p: 0.4, q: 0.4, verdict: 'SCREEN-FAIL' }),
  row({ id: 'v17-regime', date: '2026-08-08', hypothesis: 'Regime gate', instrument: 'v1', n: null, exp_r: null, p: null, q: null, verdict: 'NO-LIFT' }),
];

const LEDGER: ResearchLedger = {
  rows: ROWS, q_family_m: 2,
  verdicts: ['PASS', 'FAIL', 'NO-LIFT', 'SCREEN-FAIL'],
  instruments: ['v1', 'v2', 'screen-v1'],
};

const REGISTRY: StrategyRow[] = [{
  strategy: 'RSI', status: 'VALIDATED', n: 80, win_rate: 55, expectancy_r: 0.21,
  window: '2024-01..2025-06', run_date: '2026-08-01', live_n: 12, live_wr: 50,
  delta_vs_oos: -5, decayed: false, evidence_decay: 'fresh', gate_description: null,
  win_rate_series: [],
}];

function seed(ledger: ResearchLedger = LEDGER): InstanceType<typeof ResearchStore> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      ResearchStore,
    ],
  });
  const http = TestBed.inject(HttpTestingController);
  const store = TestBed.inject(ResearchStore);
  store.load();
  http.expectOne('/api/v1/research/ledger').flush(ledger);
  http.expectOne('/api/v1/analytics/registry').flush({ registry: REGISTRY });
  return store;
}

describe('filtersFromParams / filtersToParams', () => {
  it('round-trips a full filter set', () => {
    const filters = { verdicts: ['FAIL', 'NO-LIFT'], instrument: 'v1', search: 'gate' };
    expect(filtersFromParams(convertToParamMap(filtersToParams(filters)))).toEqual(filters);
  });

  it('writes nulls for defaults so the URL stays clean', () => {
    expect(filtersToParams({ verdicts: [], instrument: '', search: '' }))
      .toEqual({ verdict: null, instrument: null, q: null });
  });

  it('reads an empty query string as no filters', () => {
    expect(filtersFromParams(convertToParamMap({}))).toEqual({ verdicts: [], instrument: '', search: '' });
  });
});

describe('filterLedger', () => {
  it('matches the search against id and hypothesis, case-insensitively', () => {
    const none = { verdicts: [], instrument: '', search: '' };
    expect(filterLedger(ROWS, { ...none, search: 'AVWAP' }).map((r) => r.id)).toEqual(['e33-avwap']);
    expect(filterLedger(ROWS, { ...none, search: 'v17' }).map((r) => r.id)).toEqual(['v17-regime']);
  });

  it('combines verdicts (any of) with instrument (exactly)', () => {
    const got = filterLedger(ROWS, { verdicts: ['FAIL', 'NO-LIFT'], instrument: 'v1', search: '' });
    expect(got.map((r) => r.id)).toEqual(['e33-avwap', 'v17-regime']);
  });
});

describe('sortLedger', () => {
  it('puts null figures last in both directions', () => {
    expect(sortLedger(ROWS, { key: 'n', direction: 'desc' }).map((r) => r.n)).toEqual([120, 40, null, null]);
    expect(sortLedger(ROWS, { key: 'n', direction: 'asc' }).map((r) => r.n)).toEqual([40, 120, null, null]);
  });

  it('leaves the input array untouched', () => {
    const before = ROWS.map((r) => r.id);
    sortLedger(ROWS, { key: 'date', direction: 'asc' });
    expect(ROWS.map((r) => r.id)).toEqual(before);
  });
});

describe('ResearchStore', () => {
  it('loads the ledger and the registry together', () => {
    const store = seed();
    expect(store.loading()).toBe(false);
    expect(store.registry()).toEqual(REGISTRY);
    expect(store.familySize()).toBe(2);
    expect(store.verdicts()).toEqual(LEDGER.verdicts);
  });

  it('lists newest first by default', () => {
    expect(seed().matching().map((r) => r.date)).toEqual(['2026-10-08', '2026-10-06', '2026-08-08', '2026-07-26']);
  });

  it('counts each verdict over the other filters, not over the verdict selection', () => {
    const store = seed();
    store.hydrate({ verdicts: ['FAIL'], instrument: 'v1', search: '' });
    expect(store.matching().map((r) => r.id)).toEqual(['e33-avwap']);
    // NO-LIFT still shows 1: selecting FAIL must not zero the other chips.
    expect(store.verdictCounts()).toEqual({ PASS: 0, FAIL: 1, 'NO-LIFT': 1, 'SCREEN-FAIL': 0 });
    expect(store.activeFilterCount()).toBe(2);
  });

  it('pages 25 at a time and reports the pre-slice total', () => {
    const many = Array.from({ length: 61 }, (_, i) => row({ id: `r${i}`, date: `2026-01-${String((i % 28) + 1).padStart(2, '0')}` }));
    const store = seed({ ...LEDGER, rows: many });
    expect(store.visible().length).toBe(LEDGER_PAGE_SIZE);
    expect(store.pageSpec()).toEqual({ total: 61, page: 1, perPage: 25 });
    store.setPage(3);
    expect(store.visible().length).toBe(11);
  });

  it('returns to page 1 when the filters change, and clamps a page past the end', () => {
    const many = Array.from({ length: 61 }, (_, i) => row({ id: `r${i}` }));
    const store = seed({ ...LEDGER, rows: many });
    store.setPage(9);
    expect(store.pageSpec().page).toBe(3);
    store.hydrate({ verdicts: [], instrument: '', search: 'r1' });
    expect(store.pageSpec().page).toBe(1);
  });

  it('selects a row by id, across pages, and clears it', () => {
    const store = seed();
    store.select('v17-regime');
    expect(store.selected()?.hypothesis).toBe('Regime gate');
    store.select(null);
    expect(store.selected()).toBeNull();
  });

  it('fetches once per visit: ensureLoaded is a no-op once the data is in', () => {
    const store = seed();
    store.ensureLoaded().subscribe();
    TestBed.inject(HttpTestingController).expectNone('/api/v1/research/ledger');
  });

  it('keeps the last data and records the message when a reload fails', () => {
    const store = seed();
    const http = TestBed.inject(HttpTestingController);
    store.load();
    http.expectOne('/api/v1/research/ledger').flush(
      { error: { code: 'ledger_invalid', message: 'ledger line 7: invalid field(s)' } },
      { status: 500, statusText: 'Server Error' });
    // forkJoin cancels the sibling request when one fails; nothing left to flush.
    expect(http.expectOne('/api/v1/analytics/registry').cancelled).toBe(true);
    expect(store.error()).toContain('ledger line 7');
    expect(store.matching().length).toBe(4);
  });
});
