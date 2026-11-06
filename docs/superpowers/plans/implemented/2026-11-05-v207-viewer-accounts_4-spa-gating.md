# v207 part 4 — SPA gating: hide write controls on trades, dashboard, watchlist, risk, analytics

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v207 — Viewer accounts](../specs/2026-11-05-v207-viewer-accounts-design.md) (§ SPA, the `*ifAdmin` inventory table; § Testing, Frontend)
**Index:** [`2026-11-05-v207-viewer-accounts_0-index.md`](2026-11-05-v207-viewer-accounts_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

Tasks V207-13..V207-15 (index group F). The three touch disjoint files and may run in parallel; each needs V207-9 merged. `<wt>` is the implementation worktree, `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v207-viewer-accounts`; every command names it, never the main tree. Frontend runs are narrow: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include <spec>`. No task runs the full suite. None of these tasks reaches Postgres, so no `/replicate-prod-db`.

**What every task here consumes from V207-9 (index ledger, part 3):**
- `SessionStore` (`frontend/src/app/stores/session.store.ts`) gains `role: Signal<Role | null>`, `isAdmin: Signal<boolean>`, `isViewer: Signal<boolean>`.
- `IfAdminDirective` (`frontend/src/app/auth/if-admin.directive.ts`), standalone, selector `[ifAdmin]`, used as `*ifAdmin`: renders its template while `SessionStore.isAdmin()` is true, nothing otherwise, and follows the signal live.

**One rule for every gate below.** A write control is *removed* for a viewer (`*ifAdmin`, or the `actions` column filtered out of the column list), never shown disabled (Global Constraints). Where a control was the only thing in an `sb-page` slot, the `*ifAdmin` goes on the projected element itself (`<div *ifAdmin page-actions …>`), so the slot is left with no element children and `sb-page`'s `.slot:empty { display: none; }` folds it away: no gap at 390, 820 or 1440 px. Angular matches `ng-content select` against the element's own attributes under a structural directive, so admin projection is unchanged (each task's admin test proves it).

**One test idiom for every spec below (part 3's).** After V207-9, `SessionStore.isAdmin()` is `status() === 'authenticated' && role() === 'admin'` and fails closed: a store nobody signed in reports `false`, so a spec that renders a gated component against the real store shows the viewer layout unless it sets the role. Every touched spec file gets this block once, near its imports, and calls `signInAs(role)` right after **every** `TestBed.configureTestingModule(...)` in that file that mounts the gated component, before the first `createComponent` / `RouterTestingHarness.create` (`grep -n configureTestingModule <spec>` lists them). A viewer test sets `role = 'viewer'` before a helper that configures and mounts in one go (`render()`, `seed()`, `mount()` per call); where the module is configured in a `beforeEach` and the test only mounts, it calls `signInAs('viewer')` before mounting instead; a test that flips the role on a live fixture calls `signInAs('viewer')` and then `detectChanges()`. The block is repeated per file rather than shared, because a shared helper would put a file dependency between the three parallel tasks.

```ts
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { Role } from '../../api/models';
import { SessionStore } from '../../stores/session.store';

/** v207: the role every mount below signs in with (part 3's idiom: patch
 *  the real SessionStore). Viewer tests set it before mounting. */
let role: Role = 'admin';
beforeEach(() => { role = 'admin'; });
function signInAs(as: Role): void {
  patchState(unprotected(TestBed.inject(SessionStore)), {
    status: 'authenticated', username: as === 'admin' ? 'admin' : 'viewer1', role: as,
  });
}
```
(Merge `patchState` / `unprotected` / `beforeEach` / `TestBed` into the file's existing imports rather than duplicating an import line; several of these specs already import `patchState` and `unprotected`.)

**Three-width check.** jsdom has no layout, so each spec pins the *structure* a viewer gets (slot left with no children, column absent). The admin render is checked live: with the worktree's dev stack up, `node "<wt>/frontend/scripts/layout-audit.mjs" --base http://localhost:1234` exits 0 at 390, 768 and 1440 (`docs/claude/ui-design.md` § UI tasks; the audit signs in with the `.env` admin and never prints it). A live viewer pass needs a viewer account on the local instance (V207-6), so it belongs to whichever session first has both; it is not a gate for these tasks.

# Phase F — gating viewer-readable pages

### Task V207-13: Gate trades workspace + trade detail

**Model:** sonnet — two components, template-level gates and a column filter, every edit located below; no design judgement left.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.ts` (imports `:17-59`, `imports: [` `:159-185`, page-actions `:192-238`, `allColumns` `:940-958`)
- Modify: `frontend/src/app/workspaces/trades/trades.spec.ts` (the session block; `signInAs(role)` after the three `configureTestingModule` sites `:56`, `:105`, `:450`; new describe at the end)
- Modify: `frontend/src/app/workspaces/trades/trades-clear.spec.ts` (session block; `signInAs(role)` after its one `configureTestingModule`, `:31`; one viewer test) — the second spec of `trades.ts`
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (`imports: [` `:129-150`, page-actions `:159-176`, the note block `:349-380`, styles near `.note-field` `:554`, class fields `:620-630`)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (session block; `signInAs(role)` after all eight `configureTestingModule` sites `:138 :290 :387 :492 :559 :602 :935 :1125`; new describe at the end)

**Interfaces:**
- Consumes: `SessionStore.isAdmin: Signal<boolean>` and `IfAdminDirective` (`*ifAdmin`, `frontend/src/app/auth/if-admin.directive.ts`) — V207-9.
- Produces: nothing a later task reads. For V207-12's inventory, these callers are gated `'if-admin'` here: `closeTrade` / `cancelTrade` / `deleteTrade` (Trades row actions, Trade detail header), `clearOpenTrades` / `clearTradeHistory` (Trades header), `setTradeNote` (Trade detail Journal), `refreshMarket` (Trades header, Trade detail header).

**What a viewer gets.** Trades: the header keeps the price age (`sb-market-value`) and the incomplete note, and loses Refresh, Clear open, Clear history and the refusal's "Reset anyway…". The table loses its `actions` column at every width (on a phone, that is the row drawer's command buttons); every other column stays. Trade detail: the header slot is empty and folds away (`<div *ifAdmin page-actions>`); the Journal tab shows the note as read-only text, never a textarea.

- [ ] **Step 1: Write the failing tests**

Add the session block (part header) to `trades.spec.ts`, `trades-clear.spec.ts` and `trade-detail.spec.ts`, and a `signInAs(role)` call after every `configureTestingModule` listed under Files. Then append to `trades.spec.ts`:

```ts
/* -- v207 -- a viewer reads Trades and changes nothing ------------------ */

describe('Trades for a viewer (v207)', () => {
  const columnKeys = (f: ComponentFixture<Trades>): string[] =>
    (f.componentInstance as unknown as { allColumns: () => { key: string }[] })
      .allColumns().map((c) => c.key);
  const header = (f: ComponentFixture<Trades>) =>
    (f.nativeElement as HTMLElement).querySelector('sb-page header.bar .actions')!;

  it('gives the admin both clears, Refresh and the row-actions column (unchanged)', () => {
    const f = render();
    expect(header(f).querySelector('[data-action="clear-open"]')).not.toBeNull();
    expect(header(f).querySelector('[data-action="clear-history"]')).not.toBeNull();
    expect(header(f).querySelector('.prices-meta sb-market-refresh')).not.toBeNull();
    expect(columnKeys(f)).toContain('actions');
  });

  it('hides both clears and Refresh from a viewer and keeps the price age', () => {
    role = 'viewer';
    const f = render();
    expect(header(f).querySelector('[data-action="clear-open"]')).toBeNull();
    expect(header(f).querySelector('[data-action="clear-history"]')).toBeNull();
    expect(header(f).querySelector('sb-market-refresh')).toBeNull();
    expect(header(f).querySelector('.prices-meta sb-market-value')).not.toBeNull();
    expect(header(f).querySelectorAll('button')).toHaveLength(0);
  });

  it('drops only the actions column for a viewer: every read column stays', () => {
    const adminKeys = columnKeys(render());
    role = 'viewer';
    expect(columnKeys(render())).toEqual(adminKeys.filter((key) => key !== 'actions'));
  });

  it('follows a role change without a remount', () => {
    const f = render();
    signInAs('viewer');
    f.detectChanges();
    expect(header(f).querySelector('[data-action="clear-open"]')).toBeNull();
    expect(columnKeys(f)).not.toContain('actions');
  });

  it('offers Close in the admin phone drawer and no command in a viewer one', () => {
    const drawerButtons = (f: ComponentFixture<Trades>): string[] => {
      openRowDrawer(tradesTable(f));
      f.detectChanges();
      const drawer = (f.nativeElement as HTMLElement).querySelector('sb-drawer.row-drawer')!;
      return [...drawer.querySelectorAll('button')].map((b) => b.textContent!.trim());
    };
    const active = row({ status: 'ACTIVE', status_label: 'ACTIVE', exit_price: null, pnl_pct: null });
    expect(drawerButtons(renderPhone([active]))).toContain('Close');
    role = 'viewer';
    const viewer = renderPhone([active]);
    const labels = drawerButtons(viewer);
    expect(labels).not.toContain('Close');
    expect(labels).not.toContain('Delete');
    expect(drawerKeys(tradesTable(viewer))).not.toContain('actions');
  });
});
```

Append inside `describe('Trades bulk-clear replies (v189)', …)` in `trades-clear.spec.ts` (its `beforeEach` mounts as admin; the test flips the role on the live fixture, which `patch` re-renders):

```ts
  it('shows a viewer the refusal text but never the force button', () => {
    signInAs('viewer');
    patch({ clearRefusal: REFUSED });
    const refusal = el().querySelector('[data-testid="clear-refusal"]')!;
    expect(refusal.textContent).toContain('Reset refused: the kill switch is tripped.');
    expect(refusal.querySelector('button')).toBeNull();
  });
```

Append to `trade-detail.spec.ts`:

```ts
/* -- v207 -- a viewer reads a trade and changes nothing ----------------- */

describe('TradeDetail for a viewer (v207)', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: LiveValuesStore, useClass: FakeLiveValues },
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    signInAs(role);
    backend = TestBed.inject(HttpTestingController);
  });

  function mount(tab: string, status = 'ACTIVE', detail: object = DETAIL) {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', tab);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(detail, status));
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }
  const header = (el: HTMLElement) => el.querySelector('sb-page header.bar .actions')!;

  it('gives the admin Refresh and both commands on a live trade (unchanged)', () => {
    const { el } = mount('overview');
    expect(header(el).querySelector('sb-market-refresh')).not.toBeNull();
    expect(header(el).querySelectorAll('button[sb-button]:not(sb-market-refresh button)')).toHaveLength(2);
  });

  it('leaves a viewer an empty header slot on a live trade', () => {
    signInAs('viewer');
    const { el } = mount('overview');
    expect(header(el).children).toHaveLength(0);
    expect(header(el).textContent!.trim()).toBe('');
  });

  it('never offers a viewer Delete on a closed trade', () => {
    signInAs('viewer');
    const { el } = mount('overview', 'CLOSED');
    expect([...el.querySelectorAll('button')].map((b) => b.textContent!.trim())).not.toContain('Delete');
  });

  it('keeps the note textarea for the admin', () => {
    const { el } = mount('journal');
    expect(el.querySelector('textarea#trade-note')).not.toBeNull();
    expect(el.querySelector('[data-testid="note-readonly"]')).toBeNull();
  });

  it('shows a viewer the note as read-only text, never a field', () => {
    signInAs('viewer');
    const { el } = mount('journal', 'CLOSED', { ...DETAIL, note: 'Exit management.\nTrail sooner.' });
    expect(el.querySelector('textarea')).toBeNull();
    expect(el.querySelector('.note-state')).toBeNull();
    const note = el.querySelector('[data-testid="note-readonly"]')!;
    expect(note.textContent).toContain('Exit management.');
    expect(note.textContent).toContain('Trail sooner.');
    expect(note.classList).toContain('note-readonly');          // white-space: pre-wrap keeps the lines
    backend.expectNone((r) => r.method === 'PUT');
  });

  it('says "No note yet." to a viewer when the trade has none', () => {
    signInAs('viewer');
    const { el } = mount('journal', 'CLOSED');
    expect(el.querySelector('[data-testid="note-readonly"]')!.textContent!.trim()).toBe('No note yet.');
  });
});
```

Already in those files: `openRowDrawer`, `drawerKeys`, `tradesTable`, `renderPhone`, `render`, `row` (trades.spec); `patch`, `el`, `REFUSED` (trades-clear.spec); `DETAIL` (has `note: null`), `ID`, `tradeResponse`, `FakeEventStream` (trade-detail.spec). Import `ComponentFixture` where a file lacks it.

- [ ] **Step 2: Run them to see them fail**

```bash
node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/trades/trades-clear.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts
```

Expected: the viewer tests FAIL (the clears, Refresh, the `actions` column and the textarea still render for a viewer); every pre-existing test and every admin test PASSES (every setup signs in as admin).

- [ ] **Step 3: Gate `trades.ts`**

- Import `SessionStore` from `'../../stores/session.store'` and `IfAdminDirective` from `'../../auth/if-admin.directive'`; add `IfAdminDirective` to the component's `imports: [...]`.
- Field beside the other injections (`:731-740`): `private readonly session = inject(SessionStore);`
- Template, inside `<div page-actions class="page-actions">`: `<sb-market-refresh *ifAdmin [symbols]="liveSymbols()" />`; the refusal's force button becomes `<button *ifAdmin sb-button variant="danger-quiet" …>Reset anyway…</button>`; both the `data-action="clear-open"` and `data-action="clear-history"` buttons get `*ifAdmin`. The result, notice, refusal text and error lines stay ungated: a viewer can never trigger them, and they are read-only.
- `allColumns` (`:940-958`): drop the actions column for a viewer before attaching cells, so the table, the phone drawer and the reorder all see one list:

```ts
    return tradeColumns(this.now)
      .filter((column) => column.key !== 'actions' || this.session.isAdmin())
      .map((column) => (cells[column.key] ? { ...column, cell: cells[column.key] } : column));
