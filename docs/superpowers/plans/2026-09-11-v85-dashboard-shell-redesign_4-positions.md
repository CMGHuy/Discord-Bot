# v85 Part 4 — The tabbed positions table

Header block, global constraints, parallelisation and exit criteria live in
`2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

**Part 4 is a strict chain.** Every task builds on the previous one's component,
and R4-06 additionally consumes R2-05's endpoint. One at a time.

This part replaces four stacked `sb-trade-group` instances with one tabbed
table. The win is not only visual: today all four groups fetch on every visit,
and the tabbed version fetches only the selected tab — strictly less work.

**`TradeGroup` is used only by this workspace** (`dashboard.ts`,
`trade-group.spec.ts` and a reference in `trades.store.spec.ts`), so nothing
outside the Dashboard is affected.

---

# Phase 1 — The table

### Task R4-01: The tabbed positions table

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/positions-table.ts`
- Create: `frontend/src/app/workspaces/dashboard/positions-table.spec.ts`

**Interfaces:**
- Consumes: `TradesStore` (`setQuery`, `rows`, `pagination`), `sb-tab-bar`
  (`tabs: Tab[]` where `Tab = { id: string; label: string }`, `active: string`,
  `activeChange`), `DataTable`.
- Produces: `<sb-positions-table>` with inputs
  `counts: Record<string, number>`, `today: boolean | null`,
  `columns: ColumnDef<TradeRow>[]`, `visibleFor: (tab: string) => string[]`,
  `pinned: string[]`, `rowKey: (row: TradeRow) => string`;
  outputs `rowActivate`, `reorder`;
  and exported `POSITION_TABS`, `OPEN_POSITIONS_CAP`.

  R4-02 supplies `visibleFor`, R4-04 mounts it, R4-05/R4-06 add its actions.

- [ ] **Step 1: Write the failing test**

```ts
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TradesStore } from '../../stores/trades.store';
import { PositionsTable } from './positions-table';

describe('positions table', () => {
  let setQuery: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setQuery = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
  });

  function mount(inputs: Record<string, unknown> = {}) {
    const f = TestBed.createComponent(PositionsTable);
    // The component provides TradesStore itself; override the instance it got.
    const store = f.debugElement.injector.get(TradesStore) as unknown as {
      setQuery: unknown;
    };
    store.setQuery = setQuery;
    f.componentRef.setInput('counts', { ACTIVE: 1, PENDING: 0, PARTIAL: 0, CLOSED: 0, CANCELLED: 0 });
    for (const [k, v] of Object.entries(inputs)) f.componentRef.setInput(k, v);
    f.detectChanges();
    return f;
  }

  it('offers the five lifecycle tabs, in lifecycle order', () => {
    const f = mount();
    const labels = [...(f.nativeElement as HTMLElement).querySelectorAll('[role="tab"]')]
      .map((t) => t.textContent?.replace(/\s+/g, ' ').trim());
    expect(labels).toEqual([
      'Open positions 1', 'Pending 0', 'Partial 0', 'Closed 0', 'Cancelled 0',
    ]);
  });

  it('queries only the active tab, not all five', () => {
    mount();
    expect(setQuery).toHaveBeenCalledTimes(1);
    expect(setQuery.mock.calls[0][0]).toMatchObject({ status: 'ACTIVE' });
  });

  it('re-queries with the new status when a tab is chosen', () => {
    const f = mount();
    setQuery.mockClear();
    (f.nativeElement as HTMLElement)
      .querySelectorAll<HTMLButtonElement>('[role="tab"]')[1].click();
    f.detectChanges();
    expect(setQuery).toHaveBeenCalledTimes(1);
    expect(setQuery.mock.calls[0][0]).toMatchObject({ status: 'PENDING' });
  });

  it('passes the Today scope only to the closed and cancelled tabs', () => {
    const f = mount({ today: true });
    // ACTIVE is all-time regardless of the page scope.
    expect(setQuery.mock.calls.at(-1)![0].today).toBeUndefined();

    setQuery.mockClear();
    (f.nativeElement as HTMLElement)
      .querySelectorAll<HTMLButtonElement>('[role="tab"]')[3].click();
    f.detectChanges();
    expect(setQuery.mock.calls.at(-1)![0]).toMatchObject({ status: 'CLOSED', today: true });
  });

  it('resets to the first page when the tab changes', () => {
    const f = mount();
    setQuery.mockClear();
    (f.nativeElement as HTMLElement)
      .querySelectorAll<HTMLButtonElement>('[role="tab"]')[2].click();
    f.detectChanges();
    expect(setQuery.mock.calls.at(-1)![0]).toMatchObject({ page: 1 });
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/positions-table.spec.ts
```

