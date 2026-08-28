# v65 — Table Pagination Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-08-28-v65-table-pagination-overhaul-design.md`

**Version:** ui 1.9.2 · bot 1.4.5
**Bump:** ui minor (1.9.2 → 1.10.0) · bot none
**Edge:** none (integrity)

**Goal:** Give every row-list table in the admin SPA a pager at the top and the
bottom, a constant page height, and a `Held` column that is correct to the
minute rather than to the hour at whatever moment the server last answered.

**Architecture:** All the shared behaviour lands in three files that every
table already goes through — `ui/pagination.ts`, `ui/data-table/data-table.ts`
and `ui/data-table/client-page.ts` — so the workspace tasks are wiring, not
reimplementation. The live `Held` value comes from a new injectable `CLOCK`
signal read *inside* a column's `value()` at template-evaluation time, which is
what makes the affected cells re-render without rebuilding column arrays.

**Tech Stack:** Angular 21 (standalone, signals, zoneless, `OnPush`), Vitest +
`@angular/core/testing` TestBed, TypeScript strict.

## Global Constraints

- **Frontend only.** No file under `swingbot/`, `tests/` or `scripts/` is
  touched by any task in this plan. No Python suite is run.
- **`DataTable` never reorders or slices `rows`.** Client-paged call sites
  slice *before* handing rows in. `PageSpec.total` is always the pre-slice
  count, never `rows.length`.
- **A missing value renders as `ABSENT` (`—`), never `0` and never blank.**
  `ui/format.ts`'s standing rule; it governs every duration in this plan.
- **Per-task verification is one spec file**:
  `cd frontend && npm test -- --include <path to the one spec file>`.
  A full `npm test` runs **once**, in Task 15. Never per task.
- Filler-row background is `var(--bg)` (`#0a0b10`), the page colour, one step
  darker than the panel's `var(--surface)` (`#10121a`).
- Clock cadence is **30_000 ms**. Tests always override the `CLOCK` token with
  a fixed `signal()` — a real interval must never run under Vitest.

## Parallelisation

- **Group 1 (parallel):** Task 1, Task 6, Task 7 — `ui/clock.ts`,
  `ui/format.ts`, `ui/data-table/client-page.ts`. Three disjoint files, no
  shared contract between them.
- **Sequential:** Task 2 → Task 3 → Task 4 → Task 5. Tasks 3–5 all edit
  `data-table.ts`; Task 3 consumes Task 2's new `PaginationComponent` inputs.
- **Sequential:** Task 8 after Tasks 1 and 6 (consumes `CLOCK` and the new
  `elapsedHours`). Task 9 after Task 2. Task 8 and Task 9 are **not** parallel
  with each other — both are read by `dashboard.ts`, which Task 8 edits.
- **Group 2 (parallel), after Tasks 1–9:** Task 10, 11, 12, 13 — `risk.ts`,
  `watchlist.ts`, `ticker-detail.ts`, `analytics.ts`. One workspace file each,
  no shared file, all four consume only already-landed contracts.
- **Sequential last:** Task 14 (sticky header — highest visual risk, sequenced
  so a problem there blocks nothing), then Task 15 (full-suite verification).

---

# Phase A — Shared primitives

### Task 1: The injectable clock

**Files:**
- Create: `frontend/src/app/ui/clock.ts`
- Test: `frontend/src/app/ui/clock.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `CLOCK: InjectionToken<Signal<number>>` (epoch milliseconds) and
  `CLOCK_INTERVAL_MS = 30_000`. Tasks 8 and 14 inject `CLOCK`; every spec that
  renders a trade table overrides it with `{ provide: CLOCK, useValue: signal(FIXED) }`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/app/ui/clock.spec.ts
import { Injector, runInInjectionContext, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, vi } from 'vitest';

import { CLOCK, CLOCK_INTERVAL_MS } from './clock';

describe('CLOCK', () => {
  it('ticks on the documented interval', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-28T10:00:00Z'));
    TestBed.configureTestingModule({});
    const now = TestBed.inject(CLOCK);
    const first = now();

    vi.advanceTimersByTime(CLOCK_INTERVAL_MS);
    expect(now()).toBeGreaterThan(first);
    vi.useRealTimers();
  });

  it('is overridable, so no real timer runs in a suite under test', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [{ provide: CLOCK, useValue: signal(1_700_000_000_000) }],
    });
    expect(TestBed.inject(CLOCK)()).toBe(1_700_000_000_000);
  });

  it('is 30 seconds, not one', () => {
    expect(CLOCK_INTERVAL_MS).toBe(30_000);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/clock.spec.ts`
Expected: FAIL — `Cannot find module './clock'`.

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/app/ui/clock.ts
import { InjectionToken, Signal, signal } from '@angular/core';

/**
 * How often the ambient clock advances.
 *
 * Thirty seconds, not one. The only consumer is a minute-precision duration
 * (`Held`), so a per-second tick would re-render the table for a value that is
 * identical 29 times out of 30.
 */
export const CLOCK_INTERVAL_MS = 30_000;

/**
 * Wall-clock time, as a signal, for values that must age on screen.
 *
 * A live position's holding period is measured from `opened_at` to *now*, and
 * `now` moves whether or not the server has been asked anything. The server's
 * `held_hours` is computed at response time (`swingbot/admin/api_v1/trades.py`),
 * and this SPA refreshes on bot events rather than on a timer -- so a table
 * left open for twenty minutes would show a duration twenty minutes stale.
 * Rounding to the hour hid that; minute precision would display it.
 *
 * A token rather than a service, mirroring `CHART_PREFS_STORE`: the default is
 * a real interval, and every test replaces it with a fixed `signal()` so no
 * timer runs under Vitest.
 */