```

`sb-data-table.renderedColumns` already skips a `visible` key with no column, so a saved layout listing `actions` renders cleanly for a viewer; `PINNED_COLUMNS` and `hiddenFields` need no change (`actions` is already kept out of the expansion). The confirm dialogs stay mounted: nothing a viewer can click opens them.

- [ ] **Step 4: Gate `trade-detail.ts`**

- The same two imports; `IfAdminDirective` into `imports: [...]`; field `protected readonly session = inject(SessionStore);` beside `store`.
- The header: `<div *ifAdmin page-actions class="page-actions">` — the whole slot is admin-only, because Refresh and the commands are its only content.
- The Journal note (`:349-380`): keep the `not-journaled` paragraph as is, then replace the label, the textarea and the `note-state` paragraph with:

```html
              @if (session.isAdmin()) {
                <label class="note-label" for="trade-note">Note</label>
                <!-- the textarea and p.note-state, unchanged -->
              } @else {
                <!-- v207: a viewer reads the note; there is no field to type into. -->
                <p class="note-label">Note</p>
                <p class="note-readonly" data-testid="note-readonly">{{ store.noteText() || 'No note yet.' }}</p>
              }
```

- Style, after `.note-field:disabled`:

```css
    .note-readonly {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: var(--text);
      font-size: var(--text-table);
      line-height: 1.6;
    }