Expected: FAIL — cannot resolve `./positions-table`.

- [ ] **Step 3: Write the component**

```ts
import {
  ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal, untracked,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { TradeRow } from '../../api/models';
import { TradesStore } from '../../stores/trades.store';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, EmptyState } from '../../ui/data-table/data-table.types';
import { Tab, TabBar } from '../../ui/layout';

/** A cap, not a page — the Dashboard answers "what is happening right now" at
 *  a glance, and a glance does not scroll. Paging lives in Trades. */
export const OPEN_POSITIONS_CAP = 6;

/** Lifecycle order, not size order: this is the order a plan moves through,
 *  and sorting by count would reshuffle the strip every time a trade closed. */
export const POSITION_TABS: (Tab & { status: string; scoped: boolean })[] = [
  { id: 'ACTIVE',    label: 'Open positions', status: 'ACTIVE',    scoped: false },
  { id: 'PENDING',   label: 'Pending',        status: 'PENDING',   scoped: false },
  { id: 'PARTIAL',   label: 'Partial',        status: 'PARTIAL',   scoped: false },
  { id: 'CLOSED',    label: 'Closed',         status: 'CLOSED',    scoped: true  },
  { id: 'CANCELLED', label: 'Cancelled',      status: 'CANCELLED', scoped: true  },
];

const EMPTY_STATES: Record<string, EmptyState> = {
  ACTIVE: { title: 'No active positions', hint: 'They appear here once a plan’s entry fills.' },
  PENDING: { title: 'No pending plans', hint: 'They appear here once a plan is posted, waiting for its entry trigger.' },
  PARTIAL: { title: 'No partial positions', hint: 'They appear here once TP1 hits and part of the position closes.' },
  CLOSED: { title: 'No closed trades', hint: 'They appear here once a position’s target or stop closes it out.' },
  CANCELLED: { title: 'No cancelled plans', hint: 'A plan lands here if it expires or is invalidated before filling.' },
};

/**
 * One table, five lifecycle tabs — v85 D11.
 *
 * **Only the selected tab fetches.** The four stacked groups this replaces
 * each held their own `TradesStore` and all four queried on every visit; one
 * store re-queried on tab change is strictly less work for the same answer.
 *
 * Only CLOSED and CANCELLED honour the page's Today/All scope. ACTIVE,
 * PENDING and PARTIAL are all-time by definition: a position that is open is
 * open regardless of when it opened, and narrowing those to "today" would
 * hide the book.
 */
@Component({
  selector: 'sb-positions-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TabBar, DataTable, RouterLink],
  providers: [TradesStore],
  template: `
    <sb-tab-bar [tabs]="tabs()" [active]="active()" (activeChange)="choose($event)" />

    <div class="table-head">
      <a class="all-link" routerLink="/trades" [queryParams]="{ status: active() }">
        View in Trades →
      </a>
      <ng-content select="[table-actions]" />
    </div>

    <sb-data-table
      [rows]="rows()"
      [columns]="columns()"
      [visible]="visible()"
      [pinned]="pinned()"
      [rowKey]="rowKey()"
      [emptyState]="emptyState()"
      (rowActivate)="rowActivate.emit($event)"
      (reorder)="reorder.emit($event)"
    />
  `,
  styles: `
    :host { display: block; }
    .table-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-10);
      padding: var(--space-10) var(--space-14) var(--space-4);
    }
    .all-link { color: var(--accent); font-size: var(--text-chip); text-decoration: none; }
    .all-link:hover { text-decoration: underline; }
  `,
})
export class PositionsTable {
  protected readonly trades = inject(TradesStore);

  /** Lifecycle counts from the dashboard payload, keyed by status. Rendered
   *  on the tab labels so the strip answers "how many" before it is clicked. */
  readonly counts = input<Record<string, number>>({});
  readonly today = input<boolean | null>(null);
  readonly columns = input.required<ColumnDef<TradeRow>[]>();
  /** Per-tab column order — see R4-02. Takes the tab id so each status can
   *  show the columns that mean something for it. */
  readonly visibleFor = input.required<(tab: string) => string[]>();
  readonly pinned = input<string[]>([]);
  readonly rowKey = input.required<(row: TradeRow) => string>();
  readonly cap = input(OPEN_POSITIONS_CAP);

  readonly rowActivate = output<TradeRow>();
  readonly reorder = output<string[]>();
  readonly tabChange = output<string>();

  protected readonly active = signal<string>('ACTIVE');
  private readonly page = signal(1);

  protected readonly rows = computed(() => this.trades.rows());
  protected readonly visible = computed(() => this.visibleFor()(this.active()));
  protected readonly emptyState = computed(() => EMPTY_STATES[this.active()] ?? null);

  protected readonly tabs = computed<Tab[]>(() =>
    POSITION_TABS.map((tab) => ({
      id: tab.id,
      label: `${tab.label} ${this.counts()[tab.status] ?? 0}`,
    })),
  );

  protected choose(id: string): void {
    if (id === this.active()) return;
    this.active.set(id);
    this.tabChange.emit(id);
  }

  constructor() {
    // Page resets on tab change: landing on page 3 of a table you just
    // switched to shows a slice of something you have not seen the start of.
    effect(() => {
      this.active();
      untracked(() => this.page.set(1));
    });

    // The one query. Reading `active`/`today`/`cap`/`page` here IS the
    // subscription, so a tab change re-queries without a second code path.
    effect(() => {
      const tab = POSITION_TABS.find((t) => t.id === this.active());
      this.trades.setQuery({
        status: tab?.status ?? 'ACTIVE',
        today: tab?.scoped ? (this.today() ?? undefined) : undefined,
        sort: '-opened_at',
        page: this.page(),
        per_page: this.cap(),
      });
    });
  }
}
```

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/positions-table.spec.ts
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/positions-table.ts \
        frontend/src/app/workspaces/dashboard/positions-table.spec.ts