export const CLOCK = new InjectionToken<Signal<number>>('CLOCK', {
  providedIn: 'root',
  factory: () => {
    const now = signal(Date.now());
    setInterval(() => now.set(Date.now()), CLOCK_INTERVAL_MS);
    return now.asReadonly();
  },
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/clock.spec.ts`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/clock.ts frontend/src/app/ui/clock.spec.ts
git commit -m "feat(v65): add injectable CLOCK signal for live durations"
```

---

### Task 2: Pager — first/last, jump-to-page, unconditional count, announcements

**Files:**
- Modify: `frontend/src/app/ui/pagination.ts`
- Test: `frontend/src/app/ui/pagination.spec.ts`

**Interfaces:**
- Consumes: `PageSpec` from `data-table.types` (unchanged).
- Produces: `PaginationComponent` gains `announce = input(false)`. Existing
  `pagination`, `showPerPage`, `pageChange`, `perPageChange` are unchanged.
  Task 3 sets `[announce]="true"` on the top instance only.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/app/ui/pagination.spec.ts` (keep the file's existing
host/setup helpers; these use the same `PageSpec` shape):

```ts
  it('shows the row count even on a single page, with no navigation buttons', () => {
    host.pagination.set({ total: 6, page: 1, perPage: 25 });
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('6 rows');
    expect(el.querySelector('button[aria-label="Next page"]')).toBeNull();
  });

  it('shows the range and the buttons once there is more than one page', () => {
    host.pagination.set({ total: 90, page: 2, perPage: 25 });
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('26–50 of 90');
    expect(el.querySelector('button[aria-label="Next page"]')).not.toBeNull();
  });

  it('first and last jump to the ends and are disabled at them', () => {
    host.pagination.set({ total: 90, page: 1, perPage: 25 });
    fixture.detectChanges();
    const first = fixture.nativeElement.querySelector<HTMLButtonElement>(
      'button[aria-label="First page"]',
    )!;
    const last = fixture.nativeElement.querySelector<HTMLButtonElement>(
      'button[aria-label="Last page"]',
    )!;
    expect(first.disabled).toBe(true);
    last.click();
    expect(host.pages).toEqual([4]);
  });

  it('jump-to-page clamps an out-of-range entry instead of emitting it', () => {
    host.pagination.set({ total: 90, page: 1, perPage: 25 });
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector<HTMLInputElement>('input.jump')!;
    input.value = '99';
    input.dispatchEvent(new Event('change'));
    expect(host.pages).toEqual([4]);

    input.value = '0';
    input.dispatchEvent(new Event('change'));
    expect(host.pages).toEqual([4, 1]);
  });

  it('announces the page only when asked to', () => {
    host.pagination.set({ total: 214, page: 3, perPage: 25 });
    host.announce.set(false);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[aria-live]')).toBeNull();

    host.announce.set(true);
    fixture.detectChanges();
    const live = fixture.nativeElement.querySelector('[aria-live="polite"]')!;
    expect(live.textContent).toContain('Page 3 of 9, showing 51–75 of 214');
  });
```

Add to the spec's host component: `readonly announce = signal(false);` and
`[announce]="announce()"` on the `<sb-pagination>` element.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/pagination.spec.ts`
Expected: FAIL — `announce` is not a known property, and `6 rows` is absent.

- [ ] **Step 3: Write minimal implementation**

Replace the `@if (pageCount() > 1) { ... }` block in `pagination.ts` with the
following, and add the members below to the class:

```html
    <!-- The range is OUTSIDE the pageCount() guard now. A one-page table
         previously rendered no pager at all, which also hid the total -- so
         "how many rows are here" could only be answered by counting them. -->
    <div class="pager">
      <span class="range num">{{ rangeLabel() }}</span>
      @if (pageCount() > 1) {
        <button type="button" aria-label="First page"
                [disabled]="pagination().page <= 1" (click)="jump(1)">⏮</button>
        <button type="button" aria-label="Previous page"
                [disabled]="pagination().page <= 1" (click)="goTo(-1)">Previous</button>
        <label class="of">
          <span class="sr-only">Page</span>
          <input class="jump num" type="number" inputmode="numeric" min="1"
                 [max]="pageCount()" [value]="pagination().page"
                 (change)="onJump($any($event.target).value)" />
          <span aria-hidden="true">/ {{ pageCount() }}</span>
        </label>
        <button type="button" aria-label="Next page"
                [disabled]="pagination().page >= pageCount()" (click)="goTo(1)">Next</button>
        <button type="button" aria-label="Last page"
                [disabled]="pagination().page >= pageCount()"
                (click)="jump(pageCount())">⏭</button>
      }
    </div>
    @if (announce()) {
      <!-- One region per TABLE, not per pager: DataTable sets this on the top
           instance only, because two live regions saying the same sentence
           announce every page change twice. -->
      <span class="sr-only" role="status" aria-live="polite">{{ announcement() }}</span>
    }
```

```ts
  /** Whether this instance owns the table's live region. See the template. */
  readonly announce = input(false);

  /** "26–50 of 90" on a paged table, "6 rows" when it all fits.
   *
   *  The single-page wording deliberately drops the range: "1–6 of 6" is three
   *  numbers to say what one number says, and the range only earns its keep
   *  when there is something off-screen it is distinguishing from. */
  protected readonly rangeLabel = computed(() => {
    const { total, page, perPage } = this.pagination();
    if (this.pageCount() <= 1) return `${total} ${total === 1 ? 'row' : 'rows'}`;
    const first = (page - 1) * perPage + 1;
    const last = Math.min(page * perPage, total);
    return `${first}–${last} of ${total}`;
  });

  protected readonly announcement = computed(
    () => `Page ${this.pagination().page} of ${this.pageCount()}, showing ${this.rangeLabel()}`,
  );

  /** Absolute navigation, clamped. `goTo` is the relative form and keeps its
   *  own guard; both refuse a target outside 1..pageCount rather than
   *  emitting a page the caller would have to reject. */
  protected jump(target: number): void {
    const clamped = Math.min(Math.max(1, Math.trunc(target) || 1), this.pageCount());
    if (clamped === this.pagination().page) return;
    this.pageChange.emit(clamped);
  }

  protected onJump(value: string): void {
    this.jump(Number(value));
  }
```

Add these styles to the component's `styles` block:

```css
    .jump {
      width: 3.5rem;
      padding: 2px var(--space-4);
      background: var(--surface-raised);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      font: inherit;
      text-align: right;
    }
    .of { display: inline-flex; align-items: center; gap: var(--space-4); }
    .sr-only {
      position: absolute;
      width: 1px; height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }
```

Delete the now-superseded `rangeLabel` further down the class.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/pagination.spec.ts`
Expected: PASS. Existing tests in the file must stay green — if one asserted
"renders nothing when there is one page", update it to assert "renders the
count and no buttons", which is this task's deliberate behaviour change.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/pagination.ts frontend/src/app/ui/pagination.spec.ts
git commit -m "feat(v65): first/last/jump paging, always-visible count, page announcements"
```

---

### Task 3: The top pager

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.ts`
- Test: `frontend/src/app/ui/data-table/data-table.spec.ts`

**Interfaces:**
- Consumes: `PaginationComponent`'s `announce` input (Task 2).
- Produces: no new public API. `DataTable` renders two `<sb-pagination>`
  instances; every existing call site is unchanged.

- [ ] **Step 1: Write the failing test**

Append to `data-table.spec.ts`:

```ts
  it('renders a pager above and below the table, with identical controls', () => {
    host.pagination.set({ total: 90, page: 2, perPage: 25 });
    fixture.detectChanges();
    const pagers = fixture.nativeElement.querySelectorAll('sb-pagination');
    expect(pagers.length).toBe(2);
    for (const pager of pagers) {
      expect(pager.querySelector('button[aria-label="Next page"]')).not.toBeNull();
    }
  });

  it('gives the table exactly one live region, on the top pager', () => {
    host.pagination.set({ total: 90, page: 2, perPage: 25 });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('[aria-live]').length).toBe(1);
  });

  it('emits pageChange from either pager', () => {
    host.pagination.set({ total: 90, page: 2, perPage: 25 });
    fixture.detectChanges();
    const nexts = fixture.nativeElement.querySelectorAll<HTMLButtonElement>(
      'button[aria-label="Next page"]',
    );
    nexts[0].click();
    nexts[1].click();
    expect(host.pages).toEqual([3, 3]);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: FAIL — one `sb-pagination`, not two.

- [ ] **Step 3: Write minimal implementation**

In `data-table.ts`, extract the pager into a template so the two instances
cannot drift, and render it above `.scroller` as well as at the bottom. Insert
immediately after the opening `<div class="wrap" ...>` / spinner block:

```html
      <!-- Top and bottom, from one ng-template, so the two can never drift.
           A table taller than the viewport otherwise makes "next page" a
           scroll-to-the-bottom errand, and after it lands you are at the
           bottom of a page you have not read yet.
           `announce` is true only here: see PaginationComponent's template
           for why one live region per table rather than two. -->
      @if (pagination(); as page) {
        <ng-container
          [ngTemplateOutlet]="pagerTemplate"
          [ngTemplateOutletContext]="{ $implicit: page, announce: true }"
        />
      }
```

and replace the existing bottom `@if (pagination(); as page) { <sb-pagination .../> }`
block with:

```html
      @if (pagination(); as page) {
        <ng-container
          [ngTemplateOutlet]="pagerTemplate"
          [ngTemplateOutletContext]="{ $implicit: page, announce: false }"
        />
      }
    </div>

    <ng-template #pagerTemplate let-page let-announce="announce">
      <sb-pagination
        [pagination]="page"
        [showPerPage]="showPerPage()"
        [announce]="announce"
        (pageChange)="pageChange.emit($event)"
        (perPageChange)="perPageChange.emit($event)"
      />
    </ng-template>
```

(The `</div>` above closes `.wrap`; the template sits outside it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/data-table/data-table.spec.ts
git commit -m "feat(v65): render a pager above the table as well as below"
```

---

### Task 4: Filler rows

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.ts`
- Test: `frontend/src/app/ui/data-table/data-table.spec.ts`

**Interfaces:**
- Consumes: `pagination()`, `cards()`, `renderedColumns()`, `colspan()` —
  all existing members of `DataTable`.
- Produces: `protected readonly fillerRows: Signal<number[]>`. No public API.

- [ ] **Step 1: Write the failing test**

```ts
  it('pads a short page up to perPage so page heights do not jump', () => {
    host.pagination.set({ total: 13, page: 2, perPage: 10 });
    fixture.detectChanges();
    // ROWS is 3 long; the page holds 10.
    expect(fixture.nativeElement.querySelectorAll('tr.filler').length).toBe(7);
  });

  it('hides filler rows from assistive tech, so only real rows are counted', () => {
    host.pagination.set({ total: 13, page: 2, perPage: 10 });
    fixture.detectChanges();
    const filler = fixture.nativeElement.querySelector('tr.filler')!;
    expect(filler.getAttribute('aria-hidden')).toBe('true');
    expect(filler.textContent!.trim()).toBe('');
  });

  it('adds no filler when the page is full', () => {
    host.pagination.set({ total: 9, page: 1, perPage: 3 });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('tr.filler').length).toBe(0);
  });

  it('adds no filler when per-page is All -- there is no page height to fill', () => {
    host.pagination.set({ total: 3, page: 1, perPage: 0 });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('tr.filler').length).toBe(0);
  });

  it('adds no filler in card mode -- a blank card is a broken card', () => {
    host.cardsAt.set(true);
    host.pagination.set({ total: 13, page: 2, perPage: 10 });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.filler').length).toBe(0);
  });

  it('adds no filler when the table is unpaginated', () => {
    host.pagination.set(null);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('tr.filler').length).toBe(0);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: FAIL — no `tr.filler` exists.

- [ ] **Step 3: Write minimal implementation**

Add inside `<tbody>`, immediately after the closing `}` of the row `@for`:

```html
          <!-- Blank spacing, not data. Painted in the PAGE background rather
               than the panel's, so the remainder of a short page reads as void
               beneath the table instead of as rows that failed to load -- and
               aria-hidden so a screen reader counts three rows, not ten. -->
          @for (slot of fillerRows(); track slot) {
            <tr class="filler" aria-hidden="true">
              <td [attr.colspan]="colspan()"></td>
            </tr>
          }
```

Add the computed to the class, next to `colspan`:

```ts
  /**
   * How many blank rows to pad a short page with.
   *
   * Zero in four cases, each for its own reason: an unpaginated table has no
   * page height to fill; `perPage: 0` is `ALL_PER_PAGE`, which means "no
   * paging" and so likewise has no target; a full page needs nothing; and card
   * mode renders a stack rather than a grid, where a blank card is not spacing,
   * it is a broken card.
   *
   * An array of indices rather than a count, because `@for` needs something to
   * iterate and a `track` key that is stable across renders.
   */
  protected readonly fillerRows = computed<number[]>(() => {
    const page = this.pagination();
    if (!page || page.perPage <= 0 || this.cards()) return [];
    const missing = page.perPage - this.rows().length;
    return missing > 0 ? Array.from({ length: missing }, (_, i) => i) : [];
  });
```

Add the style, next to the `.row:hover` rule:

```css
    /* --bg, not --surface: the page colour is a step darker than the panel,
       so the unfilled remainder reads as space rather than as empty rows.
       No border, or the filler would draw a ladder of rules under the data. */
    tr.filler > td {
      background: var(--bg);
      border-bottom: 0;
      /* Matches a populated row's height exactly -- padding alone does not,
         because a real cell has a line box and an empty one does not. */
      height: calc(1lh + 2 * var(--space-6));
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: PASS, all six new tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/data-table/data-table.spec.ts
git commit -m "feat(v65): pad short pages with page-background filler rows"
```

---

### Task 5: Column footers

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.types.ts`
- Modify: `frontend/src/app/ui/data-table/data-table.ts`
- Test: `frontend/src/app/ui/data-table/data-table.spec.ts`

**Interfaces:**
- Consumes: `ColumnDef<T>`, `renderedColumns()`, `expansion()`.
- Produces: `ColumnDef<T>.footer?: (rows: T[]) => string | number | null`.
  Task 10 (`risk.ts`) is the only consumer.

- [ ] **Step 1: Write the failing test**

```ts
  it('renders a footer only for columns that declare one', () => {
    host.columns.set([
      { key: 'ticker', header: 'Ticker', value: (r: Row) => r.ticker },
      {
        key: 'pnl',
        header: 'P&L',
        numeric: true,
        value: (r: Row) => r.pnl,
        footer: (rows: Row[]) => rows.reduce((sum, r) => sum + (r.pnl ?? 0), 0).toFixed(2),
      },
    ]);
    fixture.detectChanges();
    const cells = fixture.nativeElement.querySelectorAll('tfoot td');
    expect(cells.length).toBe(2);
    expect(cells[0].textContent!.trim()).toBe('');
    expect(cells[1].textContent!.trim()).toBe('2.70');
  });

  it('renders no tfoot when no column declares a footer', () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('tfoot')).toBeNull();
  });

  it('renders no tfoot over an empty table -- a total of zero is a claim', () => {
    host.columns.set([
      { key: 'pnl', header: 'P&L', value: (r: Row) => r.pnl, footer: () => '0.00' },
    ]);
    host.rows.set([]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('tfoot')).toBeNull();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: FAIL — `footer` is not a property of `ColumnDef`, no `tfoot` exists.

- [ ] **Step 3: Write minimal implementation**

In `data-table.types.ts`, add to `ColumnDef<T>`:

```ts
  /**
   * A summary cell for this column, computed over **all** the rows the table
   * was handed.
   *
   * Only safe on a client-paged table, where `rows` is the complete set. On a
   * server-paged one it would sum the visible page and present that as a
   * total -- the same defect as a pager counting the rows it can see, which is
   * exactly what `PageSpec.total` exists to prevent. Trades therefore declares
   * no footer; an honest total there needs a server-side aggregate.
   */
  footer?: (rows: T[]) => string | number | null;
```

In `data-table.ts`, add after the closing `</tbody>`:

```html
        @if (hasFooter()) {
          <tfoot>
            <tr>
              @if (expansion()) { <td class="expander-cell"></td> }
              @for (col of renderedColumns(); track col.key) {
                <td [class.num]="col.numeric">{{ footerText(col) }}</td>
              }
            </tr>
          </tfoot>
        }
```

and to the class:

```ts
  /** No footer over no rows: a total of zero across an empty table is a claim,
   *  not a measurement, and the empty state is already saying the true thing. */
  protected readonly hasFooter = computed(
    () => this.rows().length > 0 && this.renderedColumns().some((c) => c.footer),
  );

  /** Blank, not an em dash, for a column with no footer. The dash means "this
   *  value is missing"; a column that was never going to have a total is not
   *  missing one. */
  protected footerText(column: ColumnDef<T>): string {
    const value = column.footer?.(this.rows());
    return value === null || value === undefined ? '' : String(value);
  }
```

Add the style:

```css
    tfoot td {
      border-top: 1px solid var(--border-strong);
      border-bottom: 0;
      font-weight: 600;
      color: var(--text);
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/data-table/
git commit -m "feat(v65): optional per-column footer totals on DataTable"
```

---

# Phase B — Formatting and client paging

### Task 6: `held` absorbs `heldPrecise`; add `elapsedHours`

**Files:**
- Modify: `frontend/src/app/ui/format.ts:60-86`
- Test: `frontend/src/app/ui/format.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `held(hours: number | null | undefined): string` at day/hour/minute
  precision, and `elapsedHours(iso: string | null | undefined, nowMs: number): number | null`.
  **`heldPrecise` is deleted.** Tasks 8 and 14 consume both.

- [ ] **Step 1: Write the failing test**

Replace the existing `held`/`heldPrecise` describe blocks in `format.spec.ts`
with:

```ts
describe('held', () => {
  it('carries minutes, which is the whole point of v65', () => {
    expect(held(1.5)).toBe('1h 30m');
    expect(held(73.4)).toBe('3d 1h 24m');
  });

  it('omits units that are zero, so "2 days exactly" is not "2d 0h 0m"', () => {
    expect(held(48)).toBe('2d');
    expect(held(2)).toBe('2h');
  });

  it('renders a sub-minute hold as 0m, not as blank', () => {
    expect(held(0)).toBe('0m');
  });

  it('renders a missing duration as an em dash, never as zero', () => {
    expect(held(null)).toBe(ABSENT);
    expect(held(undefined)).toBe(ABSENT);
  });
});

describe('elapsedHours', () => {
  const NOW = Date.parse('2026-08-28T12:00:00Z');

  it('measures from an ISO instant to the supplied now', () => {
    expect(elapsedHours('2026-08-28T09:30:00Z', NOW)).toBeCloseTo(2.5, 6);
  });

  it('never goes negative for a clock that is behind the server', () => {
    expect(elapsedHours('2026-08-28T13:00:00Z', NOW)).toBe(0);
  });

  it('returns null for a missing or unparseable instant, so held() dashes it', () => {
    expect(elapsedHours(null, NOW)).toBeNull();
    expect(elapsedHours('not a date', NOW)).toBeNull();
    expect(held(elapsedHours(null, NOW))).toBe(ABSENT);
  });
});
```

Update the file's import to drop `heldPrecise` and add `elapsedHours`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/format.spec.ts`
Expected: FAIL — `elapsedHours` is not exported; `held(1.5)` returns `'2h'`.

- [ ] **Step 3: Write minimal implementation**

Replace `format.ts:60-86` (both `held` and `heldPrecise`) with:

```ts
/**
 * Holding period at day/hour/minute precision — "3d 1h 24m".
 *
 * This absorbed `heldPrecise`, which existed only because the old `held`
 * rounded a LIVE position to the nearest hour: minute-level jitter was called
 * noise on a number that changes every render. v65 removes the premise. The
 * live value is now computed in the browser from `opened_at` (see
 * `elapsedHours` and `ui/clock.ts`), so the minutes are real rather than a
 * false-precision rendering of whatever the server last said. With that true,
 * one duration format serves both a live position and a closed one, and the
 * duplicate `Hold` column that existed to show the precise form is gone.
 *
 * Zero units are omitted, so "exactly two days" is "2d" and not "2d 0h 0m".
 */
export function held(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return ABSENT;
  const totalMinutes = Math.round(hours * 60);
  const days = Math.floor(totalMinutes / 1440);
  const hrs = Math.floor((totalMinutes % 1440) / 60);
  const mins = totalMinutes % 60;
  const parts: string[] = [];
  if (days) parts.push(`${days}d`);
  if (hrs) parts.push(`${hrs}h`);
  if (mins || parts.length === 0) parts.push(`${mins}m`);
  return parts.join(' ');
}

/**
 * Hours between an ISO instant and `nowMs`, or null if there is no instant.
 *
 * `null` rather than 0 for a missing or unparseable date: a PENDING plan has
 * no `opened_at`, and "held for zero minutes" is a different claim from "has
 * not been opened". Feeding the null straight to `held` renders the em dash
 * this module's header rule requires.
 *
 * Clamped at zero. A browser clock a few seconds behind the server would
 * otherwise render a position opened "just now" as a negative duration.
 */
export function elapsedHours(
  iso: string | null | undefined,
  nowMs: number,
): number | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, (nowMs - then) / 3_600_000);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/format.spec.ts`
Expected: PASS. TypeScript will now flag the two `heldPrecise` importers
(`trades.columns.ts`) — that is Task 8's job and is expected to be red until
then.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/format.ts frontend/src/app/ui/format.spec.ts
git commit -m "feat(v65): held() gains minute precision and absorbs heldPrecise"
```

---

### Task 7: `createClientPage` takes a reactive page size

**Files:**
- Modify: `frontend/src/app/ui/data-table/client-page.ts`
- Test: `frontend/src/app/ui/data-table/client-page.spec.ts` (create if absent)

**Interfaces:**
- Consumes: `PageSpec`, and `ALL_PER_PAGE` from `../table-prefs`.
- Produces: `createClientPage<T>(rows: () => readonly T[], perPage?: number | (() => number)): ClientPage<T>`.
  The numeric form is still accepted, so the eight existing Analytics call
  sites compile unchanged. Tasks 10–13 pass the function form.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/app/ui/data-table/client-page.spec.ts
import { signal } from '@angular/core';
import { describe, expect, it } from 'vitest';

import { createClientPage } from './client-page';

const ROWS = Array.from({ length: 42 }, (_, i) => i);

describe('createClientPage', () => {
  it('still accepts a fixed page size, so existing call sites compile', () => {
    const page = createClientPage(() => ROWS, 10);
    expect(page.visible().length).toBe(10);
    expect(page.pageSpec()).toEqual({ total: 42, page: 1, perPage: 10 });
  });

  it('tracks a reactive page size', () => {
    const perPage = signal(10);
    const page = createClientPage(() => ROWS, () => perPage());
    expect(page.visible().length).toBe(10);
    perPage.set(25);
    expect(page.visible().length).toBe(25);
    expect(page.pageSpec().perPage).toBe(25);
  });

  it('clamps onto a page that exists when the size shrinks', () => {
    const perPage = signal(10);
    const page = createClientPage(() => ROWS, () => perPage());
    page.setPage(5);
    expect(page.page()).toBe(5);
    perPage.set(25);
    // 42 rows at 25 per page is 2 pages; page 5 no longer exists.
    expect(page.page()).toBe(2);
    expect(page.visible()).toEqual(ROWS.slice(25));
  });

  it('treats ALL_PER_PAGE (0) as one page of everything, not a divide by zero', () => {
    const page = createClientPage(() => ROWS, () => 0);
    expect(page.visible().length).toBe(42);
    expect(page.pageSpec()).toEqual({ total: 42, page: 1, perPage: 0 });
  });

  it('stays correct when the underlying array identity changes', () => {
    const rows = signal<number[]>([1, 2, 3]);
    const page = createClientPage(() => rows(), () => 2);
    expect(page.visible()).toEqual([1, 2]);
    rows.set([9]);
    expect(page.visible()).toEqual([9]);
    expect(page.pageSpec().total).toBe(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/client-page.spec.ts`
Expected: FAIL — the function form is not accepted; `perPage: 0` divides by zero.

- [ ] **Step 3: Write minimal implementation**

Replace the body of `createClientPage` in `client-page.ts`:

```ts
export function createClientPage<T>(
  rows: () => readonly T[],
  perPage: number | (() => number) = 25,
): ClientPage<T> {
  // Both forms accepted: the eight Analytics call sites pass a literal and
  // have no size control, while a table with a rows-per-page selector passes
  // the signal getter so the slice tracks it.
  const size = typeof perPage === 'function' ? perPage : () => perPage;
  const requestedPage = signal(1);

  // ALL_PER_PAGE is 0, and 0 means "no paging" rather than a page of no rows.
  // Resolving it to the row count here is what keeps every consumer below --
  // totalPages, the slice, the pageSpec -- free of a special case, and what
  // stops the ceil() from dividing by zero.
  const effective = computed(() => (size() > 0 ? size() : Math.max(1, rows().length)));

  const totalPages = computed(() => Math.max(1, Math.ceil(rows().length / effective())));

  // Clamp on read rather than in a separate effect: a `setPage` call can
  // race a rows() shrink OR a perPage growth from either direction, and
  // clamping wherever the value is actually consumed is the one place that
  // cannot be out of date. Exposed AS `page` (rather than the raw requested
  // value) so a caller reading `page()` right after either sees the same
  // clamped number the table is showing.
  const page = computed(() => Math.min(requestedPage(), totalPages()));

  const visible = computed(() => {
    const start = (page() - 1) * effective();
    return rows().slice(start, start + effective());
  });

  // perPage reports the RAW size, not the resolved one: the pager's "All"
  // option is selected by matching against ALL_PER_PAGE, and reporting the row
  // count here would leave the selector showing a number nobody chose.
  const pageSpec = computed<PageSpec>(() => ({
    total: rows().length,
    page: page(),
    perPage: size(),
  }));

  return {
    page,
    visible,
    pageSpec,
    setPage: (n: number) => requestedPage.set(Math.max(1, n)),
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/client-page.spec.ts`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/data-table/client-page.ts frontend/src/app/ui/data-table/client-page.spec.ts
git commit -m "feat(v65): createClientPage accepts a reactive page size"
```

---

# Phase C — Trades columns and the Dashboard

### Task 8: Live `Held`, and the `Hold` column deleted

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.columns.ts:1-3,95,104`
- Modify: `frontend/src/app/workspaces/trades/trades.ts:666`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts:993`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.helpers.ts` (drop
  `'hold'` from the closed-group column list)
- Test: `frontend/src/app/workspaces/trades/trades.columns.spec.ts`

One task, not three: changing `tradeColumns()`'s signature breaks both call
sites at compile time, so they must land together or the build is red between
tasks.

**Interfaces:**
- Consumes: `CLOCK` (Task 1), `held` and `elapsedHours` (Task 6).
- Produces: `tradeColumns(now: Signal<number>): ColumnDef<TradeRow>[]`.
  The `'hold'` key no longer exists in the returned array.

- [ ] **Step 1: Write the failing test**

```ts
  it('takes the clock and reads it inside the cell, not at build time', () => {
    const now = signal(Date.parse('2026-08-28T12:00:00Z'));
    const columns = tradeColumns(now);
    const held = columns.find((c) => c.key === 'held')!;
    const open = { ...ROW, opened_at: '2026-08-28T09:30:00Z', closed_at: null,
                   held_hours: 0.1 } as TradeRow;

    expect(held.value!(open)).toBe('2h 30m');
    now.set(Date.parse('2026-08-28T12:45:00Z'));
    // Same column object -- the value tracks the clock, so the array does not
    // have to be rebuilt on every tick.
    expect(held.value!(open)).toBe('3h 15m');
  });

  it('uses the server duration for a CLOSED row, which does not tick', () => {
    const now = signal(Date.parse('2026-08-28T12:00:00Z'));
    const held = tradeColumns(now).find((c) => c.key === 'held')!;
    const closed = { ...ROW, opened_at: '2026-08-01T09:00:00Z',
                     closed_at: '2026-08-02T10:30:00Z', held_hours: 25.5 } as TradeRow;

    expect(held.value!(closed)).toBe('1d 1h 30m');
    now.set(Date.parse('2026-09-01T12:00:00Z'));
    expect(held.value!(closed)).toBe('1d 1h 30m');
  });

  it('dashes a PENDING row, which has no opened_at at all', () => {
    const now = signal(Date.parse('2026-08-28T12:00:00Z'));
    const held = tradeColumns(now).find((c) => c.key === 'held')!;
    const pending = { ...ROW, opened_at: null, closed_at: null,
                      held_hours: null } as TradeRow;
    expect(held.value!(pending)).toBe('—');
  });

  it('no longer has a separate hold column -- held subsumes it', () => {
    const now = signal(Date.parse('2026-08-28T12:00:00Z'));
    expect(tradeColumns(now).find((c) => c.key === 'hold')).toBeUndefined();
  });
```

Update every other `tradeColumns()` call in this spec file to
`tradeColumns(signal(0))`. Add a `ROW` fixture at the top of the file if the
spec does not already have one:

```ts
const ROW = { id: 'x', ticker: 'AAPL' } as unknown as TradeRow;
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/trades/trades.columns.spec.ts`
Expected: FAIL — `tradeColumns` expects 0 arguments; `heldPrecise` no longer
exists (a compile error left over from Task 6).

- [ ] **Step 3: Write minimal implementation**

In `trades.columns.ts`, change the import line and signature:

```ts
import { Signal } from '@angular/core';

import { TradeRow } from '../../api/models';
import { ColumnDef } from '../../ui/data-table/data-table.types';
import { age, elapsedHours, held, num, signed, text } from '../../ui/format';
```

```ts
/**
 * @param now Epoch milliseconds, from `CLOCK`. Taken as a Signal and READ
 *   INSIDE `value()` rather than as a number, deliberately: reading it during
 *   template evaluation re-renders the two cells that changed, whereas taking
 *   `now()` and rebuilding this array each tick would invalidate the caller's
 *   `computed`, re-run the column picker's mapping, and re-render every table
 *   on the Dashboard every thirty seconds.
 */
export function tradeColumns(now: Signal<number>): ColumnDef<TradeRow>[] {
```

Replace the `held` column (line 95) with:

```ts
    /* v65: minute precision, and live for an open position.
     *
     * A CLOSED row uses the server's `held_hours`, which is fixed and correct.
     * An OPEN one is measured in the browser from `opened_at`, because
     * `_held_hours` computes to `datetime.now()` at RESPONSE time and this SPA
     * refreshes on bot events rather than on a timer -- so the server's value
     * for a live position is only as fresh as the last fetch. Rounding to the
     * hour hid that; minutes would have displayed it as a wrong number. */
    {
      key: 'held',
      header: 'Held',
      value: (row) =>
        held(row.closed_at ? row.held_hours : elapsedHours(row.opened_at, now())),
      numeric: true,
      sortable: true,
    },
```

Delete the `'hold'` column definition and its comment block (lines 98–104).

In `trades.ts:666` and `dashboard.ts:993`, add `private readonly now = inject(CLOCK);`
to each class (importing `CLOCK` from `../../ui/clock`) and change both calls to
`tradeColumns(this.now)`.

In `dashboard.helpers.ts`, remove `'hold'` from the closed-group column list
and update the comment that names it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/trades/trades.columns.spec.ts`
Then: `cd frontend && npm test -- --include src/app/workspaces/dashboard/dashboard.helpers.spec.ts`
Expected: PASS both. `dashboard.helpers.spec.ts:82` asserts on the closed
group's order and may name `'hold'` — update that expectation, do not restore
the column.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/trades/ frontend/src/app/workspaces/dashboard/
git commit -m "feat(v65): live minute-precision Held; delete the duplicate Hold column"
```

---

### Task 9: Pagers on the Dashboard groups

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/trade-group.ts:17-26,64-73,168-196`
- Test: `frontend/src/app/workspaces/dashboard/trade-group.spec.ts` (create if absent)

**Interfaces:**
- Consumes: `DataTable`'s `[pagination]`/`(pageChange)` (already existed) and
  the top pager from Task 3.
- Produces: no new exported API. `OPEN_POSITIONS_CAP` keeps its value of 6.

- [ ] **Step 1: Write the failing test**

```ts
  it('shows no pager while the group fits inside the cap', async () => {
    api.respond({ items: makeRows(4), total: 4, page: 1, per_page: 6 });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button[aria-label="Next page"]')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('4 rows');
  });

  it('shows a pager once the group exceeds the cap', async () => {
    api.respond({ items: makeRows(6), total: 19, page: 1, per_page: 6 });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button[aria-label="Next page"]')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('1–6 of 19');
  });

  it('refetches the next page rather than slicing what it already has', async () => {
    api.respond({ items: makeRows(6), total: 19, page: 1, per_page: 6 });
    await fixture.whenStable();
    fixture.detectChanges();
    fixture.nativeElement
      .querySelector<HTMLButtonElement>('button[aria-label="Next page"]')!
      .click();
    await fixture.whenStable();
    expect(api.lastQuery.page).toBe(2);
    expect(api.lastQuery.per_page).toBe(6);
  });

  it('offers no rows-per-page control -- the cap is the design', async () => {
    api.respond({ items: makeRows(6), total: 19, page: 1, per_page: 6 });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.per-page')).toBeNull();
  });
```

Build the harness with the same fake-`ApiClient` provider the other dashboard
specs use, and a `makeRows(n)` helper returning `n` `TradeRow` fixtures.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/dashboard/trade-group.spec.ts`
Expected: FAIL — no pager renders at all; page 2 is never requested.

- [ ] **Step 3: Write minimal implementation**

Add a page signal and bind it, in `trade-group.ts`:

```ts
  /** Which page of this group is showing. Server-side: `setQuery` below sends
   *  it, so paging refetches rather than slicing the six rows already held. */
  private readonly page = signal(1);
```

In the template, on `<sb-data-table>`:

```html
        [pagination]="trades.pagination()"
        (pageChange)="page.set($event)"
```

In the constructor's effect, replace `page: 1` with `page: this.page()`.

Reset the page whenever the query's *shape* changes, so the CLOSED group's
Today toggle cannot leave it stranded on a page that no longer exists:

```ts
    // A separate effect from the query one, and it must not read `page`:
    // reading it here would make this effect re-run on its own write.
    effect(() => {
      this.status();
      this.today();
      untracked(() => this.page.set(1));
    });
```

Rewrite `OPEN_POSITIONS_CAP`'s doc comment to record the reversal:

```ts
/**
 * How many rows one category's summary table shows AT ONCE.
 *
 * A page size, and still a cap on what is on screen. The Dashboard answers
 * "what is happening right now" at a glance, and a glance does not scroll.
 *
 * v65 narrowly reverses this comment's original claim that a pager here "would
 * invite paging through a summary, which is the Trades workspace wearing a
 * disguise". The cap itself survives untouched, so the summary is still a
 * summary and `showPerPage` stays off -- what changed is that rows 7+ used to
 * be SILENTLY invisible. A pager appears only when `total` exceeds this, which
 * `PaginationComponent` already handles by rendering no buttons on a
 * single-page table; there is no conditional here to get wrong. The "All N →"
 * link remains the route into the full list.
 */
export const OPEN_POSITIONS_CAP = 6;
```

Import `signal` and `untracked` from `@angular/core`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/dashboard/trade-group.spec.ts`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/trade-group.ts frontend/src/app/workspaces/dashboard/trade-group.spec.ts
git commit -m "feat(v65): page the Dashboard trade groups beyond the six-row cap"
```

---

# Phase D — Workspaces (parallel group)

### Task 10: Risk — client paging, sorting, totals

**Files:**
- Modify: `frontend/src/app/workspaces/risk/risk.ts:222-229,478-483`
- Test: `frontend/src/app/workspaces/risk/risk.spec.ts`

**Interfaces:**
- Consumes: `createClientPage` (Task 7), `ColumnDef.footer` (Task 5),
  `readTablePerPage`/`writeTablePerPage` from `ui/table-prefs`, and
  `PreferencesStore` from `../../stores/preferences.store` (it is
  `providedIn: 'root'`, so `inject()` is all the wiring needed).
- Produces: `Risk.TABLE_ID = 'risk-exposure'`.

- [ ] **Step 1: Write the failing test**

Use the file's existing `seed()` and `payload()` helpers — this suite drives
`HttpTestingController` and flushes real payloads; there is no fake store to
set. Add a row factory next to `payload()`:

```ts
/** N positions with ascending risk_pct 0..N-1, so an ordering assertion has
 *  something unambiguous to land on. */
function positions(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    ticker: `T${i}`, strategy: 'RSI', shares: 10,
    entry: 100, stop_loss: 95, risk_pct: i,
  }));
}
```

```ts
  it('pages the exposure table and reports the pre-slice total', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/risk').flush(payload({ positions: positions(30) }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('tbody tr.row').length).toBe(25);
    expect(el.textContent).toContain('1–25 of 30');
  });

  it('sorts by risk %, which is the question the table exists to answer', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/risk').flush(payload({ positions: positions(30) }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const header = [...el.querySelectorAll<HTMLButtonElement>('thead .sort')].find(
      (b) => b.textContent!.includes('Risk %'),
    )!;
    header.click();               // ascending
    fixture.detectChanges();
    header.click();               // descending
    fixture.detectChanges();

    // Sorted over all 30, not over the 25 on the page: T29 has the highest
    // risk_pct and sits on page 2 before the sort.
    const first = el.querySelector('tbody tr.row td')!;
    expect(first.textContent!.trim()).toBe('T29');
  });

  it('totals risk over every position, not just the visible page', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/risk').flush(payload({ positions: positions(30) }));
    await fixture.whenStable();
    fixture.detectChanges();

    // Sum of 0..29 is 435. A footer over the visible 25 would read 300.
    const footer = (fixture.nativeElement as HTMLElement).querySelector('tfoot tr')!;
    expect(footer.textContent).toContain('435.00');
  });

  it('renders no footer when there are no positions', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/risk').flush(payload({ positions: [] }));
    await fixture.whenStable();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('tfoot')).toBeNull();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/risk/risk.spec.ts`
Expected: FAIL — all 30 rows render, no `tfoot`, `setSort` is not a member.

- [ ] **Step 3: Write minimal implementation**

Add the preferences store to `risk.ts`'s imports and class — it is
`providedIn: 'root'`, so injecting it is the whole of the wiring:

```ts
import { PreferencesStore } from '../../stores/preferences.store';
import { readTablePerPage, writeTablePerPage } from '../../ui/table-prefs';
import { createClientPage } from '../../ui/data-table/client-page';
import { SortSpec } from '../../ui/data-table/data-table.types';
```

```ts
  private readonly preferences = inject(PreferencesStore);

  /** Stable across releases; the key `table-prefs` stores this table's page
   *  size under. */
  static readonly TABLE_ID = 'risk-exposure';

  protected readonly sort = signal<SortSpec | null>(null);
  protected setSort(next: SortSpec): void { this.sort.set(next); }

  protected readonly perPage = signal(
    readTablePerPage(this.preferences.values(), Risk.TABLE_ID),
  );

  protected onPerPage(value: number): void {
    this.perPage.set(value);
    this.preferences.update((prefs) => writeTablePerPage(prefs, Risk.TABLE_ID, value));
  }

  /** Sorted BEFORE the client page slices, so an ordering applies to the whole
   *  list rather than to the twenty-five rows that happen to be on screen --
   *  the exact defect `DataTable`'s "server-side everything" property exists to
   *  prevent, reproduced client-side if the two are composed the wrong way. */
  protected readonly sortedPositions = computed(() => {
    const sort = this.sort();
    const rows = [...this.store.positions()];
    if (!sort) return rows;
    const dir = sort.direction === 'asc' ? 1 : -1;
    return rows.sort((a, b) => {
      const left = (a as Record<string, unknown>)[sort.key];
      const right = (b as Record<string, unknown>)[sort.key];
      // Valueless rows sink in BOTH directions, matching the API's own
      // `_sorted_rows` behaviour, so a legacy row never floats to the top.
      if (left === null || left === undefined) return 1;
      if (right === null || right === undefined) return -1;
      return left < right ? -dir : left > right ? dir : 0;
    });
  });

  protected readonly exposurePage = createClientPage(
    () => this.sortedPositions(),
    () => this.perPage(),
  );
```

Mark the columns sortable and give the two numeric ones footers:

```ts
    { key: 'ticker', header: 'Ticker', cell: this.tickerCell(), sortable: true },
    { key: 'strategy', header: 'Strategy', value: (row) => text(row.strategy), sortable: true },
    {
      key: 'shares', header: 'Shares', value: (row) => num(row.shares, 0),
      numeric: true, sortable: true,
      footer: (rows) => num(rows.reduce((sum, r) => sum + (r.shares ?? 0), 0), 0),
    },
    { key: 'entry', header: 'Entry', value: (row) => num(row.entry), numeric: true, sortable: true },
    { key: 'stop_loss', header: 'Stop', value: (row) => num(row.stop_loss), numeric: true, sortable: true },
    {
      key: 'risk_pct', header: 'Risk %', numeric: true, cell: this.riskCell(), sortable: true,
      // Total open risk -- what "how exposed am I right now" is asking. Honest
      // because this table holds the complete set client-side; Trades declares
      // no footer for exactly the opposite reason.
      footer: (rows) => num(rows.reduce((sum, r) => sum + (r.risk_pct ?? 0), 0)),
    },
```

Bind the table:

```html
      <sb-data-table
        [rows]="exposurePage.visible()"
        [columns]="columns()"
        [visible]="visible"
        [rowKey]="rowKey"
        [sort]="sort()"
        [pagination]="exposurePage.pageSpec()"
        [showPerPage]="true"
        [emptyState]="emptyState"
        (sortChange)="setSort($event)"
        (pageChange)="exposurePage.setPage($event)"
        (perPageChange)="onPerPage($event)"
      />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/risk/risk.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/risk/
git commit -m "feat(v65): page, sort and total the Risk exposure table"
```

---

### Task 11: Watchlist — client paging over the sorted list

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts:224-234`
- Test: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`

**Interfaces:**
- Consumes: `createClientPage` (Task 7), the existing `sortedRows()` and
  `setSort()` on this component, `readTablePerPage`/`writeTablePerPage`,
  `PreferencesStore` (root-provided).
- Produces: `Watchlist.TABLE_ID = 'watchlist'`.

- [ ] **Step 1: Write the failing test**

Use the file's existing `seed()`; this suite flushes
`/api/v1/watchlist/tickers`. Add a factory:

```ts
/** T00..T39, zero-padded so a lexical sort and a numeric one agree. */
function tickers(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    ticker: `T${String(i).padStart(2, '0')}`, earnings_date: null,
  }));
}
```

```ts
  it('pages the watchlist and reports the pre-slice total', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/watchlist/tickers').flush({ tickers: tickers(40) });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('tbody tr.row').length).toBe(25);
    expect(el.textContent).toContain('1–25 of 40');
  });

  it('sorts the whole list before paging, not the visible page', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/watchlist/tickers').flush({ tickers: tickers(40) });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const header = [...el.querySelectorAll<HTMLButtonElement>('thead .sort')].find(
      (b) => b.textContent!.includes('Ticker'),
    )!;
    header.click();
    fixture.detectChanges();
    header.click();               // descending
    fixture.detectChanges();

    // T39 lives on page 2 before the sort; ordering the whole list brings it
    // to the top of page 1. Sorting only the visible slice would leave T24.
    expect(el.querySelector('tbody tr.row td')!.textContent!.trim()).toBe('T39');
  });

  it('pads the last page so its height matches a full one', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/watchlist/tickers').flush({ tickers: tickers(28) });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const next = el.querySelector<HTMLButtonElement>('button[aria-label="Next page"]')!;
    next.click();
    fixture.detectChanges();
    expect(el.querySelectorAll('tbody tr.row').length).toBe(3);
    expect(el.querySelectorAll('tbody tr.filler').length).toBe(22);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/watchlist/watchlist.spec.ts`
Expected: FAIL — 40 rows render and no pager exists.

- [ ] **Step 3: Write minimal implementation**

Add the same imports Task 10 added (`PreferencesStore`, `readTablePerPage`,
`writeTablePerPage`, `createClientPage`), then to the class:

```ts
  private readonly preferences = inject(PreferencesStore);

  static readonly TABLE_ID = 'watchlist';

  protected readonly perPage = signal(
    readTablePerPage(this.preferences.values(), Watchlist.TABLE_ID),
  );

  protected onPerPage(value: number): void {
    this.perPage.set(value);
    this.preferences.update((prefs) => writeTablePerPage(prefs, Watchlist.TABLE_ID, value));
  }

  /** Over `sortedRows()`, never the raw rows: order the whole list, THEN
   *  slice. Paging a list and sorting the slice is the bug `DataTable` refuses
   *  to commit server-side, and it is just as wrong done here. */
  protected readonly watchlistPage = createClientPage(
    () => this.sortedRows(),
    () => this.perPage(),
  );
```

Bind the table:

```html
        <sb-data-table
          [rows]="watchlistPage.visible()"
          [columns]="columns()"
          [visible]="visible"
          [rowKey]="rowKey"
          [rowClass]="rowClassFn"
          [sort]="sort()"
          [pagination]="watchlistPage.pageSpec()"
          [showPerPage]="true"
          [emptyState]="emptyState"
          (sortChange)="setSort($event)"
          (pageChange)="watchlistPage.setPage($event)"
          (perPageChange)="onPerPage($event)"
          (rowActivate)="open($event)"
        />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/watchlist/watchlist.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/watchlist/watchlist.spec.ts
git commit -m "feat(v65): page the Watchlist over its sorted list"
```

---

### Task 12: Ticker detail — paging, sorting, live Held

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/ticker-detail.ts:89-96,177`
- Create: `frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts` — this
  component has **no spec file today**; this task writes its first one.

**Interfaces:**
- Consumes: `createClientPage` (Task 7), `CLOCK` (Task 1), `held` and
  `elapsedHours` (Task 6), `PreferencesStore` (root-provided).
- Produces: `TickerDetail.TABLE_ID = 'ticker-trades'`.

- [ ] **Step 1: Write the failing test**

Create the file, modelled on `watchlist.spec.ts`'s `seed()`. The component
reads its symbol from the route, so the router must be seeded with one.

```ts
// frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { CLOCK } from '../../ui/clock';
import { TickerDetail } from './ticker-detail';

const NOW = Date.parse('2026-08-28T12:00:00Z');
const clock = signal(NOW);

function trade(over: Record<string, unknown> = {}) {
  return {
    id: 'x', ticker: 'AAPL', status: 'CLOSED', direction: 'LONG',
    entry: 100, current_price: 105, pnl_pct: 5, r_multiple: 1,
    opened_at: '2026-08-01T09:00:00Z', closed_at: '2026-08-02T10:30:00Z',
    held_hours: 25.5, ...over,
  };
}

function seed(): { fixture: ComponentFixture<TickerDetail>; backend: HttpTestingController } {
  TestBed.resetTestingModule();
  clock.set(NOW);
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([], withComponentInputBinding()),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      // Never the real token here: its default starts a 30s interval that
      // would outlive the suite.
      { provide: CLOCK, useValue: clock },
    ],
  });
  const fixture = TestBed.createComponent(TickerDetail);
  fixture.componentRef.setInput('symbol', 'AAPL');
  return { fixture, backend: TestBed.inject(HttpTestingController) };
}

/** Flush every request this view fires, returning the trades one's payload. */
function flush(backend: HttpTestingController, items: unknown[]): void {
  for (const req of backend.match(() => true)) {
    if (req.request.url.includes('/trades')) {
      req.flush({ items, total: items.length, page: 1, per_page: 200 });
    } else {
      req.flush({});
    }
  }
}

describe('TickerDetail trades table', () => {
  it('pages a ticker with a long history', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flush(backend, Array.from({ length: 30 }, (_, i) => trade({ id: `t${i}` })));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('tbody tr.row').length).toBe(25);
    expect(el.textContent).toContain('1–25 of 30');
  });

  it('shows a live minute-precision Held for an open position', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flush(backend, [
      trade({ opened_at: '2026-08-28T09:30:00Z', closed_at: null, held_hours: 0 }),
    ]);
    await fixture.whenStable();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('2h 30m');

    // Advancing the clock alone must move the cell -- no refetch involved.
    clock.set(Date.parse('2026-08-28T12:45:00Z'));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('3h 15m');
  });

  it('leaves a CLOSED row fixed when the clock moves', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flush(backend, [trade()]);
    await fixture.whenStable();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('1d 1h 30m');

    clock.set(Date.parse('2026-09-01T12:00:00Z'));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('1d 1h 30m');
  });

  it('offers a sortable Held column, matching Trades', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flush(backend, [trade()]);
    await fixture.whenStable();
    fixture.detectChanges();

    const headers = [...(fixture.nativeElement as HTMLElement)
      .querySelectorAll<HTMLButtonElement>('thead .sort')];
    expect(headers.some((b) => b.textContent!.includes('Held'))).toBe(true);
  });
});
```

If `TickerDetail` takes its symbol from a route param rather than a signal
input, drop the `setInput` line and seed the route instead — check the
component's own `symbol` declaration first and match it.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/watchlist/ticker-detail.spec.ts`
Expected: FAIL — 30 rows render, `held` is not sortable, and the Held cell
still reads the server's `held_hours`.

