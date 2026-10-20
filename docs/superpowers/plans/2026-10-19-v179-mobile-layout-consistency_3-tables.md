# v179 — Mobile layout consistency, Part 3: compact rows, the row drawer and per-table declarations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-19-v179-mobile-layout-consistency-design.md](../specs/2026-10-19-v179-mobile-layout-consistency-design.md) — §3.1 (compact rows plus a drawer), §4 anti-goals (column reachability, no hand-rolled cards, captions travel), §6a.1, §6a.2, §6a.4, §6a.5, §6a.7, §6b.2, §6b.4, §6b.9 and §7.5.
**Index:** [2026-10-19-v179-mobile-layout-consistency_0-index.md](2026-10-19-v179-mobile-layout-consistency_0-index.md) — Goal, Architecture, **Global Constraints**, **Contracts**, **Parallelisation** and the task ledger live there and bind every task below.

Tasks V179-9..V179-13. Every task runs in the worktree `.claude/worktrees/2026-10-19-v179-mobile-layout-consistency` (created by V179-1). Paths under "Files" are full repo paths; commands run from the worktree root. Parts 1–2 are in place before this part starts: `--font-num`, the floored text tokens, `--hit-min` and the global `.sb-hit` (a transparent centred `::after` of `max(100%, var(--hit-min))`), `--control-h: 44px` under `(pointer: coarse), (max-width: 1023px)`, and the restyled filter row.

**Three things every task here relies on:**

- **jsdom cannot be a phone.** `sb-data-table`'s `cardsAt`/`viewportAt` inputs force phone mode inside `data-table.spec.ts`. A workspace spec cannot reach those inputs, so it overrides `ViewportService` instead, with `phoneViewport()` from `ui/data-table/testing/reachability.ts` (V179-10). `ViewportService` is read only through `viewport()`, `isPhone()` and `isNarrow()` anywhere in the app (`git grep -n "viewportService\.\|viewport\." -- frontend/src/app`), so a stub of those three signals is complete.
- **A compact row is a `<button>`.** Cell templates that hold a link (`sb-row-link` in the Watchlist, ticker-detail and Risk ticker cells) render inside it with `pointer-events: none`, so a tap anywhere on the row does one thing — open the drawer (or emit). The same cell renders live in the drawer, and the drawer's `detailLink` keeps the old destination (spec §6b.4).
- **`rowLabel()` names the drawer.** The drawer heading is the pinned identity column's `value(row)`. A column that renders through a `cell` template only (Watchlist `symbol`, ticker-detail and Risk `ticker`) gains a plain `value` in its own task, so the heading and the row's accessible name read "NVDA", not "row". `value` is ignored for rendering when `cell` is set (`data-table.types.ts`), so nothing on screen changes.

---

# Phase 3 — Compact rows, the row drawer and per-table declarations

### Task V179-9: `ColumnDef.compact` and compact-row rendering; v80 test reversed

**Model:** sonnet — one new pure module plus a template branch in the load-bearing table; the v80 record is reversed deliberately, not deleted.

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.types.ts`
- Create: `frontend/src/app/ui/data-table/compact.ts`
- Create: `frontend/src/app/ui/data-table/compact.spec.ts`
- Modify: `frontend/src/app/ui/data-table/data-table.ts`
- Modify: `frontend/src/app/ui/data-table/data-table.spec.ts`

**Interfaces:**
- Consumes: `--hit-min` and the global `.sb-hit` (V179-2); `--font-num` (V179-1); the existing `DataTable` members `phone`, `renderedColumns`, `inlineColumns`, `shownRows`, `rowKey`, `rowClass`, `text()`, `footerText()`, `rowActivate`.
- Produces (index Contracts, verbatim):
  - `data-table.types.ts`: `export interface CompactSlot { line: 1 | 2; order: number }`, `export type PhoneTap = 'drawer' | 'emit';`, `export interface DetailLink { commands: unknown[]; label: string }`, and `ColumnDef<T>.compact?: CompactSlot`.
  - `compact.ts`: `export interface CompactLines<T> { line1: ColumnDef<T>[]; line2: ColumnDef<T>[] }`, `compactLines<T>(columns, rendered): CompactLines<T>`, `hasCompact<T>(columns, rendered): boolean`, `drawerColumns<T>(columns, rendered): ColumnDef<T>[]`.
  - `DataTable`: `protected readonly compact: Signal<boolean>` (`phone() && hasCompact(columns(), visible())`); a shared `<ng-template #cellTemplate let-col let-row="row">` (the drawer in V179-10 renders through it); `protected onCompactTap(row: T): void` (emits `rowActivate` here; V179-10 adds the `phoneTap` precedence).
  - DOM: `ul.compact-list > li.compact-row > button.compact-hit > .line1 / .line2 > [data-col="<key>"]`, and `.compact-footer [data-col]` for column footers.

