# v142 — Partials analytics tab: Part 3 — SPA, full suites, production backfill

> Part of [`2026-10-08-v142-partials-analytics-tab_0-index.md`](2026-10-08-v142-partials-analytics-tab_0-index.md). The index carries the header block, the spec resolutions, the Global Constraints, the Review Focus and the full `## Parallelisation`. Read it first. **Pull one task at a time:** `grep -n "^### Task V142-9" -A 500 <this file>`. Frontend commands run from `frontend/` inside the worktree (`npm --prefix frontend ...` or the agent's own working directory; never `cd` in a shared shell).

# Phase 4 — The Partials tab

## Parallelisation

- **Sequential:** V142-7, then V142-9. V142-9 consumes `AnalyticsPartials`, `store.partials` and `PARTIALS_FIXTURE` from V142-7.
- **V142-8 is retired** (partner, 2026-10-08: the TP2 ladder is a bar list, so `LineChart` needs no `xLabel`). Its id is kept so no other task's address moves. Nothing to schedule.

### Task V142-7: Models, API client and the store's partials slice

**Files:**
- Modify: `frontend/src/app/api/models.ts` (insert above `export interface AnalyticsPlans {`, ~:600)
- Modify: `frontend/src/app/api/api-client.ts` (import list ~:13; after `analyticsExitQuality`, ~:263-265)
- Modify: `frontend/src/app/stores/analytics.store.ts` (imports ~:21, `AnalyticsTab` ~:209, `ANALYTICS_TABS` ~:212, `PanelKey` ~:225, slice ~:393, initial state ~:474, loaders ~:735, resolvers ~:860, `RESOLVERS`/`LOADERS` ~:874-887, `reload` ~:916)
- Create: `frontend/src/app/workspaces/analytics/tabs/partials.fixture.ts`
- Test: `frontend/src/app/stores/analytics.partials.spec.ts` (create)

**Interfaces:**
- Consumes: the V142-6 response shape.
- Produces: the types `AnalyticsPartials`, `PartialsKpis`, `PartialsBreakdownRow`, `PartialsBucket`, `PartialsDimension`, `PartialsHoldStage`, `PartialsHold`, `PartialsLadderRow`, `PartialsSplitRow`, `PartialsOutcome`, `PartialsStage`; `ApiClient.analyticsPartials(scope?) : Observable<AnalyticsPartials>`; `AnalyticsTab` gains `'partials'` (7th in `ANALYTICS_TABS`, so `?tab=partials` routes through `scopeFromParams` unchanged); the store's `partials()` / `partialsError()` signals; `PanelKey` `'partials'` for `reload('partials')`; `PARTIALS_FIXTURE`. `scopeN` is deliberately **not** fed by `partials` (index, spec resolution 6).

- [ ] **Step 1: Write the fixture and the failing spec**

Create `frontend/src/app/workspaces/analytics/tabs/partials.fixture.ts`:

```ts
import { AnalyticsPartials, PartialsBreakdownRow, PartialsKpis } from '../../../api/models';

/** v142 — one `/analytics/partials` payload, shaped from the Python test
 *  book (`tests/analytics/test_partials.py::_book`). Shared by the store
 *  and tab specs so both read the same response. */
const KPIS: PartialsKpis = {
  tp1_rate: 85.7, tp1_rate_n: 7, tp1_tp2_rate: 25, tp1_tp2_n: 4,
  beat_all_out: 80, beat_all_out_n: 5, mean_runner_delta_r: 0.324,
  median_tp1_exit_sessions: 2, tp1_exit_n: 5,
};

const row = (key: string, n: number, thin: boolean): PartialsBreakdownRow => ({ ...KPIS, key, n, thin });

export const PARTIALS_FIXTURE: AnalyticsPartials = {
  kpis: KPIS,
  funnel: [
    { stage: 'filled', n: 8 }, { stage: 'tp1', n: 6 }, { stage: 'runner_closed', n: 5 }, { stage: 'tp2', n: 1 },
  ],
  outcomes: [
    { bucket: 'tp2', n: 1, share: 16.7, avg_runner_r: 4 },
    { bucket: 'trail', n: 1, share: 16.7, avg_runner_r: 3 },
    { bucket: 'floor', n: 1, share: 16.7, avg_runner_r: 1.34 },
    { bucket: 'stall', n: 0, share: 0, avg_runner_r: null },
    { bucket: 'time', n: 0, share: 0, avg_runner_r: null },
    { bucket: 'manual', n: 1, share: 16.7, avg_runner_r: 2.5 },
    { bucket: 'no_tp2', n: 1, share: 16.7, avg_runner_r: 2.4 },
    { bucket: 'open', n: 1, share: 16.7, avg_runner_r: null },
  ],
  counterfactuals: {
    actual_exp_r: 2.324, all_out_exp_r: 2, giveback: [0.2, 1.26, 0.6, 0.4],
    ladder: [
      { level_r: 1.5, touch_rate: 100, cf_exp_r: 1.75, n: 4 },
      { level_r: 2, touch_rate: 100, cf_exp_r: 2, n: 4 },
      { level_r: 2.5, touch_rate: 100, cf_exp_r: 2.25, n: 4 },
      { level_r: 3, touch_rate: 50, cf_exp_r: 2.2175, n: 4 },
      { level_r: 4, touch_rate: 25, cf_exp_r: 2.3425, n: 4 },
    ],
    split: [
      { fraction: 0.33, exp_r: 2.4342, n: 5 }, { fraction: 0.5, exp_r: 2.324, n: 5 },
      { fraction: 0.67, exp_r: 2.2138, n: 5 },
    ],
    path_unavailable: 1, runner_r_unavailable: 0,
  },
  holds: {
    entry_tp1: { p25: 2, median: 2, p75: 2, points: [2, 2, 2, 2, 2, 2] },
    tp1_exit: { p25: 2, median: 2, p75: 2, points: [2, 2, 2, 2, 4] },
    entry_exit: { p25: 4, median: 4, p75: 4, points: [4, 4, 4, 4, 6] },
  },
  breakdowns: {
    strategy: [row('MACD', 2, true), row('RSI', 4, true)],
    horizon: [row('4w', 6, true)],
    side: [row('bearish', 0, true), row('bullish', 6, true)],
    month: [
      { ...row('2026-09', 12, false), tp1_rate: null, tp1_rate_n: null, beat_all_out: 75 },
      { ...row('2026-10', 6, true), tp1_rate: null, tp1_rate_n: null },
    ],
  },
  thin_n: 10,
  population: { filled: 8, partial: 6, unreadable: 0 },
  scope: { from: null, to: null, ledger: 'main', strategy: null, horizon: null, direction: null },
  n: 8,
};
```

Create `frontend/src/app/stores/analytics.partials.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Signal, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { convertToParamMap } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../api/event-stream';
import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { PARTIALS_FIXTURE } from '../workspaces/analytics/tabs/partials.fixture';
import { scopeFromParams } from '../workspaces/analytics/scope-url';
import { ANALYTICS_TABS, AnalyticsStore } from './analytics.store';

/* v142 — the Partials slice: one payload, its own error, the one scope. */

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();
  changes(name: string): Signal<number> {
    if (!this.counters.has(name)) this.counters.set(name, signal(0));
    return this.counters.get(name)!.asReadonly();
  }
}

describe('AnalyticsStore — partials slice', () => {
  let store: InstanceType<typeof AnalyticsStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        AnalyticsStore,
      ],
    });
    store = TestBed.inject(AnalyticsStore);
    backend = TestBed.inject(HttpTestingController);
  });

  it('is the seventh tab and routes from ?tab=partials', () => {
    expect(ANALYTICS_TABS.at(-1)).toBe('partials');
    expect(scopeFromParams(convertToParamMap({ tab: 'partials' })).tab).toBe('partials');
  });

  it('fetches only /partials, against the one scope', () => {
    store.setScope({ strategy: 'RSI' });
    backend.match(() => true).forEach((request) => request.flush({}));   // the Overview load
    store.setTab('partials');
    const request = backend.expectOne((req) => req.url === '/api/v1/analytics/partials');
    expect(request.request.params.get('strategy')).toBe('RSI');
    request.flush(PARTIALS_FIXTURE);
    backend.verify();
    expect(store.partials()?.n).toBe(8);
    // The scope bar's N counts CLOSED TRADES; a filled-plan count would
    // mislabel it, so the Partials payload never feeds scopeN.
    expect(store.scopeN()).toBeNull();
  });

  it('keeps its own error and retries only itself', () => {
    store.setTab('partials');
    backend.expectOne((req) => req.url === '/api/v1/analytics/partials')
      .flush({ message: 'boom' }, { status: 500, statusText: 'Server Error' });
    expect(store.partialsError()).not.toBeNull();
    store.reload('partials');
    backend.expectOne((req) => req.url === '/api/v1/analytics/partials').flush(PARTIALS_FIXTURE);
    expect(store.partialsError()).toBeNull();
    backend.verify();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

`npx ng test --include src/app/stores/analytics.partials.spec.ts` (from `frontend/`)
Expected: the build fails with `TS2305: Module '"../../../api/models"' has no exported member 'AnalyticsPartials'` (and `store.partials` missing).

- [ ] **Step 3: Add the models**

In `frontend/src/app/api/models.ts`, insert directly above `export interface AnalyticsPlans {`:

```ts
/** v142 — `GET /analytics/partials` (`swingbot/core/analytics/partials.py`).
 *  Rates are percentages 0-100; every R is on the plan's initial risk. The
 *  scope's date range filters on FILL date and `n` is the filled plans. */
export interface PartialsKpis {
  tp1_rate: number | null; tp1_rate_n: number | null;
  tp1_tp2_rate: number | null; tp1_tp2_n: number;
  beat_all_out: number | null; beat_all_out_n: number;
  mean_runner_delta_r: number | null;
  median_tp1_exit_sessions: number | null; tp1_exit_n: number;
}
export type PartialsStage = 'filled' | 'tp1' | 'runner_closed' | 'tp2';
export type PartialsBucket = 'tp2' | 'trail' | 'floor' | 'stall' | 'time' | 'manual' | 'no_tp2' | 'open' | 'other';
export type PartialsDimension = 'strategy' | 'horizon' | 'side' | 'month';
export type PartialsHoldStage = 'entry_tp1' | 'tp1_exit' | 'entry_exit';
export interface PartialsHold { p25: number | null; median: number | null; p75: number | null; points: number[]; }
export interface PartialsBreakdownRow extends PartialsKpis { key: string; n: number; thin: boolean; }
export interface PartialsLadderRow { level_r: number; touch_rate: number | null; cf_exp_r: number | null; n: number; }
export interface PartialsSplitRow { fraction: number; exp_r: number | null; n: number; }
export interface PartialsOutcome { bucket: PartialsBucket; n: number; share: number | null; avg_runner_r: number | null; }
export interface AnalyticsPartials extends Scoped {
  kpis: PartialsKpis;
  funnel: { stage: PartialsStage; n: number }[];
  outcomes: PartialsOutcome[];
  counterfactuals: {
    actual_exp_r: number | null; all_out_exp_r: number | null; giveback: number[];
    ladder: PartialsLadderRow[]; split: PartialsSplitRow[];
    path_unavailable: number; runner_r_unavailable: number;
  };
  holds: Record<PartialsHoldStage, PartialsHold>;
  breakdowns: Record<PartialsDimension, PartialsBreakdownRow[]>;
  thin_n: number;
  population: { filled: number; partial: number; unreadable: number };
}
```

- [ ] **Step 4: Add the client method**

In `frontend/src/app/api/api-client.ts`, add `AnalyticsPartials,` to the `./models` import list, between `AnalyticsJournal,` and `AnalyticsPerformance,`. Directly after the `analyticsExitQuality` method add:

```ts

  /** v142 — the Partials tab: TP1->TP2 conversion and runner counterfactuals. */
  analyticsPartials(scope?: Partial<BookScope> | null): Observable<AnalyticsPartials> {
    return this.http.get<AnalyticsPartials>(`${this.base}/analytics/partials`, { params: scopeParams(scope) });
  }
```

- [ ] **Step 5: Add the store slice**

In `frontend/src/app/stores/analytics.store.ts` make these exact replacements:

1. In the `../api/models` import list, add `AnalyticsPartials,` between `AnalyticsJournal,` and `AnalyticsPerformance,`.
2. `export type AnalyticsTab = 'overview' | 'attribution' | 'execution' | 'edge' | 'pipeline' | 'tuning';` → `export type AnalyticsTab = 'overview' | 'attribution' | 'execution' | 'edge' | 'pipeline' | 'tuning' | 'partials';`
3. `  ['overview', 'attribution', 'execution', 'edge', 'pipeline', 'tuning'] as const;` → `  ['overview', 'attribution', 'execution', 'edge', 'pipeline', 'tuning', 'partials'] as const;`
4. `  | 'byHorizon' | 'byDirection' | 'byDow';` → `  | 'byHorizon' | 'byDirection' | 'byDow' | 'partials';`
5. After the slice line `  plans: AnalyticsPlans | null;               plansError: string | null;` add:

```ts
  /** v142 — the Partials tab's one payload. */
  partials: AnalyticsPartials | null;         partialsError: string | null;
```

6. After the initial-state line `      plans: null, plansError: null,` add `      partials: null, partialsError: null,`.
7. After `    const loadPipeline = (): void => fetchPanel(api.analyticsPlans(), 'plans', 'plansError');` add:

```ts
    const loadPartials = (): void =>
      fetchPanel(api.analyticsPartials(s()), 'partials', 'partialsError');
```

8. After the `resolvePipeline` definition (`      resolveOne(api.analyticsPlans(), 'plans', 'plansError');`) add:

```ts

    const resolvePartials = (): Observable<void> =>
      resolveOne(api.analyticsPartials(s()), 'partials', 'partialsError');
```

9. `      edge: resolveEdge, pipeline: resolvePipeline, tuning: resolveTuning,` → `      edge: resolveEdge, pipeline: resolvePipeline, tuning: resolveTuning, partials: resolvePartials,`
10. `      edge: loadEdge, pipeline: loadPipeline, tuning: loadTuning,` → `      edge: loadEdge, pipeline: loadPipeline, tuning: loadTuning, partials: loadPartials,`
11. In `reload`'s `one` map, after `          plans: () => fetchPanel(api.analyticsPlans(), 'plans', 'plansError'),` add `          partials: () => fetchPanel(api.analyticsPartials(s()), 'partials', 'partialsError'),`

`scopeN` stays exactly as it is.

- [ ] **Step 6: Run the specs to verify they pass**

```bash
npx ng test --include src/app/stores/analytics.partials.spec.ts --include src/app/workspaces/analytics/scope-url.spec.ts --include src/app/stores/analytics.store.spec.ts
```

Expected: 3 files passed. If the build stops on `src/app/workspaces/calendar/calendar.spec.ts` `TS2739 ... missing ... plan_id, opened_at`, that is a **pre-existing** break on `main` (present at `bba72100`, from the calendar `ROW_KEYS` change). It is not this task's: see V142-10 Step 3. Until it is fixed, add `--include` only for the files above and report it.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.partials.spec.ts frontend/src/app/workspaces/analytics/tabs/partials.fixture.ts
git commit -m "$(cat <<'EOF'
feat(v142): partials models, client and store slice

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

### Task V142-8: Retired -- LineChart xLabel (ladder drawn as a bar list instead)

Intentionally empty: no code, no test, no commit. The partner chose (2026-10-08) to draw the TP2 ladder as a `BarList` per level (V142-9), so `LineChart` keeps its date-only x axis and needs no `xLabel` input.

### Task V142-9: The Partials tab, registered as the seventh tab

**Files:**
- Create: `frontend/src/app/workspaces/analytics/tabs/partials.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (imports ~:12, `imports:` ~:43, `@switch` ~:58, `tabs` ~:63-66, the doc comment ~:24)
- Modify: `docs/features/features-admin.md` (the "six tabs" paragraph, ~:72)
- Test: `frontend/src/app/workspaces/analytics/tabs/partials.spec.ts` (create), `frontend/src/app/workspaces/analytics/analytics.spec.ts` (modify)

**Interfaces:**
- Consumes: `AnalyticsPartials` and friends, `store.partials()`, `store.partialsError()`, `store.reload('partials')`, `PARTIALS_FIXTURE` (V142-7); the existing `StatTile`, `BarList`, `ShareBar`, `Waterfall`, `LineChart`, `Histogram`, `StripPlot`, `Segmented`, `EmptyStateComponent`, `Panel`, `PanelHeader`, `PanelError`.
- Produces: `<sb-partials-tab>` (`PartialsTab`) and its pure helpers `kpiTiles`, `funnelRows`, `outcomeSegments`, `runnerWaterfall`, `ladderRows` (one `BarRow` per TP2 level, label `TP2 at X.XR`, value `cf_exp_r`, `n`; then an `Actual` row carrying `actual_exp_r`, because `BarList` draws its `reference` marker only in `rate` mode and has no secondary-figure column), `touchRows` (the touch rate per level, a second `BarList` in `rate` mode), `splitRows`, `givebackBins`, `holdGroups`, `monthTrend`, `pctText`, `rText`, `DIMENSIONS`.

- [ ] **Step 1: Write the failing specs**

Create `frontend/src/app/workspaces/analytics/tabs/partials.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsPartials } from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import {
  PartialsTab, funnelRows, givebackBins, kpiTiles, ladderRows, monthTrend, outcomeSegments,
  runnerWaterfall, splitRows, touchRows,
} from './partials';
import { PARTIALS_FIXTURE } from './partials.fixture';

function render(payload: AnalyticsPartials | null, error: string | null = null) {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: AnalyticsStore, useValue: { partials: signal(payload), partialsError: signal(error), reload: () => {} } },
      { provide: PreferencesStore, useValue: { values: () => ({}) } },
    ],
  });
  const fixture = TestBed.createComponent(PartialsTab);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('partials helpers', () => {
  it('leads the KPI row with the five figures, the hero marked', () => {
    const tiles = kpiTiles(PARTIALS_FIXTURE);
    expect(tiles.map((t) => t.label)).toEqual(
      ['TP1 rate', 'TP1 → TP2', 'Runner beat all-out', 'Mean runner ΔR', 'Median TP1 → exit']);
    expect(tiles.filter((t) => t.hero).map((t) => [t.value, t.sample, t.tone])).toEqual([['80.0%', 5, 'pos']]);
    expect(tiles[3].value).toBe('+0.32R');
  });

  it('draws the funnel as a share of filled trades, keeping each count', () => {
    expect(funnelRows(PARTIALS_FIXTURE).map((r) => [r.label, r.value, r.n])).toEqual([
      ['Filled', 100, 8], ['Hit TP1', 75, 6], ['Runner closed', 62.5, 5], ['Hit TP2', 12.5, 1]]);
  });

  it('labels each outcome with its average runner R', () => {
    const segments = outcomeSegments(PARTIALS_FIXTURE);
    expect(segments[0]).toEqual({ label: 'TP2 +4.00R', count: 1, tone: 'pos' });
    expect(segments.find((s) => s.label.startsWith('Open'))?.label).toBe('Open —');
  });

  it('builds the waterfall from all-out to actual ExpR', () => {
    const [allOut, runner] = runnerWaterfall(PARTIALS_FIXTURE);
    expect(allOut).toEqual({ label: 'All-out at TP1', value: 2 });
    expect(runner.value).toBeCloseTo(0.324, 6);
  });

  it('draws one ladder bar per TP2 level, then the actual setup', () => {
    expect(ladderRows(PARTIALS_FIXTURE)).toEqual([
      { label: 'TP2 at 1.5R', value: 1.75, n: 4 }, { label: 'TP2 at 2.0R', value: 2, n: 4 },
      { label: 'TP2 at 2.5R', value: 2.25, n: 4 }, { label: 'TP2 at 3.0R', value: 2.2175, n: 4 },
      { label: 'TP2 at 4.0R', value: 2.3425, n: 4 }, { label: 'Actual', value: 2.324, n: 5 }]);
    expect(touchRows(PARTIALS_FIXTURE).map((r) => [r.label, r.value])).toEqual([
      ['1.5R', 100], ['2.0R', 100], ['2.5R', 100], ['3.0R', 50], ['4.0R', 25]]);
  });

  it('labels the split rows by the share taken at TP1', () => {
    expect(splitRows(PARTIALS_FIXTURE).map((r) => r.label)).toEqual(['33% at TP1', '50% at TP1', '67% at TP1']);
  });

  it('bins giveback in half-R steps, keeping empty bins between', () => {
    expect(givebackBins([0.2, 1.26, 0.6, 0.4])).toEqual([
      { label: '0.0–0.5R', count: 2 }, { label: '0.5–1.0R', count: 1 }, { label: '1.0–1.5R', count: 1 }]);
    expect(givebackBins([])).toEqual([]);
  });

  it('trends the hero figure by month', () => {
    expect(monthTrend(PARTIALS_FIXTURE.breakdowns.month)[0].points).toEqual([
      { date: '2026-09-01', value: 75 }, { date: '2026-10-01', value: 80 }]);
  });
});

describe('PartialsTab', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('renders every panel from one payload, hero first among the KPIs', () => {
    const { el } = render(PARTIALS_FIXTURE);
    expect(el.querySelector('sb-line-chart')).toBeNull();            // ladder is a bar list
    expect(el.querySelectorAll('sb-stat-tile')).toHaveLength(5);
    expect(el.querySelector('.tile.hero')?.textContent).toContain('Runner beat all-out');
    for (const selector of ['sb-share-bar', 'sb-waterfall', 'sb-histogram', 'sb-strip-plot', 'sb-segmented']) {
      expect(el.querySelector(selector)).not.toBeNull();
    }
    expect(el.querySelector('.footer')?.textContent).toContain('1 closed runners without a price path');
    expect(el.querySelector('.footer')?.textContent).toContain('not a gate');
  });

  it('dims thin breakdown rows and switches dimension in place', () => {
    const { fixture, el } = render(PARTIALS_FIXTURE);
    expect(el.querySelectorAll('tr.thin')).toHaveLength(2);           // MACD and RSI, both N < 10
    (fixture.componentInstance as PartialsTab).dimension.set('month');
    fixture.detectChanges();
    const rows = [...el.querySelectorAll('.breakdown tbody tr')];
    expect(rows.map((r) => r.classList.contains('thin'))).toEqual([false, true]);
    expect(el.querySelectorAll('sb-line-chart')).toHaveLength(1);    // the month trend only
  });

  it('shows the empty state when the scope holds no partial trade', () => {
    const empty = { ...PARTIALS_FIXTURE, population: { filled: 3, partial: 0, unreadable: 0 } };
    const { el } = render(empty);
    expect(el.querySelector('sb-empty-state')).not.toBeNull();
    expect(el.querySelector('sb-stat-tile')).toBeNull();
  });

  it('shows its own error with a retry', () => {
    const { el } = render(null, 'boom');
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
  });
});

describe('partials.ts breakpoints', () => {
  it('uses only declared breakpoint values in width queries', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/tabs/partials.ts'), 'utf8');
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
```

In `frontend/src/app/workspaces/analytics/analytics.spec.ts`:

1. `  it('renders the six tabs and puts the scope in the URL', async () => {` → `  it('renders the seven tabs and puts the scope in the URL', async () => {`
2. `    for (const label of ['Overview', 'Attribution', 'Execution', 'Edge', 'Pipeline', 'Tuning']) {` → `    for (const label of ['Overview', 'Attribution', 'Execution', 'Edge', 'Pipeline', 'Tuning', 'Partials']) {`
3. `      'Overview', 'Attribution', 'Execution', 'Edge', 'Pipeline', 'Tuning',` (inside `toEqual([`) → `      'Overview', 'Attribution', 'Execution', 'Edge', 'Pipeline', 'Tuning', 'Partials',`
4. Insert directly before `  it('mounts the tab the store says is open', () => {`:

```ts
  it('mounts the Partials tab from the store', () => {
    const { fixture } = create();
    TestBed.inject(AnalyticsStore).setTab('partials', false);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('sb-partials-tab')).not.toBeNull();
  });

```

- [ ] **Step 2: Run them to verify they fail**

`npx ng test --include src/app/workspaces/analytics/tabs/partials.spec.ts --include src/app/workspaces/analytics/analytics.spec.ts`
Expected: the build fails with `Could not resolve "./partials"` (TS2307).

- [ ] **Step 3: Write the tab**

Create `frontend/src/app/workspaces/analytics/tabs/partials.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import {
  AnalyticsPartials, PartialsBreakdownRow, PartialsBucket, PartialsDimension, PartialsHoldStage,
} from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { BarList, BarRow } from '../../../ui/bar-list';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { Histogram, HistogramBin } from '../../../ui/histogram';
import { Panel } from '../../../ui/layout';
import { LineChart, LineChartSeries } from '../../../ui/line-chart';
import { PanelError } from '../../../ui/panel-error';
import { PanelHeader } from '../../../ui/panel-header';
import { SegmentOption, Segmented } from '../../../ui/segmented';
import { ShareBar, ShareSegment } from '../../../ui/share-bar';
import { StatTile, StatTone } from '../../../ui/stat-tile';
import { StripGroup, StripPlot } from '../../../ui/strip-plot';
import { Waterfall, WaterfallStep } from '../../../ui/waterfall';

/* v142 — Partials: does the runner earn its keep, and where would a different
 * TP2 or split have landed? Descriptive only: the live book is a small,
 * non-pre-registered sample, so nothing on this tab is a gate. Every figure
 * is computed server-side (`swingbot/core/analytics/partials.py`); the
 * helpers below only shape it for the existing chart primitives. */

export interface PartialsTile {
  label: string; value: string; sample: number | null; tone: StatTone; hint: string; hero: boolean;
}

const STAGES: Record<string, string> = {
  filled: 'Filled', tp1: 'Hit TP1', runner_closed: 'Runner closed', tp2: 'Hit TP2',
};
const BUCKETS: Record<PartialsBucket, { label: string; tone: NonNullable<ShareSegment['tone']> }> = {
  tp2: { label: 'TP2', tone: 'pos' }, trail: { label: 'Trail', tone: 'accent' },
  floor: { label: 'Floor', tone: 'neg' }, stall: { label: 'Stall', tone: 'warn' },
  time: { label: 'Time', tone: 'warn' }, manual: { label: 'Manual', tone: 'muted' },
  no_tp2: { label: 'No TP2', tone: 'muted' }, open: { label: 'Open', tone: 'muted' },
  other: { label: 'Unrecorded', tone: 'warn' },
};
const HOLDS: [PartialsHoldStage, string][] = [
  ['entry_tp1', 'Entry → TP1'], ['tp1_exit', 'TP1 → exit'], ['entry_exit', 'Entry → exit'],
];
export const DIMENSIONS: SegmentOption[] = [
  { value: 'strategy', label: 'Strategy' }, { value: 'horizon', label: 'Horizon' },
  { value: 'side', label: 'Side' }, { value: 'month', label: 'Month' },
];
const GIVEBACK_BIN = 0.5;

export const pctText = (v: number | null): string => (v === null ? '—' : `${v.toFixed(1)}%`);
export const rText = (v: number | null): string =>
  (v === null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}R`);
const signTone = (v: number | null, pivot: number): StatTone =>
  (v === null || v === pivot ? 'neutral' : v > pivot ? 'pos' : 'neg');

export function kpiTiles(p: AnalyticsPartials): PartialsTile[] {
  const k = p.kpis;
  const held = k.median_tp1_exit_sessions === null ? '—' : `${k.median_tp1_exit_sessions} sessions`;
  return [
    { label: 'TP1 rate', value: pctText(k.tp1_rate), sample: k.tp1_rate_n, tone: 'neutral',
      hint: 'Partial trades ÷ filled trades no longer open before TP1', hero: false },
    { label: 'TP1 → TP2', value: pctText(k.tp1_tp2_rate), sample: k.tp1_tp2_n, tone: 'neutral',
      hint: 'Closed runners that reached TP2 (plans without a TP2 excluded)', hero: false },
    { label: 'Runner beat all-out', value: pctText(k.beat_all_out), sample: k.beat_all_out_n,
      tone: signTone(k.beat_all_out, 50), hint: 'Closed runners whose blended R beat closing 100% at TP1', hero: true },
    { label: 'Mean runner ΔR', value: rText(k.mean_runner_delta_r), sample: k.beat_all_out_n,
      tone: signTone(k.mean_runner_delta_r, 0), hint: 'Blended R minus all-out R, per closed runner', hero: false },
    { label: 'Median TP1 → exit', value: held, sample: k.tp1_exit_n, tone: 'neutral',
      hint: 'Trading sessions the runner was held', hero: false },
  ];
}

export function funnelRows(p: AnalyticsPartials): BarRow[] {
  const filled = p.funnel[0]?.n ?? 0;
  return p.funnel.map((step) => ({
    label: STAGES[step.stage] ?? step.stage, value: filled ? (step.n / filled) * 100 : null, n: step.n,
  }));
}

export function outcomeSegments(p: AnalyticsPartials): ShareSegment[] {
  return p.outcomes.map((o) => ({
    label: `${BUCKETS[o.bucket]?.label ?? o.bucket} ${rText(o.avg_runner_r)}`,
    count: o.n, tone: BUCKETS[o.bucket]?.tone ?? 'warn',
  }));
}

/** All-out ExpR, then what holding the runner added (or cost); the waterfall's
 *  own total bar is the actual ExpR. */
export function runnerWaterfall(p: AnalyticsPartials): WaterfallStep[] {
  const { all_out_exp_r: allOut, actual_exp_r: actual } = p.counterfactuals;
  if (allOut === null || actual === null) return [];
  return [{ label: 'All-out at TP1', value: allOut }, { label: 'Runner contribution', value: actual - allOut }];
}

/** One bar per TP2 level: the counterfactual ExpR had TP2 sat there. The
 *  actual setup is the last row, "Actual", so every level reads against it on
 *  the same signed axis (BarList draws a reference marker only in rate mode). */
export function ladderRows(p: AnalyticsPartials): BarRow[] {
  const cf = p.counterfactuals;
  const rows: BarRow[] = cf.ladder.map((row) => ({
    label: `TP2 at ${row.level_r.toFixed(1)}R`, value: row.cf_exp_r, n: row.n,
  }));
  return [...rows, { label: 'Actual', value: cf.actual_exp_r, n: p.kpis.beat_all_out_n }];
}

export function touchRows(p: AnalyticsPartials): BarRow[] {
  return p.counterfactuals.ladder.map((row) => ({ label: `${row.level_r.toFixed(1)}R`, value: row.touch_rate, n: row.n }));
}

export function splitRows(p: AnalyticsPartials): BarRow[] {
  return p.counterfactuals.split.map((row) => ({
    label: `${Math.round(row.fraction * 100)}% at TP1`, value: row.exp_r, n: row.n,
  }));
}

export function givebackBins(values: readonly number[]): HistogramBin[] {
  if (!values.length) return [];
  const bin = (v: number): number => Math.floor(v / GIVEBACK_BIN);
  const bins: HistogramBin[] = [];
  for (let i = bin(Math.min(...values)); i <= bin(Math.max(...values)); i++) {
    const from = i * GIVEBACK_BIN;
    bins.push({
      label: `${from.toFixed(1)}–${(from + GIVEBACK_BIN).toFixed(1)}R`,
      count: values.filter((v) => bin(v) === i).length,
    });
  }
  return bins;
}

export function holdGroups(p: AnalyticsPartials): StripGroup[] {
  return HOLDS.map(([stage, label]) => {
    const h = p.holds[stage];
    const iqr = h.p25 === null ? '' : ` (IQR ${h.p25}–${h.p75})`;
    return { label: `${label}${iqr}`, values: h.points, tone: 'accent' as const };
  });
}

export function monthTrend(rows: readonly PartialsBreakdownRow[]): LineChartSeries[] {
  const points = rows
    .filter((row) => row.beat_all_out !== null)
    .map((row) => ({ date: `${row.key}-01`, value: row.beat_all_out as number }));
  return [{ name: 'Runner beat all-out %', points }];
}

@Component({
  selector: 'sb-partials-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, PanelError, StatTile, BarList, ShareBar, Waterfall, LineChart,
    Histogram, StripPlot, Segmented, EmptyStateComponent],
  template: `
    @if (store.partialsError(); as error) {
      <sb-panel-error [message]="error" (retry)="store.reload('partials')" />
    } @else if (data(); as p) {
      @if (p.population.partial === 0) {
        <sb-empty-state title="No partial trades in this scope" reason="measured-zero"
          hint="No filled trade reached TP1 here. Widen the date range or clear a filter." />
      } @else {
        <div class="kpis">@for (tile of tiles(); track tile.label) {
          <div class="tile" [class.hero]="tile.hero">
            <sb-stat-tile [label]="tile.label" [value]="tile.value" [sample]="tile.sample" [tone]="tile.tone" [hint]="tile.hint" />
          </div>
        }</div>
        <div class="panels">
          <sb-panel><sb-panel-header title="Funnel" [n]="p.n" hint="Share of filled trades reaching each stage." />
            <sb-bar-list [rows]="funnel()" mode="rate" [format]="pctFmt" /></sb-panel>
          <sb-panel><sb-panel-header title="Runner outcome mix" [n]="p.population.partial" hint="How each runner ended, with its average runner R." />
            <sb-share-bar label="Runner outcomes" [segments]="outcomes()" /></sb-panel>
          <sb-panel><sb-panel-header title="Does the runner pay?" [n]="p.kpis.beat_all_out_n" hint="ExpR had 100% closed at TP1, plus what holding the runner added." />
            <sb-waterfall [steps]="waterfall()" [format]="rFmt" totalLabel="Actual ExpR" /></sb-panel>
          <sb-panel><sb-panel-header title="TP2 ladder" [n]="ladderN()" hint="Counterfactual ExpR with TP2 at each R level; the last row is the actual ExpR. Below: share of runners that touched each level." />
            <sb-bar-list [rows]="ladder()" [format]="rFmt" />
            <sb-bar-list [rows]="touches()" mode="rate" [format]="pctFmt" /></sb-panel>
          <sb-panel><sb-panel-header title="Split what-if" [n]="p.kpis.beat_all_out_n" hint="ExpR had a different share been taken at TP1, from each trade's own two legs." />
            <sb-bar-list [rows]="split()" [format]="rFmt" /></sb-panel>
          <sb-panel><sb-panel-header title="Giveback" [n]="p.counterfactuals.giveback.length" hint="Best R the runner saw minus the R it banked." />
            <sb-histogram [bins]="giveback()" /></sb-panel>
          <sb-panel class="wide"><sb-panel-header title="Hold times" [n]="p.population.partial" hint="Trading sessions per stage; open runners count only before TP1." />
            <sb-strip-plot [groups]="holds()" unit=" sessions" /></sb-panel>
          <sb-panel class="wide"><sb-panel-header title="Breakdown" [n]="p.population.partial" [hint]="thinHint()" />
            <sb-segmented label="Group by" [options]="dimensions" [value]="dimension()" (valueChange)="dimension.set($any($event))" />
            @if (dimension() === 'month') { <sb-line-chart [series]="trend()" [valueFormat]="pctFmt" /> }
            <table class="breakdown">
              <thead><tr><th>{{ dimensionLabel() }}</th><th>N</th><th>TP1 rate</th><th>TP1 → TP2</th><th>Beat all-out</th><th>Mean ΔR</th><th>Median TP1 → exit</th></tr></thead>
              <tbody>@for (row of rows(); track row.key) {
                <tr [class.thin]="row.thin">
                  <td>{{ row.key }}</td><td class="num">{{ row.n }}</td><td class="num">{{ pctFmt(row.tp1_rate) }}</td>
                  <td class="num">{{ pctFmt(row.tp1_tp2_rate) }}</td><td class="num">{{ pctFmt(row.beat_all_out) }}</td>
                  <td class="num">{{ rFmt(row.mean_runner_delta_r) }}</td><td class="num">{{ row.median_tp1_exit_sessions ?? '—' }}</td>
                </tr>
              }</tbody>
            </table></sb-panel>
        </div>
        <p class="footer">{{ footer() }}</p>
      }
    }
  `,
  styles: `:host{display:grid;gap:var(--space-14)}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:var(--space-10)}.tile.hero{outline:1px solid var(--accent);border-radius:var(--radius)}.panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-14)}.wide{grid-column:1/-1}.breakdown{width:100%;border-collapse:collapse;font-size:var(--text-table);margin-top:var(--space-10)}.breakdown th,.breakdown td{padding:var(--space-4) var(--space-8);text-align:left;border-bottom:1px solid var(--border)}.breakdown .num{text-align:right;font-variant-numeric:tabular-nums}.breakdown tr.thin td{color:var(--text-faint)}.footer{margin:0;font-size:var(--text-micro);color:var(--text-faint)}@media(max-width:639px){.panels{grid-template-columns:1fr}}`,
})
export class PartialsTab {
  readonly store = inject(AnalyticsStore);
  readonly data = computed(() => this.store.partials());
  readonly dimensions = DIMENSIONS;
  readonly dimension = signal<PartialsDimension>('strategy');
  readonly pctFmt = (v: number | null): string => pctText(v);
  readonly rFmt = (v: number | null): string => rText(v);

