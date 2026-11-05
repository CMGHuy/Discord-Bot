# v195 — Graphite, Part 5: one pager and never-collapsed columns; the `search` icon and `Hint.anchor`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-14:" -A 400 <this file>`.

**Scope of this part (V195-13..V195-14; V195-15 is in Part 5b):** the last primitive (tables) and the two shell building blocks the rail needs before the shell is rebuilt in Part 6. V195-13 deletes `sb-data-table`'s top pager (spec correction 7), moves cell padding onto V195-6's density tokens, pins the hairline rows and the muted micro header, and stops the columns the partner acts on from collapsing on a tablet (correction 8: `stop_loss` and `tier` on the trade table). V195-14 adds the `search` icon (correction 1) and `Hint`'s anchor mode, the label popover the rail uses because a hint's `<button>` cannot nest inside a nav `<a>` (correction 10). V195-15 creates the four-group nav model, the phone tabs, the breadcrumb derivation and the `sb-breadcrumb` component, and gives `RouteTitleService` a `detail` channel for detail routes (§5.1, Phase 3). Nothing in this part changes what the shell renders yet: V195-16 consumes all three.

**Where commands run.** Shell state does not persist between Bash calls and `cd` breaks the guardrail hooks, so every command below spells out the worktree path:

- `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`
- `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`

Frontend runs through `npm --prefix "$WT/frontend" ...`. Edit files only under `$WT/`; never the main tree's copies.

**The state earlier tasks leave (read before editing).** After V195-12, in `$WT`:

- `frontend/src/styles/tokens.css` (V195-6): `--row-h` 28px dense / 44px comfortable on a desktop fine pointer / 44px touch; `--cell-pad-y` / `--cell-pad-x` are `var(--space-4)` / `var(--space-8)` dense, `var(--space-10)` / `var(--space-14)` comfortable, `var(--space-10)` / `var(--space-10)` touch. `spacing.spec.ts` therefore finds both tokens defined.
- `frontend/src/app/ui/data-table/data-table.ts`: V195-12 changed only the `.loading-spinner` rule's `border-top-color` (to `var(--text-secondary)`) and its comment. The two pager blocks, `showHeaderPager`, `#pagerTemplate` and the `th, td` rule are as on `main`.
- `frontend/src/app/workspaces/dashboard/dashboard.ts`: V195-8 renamed the close-all button's variant to `danger-quiet`; the `DASHBOARD_COLUMNS` docblock and constant are as on `main`. `dashboard.spec.ts`: v194 (V194-1b, V194-4, V194-13) edited it; the `describe('DASHBOARD_COLUMNS', ...)` block is as on `main`.
- `frontend/src/app/ui/hint.ts` and `hint.spec.ts`: as v194 left them (V194-1b `supportsPopover`, the `#pop` view child, `native`, `shown`, `show()`/`hide()`; V194-2 `POP_GAP`, `clamp`, `clampPopover`, the clamped `reposition` and the `requestAnimationFrame` re-measure; V194-2b `DIALOG_CLOSING_EVENT` and `watchHostDialog()`); `hint.spec.ts` imports `POPOVER_OPEN_ATTR` from `../testing/popover-polyfill` and reads `isOpen()` through it. No v195 task before this one edits either file.
- `frontend/src/app/ui/icon.ts`, `frontend/src/app/routing/route-title.service.ts` and their specs: as on `main` (v194 lists `ui/icon.ts`'s host `title` in `title-usage.allow.ts` as a control name; this part leaves that binding alone).

v194 and V195-6..V195-12 edited several of these files: every step below names its edit by symbol or by the exact string, never by line number. Re-read each file before editing it.

# Phase 2 — Primitives (tables)

### Task V195-13: Tables: one pager at the bottom (top pager deleted), density-driven rows, muted micro header; never-collapsed columns (ticker, side, stop, risk money where carried, R/P&L, badge tier)
**Model:** sonnet — a template deletion and a padding swap in the load-bearing table plus a badge column and two `inlineFrom` floors; the care is in moving the pinning specs (two pagers → one) without loosening the phone-row rules beside them.

**Files:**
- Modify: `frontend/src/app/ui/data-table/data-table.ts` (template: the top `@if (showHeaderPager() ...)` block deleted, the bottom pager outlet inlined, `#pagerTemplate` deleted; styles: the `th, td` rule's padding and a comment above it; class: the `showHeaderPager` computed and its docblock deleted)
- Modify: `frontend/src/app/ui/data-table/data-table.spec.ts` (the `DataTable single pager below md` describe replaced; one new describe at the end)
- Modify: `frontend/src/app/workspaces/trades/trades.columns.ts` (`badge` added to `COMPACT_COLUMNS` and `FULL_COLUMNS`; a new `badge` column; `stop_loss` and `tier` floors; new export `NEVER_COLLAPSED_COLUMNS` and its docblock)
- Modify: `frontend/src/app/workspaces/trades/trades.columns.spec.ts` (imports; five existing cases amended; a phone host and two new describes)
- Modify: `frontend/src/app/ui/pagination.ts` (the `.bar` rule's padding and its comment)
- Modify: `frontend/src/app/ui/pagination.spec.ts` (one new describe)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (the `DASHBOARD_COLUMNS` docblock only)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (imports; one new case in `describe('DASHBOARD_COLUMNS', ...)`)

**Interfaces:**
- Consumes: `DataTable` (`activePagination`, `activeShowPerPage`, `perPageChoice`, `onPage`, `onPerPage`, `viewportAt`), `PaginationComponent` (`pagination`, `showPerPage`, `announce`, `perPageChoice`, `pageChange`, `perPageChange`; its `navOnly` input stays, now unused by the table), `isInline(inlineFrom, viewport)` (`ui/priority.ts`), `tradeColumns()`, `COMPACT_COLUMNS`, `FULL_COLUMNS`, `compactLines` (`ui/data-table/compact.ts`), `text()` (`ui/format.ts`), `TradeRow.badge` (`'VALIDATED' | 'WEAK' | null`, the field the row expansion's `Badge` line reads), `DASHBOARD_COLUMNS`, the V195-6 tokens `--row-h`, `--cell-pad-y`, `--cell-pad-x`, `.sb-label` (styles.css: mono, `--text-micro`, `--text-muted`).
- Produces:
  - `DataTable.showHeaderPager` is deleted. Every paginated `sb-data-table` renders exactly one `sb-pagination`, after the table (or the phone list) and the empty state, with `announce` on and per-page when the call site asks for it.
  - Cells pad with `var(--cell-pad-y) var(--cell-pad-x)`; body rows stay `height: var(--row-h)`; rows divide with `1px solid var(--border)`; header cells keep `class="sb-label"` (muted micro), never `--text-faint`.
  - A strategy-badge column: `{ key: 'badge', header: 'Badge', value: (row) => text(row.badge), inlineFrom: 'xs', compact: { line: 2, order: 3 } }`, in both default sets (`COMPACT_COLUMNS` and `FULL_COLUMNS`, right after `direction`). Never collapsed on any device: inline from `xs`, and on the phone card's line 2 after the plan and status. The word itself (`VALIDATED` / `WEAK`) is the cue, so colour is never the only one; there is no badge-chip primitive to reuse (`sb-quality-chip` is the tier's A/B/C ramp), so the cell is the column's text value, which Trades, Dashboard, the phone card and the row drawer all render without a template.
  - `NEVER_COLLAPSED_COLUMNS` (exported from `trades.columns.ts`): `['ticker', 'direction', 'plan', 'stop_loss', 'pnl_pct', 'r_multiple', 'tier', 'badge'] as const`. Each is inline at `sm` and above in `tradeColumns()`, so in Trades and in Dashboard's Open positions (`DASHBOARD_COLUMNS` is `tradeColumns()`); `badge` also at `xs`. `stop_loss` and `tier` move from `inlineFrom: 'lg'` to `'sm'`. Only this task's specs read the constant.
  - `sb-pagination`'s `.bar` pads `var(--space-10) var(--cell-pad-x)`, so the pager's left edge stays on the cells' at every density.
- Not changed, on purpose (spec correction 8): no risk-$ column is added. `TradeRow` carries no risk amount, and the table that shows risk (Risk's *Exposure by position*, `risk.ts`) declares no `inlineFrom` at all, so nothing there collapses. On the phone (`xs`) card, line 2 is the plan cell (whose stop is never one tap away), the status, and now the badge.

**What changes, and what is already there.** `sb-data-table` draws two pagers from `md` up: a nav-only one over the table and a full one under it (v95 C4 already dropped the top one below `md`). Phase 2 wants one pager per table, at the bottom only, so the top block, the `showHeaderPager` computed that gated it and the shared `#pagerTemplate` (which existed only to serve the two call sites) all go, and the bottom pager becomes a plain `sb-pagination`. The density axis V195-6 added reaches the table through tokens: `--row-h` already sets the row height, and the cell padding now reads `--cell-pad-y`/`--cell-pad-x`, so a dense row is 28px with 4px/8px padding and a comfortable or touch row is 44px. The hairline divider and the muted micro header (`.sb-label` on every `th`) already exist; this task pins them. Tablet collapse already exists (`inlineFrom`, `demotedColumns`, the row expansion); correction 8 only lifts the stop and the tier off the `'lg'` floor, so a picked Stop or Tier column never drops into the expansion on a tablet. The strategy badge (VALIDATED/WEAK) had no column at all, only a line in the row expansion; it becomes a default column that never collapses, so a WEAK strategy never reads as validated for want of its label. The pager's own padding followed the old `--space-10` cell inset; it now reads `--cell-pad-x`.

- [ ] **Step 1: Write the failing table tests**

1. In `$WT/frontend/src/app/ui/data-table/data-table.spec.ts`, replace the whole block from the comment line `/* -- v95 C4 -- one pager below md ------------------------------------------ */` through the closing `});` of `describe('DataTable single pager below md', () => { ... });` with:

```ts
/* -- v195 correction 7 -- one pager, at the bottom only --------------------- */

describe('DataTable one pager, at the bottom (v195 correction 7)', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    host.pagination.set({ page: 1, perPage: 12, total: 40 });
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;

  // v95 C4 dropped the top pager below md; Phase 2 drops it everywhere. One
  // pager, where the eye already is after scanning the rows.
  it.each(['xs', 'sm', 'md', 'lg', 'xl'] as const)('renders exactly one pager at %s', (viewport) => {
    host.viewportAt.set(viewport);
    fixture.detectChanges();
    expect(el().querySelectorAll('sb-pagination')).toHaveLength(1);
  });

  it('puts the one pager after the table, not above it', () => {
    host.viewportAt.set('lg');
    fixture.detectChanges();
    const pager = el().querySelector('sb-pagination')!;
    // From the pager's own position, the table PRECEDES it.
    expect(pager.compareDocumentPosition(el().querySelector('table')!) &
      Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
  });

  it('pages from the one pager', () => {
    host.viewportAt.set('lg');
    fixture.detectChanges();
    const next = el().querySelector<HTMLButtonElement>('sb-pagination button[aria-label="Next page"]');
    expect(next).not.toBeNull();
    next!.click();
    fixture.detectChanges();
    expect(host.pages).toEqual([2]);
  });

  it('keeps no header-pager switch or nav-only copy in the source', () => {
    expect(DATA_TABLE_SOURCE).not.toContain('showHeaderPager');
    expect(DATA_TABLE_SOURCE).not.toContain('pagerTemplate');
    expect(DATA_TABLE_SOURCE).not.toMatch(/\[navOnly\]/);
  });
});
```

`DATA_TABLE_SOURCE` and `tableRule` are declared further down the file at module level, so they are initialised before any test runs. `Next page` is the next button's `aria-label` in `frontend/src/app/ui/pagination.ts`.

2. At the end of the same file, after the last `describe(...)` block, append:

```ts

/* -- v195 Phase 2 -- the table look: density rows, hairlines, muted header -- */

describe('DataTable look (v195 Phase 2)', () => {
  it('pads every cell with the row-density tokens', () => {
    // Dense 4px/8px, comfortable 10px/14px, touch 10px/10px (tokens.css, V195-6).
    expect(tableRule('th, td')).toContain('padding: var(--cell-pad-y) var(--cell-pad-x)');
    expect(tableRule('th, td')).not.toMatch(/padding: var\(--space-/);
  });

  it('sizes a body row by --row-h, so density sets its height', () => {
    expect(tableRule('tbody tr.row > td')).toContain('height: var(--row-h)');
  });

  it('divides rows with a hairline', () => {
    expect(tableRule('th, td')).toContain('border-bottom: 1px solid var(--border)');
  });

  it('sets the header in the muted micro label, never the faint rule colour', () => {
    // Correction 13: --text-faint is a rule/divider colour, not text.
    expect(DATA_TABLE_SOURCE).toMatch(/<th\s+class="sb-label"/);
    expect(DATA_TABLE_SOURCE).not.toContain('color: var(--text-faint)');
  });
});
```

3. In `$WT/frontend/src/app/ui/pagination.spec.ts`, after the closing `});` of `describe('PaginationComponent narrow layout (v167)', ...)`, insert:

```ts

describe('PaginationComponent inset (v195 Phase 2)', () => {
  it('pads sideways with the table cells\' --cell-pad-x, so the pager shares their left edge', () => {
    expect(SOURCE).toMatch(/\.bar \{[^}]*padding: var\(--space-10\) var\(--cell-pad-x\);/);
    expect(SOURCE).toContain("the table cells' --cell-pad-x inset");
  });
});
```

- [ ] **Step 2: Write the failing column tests**

1. In `$WT/frontend/src/app/workspaces/trades/trades.columns.spec.ts`, add `NEVER_COLLAPSED_COLUMNS` to the existing multi-line `import { ... } from './trades.columns';` list (after `FULL_COLUMNS`), and add these imports above it:

```ts
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { TradeRow } from '../../api/models';
import { DataTable } from '../../ui/data-table/data-table';
```

(`TRADE_SORTABLE` is already imported from `'../../api/models'`: add `TradeRow` to that line instead of a second one.) Then amend five existing cases, old → new:
   - `compact is exactly the spec list`: `'num', 'status', 'ticker', 'confidence_level', 'direction',` / `'now', 'plan', ...` → `'num', 'status', 'ticker', 'confidence_level', 'direction', 'badge',` / `'now', 'plan', ...` (the rest unchanged).
   - `full is exactly the spec list`: the same insertion of `'badge',` after `'direction',`.
   - `inlines exactly ticker, plan and P&L % at xs -- the rest is the row accordion`: rename it `inlines exactly ticker, plan, P&L % and the badge at xs -- the rest is the row accordion` and expect `['badge', 'plan', 'pnl_pct', 'ticker']`.
   - `leads line 1 with identity, direction and P&L; line 2 with the plan and status`: rename it `... line 2 with the plan, status and badge` and expect `keys(line2)` to equal `['plan', 'status', 'badge']`.
   - `declares a slot on those five columns only -- the rest is one tap away`: rename `five` → `six` and expect `['badge', 'direction', 'plan', 'pnl_pct', 'status', 'ticker']`.

2. After the closing `});` of `describe('Trades column floors', ...)`, insert:

```ts

/* -- v195 correction 8 -- what never collapses on a tablet ------------------- */

describe('never-collapsed trade columns (v195 correction 8)', () => {
  const columns = tradeColumns();
  const floor = (key: string) => columns.find((column) => column.key === key)?.inlineFrom;

  it('names ticker, side, plan, stop, P&L, R, tier and the strategy badge', () => {
    expect([...NEVER_COLLAPSED_COLUMNS]).toEqual(['ticker', 'direction', 'plan', 'stop_loss', 'pnl_pct', 'r_multiple', 'tier', 'badge']);
  });

  it('declares every never-collapsed key in tradeColumns()', () => {
    const known = new Set(columns.map((column) => column.key));
    for (const key of NEVER_COLLAPSED_COLUMNS) expect(known, `missing column def: ${key}`).toContain(key);
  });

  it.each(['sm', 'md', 'lg', 'xl'] as const)('keeps every one inline at %s -- never in the row expansion', (viewport) => {
    for (const key of NEVER_COLLAPSED_COLUMNS) {
      expect(isInline(floor(key), viewport), `${key} collapses at ${viewport}`).toBe(true);
    }
  });

  it('lifts the stop and the tier off the picker-only lg floor', () => {
    expect(floor('stop_loss')).toBe('sm');
    expect(floor('tier')).toBe('sm');
  });

  it('shows the strategy badge by default and on every device, phone card included', () => {
    expect(COMPACT_COLUMNS).toContain('badge');
    expect(FULL_COLUMNS).toContain('badge');
    expect(floor('badge')).toBe('xs');
    expect(columns.find((column) => column.key === 'badge')!.compact).toEqual({ line: 2, order: 3 });
  });

  it('reads the badge as its word, so colour is never the only cue', () => {
    const badge = columns.find((column) => column.key === 'badge')!;
    expect(badge.value!({ badge: 'WEAK' } as TradeRow)).toBe('WEAK');
    expect(badge.value!({ badge: 'VALIDATED' } as TradeRow)).toBe('VALIDATED');
    expect(badge.value!({ badge: null } as TradeRow)).toBe('—');
  });
});

@Component({
  imports: [DataTable],
  template: `<sb-data-table [rows]="rows" [columns]="columns" [visible]="visible" [rowKey]="key" viewportAt="xs" />`,
})
class PhoneTradesHost {
  readonly rows = [{ id: '1', leg_index: 0, ticker: 'NVDA', badge: 'WEAK' } as unknown as TradeRow];
  readonly columns = tradeColumns().filter((column) => column.key === 'ticker' || column.key === 'badge');
  readonly visible = ['ticker', 'badge'];
  readonly key = (row: TradeRow) => row.id;
}

describe('the strategy badge on a phone (v195 correction 8)', () => {
  it('renders a WEAK row as WEAK on the 390px card, not behind a tap', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(PhoneTradesHost);
    fixture.detectChanges();
    const cell = (fixture.nativeElement as HTMLElement).querySelector('.compact-row [data-col="badge"]');
    expect(cell).not.toBeNull();
    expect(cell!.textContent!.trim()).toBe('WEAK');
  });
});
```

`value` is declared optional on `ColumnDef`, hence the `!`; `ABSENT` is the em dash (`ui/format.ts`). The host keeps to the two columns whose `value` functions read only `ticker` and `badge`, so the sparse fixture row is enough.

The existing `inlines exactly ticker, plan and P&L % at xs` case stays as it is and must stay green: `'sm'` is not inline at `xs`.

3. In `$WT/frontend/src/app/workspaces/dashboard/dashboard.spec.ts`:
   - Add `import { isInline } from '../../ui/priority';` and `import { NEVER_COLLAPSED_COLUMNS } from '../trades/trades.columns';` after `import { PositionsTable } from './positions-table';`, unless a line already imports from either module (then add the name to that line).
   - Inside `describe('DASHBOARD_COLUMNS', () => { ... })`, after the `reuses tradeColumns() rather than a second, driftable floor list` case, add:

```ts

  it('keeps the never-collapsed columns, the badge among them, inline on a tablet (v195 correction 8)', () => {
    // Open positions is where a stop is checked before acting: it must not sit
    // one tap away in the row expansion at 640-1023px.
    for (const key of NEVER_COLLAPSED_COLUMNS) {
      const column = DASHBOARD_COLUMNS.find((c) => c.key === key);
      expect(column, `missing column: ${key}`).toBeDefined();
      expect(isInline(column!.inlineFrom, 'sm'), `${key} collapses at sm`).toBe(true);
    }
  });
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/data-table/data-table.spec.ts --include src/app/workspaces/trades/trades.columns.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/ui/pagination.spec.ts
```

Expected: FAIL. `trades.columns.spec.ts` and `dashboard.spec.ts` do not compile (`NEVER_COLLAPSED_COLUMNS` is not exported). In `data-table.spec.ts`, `renders exactly one pager at md`, `at lg` and `at xl` (two pagers today), `keeps no header-pager switch or nav-only copy in the source` and `pads every cell with the row-density tokens` fail; `at xs`, `at sm`, `puts the one pager after the table`, `pages from the one pager` and the other three look cases already pass. `pagination.spec.ts`: `pads sideways with the table cells' --cell-pad-x ...` fails.

- [ ] **Step 4: One pager in `data-table.ts`**

Re-read `$WT/frontend/src/app/ui/data-table/data-table.ts` first.

1. In the template, delete these three lines (directly after the `@if (showSpinner()) { ... }` block, before `@if (sortOptions().length) {`):

```html
      @if (showHeaderPager() && activePagination(); as page) {
        <ng-container [ngTemplateOutlet]="pagerTemplate" [ngTemplateOutletContext]="{ $implicit: page, announce: false }" />
      }
```

2. In the template, the bottom pager (after the `@if (showEmptyState(); as state) { ... }` block), old → new:

```html
      @if (activePagination(); as page) {
        <ng-container [ngTemplateOutlet]="pagerTemplate" [ngTemplateOutletContext]="{ $implicit: page, announce: true }" />
      }
```

```html
      <!-- v195 correction 7: one pager per table, at the bottom only. -->
      @if (activePagination(); as page) {
        <sb-pagination [pagination]="page" [showPerPage]="activeShowPerPage()" [announce]="true"
          [perPageChoice]="perPageChoice()"
          (pageChange)="onPage($event)" (perPageChange)="onPerPage($event)" />
      }
```

3. In the template, delete the whole pager template and the blank line before it:

```html
    <ng-template #pagerTemplate let-page let-announce="announce">
      <sb-pagination [pagination]="page" [showPerPage]="activeShowPerPage()" [announce]="announce" [navOnly]="!announce"
        [perPageChoice]="perPageChoice()"
        (pageChange)="onPage($event)" (perPageChange)="onPerPage($event)" />
    </ng-template>
```

`NgTemplateOutlet` stays imported: `#cellTemplate`, the expansion and the row drawer still use it.

4. In the class, delete the computed and its docblock:

```ts
  /** One pager below md — v95 C4. Two pagers cost ~250px on a phone, more
   *  than the five rows between them; the footer one (which also carries
   *  per-page) stays, so the reader's eye is already there after scanning
   *  the rows. */
  protected readonly showHeaderPager = computed(
    () => isInline('md', this.viewport()),
  );
```

`isInline` stays imported (`inlineColumns` uses it), and so does `computed`. Then `git -C "$WT" grep -n "pager" -- frontend/src/app/ui/data-table/data-table.ts`: any remaining comment that speaks of two pagers or a header pager is rewritten to say there is one pager, below the rows (v195 correction 7); comments about "the pager" alone stay.

- [ ] **Step 5: Density padding in `data-table.ts`**

In the `styles`, the `th, td` rule, old → new (the long wrapping comment above the rule stays where it is; the new comment goes between it and the rule):

```css
    th, td {
      padding: var(--space-6) var(--space-10);
```

```css
    /* v195 §1.4: cell padding follows row density (tokens.css: 4px/8px dense,
       10px/14px comfortable, 10px/10px on touch), as --row-h does the height. */
    th, td {
      padding: var(--cell-pad-y) var(--cell-pad-x);
```

The rest of the rule (`text-align`, the `border-bottom` hairline, `overflow-wrap`, `vertical-align: middle`) is unchanged; `vertical-centre.spec.ts` reads `vertical-align: middle` from the same rule.

Then in `$WT/frontend/src/app/ui/pagination.ts` `styles`, in the comment above `:host`, old → new: `Padding matches` / `the table cells' --space-10 inset so everything shares one left edge. */` → `Horizontal padding is` / `the table cells' --cell-pad-x inset (v195) so everything shares one left edge. */`; and in the `.bar` rule change `padding: var(--space-10);` to `padding: var(--space-10) var(--cell-pad-x);`.

- [ ] **Step 6: The badge column and the never-collapsed floors in `trades.columns.ts`**

Re-read `$WT/frontend/src/app/workspaces/trades/trades.columns.ts` first.

0. In `COMPACT_COLUMNS` and in `FULL_COLUMNS`, insert `'badge',` on its own line after `'direction',`. In `tradeColumns()`, after the `direction` column's line, insert:

```ts
    // v195 correction 8: the strategy badge (VALIDATED / WEAK) is a default
    // column that never collapses, phone card included -- a WEAK strategy
    // must never read as validated. The word is the cue; no colour needed.
    { key: 'badge', header: 'Badge', value: (row) => text(row.badge), inlineFrom: 'xs', compact: { line: 2, order: 3 } },
```

`text` is already imported from `'../../ui/format'`.

1. In `tradeColumns()`, old → new:

```ts
    { key: 'stop_loss', header: 'Stop', value: (row) => num(row.stop_loss), numeric: true, inlineFrom: 'lg' },
```

```ts
    // v195 correction 8: never collapsed on a tablet (NEVER_COLLAPSED_COLUMNS).
    { key: 'stop_loss', header: 'Stop', value: (row) => num(row.stop_loss), numeric: true, inlineFrom: 'sm' },
```

and old → new:

```ts
    { key: 'tier', header: 'Tier', inlineFrom: 'lg' },
```

```ts
    { key: 'tier', header: 'Tier', inlineFrom: 'sm' },
```

2. Directly above the `/* Column floors — v95 C2, amended 2026-09-28.` comment, insert:

```ts
/**
 * The columns that never collapse into the row expansion on a tablet or
 * desktop -- v195 Phase 2, spec correction 8. Ticker, side, the plan (entry,
 * target and stop in one cell), the stop on its own, P&L, R, the tier and
 * the strategy badge stay in the priority columns wherever they are shown,
 * so a stop is never one tap away and a WEAK strategy never reads as
 * validated. `stop_loss` and `tier` are picker columns (in neither default
 * set): this fixes where they sit once picked. `badge` is a default column
 * and the one that also holds on a phone (`xs` floor, card line 2). TradeRow
 * has no risk amount, so no risk-$ column exists to protect here (Risk's own
 * table declares no floors at all).
 */
export const NEVER_COLLAPSED_COLUMNS = ['ticker', 'direction', 'plan', 'stop_loss', 'pnl_pct', 'r_multiple', 'tier', 'badge'] as const;

```

3. In the `/* Column floors — v95 C2, amended 2026-09-28.` comment, after its last paragraph (before the closing ` */`), add:

```ts
 *
 * v195 (correction 8): Stop and Tier take the `sm` floor, not `lg`, so on a
 * tablet a picked Stop or Tier column stays in the row; the new Badge
 * column is inline at every width. See NEVER_COLLAPSED_COLUMNS above.
```

- [ ] **Step 7: Note the floors where Dashboard reuses them**

In `$WT/frontend/src/app/workspaces/dashboard/dashboard.ts`, in the docblock above `export const DASHBOARD_COLUMNS = tradeColumns();`, old → new (its last sentence):

```ts
 * default: the gate reads `inlineFrom`, never a cell's rendered value, so
 * which instant it is does not matter here. */
```

```ts
 * default: the gate reads `inlineFrom`, never a cell's rendered value, so
 * which instant it is does not matter here.
 *
 * v195 correction 8: the same function carries NEVER_COLLAPSED_COLUMNS
 * (trades.columns.ts), so Open positions keeps ticker, side, plan, stop,
 * P&L, R, tier and the strategy badge inline on a tablet with no list of
 * its own. */
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/data-table/data-table.spec.ts --include src/app/workspaces/trades/trades.columns.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/ui/vertical-centre.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/cancels/cancels-table.spec.ts --include src/app/ui/pagination.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. `data-table.spec.ts`'s compact-rows case `keeps the pager, below the list` still finds the one pager after the list; `vertical-centre.spec.ts` still reads `vertical-align: middle` from `th, td`; `spacing.spec.ts` finds `--cell-pad-y`/`--cell-pad-x` defined (V195-6); `trades.spec.ts` still finds its pager (now the only one) and its column picker.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. A Trades or Dashboard spec that lists a default row's cells or headers in full gains `Badge` after the side column: add it to that expectation, never drop the column. A workspace spec that clicked the *first* `sb-pagination`'s button and expected the nav-only (top) pager now lands on the bottom one, which has the same nav buttons; a spec that counted two pagers is a missed pin: assert one, never restore the top pager.

- [ ] **Step 9: Check the look at three widths**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`, then click through to Trades. Before the pass, add Stop and Tier with the Trades column picker. At 1440 (fine pointer): one pager under the table, none above; rows 28px with tight padding; header in the muted caps label; then switch Density to Comfortable through `localStorage.setItem('ui.density', 'comfortable')` and a reload (the profile-menu control lands in V195-17): rows 44px, padding 10px/14px. At 768: Stop and Tier sit in the row, not in the expansion; rows 44px (touch block). At 390: the phone card shows ticker, side and P&L on line 1 and the plan (with the stop), status and badge on line 2, with the one pager under the list. At every width a WEAK row reads `WEAK` in the Badge column, on Trades and in Dashboard's Open positions; the pager's left edge lines up with the first column's text. Save the PNGs under the session scratchpad.

- [ ] **Step 10: Close**

Close: standard (test: `frontend/src/app/ui/data-table/data-table.spec.ts`), plus `frontend/src/app/workspaces/trades/trades.columns.spec.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` and `frontend/src/app/ui/pagination.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/data-table/data-table.spec.ts frontend/src/app/workspaces/trades/trades.columns.ts frontend/src/app/workspaces/trades/trades.columns.spec.ts frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts frontend/src/app/ui/pagination.ts frontend/src/app/ui/pagination.spec.ts
git -C "$WT" commit -m "feat(v195): one table pager at the bottom, density cell padding, a never-collapsed strategy-badge column (V195-13)" -m "Phase 2, spec corrections 7 and 8: sb-data-table loses its top pager (showHeaderPager and the shared pager template go; the v95 C4 'one pager below md, two above' spec now asserts one pager at every width, after the rows). Cells pad with --cell-pad-y/--cell-pad-x so row density sets padding as well as --row-h; the hairline rows and the muted micro header are pinned. The pager's side padding reads --cell-pad-x so it keeps the cells' left edge. A Badge column (VALIDATED/WEAK, the field the row expansion already showed) joins both default sets, inline at every width and on the phone card; Stop and Tier take the sm floor; NEVER_COLLAPSED_COLUMNS pins ticker, side, plan, stop, P&L, R, tier and badge inline from sm up in Trades and Dashboard's Open positions." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

# Phase 3 — Shell (building blocks)

### Task V195-14: `search` icon; `Hint.anchor` label mode (sibling popover opened by the anchor's hover and focus, no extra tab stop)
**Model:** sonnet — one icon and one new input on a component v194 just rebuilt; the care is in reusing v194's open/show/hide machinery so anchor mode adds listeners, not a second popover path.

**Files:**
- Modify: `frontend/src/app/ui/icon.ts` (`ICON_NAMES` gains `'search'`; `PATHS`: `search` takes the magnifier, `research` is redrawn as a flask; `LABELS` gains `search`)
- Modify: `frontend/src/app/ui/icon.spec.ts` (two new cases; `'search'` in the shell list)
- Modify: `frontend/src/app/ui/hint.ts` (new export `placeBeside` after `DIALOG_CLOSING_EVENT`; class docblock; host binding; template: the trigger behind `@if (!anchor())`, a `label` class on `.pop`; two style rules; the `anchor` input; `reposition`; one constructor effect; new private `bindAnchor`)
- Modify: `frontend/src/app/ui/hint.spec.ts` (imports; a second host component; one new `describe` block at the end)

**Interfaces:**
- Consumes: v194's `Hint` internals: `open`, `hovered`, `focused`, `close()`, `id`, `pop` (view child), `reposition`, `POP_GAP`, `clamp`, `clampPopover(trigger, pop, viewport, align, margin = 8)`, `DIALOG_CLOSING_EVENT`; `POPOVER_OPEN_ATTR` (`frontend/src/app/testing/popover-polyfill.ts`, already imported by `hint.spec.ts`); `ICON_NAMES`, `IconName`, `Icon`.
- Produces (V195-16 and V195-18 consume these):
  - `'search'` in `ICON_NAMES` (so `IconName` accepts it), drawn as the magnifier, default label `Search`. `research` keeps its name and gets a flask glyph, so the rail's Research entry and the top bar's search trigger never share a glyph on an icon-only rail.
  - `Hint.anchor = input<HTMLElement | null>(null)`. Non-null: no trigger button is rendered (no extra tab stop); the popover opens on the anchor's `mouseenter` and `focus`, closes on `mouseleave`, `blur` and Escape on the anchor (plus the existing outside-pointer and dialog-close rules); the anchor gets `aria-describedby` = the popover's id while bound; the popover sits beside the anchor (right, vertically centred, clamped 8px inside the viewport) with the one-line `.pop.label` style; the host gets class `anchored` (`display: contents`). Null: exactly v194's behaviour.
  - `placeBeside(anchor: { top: number; bottom: number; left: number; right: number; width: number }, pop: { width: number; height: number }, viewport: { width: number; height: number }, margin = 8): { top: number; left: number }` (exported from `hint.ts`; pure; used by `reposition` in anchor mode and by the spec). Not in the ledger row because nothing outside `hint.ts` and its spec reads it.
  - Usage V195-16 writes: `<a #link class="rail-link" [routerLink]="entry.path" [attr.aria-label]="entry.label">…</a><sb-hint [anchor]="link" [text]="entry.label" />`.

**What changes, and what is already there.** The rail shows each entry's label on hover and keyboard focus (spec Phase 3). `sb-hint` is a glyph `<button>` with its popover, and a button cannot sit inside the rail's `<a>` (interactive content in interactive content), so correction 10 asks for a label mode: the hint sits beside the link and listens to the link. v194 already gave `Hint` everything the label needs: a native top-layer popover (`popover="manual"`, guarded `show`/`hide`), one `open` computed fed by `hovered`/`focused`/`pinned`, the viewport clamp and the dialog-close rule. Anchor mode adds only the wiring: the anchor's events set the same `hovered`/`focused` signals, the trigger button is not rendered, and `reposition` measures the anchor and places the label to its right (a label under a 48px rail icon would cover the next entry). Escape on the anchor dismisses the label without moving focus (WCAG 1.4.13). The magnifier glyph is today's `research` icon; giving it to `search` and drawing Research a flask keeps one meaning per glyph, which an always-collapsed rail depends on (spec § Risks, icon recognition).

- [ ] **Step 1: Write the failing icon tests**

In `$WT/frontend/src/app/ui/icon.spec.ts`:

1. In `it('covers every name the shell needs', ...)`, change the list `['dashboard', 'trades', 'analytics', 'watchlist', 'risk',` / `'system', 'collapse', 'expand', 'profile', 'signout', 'menu']` to `['dashboard', 'trades', 'analytics', 'watchlist', 'risk',` / `'system', 'collapse', 'expand', 'profile', 'signout', 'menu', 'search']`.

2. After `it('renders the brand icon (R1-14)', ...)`, inside the same describe, add:

```ts

  it('carries the search glyph the top bar and the phone bar use (v195 correction 1)', () => {
    expect(ICON_NAMES).toContain('search');
    expect(render('search').querySelector('svg path')).not.toBeNull();
    // Named by its default label when the caller gives none.
    expect(render('search').getAttribute('title')).toBe('Search');
  });

  it('never draws two names with the same glyph -- an icon-only rail reads by shape', () => {
    const glyphs = new Map<string, string>();
    for (const name of ICON_NAMES) {
      const d = render(name).querySelector('svg path')!.getAttribute('d')!;
      expect(glyphs.get(d), `${name} draws the same glyph as ${glyphs.get(d)}`).toBeUndefined();
      glyphs.set(d, name);
    }
  });
```

- [ ] **Step 2: Write the failing anchor-mode tests**

In `$WT/frontend/src/app/ui/hint.spec.ts` (re-read it first; v194 left its imports and blocks):

1. Make sure `signal` is in the `@angular/core` import (add it to that line if it is not there), and add `placeBeside` to the `import { ... } from './hint';` list.

2. Directly after the existing `class Host {}` (the v80 host component), add a second host:

```ts

/** v195 correction 10: a rail-style link with its label hint beside it. */
@Component({
  imports: [Hint],
  template: `
    <a #link href="/dashboard" class="rail-link" aria-label="Dashboard">D</a>
    <sb-hint [anchor]="anchored() ? link : null" text="Dashboard" />
    <span class="outside">Elsewhere</span>
  `,
})
class AnchorHost {
  readonly anchored = signal(true);
}
```

3. At the end of the file, after the last `describe(...)` block, append:

```ts

describe('Hint anchor (label) mode (v195 correction 10)', () => {
  let fixture: ComponentFixture<AnchorHost>;

  beforeEach(async () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(AnchorHost);
    fixture.detectChanges();
    await fixture.whenStable();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const link = () => el().querySelector('a.rail-link') as HTMLAnchorElement;
  const pop = () => el().querySelector('sb-hint [role=tooltip]') as HTMLElement;
  const fire = async (target: Element, event: Event) => {
    target.dispatchEvent(event);
    fixture.detectChanges();
    await fixture.whenStable();
  };
  const isOpen = () => pop().hasAttribute(POPOVER_OPEN_ATTR);

  it('renders no trigger button, so the rail link stays the only tab stop', () => {
    expect(el().querySelectorAll('sb-hint button')).toHaveLength(0);
    expect(pop().hasAttribute('tabindex')).toBe(false);
    expect(el().querySelector('sb-hint')!.classList).toContain('anchored');
  });

  it('describes the anchor with the label popover, closed at rest', () => {
    expect(link().getAttribute('aria-describedby')).toBe(pop().id);
    expect(pop().textContent!.trim()).toBe('Dashboard');
    expect(pop().classList).toContain('label');
    expect(isOpen()).toBe(false);
  });

  it('opens on the anchor hover and closes when the pointer leaves it', async () => {
    await fire(link(), new MouseEvent('mouseenter'));
    expect(isOpen()).toBe(true);
    await fire(link(), new MouseEvent('mouseleave'));
    expect(isOpen()).toBe(false);
  });

  it('opens on the anchor keyboard focus and closes on blur', async () => {
    await fire(link(), new FocusEvent('focus'));
    expect(isOpen()).toBe(true);
    await fire(link(), new FocusEvent('blur'));
    expect(isOpen()).toBe(false);
  });

  it('closes on Escape on the anchor without moving focus away', async () => {
    await fire(link(), new FocusEvent('focus'));
    await fire(link(), new MouseEvent('mouseenter'));
    expect(isOpen()).toBe(true);
    await fire(link(), new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(isOpen()).toBe(false);
  });

  it('ignores other keys on the anchor', async () => {
    await fire(link(), new FocusEvent('focus'));
    await fire(link(), new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(isOpen()).toBe(true);
  });

  it('unbinds when the anchor goes away and falls back to the glyph trigger', async () => {
    await fire(link(), new MouseEvent('mouseenter'));
    expect(isOpen()).toBe(true);
    fixture.componentInstance.anchored.set(false);
    fixture.detectChanges();
    await fixture.whenStable();
    expect(isOpen()).toBe(false);
    expect(link().hasAttribute('aria-describedby')).toBe(false);
    await fire(link(), new MouseEvent('mouseenter'));
    expect(isOpen()).toBe(false);
    expect(el().querySelector('sb-hint button.trigger')).not.toBeNull();
    expect(el().querySelector('sb-hint')!.classList).not.toContain('anchored');
  });
});

describe('placeBeside (v195 correction 10)', () => {
  const rail = { top: 100, bottom: 140, left: 0, right: 48, width: 48 };
  const label = { width: 80, height: 24 };

  it('sits right of the anchor, 8px off it, vertically centred on it', () => {
    expect(placeBeside(rail, label, { width: 1440, height: 900 })).toEqual({ top: 108, left: 56 });
  });

  it('stays 8px above the bottom edge for an anchor at the foot of the screen', () => {
    const foot = { ...rail, top: 880, bottom: 900 };
    expect(placeBeside(foot, label, { width: 1440, height: 900 }).top).toBe(868);
  });

  it('stays 8px inside the top edge', () => {
    const head = { ...rail, top: 0, bottom: 10 };
    expect(placeBeside(head, label, { width: 1440, height: 900 }).top).toBe(8);
  });

  it('shifts left rather than run off a narrow viewport', () => {
    expect(placeBeside(rail, label, { width: 100, height: 900 }).left).toBe(12);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/icon.spec.ts --include src/app/ui/hint.spec.ts
```

Expected: FAIL. `icon.spec.ts`: `covers every name the shell needs` and `carries the search glyph ...` fail (`search` missing); `never draws two names with the same glyph` passes today and must still pass after Step 4 (it is the guard against giving `search` the magnifier while `research` keeps it). `hint.spec.ts` does not compile (`placeBeside` is not exported; `anchor` is not a known input of `sb-hint`).

- [ ] **Step 4: The `search` icon**

In `$WT/frontend/src/app/ui/icon.ts`:

1. In `ICON_NAMES`, after `'research',` add `'search',`.

2. In `PATHS`, the `research` entry and its comment, old → new:

```ts
  // A magnifying glass: looking something up, not watching a live list --
  // distinct from `watchlist`'s eye, which Research wrongly reused before
  // (2026-09-14; nav duplicated a glyph across two different sidebar
  // entries).
  research: 'M7.2 12A4.8 4.8 0 1 0 7.2 2.4a4.8 4.8 0 0 0 0 9.6z M10.7 10.7l3.3 3.3',
```

```ts
  // A flask: experiments and their verdicts -- the strategy registry and the
  // pre-registration ledger. Research had the magnifier until v195, which
  // gave it to `search` (below): on an always-collapsed rail, a magnifier
  // entry beside a magnifier search trigger would read as one control.
  research: 'M6 1.5h4 M6.5 1.5v4.2L2.6 12.6a1.2 1.2 0 0 0 1 1.9h8.8a1.2 1.2 0 0 0 1-1.9L9.5 5.7V1.5 M4.3 10h7.4',
  // A magnifying glass: the command palette's trigger in the top bar and the
  // phone bar's search icon (v195 correction 1).
  search: 'M7.2 12A4.8 4.8 0 1 0 7.2 2.4a4.8 4.8 0 0 0 0 9.6z M10.7 10.7l3.3 3.3',
```

3. In `LABELS`, change `reports: 'Reports', research: 'Research',` to `reports: 'Reports', research: 'Research', search: 'Search',`.

- [ ] **Step 5: Anchor mode in `hint.ts`**

Re-read `$WT/frontend/src/app/ui/hint.ts` first (v194's shape: `supportsPopover`, `POP_GAP`, `clamp`, `clampPopover`, `DIALOG_CLOSING_EVENT`, then the component).

1. After the `export const DIALOG_CLOSING_EVENT = 'sb-dialog-closing';` line, insert:

```ts

/**
 * Where an anchor-mode label goes (v195 correction 10): to the right of its
 * anchor, two gaps off it, vertically centred on it, and kept `margin` px
 * inside the viewport -- shifted up off the bottom edge, down off the top,
 * left off the right. A rail label under its 48px icon would cover the next
 * entry, so it goes beside. Pure, like clampPopover.
 */
export function placeBeside(
  anchor: { top: number; bottom: number; left: number; right: number; width: number },
  pop: { width: number; height: number },
  viewport: { width: number; height: number },
  margin = 8,
): { top: number; left: number } {
  const centre = (anchor.top + anchor.bottom) / 2;
  return {
    top: clamp(centre - pop.height / 2, margin, viewport.height - margin - pop.height),
    left: clamp(anchor.right + 2 * POP_GAP, margin, viewport.width - margin - pop.width),
  };
}
```

2. In the class docblock above `@Component({` (the one starting `An info popover -- spec v80 D4.`), before its closing ` */`, append:

```ts
 *
 * Anchor (label) mode, v195 correction 10: with `anchor` set, no trigger is
 * rendered and the popover labels that element instead -- a rail link, which
 * cannot contain a button. The anchor's own hover and focus open it, Escape
 * on the anchor closes it, the anchor is described by it, and it sits beside
 * the anchor (placeBeside) as a one-line label. Everything else -- the top
 * layer, the guards, the dialog-close rule -- is the same machinery.
```

3. In the `host: { ... }` object, after `'(document:pointerdown)': 'onDocumentPointer($event)',` add:

```ts
    '[class.anchored]': 'anchor() !== null',
```

4. In the template, wrap the trigger button in `@if (!anchor()) { ... }` and mark the popover as a label in anchor mode, old → new (the button's attributes are as v194 left them; keep them exactly):

```html
    <button
      type="button"
      class="trigger"
```

```html
    @if (!anchor()) {
    <button
      type="button"
      class="trigger"
```

then, after that button's closing `</button>`, insert a line with `    }`. On the `.pop` span (it starts `<span` / `#pop` / `class="pop elev-overlay"`), add after `[class.xl]="xl()"`:

```html
      [class.label]="anchor() !== null"
```

5. In `styles`, after `.pop.fallback-closed { display: none; }` insert:

```css
    /* Anchor mode (v195 correction 10): the host has no box of its own -- the
       label lives in the top layer beside its anchor -- and the popover is a
       one-line name, not an explanation. */
    :host(.anchored) { display: contents; }
    .pop.label { padding: var(--space-4) var(--space-8); font-size: var(--text-table); white-space: nowrap; }
```

6. After the `align` input (`readonly align = input<'center' | 'left'>('center');`), insert:

```ts
  /** Anchor (label) mode, v195 correction 10: the element this hint labels.
   *  Non-null renders no trigger; the anchor's hover and focus open the
   *  popover, which sits beside it. Null (default) is the glyph trigger. */
  readonly anchor = input<HTMLElement | null>(null);
```

7. Replace `reposition` (as V194-2 left it, starting `private readonly reposition = (): void => {` and ending with `this.popLeft.set(place.left);` / `};`) in full with:

```ts
  private readonly reposition = (): void => {
    const anchor = this.anchor();
    const target = anchor ?? this.host.querySelector('.trigger');
    if (!target) return;
    const pop = this.pop().nativeElement;
    const root = document.documentElement;
    const rect = target.getBoundingClientRect();
    const size = { width: pop.offsetWidth, height: pop.offsetHeight };
    const viewport = { width: root.clientWidth, height: root.clientHeight };
    // Anchor mode labels beside its anchor; the glyph trigger opens below.
    const place = anchor ? placeBeside(rect, size, viewport) : clampPopover(rect, size, viewport, this.align());
    this.popTop.set(place.top);
    this.popLeft.set(place.left);
  };
```

8. In the constructor, after the existing `effect((onCleanup) => { ... });` (the open/show/hide one), add a second effect before the constructor's closing `}`:

```ts

    /** Anchor mode: bind the anchor's events for as long as it is set, and
     *  unbind (closing the label) when it changes or goes away. */
    effect((onCleanup) => {
      const anchor = this.anchor();
      if (anchor) onCleanup(this.bindAnchor(anchor));
    });
```

9. After `watchHostDialog()` (V194-2b's method, now the class's last), insert:

```ts

  /** Anchor mode (v195 correction 10): the anchor's hover and focus feed the
   *  same hovered/focused signals the glyph trigger does, Escape on it
   *  dismisses the label without moving focus (WCAG 1.4.13), and the anchor
   *  -- not a trigger of ours -- is described by the popover. Returns the
   *  remover, which also closes the label. */
  private bindAnchor(anchor: HTMLElement): () => void {
    const onKey = (event: Event): void => {
      if ((event as KeyboardEvent).key === 'Escape') this.close();
    };
    const listeners: [string, EventListener][] = [
      ['mouseenter', () => this.hovered.set(true)],
      ['mouseleave', () => this.hovered.set(false)],
      ['focus', () => this.focused.set(true)],
      ['blur', () => this.focused.set(false)],
      ['keydown', onKey],
    ];
    for (const [type, listener] of listeners) anchor.addEventListener(type, listener);
    anchor.setAttribute('aria-describedby', this.id);
    return () => {
      for (const [type, listener] of listeners) anchor.removeEventListener(type, listener);
      if (anchor.getAttribute('aria-describedby') === this.id) anchor.removeAttribute('aria-describedby');
      this.close();
    };
  }
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/icon.spec.ts --include src/app/ui/hint.spec.ts --include src/app/ui/layout.spec.ts --include src/app/shell/shell.spec.ts --include src/app/ui/title-usage.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. Every v80/v194 hint case is unchanged (the glyph-trigger path is the `anchor() === null` branch); `layout.spec.ts` still finds the heading hint; `shell.spec.ts` still renders the Research nav entry (now the flask); `title-usage.spec.ts` sees no new `title` attribute. If an anchor-mode `isOpen()` reads false right after `fire(...)` although the listener ran, the effect has not flushed: the `await fixture.whenStable()` in `fire` is there for that; do not change the component.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. Nothing renders anchor mode yet (V195-16 does), so no browser pass here; V195-16's Playwright pass checks the rail labels at 768 and 1440, and V195-35's `rail-label` audit check proves them on every route.

- [ ] **Step 7: Close**

Close: standard (test: `frontend/src/app/ui/hint.spec.ts`), plus `frontend/src/app/ui/icon.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/ui/icon.ts frontend/src/app/ui/icon.spec.ts frontend/src/app/ui/hint.ts frontend/src/app/ui/hint.spec.ts
git -C "$WT" commit -m "feat(v195): search icon and the Hint anchor (label) mode (V195-14)" -m "Spec corrections 1 and 10: 'search' joins ICON_NAMES with the magnifier, and Research is redrawn as a flask so no two icons share a glyph (pinned by a new icon.spec case). sb-hint gains anchor = input<HTMLElement | null>(null): with an anchor it renders no trigger, opens on the anchor's hover and focus, closes on leave, blur and Escape, describes the anchor, and places a one-line label beside it (placeBeside, pure and clamped) -- the rail's labels, since a button cannot nest in a nav link. The glyph-trigger path is unchanged." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```
