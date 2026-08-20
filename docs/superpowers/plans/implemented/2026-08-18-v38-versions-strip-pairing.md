Version: ui 1.7.2 · bot 1.2.1
Bump: ui minor (1.7.2 → 1.8.0); bot none

# Versions Strip: Newest-First Axis + Paired-Version Hover — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flip the Versions workspace strip so the current/live segment of every
lane reads first (left edge), matching the change-stream list's existing
newest-first order; and let hovering any segment show which versions of every
other component were paired with it, without ever calling that pairing
"compatible" or "tested."

**Architecture:** Pure client-side change to one signal store
(`VersionsStore`) and one component (`Versions`). `lanes()` and `bracket()`
gain a coordinate flip (`1 - start - width`) applied as the very last step
after existing geometry math, so `applyFloor` and the run-collapsing logic are
untouched. `LaneSegment` gains a `pairedWith` field populated from a release
snapshot the lane-building loop already looks up for `lastSeen` — no new
computation, no API change. The component adds a local hover signal, a custom
tooltip (mirroring `line-chart.ts`'s existing pointer-tooltip pattern), and a
CSS box-shadow "spotlight" overlay that dims every lane outside the hovered
segment's time window in one paint.

**Tech Stack:** Angular 21 (signals, `@ngrx/signals` store), Vitest 4 via
`@angular/build:unit-test`, TypeScript.

## Global Constraints

- **Never call this "compatible" or a "compatibility/support matrix."** The
  page's own doc comment in `versions.ts` is deliberate: it claims only that
  components shipped in the same release, never that anyone verified they
  work together. All new UI copy uses "paired with" / "shipped alongside."
- **One convention: newest-first, everywhere on the page.** The strip's axis
  direction must match the change-stream list below it (already newest-first,
  unchanged by this plan).
- **No backend/API change.** `build_version_matrix.py` and
  `version_history.json` are untouched. Every new field is derived
  client-side from data already on the wire (`Release.versions` is already a
  full per-release snapshot of every component, not just the ones that
  changed that release).
- **`applyFloor` and the run-collapsing logic in `lanes()` are untouched.**
  The axis flip is a coordinate transform applied after they run, not a
  change to how widths are computed.
- Run frontend tests with `cd frontend && npx ng test --watch=false`. If it
  times out at exactly 60s with `[vitest-pool-runner]: Timeout waiting for
  worker to respond` and `Test Files no tests`, that's known machine-load
  flakiness (`docs/claude/testing-cost.md`) — just re-run, don't diagnose it.

---

## File Structure

- `frontend/src/app/stores/versions.store.ts` — `LaneSegment` interface gains
  `pairedWith`; `lanes()` and `bracket()` computeds flip their emitted
  fractions.
- `frontend/src/app/stores/versions.store.spec.ts` — new assertions for the
  flip and for `pairedWith`.
- `frontend/src/styles/tokens.css` — one new token, `--overlay-dim`.
- `frontend/src/app/workspaces/versions/versions.ts` — ticks order, the
  absent-region binding (now driven by data instead of a hardcoded CSS side),
  the hover signal, the custom tooltip, and the spotlight overlay.
- `frontend/src/app/workspaces/versions/versions.spec.ts` — new assertions
  for tick order, the absent region's flipped position, and the hover
  tooltip/spotlight; existing test refactored onto a shared `seed()` helper
  (matches the pattern `versions.store.spec.ts` already uses) so the new
  tests don't duplicate its `TestBed` boilerplate.

## Parallelisation

None of these four tasks can run concurrently. Task 1 and Task 2 both edit
`versions.store.ts` and must land before Task 3/4 can be written against the
new `LaneSegment` shape; Task 3 and Task 4 both edit `versions.ts` and Task 4
depends on Task 3's absent-region binding change being in place first
(both touch the same template file's geometry). Total surface is two files
plus their two spec files — not worth splitting across sessions.

---

### Task 1: Flip the strip's time axis in the store

**Files:**
- Modify: `frontend/src/app/stores/versions.store.ts` (the `lanes` computed,
  lines 174-229; the `bracket` computed, lines 234-249)
- Test: `frontend/src/app/stores/versions.store.spec.ts`

**Interfaces:**
- Consumes: nothing new — this task only changes the fraction values already
  emitted by `lanes()`/`bracket()`. `LaneSegment.start`, `Lane.absentWidth`
  (the field itself, not its rendered CSS side — that's Task 3), and
  `bracket().start` keep their existing types.
- Produces: `LaneSegment.start` and `bracket().start` are now newest-first
  (the current/newest segment of every lane sits at `start ≈ 0`; the
  earliest segment's trailing edge sits at `start + width ≈ 1 - absentWidth`).
  Task 3 and Task 4 consume this ordering as given.

- [ ] **Step 1: Write the failing tests**

Add to `versions.store.spec.ts`, inside the `describe('lane geometry', ...)`
block (after the existing `'brackets the visible page'` test):

```ts
it('draws the newest segment flush to the strip\'s leading edge', () => {
  // RESPONSE's `ui` lane has two runs (1.0.0 then 1.2.0); the current one
  // is the flip's whole point — it must be at start 0, not buried at the
  // trailing edge where the old oldest-first axis put it.
  const ui = store.lanes().find((l) => l.component === 'ui')!;
  const current = ui.segments[ui.segments.length - 1];
  expect(current.current).toBe(true);
  expect(current.start).toBeCloseTo(0, 5);
});

it('trails the earliest segment off toward the strip\'s far edge', () => {
  const ui = store.lanes().find((l) => l.component === 'ui')!;
  const earliest = ui.segments[0];
  // ui's absentWidth is 0 (it existed from the first release), so the
  // earliest segment's trailing edge lands exactly at 1.
  expect(earliest.start + earliest.width).toBeCloseTo(1, 5);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false`
Expected: the two new tests FAIL — `current.start` is currently close to
`1 - width` (the old oldest-first placement put the current segment's
trailing edge, not its leading edge, at `start`), not `0`.

- [ ] **Step 3: Flip `lanes()`'s emitted fractions**

In `versions.store.ts`, inside the `lanes` computed's `components().map(...)`
callback, change the segment-building loop from:

```ts
        let cursor = absentWidth;
        const segments = runs.map((run, i) => {
          const segment: LaneSegment = {
            version: run.version,
            start: cursor,
            width: widths[i],
            firstSeen: ordered.find((r) => t(r.date) === run.from)?.date ?? '',
            lastSeen: ordered.find((r) => t(r.last_seen) === run.to)?.last_seen ?? '',
            current: i === runs.length - 1,
          };
          cursor += widths[i];
          return segment;
        });
```

to:

```ts
        // Newest-first: the axis is flipped last, after every existing
        // width/position computation, so applyFloor and the run-collapsing
        // above are untouched. `cursor` still accumulates chronologically
        // (oldest to newest) exactly as before; only the emitted `start`
        // is mirrored around the strip's midpoint.
        let cursor = absentWidth;
        const segments = runs.map((run, i) => {
          const segment: LaneSegment = {
            version: run.version,
            start: 1 - cursor - widths[i],
            width: widths[i],
            firstSeen: ordered.find((r) => t(r.date) === run.from)?.date ?? '',
            lastSeen: ordered.find((r) => t(r.last_seen) === run.to)?.last_seen ?? '',
            current: i === runs.length - 1,
          };
          cursor += widths[i];
          return segment;
        });
```

- [ ] **Step 4: Flip `bracket()`'s emitted fraction**

Change:

```ts
      // `visible` is newest-first, so its last row is the oldest on screen.
      const from = t(rows[rows.length - 1].date);
      const to = t(rows[0].last_seen);
      const start = (from - t0) / span;
      return { start, width: Math.max((to - from) / span, 2 / Math.max(1, stripWidth())) };
```

to:

```ts
      // `visible` is newest-first, so its last row is the oldest on screen.
      const from = t(rows[rows.length - 1].date);
      const to = t(rows[0].last_seen);
      const chronoStart = (from - t0) / span;
      const width = Math.max((to - from) / span, 2 / Math.max(1, stripWidth()));
      // Same mirror as lanes() above — flipped last, after the width floor.
      return { start: 1 - chronoStart - width, width };
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false`
Expected: PASS, including the two new tests and every pre-existing test in
`versions.store.spec.ts` (the file's own comment already notes none of the
existing geometry assertions hard-code a direction — they compare relative
widths or check the lane sums to 1 — so none of them needed to change).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/stores/versions.store.ts frontend/src/app/stores/versions.store.spec.ts
git commit -m "feat(versions): flip the strip's axis to newest-first

Matches the change-stream list below it, which already reverses the
wire order exactly once. lanes() and bracket() now mirror their
emitted start fraction (1 - start - width) as the last step, after
applyFloor and the run-collapsing logic -- neither of which changes.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Capture paired versions on every segment

**Files:**
- Modify: `frontend/src/app/stores/versions.store.ts` (the `LaneSegment`
  interface; the `lanes` computed's segment-building loop, just edited in
  Task 1)
- Test: `frontend/src/app/stores/versions.store.spec.ts`

**Interfaces:**
- Consumes: `LaneSegment` as flipped in Task 1.
- Produces: `LaneSegment.pairedWith: Record<string, string>` — every other
  component's version as of this segment's `lastSeen`, excluding this
  segment's own component and excluding any component that hadn't shipped
  yet (`null` on the wire). Task 4 renders this directly.

- [ ] **Step 1: Write the failing tests**

Add to `versions.store.spec.ts`'s `describe('lane geometry', ...)` block:

```ts
it('captures paired versions from the run-closing release', () => {
  // a3 closes ui's current run and carries { ui: '1.2.0', bot: '1.1.2',
  // worker: '0.1.0' } -- pairedWith is that snapshot minus ui itself.
  const ui = store.lanes().find((l) => l.component === 'ui')!;
  const current = ui.segments[ui.segments.length - 1];
  expect(current.pairedWith).toEqual({ bot: '1.1.2', worker: '0.1.0' });
});

it('excludes a component that had not shipped yet from pairedWith', () => {
  // a2 closes ui's first run (a1..a2, both ui 1.0.0) and carries
  // { ui: '1.0.0', bot: '1.1.2', worker: null } -- worker must not appear.
  const ui = store.lanes().find((l) => l.component === 'ui')!;
  const earliest = ui.segments[0];
  expect(earliest.pairedWith).toEqual({ bot: '1.1.2' });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false`
Expected: FAIL — `pairedWith` does not exist on `LaneSegment` yet (`undefined`
does not equal the expected object).

- [ ] **Step 3: Add the field and populate it**

In `versions.store.ts`, add to the `LaneSegment` interface (after
`current: boolean;`):

```ts
  /** Every other component's version as of this segment's last_seen -- the
   *  ceiling reached while this version was active. Never includes the
   *  segment's own component, and never a component that hadn't shipped
   *  yet (null on the wire -- absent must not read as a value, same rule
   *  `absentWidth` already enforces for this lane's own component). */
  pairedWith: Record<string, string>;
```

Then, in the `lanes` computed's segment-building loop (just edited in
Task 1), capture the closing release once and reuse it for both `lastSeen`
and `pairedWith`:

```ts
        let cursor = absentWidth;
        const segments = runs.map((run, i) => {
          const closingRelease = ordered.find((r) => t(r.last_seen) === run.to);
          const segment: LaneSegment = {
            version: run.version,
            start: 1 - cursor - widths[i],
            width: widths[i],
            firstSeen: ordered.find((r) => t(r.date) === run.from)?.date ?? '',
            lastSeen: closingRelease?.last_seen ?? '',
            current: i === runs.length - 1,
            pairedWith: Object.fromEntries(
              Object.entries(closingRelease?.versions ?? {}).filter(
                (entry): entry is [string, string] =>
                  entry[0] !== component && entry[1] !== null,
              ),
            ),
          };
          cursor += widths[i];
          return segment;
        });
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false`
Expected: PASS, all tests in the file including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/stores/versions.store.ts frontend/src/app/stores/versions.store.spec.ts
git commit -m "feat(versions): capture paired-component versions per segment

LaneSegment.pairedWith reuses the run-closing release lookup lanes()
already does for lastSeen -- no new computation, no API change.
Excludes the segment's own component and any component that hadn't
shipped yet, same rule absentWidth already enforces.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Flip the template to match — ticks and the absent region

**Files:**
- Modify: `frontend/src/app/workspaces/versions/versions.ts`
- Test: `frontend/src/app/workspaces/versions/versions.spec.ts`

**Interfaces:**
- Consumes: `lane.absentWidth` (unchanged type, `number`), `store.firstDate()`
  / `store.lastDate()` (unchanged).
- Produces: the `.absent` region is now positioned by an inline `left`
  binding instead of a hardcoded CSS side, so Task 4's spotlight overlay can
  be added to the same `.strip` without fighting a stale `left: 0` rule.

- [ ] **Step 1: Write the failing tests**

`versions.spec.ts` currently builds its own `TestBed` inline inside its one
`it`. Replace the whole file's setup with a shared `seed()` helper (matching
the pattern `versions.store.spec.ts` already uses) and add the two new tests:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { VersionHistory } from '../../api/models';
import { Versions } from './versions';

/* The Versions page's one structural guarantee: an open-ended component
 * count costs vertical space, never horizontal. Chips wrap and lanes stack
 * by CSS, but a comment cannot enforce that property -- only a narrow host
 * with more components than the matrix could ever have represented can. */

/** Six components, one of them arriving late. The point is the count: this is
 *  three times what the matrix could represent at all, and the assertion is
 *  that it costs vertical space only. */
const SIX: VersionHistory = {
  generated_at: '2026-08-15 07:00:00 UTC',
  basis: 'Versions observed together in VERSION.json.',
  live: { ui: '2.0.0', bot: '1.1.2', worker: '0.3.0', schema: '4', api: '1.0.0', cron: '0.9.1' },
  stale: false,
  components: ['ui', 'bot', 'worker', 'schema', 'api', 'cron'],
  current: { ui: '2.0.0', bot: '1.1.2', worker: '0.3.0', schema: '4', api: '1.0.0', cron: '0.9.1' },
  releases: [
    { date: '2026-07-01', last_seen: '2026-07-09', commit: 'b1', subject: 'start',
      versions: { ui: '1.0.0', bot: '1.0.0', worker: null, schema: null, api: null, cron: null },
      changed: ['ui', 'bot'] },
    { date: '2026-07-10', last_seen: '2026-08-15', commit: 'b2', subject: 'the rest arrive',
      versions: { ui: '2.0.0', bot: '1.1.2', worker: '0.3.0', schema: '4', api: '1.0.0', cron: '0.9.1' },
      changed: ['ui', 'bot', 'worker', 'schema', 'api', 'cron'] },
  ],
};

/** Two components, one bump -- small enough that hover assertions in later
 *  tests can name an exact expected version instead of picking through SIX. */
const PAIRED: VersionHistory = {
  generated_at: '2026-08-15 07:00:00 UTC',
  basis: 'Versions observed together in VERSION.json.',
  live: { ui: '1.2.0', bot: '1.1.2' },
  stale: false,
  components: ['ui', 'bot'],
  current: { ui: '1.2.0', bot: '1.1.2' },
  releases: [
    { date: '2026-07-01', last_seen: '2026-07-04', commit: 'a1', subject: 'first',
      versions: { ui: '1.0.0', bot: '1.0.0' }, changed: ['ui', 'bot'] },
    { date: '2026-07-05', last_seen: '2026-07-31', commit: 'a2', subject: 'ui bumps',
      versions: { ui: '1.2.0', bot: '1.1.2' }, changed: ['ui', 'bot'] },
  ],
};

/** Stand the component up and answer its one request. Each test gets its
 *  own TestBed, same reasoning as the store spec's `seed()`: a fresh
 *  module per test is cheap here and avoids state leaking between cases. */
function seed(payload: VersionHistory): ComponentFixture<Versions> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
    ],
  });
  const fixture = TestBed.createComponent(Versions);
  TestBed.inject(HttpTestingController).expectOne('/api/v1/versions').flush(payload);
  return fixture;
}