- [ ] **Step 3: Write minimal implementation**

Add the same imports Task 10 added (`PreferencesStore`, `readTablePerPage`,
`writeTablePerPage`, `createClientPage`, `SortSpec`) plus `CLOCK` from
`../../ui/clock` and `elapsedHours` alongside the existing `held` import, then
to the class:

```ts
  static readonly TABLE_ID = 'ticker-trades';

  private readonly preferences = inject(PreferencesStore);
  private readonly now = inject(CLOCK);

  protected readonly sort = signal<SortSpec | null>(null);
  protected setSort(next: SortSpec): void { this.sort.set(next); }

  protected readonly perPage = signal(
    readTablePerPage(this.preferences.values(), TickerDetail.TABLE_ID),
  );

  protected onPerPage(value: number): void {
    this.perPage.set(value);
    this.preferences.update((prefs) =>
      writeTablePerPage(prefs, TickerDetail.TABLE_ID, value),
    );
  }

  /** Sorted first, sliced second -- see `watchlist.ts` for why that order is
   *  not interchangeable. */
  protected readonly sortedTrades = computed(() => {
    const sort = this.sort();
    const rows = [...this.trades.rows()];
    if (!sort) return rows;
    const dir = sort.direction === 'asc' ? 1 : -1;
    return rows.sort((a, b) => {
      const left = (a as Record<string, unknown>)[sort.key];
      const right = (b as Record<string, unknown>)[sort.key];
      if (left === null || left === undefined) return 1;
      if (right === null || right === undefined) return -1;
      return left < right ? -dir : left > right ? dir : 0;
    });
  });

  protected readonly tradesPage = createClientPage(
    () => this.sortedTrades(),
    () => this.perPage(),
  );
```

