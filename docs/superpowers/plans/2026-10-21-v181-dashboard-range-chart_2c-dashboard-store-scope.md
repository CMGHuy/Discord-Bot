# v181 — Dashboard range chart: Part 2c — the `DashboardStore` scope (V181-13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V181-13:" -A 400 <this file>`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-10-21-v181-dashboard-range-chart-design.md](../specs/2026-10-21-v181-dashboard-range-chart-design.md)
**Index:** [2026-10-21-v181-dashboard-range-chart_0-index.md](2026-10-21-v181-dashboard-range-chart_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there and bind every task below.

**Order:** this part was split off part 2a for the 1500-line limit. Its one task, V181-13, runs **after** V181-12 (part 2a) and **before** V181-14 (part 2b), which consumes the store members it creates — the file letter is not the run order.

Spec sections covered: § 1 (the preset persists, an ad-hoc Range never does), § 6 (rolling presets recompute on every refresh), § 7 (`DashboardStore` owns the scope, `stale` and the debounced refetch with its latest-request guard), § 8 (pan → `setRange`, debounced ~300 ms; preset → store → chart), § 9 (a failed range refetch keeps the last KPIs, marked stale).

Work in the worktree `.claude/worktrees/2026-10-21-v181-dashboard-range-chart` (created in V181-1); every path below is relative to its root.

**Frontend runner:** `cd frontend && npx ng test --include <spec> --watch=false` — never bare `npx vitest run`. A run that dies after exactly 60 s with `Timeout waiting for worker to respond` ran nothing: re-run it (`docs/claude/testing-cost.md` § Frontend).

---

# Phase 4 — Range scope: client model and store (continued)

### Task V181-13: `DashboardStore` scope selection, range refetch, stale

**Model:** sonnet — one store's state reshaped around a selection, with a debounce, a latest-request guard and a preference restore whose ordering against the first load is easy to get wrong; every path has a spec.

**Files:**
- Modify: `frontend/src/app/stores/dashboard.store.ts` (imports lines 1-17; `DashboardSlice` lines 19-27; `withState` lines 76-84; `withComputed` from line 85; `withMethods` lines 211-228; `withHooks` lines 229-262)
- Modify: `frontend/src/app/stores/dashboard.store.spec.ts` (imports lines 1-24; the `beforeEach` providers lines 85-104; a new `describe` appended inside `describe('DashboardStore')`)

**Interfaces:**
- Consumes (V181-12): from `frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts` — `ScopePreset`, `ScopeSelection`, `ChartTarget`, `TimeWindow`, `scopeToRequest(scope, now) -> { mode, window }`, `chartWindowFor(preset, now) -> TimeWindow | null`; from `frontend/src/app/ui/equity-chart-prefs.ts` — `readScopePreset(prefs)`, `writeScopePreset(prefs, preset) -> Preferences`; `ApiClient.dashboard(mode?, window?)`. Existing: `PreferencesStore` (`values()`, `isLoaded()`, `update(mutate)`), `routeRequest`, `ApiError`.
- Produces (V181-14's controls and Closed tab, V181-15's two-way link):
  - State `selection: ScopeSelection` (initially `{ kind: 'preset', preset: '1D' }`), `stale: boolean`, `targetSeq: number` (initially 0), and `requestWindow: TimeWindow | null` (the window the latest request was sent with; read through `closedWindow`).
  - Computed `scope: DashboardScope` (`today` / `all` / `range`), `preset: ScopePreset | null` (null under a Range), `closedWindow: TimeWindow | null` (the KPI request's window: null for 1D and All), `chartTarget: ChartTarget` (`{ window: chartWindowFor(preset) or the Range's own window, seq: targetSeq }`; `seq` 0 means no move has been asked for).
  - `setPreset(preset: ScopePreset): void` — always bumps `targetSeq` (re-choosing the current preset recentres the chart); when the preset differs, writes `dashboard.scope.preset` and refetches; cancels a Range still settling.
  - `setRange(window: TimeWindow): void` — debounced `RANGE_DEBOUNCE_MS = 300`, then selects the Range and refetches; never writes the preference, never bumps `targetSeq`; a window equal to the current Range is ignored.
  - `setScope(scope: DashboardScope): void` kept for the current toggle: `all` → `setPreset('All')`, anything else → `setPreset('1D')`.
  - `adoptStoredPreset(preset: ScopePreset): void` — called once by `onInit` when preferences have loaded; a no-op once the partner has chosen.
  - Exported const `RANGE_DEBOUNCE_MS = 300`.

**Rules (spec § 1, § 6-§ 9):** the preset is restored from preferences, the Range never is. Every request recomputes its window from `new Date()`, so a rolling preset follows the New York day on the next scan refresh. A response from a superseded request is dropped (latest-request counter, the `EquityCandlesStore` pattern). A failed refetch with figures on screen keeps them and sets `stale`; a failed first load sets only `error` (flow unchanged); any success clears `stale`. The selection is read `untracked` inside `resolve()`, so the onInit effect never refetches on a selection change on top of the method's own refetch.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/stores/dashboard.store.spec.ts`, extend the imports:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
```

```ts
import { Dashboard, Preferences } from '../api/models';
import { DashboardStore, RANGE_DEBOUNCE_MS } from './dashboard.store';
import { PreferencesStore } from './preferences.store';
```

Above `describe('DashboardStore', …)`, add the preferences fake (a signal, so a restored preset and a write behave as against the real store, and no request leaves for `/preferences` — `backend.verify()` would see it):

```ts
/** Signal-backed PreferencesStore fake, as in equity-candles.store.spec.ts. */
const stored = signal<Preferences>({});
const preferencesFake = {
  values: () => stored(),
  isLoaded: () => true,
  update: (mutate: (p: Preferences) => Preferences) => stored.update(mutate),
};
```

In the `beforeEach`, reset it first and provide it:

```ts
  beforeEach(() => {
    stored.set({});
    events = new FakeEventStream();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: events },
        { provide: PreferencesStore, useValue: preferencesFake },
        DashboardStore,
      ],
    });