  readonly tiles = computed(() => this.shape(kpiTiles, []));
  readonly funnel = computed(() => this.shape(funnelRows, []));
  readonly outcomes = computed(() => this.shape(outcomeSegments, []));
  readonly waterfall = computed(() => this.shape(runnerWaterfall, []));
  readonly ladder = computed(() => this.shape(ladderRows, []));
  readonly ladderN = computed(() => this.data()?.counterfactuals.ladder[0]?.n ?? 0);
  readonly touches = computed(() => this.shape(touchRows, []));
  readonly split = computed(() => this.shape(splitRows, []));
  readonly giveback = computed(() => givebackBins(this.data()?.counterfactuals.giveback ?? []));
  readonly holds = computed(() => this.shape(holdGroups, []));
  readonly rows = computed(() => this.data()?.breakdowns[this.dimension()] ?? []);
  readonly trend = computed(() => monthTrend(this.data()?.breakdowns.month ?? []));
  readonly thinHint = computed(() => `Rows under N=${this.data()?.thin_n ?? 10} are dimmed: shown, not trusted.`);
  readonly dimensionLabel = computed(() => DIMENSIONS.find((d) => d.value === this.dimension())?.label ?? '');
  readonly footer = computed(() => {
    const p = this.data();
    if (!p) return '';
    const cf = p.counterfactuals;
    return `Population: ${p.population.filled} filled · ${p.population.partial} partial · `
      + `${cf.path_unavailable} closed runners without a price path · `
      + `${cf.runner_r_unavailable} manual runners without a price · live book only — not a gate.`;
  });