Replace the `held` column (line 177) with the same live form Task 8 used:

```ts
    {
      key: 'held',
      header: 'Held',
      value: (row) =>
        held(row.closed_at ? row.held_hours : elapsedHours(row.opened_at, this.now())),
      numeric: true,
      sortable: true,
    },
```

Bind the table with `[rows]="tradesPage.visible()"`, `[sort]="sort()"`,
`[pagination]="tradesPage.pageSpec()"`, `[showPerPage]="true"`, and the
matching `(sortChange)`, `(pageChange)`, `(perPageChange)` handlers.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/watchlist/ticker-detail.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/watchlist/ticker-detail.ts frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts
git commit -m "feat(v65): page, sort and live-Held the ticker detail trade table"
```

---

### Task 13: Analytics — rows-per-page on the eight tables

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts:492,516,567,659,691,718,800,821`
- Test: `frontend/src/app/workspaces/analytics/analytics.spec.ts`

**Interfaces:**
- Consumes: `createClientPage`'s function form (Task 7),
  `readTablePerPage`/`writeTablePerPage`.
- Produces: nothing consumed by a later task.

- [ ] **Step 1: Write the failing test**

Use the file's existing `seed()` and `performancePayload()` helpers, flushing
the same three endpoints the other tests in this suite do. Extend
`performancePayload()` so the breakdown array can be given a length:

```ts
/** Breakdown rows keyed T0..T(n-1), so a page slice is countable. */
function breakdown(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    bucket: `T${i}`, trades: 10, win_rate: 50, exp_r: 0.1,
  }));
}
```

```ts
  it('offers a rows-per-page control on the breakdown table', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/analytics/journal').flush({ digest: [], lessons: [], entries_n: 0 });
    backend.expectOne('/api/v1/analytics/snapshot').flush({});
    backend
      .expectOne('/api/v1/analytics/performance')
      .flush(performancePayload({ breakdown: breakdown(40) }));
    await fixture.whenStable();
    fixture.detectChanges();

    const select = (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLSelectElement>('.per-page select');
    expect(select).not.toBeNull();
    expect([...select!.options].map((o) => o.value)).toEqual(['10', '25', '50', '0']);
  });

  it('re-slices the table when the page size changes', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/analytics/journal').flush({ digest: [], lessons: [], entries_n: 0 });
    backend.expectOne('/api/v1/analytics/snapshot').flush({});
    backend
      .expectOne('/api/v1/analytics/performance')
      .flush(performancePayload({ breakdown: breakdown(40) }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('tbody tr.row').length).toBe(25);

    const select = el.querySelector<HTMLSelectElement>('.per-page select')!;
    select.value = '50';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    expect(el.querySelectorAll('tbody tr.row').length).toBe(40);
    expect(el.textContent).toContain('40 rows');
  });

  it('remembers the choice under a per-table key, not a global one', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/analytics/journal').flush({ digest: [], lessons: [], entries_n: 0 });
    backend.expectOne('/api/v1/analytics/snapshot').flush({});
    backend
      .expectOne('/api/v1/analytics/performance')
      .flush(performancePayload({ breakdown: breakdown(40) }));
    await fixture.whenStable();
    fixture.detectChanges();

    const select = (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLSelectElement>('.per-page select')!;
    select.value = '10';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    const prefs = TestBed.inject(PreferencesStore);
    expect(prefs.values()['tables.analytics-breakdown.per_page']).toBe(10);
    // The eight tables must not share one key -- changing one would silently
    // repage the other seven.
    expect(prefs.values()['tables.analytics-strategy.per_page']).toBeUndefined();
  });
```

