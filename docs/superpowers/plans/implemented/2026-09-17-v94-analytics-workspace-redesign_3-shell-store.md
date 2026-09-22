# Analytics Workspace Redesign (v94) — Part 3: Models, API client, store, URL sync, shell

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Header, constraints and prerequisite in `_0-index.md`. **Spec:** `docs/superpowers/specs/2026-09-17-v94-analytics-workspace-redesign-design.md` §3.2, §3.3, §3.12.

# Phase 3 — The scope reaches the page

## Parallelisation (this phase)

**Sequential throughout.** S1 defines the types S2 sends and S4 stores; S3's formatter is consumed by S4's computeds and every tab; S4 owns the state S5 syncs and S6 renders. No two tasks here touch disjoint files with no contract dependency.

## Exit criteria

`?from=2026-08-01&ledger=both&strategy=MACD&unit=money&tab=execution` round-trips through the URL, reaches every request, and renders in the bar; old `?tab=performance|strategies|calibration|plans` links land on their new tabs; `cd frontend && npm test -- --include src/app/stores/analytics.store.spec.ts` green.

---

### Task S1: `models.ts` — scope types, payload updates, `analyticsUnit` preference

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`AnalyticsPerformance` L442–466, `AnalyticsEquityCurve` L416–420, `AnalyticsByDimensionRow` L426–440, `AnalyticsStrategies` L522–525, `AnalyticsCalibration` L527–532, `AnalyticsExitQuality` L534–543, `AnalyticsPlans` L545, `AnalyticsJournal` L514–520, `Preferences` L1115–1137)

**Interfaces:**
- Produces:
  ```ts
  export type LedgerScope = 'main' | 'weak' | 'both';
  export type AnalyticsUnit = 'r' | 'pct' | 'money';
  export interface BookScope { from: string | null; to: string | null; ledger: LedgerScope;
                               strategy: string | null; horizon: string | null; direction: string | null }
  export interface Scoped { scope: BookScope; n: number }
  export interface AnalyticsHeatGrid { rows: string[]; cols: string[];
    cells: { r: number; c: number; n: number; exp_r: number | null; win_rate: number | null }[];
    folded: { n_strategies: number; cells: { c: number; n: number; exp_r: number | null; win_rate: number | null }[] };
    min_cell_n: number; scope: BookScope; n: number }
  ```
  plus `Preferences.analyticsUnit?: AnalyticsUnit` and `Preferences.analyticsScope?: Partial<BookScope>` (the scope a fresh visit restores).
- Consumes: Part 1's payloads (B2–B9).

- [ ] **Step 1: Write the types** — add near the other analytics models:

```ts
/** The one scope every analytics request sends and every scoped payload
 *  echoes (spec v94 D2/D5/H2). `ledger` follows v93's main/weak split. */
export type LedgerScope = 'main' | 'weak' | 'both';

export interface BookScope {
  from: string | null;
  to: string | null;
  ledger: LedgerScope;
  strategy: string | null;
  horizon: string | null;
  direction: string | null;
}

/** Mixed into every scoped payload: the scope the server actually applied
 *  and the closed-trade count it produced. A panel renders `n` beside its
 *  title so no figure is read against an unknown population. */
export interface Scoped {
  scope: BookScope;
  n: number;
}

/** The headline unit. The currency figure is rendered alongside whichever
 *  unit is chosen, never hidden behind the toggle (spec v94 D3). */
export type AnalyticsUnit = 'r' | 'pct' | 'money';
```

- [ ] **Step 2: Update each payload interface**

- `AnalyticsPerformance extends Scoped`: drop the two "All-time, NOT scoped" doc comments (B2 made them scoped — replace with `/** Scoped by the control bar (v94 D5). */`), add `rolling_wr: { date: string; win_rate: number }[]; rolling_exp_r: { date: string; exp_r: number }[];` and (from v93) keep `weak`.
- `AnalyticsEquityCurve extends Scoped`: `points: EquityCurvePoint[]` where `EquityCurvePoint` gains `cum_pnl: number; cum_pct: number | null;`; rename `n` → `points_n` (B3 renamed it) and add `benchmark: { spy_indexed: { date: string; pct: number }[] };`.
- `AnalyticsByDimensionRow`: add `wins: number; losses: number; avg_win_r: number | null; avg_loss_r: number | null; total_pnl: number;` and keep optional `badge?: string; soak?: unknown;`. `AnalyticsByDimension extends Scoped` and gains `min_cell_n: number`.
- `AnalyticsStrategies extends Scoped`: replace `heatmap` with `registry_scope: 'all-time'; contribution: { strategy: string; total_r: number | null; n: number }[]; cumulative: Record<string, { date: string; cum_r: number }[]>;`.
- `AnalyticsExitQuality extends Scoped` (keeps its keys), `AnalyticsJournal extends Scoped`.
- `AnalyticsCalibration` and `AnalyticsPlans`: add `scope: 'all-time';`.
- Add `AnalyticsHeatGrid` as specified in **Interfaces**.
- `Preferences`: add

```ts
  /** v94 D3 — the headline unit for the Analytics workspace. The currency
   *  figure is always rendered too, so this never hides money. */
  analyticsUnit?: AnalyticsUnit;
  /** v94 D2 — the scope a fresh visit restores when the URL carries none. */
  analyticsScope?: Partial<BookScope>;
```

