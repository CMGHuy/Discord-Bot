# v175 Normal bad luck, part 3: SPA panel, three-width check, full suite, release, deploy check, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V175-10:" -A 400 docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_3-panel-release.md`.

**Spec:** [`docs/superpowers/specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md`](../specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md) (§3 Panel, § Testing "Frontend spec", `**Panel:**` line)
**Index:** [`2026-10-18-v175-normal-bad-luck-variance-band_0-index.md`](2026-10-18-v175-normal-bad-luck-variance-band_0-index.md) — Global Constraints (the **UI copy is verbatim there**), Parallelisation, Task ledger and `$WT`/`$R` live there and bind every task below.

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v175-normal-bad-luck-variance-band`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`, branch `2026-10-18-v175-normal-bad-luck-variance-band`. `$SCRATCH` is the implementing session's scratchpad directory (absolute path, from the session's environment): commit messages are written to a file there and passed with `git commit -F` (a heredoc inside `$(...)` breaks in this shell), and the Playwright scripts and VM scripts live there; nothing in `$SCRATCH` is committed. Never `cd`; use absolute paths, `git -C` and `npm --prefix`.

Tasks: V175-8 (store slice), V175-9 (copy model), V175-10 (panel on the Overview tab), V175-11 (three-width check), V175-12 (full suite), V175-13 (`/panel`, merge, bump, push), V175-14 (deploy check against the live book), V175-15 (close-out).

Consumed from part 2: `GET /api/v1/analytics/variance-band` (V175-5), body = the `Band` of Global Constraints, unscoped (any query parameter is a 400, so the client sends none). Consumed from part 1 for the release checks only: `swingbot/core/analytics/variance_band.py` (`variance_band`, `ZONES`, `CAVEAT`). Consumed from part 2 for the deploy check: `swingbot/commands/scanning/book_status.py` (`ZONE_JOB = "variance_band:zone"`, swallowed tag `scan.book_status`).

**Money text in the UI.** The panel writes the dollar figure unsigned with the currency symbol first (`$312.34`), the same text the book-status message shows (`tokens.fmt_money(...)` with its sign stripped). It deliberately does not use `ui/format.ts`'s `amount()` (`312.34 $`), so the panel and the Discord line read the same figure the same way. The symbol is `ConnectionStore.currency()`, never a literal.

**Frontend specs** are outside `tests/suites.toml`; each task runs only its own spec with `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec path relative to frontend/>`.

# Phase C: SPA panel (V175-8..V175-11)

### Task V175-8: SPA models, `ApiClient.analyticsVarianceBand`, store slice `varianceBand`

**Model:** sonnet — client and store following the calibration slice; six touch points in one store, each with a precedent beside it.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (new block right after `export interface AnalyticsPartials extends Scoped { ... }`, today ending at line 716)
- Modify: `frontend/src/app/api/api-client.ts` (import list lines 7-72; new method right after `analyticsPartials(...)`, today at lines 271-274)
- Modify: `frontend/src/app/stores/analytics.store.ts` (import list lines 15-31, `PanelKey` lines 203-206, state interface line 380, initial state line 468, `loadOverview` lines 703-706, `resolveOverview` lines 841-844, `reload` map lines 923-937)
- Create: `frontend/src/app/stores/analytics.variance-band.spec.ts`

**Interfaces:**
- Consumes (V175-5): `GET /api/v1/analytics/variance-band`, no query parameters, body = `Band` (Global Constraints).
- Produces (consumed by V175-9 and V175-10), all exported from `frontend/src/app/api/models.ts`:
  - `type BandZone = 'normal' | 'rough' | 'outside'`
  - `interface BandQuantiles { p80: number; p95: number; p95_lo: number; p95_hi: number }`
  - `interface BandHorizon { horizon: number; weeks_span: number; run: BandQuantiles; drawdown: BandQuantiles }`
  - `interface BandCurrent { run: number; run_age_days: number | null; drawdown: number; drawdown_age_days: number | null; run_zone: BandZone; drawdown_zone: BandZone; zone: BandZone }`
  - `interface BandExpR { value: number | null; n: number; start: string | null; end: string | null; ci: [number, number] | null; not_positive: boolean }`
  - `interface BandDollars { median_risk: number; drawdown_usd: number }`
  - `interface VarianceBandInsufficient { status: 'insufficient'; scope: 'whole_book'; days: number; weeks: number }`
  - `interface VarianceBandOk { status: 'ok'; scope: 'whole_book'; asof: string; days: number; weeks: number; pool: 'v2' | 'all'; composition: { days_by_era: { v2: number; legacy: number }; trades_by_horizon: Record<string, number> }; horizons: BandHorizon[]; current: BandCurrent; expr: BandExpR; dollars?: BandDollars }`
  - `type AnalyticsVarianceBand = VarianceBandOk | VarianceBandInsufficient`
  - `ApiClient.analyticsVarianceBand(): Observable<AnalyticsVarianceBand>`
  - `AnalyticsStore` state `varianceBand: AnalyticsVarianceBand | null`, `varianceBandError: string | null`; `PanelKey` gains `'varianceBand'`; `store.reload('varianceBand')` refetches only the band.

**Why this shape.** The band is whole-book (spec §2): the client sends no `BookScope` (the route 400s on any parameter), exactly like `analyticsCalibration()`. It loads with the Overview tab because the panel lives there; a scope change re-runs the Overview loader and so refetches the band too, which is harmless (the body does not depend on the scope) and keeps one loader per tab. The `dollars` key is optional in the type because the server omits it rather than sending `null` (Global Constraints, Dollars).

- [ ] **Step 1: Write the failing store spec**

Create `frontend/src/app/stores/analytics.variance-band.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Signal, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsVarianceBand } from '../api/models';
import { EventStream } from '../api/event-stream';
import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { AnalyticsStore } from './analytics.store';

/* v175 — the variance-band slice: whole book, unscoped, loaded with Overview,
 * its own error and its own retry. */

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();
  changes(name: string): Signal<number> {
    if (!this.counters.has(name)) this.counters.set(name, signal(0));
    return this.counters.get(name)!.asReadonly();
  }
}

const URL = '/api/v1/analytics/variance-band';

const INSUFFICIENT: AnalyticsVarianceBand = {
  status: 'insufficient', scope: 'whole_book', days: 64, weeks: 15,
};

describe('AnalyticsStore — variance-band slice', () => {
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

  it('starts empty, with no error', () => {
    expect(store.varianceBand()).toBeNull();
    expect(store.varianceBandError()).toBeNull();
  });

  it('fetches the band with the Overview tab, and never sends the scope', () => {
    store.setScope({ strategy: 'RSI', ledger: 'weak' });
    const band = backend.expectOne((req) => req.url === URL);
    // Whole book: the route answers 400 to any query parameter.
    expect(band.request.params.keys()).toEqual([]);
    expect(band.request.urlWithParams).toBe(URL);
    band.flush(INSUFFICIENT);
    backend.match(() => true).forEach((request) => request.flush({}));   // the rest of the Overview load
    backend.verify();
    expect(store.varianceBand()).toEqual(INSUFFICIENT);
  });

  it('is not fetched by a tab that does not show it', () => {
    store.setTab('partials');
    expect(backend.match((req) => req.url === URL)).toEqual([]);
    backend.match(() => true).forEach((request) => request.flush({}));
    backend.verify();
  });

  it('keeps its own error and retries only itself', () => {
    store.setTab('overview');
    backend.expectOne((req) => req.url === URL)
      .flush({ message: 'boom' }, { status: 500, statusText: 'Server Error' });
    backend.match(() => true).forEach((request) => request.flush({}));
    expect(store.varianceBandError()).not.toBeNull();

    store.reload('varianceBand');
    const retry = backend.match(() => true);
    expect(retry.map((request) => request.request.url)).toEqual([URL]);
    retry[0].flush(INSUFFICIENT);
    backend.verify();
    expect(store.varianceBandError()).toBeNull();
    expect(store.varianceBand()?.status).toBe('insufficient');
  });
});
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/stores/analytics.variance-band.spec.ts`
Expected: FAIL — the build reports that `AnalyticsVarianceBand` is not exported from `../api/models` and that `varianceBand`/`varianceBandError` do not exist on the store.

- [ ] **Step 3: Add the types**

In `frontend/src/app/api/models.ts`, insert right after the closing `}` of `export interface AnalyticsPartials extends Scoped { ... }`:

```ts
/** v175 — `GET /analytics/variance-band`: the whole closed book's losing-run
 *  band (`swingbot/core/analytics/variance_band.py`). Not `Scoped`: the band
 *  never follows the Analytics scope bar, and says so in `scope`. */
export type BandZone = 'normal' | 'rough' | 'outside';
/** p80/p95 of one statistic across the simulated paths, plus p95's own
 *  10–90% range across the outer resamples of the week set. Integers for the
 *  run (close days), R rounded to 2 dp for the drawdown. */
export interface BandQuantiles { p80: number; p95: number; p95_lo: number; p95_hi: number; }
export interface BandHorizon {
  /** Simulated length in close days (20 or 50). */
  horizon: number;
  /** `horizon` close days expressed in weeks at this book's pace, 1 dp. */
  weeks_span: number;
  run: BandQuantiles;
  drawdown: BandQuantiles;
}
export interface BandCurrent {
  /** Losing close days in a row at the latest close day (scratch days skipped). */
  run: number;
  /** Inclusive calendar days from the run's first loss day; null when `run` is 0. */
  run_age_days: number | null;
  /** Peak-to-now drawdown inside the last 50 close days, in R (>= 0). */
  drawdown: number;
  /** Inclusive calendar days since the window's peak; null when `drawdown` is 0. */
  drawdown_age_days: number | null;
  run_zone: BandZone;
  drawdown_zone: BandZone;
  /** The worse of the two. */
  zone: BandZone;
}
export interface BandExpR {
  value: number | null;
  n: number;
  /** First and last NYSE close date of the pool, ISO. */
  start: string | null;
  end: string | null;
  /** 2.5–97.5% week-cluster bootstrap interval; null when it has no draws. */
  ci: [number, number] | null;
  not_positive: boolean;
}
export interface BandDollars { median_risk: number; drawdown_usd: number; }
export interface VarianceBandInsufficient {
  status: 'insufficient';
  scope: 'whole_book';
  days: number;
  weeks: number;
}
export interface VarianceBandOk {
  status: 'ok';
  scope: 'whole_book';
  asof: string;
  days: number;
  weeks: number;
  pool: 'v2' | 'all';
  composition: { days_by_era: { v2: number; legacy: number }; trades_by_horizon: Record<string, number> };
  /** One entry per simulated horizon, in order (20, then 50). */
  horizons: BandHorizon[];
  current: BandCurrent;
  expr: BandExpR;
  /** Omitted (never null) when no pool trade carries shares and a stop distance. */
  dollars?: BandDollars;
}
export type AnalyticsVarianceBand = VarianceBandOk | VarianceBandInsufficient;
```

- [ ] **Step 4: Add the client method**

In `frontend/src/app/api/api-client.ts`, add `AnalyticsVarianceBand,` to the `import { ... } from './models';` list (alphabetical, after `AnalyticsStrategies,`), and insert right after the `analyticsPartials(...)` method:

```ts
  /** v175 — the whole-book losing-run band. Unscoped on purpose: the route
   *  rejects any query parameter, so no `BookScope` is ever sent. */
  analyticsVarianceBand(): Observable<AnalyticsVarianceBand> {
    return this.http.get<AnalyticsVarianceBand>(`${this.base}/analytics/variance-band`);
  }
```

- [ ] **Step 5: Add the store slice**

In `frontend/src/app/stores/analytics.store.ts`:

1. Add `AnalyticsVarianceBand,` to the `import { ... } from '../api/models';` block (after `AnalyticsUnit,`).
2. `PanelKey`: change the last line to
   ```ts
     | 'byHorizon' | 'byDirection' | 'byDow' | 'partials' | 'varianceBand';
   ```
3. State interface, right after the `partials: ... partialsError: ...` line:
   ```ts
     /** v175 — the whole-book losing-run band (Overview's "Normal bad luck"
      *  panel). Unscoped: it never feeds `scopeN`. */
     varianceBand: AnalyticsVarianceBand | null; varianceBandError: string | null;
   ```
4. Initial state, right after `partials: null, partialsError: null,`:
   ```ts
         varianceBand: null, varianceBandError: null,
   ```
5. `loadOverview` becomes:
   ```ts
       const loadOverview = (): void => {
         fetchPanel(api.analyticsPerformance(s()), 'performance', 'performanceError');
         fetchPanel(api.analyticsEquityCurve(s()), 'equityCurve', 'equityCurveError');
         fetchPanel(api.analyticsVarianceBand(), 'varianceBand', 'varianceBandError');
       };
   ```
6. `resolveOverview` becomes:
   ```ts
       const resolveOverview = (): Observable<void> =>
         resolveOne(api.analyticsPerformance(s()), 'performance', 'performanceError', () => {
           fetchPanel(api.analyticsEquityCurve(s()), 'equityCurve', 'equityCurveError');
           fetchPanel(api.analyticsVarianceBand(), 'varianceBand', 'varianceBandError');
         });
   ```
7. In `reload(panel)`'s `one` map, right after the `partials:` entry:
   ```ts
             varianceBand: () => fetchPanel(api.analyticsVarianceBand(), 'varianceBand', 'varianceBandError'),
   ```

The `Record<PanelKey, () => void>` type makes a missing map entry a compile error, so item 7 is checked by the build.

- [ ] **Step 6: Run the new spec and the neighbouring store specs**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/stores/analytics.variance-band.spec.ts`
Expected: PASS, 4 tests, 0 failed.

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/stores/analytics.partials.spec.ts`
Expected: PASS (its `backend.match(() => true)` flush already absorbs the extra Overview request).

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include "src/app/stores/analytics.store*.spec.ts"`
Expected: PASS. A store spec that counted the Overview requests exactly (an `expectOne` the Overview load now trips over, or a request-count assertion) fails here: add the band request to that expectation (flush it with `{ status: 'insufficient', scope: 'whole_book', days: 0, weeks: 0 }`), never loosen the assertion.

- [ ] **Step 7: Commit**

Write `$SCRATCH/v175-8-msg.txt`:

```text
feat(ui): variance-band types, client and store slice (v175)