```

(the two lines after it — `store = …`, `backend = …` — are unchanged). Append inside `describe('DashboardStore')`, after `describe('the date scope')`:

```ts
  /* -- v181: presets, Range, stale -------------------------------------- */

  describe('the v181 scope selection', () => {
    // Wed 21 Oct 2026, 10:00 New York. Presets snap to New York midnights.
    const NOW = new Date('2026-10-21T14:00:00Z');
    const TO = '2026-10-22T04:00:00.000Z';
    const W1 = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
    const W2 = { from: '2026-09-10T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
    const dashboardRequests = () => backend.match((req) => req.url === '/api/v1/dashboard');
    const one = () => backend.expectOne((req) => req.url === '/api/v1/dashboard');

    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(NOW);
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('starts on 1D with no window and no chart move', () => {
      tick();
      expect(one().request.params.get('mode')).toBe('today');
      expect(store.selection()).toEqual({ kind: 'preset', preset: '1D' });
      expect(store.preset()).toBe('1D');
      expect(store.closedWindow()).toBeNull();
      expect(store.chartTarget().seq).toBe(0);
      expect(store.stale()).toBe(false);
    });

    it('restores the stored preset before the first load, in one request', () => {
      stored.set({ 'dashboard.scope.preset': '3M' });
      tick();
      const request = one();
      expect(request.request.params.get('mode')).toBe('range');
      expect(request.request.params.get('from')).toBe('2026-07-21T04:00:00.000Z');
      expect(request.request.params.get('to')).toBe(TO);
      request.flush(RESPONSE);
      expect(store.preset()).toBe('3M');
      expect(store.scope()).toBe('range');
      expect(store.closedWindow()).toEqual({ from: '2026-07-21T04:00:00.000Z', to: TO });
      expect(store.chartTarget()).toEqual({ window: { from: '2026-07-21T04:00:00.000Z', to: TO }, seq: 1 });
      backend.verify();
    });

    it('setPreset writes the preference, refetches with the window and moves the chart', () => {
      tick();
      respond();
      store.setPreset('5D');
      const request = one();
      expect(request.request.params.get('from')).toBe('2026-10-15T04:00:00.000Z');
      expect(request.request.params.get('to')).toBe(TO);
      expect(stored()['dashboard.scope.preset']).toBe('5D');
      expect(store.chartTarget().seq).toBe(1);
    });

    it('maps 1D and All onto today and all, with no window for the Closed tab', () => {
      tick();
      respond();
      store.setPreset('All');
      const request = one();
      expect(request.request.params.get('mode')).toBe('all');
      expect(request.request.params.has('from')).toBe(false);
      expect(store.closedWindow()).toBeNull();
      expect(store.chartTarget().window).toBeNull();
    });

    it('re-choosing the current preset recentres the chart without a refetch or a write', () => {
      tick();
      respond();
      store.setPreset('1D');
      expect(store.chartTarget().seq).toBe(1);
      expect(stored()).toEqual({});
      backend.verify();
    });

    it('setRange waits 300 ms of quiet, then selects the Range without persisting or moving', () => {
      expect(RANGE_DEBOUNCE_MS).toBe(300);
      tick();
      respond();
      store.setRange(W1);
      vi.advanceTimersByTime(200);
      store.setRange(W2);
      vi.advanceTimersByTime(299);
      expect(dashboardRequests()).toHaveLength(0);
      vi.advanceTimersByTime(1);
      const request = one();
      expect(request.request.params.get('mode')).toBe('range');
      expect(request.request.params.get('from')).toBe(W2.from);
      expect(store.selection()).toEqual({ kind: 'range', window: W2 });
      expect(store.preset()).toBeNull();
      expect(store.closedWindow()).toEqual(W2);
      expect(store.chartTarget()).toEqual({ window: W2, seq: 0 });
      expect(stored()).toEqual({});
    });

    it('ignores a Range equal to the one already selected', () => {
      tick();
      respond();
      store.setRange(W1);
      vi.advanceTimersByTime(RANGE_DEBOUNCE_MS);
      one().flush(RESPONSE);
      store.setRange({ ...W1 });
      vi.advanceTimersByTime(RANGE_DEBOUNCE_MS);
      backend.verify();
    });

    it('a preset click cancels a Range still settling', () => {
      tick();
      respond();
      store.setRange(W1);
      store.setPreset('1M');
      one().flush(RESPONSE);
      vi.advanceTimersByTime(RANGE_DEBOUNCE_MS);
      backend.verify();
      expect(store.preset()).toBe('1M');
    });

    it('drops the response of a superseded request', () => {
      tick();
      respond();
      store.setPreset('All');
      store.setPreset('5D');
      const [first, second] = dashboardRequests();
      second.flush({ ...RESPONSE, account_balance: 2 });
      first.flush({ ...RESPONSE, account_balance: 1 });
      expect(store.balance()).toBe(2);
    });

    it('recomputes a rolling preset on every refresh, so it follows the New York day', () => {
      tick();
      respond();
      store.setPreset('1M');
      one().flush(RESPONSE);
      vi.setSystemTime(new Date('2026-10-22T05:00:00Z'));   // 01:00 New York, 22 Oct
      store.load();
      const request = one();
      expect(request.request.params.get('from')).toBe('2026-09-22T04:00:00.000Z');
      expect(request.request.params.get('to')).toBe('2026-10-23T04:00:00.000Z');
    });

    it('keeps the last figures, marked stale, when a range refetch fails; a success clears it', () => {
      tick();
      respond();
      store.setPreset('3M');
      one().error(new ProgressEvent('error'), { status: 0 });
      expect(store.balance()).toBe(10_000);
      expect(store.stale()).toBe(true);
      expect(store.preset()).toBe('3M');

      store.load();
      one().flush(RESPONSE);
      expect(store.stale()).toBe(false);
      expect(store.error()).toBeNull();
    });

    it('a failed first load is an error, not stale', () => {
      tick();
      one().error(new ProgressEvent('error'), { status: 0 });
      expect(store.stale()).toBe(false);
      expect(store.error()).not.toBeNull();
    });

    it('keeps setScope for the Today / All days toggle', () => {
      tick();
      respond();
      store.setScope('all');
      one().flush({ ...RESPONSE, scope: { mode: 'all' } });
      expect(store.preset()).toBe('All');
      expect(store.scope()).toBe('all');
      expect(stored()['dashboard.scope.preset']).toBe('All');
    });
  });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx ng test --include src/app/stores/dashboard.store.spec.ts --watch=false`
Expected: FAIL — `RANGE_DEBOUNCE_MS` is not exported, `store.selection` / `setPreset` / `setRange` / `stale` / `chartTarget` do not exist. The pre-existing tests still pass with the fake provided.

- [ ] **Step 3: Rework the store**

In `frontend/src/app/stores/dashboard.store.ts`, replace the imports (lines 1-17) with:

```ts
import { computed, effect, inject, untracked } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { EventStream } from '../api/event-stream';
import { Observable, Subject, debounceTime, defer } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { routeRequest } from '../routing/route-request';
import { Dashboard, DashboardScope } from '../api/models';
import { readScopePreset, writeScopePreset } from '../ui/equity-chart-prefs';
import {
  ChartTarget,
  ScopePreset,
  ScopeSelection,
  TimeWindow,
  chartWindowFor,
  scopeToRequest,
} from '../workspaces/dashboard/panels/equity-range.model';
import { PreferencesStore } from './preferences.store';
```

Replace `DashboardSlice` with:

```ts
interface DashboardSlice {
  data: Dashboard | null;
  loading: boolean;
  error: string | null;
  /** SR58, reshaped by v181 -- what the panel is scoped to: a preset (1D,
   *  5D … All) or a Range the partner dragged or zoomed to. A fetch input,
   *  so it lives here: the server does the date filtering. `scope` is
   *  derived from it. */
  selection: ScopeSelection;
  /** The window the latest request was sent with (null for 1D and All). The
   *  Closed tab reads it through `closedWindow`, so the table under the KPI
   *  cards always asks for the window the cards were asked for. */
  requestWindow: TimeWindow | null;
  /** A refetch failed while figures were on screen: they are kept, dimmed,
   *  with a stale hint (spec v181 § 9). Never set by a failed first load. */
  stale: boolean;
  /** Bumped on every programmatic chart move (a preset click, a restored
   *  preset); the chart moves when it changes. 0 = nothing asked yet. */
  targetSeq: number;
}

/** How long a pan or zoom must settle before the KPIs refetch (spec § 8). */
export const RANGE_DEBOUNCE_MS = 300;

const NOT_RESPONDING = 'The admin is not responding.';

function sameWindow(selection: ScopeSelection, window: TimeWindow): boolean {
  return selection.kind === 'range'
    && selection.window.from === window.from && selection.window.to === window.to;
}

function isPreset(selection: ScopeSelection, preset: ScopePreset): boolean {
  return selection.kind === 'preset' && selection.preset === preset;
}

function failure(hadData: boolean, error: ApiError): Partial<DashboardSlice> {
  return {
    loading: false,
    stale: hadData,
    error: error.code === 'unavailable' ? NOT_RESPONDING : error.message,
  };
}
```

Replace the `withState` initial value line (`data: null, loading: false, error: null, scope: 'today',`) — keep the comment block above it, and append to it one line: `// v181: 'today' is now the 1D preset, 'all' the All preset.` — with:

```ts
    data: null, loading: false, error: null,
    selection: { kind: 'preset', preset: '1D' },
    requestWindow: null, stale: false, targetSeq: 0,
```

Change `withComputed(({ data }) => ({` to `withComputed(({ data, selection, requestWindow, targetSeq }) => ({` and add, directly after the `empty` computed:

```ts
    /* -- v181: the scope selection ---------------------------------------- */

    /** The `/dashboard` mode the selection maps to: 1D -> `today`, All ->
     *  `all`, every other preset and a Range -> `range`. */
    scope: computed<DashboardScope>(() => scopeToRequest(selection(), new Date()).mode),

    /** The chosen preset, or null under a hand-picked Range. */
    preset: computed<ScopePreset | null>(() => {
      const current = selection();
      return current.kind === 'preset' ? current.preset : null;
    }),

    /** The Closed tab's window: the latest KPI request's (null for 1D/All,
     *  where the tab keeps its `today` flag or no filter). */
    closedWindow: computed(() => requestWindow()),

    /** Where the chart should move, and a sequence number that changes only
     *  for a programmatic move. Under a Range the window is the Range itself
     *  and `seq` does not move, so a hand pan never moves the chart back. */
    chartTarget: computed<ChartTarget>(() => {
      const current = selection();
      const window = current.kind === 'preset'
        ? chartWindowFor(current.preset, new Date())
        : current.window;
      return { window, seq: targetSeq() };
    }),
```

Replace the whole `withMethods(…)` block with:

```ts
  withMethods((store, api = inject(ApiClient), prefs = inject(PreferencesStore)) => {
    let latestRequest = 0;
    // Bumped by a preset click, so a Range still inside its debounce never
    // lands on top of the preset the partner chose after it.
    let rangeGeneration = 0;
    let chosen = false;
    const ranges = new Subject<{ window: TimeWindow; generation: number }>();

    // `defer`: the request number and the window are taken when the route
    // resolver or a method subscribes. `untracked`: `load()` runs inside the
    // onInit effect, and a tracked read would refetch on every selection
    // change on top of the method's own refetch.
    const resolve = (): Observable<void> => defer(() => {
      const request = ++latestRequest;
      const current = (): boolean => request === latestRequest;
      const { mode, window } = scopeToRequest(untracked(() => store.selection()), new Date());
      return routeRequest(api.dashboard(mode, window), {
        start: () => patchState(store, { loading: true, requestWindow: window }),
        next: (data) => {
          if (current()) patchState(store, { data, loading: false, error: null, stale: false });
        },
        error: (error) => {
          if (current()) patchState(store, failure(untracked(() => store.data()) !== null, error));
        },
      });
    });

    const refetch = (): void => { resolve().subscribe({ error: () => undefined }); };

    const select = (selection: ScopeSelection): void => {
      patchState(store, { selection });
      refetch();
    };

    const setPreset = (preset: ScopePreset): void => {
      chosen = true;
      rangeGeneration += 1;
      patchState(store, { targetSeq: store.targetSeq() + 1 });
      if (isPreset(store.selection(), preset)) return;
      prefs.update((current) => writeScopePreset(current, preset));
      select({ kind: 'preset', preset });
    };

    ranges.pipe(debounceTime(RANGE_DEBOUNCE_MS), takeUntilDestroyed()).subscribe(
      ({ window, generation }) => {
        if (generation !== rangeGeneration || sameWindow(store.selection(), window)) return;
        select({ kind: 'range', window });
      },
    );

    return {
      resolve,
      load: refetch,
      setPreset,
      /** A user pan or zoom settled on `window` (V181-15 calls this). Never
       *  persisted: a reload returns to the last preset (spec § 1). */
      setRange(window: TimeWindow): void {
        chosen = true;
        ranges.next({ window, generation: rangeGeneration });
      },
      /** The pre-v181 Today / All days toggle, kept until V181-14 replaces it. */
      setScope(scope: DashboardScope): void {
        setPreset(scope === 'all' ? 'All' : '1D');
      },
      /** The preset restored from preferences, once they have loaded. Moves
       *  the chart there; refetches only if a load already went out with the
       *  default. A no-op once the partner has chosen. */
      adoptStoredPreset(preset: ScopePreset): void {
        if (chosen || isPreset(store.selection(), preset)) return;
        patchState(store, { selection: { kind: 'preset', preset }, targetSeq: store.targetSeq() + 1 });
        if (latestRequest > 0) refetch();
      },
    };
  }),
```

In `withHooks`, change the signature to `onInit(store, events = inject(EventStream), prefs = inject(PreferencesStore)) {` and add, as the **first** statement of the body (before `const account = …`), so a preset stored before this page opened is adopted before the first load runs and the first request already carries it:

```ts
      // v181 -- restore the stored preset once preferences are in. Created
      // before the load effect below, so on a warm start (preferences already
      // loaded) it runs first and the initial load asks for the stored scope.
      let adopted = false;
      effect(() => {
        if (adopted || !prefs.isLoaded()) return;
        adopted = true;
        const preset = readScopePreset(prefs.values());
        untracked(() => store.adoptStoredPreset(preset));
      });
```

`appliedScope` and every other computed stay as they are; `appliedScope` still reads `data()?.scope?.mode`.

- [ ] **Step 4: Run the store tests to verify they pass**

Run: `cd frontend && npx ng test --include src/app/stores/dashboard.store.spec.ts --watch=false`
Expected: PASS — the new `describe` and every pre-existing test (`setScope('all')` still sends `mode=all`; `setScope('today')` on 1D still sends nothing).

If `restores the stored preset before the first load` sees two requests, the adoption effect was created after the load effect: move it to the top of `onInit`, never relax the `one()` assertion.

- [ ] **Step 5: Run the dashboard workspace specs**

Run: `cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --watch=false`
Expected: PASS. `dashboard.spec.ts` provides `preferencesStub` (`values`, `isLoaded`, a no-op `update`), so `setScope('all')` still lands on `scope() === 'all'` (line ~271); `dashboard.ts` reads `store.scope()`, now a computed with the same values.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/stores/dashboard.store.ts frontend/src/app/stores/dashboard.store.spec.ts
git commit -m "feat(v181): DashboardStore scope selection -- presets, debounced Range refetch, stale figures" -m "The preset restores from preferences before the first load; a superseded response is dropped." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