- [ ] **Step 3: Verify** — `cd frontend && npx tsc --noEmit -p tsconfig.json` (or `npm run build`) reports errors **only** in `analytics.store.ts`, `analytics.ts`, `api-client.ts` and their specs. Those are S2/S4/S6's work. Note the list; do not fix them here.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/api/models.ts
git commit -m "feat(v94): scope, unit and heat-grid types; scoped analytics payload shapes"
```

---

### Task S2: `api-client.ts` — `scopeParams`, every analytics method takes a scope

**Files:**
- Modify: `frontend/src/app/api/api-client.ts` (analytics block L199–268)
- Modify: `frontend/src/app/api/api-client.spec.ts` (if it pins analytics URLs — `grep -n "analytics" frontend/src/app/api/api-client.spec.ts`)

**Interfaces:**
- Consumes: S1's `BookScope`, `AnalyticsHeatGrid`.
- Produces:
  ```ts
  export function scopeParams(scope: Partial<BookScope> | null | undefined, extra?: Record<string, string>): HttpParams
  // methods, each taking `scope?: Partial<BookScope> | null`:
  analyticsPerformance(scope?) analyticsEquityCurve(scope?) analyticsJournal(scope?, lessons?)
  analyticsExitQuality(scope?) analyticsStrategies(scope?)
  analyticsByDimension(dim: string, scope?)  analyticsHeatGrid(scope?)
  analyticsCalibration() analyticsPlans() analyticsRegistry()   // unchanged, all-time
  ```
  `analyticsSnapshot()` **stays** (the Dashboard store and `trade-detail.store.ts` use the client too) but the Analytics workspace no longer calls it.

- [ ] **Step 1: Failing spec** — append to `api-client.spec.ts` (mirror the file's existing setup: `provideHttpClient`, `provideHttpClientTesting`, `TestBed.inject(ApiClient)`, `HttpTestingController`):

```ts
  it('sends only the set scope fields, and never an empty value', () => {
    const api = TestBed.inject(ApiClient);
    api.analyticsPerformance({ from: '2026-08-01', to: null, ledger: 'both', strategy: 'MACD',
                               horizon: null, direction: null }).subscribe();
    const req = TestBed.inject(HttpTestingController)
      .expectOne((r) => r.url.endsWith('/analytics/performance'));
    expect(req.request.params.get('from')).toBe('2026-08-01');
    expect(req.request.params.get('ledger')).toBe('both');
    expect(req.request.params.get('strategy')).toBe('MACD');
    expect(req.request.params.has('to')).toBe(false);
    expect(req.request.params.has('direction')).toBe(false);
  });

  it('by-dimension and heat-grid carry the same scope', () => {
    const api = TestBed.inject(ApiClient);
    const http = TestBed.inject(HttpTestingController);
    api.analyticsByDimension('horizon', { direction: 'bearish' }).subscribe();
    const a = http.expectOne((r) => r.url.endsWith('/analytics/by-dimension'));
    expect(a.request.params.get('dim')).toBe('horizon');
    expect(a.request.params.get('direction')).toBe('bearish');
    api.analyticsHeatGrid({ direction: 'bearish' }).subscribe();
    expect(http.expectOne((r) => r.url.endsWith('/analytics/heat-grid'))
      .request.params.get('direction')).toBe('bearish');
  });
```

Run: `cd frontend && npm test -- --include src/app/api/api-client.spec.ts` → FAIL.

- [ ] **Step 2: Implement** — replace the analytics block's per-method param building with one helper above the class (or as a module function in the same file):

```ts
/**
 * The scope as query parameters (spec v94 D2/D5). An unset field is OMITTED
 * rather than sent empty: the server distinguishes "unbounded" from `''`,
 * and an empty `strategy=` would 400 nothing but would still make two
 * identical scopes produce two different cache keys.
 */
export function scopeParams(scope?: Partial<BookScope> | null, extra?: Record<string, string>): HttpParams {
  let params = new HttpParams();
  for (const [key, value] of Object.entries(extra ?? {})) params = params.set(key, value);
  if (!scope) return params;
  const map: [keyof BookScope, string][] = [
    ['from', 'from'], ['to', 'to'], ['ledger', 'ledger'],
    ['strategy', 'strategy'], ['horizon', 'horizon'], ['direction', 'direction'],
  ];
  for (const [field, name] of map) {
    const value = scope[field];
    if (value) params = params.set(name, String(value));
  }
  return params;
}
```

Then each method becomes, e.g.:

```ts
  /** v94 D5 — every analytics figure comes from the one BookScope. */
  analyticsPerformance(scope?: Partial<BookScope> | null): Observable<AnalyticsPerformance> {
    return this.http.get<AnalyticsPerformance>(`${this.base}/analytics/performance`, { params: scopeParams(scope) });
  }

  analyticsByDimension(dim: string, scope?: Partial<BookScope> | null): Observable<AnalyticsByDimension> {
    return this.http.get<AnalyticsByDimension>(`${this.base}/analytics/by-dimension`, { params: scopeParams(scope, { dim }) });
  }

  /** v94 D7 — strategies x horizons, thin rows folded server-side. */
  analyticsHeatGrid(scope?: Partial<BookScope> | null): Observable<AnalyticsHeatGrid> {
    return this.http.get<AnalyticsHeatGrid>(`${this.base}/analytics/heat-grid`, { params: scopeParams(scope) });
  }

  analyticsJournal(scope?: Partial<BookScope> | null, lessons?: number): Observable<AnalyticsJournal> {
    return this.http.get<AnalyticsJournal>(`${this.base}/analytics/journal`,
      { params: scopeParams(scope, lessons ? { lessons: String(lessons) } : undefined) });
  }
```

`analyticsEquityCurve`, `analyticsExitQuality`, `analyticsStrategies` follow the first shape. Delete `analyticsEquityCurve`'s separate `strategy` argument — the scope carries it now. Leave `analyticsCalibration`, `analyticsPlans`, `analyticsRegistry`, `analyticsSnapshot` untouched.

- [ ] **Step 3: Verify** — `npm test -- --include src/app/api/api-client.spec.ts` → PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/api/api-client.ts frontend/src/app/api/api-client.spec.ts
git commit -m "feat(v94): one scopeParams helper; every analytics request carries the BookScope"
```

---

### Task S3: `unit-format.ts` — `inUnit`, `unitLabel`

**Files:**
- Create: `frontend/src/app/ui/unit-format.ts`, `frontend/src/app/ui/unit-format.spec.ts`

**Interfaces:**
- Consumes: `format.ts`'s `rMultiple`, `pct`, `money`, `ABSENT`.
- Produces:
  ```ts
  export interface UnitValues { r: number | null; pct: number | null; money: number | null }
  export function inUnit(values: UnitValues, unit: AnalyticsUnit, currency: string): string   // the headline
  export function unitLabel(unit: AnalyticsUnit): string                                      // 'R' | '%' | currency
  export function alwaysMoney(values: UnitValues, currency: string): string | null            // the second line (D3)
  ```
  `alwaysMoney` returns `null` **only** when `money` is null; when the headline unit *is* money it still returns the string, and callers suppress the duplicate line themselves.

- [ ] **Step 1: Failing spec**