  /** One payload, many shapes: every panel reads the same response. */
  private shape<T>(fn: (p: AnalyticsPartials) => T, empty: T): T {
    const p = this.data();
    return p ? fn(p) : empty;
  }
}
```

- [ ] **Step 4: Register it in the shell**

In `frontend/src/app/workspaces/analytics/analytics.ts`:

1. After `import { OverviewTab } from './tabs/overview';` add `import { PartialsTab } from './tabs/partials';`
2. `  imports: [TabBar, ScopeBar, OverviewTab, AttributionTab, ExecutionTab, EdgeTab, PipelineTab, TuningTab],` → `  imports: [TabBar, ScopeBar, OverviewTab, AttributionTab, ExecutionTab, EdgeTab, PipelineTab, TuningTab, PartialsTab],`
3. After `      @case ('tuning') { <sb-tuning-tab /> }` add `      @case ('partials') { <sb-partials-tab /> }`
4. After `    { id: 'pipeline', label: 'Pipeline' }, { id: 'tuning', label: 'Tuning' },` add `    { id: 'partials', label: 'Partials' },`
5. In the class doc comment, ` * Analytics — six tabs in the order a trader asks (spec v94 D1), one scope` → ` * Analytics — seven tabs in the order a trader asks (spec v94 D1; v142 adds` + newline + ` * Partials last), one scope`

- [ ] **Step 5: Update the feature doc**

In `docs/features/features-admin.md`, replace `**The Analytics workspace is six tabs, in the order a trader asks** (spec` with `**The Analytics workspace is seven tabs, in the order a trader asks** (spec`. Replace `is the model calibrated), **Pipeline** (what is coming), **Tuning**` + newline + `(operations).` with:

```markdown
is the model calibrated), **Pipeline** (what is coming), **Tuning**
(operations), **Partials** (v142: does the runner earn its keep — TP1→TP2
conversion, runner-beat-all-out, the TP2-ladder / split / giveback
counterfactuals and hold times, from the `runner_path` stamp; live book only,
never a gate).
```

- [ ] **Step 6: Run the specs to verify they pass**

```bash
npx ng test --include src/app/workspaces/analytics/tabs/partials.spec.ts --include src/app/workspaces/analytics/analytics.spec.ts
```

Expected: 2 files passed (18 tests). `sb-line-chart` appears only for the month trend.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/partials.ts frontend/src/app/workspaces/analytics/tabs/partials.spec.ts frontend/src/app/workspaces/analytics/analytics.ts frontend/src/app/workspaces/analytics/analytics.spec.ts docs/features/features-admin.md
git commit -m "$(cat <<'EOF'
feat(v142): Partials analytics tab -- KPIs, funnel, counterfactuals, holds, breakdown

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

# Phase 5 — Verification and production

## Parallelisation

Sequential throughout. V142-10 verifies everything once. V142-11 needs the verified branch merged and deployed: the backfill must write the same shape the deployed live stamp writes.

### Task V142-10: Full-suite verification

**Files:** none changed unless a regression is found.

- [ ] **Step 1: Python, once**

Dispatch the `test-runner` subagent (or run `python scripts/dev/testrun.py full`) inside the worktree, with `db-test` reachable. Expected: `0 failed`, `0 xfailed`, and no new SKIPPED DB test. A changed pass count is not a failure. Two failures seen while this plan was verified, and how to read them:
- `tests/infra/test_log_tracebacks.py`: an `except` that logs without `exc_info=True`. This is a real regression; fix forward. (`runner_path.stamp_runner_path` already carries it.)
- `tests/admin/test_api_v1_system_settings.py::test_omitted_keys_are_left_alone` with `PermissionError: [WinError 5]` on `os.replace(... .env)`. This is a Windows file-lock flake under `-n 4`. Re-run that one file. If it passes alone, it is not this plan's.

- [ ] **Step 2: Frontend, once**

`npm test` from `frontend/` (no `--include`). Expected: every file passed.

- [ ] **Step 3: If `calendar.spec.ts` fails to build (TS2739, `plan_id`, `opened_at`)**

That break predates this plan: it is on `main` at `bba72100`, and it is why the whole Angular test build stops. Check `git log main -- frontend/src/app/workspaces/calendar/calendar.spec.ts` for a fix that landed since. If it is fixed, merge `main` into the branch and re-run Step 2. If not, **ask the partner** (`AskUserQuestion`). The recommended option is to fix it here, in its own commit `test(calendar): add plan_id/opened_at to the TRADE fixture`, adding `plan_id: null, opened_at: null,` to the `TRADE` literal, because the gate needs a green build. Do not fold the fix into a v142 commit.

- [ ] **Step 4: Complexity, over every touched Python file**

```bash
python -m radon cc -s -n C swingbot/core/analytics/runner_path.py swingbot/core/analytics/partials.py scripts/data/backfill_runner_path.py swingbot/admin/api_v1/trade_commands.py swingbot/admin/api_v1/analytics.py swingbot/core/planning/plan_manager.py
```

Expected: nothing at 15 or above that this plan wrote or changed. Only the legacy `analytics_by_dimension` E (33), `analytics_performance` C (17), `analytics_heat_grid` C (16), `analytics_strategies` C (15), `_step_active` D (21), `poll` C (20) and `_on_event` C (15) may appear, none of which this plan touched.

**If either suite is not green, fix forward from those failures.** They are this plan's regressions, and the task is not done until both runs are green.

### Task V142-11: Merge, deploy, and the production backfill

**Files:** none (production data only; the script is already committed).

- [ ] **Step 1: Merge and deploy**

Follow the `worktree-lifecycle` skill to merge `2026-10-08-v142-partials-analytics-tab` into `main` (check for concurrent sessions first). Push `main`. The "Deploy Discord Swing Trade Bot to Hetzner" workflow deploys it. Watch it with `gh run watch` until it succeeds. Do not re-run either suite after a conflict-free merge.

- [ ] **Step 2: Confirm production runs the new code**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c 'from swingbot.core.analytics.runner_path import LADDER_R; from scripts.data import backfill_runner_path; print(LADDER_R)'"
```

