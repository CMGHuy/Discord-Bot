# v150 Reports and Research workspaces: Part 2, the two stores

> Part of the v150 plan. Header, Global Constraints, the blocked-task gate, the wire shapes and the parallelisation map are in [`_0-index`](2026-10-09-v150-reports-research-workspaces_0-index.md). **Never read this file whole**: `/task-brief V150-7`.

All commands run inside the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v150-reports-research-workspaces`.

---

### Task V150-6: `ResearchStore`

**Model:** sonnet — a signal store with pure filter, sort and paging helpers, in one file.

**Files:**
- Create: `frontend/src/app/stores/research.store.ts`
- Create: `frontend/src/app/stores/research.store.spec.ts`

**Interfaces:**
- Consumes (V150-4): `LedgerRow`, `ResearchLedger`, `StrategyRow`, `ApiClient.researchLedger()`, `ApiClient.analyticsRegistry()`. Existing: `routeRequest`, `PageSpec`, `SortSpec`.
- Produces (V150-8 relies on these exact names):
  - `LEDGER_PAGE_SIZE = 25`
  - `interface LedgerFilters { verdicts: string[]; instrument: string; search: string }`
  - `filtersFromParams(params: ParamMap): LedgerFilters`, `filtersToParams(filters: LedgerFilters): Params` (query keys `verdict`, `instrument`, `q`)
  - `filterLedger(rows, filters, opts?)`, `sortLedger(rows, sort)`
  - `ResearchStore` with signals `data`, `loading`, `error`, `filters`, `sort`, `registry`, `verdicts`, `instruments`, `familySize`, `matching`, `verdictCounts`, `visible`, `pageSpec`, `selected`, `activeFilterCount`; methods `resolve(): Observable<void>`, `ensureLoaded(): Observable<void>`, `load()`, `hydrate(filters)`, `setSort(sort)`, `setPage(n)`, `select(id | null)`

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/stores/research.store.spec.ts`:

```ts
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
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd frontend && npm test -- --include src/app/stores/research.store.spec.ts --watch=false`
Expected: FAIL: cannot resolve `./research.store`.

- [ ] **Step 3: Write the store**

Create `frontend/src/app/stores/research.store.ts`:

```ts
import { computed, inject } from '@angular/core';
import { ParamMap, Params } from '@angular/router';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { Observable, forkJoin, of } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { LedgerRow, ResearchLedger, StrategyRow } from '../api/models';
import { routeRequest } from '../routing/route-request';
import { PageSpec, SortSpec } from '../ui/data-table/data-table.types';

export const LEDGER_PAGE_SIZE = 25;

/** What the toolbar can narrow by. All three live in the query string, so a
 *  filtered view is a link. An empty value means "no filter on this axis". */
export interface LedgerFilters {
  verdicts: string[];
  instrument: string;
  search: string;
}

const NO_FILTERS: LedgerFilters = { verdicts: [], instrument: '', search: '' };
const NEWEST_FIRST: SortSpec = { key: 'date', direction: 'desc' };

export function filtersFromParams(params: ParamMap): LedgerFilters {
  return {
    verdicts: (params.get('verdict') ?? '').split(',').filter((v) => v !== ''),
    instrument: params.get('instrument') ?? '',
    search: params.get('q') ?? '',
  };
}

/** Nulls, not empty strings: `queryParamsHandling: 'merge'` drops a null key,
 *  so a default never lingers in the URL. */
export function filtersToParams(filters: LedgerFilters): Params {
  return {
    verdict: filters.verdicts.length ? filters.verdicts.join(',') : null,
    instrument: filters.instrument || null,
    q: filters.search || null,
  };
}

function matchesSearch(row: LedgerRow, search: string): boolean {
  const needle = search.trim().toLowerCase();
  return needle === '' || row.id.toLowerCase().includes(needle)
    || row.hypothesis.toLowerCase().includes(needle);
}

/** `anyVerdict` skips the verdict axis: the chip counts need every row the
 *  OTHER filters allow, or selecting one verdict would zero the rest. */
export function filterLedger(
  rows: readonly LedgerRow[],
  filters: LedgerFilters,
  opts: { anyVerdict?: boolean } = {},
): LedgerRow[] {
  return rows.filter((row) =>
    (opts.anyVerdict || filters.verdicts.length === 0 || filters.verdicts.includes(row.verdict))
    && (filters.instrument === '' || row.instrument === filters.instrument)
    && matchesSearch(row, filters.search));
}

type SortValue = string | number | null;

/** A null figure is "not recorded", so it sorts last whichever way the
 *  column runs: it is not the smallest value and not the largest. */
export function sortLedger(rows: readonly LedgerRow[], sort: SortSpec): LedgerRow[] {
  const sign = sort.direction === 'asc' ? 1 : -1;
  const value = (row: LedgerRow) => (row as unknown as Record<string, SortValue>)[sort.key] ?? null;
  return [...rows].sort((a, b) => {
    const x = value(a);
    const y = value(b);
    if (x === null || y === null) return (x === null ? 1 : 0) - (y === null ? 1 : 0);
    if (x === y) return 0;
    return (x < y ? -1 : 1) * sign;
  });
}

interface ResearchData {
  ledger: ResearchLedger;
  registry: StrategyRow[];
}

interface ResearchSlice {
  data: ResearchData | null;
  loading: boolean;
  error: string | null;
  filters: LedgerFilters;
  sort: SortSpec;
  page: number;
  selectedId: string | null;
}

/**
 * The Research workspace's data: the pre-registration ledger and the
 * strategy registry, fetched together and never refetched on an event.
 *
 * Both change only when a commit lands and deploys, which cannot happen
 * while the page is open, so there is no event wiring. The ledger is small
 * (a few dozen rows), so filtering, sorting and paging all happen here.
 */
export const ResearchStore = signalStore(
  withState<ResearchSlice>({
    data: null,
    loading: false,
    error: null,
    filters: NO_FILTERS,
    sort: NEWEST_FIRST,
    page: 1,
    selectedId: null,
  }),
  withComputed(({ data, filters, sort }) => ({
    registry: computed<StrategyRow[]>(() => data()?.registry ?? []),
    verdicts: computed<string[]>(() => data()?.ledger.verdicts ?? []),
    instruments: computed<string[]>(() => data()?.ledger.instruments ?? []),
    /** How many ledger rows have a p-value: the BH family behind every q. */
    familySize: computed(() => data()?.ledger.q_family_m ?? 0),
    matching: computed<LedgerRow[]>(() =>
      sortLedger(filterLedger(data()?.ledger.rows ?? [], filters()), sort())),
    verdictCounts: computed<Record<string, number>>(() => {
      const pool = filterLedger(data()?.ledger.rows ?? [], filters(), { anyVerdict: true });
      const counts: Record<string, number> = {};
      for (const verdict of data()?.ledger.verdicts ?? []) counts[verdict] = 0;
      for (const row of pool) counts[row.verdict] = (counts[row.verdict] ?? 0) + 1;
      return counts;
    }),
    activeFilterCount: computed(() => {
      const f = filters();
      return (f.verdicts.length ? 1 : 0) + (f.instrument ? 1 : 0) + (f.search ? 1 : 0);
    }),
  })),
  withComputed(({ data, matching, page, selectedId }) => {
    const current = computed(() =>
      Math.min(page(), Math.max(1, Math.ceil(matching().length / LEDGER_PAGE_SIZE))));
    return {
      visible: computed<LedgerRow[]>(() => {
        const start = (current() - 1) * LEDGER_PAGE_SIZE;
        return matching().slice(start, start + LEDGER_PAGE_SIZE);
      }),
      // The count BEFORE slicing; `visible().length` would show one page forever.
      pageSpec: computed<PageSpec>(() => ({
        total: matching().length, page: current(), perPage: LEDGER_PAGE_SIZE,
      })),
      /** Looked up in the whole ledger, so a drawer survives a filter change. */
      selected: computed<LedgerRow | null>(() =>
        data()?.ledger.rows.find((row) => row.id === selectedId()) ?? null),
    };
  }),
  withMethods((store, api = inject(ApiClient)) => {
    const resolve = (): Observable<void> => routeRequest(
      forkJoin({ ledger: api.researchLedger(), registry: api.analyticsRegistry() }),
      {
        start: () => patchState(store, { loading: true }),
        next: ({ ledger, registry }) => patchState(store, {
          data: { ledger, registry: registry.registry }, loading: false, error: null,
        }),
        error: (error) => patchState(store, {
          loading: false,
          error: error.code === 'unavailable'
            ? 'The admin is not responding — the ledger is unavailable.'
            : error.message,
        }),
      },
    );
    return {
      resolve,
      /** For the route resolver. Every filter change is a navigation, and the
       *  resolver runs on each one; the ledger is fetched once per visit. */
      ensureLoaded(): Observable<void> { return store.data() ? of(undefined) : resolve(); },
      load(): void { resolve().subscribe({ error: () => undefined }); },
      /** Sets the filters from the URL. A filter change always returns to page 1. */
      hydrate(filters: LedgerFilters): void { patchState(store, { filters, page: 1 }); },
      setSort(sort: SortSpec): void { patchState(store, { sort, page: 1 }); },
      setPage(n: number): void { patchState(store, { page: Math.max(1, n) }); },
      select(id: string | null): void { patchState(store, { selectedId: id }); },
    };
  }),
);
```