If more than one `.per-page select` is on screen for the active tab, scope each
query to the panel under test rather than relaxing the assertion.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/analytics.spec.ts`
Expected: FAIL — no `.per-page` control renders.

- [ ] **Step 3: Write minimal implementation**

Add the imports Task 10 added (`PreferencesStore`, `readTablePerPage`,
`writeTablePerPage`) plus `WritableSignal` from `@angular/core`, then one
shared helper to the class rather than eight near-copies:

```ts
  private readonly preferences = inject(PreferencesStore);

  /** The eight client-paged Analytics tables, each with its own remembered
   *  page size. Keyed rather than eight fields, because the read/write pair is
   *  identical for all of them and eight copies of it is where a typo lives. */
  private readonly perPageSignals = new Map<string, WritableSignal<number>>();

  private perPageFor(table: string): WritableSignal<number> {
    let existing = this.perPageSignals.get(table);
    if (!existing) {
      existing = signal(readTablePerPage(this.preferences.values(), `analytics-${table}`));
      this.perPageSignals.set(table, existing);
    }
    return existing;
  }

  protected onPerPage(table: string, value: number): void {
    this.perPageFor(table).set(value);
    this.preferences.update((prefs) =>
      writeTablePerPage(prefs, `analytics-${table}`, value),
    );
  }