AnalyticsVarianceBand (ok | insufficient), ApiClient.analyticsVarianceBand
(unscoped: the route rejects any parameter), and the store's varianceBand
slice, loaded with the Overview tab and retried on its own.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $WT add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.variance-band.spec.ts
git -C $WT commit -F "$SCRATCH/v175-8-msg.txt"
git -C $R status --short
```
Expected: one commit on the branch (a store-spec fix from Step 6 rides in the same commit, its file added to the `git add` line); the main tree shows no change from this task.

### Task V175-9: Copy model `variance-band.model.ts`

**Model:** sonnet — pure copy and segment helpers whose strings are fixed verbatim by Global Constraints.

**Files:**
- Create: `frontend/src/app/workspaces/analytics/tabs/variance-band.model.ts`
- Create: `frontend/src/app/workspaces/analytics/tabs/variance-band.model.spec.ts`

**Interfaces:**
- Consumes (V175-8): `BandZone`, `BandQuantiles`, `BandHorizon`, `BandCurrent`, `BandExpR`, `BandDollars`, `VarianceBandOk` from `frontend/src/app/api/models.ts`; existing `ABSENT`, `rMultiple` from `frontend/src/app/ui/format.ts`.
- Produces (consumed by V175-10), all exported from `variance-band.model.ts`:
  - constants `PANEL_TITLE`, `HEADER_COPY`, `CAPTION`, `CAVEAT`, `ZONE_COPY: Record<BandZone, string>`, `BAR_LABELS: { run: string; drawdown: string }`
  - `type BandUnit = 'days' | 'R'`
  - `interface BandSegment { zone: BandZone; label: string; range: string; width: number }` (`width` = percent of the bar, the three widths sum to 100)
  - `scaleMax(q: { p80: number; p95: number }): number`
  - `bandSegments(q: { p80: number; p95: number }, unit: BandUnit): BandSegment[]` (rough omitted when `p80 === p95`)
  - `markerPercent(value: number, q: { p80: number; p95: number }): number` (0–100, clamped)
  - `moneyText(value: number, currency: string): string` (unsigned, symbol first: `$312.34`)
  - `runMarkerText(cur: BandCurrent): string`
  - `drawdownMarkerText(cur: BandCurrent, dollars: BandDollars | undefined, currency: string): string`
  - `uncertaintyText(q: BandQuantiles, unit?: BandUnit): string` (`unit` defaults to `'days'`)
  - `spanText(h: BandHorizon): string`
  - `secondaryText(h20: BandHorizon): string`
  - `exprLine(e: BandExpR): string`
  - `compositionLine(c: VarianceBandOk['composition']): string`
  - `dollarNote(d: BandDollars, currency: string): string`
  - `insufficientCopy(days: number, weeks: number): string`
  - `barAriaLabel(label: string, segments: BandSegment[], marker: string): string`

  The ledger's signatures hold; three additions live only inside this part (V175-10 is their one consumer): `BandSegment.width`, the optional `unit` of `uncertaintyText`, and `scaleMax`/`moneyText`/`barAriaLabel`/`BandUnit`.

**Why a separate model file.** Every word on the panel is fixed by the spec (copy reviewed by the financial-advisor seat: no instruction verbs, never "edge"). Keeping the strings and the arithmetic in one pure file makes them testable without a DOM and lets the copy test sweep every string the panel can show. The panel component (V175-10) only lays them out.

**Copy decisions this task fixes** (all inside the verbatim templates of Global Constraints):
- Counts use `day` for exactly 1 and `days` otherwise (`now: 1 day, 1 calendar day long`); the template's plural is the general case.
- R values print with one decimal everywhere on the panel (`3.2R`), the same as the book-status message's `{dd}` (`f"{drawdown:.1f}"`); run values print as integers.
- When an age is `null` (no run, no drawdown) the `, {age} …` tail is dropped for both markers.
- Segment ranges read `≤ 3 days`, `> 3 to ≤ 5 days`, `> 5 days` (R: `≤ 2.4R`, `> 2.4 to ≤ 3.9R`, `> 3.9R`), matching the zone rule (`normal` ≤ p80, `rough` > p80 and ≤ p95, `outside` > p95).
- The bar's scale runs from 0 to `scaleMax = max(1.25 × p95, p95 + 1)`, so the outside segment always has room and an all-win book (p95 = 0) still draws a bar; a current value beyond the scale pins the marker at 100%.
- The dollar note keeps the spec's literal `≈ $ =` (it names the approximation, not the account currency); the figures themselves use `ConnectionStore.currency()`.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/analytics/tabs/variance-band.model.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { BandCurrent, BandHorizon, VarianceBandOk } from '../../../api/models';
import {
  BAR_LABELS, CAPTION, CAVEAT, HEADER_COPY, PANEL_TITLE, ZONE_COPY,
  bandSegments, barAriaLabel, compositionLine, dollarNote, drawdownMarkerText, exprLine,
  insufficientCopy, markerPercent, moneyText, runMarkerText, scaleMax, secondaryText,
  spanText, uncertaintyText,
} from './variance-band.model';

const H20: BandHorizon = {
  horizon: 20, weeks_span: 5.3,
  run: { p80: 3, p95: 4, p95_lo: 4, p95_hi: 5 },
  drawdown: { p80: 3.12, p95: 4.4, p95_lo: 3.9, p95_hi: 5.06 },
};
const H50: BandHorizon = {
  horizon: 50, weeks_span: 13.2,
  run: { p80: 4, p95: 7, p95_lo: 6, p95_hi: 8 },
  drawdown: { p80: 4.81, p95: 6.62, p95_lo: 5.9, p95_hi: 7.4 },
};
const CURRENT: BandCurrent = {
  run: 4, run_age_days: 9, drawdown: 5.27, drawdown_age_days: 23,
  run_zone: 'normal', drawdown_zone: 'rough', zone: 'rough',
};
const COMPOSITION: VarianceBandOk['composition'] = {
  days_by_era: { v2: 118, legacy: 42 },
  trades_by_horizon: { '2w': 88, '4w': 131, unknown: 3 },
};

describe('variance-band copy constants (verbatim from the spec)', () => {
  it('carries the title, header, caveat and caption word for word', () => {
    expect(PANEL_TITLE).toBe('Normal bad luck');
    expect(HEADER_COPY).toBe("Whole book, closed trades only. Filters don't apply.");
    expect(CAVEAT).toBe("This book's past results are not positive. A run within their range is still a losing run.");
    expect(CAPTION).toBe(
      "Simulated from this book's closed trades, resampled by week. It shows the range of losing runs these past "
      + "results produce by chance; it is not a forecast. Checked continuously, so 'beyond 95%' will sometimes "
      + 'appear by chance alone. Paper book, before tax.',
    );
  });

  it('carries the bar labels and one copy line per zone', () => {
    expect(BAR_LABELS).toEqual({ run: 'Losing days in a row', drawdown: 'Drawdown over the last 50 close days' });
    expect(ZONE_COPY).toEqual({
      normal: "Within the range this book's past trades produce",
      rough: 'Deeper than 80% of simulated runs, within 95%',
      outside: 'Beyond 95% of simulated runs',
    });
  });

  it('formats the insufficient state with its counts so far', () => {
    expect(insufficientCopy(64, 15)).toBe('Needs 100 close days over 20 weeks (64 days, 15 weeks so far).');
  });
});

describe('band segments', () => {
  it('gives three labelled segments with their values as text, widths summing to 100', () => {
    const segments = bandSegments(H50.run, 'days');
    expect(segments.map((s) => [s.zone, s.label, s.range])).toEqual([
      ['normal', 'Normal', '≤ 4 days'],
      ['rough', 'Rough', '> 4 to ≤ 7 days'],
      ['outside', 'Outside', '> 7 days'],
    ]);
    expect(segments.reduce((sum, s) => sum + s.width, 0)).toBeCloseTo(100, 6);
  });

  it('writes R ranges with one decimal', () => {
    expect(bandSegments(H50.drawdown, 'R').map((s) => s.range))
      .toEqual(['≤ 4.8R', '> 4.8 to ≤ 6.6R', '> 6.6R']);
  });

  it('omits the empty rough zone when p80 equals p95', () => {
    const segments = bandSegments({ p80: 3, p95: 3 }, 'days');
    expect(segments.map((s) => s.zone)).toEqual(['normal', 'outside']);
    expect(segments.map((s) => s.range)).toEqual(['≤ 3 days', '> 3 days']);
    expect(segments.reduce((sum, s) => sum + s.width, 0)).toBeCloseTo(100, 6);
  });

  it('still draws a bar for an all-win book (p95 = 0)', () => {
    expect(scaleMax({ p80: 0, p95: 0 })).toBe(1);
    const segments = bandSegments({ p80: 0, p95: 0 }, 'days');
    expect(segments.map((s) => s.zone)).toEqual(['normal', 'outside']);
    expect(segments[1].width).toBe(100);
  });

  it('places the marker on the same scale and clamps it to the bar', () => {
    expect(scaleMax(H50.run)).toBe(8.75);
    expect(markerPercent(7, H50.run)).toBeCloseTo(80, 6);
    expect(markerPercent(0, H50.run)).toBe(0);
    expect(markerPercent(40, H50.run)).toBe(100);
    expect(markerPercent(-1, H50.run)).toBe(0);
  });
});

describe('marker and line text', () => {
  it('writes the run marker with its age', () => {
    expect(runMarkerText(CURRENT)).toBe('now: 4 days, 9 calendar days long');
    expect(runMarkerText({ ...CURRENT, run: 1, run_age_days: 1 })).toBe('now: 1 day, 1 calendar day long');
    expect(runMarkerText({ ...CURRENT, run: 0, run_age_days: null })).toBe('now: 0 days');
  });

  it('writes the drawdown marker with approximate dollars only when they exist', () => {
    expect(drawdownMarkerText(CURRENT, { median_risk: 59.26, drawdown_usd: 312.34 }, '$'))
      .toBe('now: 5.3R (≈ $312.34), 23 calendar days since the peak');
    expect(drawdownMarkerText(CURRENT, undefined, '$'))
      .toBe('now: 5.3R, 23 calendar days since the peak');
    expect(drawdownMarkerText({ ...CURRENT, drawdown: 0, drawdown_age_days: null }, undefined, '€'))
      .toBe('now: 0.0R');
  });

  it('writes money unsigned with the symbol first, grouped', () => {
    expect(moneyText(1312.346, '$')).toBe('$1,312.35');
    expect(moneyText(-40, '€')).toBe('€40.00');
  });

  it("states the band's own uncertainty", () => {
    expect(uncertaintyText(H50.run)).toBe('p95 ≈ 7 (6–8)');
    expect(uncertaintyText(H50.drawdown, 'R')).toBe('p95 ≈ 6.6R (5.9–7.4R)');
  });

  it('writes the span and the 20-day secondary line', () => {
    expect(spanText(H50)).toBe("50 close days ≈ 13.2 weeks at this book's pace");
    expect(spanText(H20)).toBe("20 close days ≈ 5.3 weeks at this book's pace");
    expect(secondaryText(H20)).toBe('Over 20 close days: p95 4 days in a row, 4.4R drawdown');
  });

  it('writes the ExpR line with N and window', () => {
    expect(exprLine({ value: 0.214, n: 222, start: '2026-01-05', end: '2026-10-16', ci: [0.02, 0.41], not_positive: false }))
      .toBe('Book: ExpR +0.21R over N=222 trades (2026-01-05 to 2026-10-16)');
    expect(exprLine({ value: null, n: 0, start: null, end: null, ci: null, not_positive: true }))
      .toBe('Book: ExpR — over N=0 trades (— to —)');
  });

  it('writes the composition line', () => {
    expect(compositionLine(COMPOSITION)).toBe('Close days: 118 v2, 42 legacy · Trades: 2w 88, 4w 131, unknown 3');
    expect(compositionLine({ days_by_era: { v2: 0, legacy: 0 }, trades_by_horizon: {} }))
      .toBe('Close days: 0 v2, 0 legacy · Trades: —');
  });

  it('says how the dollar figure is derived', () => {
    expect(dollarNote({ median_risk: 59.26, drawdown_usd: 312.34 }, '$'))
      .toBe('≈ $ = R × the median per-trade dollar risk ($59.26), from shares × entry-to-stop distance.');
  });

  it("gives each bar a text equivalent for screen readers", () => {
    const segments = bandSegments(H50.run, 'days');
    expect(barAriaLabel(BAR_LABELS.run, segments, runMarkerText(CURRENT)))
      .toBe('Losing days in a row: Normal ≤ 4 days, Rough > 4 to ≤ 7 days, Outside > 7 days. now: 4 days, 9 calendar days long');
  });
});

describe('copy discipline', () => {
  /** Every string the panel can show, for one full band with dollars. */
  function everyString(): string[] {
    const dollars = { median_risk: 59.26, drawdown_usd: 312.34 };
    return [
      PANEL_TITLE, HEADER_COPY, CAPTION, CAVEAT, ...Object.values(ZONE_COPY), ...Object.values(BAR_LABELS),
      insufficientCopy(64, 15),
      ...bandSegments(H50.run, 'days').flatMap((s) => [s.label, s.range]),
      ...bandSegments(H50.drawdown, 'R').flatMap((s) => [s.label, s.range]),
      runMarkerText(CURRENT), drawdownMarkerText(CURRENT, dollars, '$'),
      uncertaintyText(H50.run), uncertaintyText(H50.drawdown, 'R'), spanText(H20), spanText(H50),
      secondaryText(H20), compositionLine(COMPOSITION), dollarNote(dollars, '$'),
      exprLine({ value: -0.1, n: 40, start: '2026-01-05', end: '2026-10-16', ci: [-0.3, 0.1], not_positive: true }),
    ];
  }

  it('never uses the word "edge"', () => {
    for (const text of everyString()) expect(text).not.toMatch(/\bedge\b/i);
  });

  it('never opens a sentence with an instruction verb', () => {
    // "entry-to-stop distance" names a price distance (a noun), so the
    // check is on imperative position: the start of a string or sentence.
    const imperative = /(^|[.;:!?]\s+)(stop|check|skip|size|review)\b/i;
    for (const text of everyString()) expect(text).not.toMatch(imperative);
  });
});
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/variance-band.model.spec.ts`
Expected: FAIL — `Cannot find module './variance-band.model'` (or the build's equivalent "could not resolve").

- [ ] **Step 3: Write the model**

Create `frontend/src/app/workspaces/analytics/tabs/variance-band.model.ts`:

```ts
import {
  BandCurrent, BandDollars, BandExpR, BandHorizon, BandQuantiles, BandZone, VarianceBandOk,
} from '../../../api/models';
import { ABSENT, rMultiple } from '../../../ui/format';

/* v175 — every word of the "Normal bad luck" panel, and the arithmetic that
 * places its segments and marker. Pure: no Angular, no store, no DOM.
 *
 * The copy is fixed by the spec and reviewed by the financial-advisor seat:
 * it describes and never instructs (no sentence opens with stop, check, skip,
 * size or review), and it never says "edge" -- the band shows the range this
 * book's PAST trades produce by chance, which is not a claim that the book
 * has one. */

export const PANEL_TITLE = 'Normal bad luck';
export const HEADER_COPY = "Whole book, closed trades only. Filters don't apply.";
export const CAVEAT = "This book's past results are not positive. A run within their range is still a losing run.";
export const CAPTION =
  "Simulated from this book's closed trades, resampled by week. It shows the range of losing runs these past "
  + "results produce by chance; it is not a forecast. Checked continuously, so 'beyond 95%' will sometimes "
  + 'appear by chance alone. Paper book, before tax.';

export const ZONE_COPY: Record<BandZone, string> = {
  normal: "Within the range this book's past trades produce",
  rough: 'Deeper than 80% of simulated runs, within 95%',
  outside: 'Beyond 95% of simulated runs',
};

export const BAR_LABELS = {
  run: 'Losing days in a row',
  drawdown: 'Drawdown over the last 50 close days',
} as const;

const ZONE_LABEL: Record<BandZone, string> = { normal: 'Normal', rough: 'Rough', outside: 'Outside' };

export type BandUnit = 'days' | 'R';

/** One labelled segment of a band bar; `width` is its share of the bar in %. */
export interface BandSegment {
  zone: BandZone;
  label: string;
  range: string;
  width: number;
}

type Cuts = { p80: number; p95: number };

const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? '' : 's'}`;

/** A bare number in the unit's precision: integers for days, 1 dp for R. */
const bare = (value: number, unit: BandUnit): string => (unit === 'days' ? String(value) : value.toFixed(1));

/** A number with its unit: `3 days`, `1 day`, `2.4R`. */
const withUnit = (value: number, unit: BandUnit): string =>
  unit === 'days' ? plural(value, 'day') : `${value.toFixed(1)}R`;

/** The bar runs 0 → scaleMax: a quarter past p95 so the outside segment has
 *  room, and at least p95 + 1 so an all-win book (p95 = 0) still draws. */
export function scaleMax(q: Cuts): number {
  return Math.max(q.p95 * 1.25, q.p95 + 1);
}

/** normal ≤ p80 < rough ≤ p95 < outside; rough is omitted on a tie. */
export function bandSegments(q: Cuts, unit: BandUnit): BandSegment[] {
  const max = scaleMax(q);
  const share = (span: number): number => (span / max) * 100;
  const segments: BandSegment[] = [
    { zone: 'normal', label: ZONE_LABEL.normal, range: `≤ ${withUnit(q.p80, unit)}`, width: share(q.p80) },
  ];
  if (q.p95 > q.p80) {
    segments.push({
      zone: 'rough', label: ZONE_LABEL.rough,
      range: `> ${bare(q.p80, unit)} to ≤ ${withUnit(q.p95, unit)}`, width: share(q.p95 - q.p80),
    });
  }
  segments.push({ zone: 'outside', label: ZONE_LABEL.outside, range: `> ${withUnit(q.p95, unit)}`, width: share(max - q.p95) });
  return segments;
}

/** Where `value` sits on the bar, in %, clamped to [0, 100]. */
export function markerPercent(value: number, q: Cuts): number {
  const percent = (value / scaleMax(q)) * 100;
  return Math.min(100, Math.max(0, percent));
}

/** Unsigned, symbol first, grouped: `$1,312.35`. The same text the
 *  book-status message shows (`fmt_money` with its sign stripped). */
export function moneyText(value: number, currency: string): string {
  const digits = Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${currency}${digits}`;
}

export function runMarkerText(cur: BandCurrent): string {
  const age = cur.run_age_days === null ? '' : `, ${plural(cur.run_age_days, 'calendar day')} long`;
  return `now: ${plural(cur.run, 'day')}${age}`;
}

export function drawdownMarkerText(cur: BandCurrent, dollars: BandDollars | undefined, currency: string): string {
  const usd = dollars ? ` (≈ ${moneyText(dollars.drawdown_usd, currency)})` : '';
  const age = cur.drawdown_age_days === null ? '' : `, ${plural(cur.drawdown_age_days, 'calendar day')} since the peak`;
  return `now: ${cur.drawdown.toFixed(1)}R${usd}${age}`;
}

/** "p95 ≈ 7 (6–8)": the band's own uncertainty across outer resamples. */
export function uncertaintyText(q: BandQuantiles, unit: BandUnit = 'days'): string {
  const suffix = unit === 'R' ? 'R' : '';
  return `p95 ≈ ${bare(q.p95, unit)}${suffix} (${bare(q.p95_lo, unit)}–${bare(q.p95_hi, unit)}${suffix})`;
}

export function spanText(h: BandHorizon): string {
  return `${h.horizon} close days ≈ ${h.weeks_span} weeks at this book's pace`;
}

export function secondaryText(h20: BandHorizon): string {
  return `Over ${h20.horizon} close days: p95 ${h20.run.p95} days in a row, ${h20.drawdown.p95.toFixed(1)}R drawdown`;
}

export function exprLine(e: BandExpR): string {
  return `Book: ExpR ${rMultiple(e.value)} over N=${e.n} trades (${e.start ?? ABSENT} to ${e.end ?? ABSENT})`;
}

export function compositionLine(c: VarianceBandOk['composition']): string {
  const trades = Object.entries(c.trades_by_horizon).map(([horizon, n]) => `${horizon} ${n}`).join(', ');
  return `Close days: ${c.days_by_era.v2} v2, ${c.days_by_era.legacy} legacy · Trades: ${trades || ABSENT}`;
}

export function dollarNote(d: BandDollars, currency: string): string {
  return `≈ $ = R × the median per-trade dollar risk (${moneyText(d.median_risk, currency)}), `
    + 'from shares × entry-to-stop distance.';
}

export function insufficientCopy(days: number, weeks: number): string {
  return `Needs 100 close days over 20 weeks (${days} days, ${weeks} weeks so far).`;
}

/** The bar's text equivalent: every segment's range, then where the book is. */
export function barAriaLabel(label: string, segments: BandSegment[], marker: string): string {
  return `${label}: ${segments.map((s) => `${s.label} ${s.range}`).join(', ')}. ${marker}`;
}
```

- [ ] **Step 4: Run it to confirm it passes**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/variance-band.model.spec.ts`
Expected: PASS, 19 tests, 0 failed. If `toFixed(1)` rounds a fixture value differently from the expected text (binary floating point: `4.81.toFixed(1)` is `'4.8'`, `6.62.toFixed(1)` is `'6.6'`, `5.27.toFixed(1)` is `'5.3'`), fix the expectation only after printing the actual value, never the rounding rule.

- [ ] **Step 5: Commit**

Write `$SCRATCH/v175-9-msg.txt`:

```text
feat(ui): Normal bad luck copy model -- verbatim copy, segments, marker (v175)

Every string of the panel in one pure file: the spec's verbatim copy,
segment ranges (rough omitted on a p80 == p95 tie), marker placement on a
0..max(1.25 x p95, p95 + 1) scale, unsigned symbol-first dollars, and a
sweep that no string says "edge" or opens with an instruction verb.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $WT add frontend/src/app/workspaces/analytics/tabs/variance-band.model.ts frontend/src/app/workspaces/analytics/tabs/variance-band.model.spec.ts
git -C $WT commit -F "$SCRATCH/v175-9-msg.txt"
git -C $R status --short
```
Expected: one commit on the branch; the main tree shows no change from this task.

### Task V175-10: Panel `sb-variance-band-panel` on the Overview tab

**Model:** sonnet — one standalone panel component built from the tab's existing pieces, plus a two-line mount.

**Files:**
- Create: `frontend/src/app/workspaces/analytics/tabs/variance-band.fixture.ts`
- Create: `frontend/src/app/workspaces/analytics/tabs/variance-band-panel.ts`
- Create: `frontend/src/app/workspaces/analytics/tabs/variance-band-panel.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts` (imports lines 1-19 and the `imports: [...]` array; one element at the end of `<div class="panels">`; one style rule)
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts` (`storeStub` base, one new test)

**Interfaces:**
- Consumes (V175-8): `AnalyticsStore.varianceBand()`, `.varianceBandError()`, `.reload('varianceBand')`; types `VarianceBandOk`, `VarianceBandInsufficient`, `BandZone`, `BandQuantiles`.
- Consumes (V175-9): every export of `variance-band.model.ts` listed in its Interfaces block.
- Consumes (existing): `Panel` (`ui/layout.ts`, selector `sb-panel`), `PanelHeader` (`ui/panel-header.ts`, input `title` only), `PanelError` (`ui/panel-error.ts`, input `message`, output `retry`), `ConnectionStore.currency()`.
- Produces: `VarianceBandPanel` (selector `sb-variance-band-panel`), `bandView(band: VarianceBandOk, currency: string): BandView`; fixtures `BAND_OK`, `BAND_TIE`, `BAND_NOT_POSITIVE`, `BAND_INSUFFICIENT` (V175-11 copies their shapes into its browser stub).

**Layout decisions.** The panel spans the full width of the tab's two-column `.panels` grid (`grid-column: 1 / -1`), so its two bars sit side by side from 640 px up and stack below it (`@media (max-width: 639px)`, the tab's own breakpoint). Each bar is a flex track of labelled segments with an absolutely placed marker; every value is also printed as text (legend ranges, `now: …` line, zone line), so nothing relies on colour. Copy wraps (`overflow-wrap: anywhere` on the legend values); nothing uses `nowrap` or an ellipsis. The panel is non-interactive: no `hint`, no `tableable`, no `tabindex`, no link; the only control is `sb-panel-error`'s Retry. The not-positive caveat is shown once, directly under the ExpR line, so it reads beside the ExpR figure it qualifies and beside both zone lines, rather than repeated under each bar.

- [ ] **Step 1: Write the fixtures**

Create `frontend/src/app/workspaces/analytics/tabs/variance-band.fixture.ts`:

```ts
import { BandHorizon, VarianceBandInsufficient, VarianceBandOk } from '../../../api/models';

/** v175 — `/analytics/variance-band` payloads shared by the panel and tab
 *  specs. Hand-written in the Band shape of the plan's Global Constraints;
 *  the statistics themselves are tested in tests/analytics/. */
const H20: BandHorizon = {
  horizon: 20, weeks_span: 5.3,
  run: { p80: 3, p95: 4, p95_lo: 4, p95_hi: 5 },
  drawdown: { p80: 3.12, p95: 4.4, p95_lo: 3.9, p95_hi: 5.06 },
};
const H50: BandHorizon = {
  horizon: 50, weeks_span: 13.2,
  run: { p80: 4, p95: 7, p95_lo: 6, p95_hi: 8 },
  drawdown: { p80: 4.81, p95: 6.62, p95_lo: 5.9, p95_hi: 7.4 },
};

/** A full band with no `dollars` key: the server omits it, never nulls it. */
const BASE: VarianceBandOk = {
  status: 'ok', scope: 'whole_book', asof: '2026-10-16', days: 160, weeks: 38, pool: 'v2',
  composition: { days_by_era: { v2: 118, legacy: 42 }, trades_by_horizon: { '2w': 88, '4w': 131, unknown: 3 } },
  horizons: [H20, H50],
  current: {
    run: 4, run_age_days: 9, drawdown: 5.27, drawdown_age_days: 23,
    run_zone: 'normal', drawdown_zone: 'rough', zone: 'rough',
  },
  expr: { value: 0.214, n: 222, start: '2026-01-05', end: '2026-10-16', ci: [0.02, 0.41], not_positive: false },
};

/** Run normal, drawdown rough, positive ExpR, dollars present. */
export const BAND_OK: VarianceBandOk = { ...BASE, dollars: { median_risk: 59.26, drawdown_usd: 312.34 } };

/** The 50-day run band tied (p80 == p95): its rough zone is empty. No dollars. */
export const BAND_TIE: VarianceBandOk = {
  ...BASE,
  horizons: [H20, { ...H50, run: { p80: 5, p95: 5, p95_lo: 4, p95_hi: 6 } }],
};

/** Both statistics outside, ExpR interval straddling 0: the caveat shows. */
export const BAND_NOT_POSITIVE: VarianceBandOk = {
  ...BASE,
  current: {
    run: 9, run_age_days: 15, drawdown: 8.4, drawdown_age_days: 41,
    run_zone: 'outside', drawdown_zone: 'outside', zone: 'outside',
  },
  expr: { value: 0.05, n: 140, start: '2026-02-02', end: '2026-10-16', ci: [-0.12, 0.22], not_positive: true },
  dollars: { median_risk: 59.26, drawdown_usd: 497.78 },
};

export const BAND_INSUFFICIENT: VarianceBandInsufficient = {
  status: 'insufficient', scope: 'whole_book', days: 64, weeks: 15,
};
```

- [ ] **Step 2: Write the failing panel spec**

Create `frontend/src/app/workspaces/analytics/tabs/variance-band-panel.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AnalyticsStore } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { BAND_INSUFFICIENT, BAND_NOT_POSITIVE, BAND_OK, BAND_TIE } from './variance-band.fixture';
import { CAPTION, CAVEAT, HEADER_COPY, ZONE_COPY } from './variance-band.model';
import { VarianceBandPanel } from './variance-band-panel';