```ts
import { describe, expect, it } from 'vitest';

import { alwaysMoney, inUnit, unitLabel } from './unit-format';

describe('unit-format', () => {
  const values = { r: 1.25, pct: 3.4, money: 1240 };

  it('formats the headline in the chosen unit', () => {
    expect(inUnit(values, 'r', '$')).toBe('+1.25R');
    expect(inUnit(values, 'pct', '$')).toBe('+3.40%');
    expect(inUnit(values, 'money', '$')).toBe('+1,240.00 $');
  });

  it('falls back to an em dash for a missing figure, never a zero', () => {
    expect(inUnit({ r: null, pct: null, money: null }, 'r', '$')).toBe('—');
  });

  it('always offers the money line, whatever the unit', () => {
    expect(alwaysMoney(values, '$')).toBe('+1,240.00 $');
    expect(alwaysMoney({ r: 1, pct: 1, money: null }, '$')).toBeNull();
  });

  it('labels the unit', () => {
    expect(unitLabel('r')).toBe('R');
    expect(unitLabel('pct')).toBe('%');
    expect(unitLabel('money')).toBe('$');       // caller passes the currency through
  });
});
```

(If `unitLabel('money')` needs the currency, give it the signature `unitLabel(unit, currency = '$')` and assert that.)

- [ ] **Step 2: Implement**

```ts
import { AnalyticsUnit } from '../api/models';
import { ABSENT, money, pct, rMultiple } from './format';

/** The same quantity in all three units. A panel computes these once; the
 *  toggle picks the headline and the money line is rendered regardless
 *  (spec v94 D3: the amount of money is always visible). */
export interface UnitValues { r: number | null; pct: number | null; money: number | null; }

export function inUnit(values: UnitValues, unit: AnalyticsUnit, currency: string): string {
  if (unit === 'r') return rMultiple(values.r);
  if (unit === 'pct') return pct(values.pct);
  return money(values.money, currency);
}

/** The second line of every KPI tile and every hover readout. Null only when
 *  the currency figure genuinely does not exist -- never to hide it. */
export function alwaysMoney(values: UnitValues, currency: string): string | null {
  return values.money === null || values.money === undefined ? null : money(values.money, currency);
}

export function unitLabel(unit: AnalyticsUnit, currency = '$'): string {
  return unit === 'r' ? 'R' : unit === 'pct' ? '%' : currency;
}

export { ABSENT };
```

- [ ] **Step 3: Verify** — `npm test -- --include src/app/ui/unit-format.spec.ts` → PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/ui/unit-format.ts frontend/src/app/ui/unit-format.spec.ts
git commit -m "feat(v94): unit formatter -- headline in R/%/money, the money line always present"
```

---

### Task S4: `analytics.store.ts` — scope, unit, measure, per-tab loaders

**Files:**
- Modify: `frontend/src/app/stores/analytics.store.ts` (`AnalyticsTab`/`ANALYTICS_TABS` L260–269, `BREAKDOWN_DIMENSIONS` L313–324, `AnalyticsSlice` L509+, `withState` L628–660, `withComputed` L662+, `withMethods` L1047+, resolvers L1251–1316, returned API L1344+)
- Modify: `frontend/src/app/stores/analytics.store.spec.ts`

**Interfaces:**
- Consumes: S1 types, S2 client methods, S3 formatter.
- Produces (the surface every tab in Part 4 binds to):
  ```ts
  export type AnalyticsTab = 'overview' | 'attribution' | 'execution' | 'edge' | 'pipeline' | 'tuning';
  export const ANALYTICS_TABS: readonly AnalyticsTab[];
  export const BREAKDOWN_DIMENSIONS: readonly { value: string; label: string }[];   // + ledger, strategy, confidence
  export const DEFAULT_SCOPE: BookScope;
  export const RANGE_PRESETS: readonly { value: string; label: string; days: number | null }[];
  export function presetRange(preset: string, today: Date): { from: string | null; to: string | null };
  export type PanelKey = 'performance' | 'equityCurve' | 'byDimension' | 'heatGrid' | 'exitQuality'
                       | 'journal' | 'strategies' | 'calibration' | 'plans';
  // state signals
  scope() unit() measure() heatCell() breakdown() tableOpen()
  // data signals (per endpoint, each with its own error signal)
  performance() performanceError() equityCurve() equityCurveError() byDimension() byDimensionError()
  heatGrid() heatGridError() exitQuality() exitQualityError() journal() journalError()
  strategies() strategiesError() calibration() calibrationError() plans() plansError()
  // derived
  scopeN() asOf() activeFilterCount() allTimePanelCount()
  // methods
  setTab(tab, loadNow?) setScope(patch: Partial<BookScope>) clearScope() setUnit(u) setMeasure(m)
  setHeatCell(c) setBreakdown(d) setTableOpen(panel, open) hydrate(scope, unit) resolveTab(tab)
  load() reload(panel: PanelKey)
  ```
  `hydrate(scope, unit)` is `patchState(store, { scope, unit })` with **no fetch** — S5's route resolver calls it before `resolveTab`, which does the fetching. `asOf()` is
  `computed(() => equityCurve()?.as_of ?? byDimension()?.as_of ?? null)`.

- [ ] **Step 1: Failing spec** — append to `analytics.store.spec.ts` (reuse its `beforeEach`; it already provides `EventStream`, interceptors and `AnalyticsStore`):

```ts
  it('sends one scope to every Overview request and reports its N', () => {
    store.setTab('overview', false);
    store.setScope({ from: '2026-08-01', ledger: 'both', strategy: 'MACD' });
    const perf = backend.expectOne((r) => r.url.endsWith('/analytics/performance'));
    expect(perf.request.params.get('from')).toBe('2026-08-01');
    expect(perf.request.params.get('ledger')).toBe('both');
    perf.flush({ ...PERFORMANCE, scope: { from: '2026-08-01', to: null, ledger: 'both',
      strategy: 'MACD', horizon: null, direction: null }, n: 312, rolling_wr: [], rolling_exp_r: [] });
    const curve = backend.expectOne((r) => r.url.endsWith('/analytics/equity-curve'));
    expect(curve.request.params.get('strategy')).toBe('MACD');
    expect(store.scopeN()).toBe(312);
    expect(store.activeFilterCount()).toBe(3);
  });

  it('keeps a failed panel error out of its neighbours', () => {
    store.setTab('execution', false);
    store.load();
    backend.expectOne((r) => r.url.endsWith('/analytics/exit-quality'))
      .flush({ message: 'boom' }, { status: 500, statusText: 'Server Error' });
    backend.expectOne((r) => r.url.endsWith('/analytics/journal'))
      .flush({ digest: ['ok'], lessons: [], entries_n: 1, scope: {}, n: 1 });
    expect(store.exitQualityError()).not.toBeNull();
    expect(store.journalError()).toBeNull();
    expect(store.digest()).toEqual(['ok']);
  });

  it('carries the unit and offers ledger as a breakdown dimension', () => {
    expect(store.unit()).toBe('r');
    store.setUnit('money');
    expect(store.unit()).toBe('money');
    expect(BREAKDOWN_DIMENSIONS.map((d) => d.value)).toContain('ledger');
    expect(BREAKDOWN_DIMENSIONS.map((d) => d.value)).toContain('strategy');
  });
