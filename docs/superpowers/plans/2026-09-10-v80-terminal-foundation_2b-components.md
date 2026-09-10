# v80 — Terminal foundation, part 2b: canonical components (F8–F12)

Part of `2026-09-10-v80-terminal-foundation_0-index.md`. Read its Global
Constraints and the v77 precondition before starting any task here.

# Phase 2 — Canonical components (continued)

## Parallelisation

- **Group A (parallel, after F3), continued.** F8–F12 run alongside F4–F7
  (part 2a, whose table lists these five tasks' files) and F13–F20 (parts 3a
  and 3b). Each task is one component file plus its own spec file; F8 also
  edits two comments in `plan-cell.ts`, which no other task touches.
- **Sequential edge:** every task consumes F2's colours and F3's
  `--control-h`, `--row-h`, `--text-control` and `.sb-label`.

---

### Task F8: `sb-data-table` phone mode replaces card mode

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.ts`
- Modify: `frontend/src/app/ui/plan-cell.ts:32-37,58-60` (comments only)
- Test: `frontend/src/app/ui/data-table/data-table.spec.ts`:
  - replace the `SR24: card mode` block (lines 544–654);
  - replace the `applies to cards too` test (lines 682–689).

**Interfaces:**
- Consumes: `.sb-label`, `--row-h`, `--control-h`, `--text-control` (F3).
- Produces:
  - No public API change. `cardsAt` keeps its name and type, and now forces
    the pinned phone mode.
  - New protected members: `phone`, `sortOptions`, `sortValue`, `onPhoneSort`.
  - The raw `.phone-sort` select emits the existing `sortChange`.
  - `.card`, `.card-head`, `.card-body`, `.card-value` and `.card-actions` are removed.
  - The `--cell-wrap`/`--sep-wrap` hook is no longer set by anything.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/data-table/data-table.spec.ts`, replace everything
from `// --- SR24: card mode below 640px` down to (not including)
`describe('DataTable rowClass', () => {` with:

```ts
// --- v80 D4: phone mode below 640px ------------------------------------------
// Card mode is gone. Forced through `cardsAt`: jsdom evaluates neither a
// container query nor a media query, so the `.phone` class is the only thing
// a test can drive.

describe('DataTable phone mode', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.visible.set(['ticker', 'pnl', 'held']);
    host.pinned.set(['actions']);
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const wrap = () => el().querySelector('.wrap')!;

  function asPhone() {
    host.cardsAt.set(true);
    fixture.detectChanges();
  }

  it('is off by default', () => {
    expect(wrap().classList).not.toContain('phone');
  });

  it('keeps the table below the breakpoint -- no cards', () => {
    asPhone();
    expect(wrap().classList).toContain('phone');
    expect(el().querySelector('table')).not.toBeNull();
    expect(el().querySelector('.cards, .card')).toBeNull();
    expect(el().querySelectorAll('tbody tr.row')).toHaveLength(ROWS.length);
  });

  it('pins the first rendered column, header and cells alike', () => {
    asPhone();
    expect([...el().querySelectorAll('thead th.pin')].map((th) => th.textContent!.trim()))
      .toEqual(['Ticker']);
    expect([...el().querySelectorAll('tbody tr.row')].map((tr) => tr.querySelectorAll('td.pin').length))
      .toEqual([1, 1, 1]);
    expect(el().querySelector('tbody tr.row td.pin')!.textContent).toContain('AAPL');
  });

  it('pins whichever column the user moved first', () => {
    host.visible.set(['held', 'ticker', 'pnl']);
    asPhone();
    expect(el().querySelector('thead th.pin')!.textContent!.trim()).toBe('Held');
  });

  it('makes the pinned column sticky only in phone mode', () => {
    const position = () => getComputedStyle(el().querySelector('tbody td.pin')!).position;
    expect(position()).not.toBe('sticky');
    asPhone();
    expect(position()).toBe('sticky');
  });

  it('offers every sortable visible column, both ways, in its own select', () => {
    asPhone();
    const options = [...el().querySelectorAll('.phone-sort option')].map((o) => o.textContent!.trim());
    expect(options).toEqual(['Unsorted', 'Ticker ↑', 'Ticker ↓', 'P&L % ↑', 'P&L % ↓']);
  });

  it('shows the current sort as the selected option', () => {
    host.sort.set({ key: 'pnl', direction: 'desc' });
    asPhone();
    const select = el().querySelector('.phone-sort select') as HTMLSelectElement;
    expect(select.value).toBe('pnl:desc');
    expect([...select.options].map((o) => o.value)).not.toContain('');
  });

  it('emits the chosen sort through sortChange', () => {
    asPhone();
    const select = el().querySelector('.phone-sort select') as HTMLSelectElement;
    select.value = 'ticker:desc';
    select.dispatchEvent(new Event('change'));
    expect(host.lastSort).toEqual({ key: 'ticker', direction: 'desc' });
  });

  it('hides the sort select outside phone mode', () => {
    expect(getComputedStyle(el().querySelector('.phone-sort')!).display).toBe('none');
    asPhone();
    expect(getComputedStyle(el().querySelector('.phone-sort')!).display).toBe('flex');
  });

  it('renders no sort select when nothing visible is sortable', () => {
    host.visible.set(['held']);
    asPhone();
    expect(el().querySelector('.phone-sort')).toBeNull();
  });

  it('still activates a row', () => {
    asPhone();
    (el().querySelectorAll('tbody tr.row')[1] as HTMLElement).click();
    expect(host.activated.map((r) => r.ticker)).toEqual(['MSFT']);
  });

  it('keeps pagination working', () => {
    host.pagination.set({ page: 1, perPage: 2, total: 9 });
    asPhone();
    expect(el().querySelector('sb-pagination')).not.toBeNull();
  });

  it('sets headers in the shared label style', () => {
    expect(el().querySelector('thead th')!.classList).toContain('sb-label');
  });
});

```