- [ ] **Step 4: Run the spec and confirm it passes**

Run: `cd frontend && npm test -- --include src/app/stores/research.store.spec.ts --watch=false`
Expected: all tests pass.

If "keeps the last data and records the message when a reload fails" fails because the error message is not the server's, read `frontend/src/app/api/interceptors.ts` to see how `errorInterceptor` maps a 500 body to `ApiError.message`, and assert what it actually produces. The store's behaviour (keep `data`, set `error`) is what the test is for.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src/app/stores/research.store.ts frontend/src/app/stores/research.store.spec.ts
git commit -m "feat(v150): ResearchStore -- ledger and registry with URL filters, nulls-last sort and client paging"
```


---

### Task V150-7: `ReportsStore` and the two view models

**Model:** opus — statistical display rules (verdict of record vs latest reading, WAITING, the q marker, thin buckets) are decided here and nowhere else; a mistake presents a descriptive reading as a verdict.

**Blocked until** V150-5 is done.

**Files:**
- Create: `frontend/src/app/stores/reports.store.ts`
- Create: `frontend/src/app/stores/reports.store.spec.ts`

**Interfaces:**
- Consumes (V150-5): the report models, `ApiClient.reportExpectancyAttribution()`, `ApiClient.reportGateCounterfactual()`, the fixtures `ATTRIBUTION`, `GATES`, `ok`, `NOT_RUN`. Existing: `ChipTone` (`ui/chip.ts`), `BarRow` (`ui/bar-list.ts`), `routeRequest`.
- Produces (V150-9, V150-10, V150-11 rely on these exact names):
  - `type ReportTab = 'attribution' | 'gates'`; `tabFromParams(params: ParamMap): ReportTab`
  - `SCREEN_CANDIDATE_Q = 0.10`, `FLOOR_N_DISPLAY = 30`
  - `R_CAPTION`, `LATEST_HEADING`, `PORTFOLIO_NOTE`, `HOLDOUT_NOTE`, `OVER_CAP_NOTE` (string constants, exact text below)
  - `attributionView(result: ExpectancyAttribution): AttributionView`
  - `gatesView(result: GateCounterfactual): GateCellView[]`
  - interfaces `VerdictView`, `ReadingView`, `FactorView`, `DimensionView`, `SplitView`, `AttributionView`, `GateCellView`, `GateRowView`
  - `ReportsStore` with signals `tab`, `data` (the active tab's envelope), `loading`, `error`, `notRun`, `generatedAt`, `attribution` (`AttributionView | null`), `gates` (`GateCellView[] | null`); methods `resolveTab(tab): Observable<void>`, `load()`

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/stores/reports.store.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { convertToParamMap } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { ATTRIBUTION, GATES, NOT_RUN, ok } from '../testing/report-fixtures';
import {
  HOLDOUT_NOTE,
  PORTFOLIO_NOTE,
  ReportsStore,
  attributionView,
  gatesView,
  tabFromParams,
} from './reports.store';

/* The rules these tests pin are the quant panel's, and each one is a way the
 * page could mislead: a latest reading shown as the verdict, a verdict shown
 * below the floor, a thin bucket flagged as a candidate, two populations
 * blended into one figure. */

const ATTRIBUTION_URL = '/api/v1/reports/expectancy-attribution';
const GATES_URL = '/api/v1/reports/gate-counterfactual';

function create(): { store: InstanceType<typeof ReportsStore>; http: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      ReportsStore,
    ],
  });
  return { store: TestBed.inject(ReportsStore), http: TestBed.inject(HttpTestingController) };
}

describe('tabFromParams', () => {
  it('defaults to attribution, and for anything it does not know', () => {
    expect(tabFromParams(convertToParamMap({}))).toBe('attribution');
    expect(tabFromParams(convertToParamMap({ tab: 'nonsense' }))).toBe('attribution');
    expect(tabFromParams(convertToParamMap({ tab: 'gates' }))).toBe('gates');
  });
});

describe('attributionView', () => {
  const view = attributionView(ATTRIBUTION);

  it('takes THE verdict from the verdict of record, not from the latest reading', () => {
    // The fixture's latest reading says PREDICTIVE; the record says WEAK.
    expect(view.verdict).toEqual({ label: 'WEAK', tone: 'warn', date: '2026-10-12', n: 214, inverted: false });
  });

  it('keeps live and TRAIN as two readings, never one', () => {
    expect(view.readings.map((r) => [r.population, r.present, r.n])).toEqual([['Live', true, 214], ['TRAIN', true, 3120]]);
    expect(view.readings[0].spread).toBe(0.22);
    expect(view.readings[1].spread).toBe(0.04);
  });

  it('marks a factor as a screen candidate only below q 0.10', () => {
    const byKey = Object.fromEntries(view.factors.map((f) => [f.key, f.candidate]));
    expect(byKey).toEqual({ trend_alignment: true, volume_confirmation: false });
  });

  it('draws a thin bucket withheld, with its N, and never marks it', () => {
    const earnings = view.dimensions.find((d) => d.key === 'earnings_bucket')!;
    const thin = earnings.live!.find((b) => b.label === '0-5')!;
    expect(thin).toMatchObject({ withheld: true, n: 12 });
    // q is 0.01 in the fixture, well under the threshold, and it is thin.
    expect(earnings.candidates).toEqual([]);
  });

  it('marks a non-thin bucket below q 0.10, naming its population', () => {
    const regime = view.dimensions.find((d) => d.key === 'regime')!;
    expect(regime.candidates).toEqual(['bull (Live)']);
  });

  it('keeps the dimensions in the result order', () => {
    expect(view.dimensions.map((d) => d.key)).toEqual(['regime', 'earnings_bucket']);
  });

  it('lists the direction and horizon splits, each with both populations', () => {
    expect(view.splits.map((s) => `${s.axis}:${s.name}`)).toEqual([
      'Direction:long', 'Direction:short', 'Horizon:swing', 'Horizon:position']);
    expect(view.splits[1].live?.spread).toBe(-0.05);
    expect(view.splits[1].train?.n).toBe(620);
  });

  it('reads an absent population as not in this run, never as zeros', () => {
    const liveOnly = attributionView({ ...ATTRIBUTION, populations: { live: ATTRIBUTION.populations.live, train: null } });
    expect(liveOnly.readings[1]).toMatchObject({ population: 'TRAIN', present: false, n: null, spread: null });
    expect(liveOnly.dimensions[0].train).toBeNull();
    expect(liveOnly.factors[0].train).toBeNull();
  });

  it('notes "inverted" when a population reports it', () => {
    const live = ATTRIBUTION.populations.live!;
    const inverted = attributionView({
      ...ATTRIBUTION,
      verdict_of_record: { verdict: 'NOT PREDICTIVE', date: '2026-10-12', n: 214 },
      populations: { live: { ...live, monotonicity: { ...live.monotonicity, inverted: true } }, train: null },
    });
    expect(inverted.verdict).toMatchObject({ label: 'NOT PREDICTIVE', tone: 'neutral', inverted: true });
  });

  it('carries the looks count and the seed for the footer', () => {
    expect([view.looks, view.seed]).toEqual([37, 42]);
  });
});

describe('gatesView', () => {
  const cells = gatesView(GATES);
  const cell = (gate: string, population: string) => cells.find((c) => c.gate === gate && c.population === population)!;

  it('yields one view per cell, in the result order', () => {
    expect(cells.map((c) => c.id)).toEqual([
      'rs:live', 'rs:train', 'risk_cap:live', 'risk_cap:train', 'compression:live', 'compression:train']);
  });

  it('shows WAITING with its N and nothing else below the floor', () => {
    const waiting = cell('rs', 'Live');
    expect(waiting.state).toBe('waiting');
    expect(waiting.n).toBe(29);
    expect(waiting.verdict).toBeNull();
    // The fixture carries a latest reading for this cell; it must not surface.
    expect(waiting.latest).toBeNull();
    expect(waiting.labels).toEqual([]);
  });

  it('keeps the verdict of record apart from a different latest reading', () => {
    const riskCap = cell('risk_cap', 'Live');
    expect(riskCap.state).toBe('verdict');
    expect(riskCap.verdict).toMatchObject({ label: 'GATE EARNS', tone: 'good', date: '2026-10-14', n: 31 });
    expect(riskCap.latest).toEqual({ difference: -0.08, ciLow: -0.31, ciHigh: 0.12, q: 0.44 });
  });

  it('words a verdict as a historical measurement', () => {
    expect(cell('risk_cap', 'Live').verdict!.sentence)
      .toBe('Over these trades, the gate\u2019s blocked setups returned less than its taken ones.');
    expect(cell('compression', 'TRAIN').verdict!.sentence)
      .toBe('Over these trades, the gate\u2019s blocked setups returned more than its taken ones.');
  });

  it('puts the portfolio-state and holdout notes beside every live verdict', () => {
    expect(cell('risk_cap', 'Live').labels).toEqual([PORTFOLIO_NOTE, HOLDOUT_NOTE]);
    expect(cell('compression', 'Live').labels).toEqual([PORTFOLIO_NOTE, HOLDOUT_NOTE]);
    expect(cell('risk_cap', 'TRAIN').labels).toEqual([]);
  });

  it('labels TRAIN compression in-sample', () => {
    expect(cell('compression', 'TRAIN').labels).toEqual(['in-sample']);
  });

  it('shows a fixed note in place of a verdict where there is no population', () => {
    const rsTrain = cell('rs', 'TRAIN');
    expect(rsTrain.state).toBe('note');
    expect(rsTrain.note).toBe('no TRAIN population');
    expect(rsTrain.verdict).toBeNull();
  });

  it('attaches each cell its own gate x reason rows, with the over-cap figure', () => {
    const rows = cell('risk_cap', 'Live').rows;
    expect(rows.map((r) => r.reason)).toEqual(['risk_cap_exceeded']);
    expect(rows[0]).toMatchObject({ overCap: true, dollarRisk: 412.5, blockedN: 46 });
    expect(cell('risk_cap', 'TRAIN').rows).toEqual([]);
  });
});

describe('ReportsStore', () => {
  it('fetches only the active tab', () => {
    const { store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(ATTRIBUTION_URL).flush(ok(ATTRIBUTION));
    http.expectNone(GATES_URL);
    expect(store.tab()).toBe('attribution');
    expect(store.attribution()?.verdict.label).toBe('WEAK');
    expect(store.gates()).toBeNull();
    expect(store.generatedAt()).toBe('2026-10-20T21:30:00+00:00');
  });

  it('switches tab and fetches the other report', () => {
    const { store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(ATTRIBUTION_URL).flush(ok(ATTRIBUTION));
    store.resolveTab('gates').subscribe();
    http.expectOne(GATES_URL).flush(ok(GATES));
    expect(store.tab()).toBe('gates');
    expect(store.gates()?.length).toBe(6);
    expect(store.generatedAt()).toBe('2026-10-20T21:45:00+00:00');
  });

  it('reports not_run as a state, with no view and no error', () => {
    const { store, http } = create();
    store.resolveTab('gates').subscribe();
    http.expectOne(GATES_URL).flush(NOT_RUN);
    expect(store.notRun()).toBe(true);
    expect(store.gates()).toBeNull();
    expect(store.error()).toBeNull();
    expect(store.generatedAt()).toBeNull();
  });

  it('records a 500 as an error, not as not_run', () => {
    const { store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(ATTRIBUTION_URL).flush(
      { error: { code: 'report_unreadable', message: 'ValueError: Expecting value' } },
      { status: 500, statusText: 'Server Error' });
    expect(store.notRun()).toBe(false);
    expect(store.error()).toBeTruthy();
    expect(store.data()).toBeNull();
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd frontend && npm test -- --include src/app/stores/reports.store.spec.ts --watch=false`
Expected: FAIL: cannot resolve `./reports.store`.