```

Add `presetRange` unit assertions in the same file:

```ts
  it('presetRange counts back from today, inclusive', () => {
    expect(presetRange('30d', new Date('2026-09-17T12:00:00Z')))
      .toEqual({ from: '2026-08-19', to: '2026-09-17' });
    expect(presetRange('all', new Date('2026-09-17T12:00:00Z'))).toEqual({ from: null, to: null });
  });
```

Run: `npm test -- --include src/app/stores/analytics.store.spec.ts` → FAIL.

- [ ] **Step 2: Rewrite the tab vocabulary and dimensions**

```ts
/** The six questions, in the order a trader asks them (spec v94 D1).
 *  Calibration folded into Edge; Performance split into Overview,
 *  Attribution and Execution. */
export type AnalyticsTab = 'overview' | 'attribution' | 'execution' | 'edge' | 'pipeline' | 'tuning';

export const ANALYTICS_TABS: readonly AnalyticsTab[] =
  ['overview', 'attribution', 'execution', 'edge', 'pipeline', 'tuning'] as const;

/** Old `?tab=` values keep working (spec D1). */
export const LEGACY_TABS: Record<string, AnalyticsTab> = {
  performance: 'overview', strategies: 'edge', calibration: 'edge', plans: 'pipeline', tuning: 'tuning',
};

/** Every dimension `aggregate.DIMENSIONS` serves, including v93's ledger.
 *  `tier` stays retired -- it would 400. */
export const BREAKDOWN_DIMENSIONS = [
  { value: 'strategy', label: 'Strategy' },
  { value: 'horizon', label: 'Horizon' },
  { value: 'direction', label: 'Direction' },
  { value: 'dow', label: 'Day of week' },
  { value: 'month', label: 'Month' },
  { value: 'badge', label: 'Badge' },
  { value: 'confidence', label: 'Confidence' },
  { value: 'source', label: 'Source' },
  { value: 'ledger', label: 'Ledger' },
  { value: 'ticker', label: 'Ticker' },
] as const;

export const DEFAULT_SCOPE: BookScope = {
  from: null, to: null, ledger: 'main', strategy: null, horizon: null, direction: null,
};

export const RANGE_PRESETS = [
  { value: '30d', label: 'Last 30 days', days: 30 },
  { value: '90d', label: 'Last 90 days', days: 90 },
  { value: 'ytd', label: 'Year to date', days: null },
  { value: 'all', label: 'All time', days: null },
] as const;

const iso = (d: Date): string => d.toISOString().slice(0, 10);

export function presetRange(preset: string, today: Date): { from: string | null; to: string | null } {
  if (preset === 'all') return { from: null, to: null };
  if (preset === 'ytd') return { from: `${today.getUTCFullYear()}-01-01`, to: iso(today) };
  const days = RANGE_PRESETS.find((p) => p.value === preset)?.days;
  if (!days) return { from: null, to: null };
  const from = new Date(today);
  from.setUTCDate(from.getUTCDate() - (days - 1));
  return { from: iso(from), to: iso(today) };
}
```

- [ ] **Step 3: Replace the slice**

Delete `rangeFrom`, `rangeTo`, `equityCurveStrategy`, `equityCurveView`, `snapshot`, `snapshotError`, `strategyAgg`, `horizonAgg`, `riskMetrics`. Add:

```ts
  scope: BookScope;
  unit: AnalyticsUnit;
  measure: 'exp_r' | 'total_r' | 'win_rate';
  heatCell: 'exp_r' | 'win_rate' | 'n';
  breakdown: string;
  tableOpen: Record<string, boolean>;
  performance: AnalyticsPerformance | null;   performanceError: string | null;
  equityCurve: AnalyticsEquityCurve | null;   equityCurveError: string | null;
  byDimension: AnalyticsByDimension | null;   byDimensionError: string | null;
  heatGrid: AnalyticsHeatGrid | null;         heatGridError: string | null;
  exitQuality: AnalyticsExitQuality | null;   exitQualityError: string | null;
  journal: AnalyticsJournal | null;           journalError: string | null;
  strategies: AnalyticsStrategies | null;     strategiesError: string | null;
  calibration: AnalyticsCalibration | null;   calibrationError: string | null;
  plans: AnalyticsPlans | null;               plansError: string | null;
```

(Tuning state — `jobs`, `job`, `proposals`, `grid`, `gridStrategy`, `launching`, `launchError`, `proposing`, `proposeError`, `proposeResult` — stays **exactly** as it is.)

Initial state: `scope: DEFAULT_SCOPE, unit: 'r', measure: 'exp_r', heatCell: 'exp_r', breakdown: 'strategy', tableOpen: {}`, every payload `null`, every error `null`.

- [ ] **Step 4: One error handler per panel**

```ts
    /** Every panel fails on its own terms (spec v94 H4). A failed fetch sets
     *  THAT panel's error and leaves its neighbours' data untouched -- the
     *  three silent-degradation paths v94 exists to remove are the ones that
     *  had no error field at all. */
    const panelFail = (key: keyof AnalyticsSlice) => (error: ApiError): void =>
      patchState(store, { [key]: error.code === 'unavailable' ? 'The admin is not responding.' : error.message } as never);

    const fetch = <T>(source: Observable<T>, dataKey: string, errorKey: string): void => {
      source.subscribe({
        next: (value) => patchState(store, { [dataKey]: value, [errorKey]: null } as never),
        error: panelFail(errorKey as keyof AnalyticsSlice),
      });
    };