git commit -m "feat(dashboard): add the tabbed positions table"
```

---

### Task R4-02: Per-tab column sets

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.helpers.ts`
- Test: `frontend/src/app/workspaces/dashboard/dashboard.helpers.spec.ts`

**Interfaces:**
- Consumes: `deriveOpenVisible`, `deriveClosedVisible`, already in this file.
- Produces: `deriveCancelledVisible(visible: string[]): string[]`, and
  `visibleForTab(tab: string, visible: string[]): string[]` — the function
  R4-01's `visibleFor` input is bound to.

**Cancelled needs its own set.** A plan that never filled has no entry fill, no
P&L and no R — those three columns would be an em dash on every row. What it
does have is the plan it would have taken and when it ended.

- [ ] **Step 1: Write the failing test**

```ts
import { deriveCancelledVisible, visibleForTab } from './dashboard.helpers';

const ALL = ['ticker', 'status', 'confidence_level', 'entry', 'now', 'plan',
             'pnl_pct', 'r_multiple', 'hold', 'opened_at', 'closed_at'];

it('drops the columns a never-filled plan cannot fill', () => {
  const cancelled = deriveCancelledVisible(ALL);
  for (const dead of ['now', 'pnl_pct', 'r_multiple', 'hold']) {
    expect(cancelled).not.toContain(dead);
  }
});

it('keeps what a cancelled plan does have', () => {
  const cancelled = deriveCancelledVisible(ALL);
  for (const kept of ['ticker', 'status', 'plan', 'closed_at']) {
    expect(cancelled).toContain(kept);
  }
});

it('routes each tab to its own column set', () => {
  expect(visibleForTab('ACTIVE', ALL)).toEqual(deriveOpenVisible(ALL));
  expect(visibleForTab('PENDING', ALL)).toEqual(deriveOpenVisible(ALL));
  expect(visibleForTab('PARTIAL', ALL)).toEqual(deriveOpenVisible(ALL));
  expect(visibleForTab('CLOSED', ALL)).toEqual(deriveClosedVisible(ALL));
  expect(visibleForTab('CANCELLED', ALL)).toEqual(deriveCancelledVisible(ALL));
});

it('preserves the user’s column ORDER inside each set', () => {
  const reordered = ['status', 'ticker', ...ALL.filter((c) => !['status', 'ticker'].includes(c))];
  const out = visibleForTab('ACTIVE', reordered);
  expect(out.indexOf('status')).toBeLessThan(out.indexOf('ticker'));
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.helpers.spec.ts
```