In the `DataTable rowClass` block, replace:

```ts
  it('applies to cards too, not just table rows', () => {
    host.cardsAt.set(true);
    host.rowClass.set((row) => (row.ticker === 'MSFT' ? 'blink' : null));
    fixture.detectChanges();

    const cards = [...el().querySelectorAll('.card')];
    expect(cards.map((c) => c.className)).toEqual(['card', 'card blink', 'card']);
  });
```

with:

```ts
  it('applies in phone mode too -- they are the same rows', () => {
    host.cardsAt.set(true);
    host.rowClass.set((row) => (row.ticker === 'MSFT' ? 'blink' : null));
    fixture.detectChanges();

    expect(bodyRows().map((r) => r.className)).toEqual(['row', 'row blink', 'row']);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/data-table.spec.ts')`

Expected: FAIL.
- Forcing `cardsAt` still renders cards and no table.
- There is no `.phone`, `.pin` or `.phone-sort`.
- Headers have no `sb-label` class.

- [ ] **Step 3: Implement**

In `frontend/src/app/ui/data-table/data-table.ts`, replace the whole
`template:` string with:

```ts
  template: `
    <div class="wrap" [class.phone]="phone()" [attr.aria-busy]="loading()">
      @if (showSpinner()) {
        <span class="loading-spinner" aria-hidden="true"></span>
      }
      @if (pagination(); as page) {
        <ng-container [ngTemplateOutlet]="pagerTemplate" [ngTemplateOutletContext]="{ $implicit: page, announce: true }" />
      }
      @if (sortOptions().length) {
        <!-- v80 D4. A phone cannot reach the sort arrow in a header it has
             scrolled sideways past, so the table carries its own sort control.
             Always in the DOM and shown by the container query below (or the
             forced .phone class), so a table in a narrow drawer gets it too. -->
        <label class="phone-sort">
          <span class="sb-label">Sort</span>
          <select (change)="onPhoneSort($any($event.target).value)">
            @if (!sortValue()) {
              <option value="" selected disabled>Unsorted</option>
            }
            @for (option of sortOptions(); track option.value) {
              <option [value]="option.value" [selected]="option.value === sortValue()">{{ option.label }}</option>
            }
          </select>
        </label>
      }
      <div class="scroller" tabindex="0">
      <table>
        <thead>
          <tr>
            @if (expansion()) {
              <th class="expander-cell"><span class="sr-only">Expand row</span></th>
            }
            @for (col of renderedColumns(); track col.key) {
              <th
                class="sb-label"
                [style.width]="col.width"
                [class.num]="col.numeric"
                [class.pin]="$first"
                [class.dragging]="dragging() === col.key"
                [attr.aria-sort]="ariaSort(col)"
                [attr.draggable]="isPinned(col.key) ? null : 'true'"
                [attr.tabindex]="isPinned(col.key) ? null : 0"
                [attr.aria-label]="isPinned(col.key) ? null : col.header + ' column, arrow keys to reorder'"
                (dragstart)="onDragStart(col.key, $event)"
                (dragover)="onDragOver(col.key, $event)"
                (drop)="onDrop(col.key, $event)"
                (dragend)="onDragEnd()"
                (keydown)="onHeaderKeydown(col.key, $event)"
              >
                @if (col.sortable) {
                  <button type="button" class="sort" (click)="toggleSort(col)">
                    <span>{{ col.header }}</span>
                    <span class="arrow" aria-hidden="true">{{ arrow(col) }}</span>
                  </button>
                } @else {
                  {{ col.header }}
                }
              </th>
            }
          </tr>
        </thead>

        <tbody>
          @for (row of rows(); track rowKey()(row)) {
            <tr class="row" [class]="rowClass()(row)" (click)="activate(row, $event)">
              @if (expansion()) {
                <td class="expander-cell">
                  <button
                    type="button"
                    class="expander"
                    [attr.aria-expanded]="isExpanded(row)"
                    [attr.aria-label]="isExpanded(row) ? 'Collapse row' : 'Expand row'"
                    (click)="toggleExpanded(row)"
                  >
                    {{ isExpanded(row) ? '▾' : '▸' }}
                  </button>
                </td>
              }
              @for (col of renderedColumns(); track col.key) {
                <td [class.num]="col.numeric" [class.pin]="$first">
                  @if (col.cell; as cellTemplate) {
                    <ng-container
                      [ngTemplateOutlet]="cellTemplate"
                      [ngTemplateOutletContext]="{ $implicit: row }"
                    />
                  } @else {
                    {{ text(col, row) }}
                  }
                </td>
              }
            </tr>

            @if (expansion(); as expansionTemplate) {
              @if (isExpanded(row)) {
                <tr class="expansion">
                  <td [attr.colspan]="colspan()">
                    <ng-container
                      [ngTemplateOutlet]="expansionTemplate"
                      [ngTemplateOutletContext]="{ $implicit: row }"
                    />
                  </td>
                </tr>
              }
            }
          }
          @for (slot of fillerRows(); track slot) {
            <tr class="filler" aria-hidden="true"><td [attr.colspan]="colspan()"></td></tr>
          }
        </tbody>
        @if (hasFooter()) {
          <tfoot><tr>
            @if (expansion()) { <td class="expander-cell"></td> }
            @for (col of renderedColumns(); track col.key) { <td [class.num]="col.numeric">{{ footerText(col) }}</td> }
          </tr></tfoot>
        }
      </table>
      </div>

      @if (showEmptyState(); as state) {
        <sb-empty-state [title]="state.title" [hint]="state.hint" />
      }

      @if (pagination(); as page) {
        <ng-container [ngTemplateOutlet]="pagerTemplate" [ngTemplateOutletContext]="{ $implicit: page, announce: false }" />
      }
    </div>

    <ng-template #pagerTemplate let-page let-announce="announce">
      <sb-pagination [pagination]="page" [showPerPage]="showPerPage()" [announce]="announce"
        (pageChange)="pageChange.emit($event)" (perPageChange)="perPageChange.emit($event)" />
    </ng-template>  `,
```

