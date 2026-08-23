# UI Elevation (v54) — Part 2: Honest state everywhere

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Index:** `2026-08-23-v54-ui-elevation_0-index.md` — read its Global Constraints first.
**Spec:** `docs/superpowers/specs/2026-08-23-v54-ui-elevation-design.md` (decision D3)

**Goal:** All eight workspaces show a shaped skeleton while fetching, a distinguishable empty, a recoverable error and a visible staleness marker — driven by one component.

**Runs after `_1` merges. Parallel with `_3`** (disjoint files: `_2` edits workspace templates, `_3` edits `tokens.css` and `ui/` numerics).

## The rule this wave must not break

`dashboard.store.ts` records a committed v13 decision:

> *A refetch failure keeps the previous data on screen. Replacing nine live numbers with an error panel because one poll failed is worse than showing slightly stale numbers next to a warning, especially when the event stream reconnects seconds later.*

A naive `[error]="store.error()"` binding destroys that. So this wave fixes the semantics first (Task 13) and only then installs the component:

> **`error` means "there is nothing to show, and here is why". A failed refetch over data that is still on screen is a STALE condition, not an error.**

Task 13 encodes that mapping in one helper so no call site can get it wrong.

## Store shape

Every workspace store is an NgRx `signalStore` following the reference shape in `dashboard.store.ts`: a slice of `{ data, loading, error, … }`, so each exposes `store.data()`, `store.loading()`, `store.error()`. Confirm per store before binding — `grep -n "interface .*Slice" src/app/stores/<name>.store.ts`.

---

### Task 13: `asyncInputs()` — the mapping that preserves the refetch rule

**Files:**
- Modify: `frontend/src/app/ui/async.ts`
- Test: `frontend/src/app/ui/async.spec.ts` (extend)

**Interfaces:**
- Consumes: `Async` from `_1` Task 10.
- Produces:

```ts
export interface AsyncSource<T> {
  data: () => T | null;
  loading: () => boolean;
  error: () => string | null;
}
export interface AsyncInputs {
  loading: boolean;
  error: string | null;
  empty: boolean;
  staleAsOf: string | null;
}
export function asyncInputs<T>(
  source: AsyncSource<T>,
  opts: { isEmpty: (data: T) => boolean; now?: () => Date },
): AsyncInputs;
```

Tasks 14–20 call this instead of binding the store's signals directly.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/app/ui/async.spec.ts`:

```ts
import { asyncInputs } from './async';

const at = () => new Date('2026-08-23T15:42:00');

describe('asyncInputs', () => {
  const src = (data: unknown, loading: boolean, error: string | null) => ({
    data: () => data as never,
    loading: () => loading,
    error: () => error,
  });
  const opts = { isEmpty: (d: unknown[]) => d.length === 0, now: at };

  it('reports a first-load failure as an error', () => {
    expect(asyncInputs(src(null, false, 'boom'), opts))
      .toEqual({ loading: false, error: 'boom', empty: false, staleAsOf: null });
  });

  it('demotes a refetch failure to stale so the numbers stay on screen', () => {
    expect(asyncInputs(src([1], false, 'boom'), opts))
      .toEqual({ loading: false, error: null, empty: false, staleAsOf: '15:42' });
  });

  it('reports loading only while there is nothing to show', () => {
    expect(asyncInputs(src(null, true, null), opts).loading).toBe(true);
    // A background refresh over existing data is not a loading state: the
    // skeleton would blank a screen the reader is already reading.
    expect(asyncInputs(src([1], true, null), opts).loading).toBe(false);
  });

  it('reports empty only once data has actually arrived', () => {
    expect(asyncInputs(src(null, false, null), opts).empty).toBe(false);
    expect(asyncInputs(src([], false, null), opts).empty).toBe(true);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd frontend && npm test -- --include src/app/ui/async.spec.ts`
Expected: FAIL — `asyncInputs` is not exported.

- [ ] **Step 3: Implement it**