```

`onNoteInput` / `flushNote` stay; with no field they never run for a viewer.

- [ ] **Step 5: Run the three specs to see them pass**

Same command as Step 2. Expected: all PASS, `0 failed`.

- [ ] **Step 6: Three-width check (admin render)**

With the worktree's dev stack up, `node "<wt>/frontend/scripts/layout-audit.mjs" --base http://localhost:1234` exits 0 at 390, 768 and 1440 for `/trades` and `/trades/:id`. The viewer structure is pinned by the specs above.

- [ ] **Step 7: Commit**

```bash
git -C "<wt>" add frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/trades/trades.spec.ts frontend/src/app/workspaces/trades/trades-clear.spec.ts frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts
git -C "<wt>" commit -m "feat(v207): hide trade commands, clears and note editing from viewers (V207-13)"
```

### Task V207-14: Gate dashboard: row actions, close-all, market refresh

**Model:** sonnet — three components, template-level gates and one column filter, every edit located below.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (imports near `:70`, `imports: [` `:174`, page-actions `:214-243`, `sb-market-refresh` `:308`, class fields `:654-692`, `columns` `:950-967`)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (session block; `signInAs(role)` after the `configureTestingModule` in `seed()` `:119` and `routed()` `:762`; new describe at the end)
- Modify: `frontend/src/app/workspaces/dashboard/row-actions.ts` (whole template, `:29-48`; class fields `:63-66`)
- Modify: `frontend/src/app/workspaces/dashboard/row-actions.spec.ts` (session block; `signInAs(role)` after the `configureTestingModule` in `mount()` `:35`; new describe)
- Modify: `frontend/src/app/workspaces/dashboard/trade-drawer.ts` (`imports:` `:120`, `.drawer-actions` `:136-139`)
- Modify: `frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts` (session block; `signInAs(role)` after the `configureTestingModule` in the `beforeEach` `:112`; its viewer test calls `signInAs('viewer')` before `mount()`, because the `beforeEach` has already signed in; new tests)