Expected: FAIL — `deriveCancelledVisible` is not exported.

- [ ] **Step 3: Add both functions**

In `dashboard.helpers.ts`, beside the two existing derivations:

```ts
/** Columns a CANCELLED plan can actually fill.
 *
 *  `now`, `pnl_pct`, `r_multiple` and `hold` all describe an execution, and a
 *  plan that never filled has none — they would render an em dash on every
 *  row, which is a column's worth of width spent saying "not applicable".
 *  `closed_at` survives and reads as when it was cancelled. */
export function deriveCancelledVisible(visible: string[]): string[] {
  const dead = new Set(['now', 'pnl_pct', 'r_multiple', 'hold']);
  return visible.filter((column) => !dead.has(column));
}

/** The column set for one lifecycle tab — v85 D11/D12. Order comes from the
 *  user's own picker list, so a reorder applies inside every tab rather than
 *  each tab keeping a private arrangement. */
export function visibleForTab(tab: string, visible: string[]): string[] {
  if (tab === 'CLOSED') return deriveClosedVisible(visible);
  if (tab === 'CANCELLED') return deriveCancelledVisible(visible);
  return deriveOpenVisible(visible);
}
```

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.helpers.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/dashboard.helpers.ts \
        frontend/src/app/workspaces/dashboard/dashboard.helpers.spec.ts
git commit -m "feat(dashboard): per-tab column sets, including cancelled"
```

---

### Task R4-03: Preferences survive a tab change

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/positions-table.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/positions-table.ts` (only if the test exposes a gap)

**Interfaces:**
- Consumes: R4-02's `visibleForTab`; `reconcileReorder` in
  `dashboard.helpers.ts`.
- Produces: no new symbol — this task is the guard that D12's promise holds.

**D12 promised no capability regression.** Column picker, density, reorder and
saved preferences all had to survive the rebuild. The riskiest of those is
reorder: `reconcileReorder` writes a drag inside ONE tab's column list back to
the shared picker list without leaking that tab's own additions or omissions
into the others. That logic is subtle and it is exactly what a rewrite loses.

- [ ] **Step 1: Write the failing test**

```ts
it('keeps a column reorder when the tab changes and changes back', () => {
  const f = mount();
  const reordered: string[][] = [];
  f.componentInstance.reorder.subscribe((order: string[]) => reordered.push(order));

  // A drag inside the ACTIVE tab emits the reconciled picker list upward.
  f.componentInstance.reorder.emit(['status', 'ticker', 'plan']);
  f.detectChanges();

  // Switch away and back; the table must ask for the same order it was given.
  clickTab(f, 'PENDING');
  clickTab(f, 'ACTIVE');
  expect(reordered.at(-1)).toEqual(['status', 'ticker', 'plan']);
});

it('asks for the right column set per tab from one shared picker list', () => {
  const seen: string[] = [];
  const f = mount({ visibleFor: (tab: string) => { seen.push(tab); return ['ticker']; } });
  clickTab(f, 'CLOSED');
  clickTab(f, 'CANCELLED');
  expect(seen).toContain('ACTIVE');
  expect(seen).toContain('CLOSED');
  expect(seen).toContain('CANCELLED');
});
```

