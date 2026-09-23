# v95 — Part 2: Primitives

Part of `2026-09-17-v95-responsive-content-priority`. Header block, goal,
global constraints, parallelisation map and exit criteria live in
`_0-index.md` — read that first.

# Phase B — Primitives

**Sequential throughout.** B1 defines the type B2 and B3 consume; B2, B3 and B8
edit the same two files. Do not dispatch these concurrently — the second writer
overwrites the first with no conflict and no warning.

This phase carries the plan's blast radius: every workspace renders these
components. Nothing here changes what any workspace looks like yet, because no
workspace declares `inlineFrom` until Phase C — each task must leave existing
call sites rendering exactly as before.

---

### Task B1: `inlineFrom` on `ColumnDef<T>`

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.types.ts:80-106`
- Test: `frontend/src/app/ui/data-table/data-table.spec.ts`

**Interfaces:**
- Consumes: `Viewport` from `ui/breakpoints.ts`.
- Produces: `ColumnDef<T>.inlineFrom?: Viewport`. Optional, so all four existing
  call sites (Trades, Analytics/Strategies, Risk, Watchlist) compile and render
  unchanged until they opt in.

- [x] **Step 1: Write the failing test**

Append to `frontend/src/app/ui/data-table/data-table.spec.ts`:

```ts
import { isInline } from '../priority';