**Interfaces:**
- Consumes: `SessionStore.isAdmin: Signal<boolean>` and `IfAdminDirective` (`*ifAdmin`, `frontend/src/app/auth/if-admin.directive.ts`) — V207-9.
- Produces: nothing a later task reads. For V207-12's inventory, these callers are gated `'if-admin'` here: `closeOpenTrades` (Dashboard header menu), `closeTrade` / `cancelTrade` (`sb-row-actions`, in the positions table and the trade drawer), `refreshMarket` (Open positions panel).

**What a viewer gets.** The page header loses the "Close all" menu, and with it the whole `page-actions` slot, which `sb-page` then folds away (`<div *ifAdmin page-actions …>`; the menu was the slot's only content). The Open positions panel keeps its help hint and loses Refresh. The positions table loses its `actions` column at every width. The trade drawer keeps "Open full trade →" and loses the row-actions trigger; `.drawer-actions` is `justify-content: space-between`, so the link simply sits alone at the left with no gap. `RowActions` itself renders nothing for a viewer, so any future mount site is gated by default.

- [ ] **Step 1: Write the failing tests**

Add the session block (part header) to `dashboard.spec.ts`, `row-actions.spec.ts` and `trade-drawer.spec.ts`, and a `signInAs(role)` call after every `configureTestingModule` listed under Files. Then append to `dashboard.spec.ts`:

```ts
/* -- v207 -- a viewer reads the Dashboard and changes nothing ------------ */

describe('Dashboard for a viewer (v207)', () => {
  const columnKeys = (f: ComponentFixture<Dashboard>): string[] =>
    (f.componentInstance as unknown as { columns: () => { key: string }[] })
      .columns().map((c) => c.key);
  const header = (el: HTMLElement) => el.querySelector('sb-page header.bar .actions')!;

  it('gives the admin Close all, Refresh and the row-actions column (unchanged)', async () => {
    const fixture = await loaded({ lifecycle: { ACTIVE: 2, PARTIAL: 1 } as never });
    const el = fixture.nativeElement as HTMLElement;
    expect(header(el).querySelector('[data-action="close-all"]')).not.toBeNull();
    expect(el.querySelector('.positions-panel sb-market-refresh')).not.toBeNull();
    expect(columnKeys(fixture)).toContain('actions');
  });

  it('leaves a viewer an empty header slot: no Close all, no menu', async () => {
    role = 'viewer';
    const fixture = await loaded({ lifecycle: { ACTIVE: 2, PARTIAL: 1 } as never });
    const el = fixture.nativeElement as HTMLElement;
    expect(header(el).children).toHaveLength(0);
    expect(el.querySelector('[data-action="close-all"]')).toBeNull();
  });

  it('keeps the positions help for a viewer and drops only Refresh', async () => {
    role = 'viewer';
    const el = (await loaded()).nativeElement as HTMLElement;
    expect(el.querySelector('.positions-panel sb-market-refresh')).toBeNull();
    expect(el.querySelector('.positions-panel sb-hint.lifecycle-hint')).not.toBeNull();
  });

  it('drops only the actions column for a viewer: every read column stays', async () => {
    const adminKeys = columnKeys(await loaded());
    role = 'viewer';
    expect(columnKeys(await loaded())).toEqual(adminKeys.filter((key) => key !== 'actions'));
  });

  it('renders no row-actions trigger on a viewer row', async () => {
    role = 'viewer';
    const el = await loadedWithRows([tradeRow({ id: 'a1', status: 'ACTIVE', status_label: 'ACTIVE' })]);
    expect(el.querySelector('sb-positions-table sb-row-actions')).toBeNull();
    expect(el.querySelector('sb-positions-table [aria-label="Row actions"]')).toBeNull();
  });

  it('keeps the header and the dialogs out of the scope bar for a viewer too', async () => {
    role = 'viewer';
    const el = (await loaded()).nativeElement as HTMLElement;
    expect(el.querySelector('sb-page div.scope.slot')!.children).toHaveLength(0);
  });
});
```

Append to `row-actions.spec.ts`:

```ts
describe('row actions for a viewer (v207)', () => {
  it('offers the admin the trigger and its commands (unchanged)', () => {
    const f = mount({ row: row({ status: 'ACTIVE' }) });
    expect((f.nativeElement as HTMLElement).querySelector('.trigger')).not.toBeNull();
    expect(items(f)).toContain('Close position');
  });

  it('renders nothing at all for a viewer, on any status', () => {
    role = 'viewer';
    for (const status of ['ACTIVE', 'PARTIAL', 'PENDING', 'CLOSED']) {
      const host = mount({ row: row({ status }) }).nativeElement as HTMLElement;
      expect(host.querySelector('button')).toBeNull();
      expect(host.querySelector('[role="menu"]')).toBeNull();
      expect(host.textContent!.trim()).toBe('');
    }
    httpMock.expectNone(() => true);
  });
});
```

Append inside `describe('sb-trade-drawer (v179 §3.2)', …)` in `trade-drawer.spec.ts`:

```ts
  it('keeps the row-actions trigger beside the link for the admin (v207, unchanged)', () => {
    const el = mount();
    expect(el.querySelector('.drawer-actions sb-row-actions .trigger')).not.toBeNull();
    expect(el.querySelector('.drawer-actions a.full-trade')).not.toBeNull();
  });

  it('gives a viewer the link to the full trade and no command (v207)', () => {
    signInAs('viewer');
    const el = mount();
    const actions = el.querySelector('.drawer-actions')!;
    expect(actions.querySelector('sb-row-actions')).toBeNull();
    expect(actions.querySelectorAll('button')).toHaveLength(0);
    const link = actions.querySelector<HTMLAnchorElement>('a.full-trade')!;
    expect(link.getAttribute('href')).toBe('/trades/' + tradeRow().id);
  });
```

Already in those files: `loaded`, `loadedWithRows`, `tradeRow` (dashboard.spec); `mount`, `items`, `row`, `httpMock` (row-actions.spec); `mount`, `tradeRow` (trade-drawer.spec). Import `ComponentFixture` where a file lacks it.

- [ ] **Step 2: Run them to see them fail**

```bash
node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/row-actions.spec.ts --include src/app/workspaces/dashboard/trade-drawer.spec.ts
```

Expected: the viewer tests FAIL (Close all, Refresh, the `actions` column and the row-actions trigger still render for a viewer); every pre-existing test and every admin test PASSES.

- [ ] **Step 3: Gate `dashboard.ts`**

- Import `SessionStore` from `'../../stores/session.store'` and `IfAdminDirective` from `'../../auth/if-admin.directive'`; add `IfAdminDirective` to `imports: [...]`.
- Field beside the other injections: `private readonly session = inject(SessionStore);`
- Header: `<div *ifAdmin page-actions class="close-all-menu" #closeAllMenu>`. `closeAllMenuRef` is an optional `viewChild` and `onDocumentClickForCloseAllMenu` already reads it as `this.closeAllMenuRef()?.nativeElement`, so an absent menu needs no other change. The close-all `sb-confirm-dialog` stays mounted (nothing a viewer can click opens it).
- Open positions panel: `<sb-market-refresh *ifAdmin panel-actions [symbols]="liveSymbols()" />`.
- `columns` (`:950-967`):

```ts
    return tradeColumns(this.now)
      .filter((column) => column.key !== 'actions' || this.session.isAdmin())
      .map((column) => (cells[column.key] ? { ...column, cell: cells[column.key] } : column));
```

`sb-positions-table` passes the list to `sb-data-table`, whose `renderedColumns` skips a `visible` key with no column, so a saved layout listing `actions` renders cleanly.

- [ ] **Step 4: Gate `row-actions.ts` and `trade-drawer.ts`**

- `row-actions.ts`: import `IfAdminDirective` and add it to `imports: [Button, Icon, IfAdminDirective]`. Wrap the whole template (the trigger button and the `@if (open())` menu) in one `<ng-container *ifAdmin> … </ng-container>`. Nothing else changes: the menu items, `run()` and the host listeners stay as they are, and they never fire without a trigger. Extend the class docstring with one line: "v207: renders nothing for a viewer, so every mount site is gated by default."
- `trade-drawer.ts`: import `IfAdminDirective`, `imports: [Drawer, Hint, RowActions, RouterLink, IfAdminDirective]`, and `<sb-row-actions *ifAdmin [row]="row()" placement="up" (done)="actionDone.emit()" />`. Both gates are kept: the drawer's keeps the element out of the flex row, and RowActions' own protects any other mount site.

- [ ] **Step 5: Run the three specs to see them pass**

Same command as Step 2. Expected: all PASS, `0 failed`.

- [ ] **Step 6: Three-width check (admin render)**

With the worktree's dev stack up, `node "<wt>/frontend/scripts/layout-audit.mjs" --base http://localhost:1234` exits 0 at 390, 768 and 1440 for `/dashboard` (the drawer included: `/dashboard?trade=<id>`). The viewer structure is pinned by the specs above.

- [ ] **Step 7: Commit**

```bash
git -C "<wt>" add frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts frontend/src/app/workspaces/dashboard/row-actions.ts frontend/src/app/workspaces/dashboard/row-actions.spec.ts frontend/src/app/workspaces/dashboard/trade-drawer.ts frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts
git -C "<wt>" commit -m "feat(v207): hide close-all, row actions and refresh on the dashboard from viewers (V207-14)"
```

### Task V207-15: Gate watchlist, Risk killswitch buttons, Analytics Tuning tab

**Model:** sonnet — three pages, template-level gates, one column filter and two small tab helpers, every edit located below.

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts` (imports, `imports: [`, the Add tickers `sb-panel` `:347-419`, class fields `:591-596`, `columns` `:804-816`)
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts` (session block; `signInAs(role)` after all seven `configureTestingModule` sites `:53 :172 :244 :298 :462 :585 :638`; new describe)
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (imports, `imports: [`, `.kill-actions` `:217-229`, Killswitch panel copy `:404-417`, class fields `:769-772`)
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts` (session block; `signInAs(role)` after the `configureTestingModule` in `seed()` `:73`; new describe at the end)
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (tab list `:79-84`, template `:47-66`, imports)
- Modify: `frontend/src/app/workspaces/analytics/analytics.routes.ts` (the resolver `:28-33`; new exported `analyticsTabFor`) — **not in the index ledger row**: without it a viewer opening `/analytics?tab=tuning` makes the resolver fetch the admin-only tuning reads and gets a 403. The controller adds the file to the V207-15 row. No other task touches it.
- Modify: `frontend/src/app/workspaces/analytics/analytics.spec.ts` (session block; `signInAs(role)` after the `configureTestingModule` in `create()` `:36`; new describe)

**Interfaces:**
- Consumes: `SessionStore.isAdmin: Signal<boolean>` and `IfAdminDirective` (`*ifAdmin`, `frontend/src/app/auth/if-admin.directive.ts`) — V207-9; `Tab` (`ui/layout`), `AnalyticsTab` (`stores/analytics.store.ts:191`).
- Produces, local to these files (no other task reads them): `ANALYTICS_TAB_LIST: readonly Tab[]` and `visibleAnalyticsTabs(isAdmin: boolean): readonly Tab[]` exported from `analytics.ts`; `analyticsTabFor(tab: AnalyticsTab, isAdmin: boolean): AnalyticsTab` exported from `analytics.routes.ts`. For V207-12's inventory, these callers are gated here: `addTickers` / `removeTicker` `'if-admin'`, `setKillswitch` `'if-admin'`, `startTuneJob` / `createProposal` / `deleteProposal` `'hidden-tab'`.

**What a viewer gets.** Watchlist: the table and the tag filter stay; the Add tickers panel (the page's only `page-secondary` element) is gone and its slot folds away, and the `actions` (remove) column is gone at every width. Tags stay usable: they live in preferences, which V207-11 keeps in memory for a viewer. Risk: the Engage/Release buttons (`.kill-actions`) are gone from the header, while the stale message and the Killswitch panel's state stay. The panel drops "The control is at the top of this page." and, in the unknown state, "Choose an explicit action if needed."; the shell `KillswitchChip` is untouched (a read-only link). Analytics: six tabs (no Tuning); `?tab=tuning` resolves Overview and the URL is rewritten to drop the tab. The command palette's Tuning entry is already removed for viewers by part 3 (`pageItemsFor`, V207-10); this task gates only the tab itself.

- [ ] **Step 1: Write the failing tests**

Add the session block (part header) to `watchlist.spec.ts`, `risk.spec.ts` and `analytics.spec.ts`, and a `signInAs(role)` call after every `configureTestingModule` listed under Files. Then append to `watchlist.spec.ts`:

```ts
/* -- v207 -- a viewer reads the watchlist and changes nothing ----------- */

describe('Watchlist for a viewer (v207)', () => {
  function mountList(list: Partial<Ticker>[]): ComponentFixture<Watchlist> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
        { provide: LiveValuesStore, useClass: FakeLiveValues },
        WatchlistStore,
      ],
    });
    signInAs(role);
    const fixture = TestBed.createComponent(Watchlist);
    patchState(unprotected(TestBed.inject(WatchlistStore)), {
      tickers: list.map((overrides) => ticker(overrides)),
      loaded: true,
    });
    fixture.detectChanges();
    return fixture;
  }
  const columnKeys = (f: ComponentFixture<Watchlist>): string[] =>
    (f.componentInstance as unknown as { columns: () => { key: string }[] }).columns().map((c) => c.key);

  it('gives the admin the Add tickers panel and the remove column (unchanged)', () => {
    const f = mountList([{ symbol: 'AAPL' }]);
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('sb-page div.secondary.slot sb-panel.add-panel')).not.toBeNull();
    expect(columnKeys(f)).toContain('actions');
  });

  it('leaves a viewer no Add tickers panel and an empty secondary slot', () => {
    role = 'viewer';
    const el = mountList([{ symbol: 'AAPL' }]).nativeElement as HTMLElement;
    expect(el.querySelector('sb-panel.add-panel')).toBeNull();
    expect(el.querySelector('sb-page div.secondary.slot')!.children).toHaveLength(0);
    expect(el.querySelector('input[aria-label="Ticker symbols to add"]')).toBeNull();
  });

  it('drops only the remove column for a viewer: every read column stays', () => {
    const adminKeys = columnKeys(mountList([{ symbol: 'AAPL' }]));
    role = 'viewer';
    const viewer = mountList([{ symbol: 'AAPL' }]);
    expect(columnKeys(viewer)).toEqual(adminKeys.filter((key) => key !== 'actions'));
    expect((viewer.nativeElement as HTMLElement).querySelector('button[aria-label="Remove AAPL"]')).toBeNull();
    expect((viewer.nativeElement as HTMLElement).textContent).toContain('AAPL');
  });
});
```

Append to `risk.spec.ts` (after the `Risk on sb-page` describe, so `renderPage`, `headerActions`, `OK` are in scope):

```ts
/* -- v207 -- a viewer sees the killswitch state and cannot change it ----- */