```

Change each of the eight `createClientPage(...)` calls to pass the reactive
size, e.g.:

```ts
  protected readonly breakdownPage = createClientPage(
    () => this.store.breakdown(),
    () => this.perPageFor('breakdown')(),
  );
```

Do the same for `confidencePage` (`confidence`), `strategyPage` (`strategy`),
`decilePage` (`decile`), `tierPage` (`tier`), `driftPage` (`drift`),
`gridPage` (`grid`) and `pastJobsPage` (`past-jobs`).

On each of the eight `<sb-data-table>` elements add:

```html
              [showPerPage]="true"
              (perPageChange)="onPerPage('breakdown', $event)"
```

with the matching table key in each.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/analytics.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/
git commit -m "feat(v65): rows-per-page on the eight Analytics tables"
```

---

# Phase E — Sticky header and verification

### Task 14: Sticky table header

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.ts` (styles only)
- Test: `frontend/src/app/ui/data-table/data-table.spec.ts`

Sequenced last on purpose: it is the one change in this plan that can look
subtly wrong at a viewport without failing a test, so nothing else waits on it.

**Interfaces:**
- Consumes: `--header-h` (added here if `shell.css` does not already expose it).
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

```ts
  it('sticks the header, offset by the app header rather than to the scroller', () => {
    fixture.detectChanges();
    const th = fixture.nativeElement.querySelector('thead th')!;
    const styles = getComputedStyle(th);
    expect(styles.position).toBe('sticky');
    // Not 0px: sticking at 0 puts the column headers UNDER the app header,
    // which is itself sticky.
    expect(styles.top).not.toBe('0px');
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: FAIL — `position` is `static`.

- [ ] **Step 3: Write minimal implementation**

First confirm the shell exposes its height as a token:

```bash
grep -n "header-h\|position: sticky" frontend/src/app/shell/shell.css
```

If `--header-h` does not exist, add it to `frontend/src/styles/tokens.css`
alongside the other layout tokens, set to the shell header's actual height, and
make `shell.css:93`'s rule use it so the two cannot drift.

Then in `data-table.ts`:

```css
    /* The scroller is `overflow-x: auto`, and CSS computes the OTHER axis to
     * `auto` whenever one axis is not `visible` -- so .scroller is a scrollport
     * on both axes. A `position: sticky; top: 0` inside it therefore sticks to
     * a box that never scrolls vertically, which is to say it does nothing.
     * That is why this rule offsets against the VIEWPORT instead, by the
     * shell's own sticky header height: the page is what scrolls vertically.
     *
     * z-index because a sticky header still paints in document order, so the
     * rows would scroll over it. background because a sticky element is
     * transparent by default and the data would show through it. --surface,
     * not --bg: the header belongs to the panel it sits in. */
    thead th {
      position: sticky;
      top: var(--header-h);
      z-index: 2;
      background: var(--surface);
    }
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: PASS.

Then check visually — jsdom does not lay out, so the test above proves only
that the declaration is present:

```bash
cd frontend && npm start
```

At 375px, 768px and 1280px, on Trades with 50 rows per page: the column headers
must stay under the app header and above the rows, with no gap and no overlap,
and the horizontal scroller must still work.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/data-table/data-table.ts frontend/src/styles/tokens.css frontend/src/app/shell/shell.css
git commit -m "feat(v65): sticky table header, offset by the shell header"
```

---

### Task 15: Full-suite verification

**Files:** none.

- [ ] **Step 1: Run the frontend suite once, over everything this plan built**

```bash
cd frontend && npm test
```

Expected: 0 failed. No Python suite is run — this plan touches no file under
`swingbot/`, `tests/` or `scripts/`.

**If it is not green, fix forward from those failures** — they are this plan's
regressions, and the task is not done until the run is. The likely places, in
order: specs that called `tradeColumns()` with no argument; specs asserting the
old `held` hour-rounding; specs asserting a pager renders nothing on a
single-page table; and row-count assertions in workspace specs that now see a
paged slice rather than the whole list.

- [ ] **Step 2: Bump `VERSION.json`**

`ui` minor: `1.9.2` → `1.10.0`. `bot` unchanged. Then regenerate and commit
`version_history.json` in the same commit — the local gate runs before the
bump, so it structurally cannot catch a missing regeneration.

- [ ] **Step 3: Commit**

```bash
git add VERSION.json frontend/public/version_history.json
git commit -m "chore(v65): bump ui to 1.10.0 for the table pagination overhaul"
```

- [ ] **Step 4: Close the plan out**

Move both documents to `implemented/` per `docs/claude/document-lifecycle.md`,
and amend the spec's `Bump:` line if the work landed at a different level than
predicted.