Append to `frontend/src/app/ui/async.ts`:

```ts
export interface AsyncSource<T> {
  data: () => T | null;
  loading: () => boolean;
  error: () => string | null;
}

export interface AsyncInputs {
  loading: boolean;
  error: string | null;
  empty: boolean;
  staleAsOf: string | null;
}

/**
 * Maps a store slice onto `sb-async`'s inputs, preserving the v13 refetch rule.
 *
 * `dashboard.store.ts` records it: *a refetch failure keeps the previous data
 * on screen*, because replacing nine live numbers with an error panel over one
 * failed poll is worse than showing slightly stale numbers next to a warning.
 * Binding `[error]="store.error()"` straight through would break that on every
 * screen at once, so the mapping lives here and every call site uses it.
 *
 *   nothing on screen + error  -> error   ("there is nothing to show, and why")
 *   data on screen   + error   -> stale   ("these numbers stopped updating")
 *   nothing on screen + loading -> loading (skeleton)
 *   data on screen   + loading -> neither (a background refresh must not blank
 *                                          a screen the reader is reading)
 */
export function asyncInputs<T>(
  source: AsyncSource<T>,
  opts: { isEmpty: (data: T) => boolean; now?: () => Date },
): AsyncInputs {
  const data = source.data();
  const error = source.error();
  const has = data !== null;

  if (!has) {
    return {
      loading: source.loading(),
      error: source.loading() ? null : error,
      empty: false,
      staleAsOf: null,
    };
  }

  const clock = opts.now ?? (() => new Date());
  const stamp = clock();
  const staleAsOf = error
    ? `${String(stamp.getHours()).padStart(2, '0')}:${String(stamp.getMinutes()).padStart(2, '0')}`
    : null;

  return { loading: false, error: null, empty: opts.isEmpty(data), staleAsOf };
}
```

- [ ] **Step 4: Run and watch it pass**