```

- [ ] **Step 5: Per-tab loaders** — replace `loadPerformance`/`loadStrategies`/`loadCalibration`/`loadPlans` (keep `loadTuning`, `loadJob`, `loadProposals`, `loadGrid` unchanged):

```ts
    const s = () => store.scope();

    const loadOverview = (): void => {
      fetch(api.analyticsPerformance(s()), 'performance', 'performanceError');
      fetch(api.analyticsEquityCurve(s()), 'equityCurve', 'equityCurveError');
    };
    const loadAttribution = (): void => {
      fetch(api.analyticsByDimension(store.breakdown(), s()), 'byDimension', 'byDimensionError');
      fetch(api.analyticsHeatGrid(s()), 'heatGrid', 'heatGridError');
      fetch(api.analyticsStrategies(s()), 'strategies', 'strategiesError');
      fetch(api.analyticsPerformance(s()), 'performance', 'performanceError');   // horizon/dow/month bars + N
    };
    const loadExecution = (): void => {
      fetch(api.analyticsExitQuality(s()), 'exitQuality', 'exitQualityError');
      fetch(api.analyticsJournal(s()), 'journal', 'journalError');
      fetch(api.analyticsPerformance(s()), 'performance', 'performanceError');   // holding period, R:R
    };
    const loadEdge = (): void => {
      fetch(api.analyticsPerformance(s()), 'performance', 'performanceError');   // rolling_wr, rolling_exp_r
      fetch(api.analyticsStrategies(s()), 'strategies', 'strategiesError');
      fetch(api.analyticsCalibration(), 'calibration', 'calibrationError');
    };
    const loadPipeline = (): void => fetch(api.analyticsPlans(), 'plans', 'plansError');

    const LOADERS: Record<AnalyticsTab, () => void> = {
      overview: loadOverview, attribution: loadAttribution, execution: loadExecution,
      edge: loadEdge, pipeline: loadPipeline, tuning: loadTuning,
    };
    const load = (): void => LOADERS[store.tab()]();
```

`resolveTab` keeps its `routeRequest` shape; make each tab's resolver wrap its **first** request (so the route still waits on one payload) and fire the rest in `start:`. For `tuning` keep the existing resolver verbatim.

- [ ] **Step 6: Derived signals**

```ts
    scopeN: computed(() => performance()?.n ?? byDimension()?.n ?? exitQuality()?.n ?? null),
    activeFilterCount: computed(() => {
      const sc = scope();
      return (['from', 'to', 'strategy', 'horizon', 'direction'] as const).filter((k) => sc[k]).length
        + (sc.ledger === DEFAULT_SCOPE.ledger ? 0 : 1);
    }),
    /** How many panels on the open tab ignore the bar (spec v94 D2/H2). */
    allTimePanelCount: computed(() => (tab() === 'edge' ? 3 : tab() === 'pipeline' ? 4 : 0)),
```

Keep every existing computed whose source survives (`digest`, `lessons`, `streaks`, `returnsHistogram`, `rHistogram`, `holdingPeriodBars`, `riskRewardBars`, `monthBars`, `byConfidence`, `deciles`, `tiers`, `drift`, `funnelChart`, `badgeChart`, `tierChart`, `fillRatePct`, `medianDaysToFill`, `inFlight`, `jobActive`, `pastJobs`, `decileHistogram`), **re-pointed** from `snapshot()` to `performance()`/`byDimension()` where they read the snapshot. Delete `snapshotBuiltAt`, `profitFactor*`, `sharpe`, `sortino`, `maxDrawdownPct`, `totalPnl`, `totalR*`, `rPerMonth`, `sharpeR*`, `maxDrawdownR*`, `winLossSlices`, `directionBars`, `dowBars`, `breakdownRows`, `strategyContribution`, `relocated`, `missingRelocated`, `derivedMetrics`, `appliedRange`, `rangeActive`, `rangeSampleSize`, `heatmap`, `strategyNames` — Part 4's tabs derive what they need from the new payloads, and `kpiTiles` moves into the Overview component.

- [ ] **Step 7: Methods**

```ts
      setScope(patch: Partial<BookScope>): void {
        const next = { ...store.scope(), ...patch };
        if (next.from && next.to && next.from > next.to) { const f = next.from; next.from = next.to; next.to = f; }
        patchState(store, { scope: next });
        preferences.update((prefs) => ({ ...prefs, analyticsScope: next }));
        load();
      },
      clearScope(): void { patchState(store, { scope: DEFAULT_SCOPE }); load(); },
      setUnit(unit: AnalyticsUnit): void {
        patchState(store, { unit });
        preferences.update((prefs) => ({ ...prefs, analyticsUnit: unit }));   // no refetch: every unit is in the payload
      },
      setMeasure(measure: 'exp_r' | 'total_r' | 'win_rate'): void {
        patchState(store, { measure });
        preferences.update((prefs) => ({ ...prefs, analyticsMeasure: measure as never }));
      },
      setHeatCell(heatCell: 'exp_r' | 'win_rate' | 'n'): void { patchState(store, { heatCell }); },
      setBreakdown(breakdown: string): void {
        patchState(store, { breakdown });
        fetch(api.analyticsByDimension(breakdown, store.scope()), 'byDimension', 'byDimensionError');
      },
      setTableOpen(panel: string, open: boolean): void {
        patchState(store, { tableOpen: { ...store.tableOpen(), [panel]: open } });
      },
      /** Retry one panel after `sb-panel-error` (spec H4). */
      reload(panel: 'performance' | 'equityCurve' | 'byDimension' | 'heatGrid' | 'exitQuality' | 'journal' | 'strategies' | 'calibration' | 'plans'): void {
        const one: Record<string, () => void> = {
          performance: () => fetch(api.analyticsPerformance(s()), 'performance', 'performanceError'),
          equityCurve: () => fetch(api.analyticsEquityCurve(s()), 'equityCurve', 'equityCurveError'),
          byDimension: () => fetch(api.analyticsByDimension(store.breakdown(), s()), 'byDimension', 'byDimensionError'),
          heatGrid: () => fetch(api.analyticsHeatGrid(s()), 'heatGrid', 'heatGridError'),
          exitQuality: () => fetch(api.analyticsExitQuality(s()), 'exitQuality', 'exitQualityError'),
          journal: () => fetch(api.analyticsJournal(s()), 'journal', 'journalError'),
          strategies: () => fetch(api.analyticsStrategies(s()), 'strategies', 'strategiesError'),
          calibration: () => fetch(api.analyticsCalibration(), 'calibration', 'calibrationError'),
          plans: () => fetch(api.analyticsPlans(), 'plans', 'plansError'),
        };
        one[panel]?.();
      },