**Rules this task encodes (spec §3.1, §6a.1, §6a.7, §6b.9):**
- Compact mode = phone (`cardsAt` or `ViewportService.isPhone()`) **and** at least one *rendered* column declares `compact`. A column the user hid through the `Columns` picker counts as absent, so a table whose compact columns are all hidden falls back to today's scroller rather than an empty row.
- In compact mode there is no `<table>`: no header row (so no header sort buttons and no drag), no ▸ disclosure, no filler rows. The phone sort `<select>` stays above the list and offers every *rendered* sortable column (the grid's inline set no longer exists); the pager stays below. Column footers become one totals line.
- On phone the compact row **replaces** pinned-cell inlining; `inlineFrom` keeps governing tablet and desktop exactly as today.
- Header sort buttons get `sb-hit` so they reach 44px on phone and tablet (§6a.7; V179-2 left this file to this task).

- [ ] **Step 1: Write the failing pure tests**

Create `frontend/src/app/ui/data-table/compact.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { compactLines, drawerColumns, hasCompact } from './compact';
import { ColumnDef } from './data-table.types';

/* v179 §3.1 / §6a.1 -- which rendered column goes on which compact line,
 * and what is left for the row drawer. Pure, so the per-table
 * reachability tests (V179-11..13) can lean on it without a TestBed. */

interface Row { id: string }

const COLUMNS: ColumnDef<Row>[] = [
  { key: 'ticker', header: 'Ticker', compact: { line: 1, order: 1 } },
  { key: 'pnl', header: 'P&L', compact: { line: 1, order: 2 } },
  { key: 'plan', header: 'Plan', compact: { line: 2, order: 1 } },
  { key: 'held', header: 'Held' },
  { key: 'status', header: 'Status', compact: { line: 2, order: 0 } },
  { key: 'actions', header: '' },
];
const keys = (columns: ColumnDef<Row>[]) => columns.map((column) => column.key);

describe('compactLines', () => {
  it('splits the rendered compact columns by line, ordered by slot not by visible order', () => {
    const lines = compactLines(COLUMNS, ['held', 'pnl', 'plan', 'ticker', 'status', 'actions']);
    expect(keys(lines.line1)).toEqual(['ticker', 'pnl']);
    expect(keys(lines.line2)).toEqual(['status', 'plan']);
  });

  it('leaves out a compact column the user hid', () => {
    const lines = compactLines(COLUMNS, ['ticker', 'plan']);
    expect(keys(lines.line1)).toEqual(['ticker']);
    expect(keys(lines.line2)).toEqual(['plan']);
  });

  it('skips a key from a stale saved preference', () => {
    expect(keys(compactLines(COLUMNS, ['ticker', 'gone']).line1)).toEqual(['ticker']);
  });
});

describe('hasCompact', () => {
  it('is true when one rendered column declares a slot', () => {
    expect(hasCompact(COLUMNS, ['held', 'pnl'])).toBe(true);
  });

  it('is false when no column declares one', () => {
    expect(hasCompact([{ key: 'held', header: 'Held' }], ['held'])).toBe(false);
  });

  it('is false when only hidden columns declare one -- the scroller comes back', () => {
    expect(hasCompact(COLUMNS, ['held', 'actions'])).toBe(false);
  });
});

describe('drawerColumns', () => {
  it('is every rendered column not on the compact row, in rendered order', () => {
    expect(keys(drawerColumns(COLUMNS, ['actions', 'ticker', 'held', 'pnl']))).toEqual(['actions', 'held']);
  });

  it('never lists a column the user hid', () => {
    expect(keys(drawerColumns(COLUMNS, ['ticker']))).toEqual([]);
  });

  it('together with the compact row reaches every rendered column exactly once', () => {
    const rendered = ['held', 'pnl', 'plan', 'ticker', 'status', 'actions'];
    const { line1, line2 } = compactLines(COLUMNS, rendered);
    const reached = [...keys(line1), ...keys(line2), ...keys(drawerColumns(COLUMNS, rendered))];
    expect([...reached].sort()).toEqual([...rendered].sort());
  });
});
```

- [ ] **Step 2: Write the failing component tests**

In `frontend/src/app/ui/data-table/data-table.spec.ts`:

(a) Add at the top, above the `@angular/core` import:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

(b) In `describe('DataTable phone mode', …)`, replace the test `'keeps the table below the breakpoint -- no cards'` with:

```ts
  /* v80 D4 said "no cards"; v179 §6b.9 reverses that for a table that
   * declares a compact row, on purpose. A table that declares none -- this
   * Host's columns -- keeps v80's pinned-column table exactly, and this test
   * is that path's record. */
  it('keeps the table below the breakpoint for a table that declares no compact row', () => {
    asPhone(); expect(wrap().classList).toContain('phone'); expect(el().querySelector('table')).not.toBeNull();
    expect(el().querySelector('.compact-list, .cards, .card')).toBeNull(); expect(el().querySelectorAll('tbody tr.row')).toHaveLength(ROWS.length);
  });
```

(c) Append at the end of the file:

```ts
/* -- v179 §3.1 -- compact rows on a phone ------------------------------------ */

interface Trade {
  id: string;
  ticker: string;
  pnl: number | null;
  plan: string;
  held: string;
  strategy: string;
}

const TRADES: Trade[] = [
  { id: 'a', ticker: 'AAPL', pnl: 4.2, plan: '100 → 110 / 95', held: '3d', strategy: 'RSI' },
  { id: 'b', ticker: 'MSFT', pnl: null, plan: '', held: '1d', strategy: 'EMA' },
];

@Component({
  imports: [DataTable],
  template: `
    <ng-template #pnlCell let-row>
      <span class="pnl-rich">{{ row.pnl === null ? '—' : row.pnl + '%' }}</span>
    </ng-template>
    <ng-template #expansion let-row>
      <div class="expansion-body">{{ row.ticker }} detail</div>
    </ng-template>

    <sb-data-table
      [rows]="rows()"
      [columns]="columns()"
      [visible]="visible()"
      [rowKey]="rowKey"
      [sort]="sort()"
      [pagination]="pagination()"
      [expansion]="withExpansion() ? expansionTemplate() : null"
      [cardsAt]="cardsAt()"
      [viewportAt]="viewportAt()"
      (sortChange)="lastSort = $event"
      (rowActivate)="activated.push($event)"
    />
  `,
})
class CompactHost {
  readonly rows = signal<Trade[]>(TRADES);
  readonly visible = signal<string[]>(['ticker', 'pnl', 'plan', 'held', 'strategy']);
  readonly sort = signal<SortSpec | null>(null);
  readonly pagination = signal<PageSpec | null>(null);
  readonly withExpansion = signal(true);
  readonly cardsAt = signal<boolean | null>(true);
  readonly viewportAt = signal<Viewport | null>('xs');

  private readonly pnlCell = viewChild.required<TemplateRef<RowContext<Trade>>>('pnlCell');
  readonly expansionTemplate = viewChild.required<TemplateRef<RowContext<Trade>>>('expansion');

  readonly columns = computed<ColumnDef<Trade>[]>(() => [
    { key: 'ticker', header: 'Ticker', value: (row) => row.ticker, sortable: true, compact: { line: 1, order: 1 } },
    { key: 'pnl', header: 'P&L %', cell: this.pnlCell(), numeric: true, sortable: true, compact: { line: 1, order: 2 } },
    { key: 'plan', header: 'Plan', value: (row) => row.plan, compact: { line: 2, order: 1 } },
    // Sortable but below its floor at xs: the table's inline set leaves it
    // out, the compact sort select must not.
    { key: 'held', header: 'Held', value: (row) => row.held, sortable: true, inlineFrom: 'lg', footer: (rows) => `${rows.length} rows` },
    { key: 'strategy', header: 'Strategy', value: (row) => row.strategy, inlineFrom: 'lg' },
  ]);

  readonly rowKey = (row: Trade) => row.id;
  lastSort: SortSpec | null = null;
  readonly activated: Trade[] = [];
}

const DATA_TABLE_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/data-table/data-table.ts'), 'utf8');

/** The body of the first `<selector> {` rule in data-table.ts's styles. */
function tableRule(selector: string): string {
  const at = DATA_TABLE_SOURCE.indexOf(`${selector} {`);
  return at < 0 ? '' : DATA_TABLE_SOURCE.slice(at, DATA_TABLE_SOURCE.indexOf('}', at));
}

describe('DataTable compact rows (v179 §3.1)', () => {
  let fixture: ComponentFixture<CompactHost>;
  let host: CompactHost;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(CompactHost);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const rowsShown = () => [...el().querySelectorAll('li.compact-row')];
  const lineKeys = (row: Element, line: string) =>
    [...row.querySelectorAll(`.${line} > [data-col]`)].map((cell) => cell.getAttribute('data-col'));

  it('renders compact rows instead of a table when a rendered column declares a slot', () => {
    expect(el().querySelector('ul.compact-list')).not.toBeNull();
    expect(el().querySelector('table, thead')).toBeNull();
    expect(rowsShown()).toHaveLength(TRADES.length);
    expect(rowsShown()[0].querySelector(':scope > button.compact-hit')).not.toBeNull();
  });

  it('puts each declared column on its line, in slot order', () => {
    expect(lineKeys(rowsShown()[0], 'line1')).toEqual(['ticker', 'pnl']);
    expect(lineKeys(rowsShown()[0], 'line2')).toEqual(['plan']);
  });

  it("renders the column's own cell template, not a second renderer", () => {
    expect(rowsShown()[0].querySelector('[data-col="pnl"] .pnl-rich')!.textContent!.trim()).toBe('4.2%');
  });

  it('shows an em dash for a missing value, never an empty line', () => {
    expect(rowsShown()[1].querySelector('[data-col="plan"]')!.textContent!.trim()).toBe('—');
    for (const line of rowsShown()[1].querySelectorAll('.line1, .line2')) {
      expect(line.textContent!.trim()).not.toBe('');
    }
  });

  it('draws no header row, no sort buttons and no disclosure chevron', () => {
    expect(el().querySelector('button.sort, .expander, .detail-toggle')).toBeNull();
  });

  it('offers every sortable rendered column in the phone sort select', () => {
    const options = [...el().querySelectorAll('.phone-sort option')].map((option) => option.textContent!.trim());
    expect(options).toEqual(['Unsorted', 'Ticker ↑', 'Ticker ↓', 'P&L % ↑', 'P&L % ↓', 'Held ↑', 'Held ↓']);
  });

  it('keeps the pager, below the list', () => {
    host.pagination.set({ page: 1, perPage: 2, total: 9 });
    fixture.detectChanges();
    const pager = el().querySelector('sb-pagination')!;
    expect(pager).not.toBeNull();
    expect(pager.compareDocumentPosition(el().querySelector('ul.compact-list')!) &
      Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
  });

  it('turns column footers into one totals line', () => {
    const total = el().querySelector('.compact-footer [data-col="held"]')!;
    expect(total.textContent).toContain('Held');
    expect(total.textContent).toContain('2 rows');
  });

  it('activates the tapped row', () => {
    (rowsShown()[1].querySelector('button.compact-hit') as HTMLElement).click();
    expect(host.activated.map((row) => row.ticker)).toEqual(['MSFT']);
  });

  it('keeps the table at tablet width even when columns declare a slot', () => {
    host.cardsAt.set(false);
    host.viewportAt.set('sm');
    fixture.detectChanges();
    expect(el().querySelector('table')).not.toBeNull();
    expect(el().querySelector('.compact-list')).toBeNull();
  });

  it('falls back to the scroller when the user hid every compact column', () => {
    host.visible.set(['held', 'strategy']);
    fixture.detectChanges();
    expect(el().querySelector('table')).not.toBeNull();
    expect(el().querySelector('.compact-list')).toBeNull();
  });

  it('gives every compact row at least the touch hit area', () => {
    expect(tableRule('.compact-hit')).toContain('min-height: max(var(--row-h), var(--hit-min))');
  });

  it('sets mixed sizes on one line on the text baseline, never centred', () => {
    expect(tableRule('.line1, .line2')).toContain('align-items: baseline');
  });

  it('gives header sort buttons the shared hit area (§6a.7)', () => {
    expect(DATA_TABLE_SOURCE).toContain('<button type="button" class="sort sb-hit"');
  });

  it("records v179's reversal of v80's no-cards decision in the docstring", () => {
    expect(DATA_TABLE_SOURCE).toMatch(/Phone mode below `sm`[\s\S]{0,900}v179/);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/data-table/compact.spec.ts --include src/app/ui/data-table/data-table.spec.ts`
Expected: FAIL — `compact.spec.ts` cannot resolve `./compact`; `CompactHost` does not compile (`compact` is not a `ColumnDef` property); once those exist, every `DataTable compact rows` test fails on a missing `ul.compact-list`.

- [ ] **Step 4: Add the declaration types**

In `frontend/src/app/ui/data-table/data-table.types.ts`, insert above `/** What to show when there is nothing to show. */`:

```ts
/**
 * Where a column sits on the phone compact row -- v179 §3.1, §6a.1.
 *
 * Below `sm` a table with any rendered `compact` column draws each row as
 * two lines (identity and the number a trader checks first, then plan or
 * price context) and puts every other rendered column in a row drawer.
 * `order` sorts within a line; ties keep `visible` order.
 */
export interface CompactSlot {
  line: 1 | 2;
  order: number;
}

/** What a phone compact-row tap does -- v179 §6a.4. `'drawer'` opens the
 *  table's own row drawer; `'emit'` only emits `rowActivate`, for a page
 *  that already owns a drawer for its rows. */
export type PhoneTap = 'drawer' | 'emit';

/** The row drawer's "Open full …" link -- v179 §6a.4. `commands` is a
 *  `routerLink` array; `label` is the whole link text, arrow included
 *  (e.g. 'Open full trade →'). */
export interface DetailLink {
  commands: unknown[];
  label: string;
}
```

In `ColumnDef<T>`, directly after `inlineFrom?: Viewport;`, add:

```ts

  /**
   * The column's place on the phone compact row -- v179 §3.1.
   *
   * Extends the v95 declaration above rather than adding a second column
   * list: on a phone the compact row REPLACES pinned-cell inlining, and
   * `inlineFrom` keeps governing tablet and desktop. Omitted means the
   * column lives in the row drawer on a phone. A table where no rendered
   * column says anything keeps today's scroller.
   */
  compact?: CompactSlot;
```

- [ ] **Step 5: Create the pure helpers**

Create `frontend/src/app/ui/data-table/compact.ts`:

```ts
import { ColumnDef } from './data-table.types';

/**
 * The phone compact row -- spec v179 §3.1, §6a.1.
 *
 * `rendered` is the table's `visible` list: what the user's `Columns` choice
 * shows. Everything here works on that, never on `columns` alone, so a
 * column the user hid is absent from the row AND from the drawer, and
 * "reachable" means exactly what the table would show today.
 */
export interface CompactLines<T> {
  line1: ColumnDef<T>[];
  line2: ColumnDef<T>[];
}

/** `rendered` resolved to definitions, in rendered order; unknown keys (a
 *  stale saved preference) are skipped, as `DataTable.renderedColumns` does. */
function resolve<T>(columns: ColumnDef<T>[], rendered: readonly string[]): ColumnDef<T>[] {
  const byKey = new Map(columns.map((column) => [column.key, column]));
  return rendered
    .map((key) => byKey.get(key))
    .filter((column): column is ColumnDef<T> => column !== undefined);
}

/** Rendered columns on one line, by slot order. `Array.sort` is stable, so
 *  equal orders keep rendered order. */
function onLine<T>(shown: ColumnDef<T>[], line: 1 | 2): ColumnDef<T>[] {
  return shown
    .filter((column) => column.compact?.line === line)
    .sort((a, b) => a.compact!.order - b.compact!.order);
}

export function compactLines<T>(columns: ColumnDef<T>[], rendered: readonly string[]): CompactLines<T> {
  const shown = resolve(columns, rendered);
  return { line1: onLine(shown, 1), line2: onLine(shown, 2) };
}

/** Any rendered column has a slot -- the switch into compact mode. */
export function hasCompact<T>(columns: ColumnDef<T>[], rendered: readonly string[]): boolean {
  return resolve(columns, rendered).some((column) => column.compact !== undefined);
}

/** Rendered, not on the compact row, in rendered order: the drawer's fields. */
export function drawerColumns<T>(columns: ColumnDef<T>[], rendered: readonly string[]): ColumnDef<T>[] {
  return resolve(columns, rendered).filter((column) => column.compact === undefined);
}
```

- [ ] **Step 6: Render compact rows in `sb-data-table`**

All edits in `frontend/src/app/ui/data-table/data-table.ts`.

(a) Imports — below `import { readTablePerPage, writeTablePerPage } from '../table-prefs';` add:

```ts
import { compactLines, hasCompact } from './compact';
```

(b) Header sort button — replace `<button type="button" class="sort" (click)="toggleSort(col)">` with:

```html
                  <button type="button" class="sort sb-hit" (click)="toggleSort(col)">
```

(c) The compact branch — insert this block directly above `      <div class="scroller" tabindex="0">`:

```html
      @if (compact()) {
        <!-- v179 §3.1: two lines per row, the whole row one button. Cells
             render through #cellTemplate, the same template the drawer uses. -->
        <ul class="compact-list">
          @for (row of shownRows(); track rowKey()(row)) {
            <li class="compact-row" [class]="rowClass()(row)">
              <button type="button" class="compact-hit" (click)="onCompactTap(row)">
                @for (line of compactRow(); track line.name) {
                  <span [class]="line.name">
                    @for (col of line.columns; track col.key) {
                      <span class="compact-cell" [class.num]="col.numeric" [attr.data-col]="col.key">
                        <ng-container [ngTemplateOutlet]="cellTemplate" [ngTemplateOutletContext]="{ $implicit: col, row: row }" />
                      </span>
                    }
                  </span>
                }
              </button>
            </li>
          }
        </ul>
        @if (compactFooter().length) {
          <p class="compact-footer">
            @for (col of compactFooter(); track col.key) {
              <span class="compact-total" [attr.data-col]="col.key">
                <span class="sb-label">{{ col.header }}</span>
                <span class="num">{{ footerText(col) }}</span>
              </span>
            }
          </p>
        }
      } @else {
```

and directly after the `      </div>` that closes `.scroller` (the line after `</table>`), add one line:

```html
      }
```

(d) The shared cell template — directly after the `#pagerTemplate` `</ng-template>`, inside the template string, add:

```html

    <!-- One renderer per column (v179 §6a.2): the column's own cell template,
         else its text with the em-dash rule. Compact rows and the row drawer
         both render through this. -->
    <ng-template #cellTemplate let-col let-row="row">
      @if (col.cell; as cell) {
        <ng-container [ngTemplateOutlet]="cell" [ngTemplateOutletContext]="{ $implicit: row }" />
      } @else {
        {{ text(col, row) }}
      }
    </ng-template>
```

(e) Styles — append inside the `styles` string, after the `@container table (max-width: 639px) { … }` block:

```css

    /* v179 §3.1 -- compact rows. The whole row is one button: a tap does one
       thing. A link inside a cell (sb-row-link) would otherwise steal it, so
       links and buttons inside a row take no pointer events here; the same
       cell renders live in the drawer, beside its detail link. */
    .compact-list { margin: 0; padding: 0; list-style: none; }
    .compact-row { border-bottom: 1px solid var(--border); }
    .compact-hit {
      display: grid;
      gap: var(--space-4);
      width: 100%;
      min-height: max(var(--row-h), var(--hit-min));
      padding: var(--space-8) var(--space-10);
      background: none;
      border: 0;
      color: inherit;
      font: inherit;
      font-size: var(--text-table);
      text-align: left;
      cursor: pointer;
    }
    .compact-hit:hover { background: var(--surface-raised); }
    .compact-hit:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
    .compact-hit a, .compact-hit button { pointer-events: none; }
    /* Mixed sizes on one line sit on one baseline (§3.4), never centred. */
    .line1, .line2 {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: var(--space-4) var(--space-10);
      min-width: 0;
    }
    .line2 { color: var(--text-secondary); font-size: var(--text-chip); }
    .compact-cell { min-width: 0; max-width: 100%; overflow-wrap: anywhere; }
    /* The first figure on a line goes to the right edge, the rest follow it:
       identity reads left, the number a trader checks reads right. */
    .compact-cell.num { margin-left: auto; font-family: var(--font-num); font-variant-numeric: tabular-nums; white-space: nowrap; text-align: right; }
    .compact-cell.num ~ .compact-cell.num { margin-left: 0; }
    .compact-footer {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: var(--space-4) var(--space-14);
      margin: 0;
      padding: var(--space-8) var(--space-10);
      border-top: 1px solid var(--border-strong);
    }
    .compact-total { display: inline-flex; align-items: baseline; gap: var(--space-6); }
    .compact-total .num { font-family: var(--font-num); font-weight: 600; color: var(--text); }
```

(f) The docstring — replace the whole comment block that starts `   * Phone mode below `sm` — v80 D4.` (the `/** … */` above `private readonly viewportService = inject(ViewportService);`) with:

```ts
  /**
   * Phone mode below `sm` — v80 D4, narrowed by v179 §3.1.
   *
   * A table that declares a compact slot on any rendered column
   * (`ColumnDef.compact`) renders COMPACT ROWS below `sm`: two lines per
   * row, no header row, the phone sort select and the pager kept, column
   * footers as one totals line, and a tap that opens the row drawer or only
   * emits (`phoneTap`). This reverses v80's "NOT cards" on purpose (spec
   * v179 §6b.9): measured at 390px, the pinned-column table showed two
   * columns and hid the rest behind a thin scrollbar.
   *
   * A table that declares nothing keeps v80's pinned identity column and
   * sort select. The test 'keeps the table below the breakpoint for a table
   * that declares no compact row' is that path's record, so nothing
   * regresses before a table is migrated.
   *
   * Driven by the viewport rather than by an input, so no call site has to
   * remember to ask for it. `cardsAt` keeps its name and type for the same
   * reason it always had them: jsdom does not lay out, so forcing the mode is
   * the only way a test can reach it.
   */
```

(g) Class members — directly after the `phone` computed (`protected readonly phone = computed(…);`), add:

```ts

  /** v179 §3.1: phone, and something rendered declares a slot. Reads
   *  `visible`, so hiding every compact column brings the scroller back. */
  protected readonly compact = computed(
    () => this.phone() && hasCompact(this.columns(), this.visible()),
  );

  /** The compact row's non-empty lines, named for their CSS class. */
  protected readonly compactRow = computed(() => {
    const { line1, line2 } = compactLines(this.columns(), this.visible());
    return [
      { name: 'line1', columns: line1 },
      { name: 'line2', columns: line2 },
    ].filter((line) => line.columns.length > 0);
  });

  /** Footers in compact mode: every rendered column that has one -- there
   *  is no inline set to restrict them to. */
  protected readonly compactFooter = computed(() =>
    this.rows().length > 0 ? this.renderedColumns().filter((column) => column.footer) : [],
  );

  /** A compact-row tap. V179-10 routes it through `phoneTap`. */
  protected onCompactTap(row: T): void {
    this.rowActivate.emit(row);
  }
```

(h) The phone sort select — replace the `sortOptions` computed and the comment above it with:

```ts
  /* Reads the inline set, so the phone sort select never offers a column the
   * grid is not drawing -- and, in compact mode (v179 §6a.7), every rendered
   * column, because there is no grid and the select is the only sort control. */
  protected readonly sortOptions = computed(() => (this.compact() ? this.renderedColumns() : this.inlineColumns())
    .filter((column) => column.sortable)
    .flatMap((column) => [
      { value: `${column.key}:asc`, label: `${column.header} ↑` },
      { value: `${column.key}:desc`, label: `${column.header} ↓` },
    ]));
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/data-table/compact.spec.ts --include src/app/ui/data-table/data-table.spec.ts --include src/app/ui/data-table/data-table.client-paging.spec.ts`
Expected: PASS, `0 failed`. Every pre-existing `DataTable` test passes unchanged except the one rewritten in Step 2(b) — none of their hosts declares `compact`.

Then the guards that read `ui/` sources: `cd frontend && npx ng test --watch=false --include src/app/ui/hit-area.spec.ts --include src/app/ui/parity.spec.ts --include src/app/ui/priority.spec.ts`
Expected: PASS (no new touch media query was added; `compact.ts` declares no selector, so `gallery.spec.ts`'s every-primitive check is unaffected).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/ui/data-table/data-table.types.ts frontend/src/app/ui/data-table/compact.ts frontend/src/app/ui/data-table/compact.spec.ts
git commit -m "feat(ui): ColumnDef.compact and the pure compact-row helpers (v179 §3.1)"
git add frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/data-table/data-table.spec.ts
git commit -m "feat(ui): sb-data-table renders declared compact rows below sm; v80 no-cards narrowed to undeclared tables (v179 §6b.9)"
```

---

### Task V179-10: Generic row drawer, `phoneTap` precedence, `detailLink`, gallery demo

**Model:** sonnet — wires the existing `sb-drawer` into the table with one precedence rule; the reachability helpers every later table test uses.

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.ts`
- Modify: `frontend/src/app/ui/data-table/data-table.spec.ts`
- Create: `frontend/src/app/ui/data-table/testing/reachability.ts`
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts`
- Modify: `frontend/src/app/workspaces/gallery/gallery.spec.ts`

**Interfaces:**
- Consumes: V179-9's `compact`, `compactLines`, `drawerColumns`, `#cellTemplate`, `onCompactTap`, `PhoneTap`, `DetailLink`; `sb-drawer` (`Drawer`, `ui/layout.ts`: `open`, `heading`, `closed`; body mounted only while open); `installDialogPolyfill` (`app/testing/dialog-polyfill.ts`).
- Produces (index Contracts, verbatim): `phoneTap = input<PhoneTap>('drawer')`, `detailLink = input<((row: T) => DetailLink | null) | null>(null)`, `protected readonly drawerRow = signal<T | null>(null)`; DOM `sb-drawer.row-drawer > dl.drawer-fields > div[data-col]` (`dt` label, `dd` value), the `expansion` template after the `dl` in `.drawer-expansion`, `a.drawer-detail-link`; `testing/reachability.ts`: `compactKeys(root: ParentNode): string[]`, `drawerKeys(root: ParentNode): string[]`, `openRowDrawer(root: HTMLElement, index?: number): void`.
- Produces (added here, not in the index's Contracts; consumed by V179-11..13 and free for Part 4): `phoneViewport(): Provider` in the same `testing/reachability.ts` — a `ViewportService` stub reading as a phone, for workspace specs that cannot reach `cardsAt`.

**Rules (spec §3.1, §6a.2, §6a.4, §6a.5):** a compact-row tap opens the table's own drawer when `phoneTap` is `'drawer'` (the default) and **only** emits `rowActivate` when it is `'emit'` — never both, so one tap never opens two drawers. Tablet and desktop rows keep emitting `rowActivate` exactly as today. The drawer lists every rendered column not on the compact row as label/value pairs through `#cellTemplate`, then the call site's `expansion` template (it replaces the ▸ disclosure on phone), then the detail link. It is component state: it closes on Escape, backdrop tap and × (all through `sb-drawer`'s `closed`), on a page change, on any router navigation, and when the viewport leaves compact mode.

- [ ] **Step 1: Write the reachability helpers**

Create `frontend/src/app/ui/data-table/testing/reachability.ts`:

```ts
import { Provider, signal } from '@angular/core';

import { Viewport, ViewportService } from '../../breakpoints';

/**
 * Column reachability on a phone, read off the DOM -- spec v179 §7.5.
 *
 * Each migrated table's spec asserts that its compact row plus its row
 * drawer show every column the table shows today. These read the
 * `[data-col]` keys `sb-data-table` stamps, so that test stays a few lines.
 * Pass the `sb-data-table` element (or anything containing only one table)
 * as `root`.
 */

function keysIn(root: ParentNode, selector: string): string[] {
  return [...new Set([...root.querySelectorAll(selector)].map((el) => el.getAttribute('data-col') ?? ''))];
}

/** The first compact row's column keys, line 1 then line 2. */
export function compactKeys(root: ParentNode): string[] {
  const row = root.querySelector('li.compact-row');
  return row ? keysIn(row, '.line1 > [data-col], .line2 > [data-col]') : [];
}

/** The open row drawer's column keys, in drawer order. */
export function drawerKeys(root: ParentNode): string[] {
  return keysIn(root, 'sb-drawer.row-drawer dl.drawer-fields > [data-col]');
}

/** Taps compact row `index`. Run change detection afterwards. */
export function openRowDrawer(root: HTMLElement, index = 0): void {
  const hits = root.querySelectorAll<HTMLButtonElement>('li.compact-row > button.compact-hit');
  const hit = hits[index];
  if (!hit) throw new Error(`no compact row at index ${index} (found ${hits.length})`);
  hit.click();
}

/** A `ViewportService` that reads as a phone. jsdom never matches a media
 *  query, and a workspace spec cannot reach `sb-data-table`'s `cardsAt`;
 *  the app reads the service only through these three signals. */
export function phoneViewport(): Provider {
  return {
    provide: ViewportService,
    useValue: { viewport: signal<Viewport>('xs'), isPhone: signal(true), isNarrow: signal(true) },
  };
}
```

- [ ] **Step 2: Write the failing drawer tests**

In `frontend/src/app/ui/data-table/data-table.spec.ts`:

(a) Add imports beside the existing ones:

```ts
import { By } from '@angular/platform-browser';
import { Router, provideRouter } from '@angular/router';

import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { DetailLink, PhoneTap } from './data-table.types';
import { compactKeys, drawerKeys, openRowDrawer } from './testing/reachability';
```

(b) In `CompactHost`'s template add two bindings to `<sb-data-table …>`, after `[viewportAt]="viewportAt()"`:

```html
      [phoneTap]="phoneTap()"
      [detailLink]="detailLink()"
```

and to the class, after `readonly viewportAt = …`:

```ts
  readonly phoneTap = signal<PhoneTap>('drawer');
  readonly detailLink = signal<((row: Trade) => DetailLink | null) | null>(null);
```

(c) In `describe('DataTable compact rows (v179 §3.1)', …)`, delete the test `'activates the tapped row'` (V179-9's interim behaviour; the precedence tests below replace it), and change that describe's `beforeEach` providers to `[provideZonelessChangeDetection(), provideRouter([])]`.

(d) Append at the end of the file:

```ts
describe('DataTable row drawer (v179 §3.1, §6a.4)', () => {
  let fixture: ComponentFixture<CompactHost>;
  let host: CompactHost;

  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] });
    fixture = TestBed.createComponent(CompactHost);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const dialog = () => el().querySelector('sb-drawer.row-drawer dialog') as HTMLDialogElement | null;
  function open(index = 0) {
    openRowDrawer(el(), index);
    fixture.detectChanges();
  }

  it('opens its own drawer on a tap, without emitting rowActivate', () => {
    open(1);
    expect(dialog()!.open).toBe(true);
    expect(el().querySelector('sb-drawer.row-drawer h2')!.textContent!.trim()).toBe('MSFT');
    expect(host.activated).toEqual([]);
  });

  it('lists every rendered column not on the compact row, labelled, through its own cell', () => {
    open();
    expect(drawerKeys(el())).toEqual(['held', 'strategy']);
    const labels = [...el().querySelectorAll('dl.drawer-fields dt')].map((dt) => dt.textContent!.trim());
    expect(labels).toEqual(['Held', 'Strategy']);
    expect(el().querySelector('[data-col="strategy"] dd')!.textContent!.trim()).toBe('RSI');
  });

  it('reaches every rendered column between the compact row and the drawer (§7.5)', () => {
    open();
    expect([...compactKeys(el()), ...drawerKeys(el())].sort()).toEqual([...host.visible()].sort());
  });

  it('keeps a column the user hid out of the drawer too', () => {
    host.visible.set(['ticker', 'pnl', 'plan', 'held']);
    fixture.detectChanges();
    open();
    expect(drawerKeys(el())).toEqual(['held']);
  });

  it("renders the call site's expansion after the fields -- the drawer replaces the disclosure", () => {
    open();
    expect(el().querySelector('.drawer-expansion .expansion-body')!.textContent!.trim()).toBe('AAPL detail');
  });

  it('links to the detail page when the table has one', () => {
    host.detailLink.set((row) => ({ commands: ['/trades', row.id], label: 'Open full trade →' }));
    fixture.detectChanges();
    open();
    const link = el().querySelector('a.drawer-detail-link') as HTMLAnchorElement;
    expect(link.textContent!.trim()).toBe('Open full trade →');
    expect(link.getAttribute('href')).toBe('/trades/a');
  });

  it('shows no link for a table without a detail page', () => {
    open();
    expect(el().querySelector('a.drawer-detail-link')).toBeNull();
  });

  it("only emits under phoneTap 'emit', and renders no drawer of its own", () => {
    host.phoneTap.set('emit');
    fixture.detectChanges();
    open(1);
    expect(host.activated.map((row) => row.ticker)).toEqual(['MSFT']);
    expect(el().querySelector('sb-drawer.row-drawer')).toBeNull();
  });

  it('closes on a page change', () => {
    host.pagination.set({ page: 1, perPage: 2, total: 9 });
    fixture.detectChanges();
    open();
    const table = fixture.debugElement.query(By.directive(DataTable)).componentInstance as unknown as { onPage(page: number): void };
    table.onPage(2);
    fixture.detectChanges();
    expect(dialog()?.open ?? false).toBe(false);
  });

  it('closes on navigation', async () => {
    open();
    await TestBed.inject(Router).navigateByUrl('/elsewhere').catch(() => false);
    fixture.detectChanges();
    expect(dialog()?.open ?? false).toBe(false);
  });

  it('closes when the viewport leaves compact mode', () => {
    open();
    host.cardsAt.set(false);
    host.viewportAt.set('md');
    fixture.detectChanges();
    expect(dialog()?.open ?? false).toBe(false);
  });

  it('still emits rowActivate from a table row at tablet width', () => {
    host.cardsAt.set(false);
    host.viewportAt.set('md');
    fixture.detectChanges();
    (el().querySelectorAll('tbody tr.row')[0] as HTMLElement).click();
    expect(host.activated.map((row) => row.ticker)).toEqual(['AAPL']);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/data-table/data-table.spec.ts`
Expected: FAIL — `phoneTap`/`detailLink` are not inputs of `sb-data-table` (template compile error); once added, the drawer tests fail on a missing `sb-drawer.row-drawer`.

- [ ] **Step 4: Add the drawer to `sb-data-table`**

All edits in `frontend/src/app/ui/data-table/data-table.ts`.

(a) Imports — add:

```ts
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationStart, Router, RouterLink } from '@angular/router';
import { filter } from 'rxjs';

import { Drawer } from '../layout';
```

change `import { compactLines, hasCompact } from './compact';` to `import { compactLines, drawerColumns, hasCompact } from './compact';`, and add `DetailLink` and `PhoneTap` to the `./data-table.types` import list. In `@Component`, `imports` becomes `[NgTemplateOutlet, EmptyStateComponent, PaginationComponent, Drawer, RouterLink]`.

(b) Template — directly after the closing `</div>` of `.wrap` (before `<ng-template #pagerTemplate …>`), add. It sits outside `.wrap` on purpose: `.wrap[aria-busy]` sets `pointer-events: none`, which would freeze an open drawer during a refetch. It mounts only in compact mode (or while a row is still open, so leaving compact mode closes it through `closed` before it unmounts): a desktop table carries no `<dialog>`.

```html

    <!-- v179 §3.1 / §6a.4: the generic row drawer -- every rendered column the
         compact row does not show, through the same #cellTemplate, then the
         call site's expansion, then the detail link. Component state only. -->
    @if (phoneTap() === 'drawer' && (compact() || drawerRow() !== null)) {
      <sb-drawer class="row-drawer" [open]="drawerRow() !== null && compact()" [heading]="drawerHeading()"
                 (closed)="drawerRow.set(null)">
        @if (drawerRow(); as row) {
          <dl class="drawer-fields">
            @for (col of drawerFields(); track col.key) {
              <div class="drawer-field" [attr.data-col]="col.key">
                <dt class="sb-label">{{ col.header || 'Actions' }}</dt>
                <dd [class.num]="col.numeric">
                  <ng-container [ngTemplateOutlet]="cellTemplate" [ngTemplateOutletContext]="{ $implicit: col, row: row }" />
                </dd>
              </div>
            }
          </dl>
          @if (expansion(); as expansionTemplate) {
            <div class="drawer-expansion">
              <ng-container [ngTemplateOutlet]="expansionTemplate" [ngTemplateOutletContext]="{ $implicit: row }" />
            </div>
          }
          @if (drawerLink(); as link) {
            <a class="drawer-detail-link" [routerLink]="link.commands" (click)="drawerRow.set(null)">{{ link.label }}</a>
          }
        }
      </sb-drawer>
    }
```

(c) Styles — append after V179-9's compact block:

```css

    /* The row drawer: label/value pairs on one baseline per pair. */
    .drawer-fields {
      display: grid;
      grid-template-columns: max-content minmax(0, 1fr);
      align-items: baseline;
      gap: var(--space-6) var(--space-14);
      margin: 0;
    }
    .drawer-field { display: contents; }
    .drawer-field dd { min-width: 0; margin: 0; overflow-wrap: anywhere; }
    .drawer-field dd.num { font-family: var(--font-num); font-variant-numeric: tabular-nums; }
    .drawer-expansion { margin-top: var(--space-14); }
    .drawer-detail-link {
      display: inline-flex;
      align-items: center;
      min-height: var(--control-h);
      margin-top: var(--space-14);
      color: var(--accent);
    }
```

(d) Class members — directly after V179-9's `compactFooter` computed, add:

```ts

  /**
   * What a phone compact-row tap does -- v179 §6a.4. `'drawer'` opens this
   * table's own row drawer; `'emit'` only emits `rowActivate`, for a page
   * that already owns a drawer for its rows (Research ledger, Dashboard
   * positions). Never both: one tap never opens two drawers. Tablet and
   * desktop rows are unaffected and emit `rowActivate` as before.
   */
  readonly phoneTap = input<PhoneTap>('drawer');
  /** The drawer's "Open full …" link, or null for a table with no detail
   *  page (Risk, Research registry). */
  readonly detailLink = input<((row: T) => DetailLink | null) | null>(null);

  /** The row the drawer shows. Component state, never the URL (§6a.5). */
  protected readonly drawerRow = signal<T | null>(null);
  protected readonly drawerFields = computed(() => drawerColumns(this.columns(), this.visible()));
  protected readonly drawerHeading = computed(() => {
    const row = this.drawerRow();
    return row === null ? '' : this.rowLabel(row);
  });
  protected readonly drawerLink = computed(() => {
    const row = this.drawerRow();
    const link = this.detailLink();
    return row === null || link === null ? null : link(row);
  });
```

and replace V179-9's `onCompactTap` with:

```ts
  /** A compact-row tap: the drawer, or only the event (`phoneTap`). */
  protected onCompactTap(row: T): void {
    if (this.phoneTap() === 'emit') {
      this.rowActivate.emit(row);
      return;
    }
    this.drawerRow.set(row);
  }
```

(e) Close on page change — make `onPage` start with `this.drawerRow.set(null);`:

```ts
  protected onPage(page: number): void {
    this.drawerRow.set(null);
    if (this.clientPaging() === null) this.pageChange.emit(page);
    else this.requestedPage.set(page);
  }
```

(f) Close on navigation — at the end of the existing `constructor() { … }` body, after the spinner `effect`, add:

```ts

    // v179 §6a.5: a navigation closes the row drawer. Router is providedIn
    // root, so this needs no provideRouter in a test that never navigates.
    inject(Router).events
      .pipe(filter((event) => event instanceof NavigationStart), takeUntilDestroyed())
      .subscribe(() => this.drawerRow.set(null));
```

(The viewport case needs no code: `[open]` is `drawerRow() !== null && compact()`, so leaving compact mode closes the dialog, whose `closed` clears `drawerRow`.)

- [ ] **Step 5: Run the table tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/data-table/data-table.spec.ts --include src/app/ui/data-table/compact.spec.ts --include src/app/ui/data-table/data-table.client-paging.spec.ts --include src/app/ui/layout.spec.ts`
Expected: PASS, `0 failed`.

- [ ] **Step 6: Gallery demo — failing test first**

Append to `frontend/src/app/workspaces/gallery/gallery.spec.ts` (add `import { installDialogPolyfill } from '../../testing/dialog-polyfill';` and `import { compactKeys, drawerKeys, openRowDrawer } from '../../ui/data-table/testing/reachability';` at the top):

```ts
describe('the gallery shows compact rows (v179 §3.1)', () => {
  it('renders a compact-row table whose tap opens the row drawer', () => {
    installDialogPolyfill();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] });
    const fixture = TestBed.createComponent(Gallery);
    fixture.detectChanges();
    const table = (fixture.nativeElement as HTMLElement).querySelector('.compact-demo sb-data-table') as HTMLElement;
    expect(table.querySelectorAll('li.compact-row')).toHaveLength(2);
    openRowDrawer(table);
    fixture.detectChanges();
    expect([...compactKeys(table), ...drawerKeys(table)].sort()).toEqual(['note', 'outcome', 'pnl', 'ticker']);
  });
});
```

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/gallery/gallery.spec.ts`
Expected: FAIL — `.compact-demo` does not exist.

- [ ] **Step 7: Add the gallery panel**

In `frontend/src/app/workspaces/gallery/gallery.ts`, directly above `<sb-section-head [heading]="'Content priority (v95)'" [level]="2" />`, add:

```html
    <!-- -- v179: compact rows and the row drawer, forced via cardsAt ------- -->
    <sb-section-head [heading]="'Compact rows and row drawer (v179)'" [level]="2" />
    <sb-panel heading="Phone table -- spec §3.1" [flush]="true" class="compact-demo">
      <p class="section-help">
        Below 640px a table that declares compact slots shows each row as two
        lines; a tap opens every other column in a drawer.
      </p>
      <sb-data-table
        [rows]="tableRows"
        [columns]="compactColumns"
        [visible]="['ticker', 'pnl', 'note', 'outcome']"
        [rowKey]="rowKey"
        [cardsAt]="true"
        phoneTap="drawer"
      />
    </sb-panel>

```

and in the class, after `priorityColumns`:

```ts
  /** v179: the same rows, declared for the phone compact row. */
  protected readonly compactColumns: ColumnDef<GalleryRow>[] = [
    { key: 'ticker', header: 'Ticker', value: (row) => row.ticker, compact: { line: 1, order: 1 } },
    { key: 'pnl', header: 'P&L', value: (row) => row.pnl, numeric: true, compact: { line: 1, order: 2 } },
    { key: 'note', header: 'Note', value: () => 'Plan or price context', compact: { line: 2, order: 1 } },
    { key: 'outcome', header: 'Outcome', value: (row) => (row.pnl >= 0 ? 'Winner' : 'Loser') },
  ];
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/gallery/gallery.spec.ts --include src/app/ui/data-table/data-table.spec.ts`
Expected: PASS, `0 failed`.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/data-table/data-table.spec.ts frontend/src/app/ui/data-table/testing/reachability.ts
git commit -m "feat(ui): sb-data-table row drawer with phoneTap precedence and detailLink; reachability test helpers (v179 §6a.4)"
git add frontend/src/app/workspaces/gallery/gallery.ts frontend/src/app/workspaces/gallery/gallery.spec.ts
git commit -m "feat(gallery): compact rows and the row drawer (v179)"
```

---

### Task V179-11: Trades and Dashboard-positions compact declarations (money floor)

**Model:** sonnet — five slot declarations on the shared trade columns plus the Trades call site; the money floor and the null row are the review risks.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.columns.ts`
- Modify: `frontend/src/app/workspaces/trades/trades.columns.spec.ts`
- Modify: `frontend/src/app/workspaces/trades/trades.ts`
- Modify: `frontend/src/app/workspaces/trades/trades.spec.ts`

**Interfaces:**
- Consumes: `ColumnDef.compact`, `DetailLink`, `compactLines`, `drawerColumns` (V179-9); `phoneTap`, `detailLink`, `compactKeys`, `drawerKeys`, `openRowDrawer`, `phoneViewport` (V179-10); `deriveOpenVisible` (`workspaces/dashboard/dashboard.helpers.ts:46`).
- Produces: `compact` slots on `tradeColumns()` — `ticker {1,1}`, `direction {1,2}`, `pnl_pct {1,3}`, `plan {2,1}`, `status {2,2}`. The Dashboard's `sb-positions-table` renders `tradeColumns()` too (`dashboard.ts:130`, `DASHBOARD_COLUMNS`), so its compact rows come from this declaration; V179-16 sets its `phoneTap` to `'emit'`. Until then a Dashboard phone tap opens the generic drawer — an acceptable interim, as nothing is pushed before V179-21.

**Field choice (spec §6 "left to the builder", §3.1 money floor).** Line 1: identity, direction, then P&L — the one number a trader opens a phone for; the `pnl_pct` cell renders the percentage **and** the amount (`trades.ts` `#pnlCell`, `sb-pnl-cell` on the Dashboard). Line 2: the plan cell (entry or trigger → target / **stop**, with the rise/drop percentages) and the status. So P&L in money and the stop distance are on the row, never only behind a tap. The Dashboard omits `direction` (`DASHBOARD_OMITS_DIRECTION`) and its Cancelled tab drops `pnl_pct` — those rows simply show fewer compact cells. Everything else (`#`, Now, R, Held, Opened, Closed, Confidence, actions, picker-added columns) is in the drawer, with the row actions and Trades' expansion template.

- [ ] **Step 1: Write the failing pure tests**

Append to `frontend/src/app/workspaces/trades/trades.columns.spec.ts` (add `import { compactLines, drawerColumns } from '../../ui/data-table/compact';` and `import { deriveOpenVisible } from '../dashboard/dashboard.helpers';` to the imports):

```ts
describe('Trades compact row -- v179 §3.1', () => {
  const columns = tradeColumns();
  const keys = (list: { key: string }[]) => list.map((column) => column.key);
  const SETS: [string, string[]][] = [
    ['Trades, phone compact', [...PHONE_COMPACT_COLUMNS, ...PINNED_COLUMNS]],
    ['Trades, full', [...FULL_COLUMNS, ...PINNED_COLUMNS]],
    ['Dashboard open positions', deriveOpenVisible([...PHONE_COMPACT_COLUMNS, ...PINNED_COLUMNS])],
  ];

  it('leads line 1 with identity, direction and P&L; line 2 with the plan and status', () => {
    const { line1, line2 } = compactLines(columns, FULL_COLUMNS);
    expect(keys(line1)).toEqual(['ticker', 'direction', 'pnl_pct']);
    expect(keys(line2)).toEqual(['plan', 'status']);
  });

  it('declares a slot on those five columns only -- the rest is one tap away', () => {
    expect(keys(columns.filter((column) => column.compact)).sort()).toEqual(['direction', 'plan', 'pnl_pct', 'status', 'ticker']);
  });

  it.each(SETS)('%s: P&L (with its amount) and the plan (with its stop) stay on the row', (_, shown) => {
    const { line1, line2 } = compactLines(columns, shown);
    expect(keys([...line1, ...line2])).toEqual(expect.arrayContaining(['pnl_pct', 'plan']));
  });

  it.each(SETS)('%s: the row and the drawer reach every rendered column', (_, shown) => {
    const { line1, line2 } = compactLines(columns, shown);
    const reached = [...keys(line1), ...keys(line2), ...keys(drawerColumns(columns, shown))];
    expect([...reached].sort()).toEqual([...shown].sort());
  });
});
```

- [ ] **Step 2: Write the failing component tests**

Append to `frontend/src/app/workspaces/trades/trades.spec.ts` (add `import { installDialogPolyfill } from '../../testing/dialog-polyfill';` and `import { compactKeys, drawerKeys, openRowDrawer, phoneViewport } from '../../ui/data-table/testing/reachability';` to the imports):

```ts
/* -- v179 §3.1 -- Trades on a phone: compact rows and the row drawer ------ */

function renderPhone(items: TradeRow[]): ComponentFixture<Trades> {
  installDialogPolyfill();
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      TradesStore,
      { provide: ConnectionStore, useValue: connectionStub },
      { provide: PreferencesStore, useValue: preferencesStub },
      phoneViewport(),
    ],
  });
  const fixture = TestBed.createComponent(Trades);
  fixture.detectChanges();
  patchState(unprotected(TestBed.inject(TradesStore)), {
    data: { items, total: items.length, page: 1, per_page: 20 },
    query: { page: 1, per_page: 20 },
  });
  fixture.detectChanges();
  return fixture;
}

const tradesTable = (fixture: ComponentFixture<Trades>) =>
  (fixture.nativeElement as HTMLElement).querySelector('sb-data-table') as HTMLElement;

describe('Trades on a phone (v179 §3.1)', () => {
  it('reaches every visible column between the compact row and the drawer (§7.5)', () => {
    const fixture = renderPhone([row({})]);
    openRowDrawer(tradesTable(fixture));
    fixture.detectChanges();
    const shown = (fixture.componentInstance as unknown as { visible: () => string[] }).visible();
    expect([...compactKeys(tradesTable(fixture)), ...drawerKeys(tradesTable(fixture))].sort()).toEqual([...shown].sort());
  });

  it('keeps the P&L amount and the stop on the compact row (money floor)', () => {
    const table = tradesTable(renderPhone([row({ realized_pnl_amount: 50, stop_loss: 95 })]));
    expect(table.querySelector('.line1 > [data-col="pnl_pct"]')!.textContent).toContain('50.00');
    expect(table.querySelector('.line2 > [data-col="plan"] .stop')!.textContent).toContain('95.00');
  });

  it('shows a PENDING row with no fill as em dashes, never NaN, undefined or an empty line', () => {
    const pending = row({
      id: 'p1', status: 'PENDING', status_label: 'PENDING', entry: null, stop_loss: null, target: null,
      exit_price: null, pnl_pct: null, realized_pnl_amount: null, r_multiple: null, shares: null, trigger_price: 101,
    });
    const compactRow = tradesTable(renderPhone([pending])).querySelector('li.compact-row')!;
    expect(compactRow.textContent).not.toMatch(/NaN|undefined|null/);
    for (const line of compactRow.querySelectorAll('.line1, .line2')) expect(line.textContent!.trim()).not.toBe('');
    expect(compactRow.querySelector('[data-col="pnl_pct"]')!.textContent).toContain('—');
  });

  it('links the drawer to the full trade page and does not navigate on the tap', () => {
    const fixture = renderPhone([row({ id: 't9' })]);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate');
    openRowDrawer(tradesTable(fixture));
    fixture.detectChanges();
    const link = tradesTable(fixture).querySelector('a.drawer-detail-link')!;
    expect(link.textContent!.trim()).toBe('Open full trade →');
    expect(link.getAttribute('href')).toBe('/trades/t9');
    expect(navigate).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/trades.columns.spec.ts --include src/app/workspaces/trades/trades.spec.ts`
Expected: FAIL — no column declares `compact` (line keys `[]`; the phone render still draws a `<table>`, so `li.compact-row` is null); no `a.drawer-detail-link`.

- [ ] **Step 4: Declare the compact row**

In `frontend/src/app/workspaces/trades/trades.columns.ts`, append to the "Column floors" comment above `tradeColumns` (before its closing `*/`):

```ts
 *
 * v179 §3.1 -- the phone compact row. Below sm a phone shows each trade as
 * two lines: ticker, direction and P&L % (whose cell carries the amount);
 * then the plan (with its stop) and the status. That keeps money and the
 * stop on the row (§3.1 money floor). Every other rendered column, the row
 * actions and the expansion are in the row drawer. `inlineFrom` above keeps
 * governing tablet and desktop.
```

and add the slots to five entries (only the `compact` property is new on each line):

```ts
    { key: 'status', header: 'Status', sortable: true, inlineFrom: 'md', compact: { line: 2, order: 2 } },
    { key: 'ticker', header: 'Ticker', value: (row) => row.ticker, sortable: true, inlineFrom: 'xs', compact: { line: 1, order: 1 } },
    { key: 'pnl_pct', header: 'P&L %', numeric: true, sortable: true, inlineFrom: 'xs', compact: { line: 1, order: 3 } },
    { key: 'direction', header: 'Direction', width: '3.5rem', inlineFrom: 'sm', compact: { line: 1, order: 2 } },
    { key: 'plan', header: 'Plan', width: '12rem', inlineFrom: 'xs', compact: { line: 2, order: 1 } },
```

- [ ] **Step 5: Give Trades its drawer link**

In `frontend/src/app/workspaces/trades/trades.ts`:

- change the import at line 37 to `import { ColumnDef, DetailLink, SortSpec } from '../../ui/data-table/data-table.types';`;
- in the main `<sb-data-table …>` (the one with `(rowActivate)="open($event)"`), add after `[expansion]="expansionTemplate()"`:

```html
        phoneTap="drawer"
        [detailLink]="tradeLink"
```

- below `protected open(row: TradeRow): void { … }`, add:

```ts
  /** v179 §6b.4: on a phone a tap opens the row drawer instead of `open()`;
   *  this link keeps the old destination. Tablet and desktop still navigate
   *  through `rowActivate` → `open()`. */
  protected readonly tradeLink = (row: TradeRow): DetailLink => ({
    commands: ['/trades', row.id],
    label: 'Open full trade →',
  });
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/trades.columns.spec.ts --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: PASS, `0 failed`. The Dashboard specs run at jsdom's desktop width, so their tables are unchanged.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/workspaces/trades/trades.columns.ts frontend/src/app/workspaces/trades/trades.columns.spec.ts frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/trades/trades.spec.ts
git commit -m "feat(trades): phone compact row keeps P&L amount and stop on the row; drawer links to the full trade (v179 §3.1)"
```

---

### Task V179-12: Watchlist and ticker-detail compact declarations

**Model:** sonnet — slot declarations and one drawer link on two call sites, each with a reachability test.

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts`
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`
- Modify: `frontend/src/app/workspaces/watchlist/ticker-detail.ts`
- Modify: `frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts`

**Interfaces:**
- Consumes: `ColumnDef.compact`, `DetailLink` (V179-9); `phoneTap`, `detailLink`, `compactKeys`, `drawerKeys`, `openRowDrawer`, `phoneViewport` (V179-10).
- Produces: nothing later tasks import.

**Field choice.** Watchlist line 1: symbol, price, 1D% (what a glance at a watchlist is for — the same three v95 keeps inline at `xs`); line 2: company and signal ("In position" and the like). Tape, 1W%, 1M%, the sparkline, next earnings, open/closed counts and the remove action are in the drawer; the drawer link "Open ticker →" keeps today's `rowActivate` destination (`/watchlist/:symbol`, spec §6b.4). Ticker detail's trade list (no `rowActivate` today) — line 1: ticker and P&L %; line 2: status and held; entry and now in the drawer, linked to `/trades/:id`. Both identity columns render through a `cell` template only, so each gains a plain `value` for the drawer heading (`rowLabel()`); the rendered cell does not change.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/workspaces/watchlist/watchlist.spec.ts` (add `import { installDialogPolyfill } from '../../testing/dialog-polyfill';` and `import { compactKeys, drawerKeys, openRowDrawer, phoneViewport } from '../../ui/data-table/testing/reachability';`):

```ts
describe('Watchlist on a phone (v179 §3.1)', () => {
  let fixture: ComponentFixture<Watchlist>;

  beforeEach(async () => {
    installDialogPolyfill();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
        WatchlistStore,
        { provide: TapeStore, useValue: { toggle: vi.fn(), symbols: () => [] } },
        phoneViewport(),
      ],
    });
    fixture = TestBed.createComponent(Watchlist);
    TestBed.inject(WatchlistStore).load();
    fixture.detectChanges();
    TestBed.inject(HttpTestingController)
      .expectOne('/api/v1/watchlist/tickers')
      .flush({ tickers: [ticker({ symbol: 'NVDA', company_name: 'Nvidia' })] });
    await fixture.whenStable();
    fixture.detectChanges();
  });

  const table = () => (fixture.nativeElement as HTMLElement).querySelector('sb-data-table') as HTMLElement;

  it('leads the compact row with symbol, price and the 1-day change', () => {
    expect(compactKeys(table())).toEqual(['symbol', 'price', 'change_1d_pct', 'company_name', 'signal']);
  });

  it('reaches every column between the compact row and the drawer (§7.5)', () => {
    openRowDrawer(table());
    fixture.detectChanges();
    const shown = (fixture.componentInstance as unknown as { visible: string[] }).visible;
    expect([...compactKeys(table()), ...drawerKeys(table())].sort()).toEqual([...shown].sort());
    expect(table().querySelector('sb-drawer.row-drawer h2')!.textContent!.trim()).toBe('NVDA');
  });

  it('opens the drawer instead of navigating, and links to the ticker page from it', () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate');
    openRowDrawer(table());
    fixture.detectChanges();
    expect(navigate).not.toHaveBeenCalled();
    const link = table().querySelector('a.drawer-detail-link')!;
    expect(link.textContent!.trim()).toBe('Open ticker →');
    expect(link.getAttribute('href')).toBe('/watchlist/NVDA');
  });
});
```

Append to `frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts` (change the testing import to `import { ComponentFixture, TestBed } from '@angular/core/testing';` and add `import { patchState } from '@ngrx/signals';`, `import { unprotected } from '@ngrx/signals/testing';`, `import { installDialogPolyfill } from '../../testing/dialog-polyfill';`, `import { compactKeys, drawerKeys, openRowDrawer, phoneViewport } from '../../ui/data-table/testing/reachability';`):

```ts
describe('TickerDetail trades on a phone (v179 §3.1)', () => {
  function renderPhone(): ComponentFixture<TickerDetail> {
    installDialogPolyfill();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(), provideRouter([]),
        provideHttpClient(), provideHttpClientTesting(),
        TradesStore, ChartStore, phoneViewport(),
      ],
    });
    const fixture = TestBed.createComponent(TickerDetail);
    fixture.componentRef.setInput('symbol', 'AAPL');
    fixture.detectChanges();
    patchState(unprotected(TestBed.inject(TradesStore)), {
      data: { items: [row({ id: 't7' })], total: 1, page: 1, per_page: 25 },
    });
    fixture.detectChanges();
    return fixture;
  }
  const table = (fixture: ComponentFixture<TickerDetail>) =>
    (fixture.nativeElement as HTMLElement).querySelector('sb-data-table') as HTMLElement;

  it('shows ticker and P&L on line 1, status and held on line 2', () => {
    expect(compactKeys(table(renderPhone()))).toEqual(['ticker', 'pnl_pct', 'status', 'held']);
  });

  it('reaches all six columns and links the drawer to the trade', () => {
    const fixture = renderPhone();
    openRowDrawer(table(fixture));
    fixture.detectChanges();
    expect([...compactKeys(table(fixture)), ...drawerKeys(table(fixture))].sort())
      .toEqual(['entry', 'held', 'now', 'pnl_pct', 'status', 'ticker']);
    expect(table(fixture).querySelector('a.drawer-detail-link')!.getAttribute('href')).toBe('/trades/t7');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/watchlist/watchlist.spec.ts --include src/app/workspaces/watchlist/ticker-detail.spec.ts`
Expected: FAIL — `compactKeys` returns `[]` (no column declares `compact`, so both tables still render `<table>`).

- [ ] **Step 3: Declare the Watchlist compact row**

In `frontend/src/app/workspaces/watchlist/watchlist.ts`:

- change line 26 to `import { ColumnDef, DetailLink, RowContext, SortSpec } from '../../ui/data-table/data-table.types';`;
- append to the `WATCHLIST_COLUMNS` doc comment, before its closing `*/`:

```ts
 *
 * v179 §3.1: on a phone each ticker is two lines -- symbol, price and 1D%,
 * then company and signal; everything else is in the row drawer. `symbol`
 * gains a plain `value` for the drawer heading only (its cell renders).
```

- replace these five entries (the other eight are unchanged):

```ts
  { key: 'symbol', header: 'Symbol', value: (row) => row.symbol, sortable: true, compact: { line: 1, order: 1 } },
  { key: 'company_name', header: 'Company', value: (row) => text(row.company_name), sortable: true, inlineFrom: 'md', compact: { line: 2, order: 1 } },
  { key: 'price', header: 'Price', numeric: true, inlineFrom: 'xs', compact: { line: 1, order: 2 } },
  { key: 'change_1d_pct', header: '1D%', value: (row) => pct(row.change_1d_pct), numeric: true, inlineFrom: 'xs', compact: { line: 1, order: 3 } },
  { key: 'signal', header: 'Signal', inlineFrom: 'md', compact: { line: 2, order: 2 } },
```

- in the `<sb-data-table …>` inside `<sb-panel heading="Watchlist" …>`, add before `(rowActivate)="open($event)"`:

```html
          phoneTap="drawer"
          [detailLink]="tickerLink"
```

- below `protected open(row: Ticker): void { … }`, add:

```ts
  /** v179 §6b.4: a phone tap opens the row drawer; this keeps `open()`'s
   *  destination. Tablet and desktop still navigate through `rowActivate`. */
  protected readonly tickerLink = (row: Ticker): DetailLink => ({
    commands: ['/watchlist', row.symbol],
    label: 'Open ticker →',
  });
```

- [ ] **Step 4: Declare the ticker-detail compact row**

In `frontend/src/app/workspaces/watchlist/ticker-detail.ts`:

- change line 22 to `import { ColumnDef, DetailLink, RowContext, SortSpec } from '../../ui/data-table/data-table.types';`;
- replace the `columns` computed with:

```ts
  /** v179 §3.1: on a phone, ticker and P&L, then status and held; entry and
   *  now in the row drawer, which links to the trade. `ticker`'s `value` is
   *  the drawer heading only -- its cell renders. */
  protected readonly columns = computed<ColumnDef<TradeRow>[]>(() => [
    { key: 'ticker', header: 'Ticker', value: (row) => row.ticker, cell: this.tickerCell(), compact: { line: 1, order: 1 } },
    { key: 'status', header: 'Status', value: (row) => row.status, compact: { line: 2, order: 1 } },
    { key: 'entry', header: 'Entry', value: (row) => num(row.entry), numeric: true },
    { key: 'now', header: 'Now', value: (row) => num(row.current_price), numeric: true },
    { key: 'pnl_pct', header: 'P&L %', numeric: true, cell: this.pnlCell(), compact: { line: 1, order: 2 } },
    { key: 'held', header: 'Held', value: (row) => held(row.closed_at ? row.held_hours : elapsedHours(row.opened_at, this.now())), numeric: true, sortable: true, compact: { line: 2, order: 2 } },
  ]);

  protected readonly tradeLink = (row: TradeRow): DetailLink => ({
    commands: ['/trades', row.id],
    label: 'Open full trade →',
  });
```

- in its `<sb-data-table …>`, add after `[showPerPage]="true"`:

```html
        phoneTap="drawer"
        [detailLink]="tradeLink"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/watchlist/watchlist.spec.ts --include src/app/workspaces/watchlist/ticker-detail.spec.ts`
Expected: PASS, `0 failed` (including the existing `'declares a floor on every column but the pinned symbol'`: `symbol` still has no `inlineFrom`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/watchlist/watchlist.spec.ts frontend/src/app/workspaces/watchlist/ticker-detail.ts frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts
git commit -m "feat(watchlist): phone compact rows and row drawers for the watchlist and a ticker's trades (v179 §3.1)"
```

---

**Task V179-13 continues in [Part 3b](2026-10-19-v179-mobile-layout-consistency_3b-research-risk-and-check.md)** — with it this file would pass the 1500-line limit, and a task is never compressed to fit.