function render(band: unknown, error: string | null = null) {
  const reload = vi.fn();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: AnalyticsStore, useValue: { varianceBand: signal(band), varianceBandError: signal(error), reload } },
      { provide: ConnectionStore, useValue: { currency: signal('$') } },
    ],
  });
  const fixture = TestBed.createComponent(VarianceBandPanel);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const bar = (key: string) => el.querySelector(`.bar[data-bar="${key}"]`) as HTMLElement;
  return { el, bar, reload };
}

describe('VarianceBandPanel', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('is titled and scoped, and has no control at all', () => {
    const { el } = render(BAND_OK);
    expect(el.querySelector('sb-panel-header h2')?.textContent).toBe('Normal bad luck');
    expect(el.textContent).toContain(HEADER_COPY);
    // Non-interactive: no hint, no Table toggle, no link, nothing focusable.
    expect(el.querySelectorAll('button, a, [tabindex], sb-hint').length).toBe(0);
  });

  it('draws two bars, each with three labelled segments and their values as text', () => {
    const { bar } = render(BAND_OK);
    const run = bar('run');
    const drawdown = bar('drawdown');
    expect(run.querySelector('.bar-label')?.textContent).toBe('Losing days in a row');
    expect(drawdown.querySelector('.bar-label')?.textContent).toBe('Drawdown over the last 50 close days');
    expect([...run.querySelectorAll('.track .seg')].map((s) => s.getAttribute('data-zone')))
      .toEqual(['normal', 'rough', 'outside']);
    expect([...run.querySelectorAll('.legend li')].map((li) => li.textContent?.replace(/\s+/g, ' ').trim()))
      .toEqual(['Normal ≤ 4 days', 'Rough > 4 to ≤ 7 days', 'Outside > 7 days']);
    expect(drawdown.querySelector('.legend')?.textContent).toContain('> 6.6R');
  });

  it('skips the rough segment when p80 equals p95', () => {
    const { bar } = render(BAND_TIE);
    expect([...bar('run').querySelectorAll('.track .seg')].map((s) => s.getAttribute('data-zone')))
      .toEqual(['normal', 'outside']);
    expect(bar('run').querySelector('.legend')?.textContent).not.toContain('Rough');
    expect([...bar('drawdown').querySelectorAll('.track .seg')]).toHaveLength(3);
  });

  it("writes each bar's zone in words under it", () => {
    const ok = render(BAND_OK);
    expect(ok.bar('run').querySelector('.zone')?.textContent).toBe(ZONE_COPY.normal);
    expect(ok.bar('drawdown').querySelector('.zone')?.textContent).toBe(ZONE_COPY.rough);
    TestBed.resetTestingModule();
    const outside = render(BAND_NOT_POSITIVE);
    expect(outside.bar('run').querySelector('.zone')?.textContent).toBe(ZONE_COPY.outside);
    expect(outside.bar('drawdown').querySelector('.zone')?.textContent).toBe(ZONE_COPY.outside);
  });

  it('gives the marker a text equivalent, on screen and to screen readers', () => {
    const { bar } = render(BAND_OK);
    expect(bar('run').querySelector('.now')?.textContent).toBe('now: 4 days, 9 calendar days long');
    expect(bar('drawdown').querySelector('.now')?.textContent)
      .toBe('now: 5.3R (≈ $312.34), 23 calendar days since the peak');
    const track = bar('run').querySelector('.track') as HTMLElement;
    expect(track.getAttribute('role')).toBe('img');
    expect(track.getAttribute('aria-label')).toContain('now: 4 days, 9 calendar days long');
    // BAND_OK's 50-day run band: p80 4, p95 7 -> scaleMax 8.75; a run of 4 sits at 45.71%.
    expect(parseFloat((bar('run').querySelector('.marker') as HTMLElement).style.left)).toBeCloseTo(45.714, 2);
  });

  it('shows the uncertainty, the spans, the 20-day line, ExpR with N and window, and composition', () => {
    const { el } = render(BAND_OK);
    const text = el.textContent as string;
    expect(text).toContain('p95 ≈ 7 (6–8)');
    expect(text).toContain('p95 ≈ 6.6R (5.9–7.4R)');
    expect(text).toContain("50 close days ≈ 13.2 weeks at this book's pace");
    expect(text).toContain("20 close days ≈ 5.3 weeks at this book's pace");
    expect(text).toContain('Over 20 close days: p95 4 days in a row, 4.4R drawdown');
    expect(el.querySelector('.expr')?.textContent).toBe('Book: ExpR +0.21R over N=222 trades (2026-01-05 to 2026-10-16)');
    expect(el.querySelector('.composition')?.textContent)
      .toBe('Close days: 118 v2, 42 legacy · Trades: 2w 88, 4w 131, unknown 3');
    expect(el.querySelector('.caption')?.textContent).toBe(CAPTION);
  });

  it('adds the caveat only when ExpR is not positive', () => {
    expect(render(BAND_OK).el.textContent).not.toContain(CAVEAT);
    TestBed.resetTestingModule();
    const { el } = render(BAND_NOT_POSITIVE);
    expect(el.querySelector('.caveat')?.textContent).toBe(CAVEAT);
  });

  it('shows approximate dollars and their derivation only when the band carries them', () => {
    const withDollars = render(BAND_OK).el;
    expect(withDollars.querySelector('.dollar-note')?.textContent)
      .toBe('≈ $ = R × the median per-trade dollar risk ($59.26), from shares × entry-to-stop distance.');
    TestBed.resetTestingModule();
    const without = render(BAND_TIE).el;
    expect(without.querySelector('.dollar-note')).toBeNull();
    expect(without.textContent).not.toContain('≈ $');
    expect(without.textContent).not.toContain('—');   // omitted, never a dash
  });

  it('says what is missing when the book is too short, and draws no bar', () => {
    const { el } = render(BAND_INSUFFICIENT);
    expect(el.querySelector('.insufficient')?.textContent)
      .toBe('Needs 100 close days over 20 weeks (64 days, 15 weeks so far).');
    expect(el.querySelector('.bar')).toBeNull();
  });

  it('replaces the body with a retry surface that retries only this panel', () => {
    const { el, reload } = render(null, 'The admin is not responding.');
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
    expect(el.querySelector('.bar')).toBeNull();
    (el.querySelector('sb-panel-error button') as HTMLButtonElement).click();
    expect(reload).toHaveBeenCalledWith('varianceBand');
  });

  it('never says "edge" in any state', () => {
    for (const band of [BAND_OK, BAND_TIE, BAND_NOT_POSITIVE, BAND_INSUFFICIENT]) {
      TestBed.resetTestingModule();
      expect(render(band).el.textContent).not.toMatch(/\bedge\b/i);
    }
  });
});