describe('Risk for a viewer (v207)', () => {
  beforeAll(() => installDialogPolyfill());
  const panel = (el: HTMLElement) => el.querySelector('sb-panel[heading="Killswitch"]')!;

  it('gives the admin Engage and the pointer to it (unchanged)', async () => {
    const el = (await renderPage()).nativeElement as HTMLElement;
    expect(headerActions(el).querySelector('.kill-actions button[data-action="killswitch"]')).not.toBeNull();
    expect(panel(el).querySelector('.kill-where')).not.toBeNull();
  });

  it('hides Engage and Release from a viewer and keeps the state', async () => {
    role = 'viewer';
    for (const on of [false, true]) {
      const el = (await renderPage({ killswitch: { on, reason: null, at: null, availability: OK } }))
        .nativeElement as HTMLElement;
      expect(el.querySelector('.kill-actions')).toBeNull();
      expect(el.querySelector('button[data-action="killswitch"]')).toBeNull();
      expect(headerActions(el).querySelectorAll('button')).toHaveLength(0);
      expect(panel(el).textContent).toContain(on ? 'ENGAGED' : 'Clear');
      expect(panel(el).querySelector('.kill-where')).toBeNull();
    }
  });

  it('never tells a viewer to choose an action in the unknown state', async () => {
    const unknown = { killswitch: { on: null, reason: null, at: null, availability: OK } };
    const adminText = panel((await renderPage(unknown)).nativeElement as HTMLElement).textContent!;
    expect(adminText).toContain('Choose an explicit action if needed.');
    role = 'viewer';
    const viewerText = panel((await renderPage(unknown)).nativeElement as HTMLElement).textContent!;
    expect(viewerText).toContain('Current killswitch state is unavailable.');
    expect(viewerText).not.toContain('Choose an explicit action');
  });

  it('leaves the shell KillswitchChip rendered for a viewer: a read-only link, not a control', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    signInAs('viewer');
    const chip = TestBed.createComponent(KillswitchChip);
    chip.componentRef.setInput('on', false);
    chip.detectChanges();
    const link = (chip.nativeElement as HTMLElement).querySelector('a')!;
    expect(link.textContent!.trim()).toBe('Armed');
    expect(link.getAttribute('href')).toBe('/risk');
    expect((chip.nativeElement as HTMLElement).querySelector('button')).toBeNull();
  });
});
```

(`import { KillswitchChip } from '../../shell/killswitch-chip';` in `risk.spec.ts`.)

Append to `analytics.spec.ts` (add `vi` to the vitest import):

```ts
/* -- v207 -- Tuning is an admin tool (spec Decision 3) ------------------- */