In `styles`, delete everything from `    .cards { list-style: none;` through
`    .card-actions button { width: 100%; }` inclusive: the card rules and the
wrap-contract comment block between them.

Replace:

```css
    .wrap { position: relative; }
```

with:

```css
    /* The container phone mode measures (v80 D4). .wrap is a block in normal
       flow, so container-type cannot collapse it the way it collapses a
       shrink-to-fit host. */
    .wrap { position: relative; container: table / inline-size; }
```

Replace:

```css
    th {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    /* Digits line up down the column, so a magnitude is readable without
       reading the number. */
    .num { text-align: right; font-family: var(--font-mono); }
```

with:

```css
    /* Header typography is the global .sb-label (v80 D4). */
    /* Digits line up down the column, so a magnitude is readable without
       reading the number. */
    .num { text-align: right; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
    /* One row height across every table (v80 D3), 44px on touch. A cell's
       height is a minimum, so a wrapped cell still grows the row. */
    tbody tr.row > td { height: var(--row-h); }
```

Replace:

```css
    tr.filler > td { background: var(--bg); border-bottom: 0; height: calc(1lh + 2 * var(--space-6)); }
```

with:

```css
    tr.filler > td { background: var(--bg); border-bottom: 0; height: var(--row-h); }
```

Replace:

```css
    .sr-only {
      position: absolute;
      width: 1px; height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }
  `,
```

with:

```css
    .sr-only {
      position: absolute;
      width: 1px; height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }

    /* -- v80 D4: phone mode -----------------------------------------------
     * Card mode is replaced. A card per row threw away the column alignment
     * that makes a table scannable, and had no sort control at all. Below
     * 640px the table stays a table: the first rendered column pins so a row
     * keeps its identity while the rest scroll sideways under .scroller, and
     * the sort select appears above it.
     *
     * .phone forces the same layout from the viewport, and from cardsAt in a
     * test. The container query is last on purpose: a CSS parser that does
     * not know @container can only lose what follows it. */
    .phone-sort {
      display: none;
      align-items: center;
      gap: var(--space-8);
      padding: var(--space-8) var(--space-10);
    }
    .phone-sort select {
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--surface);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
    }
    .phone .phone-sort { display: flex; }
    .phone .pin { position: sticky; left: 0; z-index: 1; background: var(--surface); }
    .phone thead th.pin { z-index: 3; }
    .phone .row:hover .pin { background: var(--surface-raised); }
    @container table (max-width: 639px) {
      .phone-sort { display: flex; }
      .pin { position: sticky; left: 0; z-index: 1; background: var(--surface); }
      thead th.pin { z-index: 3; }
      .row:hover .pin { background: var(--surface-raised); }
    }
  `,
```

In the class, replace everything from the `/**\n   * Cards instead of a table, below \`sm\``
comment through the end of `pinnedColumns` (the `cards`, `headlineColumns`,
`bodyColumns` and `pinnedColumns` members) with:

```ts
  /**
   * Phone mode, below `sm` -- spec v80 D4, replacing v18 Decision 9's cards.
   *
   * The CSS switches on container width, so a table in a narrow drawer
   * behaves like one on a phone. This signal adds the viewport case as the
   * `.phone` class. `cardsAt` keeps its name so no call site breaks, and
   * forces the mode: jsdom lays nothing out and evaluates no query, so a
   * width-driven assertion would be theatre.
   */
  private readonly viewportService = inject(ViewportService);
  readonly cardsAt = input<boolean | null>(null);
  protected readonly phone = computed(
    () => this.cardsAt() ?? this.viewportService.isPhone(),
  );

  /** Every sortable visible column, both directions, in render order. The
   *  arrows match `arrow()`, so the select and the header say the same thing. */
  protected readonly sortOptions = computed(() =>
    this.renderedColumns()
      .filter((column) => column.sortable)
      .flatMap((column) => [
        { value: `${column.key}:asc`, label: `${column.header} ↑` },
        { value: `${column.key}:desc`, label: `${column.header} ↓` },
      ]),
  );

  protected readonly sortValue = computed(() => {
    const sort = this.sort();
    return sort ? `${sort.key}:${sort.direction}` : '';
  });

  /** Split on the LAST colon: a column key may contain one, a direction never does. */
  protected onPhoneSort(value: string): void {
    const cut = value.lastIndexOf(':');
    const key = value.slice(0, cut);
    const direction = value.slice(cut + 1);
    if (!key || (direction !== 'asc' && direction !== 'desc')) return;
    this.sortChange.emit({ key, direction });
  }
```

In `fillerRows`, replace:

```ts
    if (!page || page.perPage <= 0 || this.cards()) return [];
```

with:

```ts
    if (!page || page.perPage <= 0) return [];
```

In the `rowClass` input's comment, replace `An extra CSS class for the whole row (or card), or null for none --`
with `An extra CSS class for the whole row, or null for none --`.

In `frontend/src/app/ui/plan-cell.ts`, replace:

```css
    /* nowrap is the TABLE rule -- three prices and two separators read as one
       plan, and a column has a scroller behind it. --cell-wrap is DataTable's
       card-mode override (see its .card-value block): undefined here, so a
       table keeps nowrap; set to normal inside a card, where the run has no
       column to align to and nothing to scroll and would otherwise be cut off
       at the edge of a phone. */
```