- [ ] **Step 2: Run it**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/positions-table.spec.ts
```

If R4-01 was built correctly these may PASS immediately. That is a legitimate
outcome for a guard test — the point is to pin the behaviour before R4-04 wires
in the real preference plumbing, not to force a change. If either fails, fix
the component, not the test.

- [ ] **Step 3: Fix only what failed**

The table holds no preference state of its own — it renders `visibleFor()` and
emits `reorder` upward. If a test failed, the cause is almost certainly the
table caching a computed column list across tab changes; make `visible()` a
`computed` over both `visibleFor()` and `active()` so it recomputes on both.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/positions-table.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/positions-table.ts \
        frontend/src/app/workspaces/dashboard/positions-table.spec.ts
git commit -m "test(dashboard): pin column preferences across tab changes"
```

---

# Phase 2 — Wiring and actions

### Task R4-04: Mount the table and retire TradeGroup

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts`
- Delete: `frontend/src/app/workspaces/dashboard/trade-group.ts`
- Delete: `frontend/src/app/workspaces/dashboard/trade-group.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`
- Modify: `frontend/src/app/stores/trades.store.spec.ts` (drops a `TradeGroup` reference)

**Interfaces:**
- Consumes: `PositionsTable` (R4-01), `visibleForTab` (R4-02),
  `DashboardStore.lifecycle()`.
- Produces: the mounted table. R4-05/R4-06 project actions into its
  `[table-actions]` slot.

**Port `trade-group.spec.ts`'s tests before deleting it.** Any behaviour it
asserts that the new table also promises — the row cap, the "View in Trades"
link, the per-status empty states — moves into `positions-table.spec.ts`.
Deleting a test file wholesale is how a rewrite quietly loses coverage.

- [ ] **Step 1: Inventory what the old spec covers**

```bash
grep -n "it(" frontend/src/app/workspaces/dashboard/trade-group.spec.ts
```

Write the list down. Each entry is either ported to
`positions-table.spec.ts` or explicitly obsolete (anything asserting four
simultaneous groups is obsolete by design — D11).

- [ ] **Step 2: Write the failing test**

In `dashboard.spec.ts`:

```ts
it('renders one tabbed positions table, not four stacked groups', () => {
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  expect(el.querySelectorAll('sb-positions-table')).toHaveLength(1);
  expect(el.querySelector('sb-trade-group')).toBeNull();
});

it('feeds the tab counts from the lifecycle payload', () => {
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const labels = [...(f.nativeElement as HTMLElement).querySelectorAll('[role="tab"]')]
    .map((t) => t.textContent?.replace(/\s+/g, ' ').trim());
  expect(labels[0]).toMatch(/^Open positions \d+$/);
});
```

- [ ] **Step 3: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: FAIL — four `sb-trade-group` elements, no `sb-positions-table`.

- [ ] **Step 4: Swap them**

In `dashboard.ts`, replace the four `<sb-trade-group …>` elements inside the
positions `sb-panel` with:

```html
      <sb-positions-table
        [counts]="lifecycleCounts()"
        [today]="closedToday()"
        [columns]="columns()"
        [visibleFor]="columnsForTab"
        [pinned]="pinned"
        [rowKey]="rowKey"
        (rowActivate)="open($event)"
        (reorder)="onReorder($event)"
      />
```

Add to the class:

```ts
  /** The lifecycle strip's counts, reshaped for the tab labels. The strip
   *  itself is gone (R3-07) — these numbers moved onto the tabs. */
  protected readonly lifecycleCounts = computed(() =>
    Object.fromEntries(this.store.lifecycle().map((e) => [e.status, e.count])),
  );

  /** Bound as a value, not called in the template: the table takes the
   *  function and applies it per tab.
   *
   *  Named `columnsForTab`, not `visibleForTab`: the imported helper is
   *  already called that, and a class member of the same name reads as a
   *  recursive call to anyone skimming it. */
  protected readonly columnsForTab = (tab: string) => visibleForTab(tab, this.visible());