describe('variance-band-panel.ts layout', () => {
  const src = readFileSync(
    join(process.cwd(), 'src/app/workspaces/analytics/tabs/variance-band-panel.ts'), 'utf8',
  );

  it('stacks the bars on phones and uses only declared breakpoints', () => {
    expect(src).toMatch(/@media \(max-width: 639px\) \{ \.bars \{ grid-template-columns: 1fr; \} \}/);
    const allowed = new Set(['639', '640', '1023', '1024', '1439', '1440', '1919', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });

  it('wraps copy instead of truncating it', () => {
    expect(src).not.toMatch(/text-overflow:\s*ellipsis/);
    expect(src).not.toMatch(/white-space:\s*nowrap/);
  });
});
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/variance-band-panel.spec.ts`
Expected: FAIL — `./variance-band-panel` cannot be resolved.

- [ ] **Step 4: Write the panel**

Create `frontend/src/app/workspaces/analytics/tabs/variance-band-panel.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { BandQuantiles, BandZone, VarianceBandInsufficient, VarianceBandOk } from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { Panel } from '../../../ui/layout';
import { PanelError } from '../../../ui/panel-error';
import { PanelHeader } from '../../../ui/panel-header';
import {
  BAR_LABELS, BandSegment, BandUnit, CAPTION, CAVEAT, HEADER_COPY, PANEL_TITLE, ZONE_COPY,
  bandSegments, barAriaLabel, compositionLine, dollarNote, drawdownMarkerText, exprLine,
  insufficientCopy, markerPercent, runMarkerText, secondaryText, spanText, uncertaintyText,
} from './variance-band.model';

/** One bar, fully resolved: the template only lays it out. */
interface BarView {
  key: 'run' | 'drawdown';
  label: string;
  segments: BandSegment[];
  marker: number;
  markerText: string;
  zone: BandZone;
  zoneText: string;
  uncertainty: string;
  aria: string;
}

export interface BandView {
  bars: BarView[];
  span50: string;
  span20: string;
  secondary: string;
  expr: string;
  caveat: string | null;
  composition: string;
  dollarNote: string | null;
}

function barView(
  key: BarView['key'], q: BandQuantiles, unit: BandUnit, value: number, markerText: string, zone: BandZone,
): BarView {
  const label = BAR_LABELS[key];
  const segments = bandSegments(q, unit);
  return {
    key, label, segments, marker: markerPercent(value, q), markerText, zone,
    zoneText: ZONE_COPY[zone], uncertainty: uncertaintyText(q, unit),
    aria: barAriaLabel(label, segments, markerText),
  };
}

/** The whole panel's text and geometry for one `ok` band. The bars are
 *  placed against the LAST horizon (50 close days), the one the current
 *  state is zoned against; the first (20) is the secondary line. */
export function bandView(band: VarianceBandOk, currency: string): BandView {
  const h20 = band.horizons[0];
  const h50 = band.horizons[band.horizons.length - 1];
  const cur = band.current;
  return {
    bars: [
      barView('run', h50.run, 'days', cur.run, runMarkerText(cur), cur.run_zone),
      barView('drawdown', h50.drawdown, 'R', cur.drawdown, drawdownMarkerText(cur, band.dollars, currency), cur.drawdown_zone),
    ],
    span50: spanText(h50),
    span20: spanText(h20),
    secondary: secondaryText(h20),
    expr: exprLine(band.expr),
    caveat: band.expr.not_positive ? CAVEAT : null,
    composition: compositionLine(band.composition),
    dollarNote: band.dollars ? dollarNote(band.dollars, currency) : null,
  };
}

/** v175 "Normal bad luck": where the book's current losing run and 50-day
 *  drawdown sit against the range its own past trades produce by chance.
 *  Whole book, closed trades only; not interactive (Retry aside). */
@Component({
  selector: 'sb-variance-band-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, PanelError],
  template: `
    <sb-panel>
      <sb-panel-header [title]="title" />
      <p class="scope-line">{{ header }}</p>
      @if (store.varianceBandError(); as error) {
        <sb-panel-error [message]="error" (retry)="store.reload('varianceBand')" />
      } @else if (insufficient(); as band) {
        <p class="insufficient">{{ insufficientText(band) }}</p>
      } @else if (view(); as v) {
        <div class="bars">
          @for (bar of v.bars; track bar.key) {
            <section class="bar" [attr.data-bar]="bar.key">
              <h4 class="bar-label">{{ bar.label }}</h4>
              <div class="track" role="img" [attr.aria-label]="bar.aria">
                @for (seg of bar.segments; track seg.zone) {
                  <span class="seg" [attr.data-zone]="seg.zone" [style.width.%]="seg.width"></span>
                }
                <span class="marker" [style.left.%]="bar.marker"></span>
              </div>
              <ul class="legend">
                @for (seg of bar.segments; track seg.zone) {
                  <li [attr.data-zone]="seg.zone"><span class="key"></span>{{ seg.label }} <span class="num">{{ seg.range }}</span></li>
                }
              </ul>
              <p class="now">{{ bar.markerText }}</p>
              <p class="zone" [attr.data-zone]="bar.zone">{{ bar.zoneText }}</p>
              <p class="meta">{{ bar.uncertainty }}</p>
            </section>
          }
        </div>
        <p class="meta">{{ v.span50 }}</p>
        <p class="meta">{{ v.secondary }}</p>
        <p class="meta">{{ v.span20 }}</p>
        <p class="expr">{{ v.expr }}</p>
        @if (v.caveat) { <p class="caveat" role="note">{{ v.caveat }}</p> }
        <p class="composition">{{ v.composition }}</p>
        @if (v.dollarNote) { <p class="dollar-note">{{ v.dollarNote }}</p> }
        <p class="caption">{{ caption }}</p>
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    p { margin: var(--space-6) 0 0; overflow-wrap: anywhere; }
    .scope-line { font-size: var(--text-chip); color: var(--text-secondary); }
    .bars { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-14); margin-top: var(--space-10); }
    .bar { min-width: 0; }
    .bar-label { margin: 0 0 var(--space-6); font-size: var(--text-chip); color: var(--text-secondary); }
    .track { position: relative; display: flex; height: 14px; border-radius: var(--radius-sm); background: var(--bg); }
    .seg { display: block; height: 100%; min-width: 2px; opacity: 0.55; }
    [data-zone='normal'] .key, .seg[data-zone='normal'] { background: var(--pos); }
    [data-zone='rough'] .key, .seg[data-zone='rough'] { background: var(--warn); }
    [data-zone='outside'] .key, .seg[data-zone='outside'] { background: var(--neg); }
    .marker { position: absolute; top: -4px; bottom: -4px; width: 3px; margin-left: -1.5px; border-radius: 2px; background: var(--text); }
    .legend { display: flex; flex-wrap: wrap; gap: var(--space-6) var(--space-14); margin: var(--space-6) 0 0; padding: 0; list-style: none; font-size: var(--text-chip); color: var(--text-secondary); }
    .legend li { display: inline-flex; align-items: center; gap: var(--space-6); min-width: 0; }
    .key { flex: none; width: 10px; height: 10px; border-radius: var(--radius-sm); opacity: 0.55; }
    .num { color: var(--text); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
    .now { color: var(--text); font-variant-numeric: tabular-nums; }
    .zone { color: var(--text); font-weight: 600; }
    .meta, .composition, .dollar-note { font-size: var(--text-chip); color: var(--text-secondary); }
    .expr { color: var(--text); font-variant-numeric: tabular-nums; }
    .caveat { color: var(--warn); }
    .insufficient { color: var(--text-secondary); }
    .caption { font-size: var(--text-chip); color: var(--text-faint); }
    @media (max-width: 639px) { .bars { grid-template-columns: 1fr; } }
  `,
})
export class VarianceBandPanel {
  readonly store = inject(AnalyticsStore);
  private readonly connection = inject(ConnectionStore);

  protected readonly title = PANEL_TITLE;
  protected readonly header = HEADER_COPY;
  protected readonly caption = CAPTION;

  protected readonly insufficient = computed<VarianceBandInsufficient | null>(() => {
    const band = this.store.varianceBand();
    return band?.status === 'insufficient' ? band : null;
  });

  protected readonly view = computed<BandView | null>(() => {
    const band = this.store.varianceBand();
    return band?.status === 'ok' ? bandView(band, this.connection.currency()) : null;
  });

  protected insufficientText(band: VarianceBandInsufficient): string {
    return insufficientCopy(band.days, band.weeks);
  }
}
```

Before the first band arrives (`varianceBand()` null, no error) the panel shows its title and scope line only: no placeholder text that could read as a measured answer.

- [ ] **Step 5: Run the panel spec**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/variance-band-panel.spec.ts`
Expected: PASS, 13 tests, 0 failed.

- [ ] **Step 6: Mount it on the Overview tab, extend the tab's spec**

In `frontend/src/app/workspaces/analytics/tabs/overview.ts`:
1. Add `import { VarianceBandPanel } from './variance-band-panel';` after the `unit-format` import.
2. Add `VarianceBandPanel` to the component's `imports: [...]` array (after `RouterLink`).
3. Insert as the **last** child of `<div class="panels">`, right after the "By month" `</sb-panel>`:
   ```html
         <sb-variance-band-panel class="wide" />
   ```
4. Add to `styles`, right after the `.panels { ... }` rule:
   ```css
       /* v175: the Normal bad luck panel spans both columns; its own two bars
          take the columns from 640px up and stack below. */
       .wide { grid-column: 1 / -1; }
   ```

In `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts`:
1. Add `import { BAND_OK } from './variance-band.fixture';` after the `./overview` import.
2. In `storeStub`'s `base`, right after `equityCurveError: signal(null),` add:
   ```ts
       varianceBand: signal(null), varianceBandError: signal(null),
   ```
3. Add this test inside `describe('OverviewTab', ...)`, after "replaces a failed panel with a retry surface, not an empty chart":
   ```ts
     it('carries the whole-book Normal bad luck panel across both columns', () => {
       const { el } = render({ varianceBand: signal(BAND_OK) });
       const panel = el.querySelector('sb-variance-band-panel');
       expect(panel).not.toBeNull();
       expect(panel?.classList.contains('wide')).toBe(true);
       expect(panel?.textContent).toContain('Normal bad luck');
       expect(panel?.textContent).toContain("Whole book, closed trades only. Filters don't apply.");
     });
   ```

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/overview.spec.ts`
Expected: PASS, every existing test unchanged plus the new one; the breakpoint test still passes (the added rule has no media query).

- [ ] **Step 7: Run the three v175 frontend specs together**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include "src/app/workspaces/analytics/tabs/variance-band*.spec.ts"`
Expected: PASS, the model spec (19) and the panel spec (13), 0 failed.

- [ ] **Step 8: Commit**

Write `$SCRATCH/v175-10-msg.txt`:

```text
feat(ui): Normal bad luck panel on Analytics -> Overview (v175)

Two band bars (losing days in a row; drawdown over the last 50 close
days) with labelled normal/rough/outside segments, values as text and a
"now" marker with its text equivalent; band uncertainty, 20- and 50-day
spans, ExpR with N and window, composition, approximate dollars with
their derivation, and the caption. Non-interactive (Retry aside), full
width on the tab, bars stacked below 640px.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $WT add frontend/src/app/workspaces/analytics/tabs/variance-band.fixture.ts frontend/src/app/workspaces/analytics/tabs/variance-band-panel.ts frontend/src/app/workspaces/analytics/tabs/variance-band-panel.spec.ts frontend/src/app/workspaces/analytics/tabs/overview.ts frontend/src/app/workspaces/analytics/tabs/overview.spec.ts
git -C $WT commit -F "$SCRATCH/v175-10-msg.txt"
git -C $R status --short
```
Expected: one commit on the branch; the main tree shows no change from this task.

### Task V175-11: Three-width Playwright check of the panel

**Model:** sonnet — run the app and judge the layout at three widths.

**Files:**
- Create (session scratchpad only, never committed): `$SCRATCH/v175-widths.cjs`
- Modify only if a check fails: `frontend/src/app/workspaces/analytics/tabs/variance-band-panel.ts` (styles), re-running its spec

**Interfaces:**
- Consumes: V175-5's route (real endpoint on the local admin), V175-10's panel (selector `sb-variance-band-panel`, `.bar[data-bar]`, `.track`, `.seg`, `.now`, `.zone`, `.caption`), the shapes of V175-10's fixtures (copied into the stub below, since a Node script cannot import the TypeScript fixture).
- Produces: the measurement lines and screenshots named in the task report.

**Why stubbed states as well as the real one.** The local database decides which state the real endpoint returns (often `insufficient` on a thin local book), so the check first captures the real response once, then serves four fixed bands through `page.route` so every state (rough with dollars, tie without dollars, outside with the caveat, insufficient) is seen at all three widths. Logging in uses `ADMIN_USERNAME`/`ADMIN_PASSWORD` read from `$R/.env` inside the script (`process.loadEnvFile`), never printed, never on the command line; the local admin reads the same `.env` (its config falls back from `$WT/.env` to a `load_dotenv()` search that walks up from `$WT/swingbot` to `$R`), so the local instance is built from those values and never from an `admin`/`admin` default.

- [ ] **Step 1: Start the local admin and the dev server**

If the local database is not a current replica, run `/replicate-prod-db` first (the real-endpoint capture reads it; nothing it shows is quoted as the book's figure). Then start both servers in the background (Bash `run_in_background: true`, one call each):

```bash
python $WT/admin_ui.py
```

```bash
npm --prefix $WT/frontend exec -- ng serve --port 4123
```

Wait until `curl -s -o /dev/null -w "%{http_code}" http://localhost:4123/app/` prints `200`. If the admin cannot reach a database and exits, stop here, say so in the task report, and leave the check to V175-14 Step 5 (production); do not skip it silently.

- [ ] **Step 2: Write the check script**

Create `$SCRATCH/v175-widths.cjs`:

```js
// v175 three-width check for sb-variance-band-panel. Usage: node v175-widths.cjs <R> <WT> <outDir>
const { createRequire } = require('node:module');
const { mkdirSync, writeFileSync } = require('node:fs');
const [repo, wt, out] = process.argv.slice(2);
const { chromium } = createRequire(`${wt}/frontend/package.json`)('playwright');
mkdirSync(out, { recursive: true });

const BASE = 'http://localhost:4123';
const PAGE = `${BASE}/app/analytics?tab=overview`;
const h20 = { horizon: 20, weeks_span: 5.3, run: { p80: 3, p95: 4, p95_lo: 4, p95_hi: 5 },
              drawdown: { p80: 3.12, p95: 4.4, p95_lo: 3.9, p95_hi: 5.06 } };
const h50 = { horizon: 50, weeks_span: 13.2, run: { p80: 4, p95: 7, p95_lo: 6, p95_hi: 8 },
              drawdown: { p80: 4.81, p95: 6.62, p95_lo: 5.9, p95_hi: 7.4 } };
const base = {
  status: 'ok', scope: 'whole_book', asof: '2026-10-16', days: 160, weeks: 38, pool: 'v2',
  composition: { days_by_era: { v2: 118, legacy: 42 }, trades_by_horizon: { '2w': 88, '4w': 131, unknown: 3 } },
  horizons: [h20, h50],
  current: { run: 4, run_age_days: 9, drawdown: 5.27, drawdown_age_days: 23,
             run_zone: 'normal', drawdown_zone: 'rough', zone: 'rough' },
  expr: { value: 0.214, n: 222, start: '2026-01-05', end: '2026-10-16', ci: [0.02, 0.41], not_positive: false },
};
const STATES = {
  rough: { ...base, dollars: { median_risk: 59.26, drawdown_usd: 312.34 } },
  tie: { ...base, horizons: [h20, { ...h50, run: { p80: 5, p95: 5, p95_lo: 4, p95_hi: 6 } }] },
  outside: { ...base,
    current: { run: 9, run_age_days: 15, drawdown: 8.4, drawdown_age_days: 41,
               run_zone: 'outside', drawdown_zone: 'outside', zone: 'outside' },
    expr: { value: 0.05, n: 140, start: '2026-02-02', end: '2026-10-16', ci: [-0.12, 0.22], not_positive: true },
    dollars: { median_risk: 59.26, drawdown_usd: 497.78 } },
  insufficient: { status: 'insufficient', scope: 'whole_book', days: 64, weeks: 15 },
};

/** The .env admin credentials, kept in this process only: never printed. */
function credentials() {
  process.loadEnvFile(`${repo}/.env`);
  const { ADMIN_USERNAME: username, ADMIN_PASSWORD: password } = process.env;
  if (!username || !password) throw new Error('ADMIN_USERNAME / ADMIN_PASSWORD missing from .env');
  return { username, password };
}

async function measure(page) {
  return page.evaluate(() => {
    const panel = document.querySelector('sb-variance-band-panel');
    if (!panel) return { panel: false };
    const bars = [...panel.querySelectorAll('.bar')].map((b) => b.getBoundingClientRect());
    const clipped = [...panel.querySelectorAll('p, li, h4')]
      .filter((el) => el.scrollWidth > el.clientWidth + 1).map((el) => el.className || el.tagName);
    const doc = document.documentElement;
    return {
      panel: true,
      pageOverflowPx: Math.max(doc.scrollWidth - doc.clientWidth, document.body.scrollWidth - document.body.clientWidth),
      bars: bars.length,
      stacked: bars.length === 2 ? bars[1].top >= bars[0].bottom - 1 : null,
      sideBySide: bars.length === 2 ? Math.abs(bars[1].top - bars[0].top) < 2 : null,
      segments: [...panel.querySelectorAll('.bar')].map((b) => b.querySelectorAll('.seg').length),
      focusable: panel.querySelectorAll('button, a, [tabindex]').length,
      clipped,
      now: [...panel.querySelectorAll('.now')].map((el) => el.textContent.trim()),
      zones: [...panel.querySelectorAll('.zone')].map((el) => el.textContent.trim()),
      caveat: panel.querySelector('.caveat')?.textContent.trim() ?? null,
      insufficient: panel.querySelector('.insufficient')?.textContent.trim() ?? null,
    };
  });
}

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${BASE}/app/`, { waitUntil: 'domcontentloaded' });
  const ok = await page.evaluate(async (body) => (await fetch('/api/v1/session', {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })).ok, credentials());
  if (!ok) throw new Error('local sign-in with the .env credentials was refused');

  // 1. The real endpoint, once: its status line only (no figure is quoted).
  const real = await page.evaluate(async () => (await fetch('/api/v1/analytics/variance-band', { credentials: 'include' })).json());
  console.log('real', JSON.stringify({ status: real.status, scope: real.scope, keys: Object.keys(real).sort() }));
  await page.goto(PAGE, { waitUntil: 'load' });
  await page.waitForSelector('sb-variance-band-panel', { timeout: 30000 });
  await page.waitForTimeout(1200);
  await page.locator('sb-variance-band-panel').screenshot({ path: `${out}/real-1280.png` });

  // 2. Each fixed state at each width.
  let state = 'rough';
  await page.route('**/api/v1/analytics/variance-band', (route) => route.fulfill({ json: STATES[state] }));
  const report = [];
  for (state of Object.keys(STATES)) {
    for (const width of [1280, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(PAGE, { waitUntil: 'load' });
      await page.waitForSelector('sb-variance-band-panel .scope-line', { timeout: 30000 });
      await page.waitForTimeout(800);
      const m = await measure(page);
      report.push({ state, width, ...m });
      console.log(state, width, JSON.stringify(m));
      await page.locator('sb-variance-band-panel').screenshot({ path: `${out}/${state}-${width}.png` });
    }
  }
  writeFileSync(`${out}/report.json`, JSON.stringify(report, null, 2));
  await browser.close();
})();
```

- [ ] **Step 3: Run it**

Run (install Chromium once per machine first if Playwright asks: `npm --prefix $WT/frontend exec -- playwright install chromium`):

```bash
node "$SCRATCH/v175-widths.cjs" "$R" "$WT" "$SCRATCH/v175-widths"
```

Expected:
- `real`: `status` is `ok` or `insufficient`, `scope` is `whole_book`, and `keys` is exactly the Global Constraints key set for that status (`dollars` may be absent, never present as `null`).
- Every state at every width: `pageOverflowPx` 0, `focusable` 0, `clipped` `[]`.
- `rough`, `tie`, `outside`: `bars` 2; at 390 `stacked` true; at 768 and 1280 `sideBySide` true. `segments` is `[3, 3]` for `rough` and `outside`, `[2, 3]` for `tie`.
- `rough`: `now` = `["now: 4 days, 9 calendar days long", "now: 5.3R (≈ $312.34), 23 calendar days since the peak"]` with the local currency symbol in place of `$` if it differs; `zones` = the normal and rough copy; `caveat` null.
- `tie`: the drawdown `now` has no `(≈ …)`.
- `outside`: both `zones` read `Beyond 95% of simulated runs`; `caveat` is the CAVEAT text.
- `insufficient`: `bars` 0, `insufficient` = `Needs 100 close days over 20 weeks (64 days, 15 weeks so far).`

- [ ] **Step 4: Look at the screenshots**

Open `rough-1280.png`, `rough-768.png`, `rough-390.png`, `tie-390.png`, `outside-390.png` and `insufficient-390.png` with the Read tool and confirm by eye: the segments read left to right normal, rough, outside with their ranges as text under them; the marker sits on the normal segment's right edge on the run bar (run 4 = p80 4) and inside the rough segment on the drawdown bar (`rough`), past the outside boundary on both (`outside`); every line wraps inside the panel at 390 with nothing cut off; the panel spans the tab's full width. Any failed expectation is fixed in `variance-band-panel.ts`'s styles only, the panel spec re-run (`npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/variance-band-panel.spec.ts`), and the script re-run. Stop both background servers afterwards. Record the measurement lines (not the real band's figures) in the task report.

- [ ] **Step 5: Commit (only if Step 4 changed a style)**

Write `$SCRATCH/v175-11-msg.txt`:

```text
fix(ui): Normal bad luck panel layout at <width> -- <what was wrong> (v175)

Found by the three-width Playwright check (390/768/1280).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $WT add frontend/src/app/workspaces/analytics/tabs/variance-band-panel.ts
git -C $WT commit -F "$SCRATCH/v175-11-msg.txt"
git -C $R status --short
```
Expected: nothing to commit when every check passed first time; otherwise one fix commit on the branch. The main tree shows no change from this task.