with:

```css
    /* nowrap is the TABLE rule -- three prices and two separators read as one
       plan, and a column has a scroller behind it. --cell-wrap was DataTable's
       card-mode override; v80 D4 replaced cards with a pinned, scrolling table,
       nothing sets it any more, and the nowrap fallback always applies.
       Migration deletes the variable. */
```

and replace:

```css
       --sep-wrap is the card-mode counterpart of --cell-wrap above: pre-wrap
       there, so the run can break at a separator without the spacing
       collapsing and running the numbers together. */
```

with:

```css
       --sep-wrap was the card-mode counterpart of --cell-wrap above, and is
       equally unset since v80 D4. */
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/data-table.spec.ts' --include='**/plan-cell.spec.ts' --include='**/client-page.spec.ts')`

Expected: PASS.

If `makes the pinned column sticky only in phone mode` fails with an empty
`position` while every other test passes, jsdom's CSS parser did not keep the
`.phone .pin` rule. Check that the `@container` block is the last thing in
`styles` before touching the component.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/data-table/data-table.spec.ts frontend/src/app/ui/plan-cell.ts
git commit -m "feat(v80): data table keeps the table on a phone -- pinned first column, sort select"
```

---

### Task F9: `sb-pagination` touch sizing

**Files:**
- Modify: `frontend/src/app/ui/pagination.ts`
- Test: `frontend/src/app/ui/pagination.spec.ts`

**Interfaces:**
- Consumes: `--control-h`, `--text-control`, `.sb-label` (F3).
- Produces: no API change.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/pagination.spec.ts`, add at the top, before the Angular imports:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

Append to the end of the file:

```ts
describe('PaginationComponent touch sizing (v80 D4)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/pagination.ts'), 'utf8');
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const rule = (selector: string) =>
    SOURCE.match(new RegExp(`${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('sizes pager buttons from --control-h, which is 44px on touch', () => {
    expect(rule('button')).toContain('min-height: var(--control-h)');
    expect(rule('button')).toContain('min-width: var(--control-h)');
  });

  it('sizes the page jump and the rows select the same way, with 16px-on-touch text', () => {
    const r = rule('.per-page select, .jump');
    expect(r).toContain('height: var(--control-h)');
    expect(r).toContain('font-size: var(--text-control)');
  });

  it('labels the rows select in the shared label style', () => {
    const f = TestBed.createComponent(PaginationComponent);
    f.componentRef.setInput('pagination', { page: 1, perPage: 25, total: 100 });
    f.componentRef.setInput('showPerPage', true);
    f.detectChanges();
    const label = (f.nativeElement as HTMLElement).querySelector('.per-page .sb-label')!;
    expect(label.textContent!.trim()).toBe('Rows');
  });

  it('never prints readable text in the divider-only grey', () => {
    expect(SOURCE).not.toContain('--text-faint');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/pagination.spec.ts')`

Expected: FAIL. All four `v80 D4` tests fail.

- [ ] **Step 3: Implement**

In `frontend/src/app/ui/pagination.ts`'s template, replace:

```html
<label><span class="label">Rows</span><select
```

with:

```html
<label><span class="sb-label">Rows</span><select
```

In `styles`, replace:

```css
    .per-page .label { font-size: var(--text-chip); color: var(--text-secondary); }
    .per-page select, .jump { background: var(--surface-raised); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius); font: inherit; }
    .per-page select { font-size: var(--text-chip); padding: 2px var(--space-4); }
```

with:

```css
    /* v80 D4: --control-h and --text-control, so the pager grows to 44px and
       16px on touch with every other control. The caption is .sb-label. */
    .per-page select, .jump { height: var(--control-h); background: var(--surface); color: var(--text); border: 1px solid var(--border-strong); border-radius: var(--radius); font: inherit; font-size: var(--text-control); }
    .per-page select { padding: 0 var(--space-4); }
```

Replace:

```css
    .jump { width: 3.5rem; padding: 2px var(--space-4); text-align: right; }
```

with:

```css
    .jump { width: 3.5rem; padding: 0 var(--space-4); text-align: right; }
```

Replace:

```css
    button { padding: var(--space-4) var(--space-10); background: var(--surface-raised); border: 1px solid var(--border); border-radius: var(--radius); color: var(--text); font: inherit; cursor: pointer; transition: border-color var(--transition); }
    button:disabled { color: var(--text-faint); cursor: default; }
```

with:

```css
    button { min-height: var(--control-h); min-width: var(--control-h); padding: 0 var(--space-10); background: transparent; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--text); font: inherit; cursor: pointer; transition: border-color var(--transition); }
    /* Opacity, not --text-faint: that grey is divider-only. */
    button:disabled { opacity: 0.45; cursor: default; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/pagination.spec.ts')`

Expected: PASS, including the existing `insets the per-page row` alignment test.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/pagination.ts frontend/src/app/ui/pagination.spec.ts
git commit -m "feat(v80): touch-sized pager buttons, jump and rows select"
```

---

### Task F10: `sb-confidence-cell` restyle to the cell contract

**Files:**
- Modify: `frontend/src/app/ui/confidence-cell.ts`
- Test: `frontend/src/app/ui/confidence-cell.spec.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: no API change. Content stays `Lv4 · 78` / `Lv4` / `—`, per the
  spec's cell contract. The level weight is 500, and the separator and dash
  are `--text-muted`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/confidence-cell.spec.ts`, add at the top:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

Append to the end of the file:

```ts
describe('ConfidenceCell cell contract (v80 D4)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/confidence-cell.ts'), 'utf8');

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('is text, never a meter', () => {
    const el = render(4, 78);
    expect(el.querySelector('meter, progress, .bar, .meter')).toBeNull();
    expect(text(el)).toBe('Lv4 · 78');
  });

  it('sets the level in a self-hosted mono weight', () => {
    expect(SOURCE).toMatch(/\.badge \{ font-weight: 500; \}/);
  });

  it('prints the separator and the dash in a readable grey, not the divider grey', () => {
    expect(SOURCE).not.toContain('--text-faint');
    expect(SOURCE).toMatch(/\.score \{ color: var\(--text-secondary\); \}/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/confidence-cell.spec.ts')`

Expected: FAIL. The weight test and the divider-grey test fail. The meter test passes already.

- [ ] **Step 3: Implement**

In `frontend/src/app/ui/confidence-cell.ts`, replace:

```css
    .badge { font-weight: 600; }
```

with:

```css
    /* 500: JetBrains Mono is self-hosted at 400/500/700, and a 600 would be
       synthesised (v80 D3). The band colour carries the emphasis. */
    .badge { font-weight: 500; }
```

Replace:

```css
    .sep { color: var(--text-faint); white-space: pre; }
    .absent { color: var(--text-faint); }
```

with:

```css
    .sep { color: var(--text-muted); white-space: pre; }
    /* --text-muted, not --text-faint: faint is divider-only (contrast.spec.ts),
       and an absent confidence is still something a reader has to read. */
    .absent { color: var(--text-muted); }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/confidence-cell.spec.ts')`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/confidence-cell.ts frontend/src/app/ui/confidence-cell.spec.ts
git commit -m "feat(v80): confidence cell in mono 500 with readable separators"
```

---

### Task F11: `sb-empty-state` dashed box and `reason`

**Files:**
- Modify: `frontend/src/app/ui/empty-state.ts`
- Create: `frontend/src/app/ui/empty-state.spec.ts`

**Interfaces:**
- Consumes: `.sb-label` (F3); the `AsyncEmptyReason` type from `ui/async.ts`
  (existing). The import is `import type`, so there is no runtime cycle with
  `async.ts`, which imports this component.
- Produces: `EmptyStateComponent.reason = input<AsyncEmptyReason | null>(null)`.
  It renders `Result: 0` for `'measured-zero'` and `Awaiting data` for
  `'no-data-yet'`. Optional now; Migration makes it required.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/empty-state.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import type { AsyncEmptyReason } from './async';
import { EmptyStateComponent } from './empty-state';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/empty-state.ts'), 'utf8');

function render(title: string, hint?: string, reason?: AsyncEmptyReason): HTMLElement {
  const f = TestBed.createComponent(EmptyStateComponent);
  f.componentRef.setInput('title', title);
  if (hint !== undefined) f.componentRef.setInput('hint', hint);
  if (reason !== undefined) f.componentRef.setInput('reason', reason);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('EmptyStateComponent (v80 D4)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('states the title, and the hint when there is one', () => {
    const el = render('No trades match this filter', 'Clear the filters.');
    expect(el.querySelector('.empty-title')!.textContent!.trim()).toBe('No trades match this filter');
    expect(el.querySelector('.empty-hint')!.textContent!.trim()).toBe('Clear the filters.');
  });

  it('omits the hint element entirely when there is none', () => {
    expect(render('No trades yet').querySelector('.empty-hint')).toBeNull();
  });

  it('names a measured zero', () => {
    const reason = render('No trades', undefined, 'measured-zero').querySelector('.reason')!;
    expect(reason.textContent!.trim()).toBe('Result: 0');
    expect(reason.classList).toContain('sb-label');
  });

  it('names data that has not arrived', () => {
    expect(render('No trades', undefined, 'no-data-yet').querySelector('.reason')!.textContent!.trim())
      .toBe('Awaiting data');
  });

  it('shows no reason line until a caller says which empty it is', () => {
    expect(render('No trades').querySelector('.reason')).toBeNull();
  });

  it('draws a dashed hairline box', () => {
    expect(SOURCE).toMatch(/\.empty \{[^}]*border: 1px dashed var\(--border-strong\)/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/empty-state.spec.ts')`

Expected: FAIL. The build fails on `setInput('reason', …)`
(`NG0303: Can't set value of the 'reason' input`), and the dashed-box test fails.

- [ ] **Step 3: Implement**

Replace the whole of `frontend/src/app/ui/empty-state.ts` with:

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import type { AsyncEmptyReason } from './async';

/**
 * What a table shows when it has no rows.
 *
 * Always a sentence about this table's situation, never a generic "No data":
 * "no trades yet" and "no trades match this filter" look identical to a
 * component and mean opposite things to a person, and only the caller knows
 * which one it is. The `hint` carries the way out — clear the filters, add a
 * ticker — because an empty state that does not say what to do next is a dead
 * end.
 *
 * `reason` (v80 D4) is the same distinction `sb-async` draws, for the empty
 * states that do not sit inside one: "Result: 0" is a measured answer, and
 * "Awaiting data" is a feed that has not arrived. Optional until Migration
 * gives every call site one, after which it becomes required.
 */
@Component({
  selector: 'sb-empty-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="empty">
      @if (reason(); as why) {
        <span class="reason sb-label">{{ why === 'measured-zero' ? 'Result: 0' : 'Awaiting data' }}</span>
      }
      <p class="empty-title">{{ title() }}</p>
      @if (hint(); as hintText) {
        <p class="empty-hint">{{ hintText }}</p>
      }
    </div>
  `,
  styles: `
    /* A dashed hairline says "nothing here" without a colour (v80 D4). Three
       screens printed their empty states in --text-faint, which is
       divider-only; nothing in this box is. */
    .empty {
      display: grid;
      justify-items: center;
      gap: var(--space-6);
      padding: var(--space-20);
      border: 1px dashed var(--border-strong);
      border-radius: var(--radius);
      text-align: center;
    }
    .empty-title { margin: 0; color: var(--text-secondary); font-size: var(--text-body); }
    .empty-hint { margin: 0; color: var(--text-muted); font-size: var(--text-table); }
  `,
})
export class EmptyStateComponent {
  readonly title = input.required<string>();
  readonly hint = input<string | undefined>(undefined);
  readonly reason = input<AsyncEmptyReason | null>(null);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/empty-state.spec.ts' --include='**/async.spec.ts')`

Expected: PASS. `async.spec.ts` still finds its own reason chip:
`sb-async` passes no `reason`, so the box shows none of its own.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/empty-state.ts frontend/src/app/ui/empty-state.spec.ts
git commit -m "feat(v80): dashed empty state with an optional measured-zero / awaiting-data reason"
```

---

### Task F12: `sb-section-head` back and status slots

**Files:**
- Modify: `frontend/src/app/ui/section-head.ts`
- Test: `frontend/src/app/ui/section-head.spec.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - two content slots: `[back]`, always rendered before the heading, and
    `[status]`, beside the heading inside `.title-group`;
  - `[actions]` still projects and is documented as deprecated.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/section-head.spec.ts`, add at the top:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

Append to the end of the file:

```ts
@Component({
  imports: [SectionHead],
  template: `
    <sb-section-head heading="AAPL" [level]="1">
      <span status class="as-of">as of 14:02</span>
      <a back href="/trades">Trades</a>
    </sb-section-head>
  `,
})
class SlotHost {}

describe('SectionHead slots (v80 D4)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/section-head.ts'), 'utf8');

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function slots(): HTMLElement {
    const f = TestBed.createComponent(SlotHost);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('renders back before the title whatever order the caller writes them in', () => {
    const el = slots();
    const back = el.querySelector('[back]')!;
    const h1 = el.querySelector('h1')!;
    expect(back.compareDocumentPosition(h1) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('keeps status beside the title, in the same group', () => {
    const el = slots();
    const group = el.querySelector('h1')!.closest('.title-group');
    expect(group).not.toBeNull();
    expect(el.querySelector('[status]')!.closest('.title-group')).toBe(group);
  });

  it('keeps the deprecated actions slot outside the title group', () => {
    const button = render().querySelector('button')!;
    expect(button.closest('.title-group')).toBeNull();
  });

  it('lets a long title wrap rather than push status off the row', () => {
    expect(SOURCE).toMatch(/h1 \{[^}]*overflow-wrap: anywhere/);
    expect(SOURCE).toMatch(/h2 \{[^}]*overflow-wrap: anywhere/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/section-head.spec.ts')`

Expected: FAIL.
- `back` is not projected (null).
- There is no `.title-group`.
- The wrap test fails.

- [ ] **Step 3: Implement**

Replace the whole of `frontend/src/app/ui/section-head.ts` with:

```ts
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * The band at the top of a workspace or panel: a heading, and optionally the
 * controls that act on what it names.
 *
 * All seven workspaces hand-rolled this as `.head` with the same four-line
 * flex rule, which is how seven slightly different gaps and two different
 * heading sizes arrived. The level is an input rather than inferred, because
 * a panel inside a workspace needs an h2 under the workspace's h1 and only
 * the caller knows which it is -- an inferred level would silently produce
 * two h1s on one page.
 *
 * Slots (v80 D4):
 *  - `[back]` renders before the heading, always, whatever order the caller
 *    writes. A back link after a title reads as a second action.
 *  - `[status]` sits beside the heading and is for FRESHNESS only: as-of,
 *    stale, counts. It is what Trade detail's rich heading needed
 *    (primitives.spec.ts's PROMOTED_ALLOWLIST), without a `heading` template.
 *  - `[actions]` is deprecated. Controls move into a filter bar or a panel
 *    header in Migration, and this slot goes with them.
 */
@Component({
  selector: 'sb-section-head',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="title-group">
      <ng-content select="[back]" />
      @if (level() === 1) {
        <h1>{{ heading() }}</h1>
      } @else {
        <h2>{{ heading() }}</h2>
      }
      <span class="status"><ng-content select="[status]" /></span>
    </div>
    <div class="actions"><ng-content select="[actions]" /></div>
  `,
  styles: `
    :host {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: var(--space-10);
    }
    /* Baseline, so a status line in chip-sized text sits on the heading's
       baseline rather than floating at its middle. min-width: 0 lets the
       group shrink inside the flex row, which is what lets the title wrap. */
    .title-group {
      display: flex;
      align-items: baseline;
      flex-wrap: wrap;
      gap: var(--space-4) var(--space-10);
      min-width: 0;
    }
    /* margin: 0 -- five of the seven call sites this replaces reset it
       explicitly; without it the browser's default heading margin sits
       inside the flex row as unabsorbed space (flex items don't collapse
       margins the way block layout does), unevenly padding the header. */
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; overflow-wrap: anywhere; }
    h2 { margin: 0; font-size: var(--text-subhead); font-weight: 600; overflow-wrap: anywhere; }
    .status {
      display: inline-flex;
      align-items: baseline;
      gap: var(--space-8);
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }
    .status:empty { display: none; }
    .actions { display: contents; }
  `,
})
export class SectionHead {
  readonly heading = input.required<string>();
  readonly level = input<1 | 2>(1);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/section-head.spec.ts')`

Expected: PASS, including the three original tests (`emits exactly one heading element` still holds).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/section-head.ts frontend/src/app/ui/section-head.spec.ts
git commit -m "feat(v80): section head back and status slots, actions deprecated"
```