describe('Analytics for a viewer (v207)', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('lists Tuning for the admin and not for a viewer, order otherwise kept', () => {
    expect(visibleAnalyticsTabs(true).map((t) => t.id)).toEqual(ANALYTICS_TAB_LIST.map((t) => t.id));
    expect(visibleAnalyticsTabs(false).map((t) => t.id)).toEqual(
      ['overview', 'attribution', 'execution', 'edge', 'pipeline', 'partials']);
  });

  it('renders six tabs for a viewer and seven for the admin', () => {
    const asAdmin = create().fixture;
    asAdmin.detectChanges();
    expect(tabLabels(asAdmin.nativeElement as HTMLElement)).toContain('Tuning');
    role = 'viewer';
    const asViewer = create().fixture;
    asViewer.detectChanges();
    expect(tabLabels(asViewer.nativeElement as HTMLElement)).toEqual(
      ['Overview', 'Attribution', 'Execution', 'Edge', 'Pipeline', 'Partials']);
  });

  it('resolves Overview for a viewer asking for tuning, and nothing else changes', () => {
    expect(analyticsTabFor('tuning', false)).toBe('overview');
    expect(analyticsTabFor('tuning', true)).toBe('tuning');
    for (const tab of ['overview', 'attribution', 'execution', 'edge', 'pipeline', 'partials'] as const) {
      expect(analyticsTabFor(tab, false)).toBe(tab);
    }
  });

  it('rewrites ?tab=tuning away for a viewer, and leaves it for the admin', async () => {
    const arrive = async () => {
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          provideZonelessChangeDetection(),
          provideRouter([]),
          provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
          provideHttpClientTesting(),
          { provide: ConnectionStore, useValue: connectionStub },
          AnalyticsStore,
        ],
      });
      signInAs(role);
      const router = TestBed.inject(Router);
      await router.navigateByUrl('/?tab=tuning');
      const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
      TestBed.createComponent(Analytics).detectChanges();
      return navigate;
    };
    expect(await arrive()).not.toHaveBeenCalled();
    role = 'viewer';
    expect(await arrive()).toHaveBeenCalledWith([], {
      queryParams: { tab: null }, queryParamsHandling: 'merge', replaceUrl: true,
    });
  });
});
```

(`import { ANALYTICS_TAB_LIST, Analytics, visibleAnalyticsTabs } from './analytics';` and `import { analyticsTabFor } from './analytics.routes';`.)

- [ ] **Step 2: Run them to see them fail**

```bash
node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/workspaces/watchlist/watchlist.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/workspaces/analytics/analytics.spec.ts --include src/app/app.routes.spec.ts
```

Expected: the viewer tests FAIL, and `analytics.spec.ts` fails to compile until the three helpers exist. Every pre-existing test PASSES (`app.routes.spec.ts` pins the analytics refresh predicate, which this task leaves alone).

- [ ] **Step 3: Gate `watchlist.ts`**

- Import `SessionStore` from `'../../stores/session.store'` and `IfAdminDirective` from `'../../auth/if-admin.directive'`; add `IfAdminDirective` to `imports: [...]`; field `private readonly session = inject(SessionStore);`.
- `<sb-panel *ifAdmin page-secondary class="add-panel" heading="Add tickers" …>`. The `[style.display]` binding for the Earnings tab stays as it is. Extend the comment above the panel with: "v207: absent for a viewer; the slot is then empty and sb-page hides it."
- `columns` (`:804-816`):

```ts
    return WATCHLIST_COLUMNS
      .filter((column) => column.key !== 'actions' || this.session.isAdmin())
      .map((column) => (cells[column.key] ? { ...column, cell: cells[column.key] } : column));