describe('Versions', () => {
  it('does not widen when components are added', async () => {
    const fixture = seed(SIX);
    // A narrow host is the real test: the page must fit the container it is
    // given, not merely fit on a wide screen.
    fixture.nativeElement.style.width = '640px';
    await fixture.whenStable();
    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    expect(host.scrollWidth).toBeLessThanOrEqual(host.clientWidth);
  });

  it('puts the "now" tick first, matching the flipped axis', async () => {
    const fixture = seed(SIX);
    await fixture.whenStable();
    fixture.detectChanges();

    const ticks = (fixture.nativeElement as HTMLElement).querySelectorAll('.ticks span');
    expect(ticks).toHaveLength(2);
    expect(ticks[0].classList.contains('now')).toBe(true);
    expect(ticks[1].classList.contains('now')).toBe(false);
  });

  it('flushes the absent region against the trailing (oldest) edge', async () => {
    const fixture = seed(SIX);
    await fixture.whenStable();
    fixture.detectChanges();

    // 'worker' is one of SIX's late arrivals, so it has an absent region.
    const absent = (fixture.nativeElement as HTMLElement).querySelector('.absent') as HTMLElement;
    expect(absent).toBeTruthy();
    const leftPct = parseFloat(absent.style.left);
    const widthPct = parseFloat(absent.style.width);
    // Its trailing edge must sit flush at 100% -- the flipped axis's oldest
    // end -- regardless of the exact dates in the fixture.
    expect(leftPct + widthPct).toBeCloseTo(100, 1);
  });
});
```

- [ ] **Step 2: Run the tests to verify the two new ones fail**

Run: `cd frontend && npx ng test --watch=false`
Expected: `'puts the "now" tick first...'` FAILS (the DOM currently renders
`firstDate` before `lastDate`); `'flushes the absent region...'` FAILS
(`.absent`'s `style.left` is currently empty — the CSS rule sets `left: 0`
via stylesheet, not an inline binding, so `leftPct` reads `NaN`). The
`'does not widen...'` test still passes unchanged (it only moved onto the
new `seed()` helper).

- [ ] **Step 3: Swap the ticks and bind the absent region's position**

In `versions.ts`, change:

```html
      <div class="ticks">
        <span>{{ store.firstDate() }}</span>
        <span class="now">{{ store.lastDate() }} &#9650; now</span>
      </div>