```

and bind it as `[visibleFor]="columnsForTab"` in the template above.

Swap `TradeGroup` for `PositionsTable` in `imports`, then delete
`trade-group.ts` and `trade-group.spec.ts`, and remove the `TradeGroup`
reference from `trades.store.spec.ts`.

- [ ] **Step 5: Run the three affected specs**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts
cd frontend && npx ng test --include src/app/workspaces/dashboard/positions-table.spec.ts
cd frontend && npx ng test --include src/app/stores/trades.store.spec.ts
```

Expected: PASS for all three.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/app/workspaces/dashboard frontend/src/app/stores/trades.store.spec.ts
git commit -m "feat(dashboard): replace the four trade groups with the tabbed table"
```

---

### Task R4-05: Row actions

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/row-actions.ts`
- Create: `frontend/src/app/workspaces/dashboard/row-actions.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (the cell template)

**Interfaces:**
- Consumes: `ApiClient.closeTrade/cancelTrade/setTradeNote`; the `'more'` icon
  (R1-03); `ui/confirm-dialog.ts`.
- Produces: `<sb-row-actions [row]>` with output `done: void` (emitted after a
  successful mutation so the page can refetch).

**Three actions, not four — D13.** Close, Cancel, Add/edit note. **No Delete:**
`delete_trade` refuses plan-backed rows with a 422 by design, and every row
here is plan-backed. An action is shown only where its precondition holds —
Close on ACTIVE/PARTIAL, Cancel on PENDING — so the menu never offers
something that will fail.

- [ ] **Step 1: Write the failing test**

```ts
it('offers close only on an open position', () => {
  expect(items(mount({ row: row({ status: 'ACTIVE' }) }))).toContain('Close position');
  expect(items(mount({ row: row({ status: 'PARTIAL' }) }))).toContain('Close position');
  expect(items(mount({ row: row({ status: 'PENDING' }) }))).not.toContain('Close position');
});

it('offers cancel only on a plan that has not filled', () => {
  expect(items(mount({ row: row({ status: 'PENDING' }) }))).toContain('Cancel plan');
  expect(items(mount({ row: row({ status: 'ACTIVE' }) }))).not.toContain('Cancel plan');
});

it('never offers delete, because the backend refuses it for plans', () => {
  for (const status of ['ACTIVE', 'PENDING', 'PARTIAL', 'CLOSED', 'CANCELLED']) {
    expect(items(mount({ row: row({ status }) })).join(' ')).not.toContain('Delete');
  }
});

it('always offers the note, whatever the status', () => {
  for (const status of ['ACTIVE', 'PENDING', 'CLOSED']) {
    expect(items(mount({ row: row({ status }) }))).toContain('Add note');
  }
});