```

`inject(PreferencesStore)` beside `inject(ApiClient)` in `withMethods`, and seed `unit`/`measure`/`scope` from `preferences.values()` on first load (inside the existing hooks effect, guarded so it runs once).

- [ ] **Step 8: Verify** — `npm test -- --include src/app/stores/analytics.store.spec.ts` → PASS. Existing tests in that file that referenced deleted signals: update them to the new surface, keeping each test's *intent* (the two load-bearing properties in the file's header comment — the relocated metrics arriving, and tuning progress coming from events, not a timer — must both still be asserted; the relocated metrics now live on the Overview tab's tiles, so move that assertion to `tabs/overview.spec.ts` in Task T1 and say so in a comment here).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts
git commit -m "feat(v94): analytics store -- one scope, six tabs, per-panel errors, unit and measure"
```

---

### Task S5: `scope-url.ts` + routes — URL ⇄ scope, legacy tab redirects

**Files:**
- Create: `frontend/src/app/workspaces/analytics/scope-url.ts`, `frontend/src/app/workspaces/analytics/scope-url.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.routes.ts`

**Interfaces:**
- Consumes: S4's `ANALYTICS_TABS`, `LEGACY_TABS`, `DEFAULT_SCOPE`, `AnalyticsTab`.
- Produces:
  ```ts
  export function scopeFromParams(params: ParamMap): { tab: AnalyticsTab; scope: BookScope; unit: AnalyticsUnit }
  export function scopeToQueryParams(tab: AnalyticsTab, scope: BookScope, unit: AnalyticsUnit): Params  // nulls for defaults
  ```
  A field equal to its default is written as `null` so the URL stays short and one state has one URL.

- [ ] **Step 1: Failing spec**

```ts
import { convertToParamMap } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { DEFAULT_SCOPE } from '../../stores/analytics.store';
import { scopeFromParams, scopeToQueryParams } from './scope-url';

describe('scope-url', () => {
  it('reads every field, defaulting the unset ones', () => {
    const got = scopeFromParams(convertToParamMap({ tab: 'execution', from: '2026-08-01', ledger: 'weak', unit: 'money' }));
    expect(got.tab).toBe('execution');
    expect(got.scope).toEqual({ ...DEFAULT_SCOPE, from: '2026-08-01', ledger: 'weak' });
    expect(got.unit).toBe('money');
  });

  it('maps legacy tabs and rejects nonsense', () => {
    expect(scopeFromParams(convertToParamMap({ tab: 'performance' })).tab).toBe('overview');
    expect(scopeFromParams(convertToParamMap({ tab: 'calibration' })).tab).toBe('edge');
    expect(scopeFromParams(convertToParamMap({ tab: 'nope', ledger: 'nope', unit: 'nope' })))
      .toEqual({ tab: 'overview', scope: DEFAULT_SCOPE, unit: 'r' });
  });

  it('writes defaults as null so one state has one URL', () => {
    expect(scopeToQueryParams('overview', DEFAULT_SCOPE, 'r'))
      .toEqual({ tab: null, from: null, to: null, ledger: null, strategy: null, horizon: null, direction: null, unit: null });
    expect(scopeToQueryParams('edge', { ...DEFAULT_SCOPE, strategy: 'MACD' }, 'pct'))
      .toEqual({ tab: 'edge', from: null, to: null, ledger: null, strategy: 'MACD', horizon: null, direction: null, unit: 'pct' });
  });
});
```

- [ ] **Step 2: Implement**

```ts
import { ParamMap, Params } from '@angular/router';

import { AnalyticsUnit, BookScope, LedgerScope } from '../../api/models';
import { ANALYTICS_TABS, AnalyticsTab, DEFAULT_SCOPE, LEGACY_TABS } from '../../stores/analytics.store';

const LEDGERS: LedgerScope[] = ['main', 'weak', 'both'];
const UNITS: AnalyticsUnit[] = ['r', 'pct', 'money'];
const DIRECTIONS = ['bullish', 'bearish'];
const ISO = /^\d{4}-\d{2}-\d{2}$/;

const pick = <T extends string>(raw: string | null, allowed: readonly T[], fallback: T): T =>
  (allowed as readonly string[]).includes(raw ?? '') ? (raw as T) : fallback;

/** The URL is the scope (spec v94 D2): a filtered view is a link, and it
 *  survives a tab switch and a reload. Anything unrecognised falls back to
 *  the default rather than 400ing the first request. */
export function scopeFromParams(params: ParamMap): { tab: AnalyticsTab; scope: BookScope; unit: AnalyticsUnit } {
  const raw = params.get('tab');
  const tab = (ANALYTICS_TABS as readonly string[]).includes(raw ?? '')
    ? (raw as AnalyticsTab)
    : (LEGACY_TABS[raw ?? ''] ?? 'overview');
  const day = (name: string): string | null => {
    const value = params.get(name);
    return value && ISO.test(value) ? value : null;
  };
  return {
    tab,
    scope: {
      from: day('from'), to: day('to'),
      ledger: pick(params.get('ledger'), LEDGERS, DEFAULT_SCOPE.ledger),
      strategy: params.get('strategy') || null,
      horizon: params.get('horizon') || null,
      direction: pick(params.get('direction'), DIRECTIONS, '') || null,
    },
    unit: pick(params.get('unit'), UNITS, 'r'),
  };
}

export function scopeToQueryParams(tab: AnalyticsTab, scope: BookScope, unit: AnalyticsUnit): Params {
  return {
    tab: tab === 'overview' ? null : tab,
    from: scope.from, to: scope.to,
    ledger: scope.ledger === DEFAULT_SCOPE.ledger ? null : scope.ledger,
    strategy: scope.strategy, horizon: scope.horizon, direction: scope.direction,
    unit: unit === 'r' ? null : unit,
  };
}
```

- [ ] **Step 3: Rewrite `analytics.routes.ts`**

```ts
const analyticsState = (route: ActivatedRouteSnapshot) => scopeFromParams(route.queryParamMap);

const refreshOnAnalytics: RefreshPredicate = (event, route) =>
  analyticsState(route).tab === 'tuning' ? event === 'jobs' : event === 'analytics';

export const analyticsRoutes: Routes = [{
  path: '', providers: [AnalyticsStore], runGuardsAndResolvers: 'always',
  data: routeData('Analytics', refreshOnAnalytics),
  resolve: {
    ready: resolveRoute((route) => {
      const store = inject(AnalyticsStore);
      const { tab, scope, unit } = analyticsState(route);
      store.hydrate(scope, unit);          // sets state without firing a request
      return store.resolveTab(tab);
    }),
  },
  loadComponent: () => import('./analytics').then((m) => m.Analytics),
}];
```