- [ ] **Step 3: Write the store**

Create `frontend/src/app/stores/reports.store.ts`. If V150-5 renamed a wire field, the rename is applied in this file's two view functions and nowhere in a component:

```ts
import { computed, inject } from '@angular/core';
import { ParamMap } from '@angular/router';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { Observable } from 'rxjs';

import { ApiClient } from '../api/api-client';
import {
  AttributionBucket,
  AttributionMonotonicity,
  AttributionPopulation,
  ExpectancyAttribution,
  GateCell,
  GateCounterfactual,
  GateCounterfactualRow,
  ReportEnvelope,
} from '../api/models';
import { routeRequest } from '../routing/route-request';
import { BarRow } from '../ui/bar-list';
import { ChipTone } from '../ui/chip';

/* -- the fixed wording -------------------------------------------------- */

/** A factor or bucket is a Stage -2 screen CANDIDATE below this q. The page
 *  compares the q the server computed; it never computes one. */
export const SCREEN_CANDIDATE_Q = 0.10;
/** Display text only, for the "N 17 / 30" progress figure. Whether a cell is
 *  below the floor is v147's `WAITING` verdict, never a test against this. */
export const FLOOR_N_DISPLAY = 30;

export const R_CAPTION = 'R units, net of frictions as v146/v147 compute them, pre-tax.';
export const LATEST_HEADING = 'Latest reading \u2014 descriptive';
export const PORTFOLIO_NOTE = 'simulated as a lone trade; ignores heat and correlation caps';
export const HOLDOUT_NOTE = 'live window inside the 2026 holdout; a follow-on screen needs an unseen one';
export const OVER_CAP_NOTE = 'a trade the dollar-risk rule forbids; not a tradable alternative';
const IN_SAMPLE = 'in-sample';

export type ReportTab = 'attribution' | 'gates';

export function tabFromParams(params: ParamMap): ReportTab {
  return params.get('tab') === 'gates' ? 'gates' : 'attribution';
}

type PopulationKey = 'live' | 'train';
const POPULATIONS: readonly PopulationKey[] = ['live', 'train'];
const POPULATION_LABEL: Record<PopulationKey, 'Live' | 'TRAIN'> = { live: 'Live', train: 'TRAIN' };

/* -- expectancy attribution (v146) -------------------------------------- */

export interface VerdictView {
  label: string;
  tone: ChipTone;
  date: string;
  n: number;
  /** "inverted" is reported inside NOT PREDICTIVE, never as its own verdict. */
  inverted: boolean;
}

/** One population's monotonicity reading. `present: false` renders as "not
 *  in this run" and every figure is null: absent is never zero. */
export interface ReadingView {
  population: 'Live' | 'TRAIN';
  present: boolean;
  window: string | null;
  n: number | null;
  rho: number | null;
  spread: number | null;
  ciLow: number | null;
  ciHigh: number | null;
}

export interface DeltaView {
  n: number;
  delta: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  q: number | null;
}

export interface FactorView {
  key: string;
  live: DeltaView | null;
  train: DeltaView | null;
  candidate: boolean;
}

export interface DimensionView {
  key: string;
  label: string;
  /** Null when that population is absent from the run. */
  live: BarRow[] | null;
  train: BarRow[] | null;
  /** "<bucket> (<population>)" for each non-thin bucket below the q line. */
  candidates: string[];
}

export interface SplitView {
  axis: 'Direction' | 'Horizon';
  name: string;
  live: ReadingView | null;
  train: ReadingView | null;
}

export interface AttributionView {
  verdict: VerdictView;
  readings: ReadingView[];
  factors: FactorView[];
  dimensions: DimensionView[];
  splits: SplitView[];
  looks: number;
  seed: number;
}

const ATTRIBUTION_TONE: Record<string, ChipTone> = {
  PREDICTIVE: 'good',
  WEAK: 'warn',
  'NOT PREDICTIVE': 'neutral',
};

const DIMENSION_LABEL: Record<string, string> = {
  confidence_decile: 'Confidence decile',
  confidence_level: 'Confidence level',
  confluence: 'Confluence',
  regime: 'Regime',
  rs_quintile: 'RS quintile',
  earnings_bucket: 'Earnings proximity',
  earnings_in_hold: 'Earnings inside the hold',
  direction: 'Direction',
  horizon: 'Horizon',
};

const isCandidate = (q: number | null): boolean => q !== null && q < SCREEN_CANDIDATE_Q;

function reading(
  population: PopulationKey,
  mono: AttributionMonotonicity | null | undefined,
  window: string | null,
): ReadingView {
  const label = POPULATION_LABEL[population];
  if (!mono) {
    return { population: label, present: false, window: null, n: null, rho: null, spread: null, ciLow: null, ciHigh: null };
  }
  return {
    population: label, present: true, window, n: mono.n, rho: mono.spearman_rho,
    spread: mono.tercile_spread, ciLow: mono.ci_low, ciHigh: mono.ci_high,
  };
}

function factorViews(result: ExpectancyAttribution): FactorView[] {
  const side = (population: PopulationKey, key: string): DeltaView | null => {
    const factor = result.populations[population]?.factors.find((f) => f.key === key);
    return factor
      ? { n: factor.n, delta: factor.delta, ciLow: factor.ci_low, ciHigh: factor.ci_high, q: factor.q }
      : null;
  };
  const keys = new Set<string>();
  for (const population of POPULATIONS) {
    for (const factor of result.populations[population]?.factors ?? []) keys.add(factor.key);
  }
  return [...keys].map((key) => {
    const live = side('live', key);
    const train = side('train', key);
    return { key, live, train, candidate: isCandidate(live?.q ?? null) || isCandidate(train?.q ?? null) };
  });
}

const barRow = (bucket: AttributionBucket): BarRow => ({
  label: bucket.label, value: bucket.exp_r, n: bucket.n, withheld: bucket.thin,
});

function dimensionViews(result: ExpectancyAttribution): DimensionView[] {
  const source: AttributionPopulation | null = result.populations.live ?? result.populations.train;
  return Object.keys(source?.buckets ?? {}).map((key) => {
    const buckets = (population: PopulationKey) => result.populations[population]?.buckets[key] ?? null;
    const candidates: string[] = [];
    for (const population of POPULATIONS) {
      for (const bucket of buckets(population) ?? []) {
        // A thin bucket enters no marker, whatever its q says.
        if (!bucket.thin && isCandidate(bucket.q)) {
          candidates.push(`${bucket.label} (${POPULATION_LABEL[population]})`);
        }
      }
    }
    return {
      key,
      label: DIMENSION_LABEL[key] ?? key,
      live: buckets('live')?.map(barRow) ?? null,
      train: buckets('train')?.map(barRow) ?? null,
      candidates,
    };
  });
}

function splitViews(result: ExpectancyAttribution): SplitView[] {
  const axes: readonly ['direction' | 'horizon', 'Direction' | 'Horizon'][] = [
    ['direction', 'Direction'], ['horizon', 'Horizon'],
  ];
  const out: SplitView[] = [];
  for (const [key, axis] of axes) {
    const names = new Set<string>();
    for (const population of POPULATIONS) {
      for (const name of Object.keys(result.populations[population]?.splits[key] ?? {})) names.add(name);
    }
    for (const name of names) {
      const side = (population: PopulationKey): ReadingView | null => {
        const pop = result.populations[population];
        const mono = pop?.splits[key][name];
        return mono ? reading(population, mono, pop?.window ?? null) : null;
      };
      out.push({ axis, name, live: side('live'), train: side('train') });
    }
  }
  return out;
}

/** Everything the Expectancy-attribution tab draws. Pure, so the display
 *  rules are tested here once rather than through a template. */
export function attributionView(result: ExpectancyAttribution): AttributionView {
  const record = result.verdict_of_record;
  const inverted = POPULATIONS.some((p) => result.populations[p]?.monotonicity.inverted === true);
  return {
    verdict: {
      label: record.verdict,
      tone: ATTRIBUTION_TONE[record.verdict] ?? 'neutral',
      date: record.date,
      n: record.n,
      inverted,
    },
    readings: POPULATIONS.map((p) =>
      reading(p, result.populations[p]?.monotonicity, result.populations[p]?.window ?? null)),
    factors: factorViews(result),
    dimensions: dimensionViews(result),
    splits: splitViews(result),
    looks: result.looks,
    seed: result.seed,
  };
}

/* -- gate counterfactual (v147) ----------------------------------------- */

export interface GateVerdictView {
  label: string;
  tone: ChipTone;
  date: string;
  n: number;
  /** The verdict as a historical measurement, never an instruction. */
  sentence: string;
}

export interface GateLatestView {
  difference: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  q: number | null;
}

export interface GateRowView {
  reason: string;
  blockedN: number;
  noPlanN: number;
  fillRate: number | null;
  blockedExpR: number | null;
  blockedWinRate: number | null;
  takenExpR: number | null;
  takenWinRate: number | null;
  nearMissN: number | null;
  nearMissExpR: number | null;
  restN: number | null;
  restExpR: number | null;
  dollarRisk: number | null;
  overCap: boolean;
}

export interface GateCellView {
  /** `<gate>:<population>`, the table's row key. */
  id: string;
  gate: string;
  population: 'Live' | 'TRAIN';
  /** `verdict`: a verdict of record exists. `waiting`: below v147's floor.
   *  `note`: a fixed non-verdict state such as "no TRAIN population". */
  state: 'verdict' | 'waiting' | 'note';
  verdict: GateVerdictView | null;
  n: number;
  note: string | null;
  /** Null while waiting: a reading below the floor is not shown at all. */
  latest: GateLatestView | null;
  labels: string[];
  rows: GateRowView[];
}

const GATE_TONE: Record<string, ChipTone> = {
  'GATE EARNS': 'good',
  'GATE COSTS': 'warn',
  INCONCLUSIVE: 'neutral',
};

const GATE_SENTENCE: Record<string, string> = {
  'GATE EARNS': 'Over these trades, the gate\u2019s blocked setups returned less than its taken ones.',
  'GATE COSTS': 'Over these trades, the gate\u2019s blocked setups returned more than its taken ones.',
  INCONCLUSIVE: 'Over these trades, the difference between blocked and taken setups is not distinguishable from zero.',
};

const rowView = (row: GateCounterfactualRow): GateRowView => ({
  reason: row.reason,
  blockedN: row.blocked_n,
  noPlanN: row.no_plan_n,
  fillRate: row.fill_rate,
  blockedExpR: row.blocked_exp_r,
  blockedWinRate: row.blocked_win_rate,
  takenExpR: row.taken_exp_r,
  takenWinRate: row.taken_win_rate,
  nearMissN: row.near_miss_n,
  nearMissExpR: row.near_miss_exp_r,
  restN: row.rest_n,
  restExpR: row.rest_exp_r,
  dollarRisk: row.dollar_risk,
  overCap: row.over_cap,
});

function cellState(cell: GateCell): GateCellView['state'] {
  if (cell.note !== null) return 'note';
  return cell.verdict_of_record === null ? 'waiting' : 'verdict';
}

function cellLabels(cell: GateCell, state: GateCellView['state']): string[] {
  if (state !== 'verdict') return [];
  const labels: string[] = [];
  if (cell.in_sample) labels.push(IN_SAMPLE);
  if (cell.population === 'live') labels.push(PORTFOLIO_NOTE, HOLDOUT_NOTE);
  return labels;
}

function cellView(cell: GateCell, rows: readonly GateCounterfactualRow[]): GateCellView {
  const state = cellState(cell);
  const record = cell.verdict_of_record;
  return {
    id: `${cell.gate}:${cell.population}`,
    gate: cell.gate,
    population: POPULATION_LABEL[cell.population],
    state,
    verdict: state === 'verdict' && record ? {
      label: record.verdict,
      tone: GATE_TONE[record.verdict] ?? 'neutral',
      date: record.date,
      n: record.n,
      sentence: GATE_SENTENCE[record.verdict] ?? '',
    } : null,
    n: cell.n,
    note: cell.note,
    latest: state === 'verdict' && cell.latest ? {
      difference: cell.latest.difference, ciLow: cell.latest.ci_low,
      ciHigh: cell.latest.ci_high, q: cell.latest.q,
    } : null,
    labels: cellLabels(cell, state),
    rows: rows
      .filter((row) => row.gate === cell.gate && row.population === cell.population)
      .map(rowView),
  };
}

/** One view per verdict cell, in the report's order, each carrying its own
 *  gate x reason rows. */
export function gatesView(result: GateCounterfactual): GateCellView[] {
  return result.cells.map((cell) => cellView(cell, result.rows));
}

/* -- the store ---------------------------------------------------------- */

interface ReportsSlice {
  tab: ReportTab;
  attributionEnvelope: ReportEnvelope<ExpectancyAttribution> | null;
  gatesEnvelope: ReportEnvelope<GateCounterfactual> | null;
  loading: boolean;
  error: string | null;
}

/**
 * The Reports workspace's data: the latest v146 and v147 results.
 *
 * Each tab fetches only its own report, on navigation. There is no event
 * wiring: a result changes only when someone runs a report script on the VM.
 * Nothing here computes a figure; the two `*View` functions above only
 * rearrange what the report modules already decided.
 */
export const ReportsStore = signalStore(
  withState<ReportsSlice>({
    tab: 'attribution',
    attributionEnvelope: null,
    gatesEnvelope: null,
    loading: false,
    error: null,
  }),
  withComputed(({ tab, attributionEnvelope, gatesEnvelope }) => ({
    /** The active tab's envelope: what `asyncInputs` reads. */
    data: computed<ReportEnvelope<unknown> | null>(() =>
      tab() === 'gates' ? gatesEnvelope() : attributionEnvelope()),
    attribution: computed<AttributionView | null>(() => {
      const result = attributionEnvelope()?.result;
      return result ? attributionView(result) : null;
    }),
    gates: computed<GateCellView[] | null>(() => {
      const result = gatesEnvelope()?.result;
      return result ? gatesView(result) : null;
    }),
  })),
  withComputed(({ data }) => ({
    notRun: computed(() => data()?.status === 'not_run'),
    generatedAt: computed<string | null>(() => data()?.generated_at ?? null),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    const failed = (message: string, code: string | number) => patchState(store, {
      loading: false,
      error: code === 'unavailable'
        ? 'The admin is not responding \u2014 the report is unavailable.'
        : message,
    });
    const resolveTab = (tab: ReportTab): Observable<void> => {
      patchState(store, { tab });
      if (tab === 'gates') {
        return routeRequest(api.reportGateCounterfactual(), {
          start: () => patchState(store, { loading: true }),
          next: (gatesEnvelope) => patchState(store, { gatesEnvelope, loading: false, error: null }),
          error: (error) => failed(error.message, error.code),
        });
      }
      return routeRequest(api.reportExpectancyAttribution(), {
        start: () => patchState(store, { loading: true }),
        next: (attributionEnvelope) => patchState(store, { attributionEnvelope, loading: false, error: null }),
        error: (error) => failed(error.message, error.code),
      });
    };
    return {
      resolveTab,
      load(): void { resolveTab(store.tab()).subscribe({ error: () => undefined }); },
    };
  }),
);
```

- [ ] **Step 4: Run the spec and confirm it passes**

Run: `cd frontend && npm test -- --include src/app/stores/reports.store.spec.ts --watch=false`
Expected: all tests pass.

If V150-5 dropped the `note` field (v147 does not persist the two non-verdict states), replace `cellState`'s first line with a derivation and keep the spec's expectations: `rs` × `train` → `'no TRAIN population'`; gate `no_qualifying_target` → `'no verdict \u2014 no-plan'`. Put the derivation in one helper, `cellNote(cell): string | null`, and set `note: cellNote(cell)` in `cellView`.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src/app/stores/reports.store.ts frontend/src/app/stores/reports.store.spec.ts
git commit -m "feat(v150): ReportsStore -- per-tab fetch and the attribution and gate view models"
```