```

The static `visible` list keeps `'actions'`: `sb-data-table` skips a key with no column. The remove confirm stays mounted; nothing a viewer can click opens it.

- [ ] **Step 4: Gate `risk.ts`**

- The same two imports, `IfAdminDirective` into `imports: [...]`. Risk needs no `SessionStore` field: the directive is the only gate.
- `<div *ifAdmin class="kill-actions">`. The `page-actions` wrapper stays, because it also carries the stale message and the command error (`display: contents`, so an empty wrapper adds no box).
- Killswitch panel: `<p *ifAdmin class="kill-where">The control is at the top of this page.</p>`. In the unknown branch, keep "Current killswitch state is unavailable." for everyone, and wrap the second sentence: `<ng-container *ifAdmin> Choose an explicit action if needed.</ng-container>`.

- [ ] **Step 5: Gate `analytics.ts` and `analytics.routes.ts`**

- `analytics.ts`: move the seven-entry list to a module-level `export const ANALYTICS_TAB_LIST: readonly Tab[]`, unchanged in order and labels, and add:

```ts
/** v207: Tuning runs tune jobs and saves proposals, an admin tool (spec
 *  Decision 3); a viewer gets the other six, in the same order. */
export function visibleAnalyticsTabs(isAdmin: boolean): readonly Tab[] {
  return isAdmin ? ANALYTICS_TAB_LIST : ANALYTICS_TAB_LIST.filter((tab) => tab.id !== 'tuning');
}
```

  In the class: `protected readonly session = inject(SessionStore);`, `protected readonly tabs = computed(() => visibleAnalyticsTabs(this.session.isAdmin()));`, and a constructor that sends a viewer off a Tuning URL:

```ts
  constructor() {
    const requested = this.router.parseUrl(this.router.url).queryParamMap.get('tab');
    if (requested === 'tuning' && !this.session.isAdmin()) this.goToTab('overview');
  }