Expected: `(1.5, 2.0, 2.5, 3.0, 4.0)`.

- [ ] **Step 3: Re-check the cache (read-only)**

Re-run V142-0's probe exactly as in V142-0 Step 3. Expected: `missing from market_data/daily: []`. If any ticker is missing, the backfill counts those plans as `unavailable`. Note them, and do not fetch.

- [ ] **Step 4: Back up, then dry run**

Use the `mirror-prod` skill first. The backfill writes production data through a committed script, so there is nothing to mirror back, but the skill's checks still apply.

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash scripts/ops/backup_db.sh"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_runner_path.py"
```

Expected: `DRY RUN: stamped=S skipped=K unavailable=U` and `Dry run only -- pass --apply to write.` S + K + U equals the closed partial plans: 189 on 2026-10-08, plus any closed since. K counts plans the deployed live stamp already wrote. Record the three numbers.

- [ ] **Step 5: Apply, then prove idempotence**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_runner_path.py --apply"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_runner_path.py"
```

Expected: the first prints `APPLIED: stamped=S ...` with the same S as the dry run, unless a runner closed in between. The second prints `DRY RUN: stamped=0 skipped=S+K unavailable=U`.

- [ ] **Step 6: Spot-check the endpoint's population**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -c 'from swingbot.core.analytics import partials as pa; from swingbot.core.analytics.scope import BookScope; from swingbot.core.planning.plan_store import PlanStore; r = pa.build_report(pa.select_plans(PlanStore().all(), BookScope())); print(r[\"funnel\"], r[\"population\"], r[\"counterfactuals\"][\"path_unavailable\"], r[\"counterfactuals\"][\"runner_r_unavailable\"])'"
```

Expected: a funnel whose `tp1` count matches the main-ledger partials, and `path_unavailable` = U (main ledger only). This call passes no `manual_exits`, so `runner_r_unavailable` equals the main-ledger manual runners (16 across both ledgers on 2026-10-08). The endpoint itself prices them from the trades table.

- [ ] **Step 7: Record and close out**

Append the dry-run, apply and re-run counts, plus the date, to `.superpowers/sdd/progress.md`. They also go in the close-out commit message. Then run `/close-out` (`Bump: ui minor · bot patch`; the release task resolves the numbers from `VERSION.json` on disk). If U > 0, list those plan ids in the close-out commit body, so a later session can see which history the ladder cannot cover.