it('posts a close and tells the page to refetch', () => {
  const f = mount({ row: row({ status: 'ACTIVE', id: 'p1' }) });
  let done = 0;
  f.componentInstance.done.subscribe(() => (done += 1));
  openMenu(f);
  clickItem(f, 'Close position');

  const req = httpMock.expectOne('/api/v1/trades/p1/close');
  expect(req.request.method).toBe('POST');
  req.flush({});
  expect(done).toBe(1);
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/row-actions.spec.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

Model the open/close/Escape/outside-click behaviour on
`shell/profile-menu.ts`, which already solves it — same host listeners, same
focus-return-to-trigger rule.

```ts
import {
  ChangeDetectionStrategy, Component, ElementRef, computed, inject, input, output, signal,
} from '@angular/core';

import { ApiClient } from '../../api/api-client';
import { TradeRow } from '../../api/models';
import { Button } from '../../ui/button';
import { Icon } from '../../ui/icon';

const CLOSEABLE = new Set(['ACTIVE', 'PARTIAL']);

/**
 * Per-row actions — v85 D13.
 *
 * Each item's precondition mirrors its endpoint's, so the menu cannot offer a
 * command the server will refuse: close is ACTIVE/PARTIAL only, cancel is
 * PENDING only. Delete is absent entirely — `delete_trade` rejects plan-backed
 * rows with a 422, and every row on this page is plan-backed.
 */
@Component({
  selector: 'sb-row-actions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, Icon],
  host: {
    '(document:click)': 'onDocumentClick($event)',
    '(document:keydown.escape)': 'close()',
  },
  template: `
    <button sb-button variant="icon" type="button" class="trigger"
            [attr.aria-expanded]="open()" aria-haspopup="menu"
            aria-label="Row actions" (click)="toggle($event)">
      <sb-icon name="more" />
    </button>

    @if (open()) {
      <div class="menu elev-overlay" role="menu">
        @if (canClose()) {
          <button sb-button variant="ghost" role="menuitem" type="button"
                  (click)="run('close')">Close position</button>
        }
        @if (canCancel()) {
          <button sb-button variant="ghost" role="menuitem" type="button"
                  (click)="run('cancel')">Cancel plan</button>
        }
        <button sb-button variant="ghost" role="menuitem" type="button"
                (click)="run('note')">Add note</button>
      </div>
    }
  `,
  styles: `
    :host { position: relative; display: inline-flex; }
    .menu {
      position: absolute; top: calc(100% + var(--space-4)); right: 0; z-index: 20;
      min-width: 160px; display: flex; flex-direction: column; gap: var(--space-4);
      padding: var(--space-6);
    }
    .menu button { justify-content: flex-start; font-size: var(--text-table); }
  `,
})
export class RowActions {
  private readonly api = inject(ApiClient);
  private readonly host: ElementRef<HTMLElement> = inject(ElementRef);

  readonly row = input.required<TradeRow>();
  readonly done = output<void>();

  protected readonly open = signal(false);
  protected readonly canClose = computed(() =>
    CLOSEABLE.has((this.row().status ?? '').toUpperCase()));
  protected readonly canCancel = computed(() =>
    (this.row().status ?? '').toUpperCase() === 'PENDING');

  protected toggle(event: MouseEvent): void {
    event.stopPropagation();
    this.open.update((v) => !v);
  }

  protected close(): void {
    if (!this.open()) return;
    this.open.set(false);
    this.host.nativeElement.querySelector<HTMLElement>('.trigger')?.focus();
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (this.open() && !this.host.nativeElement.contains(event.target as Node)) this.close();
  }

  protected run(action: 'close' | 'cancel' | 'note'): void {
    const id = this.row().id;
    this.close();
    if (action === 'note') {
      // The note editor already exists on Trade detail; this routes there
      // rather than growing a second editor with its own save path.
      this.done.emit();
      return;
    }
    const call = action === 'close' ? this.api.closeTrade(id) : this.api.cancelTrade(id);
    call.subscribe({ next: () => this.done.emit(), error: () => this.done.emit() });
  }
}
```

For `note`, navigate to `/trades/:id` — do not build a second note editor.
Confirm how Trade detail opens its note editor and reuse that route.

- [ ] **Step 4: Add the actions cell to the table**

In `dashboard.ts`, add an `actions` cell template and include it in the column
map beside the others:

```html
    <ng-template #actionsCell let-row>
      <sb-row-actions [row]="row" (done)="store.load()" />
    </ng-template>
```

- [ ] **Step 5: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/row-actions.spec.ts
```

Expected: PASS, 5 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/row-actions.ts \
        frontend/src/app/workspaces/dashboard/row-actions.spec.ts \
        frontend/src/app/workspaces/dashboard/dashboard.ts
git commit -m "feat(dashboard): add per-row close, cancel and note actions"
```

---

### Task R4-06: Close all open/partial

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts`
- Test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes: `ApiClient.closeOpenTrades()` and `CloseOpenResult` (R2-06);
  `ui/confirm-dialog.ts`.
- Produces: the panel's one action button. No new exported symbol.

**This replaces the mockup's "+ New Trade".** There is no create-trade
endpoint — the bot authors plans, the admin never does (spec Finding 4).

**The confirm dialog is not decoration.** One word away in the same API sits
`clear-open`, which *deletes* open trades. The dialog must say plainly that
this **closes positions and realises profit or loss**, and name how many.

- [ ] **Step 1: Write the failing test**

```ts
it('asks before closing, and says what closing means', () => {
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;

  el.querySelector<HTMLButtonElement>('[data-action="close-all"]')!.click();
  f.detectChanges();

  const dialog = el.querySelector('[role="dialog"]')!;
  expect(dialog.textContent).toContain('realis');   // realise/realised
  expect(dialog.textContent).not.toContain('delete');
  // Nothing has been sent yet.
  httpMock.expectNone('/api/v1/trades/close-open');
});

it('posts once confirmed and refetches the page', () => {
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  el.querySelector<HTMLButtonElement>('[data-action="close-all"]')!.click();
  f.detectChanges();
  el.querySelector<HTMLButtonElement>('[data-confirm]')!.click();

  const req = httpMock.expectOne('/api/v1/trades/close-open');
  expect(req.request.method).toBe('POST');
  req.flush({ closed: 2, failed: 0, tickers: ['ASTS', 'HOOD'] });
});

it('reports a partial failure rather than claiming success', () => {
  // …confirm, then flush { closed: 1, failed: 1, tickers: ['ASTS'] }
  // The toast/message must mention the failure, not just the close.
  expect(lastToast()).toContain('1 failed');
});

it('offers nothing to close when the book is empty', () => {
  // With zero ACTIVE/PARTIAL positions the button is disabled: a confirm
  // dialog for a no-op is a question with one answer.
  expect(closeAllButton(f).disabled).toBe(true);
});

it('puts no destructive bulk operations on this panel -- D14', () => {
  // clear-open and clear-history DELETE records. They stay where they live
  // today; one click from a close-the-book action is how the wrong one gets
  // pressed.
  const f = TestBed.createComponent(Dashboard);
  f.detectChanges();
  const text = (f.nativeElement as HTMLElement).textContent ?? '';
  expect(text).not.toContain('Clear open');
  expect(text).not.toContain('Clear history');
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: FAIL — no `[data-action="close-all"]`.

- [ ] **Step 3: Add the button and its confirm**

Project into the table's `[table-actions]` slot:

```html
        <button sb-button variant="secondary" type="button" table-actions
                data-action="close-all"
                [disabled]="!openCount()"
                (click)="confirmCloseAll.set(true)">
          Close all open/partial
        </button>
```

and the dialog, using the existing `ui/confirm-dialog.ts` primitive:

```ts
  protected readonly confirmCloseAll = signal(false);

  /** ACTIVE + PARTIAL only — a PENDING plan never filled, so there is nothing
   *  to close and cancelling is the different act that applies to it. */
  protected readonly openCount = computed(() => {
    const counts = this.lifecycleCounts();
    return (counts['ACTIVE'] ?? 0) + (counts['PARTIAL'] ?? 0);
  });

  protected closeAll(): void {
    this.confirmCloseAll.set(false);
    this.api.closeOpenTrades().subscribe({
      next: (result) => {
        this.toast.show(
          result.failed
            ? `Closed ${result.closed}, ${result.failed} failed — check the log.`
            : `Closed ${result.closed} position${result.closed === 1 ? '' : 's'}.`,
        );
        this.store.load();
      },
      error: () => this.toast.show('Could not close positions.'),
    });
  }
```

Dialog copy — say what it does, in the words that distinguish it from the
delete next door:

> **Close all open positions?**
> This closes {{ openCount() }} position(s) at their current price and
> **realises the profit or loss**. Pending plans are not affected. This cannot
> be undone.

- [ ] **Step 4: Run it and watch it pass**

```bash
cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Exercise it for real, once**

With the dev server running against a scratch data dir containing at least one
ACTIVE position: click it, confirm, and check three things —
`data/manual_close_notify.json` gained a record, the position left the Open
positions tab, and the Closed tab now holds it.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/dashboard.ts \
        frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git commit -m "feat(dashboard): add a guarded close-all for open positions"
```