Add the matching `hydrate(scope, unit)` method to the store (S4's surface): `patchState(store, { scope, unit })`, no fetch — the resolver's `resolveTab` does the fetching.

- [ ] **Step 4: Verify** — `npm test -- --include src/app/workspaces/analytics/scope-url.spec.ts` → PASS; `npm test -- --include src/app/stores/analytics.store.spec.ts` still PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/scope-url.ts frontend/src/app/workspaces/analytics/scope-url.spec.ts frontend/src/app/workspaces/analytics/analytics.routes.ts frontend/src/app/stores/analytics.store.ts
git commit -m "feat(v94): the URL is the scope; legacy tab links land on their new tabs"
```

---

### Task S6: `scope-bar.ts` + the thin `analytics.ts` shell

**Files:**
- Create: `frontend/src/app/workspaces/analytics/scope-bar.ts`, `frontend/src/app/workspaces/analytics/scope-bar.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` — **replaced** by a ~140-line shell (tab strip + scope bar + `@switch` over six tab components). Its old body moves to Part 4's tabs; delete nothing until T7, but the shell template is written now and the six tab components are stubs that T1–T6 fill.
- Modify: `frontend/src/app/workspaces/analytics/analytics.spec.ts`

**Interfaces:**
- Consumes: S4's store surface, S5's `scopeToQueryParams`, `sb-control-bar`, `sb-select`, `sb-date-range`, `sb-segmented`, `sb-tab-bar`, `sb-freshness`.
- Produces: `<sb-scope-bar>` with inputs `scope`, `unit`, `n`, `allTimePanels`, `strategies`, `horizons`, `asOf`, `tuning` (boolean: collapse to the unit toggle), outputs `scopeChange`, `unitChange`, `cleared`.

- [ ] **Step 1: Failing specs**

`scope-bar.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { DEFAULT_SCOPE } from '../../stores/analytics.store';
import { ScopeBar } from './scope-bar';

const create = (inputs: Record<string, unknown> = {}) => {
  const fixture = TestBed.createComponent(ScopeBar);
  fixture.componentRef.setInput('scope', DEFAULT_SCOPE);
  fixture.componentRef.setInput('unit', 'r');
  fixture.componentRef.setInput('n', 312);
  fixture.componentRef.setInput('allTimePanels', 0);
  fixture.componentRef.setInput('strategies', ['MACD']);
  fixture.componentRef.setInput('horizons', ['2w', '1m']);
  for (const [k, v] of Object.entries(inputs)) fixture.componentRef.setInput(k, v);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
};

describe('ScopeBar', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('reports the population the scope produced', () => {
    const { el } = create();
    expect(el.textContent).toContain('N=312');
    expect(el.textContent).not.toContain('all-time');
  });

  it('says how many panels ignore it', () => {
    const { el } = create({ allTimePanels: 3 });
    expect(el.textContent).toContain('3 panels all-time');
  });

  it('collapses to the unit toggle on Tuning', () => {
    const { el } = create({ tuning: true });
    expect(el.querySelector('sb-date-range')).toBeNull();
    expect(el.querySelector('sb-segmented')).not.toBeNull();
  });
});
```

`analytics.spec.ts` — replace the old tab assertions with:

```ts
  it('renders the six tabs and puts the scope in the URL', async () => {
    const { fixture, router } = create();            // this file's existing helper
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    for (const label of ['Overview', 'Attribution', 'Execution', 'Edge', 'Pipeline', 'Tuning']) {
      expect(text).toContain(label);
    }
  });
```

- [ ] **Step 2: Implement `scope-bar.ts`**

```ts
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { AnalyticsUnit, BookScope } from '../../api/models';
import { RANGE_PRESETS, presetRange } from '../../stores/analytics.store';
import { ControlBar } from '../../ui/control-bar';
import { DateRange } from '../../ui/date-range';
import { Select } from '../../ui/form-controls';
import { Freshness } from '../../ui/freshness';
import { Segmented } from '../../ui/segmented';

/**
 * One bar, every panel below it (spec v94 D2). It also REPORTS: the
 * closed-trade count the scope produced, when the figures were built, and
 * how many panels on this tab ignore it. A screen that hides how scoped its
 * data is has a correctness bug -- that is what this component exists to fix.
 */
@Component({
  selector: 'sb-scope-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ControlBar, DateRange, Select, Segmented, Freshness],
  template: `
    <sb-control-bar [activeCount]="activeCount()" (cleared)="cleared.emit()">
      @if (!tuning()) {
        <sb-select filters label="Range" [value]="preset()" [options]="presetOptions"
                   (valueChange)="onPreset($event)" />
        @if (preset() === 'custom') {
          <sb-date-range filters [from]="scope().from" [to]="scope().to"
                         (changed)="scopeChange.emit($event)" />
        }
        <sb-select filters label="Ledger" [value]="scope().ledger" [options]="ledgerOptions"
                   (valueChange)="scopeChange.emit({ ledger: $any($event) })" />
        <sb-select filters label="Strategy" placeholder="Any strategy" [value]="scope().strategy ?? ''"
                   [options]="options(strategies())" (valueChange)="scopeChange.emit({ strategy: $event || null })" />
        <sb-select filters label="Horizon" placeholder="Any horizon" [value]="scope().horizon ?? ''"
                   [options]="options(horizons())" (valueChange)="scopeChange.emit({ horizon: $event || null })" />
        <sb-select filters label="Direction" placeholder="Both" [value]="scope().direction ?? ''"
                   [options]="directionOptions" (valueChange)="scopeChange.emit({ direction: $event || null })" />
      }
      <sb-segmented scope label="Unit" [options]="unitOptions" [value]="unit()"
                    (valueChange)="unitChange.emit($any($event))" />
      @if (!tuning()) {
        <span scope class="population num">N={{ n() ?? '—' }} closed</span>
        @if (asOf()) { <sb-freshness scope [asOf]="asOf()!" /> }
        @if (allTimePanels() > 0) {
          <span scope class="all-time">{{ allTimePanels() }} panels all-time</span>
        }
      }
    </sb-control-bar>
  `,
  styles: `
    .population { font-size: var(--text-chip); color: var(--text-secondary); font-variant-numeric: tabular-nums; }
    .all-time { font-size: var(--text-micro); text-transform: uppercase; letter-spacing: .08em; color: var(--warn); }
  `,
})
export class ScopeBar {
  readonly scope = input.required<BookScope>();
  readonly unit = input.required<AnalyticsUnit>();
  readonly n = input<number | null>(null);
  readonly allTimePanels = input(0);
  readonly strategies = input<readonly string[]>([]);
  readonly horizons = input<readonly string[]>([]);
  readonly asOf = input<string | null>(null);
  readonly tuning = input(false);
  readonly scopeChange = output<Partial<BookScope>>();
  readonly unitChange = output<AnalyticsUnit>();
  readonly cleared = output<void>();