describe('ColumnDef inlineFrom', () => {
  it('is optional and defaults to always inline', () => {
    // Adding the field must change nothing for a column that omits it, or
    // this becomes a breaking change to four call sites at once.
    const column: ColumnDef<{ ticker: string }> = { key: 'ticker', header: 'Ticker' };
    expect(isInline(column.inlineFrom, 'xs')).toBe(true);
  });

  it('carries a declared floor through to the resolver', () => {
    const column: ColumnDef<{ held: string }> = {
      key: 'held', header: 'Held', inlineFrom: 'md',
    };
    expect(isInline(column.inlineFrom, 'sm')).toBe(false);
    expect(isInline(column.inlineFrom, 'md')).toBe(true);
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: FAIL — TypeScript rejects `inlineFrom` as not a property of `ColumnDef`.

- [x] **Step 3: Write the implementation**

In `data-table.types.ts`, add the import and the field to `ColumnDef<T>`, after
`width`:

```ts
import { Viewport } from '../breakpoints';
```

```ts
  /**
   * The narrowest viewport at which this column renders inline — v95 §4.1.
   *
   * Below it the column leaves the grid and renders in the row's detail
   * expansion instead. **Never hidden**: the parity gate asserts every
   * declared column is reachable at every viewport.
   *
   * Omitted means always inline, so a column that says nothing behaves
   * exactly as it did before v95. Note this is deliberately NOT the same
   * axis as `visible`: `visible` is what the USER chose to show, `inlineFrom`
   * is where the layout can afford to put it. A column the user hid is gone;
   * a column below its floor is one tap away.
   */
  inlineFrom?: Viewport;
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: PASS, and every pre-existing test in the file still passes.

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/data-table/data-table.types.ts frontend/src/app/ui/data-table/data-table.spec.ts
git commit -m "feat(v95): ColumnDef.inlineFrom -- the column's viewport floor"
```

---

### Task B2: Split rendered columns into inline and demoted

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.ts:453-472`
- Test: `frontend/src/app/ui/data-table/data-table.spec.ts`

`renderedColumns` currently returns everything `visible` names. It splits into
two computed signals: the columns the grid draws, and the columns the row
detail draws. v80's `phone`/`pinKey`/`sortOptions` all keep working off the
inline set.

**Interfaces:**
- Consumes: `isInline` (A1), `ColumnDef.inlineFrom` (B1), `ViewportService`.
- Produces:
  - `protected readonly inlineColumns: Signal<ColumnDef<T>[]>`
  - `protected readonly demotedColumns: Signal<ColumnDef<T>[]>`
  - `readonly viewportAt = input<Viewport | null>(null)` — a test override, the
    same device `cardsAt` already is, for the same jsdom reason.

  B3 renders `demotedColumns`. `pinKey` and `sortOptions` must be re-pointed at
  `inlineColumns` in this task, not B3.

- [x] **Step 1: Write the failing test**

Append to `frontend/src/app/ui/data-table/data-table.spec.ts`. Add
`[viewportAt]="viewportAt()"` to the `Host` template's `sb-data-table` and
`readonly viewportAt = signal<Viewport | null>(null);` to the `Host` class
first — mirror how `cardsAt` is wired at lines 64 and 82.

```ts
describe('DataTable column demotion', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.visible.set(['ticker', 'pnl', 'held']);
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const headers = () =>
    [...el().querySelectorAll('thead th')].map((th) => th.textContent!.trim());

  it('draws every column when none declares a floor', () => {
    host.viewportAt.set('xs');
    fixture.detectChanges();
    expect(headers()).toEqual(['Ticker', 'P&L %', 'Held']);
  });

  it('drops a below-floor column out of the grid', () => {
    host.columns.set([
      { key: 'ticker', header: 'Ticker' },
      { key: 'pnl', header: 'P&L %' },
      { key: 'held', header: 'Held', inlineFrom: 'md' },
    ]);
    host.viewportAt.set('sm');
    fixture.detectChanges();
    expect(headers()).toEqual(['Ticker', 'P&L %']);
  });

  it('restores it at and above its floor', () => {
    host.columns.set([
      { key: 'ticker', header: 'Ticker' },
      { key: 'pnl', header: 'P&L %' },
      { key: 'held', header: 'Held', inlineFrom: 'md' },
    ]);
    host.viewportAt.set('md');
    fixture.detectChanges();
    expect(headers()).toEqual(['Ticker', 'P&L %', 'Held']);
  });

  it('never demotes the pinned identity column, whatever it declares', () => {
    // v80 D4: the pinned column is what says which row you are on. A floor
    // that scrolled it away would undo that decision by accident.
    host.columns.set([
      { key: 'ticker', header: 'Ticker', inlineFrom: 'xl' },
      { key: 'pnl', header: 'P&L %' },
    ]);
    host.viewportAt.set('xs');
    fixture.detectChanges();
    expect(headers()).toContain('Ticker');
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: FAIL — `viewportAt` is not an input; the drop case still shows `Held`.

- [x] **Step 3: Write the implementation**

In `data-table.ts`, after `renderedColumns` (which stays as the union), add:

```ts
  /** A test override, for the reason `cardsAt` is one: jsdom evaluates no
   *  media query, so the viewport is the only thing a test cannot observe. */
  readonly viewportAt = input<Viewport | null>(null);
  private readonly viewport = computed<Viewport>(
    () => this.viewportAt() ?? this.viewportService.viewport(),
  );

  /**
   * The split — v95 §4.1.
   *
   * The pinned identity column is exempt: v80 D4 made it the thing that says
   * which row you are looking at, and a declared floor that demoted it would
   * reverse that decision silently. A call site that puts a floor on its
   * identity column is asking for something incoherent, and the exemption is
   * cheaper than a runtime error nobody sees.
   */
  protected readonly inlineColumns = computed(() => {
    const viewport = this.viewport();
    const pin = this.pinKey();
    return this.renderedColumns().filter(
      (column) => column.key === pin || isInline(column.inlineFrom, viewport),
    );
  });

  protected readonly demotedColumns = computed(() => {
    const inline = new Set(this.inlineColumns().map((column) => column.key));
    return this.renderedColumns().filter((column) => !inline.has(column.key));
  });
```

Add `isInline` and `Viewport` to the imports.

Then re-point the three v80 members that must now read the inline set, so the
sort select never offers a column the grid is not drawing:

- `pinKey`: change `this.renderedColumns()` to `this.renderedColumns()` —
  **unchanged**. `pinKey` must stay on the full set, or the exemption above is
  circular.
- `sortOptions`: change `this.renderedColumns()` to `this.inlineColumns()`.

Finally, change the template's `@for` over header cells and body cells from
`renderedColumns()` to `inlineColumns()`. Leave `visible`, the column picker
and the reorder handlers pointed at `renderedColumns()` — those are the user's
choice, not the layout's.

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: PASS — including every pre-existing v80 phone-mode test, unmodified.

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/data-table/data-table.spec.ts
git commit -m "feat(v95): data table splits columns into inline and demoted"
```

---

### Task B3: Render demoted columns in the row detail

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.ts` (template + styles)
- Test: `frontend/src/app/ui/data-table/data-table.spec.ts`

A demoted column must be reachable, not merely absent. Every row gains a
disclosure that lists its demoted columns as label/value pairs, above the call
site's own `expansion` template when one is supplied.

**Interfaces:**
- Consumes: `demotedColumns` (B2), the existing `expansion` input and
  `RowContext<T>`.
- Produces:
  - `.row-detail` markup with one `.detail-item` per demoted column, each
    carrying `.detail-label` and `.detail-value`.
  - A per-row toggle `button.detail-toggle` with
    `[attr.aria-expanded]` and an `aria-label` naming the row.
  - No new input. A row has a detail exactly when `demotedColumns()` is
    non-empty or `expansion()` is set.

- [x] **Step 1: Write the failing test**

Append to `data-table.spec.ts`:

```ts
describe('DataTable row detail', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  const DEMOTING = [
    { key: 'ticker', header: 'Ticker', value: (r: Row) => r.ticker },
    { key: 'pnl', header: 'P&L %', value: (r: Row) => r.pnl, inlineFrom: 'md' as const },
    { key: 'held', header: 'Held', value: (r: Row) => r.held, inlineFrom: 'md' as const },
  ];

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.columns.set(DEMOTING);
    host.visible.set(['ticker', 'pnl', 'held']);
    host.viewportAt.set('sm');
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;

  it('offers a detail toggle on every row when columns are demoted', () => {
    expect(el().querySelectorAll('button.detail-toggle')).toHaveLength(ROWS.length);
  });

  it('starts collapsed', () => {
    const toggle = el().querySelector('button.detail-toggle')!;
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(el().querySelector('.row-detail')).toBeNull();
  });

  it('reveals every demoted column, labelled, on expand', () => {
    (el().querySelector('button.detail-toggle') as HTMLElement).click();
    fixture.detectChanges();

    const labels = [...el().querySelectorAll('.row-detail .detail-label')]
      .map((n) => n.textContent!.trim());
    expect(labels).toEqual(['P&L %', 'Held']);

    const values = [...el().querySelectorAll('.row-detail .detail-value')]
      .map((n) => n.textContent!.trim());
    expect(values).toEqual([String(ROWS[0].pnl), String(ROWS[0].held)]);
  });

  it('names the row it opens, so the toggle is not an anonymous chevron', () => {
    const toggle = el().querySelector('button.detail-toggle')!;
    expect(toggle.getAttribute('aria-label')).toContain(ROWS[0].ticker);
  });

  it('offers no toggle when nothing is demoted', () => {
    host.viewportAt.set('xl');
    fixture.detectChanges();
    expect(el().querySelector('button.detail-toggle')).toBeNull();
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: FAIL — no `.detail-toggle` exists.

- [x] **Step 3: Write the implementation**

Add the open-row state to the class:

```ts
  /** Which rows have their detail open, by index. Not persisted: a detail is
   *  a glance, not a preference, and a remembered one would reopen rows the
   *  user has since filtered away. */
  protected readonly openRows = signal(new Set<number>());

  protected hasDetail(): boolean {
    return this.demotedColumns().length > 0 || this.expansion() !== null;
  }

  protected toggleDetail(index: number): void {
    this.openRows.update((open) => {
      const next = new Set(open);
      next.has(index) ? next.delete(index) : next.add(index);
      return next;
    });
  }

  /** The row's identity, for the toggle's accessible name. Falls back to the
   *  index so the label is never just "expand". */
  protected rowLabel(row: T, index: number): string {
    const pin = this.pinKey();
    const column = this.renderedColumns().find((c) => c.key === pin);
    const value = column?.value?.(row);
    return value == null ? `row ${index + 1}` : String(value);
  }
```

In the template, inside the body row, append a toggle cell when `hasDetail()`:

```html
@if (hasDetail()) {
  <td class="detail-cell">
    <button
      type="button"
      class="detail-toggle"
      [attr.aria-expanded]="openRows().has(i)"
      [attr.aria-label]="'Show more for ' + rowLabel(row, i)"
      (click)="toggleDetail(i); $event.stopPropagation()"
    >›</button>
  </td>
}
```

and after the row, the detail row itself:

```html
@if (openRows().has(i)) {
  <tr class="row-detail">
    <td [attr.colspan]="inlineColumns().length + 1">
      @for (column of demotedColumns(); track column.key) {
        <div class="detail-item">
          <span class="detail-label sb-label">{{ column.header }}</span>
          <span class="detail-value">
            @if (column.cell) {
              <ng-container [ngTemplateOutlet]="column.cell" [ngTemplateOutletContext]="{ $implicit: row }" />
            } @else {
              {{ column.value?.(row) ?? '—' }}
            }
          </span>
        </div>
      }
      @if (expansion(); as tpl) {
        <ng-container [ngTemplateOutlet]="tpl" [ngTemplateOutletContext]="{ $implicit: row }" />
      }
    </td>
  </tr>
}
```

Styles:

```css
    .detail-cell { width: var(--control-h); text-align: center; }
    .detail-toggle {
      min-height: var(--control-h);
      min-width: var(--control-h);
      background: none;
      border: 0;
      color: var(--text-faint);
      cursor: pointer;
    }
    .row-detail > td { padding: var(--space-10) var(--space-14); background: var(--surface-2); }
    .detail-item { display: flex; justify-content: space-between; gap: var(--space-10); padding: 2px 0; }
    .detail-label { flex: 0 0 auto; }
    .detail-value { min-width: 0; text-align: right; font-family: var(--font-mono); }
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: PASS, and every v80 phone-mode test still passes — no workspace
declares a floor yet, so `hasDetail()` is false everywhere in production.

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/data-table/data-table.spec.ts
git commit -m "feat(v95): demoted columns render in a labelled row detail"
```

---

### Task B4: `sb-toolbar` — controls with a sheet

**Files:**
- Create: `frontend/src/app/ui/toolbar.ts`
- Create: `frontend/src/app/ui/toolbar.spec.ts`

A new component, not an edit to `control-bar.ts`/`filter-bar.ts`. Call sites
migrate in their own workspace tasks (Phase C/D), so this task ships a
component nothing uses yet and breaks nothing.

**Interfaces:**
- Consumes: `isInline` (A1), `ViewportService`, `Viewport`.
- Produces:
  - `interface ToolbarControl { id: string; label: string; inlineFrom?: Viewport; active?: boolean }`
  - `class Toolbar` with `selector: 'sb-toolbar'`, inputs
    `controls = input<ToolbarControl[]>([])` and
    `viewportAt = input<Viewport | null>(null)`, and content projection by
    `[slot]` matching each control's `id`.
  - `.toolbar-sheet-button` carrying `[attr.aria-expanded]`, and
    `.toolbar-sheet` containing the demoted controls' projected content.

- [x] **Step 1: Write the failing test**

Create `frontend/src/app/ui/toolbar.spec.ts`:

```ts
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, beforeEach, expect, it } from 'vitest';

import { Viewport } from './breakpoints';
import { Toolbar, ToolbarControl } from './toolbar';

@Component({
  imports: [Toolbar],
  template: `
    <sb-toolbar [controls]="controls()" [viewportAt]="viewportAt()">
      <button slot="status">Status</button>
      <button slot="ticker">Ticker</button>
      <button slot="badge">Badge</button>
    </sb-toolbar>
  `,
})
class Host {
  readonly viewportAt = signal<Viewport | null>(null);
  readonly controls = signal<ToolbarControl[]>([
    { id: 'status', label: 'Status' },
    { id: 'ticker', label: 'Ticker', inlineFrom: 'md' },
    { id: 'badge', label: 'Badge', inlineFrom: 'md' },
  ]);
}

describe('sb-toolbar', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.viewportAt.set('sm');
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;

  it('keeps above-floor controls inline', () => {
    expect(el().querySelector('.toolbar-inline [slot="status"]')).not.toBeNull();
  });

  it('moves below-floor controls into the sheet, not out of the DOM', () => {
    expect(el().querySelector('.toolbar-inline [slot="ticker"]')).toBeNull();
    expect(el().querySelector('.toolbar-sheet [slot="ticker"]')).not.toBeNull();
  });

  it('starts with the sheet closed', () => {
    expect(el().querySelector('.toolbar-sheet-button')!.getAttribute('aria-expanded'))
      .toBe('false');
  });

  it('offers no sheet button when nothing is demoted', () => {
    host.viewportAt.set('xl');
    fixture.detectChanges();
    expect(el().querySelector('.toolbar-sheet-button')).toBeNull();
  });

  it('names how many demoted controls it holds', () => {
    expect(el().querySelector('.toolbar-sheet-button')!.textContent).toContain('2');
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/toolbar.spec.ts`
Expected: FAIL — `Failed to resolve import "./toolbar"`.

- [x] **Step 3: Write the implementation**

Create `frontend/src/app/ui/toolbar.ts`:

```ts
import {
  ChangeDetectionStrategy, Component, computed, inject, input, signal,
} from '@angular/core';

import { Viewport, ViewportService } from './breakpoints';
import { isInline } from './priority';

/**
 * A control bar that collapses rather than stacks — v95 §4.2.
 *
 * The problem this exists for: Trades at 390px put eight filter selects, a
 * date range, a column picker and two destructive buttons in a vertical
 * column ~1700px tall, so the first trade row was four screens down. Stacking
 * is what a flex-wrap bar does when it runs out of width, and it is the wrong
 * answer for a bar with more than about four controls.
 *
 * Controls are projected by `[slot]` and reparented by CSS, not moved in the
 * DOM: a control that was destroyed and recreated would lose its focus, its
 * open dropdown and any uncommitted text the moment the viewport crossed a
 * breakpoint mid-interaction.
 */
export interface ToolbarControl {
  /** Matches the projected element's `slot` attribute. */
  id: string;
  /** Used in the sheet's heading and for the accessible name. */
  label: string;
  inlineFrom?: Viewport;
  /** Non-default — feeds the badge. See v95 §5 guard 1. */
  active?: boolean;
}

@Component({
  selector: 'sb-toolbar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="toolbar-inline">
      @for (control of inlineControls(); track control.id) {
        <ng-content [select]="'[slot=' + control.id + ']'" />
      }
    </div>

    @if (demoted().length) {
      <button
        type="button"
        class="toolbar-sheet-button"
        [attr.aria-expanded]="open()"
        [attr.aria-label]="sheetLabel()"
        (click)="open.set(!open())"
      >
        Filters
        <span class="count">{{ demoted().length }}</span>
        @if (activeCount()) { <span class="active-dot" [attr.data-count]="activeCount()"></span> }
      </button>
    }

    <div class="toolbar-sheet" [class.open]="open()">
      @for (control of demoted(); track control.id) {
        <ng-content [select]="'[slot=' + control.id + ']'" />
      }
    </div>
  `,
  styles: `
    :host { display: flex; align-items: center; gap: var(--space-10); flex-wrap: wrap; }
    .toolbar-inline { display: flex; align-items: center; gap: var(--space-10); flex-wrap: wrap; min-width: 0; }
    .toolbar-sheet-button { min-height: var(--control-h); display: inline-flex; align-items: center; gap: 6px; }
    .toolbar-sheet { display: none; width: 100%; flex-direction: column; gap: var(--space-10); }
    .toolbar-sheet.open { display: flex; }
    .active-dot::after { content: attr(data-count); color: var(--accent); }
  `,
})
export class Toolbar {
  private readonly viewportService = inject(ViewportService);

  readonly controls = input<ToolbarControl[]>([]);
  /** Test override — jsdom resolves no media query. */
  readonly viewportAt = input<Viewport | null>(null);

  protected readonly open = signal(false);

  private readonly viewport = computed<Viewport>(
    () => this.viewportAt() ?? this.viewportService.viewport(),
  );

  protected readonly inlineControls = computed(() =>
    this.controls().filter((c) => isInline(c.inlineFrom, this.viewport())),
  );

  protected readonly demoted = computed(() => {
    const inline = new Set(this.inlineControls().map((c) => c.id));
    return this.controls().filter((c) => !inline.has(c.id));
  });

  /** Guard 1 (v95 §5): a filter you cannot see that is narrowing your data is
   *  a correctness bug, so the count of ACTIVE demoted controls is surfaced
   *  separately from the count of demoted ones. */
  protected readonly activeCount = computed(
    () => this.demoted().filter((c) => c.active).length,
  );

  protected readonly sheetLabel = computed(() => {
    const active = this.activeCount();
    const total = this.demoted().length;
    return active
      ? `Filters — ${total} hidden, ${active} active`
      : `Filters — ${total} hidden`;
  });
}
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/toolbar.spec.ts`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/toolbar.ts frontend/src/app/ui/toolbar.spec.ts
git commit -m "feat(v95): sb-toolbar -- controls collapse into a sheet instead of stacking"
```

---

### Task B5: The active-filter badge is honest

**Files:**
- Modify: `frontend/src/app/ui/toolbar.ts`
- Test: `frontend/src/app/ui/toolbar.spec.ts`

B4 renders `activeCount`. This task proves it cannot lie, because guard 1 is
the reason the sheet is acceptable at all: hiding an inert control is a layout
choice, hiding an engaged one changes what the numbers on screen mean.

**Interfaces:**
- Consumes: `ToolbarControl.active` (B4).
- Produces: no API change.

- [x] **Step 1: Write the failing test**

Append to `toolbar.spec.ts`:

```ts
describe('sb-toolbar active badge', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.viewportAt.set('sm');
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const button = () => el().querySelector('.toolbar-sheet-button')!;

  it('shows no active marker when every demoted control is at its default', () => {
    expect(el().querySelector('.active-dot')).toBeNull();
    expect(button().getAttribute('aria-label')).toBe('Filters — 2 hidden');
  });

  it('marks the sheet when a demoted control is engaged', () => {
    host.controls.set([
      { id: 'status', label: 'Status' },
      { id: 'ticker', label: 'Ticker', inlineFrom: 'md', active: true },
      { id: 'badge', label: 'Badge', inlineFrom: 'md' },
    ]);
    fixture.detectChanges();
    expect(el().querySelector('.active-dot')).not.toBeNull();
    expect(button().getAttribute('aria-label')).toBe('Filters — 2 hidden, 1 active');
  });

  it('counts only DEMOTED actives — an inline active is already visible', () => {
    host.controls.set([
      { id: 'status', label: 'Status', active: true },
      { id: 'ticker', label: 'Ticker', inlineFrom: 'md' },
      { id: 'badge', label: 'Badge', inlineFrom: 'md' },
    ]);
    fixture.detectChanges();
    expect(el().querySelector('.active-dot')).toBeNull();
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/toolbar.spec.ts`
Expected: the third case may already pass; the `aria-label` cases fail if B4's
string differs. Fix B4's `sheetLabel` to match exactly, not the test.

- [x] **Step 3: Write the implementation**

No new code if B4 is correct. If the assertions fail, the defect is in
`sheetLabel`/`activeCount` — correct those, not the expectations.

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/toolbar.spec.ts`
Expected: PASS, all three.

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/toolbar.ts frontend/src/app/ui/toolbar.spec.ts
git commit -m "test(v95): the toolbar's active-filter badge counts only demoted engaged controls"
```

---

### Task B6: `sb-panel-grid` orders per band

**Files:**
- Modify: `frontend/src/app/ui/panel-grid.ts`
- Create: `frontend/src/app/ui/panel-grid.spec.ts` (if absent; else append)

`PanelGrid` is currently two grid-template rules and a `track` input. It gains
per-viewport ordering so a workspace can lead with different panels at
different widths — which is what the Dashboard needs, and what it currently
does with a hand-rolled `max-width: 720px` block in `dashboard.ts:527`.

**Interfaces:**
- Consumes: `Viewport`, `ViewportService`.
- Produces:
  - `readonly order = input<Partial<Record<Viewport, string[]>> | null>(null)` —
    panel ids, in the order they should appear, per viewport.
  - `readonly viewportAt = input<Viewport | null>(null)`.
  - Children are matched by their `data-panel-id` attribute and ordered with
    the CSS `order` property, so no DOM node moves.

- [x] **Step 1: Write the failing test**

```ts
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, beforeEach, expect, it } from 'vitest';

import { Viewport } from './breakpoints';
import { PanelGrid } from './panel-grid';

@Component({
  imports: [PanelGrid],
  template: `
    <sb-panel-grid [order]="order()" [viewportAt]="viewportAt()">
      <div data-panel-id="positions">P</div>
      <div data-panel-id="performance">Q</div>
      <div data-panel-id="activity">R</div>
    </sb-panel-grid>
  `,
})
class Host {
  readonly viewportAt = signal<Viewport | null>(null);
  readonly order = signal<Partial<Record<Viewport, string[]>> | null>(null);
}

describe('sb-panel-grid ordering', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const orders = () =>
    [...(fixture.nativeElement as HTMLElement).querySelectorAll('[data-panel-id]')]
      .map((n) => (n as HTMLElement).style.order);

  it('sets no order when none is declared', () => {
    expect(orders()).toEqual(['', '', '']);
  });

  it('orders by the band it is in', () => {
    host.order.set({ xs: ['performance', 'positions', 'activity'] });
    host.viewportAt.set('xs');
    fixture.detectChanges();
    // performance first, positions second, activity third
    expect(orders()).toEqual(['1', '0', '2']);
  });

  it('falls back to declaration order in a band with no entry', () => {
    host.order.set({ xs: ['performance', 'positions', 'activity'] });
    host.viewportAt.set('lg');
    fixture.detectChanges();
    expect(orders()).toEqual(['', '', '']);
  });

  it('leaves an unnamed panel after the named ones rather than dropping it', () => {
    host.order.set({ xs: ['activity'] });
    host.viewportAt.set('xs');
    fixture.detectChanges();
    const [positions, performance, activity] = orders();
    expect(Number(activity)).toBeLessThan(Number(positions));
    expect(Number(activity)).toBeLessThan(Number(performance));
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/panel-grid.spec.ts`
Expected: FAIL — `order` is not an input.

- [x] **Step 3: Write the implementation**

Rewrite `panel-grid.ts`, keeping the existing `track` input and styles intact
and adding:

```ts
  readonly order = input<Partial<Record<Viewport, string[]>> | null>(null);
  readonly viewportAt = input<Viewport | null>(null);

  private readonly viewportService = inject(ViewportService);
  private readonly viewport = computed<Viewport>(
    () => this.viewportAt() ?? this.viewportService.viewport(),
  );

  private readonly children = contentChildren<ElementRef<HTMLElement>>('*', { read: ElementRef });

  constructor() {
    /* CSS `order` rather than moving nodes: reordering the DOM would reset
     * scroll position and drop focus every time the viewport crossed a
     * breakpoint, and a panel mid-interaction would jump under the user. */
    effect(() => {
      const declared = this.order()?.[this.viewport()] ?? null;
      for (const ref of this.children()) {
        const element = ref.nativeElement;
        const id = element.dataset['panelId'];
        if (!declared || !id) { element.style.order = ''; continue; }
        const index = declared.indexOf(id);
        // Unnamed panels sort after named ones, in declaration order, rather
        // than vanishing to the front on -1.
        element.style.order = String(index === -1 ? declared.length : index);
      }
    });
  }
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/panel-grid.spec.ts`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/panel-grid.ts frontend/src/app/ui/panel-grid.spec.ts
git commit -m "feat(v95): sb-panel-grid orders panels per viewport band"
```

---

### Task B7: `sb-panel` collapses to a digest

**Files:**
- Modify: `frontend/src/app/ui/panel.ts`
- Test: `frontend/src/app/ui/panel.spec.ts`

Below its floor a panel renders title, one-line digest and a chevron, expanding
in place. The digest is mandatory for a collapsible panel: a panel with nothing
useful to say in one line declares `inlineFrom: 'xs'` and never collapses.

**Interfaces:**
- Consumes: `isInline` (A1), `Viewport`, `ViewportService`.
- Produces:
  - `readonly inlineFrom = input<Viewport | undefined>(undefined)`
  - `readonly digest = input<string | null>(null)`
  - `readonly viewportAt = input<Viewport | null>(null)`
  - `.panel-digest` and `button.panel-toggle` markup.

- [x] **Step 1: Write the failing test**

```ts
describe('sb-panel collapse', () => {
  // Host wires [inlineFrom], [digest], [viewportAt] onto sb-panel and
  // projects a <p class="body">Body</p>.

  it('renders in full above its floor', () => {
    host.inlineFrom.set('md'); host.viewportAt.set('md'); fixture.detectChanges();
    expect(el().querySelector('.body')).not.toBeNull();
    expect(el().querySelector('.panel-digest')).toBeNull();
  });

  it('collapses to its digest below its floor', () => {
    host.inlineFrom.set('md'); host.digest.set('no priced symbols yet');
    host.viewportAt.set('sm'); fixture.detectChanges();
    expect(el().querySelector('.panel-digest')!.textContent)
      .toContain('no priced symbols yet');
    expect(el().querySelector('.body')).toBeNull();
  });

  it('expands in place on tap and keeps the digest out of the way', () => {
    host.inlineFrom.set('md'); host.digest.set('3 open');
    host.viewportAt.set('sm'); fixture.detectChanges();
    (el().querySelector('button.panel-toggle') as HTMLElement).click();
    fixture.detectChanges();
    expect(el().querySelector('.body')).not.toBeNull();
    expect(el().querySelector('button.panel-toggle')!.getAttribute('aria-expanded'))
      .toBe('true');
  });

  it('never collapses without a digest — an empty summary is worse than none', () => {
    host.inlineFrom.set('md'); host.digest.set(null);
    host.viewportAt.set('sm'); fixture.detectChanges();
    expect(el().querySelector('.body')).not.toBeNull();
    expect(el().querySelector('button.panel-toggle')).toBeNull();
  });

  it('keeps the title readable while collapsed', () => {
    host.inlineFrom.set('md'); host.digest.set('3 open');
    host.viewportAt.set('sm'); fixture.detectChanges();
    expect(el().textContent).toContain(host.title());
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/panel.spec.ts`
Expected: FAIL — `inlineFrom` is not an input on `sb-panel`.

- [x] **Step 3: Write the implementation**

Add to `panel.ts`:

```ts
  readonly inlineFrom = input<Viewport | undefined>(undefined);
  /** One line answering the panel's own question. `null` means this panel has
   *  nothing worth saying in one line, and it therefore never collapses —
   *  v95 §4.3. A digest of '—' above a panel with real content is the defect
   *  this rule exists to prevent. */
  readonly digest = input<string | null>(null);
  readonly viewportAt = input<Viewport | null>(null);

  protected readonly expanded = signal(false);

  private readonly viewport = computed<Viewport>(
    () => this.viewportAt() ?? this.viewportService.viewport(),
  );

  protected readonly collapsible = computed(
    () => this.digest() !== null && !isInline(this.inlineFrom(), this.viewport()),
  );

  protected readonly collapsed = computed(
    () => this.collapsible() && !this.expanded(),
  );
```

Template: wrap the projected body in `@if (!collapsed())`, and render
`@if (collapsed())` a `.panel-digest` plus the toggle button carrying
`[attr.aria-expanded]="expanded()"`. When `collapsible()` is true the toggle is
rendered in the header regardless of `expanded`, so it can be closed again.

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/panel.spec.ts`
Expected: PASS. Every existing panel test must also pass — no call site sets
`inlineFrom` yet, so `collapsible()` is false in production.

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/panel.ts frontend/src/app/ui/panel.spec.ts
git commit -m "feat(v95): sb-panel collapses to a one-line digest below its floor"
```

---

### Task B8: A panel never collapses over a problem

**Files:**
- Modify: `frontend/src/app/ui/panel.ts`
- Test: `frontend/src/app/ui/panel.spec.ts`

Guard 2 (v95 §5). A collapsed digest reading `—` above a panel whose data
failed to load, is stale, or is scoped to something unrepresentative is exactly
the defect this repo's UX seat exists to refuse. Such a panel force-expands and
says why.

**Interfaces:**
- Consumes: `collapsible` (B7).
- Produces: `readonly problem = input<string | null>(null)` — a short reason,
  rendered when set; overrides collapse.

- [ ] **Step 1: Write the failing test**

```ts
describe('sb-panel force-expand guard', () => {
  beforeEach(() => {
    host.inlineFrom.set('md'); host.digest.set('3 open'); host.viewportAt.set('sm');
    fixture.detectChanges();
  });

  it('collapses normally when there is no problem', () => {
    expect(el().querySelector('.body')).toBeNull();
  });

  it('force-expands when the data is stale', () => {
    host.problem.set('stale — last updated 18:41');
    fixture.detectChanges();
    expect(el().querySelector('.body')).not.toBeNull();
  });

  it('says what the problem is rather than just opening', () => {
    host.problem.set('stale — last updated 18:41');
    fixture.detectChanges();
    expect(el().textContent).toContain('stale — last updated 18:41');
  });

  it('offers no collapse toggle while the problem stands', () => {
    // Letting the user re-collapse it would put the warning back behind a
    // digest that does not mention it.
    host.problem.set('failed to load');
    fixture.detectChanges();
    expect(el().querySelector('button.panel-toggle')).toBeNull();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/panel.spec.ts`
Expected: FAIL — `problem` is not an input.

- [ ] **Step 3: Write the implementation**

```ts
  /**
   * Why this panel must not be collapsed right now — v95 §5 guard 2.
   *
   * Stale data, a failed load, or a scope that makes the number unrepresentative.
   * Set, the panel force-expands, renders the reason, and drops its toggle:
   * a warning the user can fold back behind a digest that does not mention it
   * is a warning that does not exist.
   */
  readonly problem = input<string | null>(null);
```

and change `collapsible` to:

```ts
  protected readonly collapsible = computed(
    () => this.problem() === null
      && this.digest() !== null
      && !isInline(this.inlineFrom(), this.viewport()),
  );
```

Render `@if (problem(); as reason) { <p class="panel-problem">{{ reason }}</p> }`
above the projected body.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/panel.spec.ts`
Expected: PASS, all of B7's and B8's cases.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/panel.ts frontend/src/app/ui/panel.spec.ts
git commit -m "feat(v95): a panel with stale or failed data force-expands and says why"
```

---

## Phase B exit criteria

- `sb-data-table` splits columns and renders demoted ones in a labelled,
  keyboard-reachable row detail.
- v80 D4's phone-mode tests pass **unmodified**: pinned identity column, sort
  select, `'keeps the table below the breakpoint -- no cards'`.
- `sb-toolbar` exists, collapses below-floor controls into a sheet, and counts
  demoted actives separately from demoted totals.
- `sb-panel-grid` orders by band using CSS `order`, moving no DOM node.
- `sb-panel` collapses to a digest, refuses to collapse without one, and
  force-expands over a problem.
- **No workspace looks different yet.** Every primitive defaults to its
  pre-v95 behaviour when no floor is declared; if any workspace changed
  appearance in this phase, a default is wrong.