```

to:

```html
      <div class="ticks">
        <span class="now">{{ store.lastDate() }} &#9650; now</span>
        <span>{{ store.firstDate() }}</span>
      </div>
```

And change:

```html
              @if (lane.absentWidth > 0) {
                <div class="absent" [style.width.%]="lane.absentWidth * 100"
                     title="This component did not exist yet"></div>
              }
```

to:

```html
              @if (lane.absentWidth > 0) {
                <div class="absent" [style.left.%]="(1 - lane.absentWidth) * 100"
                     [style.width.%]="lane.absentWidth * 100"
                     title="This component did not exist yet"></div>
              }
```

And drop the now-redundant `left: 0;` from the `.absent` CSS rule:

```css
    .absent { position: absolute; left: 0; top: 0; height: 100%;
              border: 1px dashed var(--border-strong); border-radius: 2px; }
```

becomes:

```css
    .absent { position: absolute; top: 0; height: 100%;
              border: 1px dashed var(--border-strong); border-radius: 2px; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false`
Expected: PASS, all three tests in `versions.spec.ts`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/versions/versions.ts frontend/src/app/workspaces/versions/versions.spec.ts
git commit -m "feat(versions): flip the strip's template to match the store's axis

Ticks render \"now\" first. The absent region (a component that
didn't exist yet) is now positioned by a data-driven left binding
instead of a hardcoded CSS side, so it tracks the flip and Task 4's
spotlight overlay doesn't have to fight a stale rule.

versions.spec.ts moves onto a shared seed() helper (matching the
store spec's own pattern) so the new assertions don't duplicate its
TestBed boilerplate.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Hover tooltip with paired versions + cross-lane spotlight

**Files:**
- Modify: `frontend/src/styles/tokens.css` (one new token)
- Modify: `frontend/src/app/workspaces/versions/versions.ts`
- Test: `frontend/src/app/workspaces/versions/versions.spec.ts`

**Interfaces:**
- Consumes: `LaneSegment.pairedWith` (Task 2), the flipped `start`/`width`
  fractions (Task 1), `VersionsStore` (unchanged).
- Produces: nothing further downstream — this is the last task.

- [ ] **Step 1: Write the failing test**

Add to `versions.spec.ts`'s `describe('Versions', ...)` block:

```ts
  it('shows paired versions on hover, worded "paired with" not "compatible", and spotlights the matching time slice in every lane', async () => {
    const fixture = seed(PAIRED);
    await fixture.whenStable();
    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    // components: ['ui', 'bot'] -- the ui lane renders first, so this is
    // its current segment (ui 1.2.0, closed by release a2).
    const current = host.querySelector('.segment.current') as HTMLButtonElement;
    current.dispatchEvent(new Event('pointerenter'));
    fixture.detectChanges();

    const tooltip = host.querySelector('.tooltip');
    expect(tooltip?.textContent).toContain('ui 1.2.0');
    expect(tooltip?.textContent).toContain('paired with: bot 1.1.2');
    expect(tooltip?.textContent).not.toContain('compatible');

    // The spotlight must line up exactly with the hovered segment's own
    // geometry -- same fractions, not a hand-rederived copy.
    const spotlight = host.querySelector('.spotlight') as HTMLElement;
    expect(spotlight).toBeTruthy();
    expect(spotlight.style.left).toBe(current.style.left);
    expect(spotlight.style.width).toBe(current.style.width);

    current.dispatchEvent(new Event('pointerleave'));
    fixture.detectChanges();
    expect(host.querySelector('.tooltip')).toBeNull();
    expect(host.querySelector('.spotlight')).toBeNull();
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx ng test --watch=false`
Expected: FAIL — there is no `(pointerenter)` handler on `.segment`, no
`.tooltip`, and no `.spotlight` element yet.

- [ ] **Step 3: Add the `--overlay-dim` token**

`frontend/src/styles/tokens.css` has no scrim/dim token today (it's
dark-only — no `prefers-color-scheme` split to worry about). Add it next to
the other `--surface-*` tokens:

```css
  --surface-overlay: #1e2230;
  --overlay-dim: rgba(10, 11, 16, .72);
```

(`rgba(10, 11, 16, ...)` is `--bg`'s own `#0a0b10`, at 72% opacity.)

- [ ] **Step 4: Add the hover signal and paired-entries helper**

In `versions.ts`, add `signal` to the existing `@angular/core` import:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
```

Import `LaneSegment` alongside `VersionsStore`:

```ts
import { LaneSegment, VersionsStore } from '../../stores/versions.store';
```

Inside the `Versions` class, add:

```ts
  protected readonly hovered = signal<{ lane: string; segment: LaneSegment } | null>(null);

  /** `Object.entries` for the template's `@for` -- keeps the tooltip's
   *  paired-version rows from needing a pipe or a second computed just to
   *  iterate a plain object. */
  protected pairedEntries(segment: LaneSegment): [string, string][] {
    return Object.entries(segment.pairedWith);
  }
```

- [ ] **Step 5: Wire the hover handlers and render the tooltip/spotlight**

Replace the segment button's native title with pointer handlers — change:

```html
                <button type="button" class="segment" [class.current]="segment.current"
                        [style.left.%]="segment.start * 100"
                        [style.width.%]="segment.width * 100"
                        [style.background]="segment.current ? null : versionTint(segment.version)"
                        (click)="store.toggleFilter(lane.component, segment.version)"
                        [attr.title]="lane.component + ' ' + segment.version
                          + ' · ' + segment.firstSeen + ' → ' + segment.lastSeen"></button>
```

to:

```html
                <button type="button" class="segment" [class.current]="segment.current"
                        [style.left.%]="segment.start * 100"
                        [style.width.%]="segment.width * 100"
                        [style.background]="segment.current ? null : versionTint(segment.version)"
                        (click)="store.toggleFilter(lane.component, segment.version)"
                        (pointerenter)="hovered.set({ lane: lane.component, segment })"
                        (pointerleave)="hovered.set(null)"></button>
```

Add the spotlight overlay as the last child of `.strip`, right after the
`.bracket-row` div:

```html
        <div class="bracket-row">
          <div class="bracket" [style.left.%]="store.bracket().start * 100"
               [style.width.%]="store.bracket().width * 100"
               title="The releases listed below"></div>
        </div>
        @if (hovered(); as h) {
          <div class="overlay-row">
            <div class="spotlight" [style.left.%]="h.segment.start * 100"
                 [style.width.%]="h.segment.width * 100"></div>
          </div>
        }
      </div>
```

(the closing `</div>` above is `.strip`'s own — the new block goes inside
it, as a sibling of the lanes and the bracket row).

Add the tooltip as a sibling right after `.strip` closes, before `.legend`:

```html
      @if (hovered(); as h) {
        <div class="tooltip">
          <strong>{{ h.lane }} {{ h.segment.version }}</strong>
          @for (pair of pairedEntries(h.segment); track pair[0]) {
            <div>paired with: {{ pair[0] }} {{ pair[1] }}</div>
          }
          <div class="when">{{ h.segment.firstSeen }} → {{ h.segment.current ? 'now' : h.segment.lastSeen }}</div>
        </div>
      }

      <div class="legend">
```

- [ ] **Step 6: Style the overlay, spotlight and tooltip**

`.strip` needs `position: relative` (to anchor the overlay) and
`overflow: hidden` (so the spotlight's box-shadow bleed is clipped to the
strip's own bounds, not the whole page) — change:

```css
    .strip { display: flex; flex-direction: column; gap: var(--space-6); }
```

to:

```css
    .strip { display: flex; flex-direction: column; gap: var(--space-6);
              position: relative; overflow: hidden; }
```

Add, near the `.bracket-row`/`.bracket` rules:

```css
    /* Track-aligned, same left offset as .bracket-row -- an absolutely
       positioned block with only left/right set (no width) auto-sizes to
       exactly the track's own width, the same trick .bracket-row already
       relies on for its own left/width percentages. */
    .overlay-row { position: absolute; top: 0; bottom: 0;
                    left: calc(4.5rem + var(--space-8)); right: 0;
                    pointer-events: none; }
    /* The 9999px spread dims everything outside this element's own left/width
       in one paint -- clipped to .strip's bounds by its overflow: hidden,
       so it never bleeds into the basis line above or the legend below. */
    .spotlight { position: absolute; top: 0; bottom: 0;
                  box-shadow: 0 0 0 9999px var(--overlay-dim);
                  pointer-events: none; }
```

Add, near the `.legend` rules:

```css
    /* Same custom-tooltip convention as line-chart.ts's pointer tooltip:
       position: absolute with no explicit left/top, so it renders at its
       static in-flow position (right after .strip, above .legend) rather
       than tracking the cursor -- deliberately, since it must not be
       clipped by .strip's own overflow: hidden. */
    .tooltip { position: absolute; padding: var(--space-6) var(--space-8);
                background: var(--surface-overlay); border: 1px solid var(--border-strong);
                border-radius: var(--radius); font-size: var(--text-micro); color: var(--text);
                display: flex; flex-direction: column; gap: var(--space-2);
                pointer-events: none; }
    .tooltip .when { color: var(--text-faint); }
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd frontend && npx ng test --watch=false`
Expected: PASS, all tests in `versions.spec.ts` and `versions.store.spec.ts`.

- [ ] **Step 8: Full frontend suite**

Run: `cd frontend && npx ng test --watch=false`
Expected: `0 failed` across the whole frontend suite (not just the two
Versions spec files) — this task touched a shared token file
(`tokens.css`), so confirm nothing else regressed.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/app/workspaces/versions/versions.ts frontend/src/app/workspaces/versions/versions.spec.ts
git commit -m "feat(versions): hover a bar to see its paired-component versions

Custom tooltip (line-chart.ts's existing pointer-tooltip pattern,
not the native title attribute) shows every other component's
version as of the hovered segment's close, worded \"paired with\" --
never \"compatible\" -- per the page's own no-support-matrix doc
comment. A box-shadow spotlight overlay dims every lane outside the
hovered segment's time window in one paint, clipped to the strip's
own bounds.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Progress

- [x] Task 1: Flip the strip's time axis in the store
- [x] Task 2: Capture paired versions on every segment
- [x] Task 3: Flip the template to match — ticks and the absent region
- [x] Task 4: Hover tooltip with paired versions + cross-lane spotlight