  protected readonly presetOptions = [...RANGE_PRESETS.map((p) => ({ value: p.value, label: p.label })),
                                      { value: 'custom', label: 'Custom…' }];
  protected readonly ledgerOptions = [{ value: 'main', label: 'Main ledger' },
                                      { value: 'weak', label: 'WEAK ledger' },
                                      { value: 'both', label: 'Both ledgers' }];
  protected readonly directionOptions = [{ value: 'bullish', label: 'Long' }, { value: 'bearish', label: 'Short' }];
  protected readonly unitOptions = [{ value: 'r', label: 'R' }, { value: 'pct', label: '%' }, { value: 'money', label: '$' }];

  protected options(values: readonly string[]) { return values.map((v) => ({ value: v, label: v })); }

  protected readonly activeCount = computed(() => {
    const s = this.scope();
    return (['from', 'to', 'strategy', 'horizon', 'direction'] as const).filter((k) => s[k]).length
      + (s.ledger === 'main' ? 0 : 1);
  });

  /** Which preset the current bounds correspond to, or `custom`. */
  protected readonly preset = computed(() => {
    const s = this.scope();
    if (!s.from && !s.to) return 'all';
    for (const p of RANGE_PRESETS) {
      const r = presetRange(p.value, new Date());
      if (r.from === s.from && r.to === s.to) return p.value;
    }
    return 'custom';
  });

  protected onPreset(value: string): void {
    if (value === 'custom') { this.scopeChange.emit({}); return; }
    this.scopeChange.emit(presetRange(value, new Date()));
  }
}
```

- [ ] **Step 3: Write the shell `analytics.ts`**

```ts
/**
 * Analytics — six tabs in the order a trader asks (spec v94 D1), one scope
 * bar above them (D2). This file is a shell: the tab strip, the bar, and a
 * switch. Every panel lives in `tabs/`, so no file here grows back into the
 * 2,233-line component v94 replaced.
 */
@Component({
  selector: 'sb-analytics',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TabBar, ScopeBar, OverviewTab, AttributionTab, ExecutionTab, EdgeTab, PipelineTab, TuningTab],
  template: `
    <sb-tab-bar [tabs]="tabs" [active]="store.tab()" (activeChange)="goToTab($event)" />
    <sb-scope-bar
      [scope]="store.scope()" [unit]="store.unit()" [n]="store.scopeN()"
      [allTimePanels]="store.allTimePanelCount()" [strategies]="strategyNames()"
      [horizons]="horizons" [asOf]="store.asOf()" [tuning]="store.tab() === 'tuning'"
      (scopeChange)="onScope($event)" (unitChange)="onUnit($event)" (cleared)="store.clearScope()" />

    @switch (store.tab()) {
      @case ('overview') { <sb-overview-tab /> }
      @case ('attribution') { <sb-attribution-tab /> }
      @case ('execution') { <sb-execution-tab /> }
      @case ('edge') { <sb-edge-tab /> }
      @case ('pipeline') { <sb-pipeline-tab /> }
      @case ('tuning') { <sb-tuning-tab /> }
    }
  `,
})
export class Analytics {
  protected readonly store = inject(AnalyticsStore);
  private readonly router = inject(Router);
  protected readonly tabs: Tab[] = [
    { id: 'overview', label: 'Overview' }, { id: 'attribution', label: 'Attribution' },
    { id: 'execution', label: 'Execution' }, { id: 'edge', label: 'Edge' },
    { id: 'pipeline', label: 'Pipeline' }, { id: 'tuning', label: 'Tuning' },
  ];
  protected readonly horizons = HORIZON_KEYS;          // from ../../ui/horizons or a local const of the ten keys
  protected readonly strategyNames = computed(() =>
    (this.store.strategies()?.strategies ?? []).map((s: any) => String(s.strategy ?? s.name)).sort());

  protected goToTab(tab: string): void { this.navigate({ tab: tab === 'overview' ? null : tab }); }
  protected onScope(patch: Partial<BookScope>): void {
    this.store.setScope(patch);
    this.navigate(scopeToQueryParams(this.store.tab(), this.store.scope(), this.store.unit()));
  }
  protected onUnit(unit: AnalyticsUnit): void {
    this.store.setUnit(unit);
    this.navigate({ unit: unit === 'r' ? null : unit });
  }
  private navigate(queryParams: Params): void {
    this.router.navigate([], { queryParams, queryParamsHandling: 'merge', replaceUrl: true });
  }
}
```

The six tab components are created as **empty stubs** in this task (`@Component({selector:'sb-overview-tab', template:''}) export class OverviewTab {}` in their own files) so the shell compiles; T1–T6 fill them. `store.asOf()` is a new computed: `computed(() => equityCurve()?.as_of ?? byDimension()?.as_of ?? null)` — add it to S4's surface if not already there.

The ten horizon keys: `grep -n "^HORIZONS" -A 14 swingbot/core/market/strategy_types.py` and mirror them as a `const` in the shell (the frontend has no generated copy; `analytics.ts`'s old heat-grid read them off the payload, and Part 1's `/heat-grid` returns `cols`, so prefer `store.heatGrid()?.cols ?? FALLBACK_HORIZONS`).

- [ ] **Step 4: Verify** — `npm test -- --include src/app/workspaces/analytics/scope-bar.spec.ts` and `... --include src/app/workspaces/analytics/analytics.spec.ts` → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/scope-bar.ts frontend/src/app/workspaces/analytics/scope-bar.spec.ts frontend/src/app/workspaces/analytics/analytics.ts frontend/src/app/workspaces/analytics/analytics.spec.ts frontend/src/app/workspaces/analytics/tabs/
git commit -m "feat(v94): scope bar that reports its own population; analytics shell over six tab components"
```