Run: `cd frontend && npm test -- --include src/app/ui/async.spec.ts`
Expected: PASS, 11 tests (7 from `_1` T10 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/async.ts frontend/src/app/ui/async.spec.ts
git commit -m "feat(v54): asyncInputs maps store slices without breaking the v13 refetch rule"
```

---

### Tasks 14–20: install `sb-async` in each workspace

Each task is one workspace and follows the same five steps, but the **empty reason, empty copy and skeleton shape differ per surface and are stated per task**. Do not copy one workspace's reason into another — that judgement is the whole point of D3.

**Shared step template (applies to Tasks 14–20):**

1. Read the workspace's store slice: `grep -n "interface .*Slice" -A 10 src/app/stores/<name>.store.ts`.
2. Add `Async` and `asyncInputs` to the component's `imports` / imports.
3. Add a `protected readonly async = computed(() => asyncInputs(this.store, { isEmpty: … }))`.
4. Wrap the fetch-backed region, binding from `async()`.
5. Delete the component's own `@if (loading())` / `@if (error())` branches and any `.stale` / `.error` local CSS rule (`_1` T5's gate already forbids the classes; this removes the last of the markup).
6. Run `npm test`, then look at the screen with the network throttled to verify the skeleton does not shift the layout.

**Binding shape, identical everywhere:**

```html
    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      [emptyReason]="'…'"
      [emptyTitle]="'…'"
      [emptyHint]="'…'"
      [skeletonRows]="…"
      [skeletonCols]="…"
      (retry)="store.load()"
    >
      … the existing content …
    </sb-async>
```

---

### Task 14: Dashboard

**Files:** Modify `frontend/src/app/workspaces/dashboard/dashboard.ts`; Test `dashboard.spec.ts`.

Dashboard is the reference implementation — do it first and read it before the other six.

- **Empty reason:** `measured-zero`. The dashboard's metrics are computed from the trade log; zero open positions is a *result*, not missing data.
- **Empty title:** `"No open positions"` · **hint:** `"The scan found no qualifying setups in this scope."`
- **Skeleton:** `rows=3 cols=5` — three data-card rows of five metric cards, matching `.primary`.
- **Note:** the dashboard already has `sb-empty-state` in one place. Remove that usage; `sb-async` owns it now.

- [ ] Write a test asserting the three states render, run it, implement, run, commit `refactor(v54): dashboard states through sb-async`.

---

### Task 15: Trades

**Files:** Modify `frontend/src/app/workspaces/trades/trades.ts`.

- **Empty reason:** depends on the filter. `store.hasFilters()` → `no-data-yet` is wrong; an empty *filtered* set is a measured answer. Use `measured-zero` when filters are active, `no-data-yet` before the first response lands (which `asyncInputs` already suppresses), so: **`measured-zero` always.**
- **Empty title:** `store.hasFilters() ? 'No trades match this filter' : 'No trades yet'` · **hint:** `store.hasFilters() ? 'Clear the filters to see the full log.' : undefined`
- **Skeleton:** `rows=12 cols=8` — a full table page.
- **Note:** trades already has a `skeleton` implementation. Delete it; do not leave two.

---

### Task 16: Analytics

**Files:** Modify `frontend/src/app/workspaces/analytics/analytics.ts` (1582 lines — wrap regions, do not restructure).

Analytics has **several** independently-fetched panels. Each gets its own `sb-async`, not one wrapper around the page: a failed strategy-breakdown fetch must not blank the equity curve.

- **Empty reason:** `measured-zero` for every panel. Analytics computes over a closed window; an empty breakdown means the window contained no qualifying trades, which is the finding.
- **Empty titles:** per panel, naming that panel (`"No closed trades in this range"`, `"No strategy has a closed trade in this range"`).
- **Skeleton:** chart panels `rows=1 cols=1`; table panels `rows=8 cols=6`.

---

### Task 17: Risk

**Files:** Modify `frontend/src/app/workspaces/risk/risk.ts`.

- **Empty reason:** `measured-zero` — risk exposure of zero is a real, meaningful state.
- **Empty title:** `"No open risk"` · **hint:** `"No position is currently exposed."`
- **Skeleton:** `rows=6 cols=5`.

---

### Task 18: Watchlist

**Files:** Modify `frontend/src/app/workspaces/watchlist/watchlist.ts`.

- **Empty reason:** `no-data-yet` — an empty watchlist is a *configuration* gap the user can fix, not a measurement.
- **Empty title:** `"No tickers on the watchlist"` · **hint:** `"Add a ticker to start scanning."`
- **Skeleton:** `rows=10 cols=4`.

This is the one workspace where `no-data-yet` is correct. If every workspace in this wave ends up `measured-zero`, the distinction has been applied carelessly — re-read D3.

---

### Task 19: System

**Files:** Modify `frontend/src/app/workspaces/system/*.ts` (five files: each tab fetches separately).

- **Empty reason:** `no-data-yet` for the logs tab (logs arriving is a data question); `measured-zero` for anything counting jobs or scans.
- **Empty titles:** per tab.
- **Skeleton:** logs `rows=15 cols=1`; settings `rows=10 cols=2`.

---

### Task 20: Versions and Calendar

**Files:** Modify `frontend/src/app/workspaces/versions/versions.ts` and the v53 calendar workspace.

- **Versions** — reason `no-data-yet`, title `"No version history"`, skeleton `rows=8 cols=3`.
- **Calendar** — reason `measured-zero`, title `"No closed trades this month"`, hint `"Pick another month, or widen the filters."`, skeleton `rows=6 cols=7` (a month grid).

Read the v53 calendar plan's Task 9 before touching it — its month grid already has a defined empty behaviour, and this must replace it rather than nest inside it.

---

### Task 21: The wave's gates — G1, G2 and G6

**Files:**
- Create: `frontend/src/app/ui/async-coverage.spec.ts`

**Interfaces:**
- Consumes: `callSites()` from `_1` T3's `primitives.spec.ts`.
- Produces: gates G1, G2, G6.

- [ ] **Step 1: Write the coverage gate**

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { callSites } from './testing/call-sites';

/**
 * Surfaces that fetch. Enumerated, not inferred: a workspace that stops
 * fetching should make this list fail so someone deletes the entry
 * deliberately, rather than the gate quietly covering one file less.
 */
const FETCHING = [
  'workspaces/dashboard/dashboard.ts',
  'workspaces/trades/trades.ts',
  'workspaces/trades/trade-detail.ts',
  'workspaces/analytics/analytics.ts',
  'workspaces/risk/risk.ts',
  'workspaces/watchlist/watchlist.ts',
  'workspaces/versions/versions.ts',
  'workspaces/system/logs-tab.ts',
  'workspaces/system/settings-tab.ts',
  // v53's calendar. Update this path if the plan named it differently.
  'workspaces/calendar/calendar.ts',
];

const sources = new Map(callSites().map(({ name, source }) => [name, source]));

describe('G1: every fetching surface uses sb-async', () => {
  for (const file of FETCHING) {
    it(`${file} wraps its fetch in sb-async`, () => {
      expect(sources.get(file) ?? '').toContain('<sb-async');
    });
  }
});

describe('G2: every sb-async names which empty it is', () => {
  for (const { name, source } of callSites()) {
    const uses = [...source.matchAll(/<sb-async\b[^>]*>/gs)].map(([tag]) => tag);
    if (!uses.length) continue;
    it(`${name} passes emptyReason on every sb-async`, () => {
      expect(uses.filter((tag) => !tag.includes('emptyReason'))).toEqual([]);
    });
  }
});

describe('the two empty reasons are both actually used', () => {
  const all = [...sources.values()].join('\n');
  // If every surface picked the same reason, the distinction was applied
  // mechanically rather than thought about -- which is the failure D3 exists
  // to prevent, and it would pass a per-file check.
  it('uses measured-zero somewhere', () => expect(all).toContain("'measured-zero'"));
  it('uses no-data-yet somewhere', () => expect(all).toContain("'no-data-yet'"));
});

describe('no workspace still hand-rolls a loading or error branch', () => {
  for (const { name, source } of callSites()) {
    if (!source.includes('<sb-async')) continue;
    it(`${name} has no leftover skeleton or error markup`, () => {
      expect(source).not.toMatch(/class="(skeleton|loading|error-panel)"/);
    });
  }
});
```

- [ ] **Step 2: Run it**

Run: `cd frontend && npm test -- --include src/app/ui/async-coverage.spec.ts`
Expected: PASS once Tasks 14–20 are done. A failure names the file that was missed.

- [ ] **Step 3: Verify G6 by hand — this one cannot be unit-tested**

For each of the eight workspaces: `npm start`, DevTools → Network → throttle to *Slow 3G*, reload, and watch the moment data arrives. **Nothing may jump.** If the content is taller or shorter than the skeleton, adjust that call site's `skeletonRows` / `skeletonCols` until it does not.

Record the final row/col numbers per workspace in a comment above each `sb-async` — the next person to change a column count needs to know the number was measured, not guessed.

- [ ] **Step 4: Full suite and commit**

Run: `cd frontend && npm test` → green.
Run: `python scripts/dev/testrun.py full` → `1686 passed, 66 skipped, 0 failed`.

```bash
git add frontend/src/app
git commit -m "test(v54): gate sb-async coverage and the empty-reason distinction"
```

## Wave 2 done when

- [ ] All ten fetching surfaces wrap in `sb-async` (G1).
- [ ] Every `sb-async` passes `emptyReason`, and **both** reasons appear in the codebase (G2).
- [ ] No layout shift on arrival at Slow 3G, verified by eye on all eight workspaces (G6).
- [ ] A failed refetch over existing data shows the stale badge, **not** an error panel — verified by killing the API while a workspace is open.
- [ ] No workspace defines `.stale` or `.error`.
- [ ] Python suite unchanged.