```

  Template: `[tabs]="tabs()"`, `[tuning]="store.tab() === 'tuning' && session.isAdmin()"`, `@case ('tuning') { <sb-tuning-tab *ifAdmin /> }`; add `IfAdminDirective` to `imports: [...]`. Declare `router` before the constructor reads it, which it already is: field initialisers run first.
- `analytics.routes.ts`:

```ts
/** v207: a viewer asking for the admin-only Tuning tab gets Overview, so the
 *  resolver never issues the tuning reads (403 for a viewer). */
export function analyticsTabFor(tab: AnalyticsTab, isAdmin: boolean): AnalyticsTab {
  return tab === 'tuning' && !isAdmin ? 'overview' : tab;
}
```

  and in the resolver: `return store.resolveTab(analyticsTabFor(tab, inject(SessionStore).isAdmin()));` (`inject` runs inside the resolver's injection context, beside the existing `inject(AnalyticsStore)`). `refreshOnAnalytics` is unchanged: once the component rewrites the URL, it reads `overview`.

- [ ] **Step 6: Run the four specs to see them pass**

Same command as Step 2. Expected: all PASS, `0 failed`.

- [ ] **Step 7: Three-width check (admin render)**

With the worktree's dev stack up, `node "<wt>/frontend/scripts/layout-audit.mjs" --base http://localhost:1234` exits 0 at 390, 768 and 1440 for `/watchlist`, `/risk` and `/analytics`. The viewer structure is pinned by the specs above.

- [ ] **Step 8: Commit**

```bash
git -C "<wt>" add frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/watchlist/watchlist.spec.ts frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts frontend/src/app/workspaces/analytics/analytics.ts frontend/src/app/workspaces/analytics/analytics.routes.ts frontend/src/app/workspaces/analytics/analytics.spec.ts
git -C "<wt>" commit -m "feat(v207): hide watchlist edits, killswitch buttons and the Tuning tab from viewers (V207-15)"
```
