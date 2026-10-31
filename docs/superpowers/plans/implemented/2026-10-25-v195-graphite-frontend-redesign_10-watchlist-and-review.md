# v195 — Graphite, Part 10: Watchlist and ticker detail; Trades; trade and plan detail

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-29:" -A 400 <this file>`.

**Scope of this part (V195-28..V195-30):** spec Phase 4 and §5.2 for Watchlist, Trades and the three detail routes; §1.4's order-figure floor on `watchlist/:symbol`, `trades/:id`, `plans/:id` and the trade drawer; the breadcrumb detail segment (§3, `Review / Trades / NVDA #812`) that V195-15's `RouteTitleService.setDetail` carries. V195-28 closes the Dashboard + Watchlist lane; V195-29 → V195-30 open the Review lane (index § Parallelisation). The two lanes share no file.

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave (read before editing).** Part 9's list binds these tasks (the `sb-page` contract, `MINUS` and the signing helpers, `StatTile`, `PERFORMANCE_CAVEAT`, V195-8's `danger-quiet`, the `primitives.spec.ts` button and form-control gates, the `title` rule: no new `title`, `[title]` or `[attr.title]` on a native element; `sb-confirm-dialog`'s `title` input is allowed). On top of that:

- `frontend/src/app/ui/page.ts` (V195-21): `Page` (`sb-page`), inputs `heading` and `description` (null or empty falls back to `RouteTitleService.title()` / `subtitle()`). Markup `header.bar` > `div.heading` (`h1.title`, optional `p.description`) + `div.actions.slot`; `div.scope.slot`; `div.kpis.slot`; `div.primary.slot`; `div.secondary.slot`; then the default `<ng-content />`. **Each slot's content is ONE element carrying the slot attribute** (one element per secondary panel); conditionals go inside that element, never the attribute inside an `@if`; Part 9 hid whole panels with `[style.display]` to keep the element stable. Dialogs, drawers and `ng-template`s go in the default slot. Specs must not query bare `.primary` / `.secondary`: `sb-page` owns `div.primary.slot` / `div.secondary.slot`, and `StatTile` has its own `.secondary` line. Query by slot attribute (`[page-primary]`).
- `frontend/src/app/routing/route-title.service.ts` (V195-15): `RouteTitleService.detail: Signal<string | null>`, `setDetail(detail: string | null): void` (empty string stored as `null`), `set(title, subtitle, path = null)` clears `detail` on every title update **except** one that stays on the same path. A detail route calls `setDetail` from an effect, never its constructor.
- `frontend/src/app/shell/nav.ts` (V195-15): `detailCrumb(ticker: string | null, id: string | number | null): string` → `'NVDA #812'`, `'NVDA'`, `'#812'` or `''`. `frontend/src/app/shell/breadcrumb.ts`: the page crumb is a `routerLink` back to the list whenever a detail follows it, and the phone tab bar (V195-18) carries Watchlist and Trades, so an in-page `← Watchlist` / `← Trades` link duplicates the breadcrumb and goes in these tasks.
- `frontend/src/styles/tokens.css` (V195-6): `--text-body` is `calc(14px * var(--text-scale))` and never changes with density; `--text-table` is 13px dense, 14px comfortable. `.register-instrument` sets `--register-figure: var(--text-body)`. Every order-figure component these pages render (`levels-block.ts`, `sizing-panel.ts`, `plan-card.ts`, `position-card.ts`, `ui/plan-cell.ts`, the data-table cells, `trade-drawer.ts`'s `dt`/`dd`) sizes its text with `var(--text-table)`, so a page re-points `--text-table` to `var(--text-body)` on its own host, the way V195-27 did on `sb-positions-table`: custom properties inherit, so every figure on that page alone reaches 14px in both densities.
- V195-8: `trades.ts`'s `slot="clear-open"` / `slot="clear-history"` buttons and `trade-detail.ts`'s `[variant]="kind === 'delete' ? 'danger-quiet' : 'secondary'"` are `danger-quiet`; `trade-detail.spec.ts`'s `offers the %s commands in the header` case asserts `danger-quiet`. `watchlist.ts`'s row bin stays `danger-icon` (V195-8 left it unchanged: a per-row command on a named ticker with its own confirm, not a page command).
- V195-7b: `trade-detail.ts` imports `MINUS` and its regime line signs a loss with it; `trade-detail.spec.ts` expects `−0.38R`. V195-13: `trades.columns.ts` keeps `stop_loss` and `tier` inline from `sm` and adds the `badge` column; `sb-data-table` renders one pager, at the bottom.
- v194 converted `title` explanations in these files to `sb-hint` (for example `watchlist.ts`'s `.source-badge`, `trades.ts`'s Export CSV note, `trade-detail.ts`'s cohort chip and trade id). Keep whatever v194 left; where a quoted string below differs because v194 reworded it, keep v194's wording and make the same structural edit.

v194 and V195-1..V195-27 edited every file below. Each step names its edit by symbol or quoted string, never by line number; re-read each file before editing it.

---

# Phase 5 — Workspaces: Watchlist, Trades and the detail routes

### Task V195-28: Watchlist and ticker detail on `sb-page` (ticker detail: breadcrumb detail segment = symbol, no scope bar; order figures ≥ 14px)
**Model:** sonnet — two workspaces re-slotted onto an existing template plus one breadcrumb effect; the care is in the Watchlist's two tabs keeping one stable element per slot, the cell templates still resolving once they leave the tab `@if`, and the detail crumb surviving a title update.

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts` (template on `sb-page`; imports; styles; class doc comment)
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts` (imports; one appended `describe`)
- Modify: `frontend/src/app/workspaces/watchlist/ticker-detail.ts` (template on `sb-page` with `[heading]="symbol()"`; the detail-crumb effect; imports; styles; doc comment)
- Modify: `frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts` (imports; one appended `describe`)

**Interfaces:**
- Consumes: `Page` (`sb-page`, `ui/page.ts`, V195-21: `heading` input, slots `[page-actions]`, `[page-scope]`, `[page-primary]`, `[page-secondary]`, default slot); `RouteTitleService.detail()`, `setDetail(detail)`, `set(title, subtitle, path)` (`routing/route-title.service.ts`, V195-15); `detailCrumb(ticker, id)` (`shell/nav.ts`, V195-15); `SectionHead` (`ui/section-head.ts`: its workspace use retires here, both files drop the import); the existing `Watchlist` members (`store`, `tabs`, `activeTab`, `goToTab`, `toolbarControls`, `addingTag`, `pending`, the six cell `viewChild.required` templates) and `TickerDetail` members (`symbol`, `trades`, `chart`, `openCount`, `closedCount`, `columns`).
- Produces (nothing a later task consumes beyond V195-33's `workspace-consistency` check that `watchlist.ts` and `ticker-detail.ts` contain `<sb-page` and import `Page`):
  - Watchlist markup: `sb-page` > `div.head-status[page-actions]` (the `N watched` count, the Earnings-tab error); `div.scope[page-scope]` (`sb-tab-bar`; on the Watchlist tab the `sb-toolbar` and the `+ Tag` form); `div.tab-body[page-primary]` (Watchlist tab: the remove error and the `sb-async` around `sb-panel heading="Watchlist"`; Earnings tab: the `sb-async` around `sb-panel heading="Earnings"`); `sb-panel.add-panel[page-secondary] heading="Add tickers"` (hidden with `display: none` on the Earnings tab); then the remove `sb-confirm-dialog` and the six cell `ng-template`s in the default slot.
  - Ticker detail markup: `sb-page [heading]="symbol()"` > `span.counts[page-actions]`; `sb-chart-container[page-primary]`; `sb-panel.trades-panel[page-secondary]` (`Trades on <symbol>`, spanning both columns); cell templates in the default slot; no `[page-scope]`, no `a.back`. Host `--text-table: var(--text-body)`.
  - `RouteTitleService.detail()` reads the symbol (`'NVDA'`) while a ticker page is open, re-asserted after a title update on that page clears it.

**What changes, and what is already there.** Spec Phase 4, §5.2 (Watchlist: the watchlist table is the primary panel; detail routes use the template with the breadcrumb detail segment and no scope bar) and §1.4 (`watchlist/:symbol` is an order screen). Today Watchlist stacks `sb-section-head` (count, Earnings error), the tab bar, the *Add tickers* panel, the remove error, the toolbar, the optional `+ Tag` form, the table's `sb-async`, the confirm dialog and the cell templates, all but the first two inside `@if (activeTab() === 'watchlist')`. After this task it renders `sb-page`: the route title is the page's one `h1`; the count and the Earnings error move to the header's right (no destructive control is there: the row bin stays a per-row `danger-icon` with its own confirm, as V195-8 left it); the scope bar holds the tabs and, on the Watchlist tab, the tag/search toolbar and the `+ Tag` form (filters and scope only); the primary slot holds the active tab's table or calendar; *Add tickers* is the one secondary panel, after the table, and is hidden rather than removed on the Earnings tab so the slot stays one stable element. The cell templates move out of the tab `@if` into the default slot: an `ng-template` renders nothing, and `columns()` reads them only when the table renders, so behaviour is unchanged. Nothing is dropped: the format help, the earnings-pulse note and the Earnings help text stay word for word.

Ticker detail today shows an `← Watchlist` back link, a heading-less `sb-section-head` with the counts, the chart and the trades panel, and its own comment explains why it has no `h1` (the top bar owned the title). After this task it renders `sb-page` with the symbol as its `h1` (the page has no other identity line, and the route title `Ticker detail` names nothing), the counts at the header's right, the chart as the primary panel and *Trades on <symbol>* as the secondary panel at full width. It sets the breadcrumb's detail segment to the symbol (`Monitor / Watchlist / NVDA`), whose `Watchlist` crumb links back, so the in-page back link goes (on a phone the Watchlist tab is one tap away). The host re-points `--text-table` to the 14px body step, so the trades table's Entry and Now figures, like every figure on the page, stay at 14px in both densities.

- [ ] **Step 1: Write the failing Watchlist tests**

In `$WT/frontend/src/app/workspaces/watchlist/watchlist.spec.ts`:

1. Add below the existing imports:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { RouteTitleService } from '../../routing/route-title.service';
```

2. Append at the end of the file:

```ts
/* -- v195 Phase 4 and §5.2 -- Watchlist on sb-page ------------------------- */

describe('Watchlist on sb-page (v195 Phase 4, §5.2)', () => {
  function mountPage(tab?: string): HTMLElement {
    installDialogPolyfill();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
        WatchlistStore,
      ],
    });
    const fixture = TestBed.createComponent(Watchlist);
    if (tab) fixture.componentRef.setInput('tab', tab);
    TestBed.inject(RouteTitleService).set('Watchlist', 'The symbols being scanned');
    patchState(unprotected(TestBed.inject(WatchlistStore)), {
      tickers: [ticker({ symbol: 'NVDA' }), ticker({ symbol: 'AAPL', next_earnings_date: '2026-11-02' })],
      loaded: true,
    });
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders the route title as the one h1, from sb-page', () => {
    const el = mountPage();
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Watchlist');
    expect(el.querySelector('sb-section-head')).toBeNull();
  });

  it('puts the count at the header right and no destructive control there', () => {
    const actions = mountPage().querySelector('sb-page [page-actions]')!;
    expect(actions.querySelector('.count')!.textContent!.trim()).toBe('2 watched');
    expect(actions.querySelector('button')).toBeNull();
  });

  it('keeps tabs and filters in the scope bar, never an add or remove control', () => {
    const scope = mountPage().querySelector('sb-page [page-scope]')!;
    expect(scope.querySelector('sb-tab-bar')).toBeTruthy();
    expect(scope.querySelector('sb-toolbar [slot="tag"]')).toBeTruthy();
    expect(scope.querySelector('sb-toolbar [slot="search"]')).toBeTruthy();
    expect(scope.querySelector('[aria-label="Ticker symbols to add"]')).toBeNull();
    expect(scope.querySelector('.danger-icon')).toBeNull();
  });

  it('makes the watchlist table the primary panel', () => {
    const primary = mountPage().querySelector('sb-page [page-primary]')!;
    const panel = primary.querySelector('sb-panel[heading="Watchlist"]')!;
    expect(panel.querySelector('sb-data-table')).toBeTruthy();
    expect(panel.textContent).toContain('A row pulses when that ticker reports earnings this week.');
  });

  it('puts Add tickers in the secondary grid, as one element, after the table', () => {
    const secondary = mountPage().querySelectorAll<HTMLElement>('sb-page [page-secondary]');
    expect(secondary).toHaveLength(1);
    expect(secondary[0].getAttribute('heading')).toBe('Add tickers');
    expect(secondary[0].textContent).toContain('Ticker symbols must match Yahoo Finance format');
    expect(secondary[0].style.display).toBe('');
  });

  it('keeps the remove dialog and the cell templates working from the default slot', () => {
    const el = mountPage();
    expect(el.querySelector('sb-page sb-confirm-dialog')).toBeTruthy();
    expect(el.querySelector('tbody tr.row sb-row-link')).toBeTruthy();
  });

  it('shows the earnings calendar as the primary panel on the Earnings tab, Add tickers hidden in place', () => {
    const el = mountPage('earnings');
    const primary = el.querySelector('sb-page [page-primary]')!;
    expect(primary.querySelector('sb-panel[heading="Earnings"] sb-earnings-calendar')).toBeTruthy();
    expect(primary.querySelector('sb-data-table')).toBeNull();
    expect(el.querySelector('sb-page [page-scope] sb-toolbar')).toBeNull();
    expect(el.querySelector<HTMLElement>('sb-page [page-secondary]')!.style.display).toBe('none');
  });

  it('carries no hand-laid page grid of its own any more', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/watchlist/watchlist.ts'), 'utf8');
    expect(src).toContain('<sb-page');
    expect(src).not.toContain('<sb-section-head');
    expect(src).not.toMatch(/:host \{[^}]*grid-template-columns/);
  });
});
```

- [ ] **Step 2: Write the failing ticker-detail tests**

In `$WT/frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts`:

1. Add below the existing imports:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { RouteTitleService } from '../../routing/route-title.service';
```

2. Append at the end of the file:

```ts
/* -- v195 Phase 4, §5.2 and §1.4 -- ticker detail on sb-page ---------------- */

describe('TickerDetail on sb-page (v195 Phase 4, §5.2, §1.4)', () => {
  function mountDetail(symbol = 'NVDA'): ComponentFixture<TickerDetail> {
    installDialogPolyfill();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(), provideRouter([]),
        provideHttpClient(), provideHttpClientTesting(),
        TradesStore, ChartStore,
      ],
    });
    TestBed.overrideComponent(TickerDetail, {
      remove: { imports: [TradeChart] }, add: { imports: [ChartStub] },
    });
    const fixture = TestBed.createComponent(TickerDetail);
    TestBed.inject(RouteTitleService).set('Ticker detail', 'One symbol, in depth');
    fixture.componentRef.setInput('symbol', symbol);
    fixture.detectChanges();
    patchState(unprotected(TestBed.inject(TradesStore)), {
      data: {
        items: [row({ id: 't7', ticker: symbol, status: 'open' }), row({ id: 't8', ticker: symbol })],
        total: 2, page: 1, per_page: 25,
      },
    });
    fixture.detectChanges();
    return fixture;
  }
  const el = (fixture: ComponentFixture<TickerDetail>) => fixture.nativeElement as HTMLElement;

  it('titles the page with the symbol, as its one h1', () => {
    const page = el(mountDetail());
    expect(page.querySelectorAll('h1')).toHaveLength(1);
    expect(page.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('NVDA');
    expect(page.querySelector('sb-page .description')!.textContent!.trim()).toBe('One symbol, in depth');
  });

  it('names the symbol as the breadcrumb detail segment', () => {
    mountDetail();
    expect(TestBed.inject(RouteTitleService).detail()).toBe('NVDA');
  });

  it('puts the symbol back after a title update clears it while the page is open', () => {
    const fixture = mountDetail();
    const titles = TestBed.inject(RouteTitleService);
    titles.set('Ticker detail', 'One symbol, in depth', '/somewhere-else');
    expect(titles.detail()).toBeNull();
    fixture.detectChanges();
    expect(titles.detail()).toBe('NVDA');
  });

  it('follows the symbol when the route reuses the page for another ticker', () => {
    const fixture = mountDetail();
    fixture.componentRef.setInput('symbol', 'MSFT');
    fixture.detectChanges();
    expect(TestBed.inject(RouteTitleService).detail()).toBe('MSFT');
    expect(el(fixture).querySelector('sb-page h1.title')!.textContent!.trim()).toBe('MSFT');
  });

  it('has no scope bar and no in-page back link: the breadcrumb is the way back', () => {
    const page = el(mountDetail());
    expect(page.querySelector('[page-scope]')).toBeNull();
    expect(page.querySelector('a.back')).toBeNull();
    expect(page.querySelector('sb-section-head')).toBeNull();
  });

  it('puts the counts at the header right, the chart primary and the trades panel secondary', () => {
    const page = el(mountDetail());
    expect(page.querySelector('sb-page [page-actions]')!.textContent!.replace(/\s+/g, ' ').trim()).toBe('1 open · 1 closed');
    expect(page.querySelector('sb-page [page-primary]')!.tagName.toLowerCase()).toBe('sb-chart-container');
    const secondary = page.querySelectorAll('sb-page [page-secondary]');
    expect(secondary).toHaveLength(1);
    expect(secondary[0].querySelector('sb-data-table')).toBeTruthy();
    expect(secondary[0].querySelector('a.all-link')!.getAttribute('href')).toBe('/trades?ticker=NVDA');
  });

  it('sets its order figures on the 14px body step, in both densities', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/watchlist/ticker-detail.ts'), 'utf8');
    expect(src).toMatch(/:host \{[^}]*--text-table: var\(--text-body\);/);
  });
});
```

`row()` builds `status: 'CLOSED'` by default, so the fixture holds one `open` and one closed row; `openCount` filters `status === 'open'` exactly as today.

- [ ] **Step 3: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/watchlist/watchlist.spec.ts --include src/app/workspaces/watchlist/ticker-detail.spec.ts
```

Expected: FAIL. No `sb-page`, so no `h1` and no slot elements; `sb-section-head` is present; `RouteTitleService.detail()` stays `null`; `a.back` exists; the source has no `--text-table` override.

- [ ] **Step 4: Move Watchlist onto `sb-page`**

In `$WT/frontend/src/app/workspaces/watchlist/watchlist.ts`:

1. Imports: add `import { Page } from '../../ui/page';`; delete `import { SectionHead } from '../../ui/section-head';`. In the component's `imports` array replace `SectionHead` with `Page`.

2. Template: replace the whole template with the structure below. Each `<!-- MOVE: … -->` line is an instruction to this step, not template text: cut the named block from today's template (with its own comments) and paste it verbatim in that place; none of the `MOVE` lines stays in the file. Only the wrappers and the `@if` boundaries shown are new.

```html
    <sb-page>
      <!-- v195 Phase 4: the count and the Earnings error sit at the header's
           right. No destructive control lives here: removing a ticker is a
           per-row command on a named symbol with its own confirm (V195-8
           kept its danger-icon). -->
      <div page-actions class="head-status">
        <span class="count">{{ store.count() }} watched</span>
        <!-- MOVE: the comment that starts "Only for Earnings:" and its
             @if (activeTab() === 'earnings' && store.error(); as message) { <span class="stale" role="status"> } block -->
      </div>

      <!-- Scope only (spec Phase 4): the tabs, then on the Watchlist tab the
           tag/search toolbar and the + Tag form. -->
      <div page-scope class="scope">
        <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="goToTab($event)" />
        @if (activeTab() === 'watchlist') {
          <!-- MOVE: the "v85 D35/R7-05" comment and the whole <sb-toolbar [controls]="toolbarControls()"> … </sb-toolbar> -->
          <!-- MOVE: the whole @if (addingTag()) { <sb-control-row class="tag-form"> … } block -->
        }
      </div>

      <!-- v195 §5.2: the page's main table (or, on Earnings, its calendar)
           is the primary panel. One element; the tab switch is inside it. -->
      <div page-primary class="tab-body">
        @if (activeTab() === 'watchlist') {
          <!-- MOVE: the @if (store.removeError(); as message) { <p class="error" role="alert"> } block -->
          <!-- MOVE: the <sb-async … emptyTitle="No tickers on the watchlist" …> block with its sb-panel heading="Watchlist" and sb-data-table -->
        }
        @if (activeTab() === 'earnings') {
          <!-- MOVE: the <sb-async … emptyTitle="No earnings to display" …> block with its sb-panel heading="Earnings" -->
        }
      </div>

      <!-- Adding is the secondary panel, after the table it feeds. Hidden,
           not removed, on Earnings: the slot stays one stable element
           (sb-page contract). -->
      <sb-panel
        page-secondary
        class="add-panel"
        heading="Add tickers"
        [style.display]="activeTab() === 'watchlist' ? null : 'none'"
      >
        <!-- MOVE: the whole body of today's <sb-panel heading="Add tickers">, from the "SR62." comment
             through the @if (store.addError(); as message) block -->
      </sb-panel>

      <!-- MOVE: <sb-confirm-dialog [open]="pending() !== null" title="Remove from the watchlist" … /> -->

      <!-- cells ----------------------------------------------------------- -->
      <!-- Outside any @if since v195: an ng-template renders nothing, and
           columns() reads these only when the table renders. -->
      <!-- MOVE: the six <ng-template> blocks #tapeCell, #symbolCell, #priceCell, #sparkCell, #signalCell, #actionsCell with their comments -->
    </sb-page>
```

   The old outer `@if (activeTab() === 'watchlist') { … }` and `@if (activeTab() === 'earnings') { … }` wrappers are gone: their contents now sit in the places above.

3. Styles: replace

```css
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }
```

   together with the two comments above it (`/* minmax(0, 1fr), not the implicit auto track. …` and `/* v54 D1: --space-20 was this rule's own literal …`) with

```css
    /* v195 Phase 4: sb-page owns the page rhythm (header, scope, primary,
       secondary). min-width: 0 keeps a wide table scrolling inside its own
       container instead of taking the page sideways. */
    :host { display: block; min-width: 0; }
    .scope, .tab-body { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--register-pad); }
```

   Keep `.head-status` and every other rule. In the `.count` rule's comment, replace `beside the section head` with `at the page header's right`.

4. In the class doc comment above `@Component`, after the paragraph that starts `**One add box for single and bulk.**`, add:

```ts
 *
 * **On sb-page since v195.** Tabs and filters are the scope bar, the table
 * (or the earnings calendar) the primary panel, Add tickers the one
 * secondary panel; the count sits in the header.
```

- [ ] **Step 5: Move ticker detail onto `sb-page`**

In `$WT/frontend/src/app/workspaces/watchlist/ticker-detail.ts`:

1. Imports: add `untracked` to the `@angular/core` import list; add

```ts
import { RouteTitleService } from '../../routing/route-title.service';
import { detailCrumb } from '../../shell/nav';
import { Page } from '../../ui/page';
```

   and delete `import { SectionHead } from '../../ui/section-head';`. The component's `imports` become `[RouterLink, Page, Panel, DataTable, ChartContainer, RowLink, TradeChart]`.

2. Template: replace everything from the first comment (`<!-- The breadcrumb sits above the header rather than inside it: …`) through the closing `</sb-panel>` with:

```html
    <!-- v195 Phase 4: the symbol is the page's one h1 (the route title,
         "Ticker detail", names nothing). The breadcrumb's detail segment is
         the symbol too, and its Watchlist crumb is the way back, so there is
         no in-page back link and no scope bar (spec §5.2). -->
    <sb-page [heading]="symbol()">
      <span page-actions class="counts">
        {{ openCount() }} open · {{ closedCount() }} closed
      </span>

      <sb-chart-container
        page-primary
        [loading]="chart.loading()"
        [error]="chart.error()"
        [hasData]="!chart.isEmpty()"
        [height]="380"
        [caption]="symbol() + ' — daily'"
      >
        <sb-trade-chart [data]="chart.data()" />
      </sb-chart-container>

      <sb-panel page-secondary class="trades-panel" [heading]="'Trades on ' + symbol()" [flush]="true">
        <a panel-actions class="all-link sb-hit" routerLink="/trades" [queryParams]="{ ticker: symbol() }">
          Open in Trades →
        </a>

        @if (trades.error(); as message) {
          <!-- Without this a failed load renders as the table's empty state,
               and "No trades" would be a claim about this ticker rather than
               about the network. -->
          <p class="table-error" role="status">{{ message }}</p>
        }

        <sb-data-table
          [rows]="tradesPage.visible()"
          [columns]="columns()"
          [visible]="visible"
          [rowKey]="rowKey"
          [loading]="trades.loading() && trades.empty()"
          [emptyState]="emptyState"
          [sort]="sort()"
          [pagination]="tradesPage.pageSpec()"
          [showPerPage]="true"
          phoneTap="drawer"
          [detailLink]="tradeLink"
          (sortChange)="setSort($event)"
          (pageChange)="tradesPage.setPage($event)"
          (perPageChange)="onPerPage($event)"
        />
      </sb-panel>
```

   Then, after the two `<ng-template>` cell blocks (`#tickerCell`, `#pnlCell`, unchanged with their comments), close the page with `</sb-page>`, so the templates sit in the default slot.

3. Styles: replace the first comment block (`/* minmax(0, 1fr), not the implicit auto track. …`) and `:host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }`, and delete the `.back` and `.back:hover` rules, with:

```css
    /* v195 Phase 4: sb-page owns the page rhythm. §1.4: entry and the live
       price are order figures and never shrink below the 14px body step, in
       either density; every figure here reads --text-table, so the page
       re-points it on its own host. */
    :host { display: block; min-width: 0; --text-table: var(--text-body); }
    /* A table: it takes both columns of the secondary grid from 1440px. */
    .trades-panel { grid-column: 1 / -1; }
```

   Keep `.counts`, `.all-link`, `.table-error` and `sb-row-link`.

4. In the class: add the injection beside `private readonly now = inject(CLOCK);`:

```ts
  private readonly titles = inject(RouteTitleService);
```

   and at the end of the constructor, after `effect(() => this.chart.setTarget(this.symbol()));`, add:

```ts

    // v195: the breadcrumb's detail segment (Monitor / Watchlist / NVDA).
    // From an effect, never the constructor body: the router writes the
    // title after it activates the route. Reading detail() as well puts the
    // symbol back if a title update cleared it while this page is open.
    effect(() => {
      const crumb = detailCrumb(this.symbol(), null);
      this.titles.detail();
      untracked(() => this.titles.setDetail(crumb));
    });
```

5. In the class doc comment, append a paragraph:

```ts
 *
 * On sb-page since v195: the symbol is the h1 and the breadcrumb's detail
 * segment, the chart the primary panel, the trades panel the secondary one,
 * and every figure on the page reads the 14px body step (spec §1.4).
```

   The template's old `<!-- v85 D4/R7-06: no in-page heading -- … -->` comment went with step 2.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/watchlist --include src/app/ui/primitives.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/title-usage.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. Every existing Watchlist case still passes: `rows()` finds `tbody tr.row` wherever the table sits, and `keeps the add-ticker control usable while the watchlist is empty` finds an `input` and an `Add` button (the toolbar's search input now comes first in the DOM, which that case allows). If a cell template is missing (`NG0951`), it was left inside an `@if`; it must sit directly in `sb-page`'s default slot. If the detail case reads `null` after `detectChanges`, the effect is not reading `this.titles.detail()`; if it loops (`NG0103`), `setDetail` is not inside `untracked`. If `workspace-consistency.spec.ts` flags a missing `sb-freshness`, the Watchlist `sb-async` lost its `[staleAsOf]` binding in the move.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 7: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard` and click through. At 1440, 768 and 390 on `/watchlist`: one `h1` `Watchlist`; `N watched` at the header's right; tabs, then tag chips and search in the scope bar; the table directly under it; *Add tickers* below the table; switch to Earnings and see the calendar with no toolbar and no Add panel; back to Watchlist. Open a ticker: the `h1` is the symbol; the breadcrumb reads `Monitor / Watchlist / <symbol>` at 768 and 1440 (only the symbol at 390); click the `Watchlist` crumb and land back on the list. On the ticker page, the font size of a numeric cell in the trades table (`getComputedStyle(document.querySelector('sb-ticker-detail sb-data-table td.numeric')).fontSize`, or the phone card's numeric value at 390) is `14px` at 1440 dense, 1440 comfortable, 768 and 390. No horizontal page scroll at any width (`document.documentElement.scrollWidth <= innerWidth`). Do **not** add or remove a ticker. Save the PNGs under the session scratchpad.

- [ ] **Step 8: Close**

Close: standard (test: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`), plus `frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/watchlist/watchlist.spec.ts frontend/src/app/workspaces/watchlist/ticker-detail.ts frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts
git -C "$WT" commit -m "feat(v195): Watchlist and ticker detail on sb-page (V195-28)" -m "Spec Phase 4, §5.2 and §1.4. Watchlist: tabs and filters in the scope bar, the table (or the earnings calendar) primary, Add tickers secondary, the count in the header; the row bin stays a per-row danger-icon. Ticker detail: the symbol is the h1 and the breadcrumb detail segment, the chart primary, the trades panel secondary, no scope bar and no back link (the Watchlist crumb is the way back); every figure on the page reads the 14px body step." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

### Task V195-29: Trades on `sb-page`: toolbar in the scope bar, trade table primary, Clear open / Clear history in `[page-actions]` (`danger-quiet`)
**Model:** sonnet — one workspace re-slotted onto an existing template and two controls moved out of a toolbar table; the care is in the bulk-clear confirm still opening from its new place, the scope bar carrying no destructive control, and the cell templates resolving from the default slot.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.ts` (`TRADES_CONTROLS` and its doc comment; the `isFilterEngaged` doc comment; template on `sb-page`; imports; styles; class doc comment)
- Modify: `frontend/src/app/workspaces/trades/trades.spec.ts` (imports; the `leaves a filter at its default unmarked` comment; one appended `describe`)

**Interfaces:**
- Consumes: `Page` (`sb-page`, `ui/page.ts`, V195-21); `Toolbar`, `ToolbarControl` (`ui/toolbar.ts`); `button[sb-button]` `variant="danger-quiet"` and `ConfirmDialog.dangerVariant` (default `danger-quiet`, V195-8); `RouteTitleService.set(title, subtitle)` (spec only); the existing `Trades` members `store` (`clearResult`, `clearError`, `clearing`, `activeFilterCount`), `bulk`, `bulkTitle`, `bulkConsequence`, `runBulk`, `toolbarControls`, `countText`, `async`, `announce`, the cell `viewChild` templates; the `TradesStore` state keys `clearResult`, `clearError` (spec seeds them with `patchState(unprotected(...))`).
- Produces (nothing a later task consumes beyond V195-33's `workspace-consistency` check that `trades.ts` contains `<sb-page` and imports `Page`):
  - `TRADES_CONTROLS` loses `clear-open` and `clear-history` (13 entries, `status` … `note`, floors unchanged).
  - Markup: `sb-page` > `div.page-actions[page-actions]` (optional `p.cleared[role="status"]`, optional `p.command-error[role="alert"]`, `button[sb-button][data-action="clear-open"]` and `button[sb-button][data-action="clear-history"]`, both `variant="danger-quiet"`); `div.scope[page-scope]` (`sb-toolbar`, `sb-filter-bar`); `div.table-body[page-primary]` (the `sb-async` around `sb-data-table`, then the optional `p.count`); the two `sb-confirm-dialog`s and the cell `ng-template`s in the default slot.

**What changes, and what is already there.** Spec Phase 4 and §5.2 (Trades: the trade table is the primary panel; destructive actions only in the header's actions slot, always confirming, as `danger-quiet`). Today Trades stacks the clear result/error lines, one `sb-toolbar` whose last two controls are **Clear open** and **Clear history** (demoted into the toolbar's sheet below 1440px, inline above it), the `sb-filter-bar` summary, the table's `sb-async`, the count footer, two confirm dialogs and the cell templates. After this task it renders `sb-page`: the route title is the page's one `h1`; the two bulk clears leave the toolbar for the header's right, still `danger-quiet`, still opening the same bulk `sb-confirm-dialog` (default `dangerVariant`, so `danger-quiet`), and visible at every width, since a header action never folds into a filter sheet; the clear result and the clear error sit beside the buttons that produced them (the same move Risk made with its command error, V195-25). The scope bar holds the toolbar (filters, column picker, column-set toggle, Export CSV) and the active-filter summary: filters and scope only. The table, with its count footer, is the primary panel. `TRADES_CONTROLS` drops the two clear entries, and its doc comment's sentence about demoting them furthest becomes the reason they left. The cell templates and the two dialogs sit in the default slot, unchanged. The host keeps `register-instrument`, whose figure step V195-6 already raised to 14px. No KPI strip: Trades has no headline figure the store already computes, and inventing one is out of scope.

- [ ] **Step 1: Write the failing tests**

In `$WT/frontend/src/app/workspaces/trades/trades.spec.ts`:

1. Add below the existing imports:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { RouteTitleService } from '../../routing/route-title.service';
```

2. In `it('leaves a filter at its default unmarked', ...)`, replace the comment `// columns/density/export/clear-* are not filters and report no state.` with `// columns/density/export are not filters and report no state.`

3. Append at the end of the file:

```ts
/* -- v195 Phase 4 and §5.2 -- Trades on sb-page ----------------------------- */

describe('Trades on sb-page (v195 Phase 4, §5.2)', () => {
  function mountPage(): ComponentFixture<Trades> {
    installDialogPolyfill();
    const fixture = render({ total: 0, page: 1, perPage: 12 });
    TestBed.inject(RouteTitleService).set('Trades', 'Every plan, filled or not');
    fixture.detectChanges();
    return fixture;
  }
  const el = (fixture: ComponentFixture<Trades>) => fixture.nativeElement as HTMLElement;

  it('renders the route title as the one h1, from sb-page', () => {
    const page = el(mountPage());
    expect(page.querySelectorAll('h1')).toHaveLength(1);
    expect(page.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Trades');
  });

  it('puts Clear open and Clear history in the header actions, quiet, never solid', () => {
    const actions = el(mountPage()).querySelector('sb-page [page-actions]')!;
    const buttons = [...actions.querySelectorAll<HTMLButtonElement>('button[sb-button]')];
    expect(buttons.map((b) => b.getAttribute('data-action'))).toEqual(['clear-open', 'clear-history']);
    expect(buttons.map((b) => b.textContent!.trim())).toEqual(['Clear open', 'Clear history']);
    for (const button of buttons) {
      expect(button.classList).toContain('danger-quiet');
      expect(button.classList).not.toContain('danger');
    }
  });

  it('confirms a bulk clear from the header before anything is deleted', () => {
    const fixture = mountPage();
    el(fixture).querySelector<HTMLButtonElement>('[page-actions] [data-action="clear-history"]')!.click();
    fixture.detectChanges();
    const dialog = el(fixture).querySelector('sb-page sb-confirm-dialog:last-of-type')!;
    expect(dialog.textContent).toContain('Clear trade history');
    expect(TestBed.inject(TradesStore).clearing()).toBeNull();
  });

  it('reports a clear result and a clear error beside the buttons that sent it', () => {
    const fixture = mountPage();
    patchState(unprotected(TestBed.inject(TradesStore)), {
      clearResult: 'Cleared 3 open positions.',
      clearError: 'Clear failed: unavailable',
    });
    fixture.detectChanges();
    const actions = el(fixture).querySelector('sb-page [page-actions]')!;
    expect(actions.querySelector('p.cleared[role="status"]')!.textContent).toContain('Cleared 3 open positions.');
    expect(actions.querySelector('p.command-error[role="alert"]')!.textContent).toContain('Clear failed: unavailable');
  });

  it('keeps the scope bar to filters and scope: no destructive control in it', () => {
    const scope = el(mountPage()).querySelector('sb-page [page-scope]')!;
    expect(scope.querySelector('sb-toolbar [slot="status"]')).toBeTruthy();
    expect(scope.querySelector('sb-toolbar [slot="columns"]')).toBeTruthy();
    expect(scope.querySelector('sb-filter-bar')).toBeTruthy();
    expect(scope.querySelector('[slot^="clear"]')).toBeNull();
    expect(scope.querySelector('.danger, .danger-quiet')).toBeNull();
  });

  it('drops the two clear controls from the toolbar priorities', () => {
    expect(TRADES_CONTROLS.map((c) => c.id)).toEqual([
      'status', 'columns', 'density', 'export', 'dates', 'ticker', 'origin',
      'strategy', 'horizon', 'confidence', 'tier', 'badge', 'note',
    ]);
  });

  it('makes the trade table, with its count footer, the primary panel', () => {
    const primary = el(mountPage()).querySelector('sb-page [page-primary]')!;
    expect(primary.querySelector('sb-async')).toBeTruthy();
    expect(primary.querySelector('p.count')!.textContent).toContain('No trades yet');
  });

  it('renders the table rows through the cell templates in the default slot', () => {
    const page = renderRows([row({ id: 'abcdef123456' })]);
    expect(page.querySelector('sb-page [page-primary] tbody tr.row sb-row-link')).toBeTruthy();
  });

  it('carries no hand-laid page grid of its own any more', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/trades/trades.ts'), 'utf8');
    expect(src).toContain('<sb-page');
    expect(src).not.toMatch(/:host \{[^}]*grid-template-columns/);
  });
});
```

   `render()` and `renderRows()` are this file's existing helpers; `row()` builds a closed `AAPL` trade.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/trades.spec.ts
```

Expected: FAIL. No `sb-page`, so no `h1` and no slot elements; `TRADES_CONTROLS` still lists `clear-open` and `clear-history`; the clear buttons sit inside `sb-toolbar`.

- [ ] **Step 3: Trim `TRADES_CONTROLS`**

In `$WT/frontend/src/app/workspaces/trades/trades.ts`:

1. Delete the two entries `{ id: 'clear-open', label: 'Clear open', inlineFrom: 'lg' },` and `{ id: 'clear-history', label: 'Clear history', inlineFrom: 'lg' },`.

2. In the doc comment above `TRADES_CONTROLS`, replace the paragraph

```ts
 * The two destructive controls demote furthest (`lg`). They were the first
 * thing under a thumb at 390px, above the data they destroy.
```

   with

```ts
 * The two destructive controls are not here. They used to demote furthest
 * (`lg`), having been the first thing under a thumb at 390px; since v195
 * they sit in the page header's actions slot (spec Phase 4), the one home
 * of a destructive control, and never fold into the filter sheet.
```

3. In the doc comment of `isFilterEngaged`, replace `` `columns`, `density`, `export` and the two destructive controls are not `` with `` `columns`, `density` and `export` are not ``.

- [ ] **Step 4: Move Trades onto `sb-page`**

Still in `trades.ts`:

1. Imports: add `import { Page } from '../../ui/page';` and add `Page` to the component's `imports` array (first entry).

2. Template: replace the whole template with the structure below. Each `<!-- MOVE: … -->` line is an instruction to this step, not template text: cut the named block from today's template (with its own comments) and paste it verbatim there; none of the `MOVE` lines stays in the file. Only the wrappers and the two buttons shown are new.

```html
    <sb-page>
      <!-- v195 Phase 4: the header's actions slot is the one home of a
           destructive control. Both clears are bulk deletes, so they are
           danger-quiet and open the bulk confirm below; the result and the
           error read beside the buttons that sent them. -->
      <div page-actions class="page-actions">
        <!-- MOVE: the @if (store.clearResult(); as message) { <p class="cleared" role="status"> } block with its comment -->
        <!-- MOVE: the @if (store.clearError(); as message) { <p class="command-error" role="alert"> } block -->
        <button
          sb-button
          variant="danger-quiet"
          type="button"
          data-action="clear-open"
          (click)="bulk.set('open')"
        >
          Clear open
        </button>
        <button
          sb-button
          variant="danger-quiet"
          type="button"
          data-action="clear-history"
          (click)="bulk.set('history')"
        >
          Clear history
        </button>
      </div>

      <!-- Scope only (spec Phase 4): filters, the column picker, the
           column-set toggle, Export CSV and the active-filter summary. -->
      <div page-scope class="scope">
        <!-- MOVE: the "v95 C1" comment and the whole <sb-toolbar [controls]="toolbarControls()"> … </sb-toolbar>,
             minus its two last children, the slot="clear-open" and slot="clear-history" buttons, which are deleted -->
        <!-- MOVE: the "What sb-filter-bar keeps after C1" comment and <sb-filter-bar … (cleared)="clearFilters()" /> -->
      </div>

      <!-- v195 §5.2: the trade table is the primary panel. -->
      <div page-primary class="table-body">
        <!-- MOVE: the "v54: rows=12 cols=8" comment and the whole <sb-async …> … </sb-async> around sb-data-table -->
        <!-- MOVE: the "R6-05: the count footer" comment and the @if (countText(); as count) { <p class="count"> } block -->
      </div>

      <!-- MOVE: the "cells" divider comment and every <ng-template> block (#numCell through the last cell template), unchanged -->
      <!-- MOVE: both <sb-confirm-dialog> blocks with the comment between them, unchanged -->
    </sb-page>
```

   The Export CSV anchor keeps whatever v194 left on it (a hint or its note): only its position inside the toolbar is unchanged.

3. Styles: replace

```css
    /* v89 audit (UA15): sb-trades had no :host stacking rule, so its
       top-level children (section head, control bar, filter bar, the
       table) sat flush against each other instead of --section-gap apart.
       Same pattern as every other workspace host. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }
```

   with

```css
    /* v195 Phase 4: sb-page owns the page rhythm (header, scope, primary).
       min-width: 0 keeps the 29-column table scrolling inside its own
       container instead of taking the page sideways. */
    :host { display: block; min-width: 0; }
    .scope, .table-body { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--register-pad); }
    /* Wraps under the title on a phone; the result and error lines take
       their own row above the buttons. */
    .page-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: var(--space-8); }
    .page-actions p { flex: 1 0 100%; margin: 0; text-align: right; }
```

   Keep every other rule (`.cleared`, `.command-error`, `.count`, `.density`, `.export`, …).

4. In the class doc comment (`The Trades workspace — the entity that Plans, Journal …`), append:

```ts
 *
 * On sb-page since v195: the toolbar and filter summary are the scope bar,
 * the table the primary panel, and the two bulk clears the header's
 * actions, each behind its confirm.
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/trades/trades.columns.spec.ts --include src/app/ui/button.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/title-usage.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. The existing chip cases still find `sb-toolbar [slot=status] .chip`; the count-footer cases still find `p.count` and one `.bar .range`. V195-8's `button.spec.ts` source scan (only the Risk killswitch uses `variant="danger"`) stays green: both new buttons are `danger-quiet`. If the bulk-confirm case finds the row dialog's text, `:last-of-type` picked the wrong dialog: the bulk `sb-confirm-dialog` must stay the second of the two, as today. If a cell template is missing (`NG0951`), it was left outside `sb-page`; it must sit in the default slot.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 6: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard` and click to Trades. At 1440, 768 and 390: one `h1` `Trades`; `Clear open` and `Clear history` at the header's right, bordered red text on no fill (not solid), wrapping under the title at 390 and at least 44px tall at 768 and 390; open `Clear history`, read the confirm, and press **Cancel** (never confirm: it deletes the trade log). The toolbar sits under the header with the status chips and the column picker inline at 390, and its sheet (below 1024px) lists no clear control. The table follows with one pager at the bottom. No horizontal page scroll (`document.documentElement.scrollWidth <= innerWidth`). Save the PNGs under the session scratchpad.

- [ ] **Step 7: Close**

Close: standard (test: `frontend/src/app/workspaces/trades/trades.spec.ts`). One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/trades/trades.spec.ts
git -C "$WT" commit -m "feat(v195): Trades on sb-page, bulk clears in the header (V195-29)" -m "Spec Phase 4 and §5.2. Trades renders sb-page: Clear open and Clear history leave the toolbar for the header's actions slot (danger-quiet, same confirm, visible at every width) with their result and error beside them; the toolbar and filter summary are the scope bar; the table and its count footer are the primary panel. TRADES_CONTROLS drops the two clear entries." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

### Task V195-30: Trade detail and plan detail on `sb-page`: breadcrumb detail `NVDA #812`, no scope bar, delete in `[page-actions]`, entry/stop/target/size/risk figures ≥ 14px
**Model:** sonnet — two detail routes re-slotted onto an existing template, one pure crumb helper and a token re-point on three hosts; the care is in the trade commands keeping their confirm from the header, the existing identity and outcome-strip specs keeping their DOM shape, and the crumb surviving a title update.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (new export `tradeCrumb`; template on `sb-page`; the detail-crumb effect; imports; styles; class doc comment)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (imports; the two header-command cases' selectors; one appended `describe`)
- Modify: `frontend/src/app/workspaces/plans/plan-detail.ts` (template on `sb-page`; the detail-crumb effect; imports; styles; class doc comment)
- Modify: `frontend/src/app/workspaces/plans/plan-detail.spec.ts` (imports; one appended `describe`)
- Modify: `frontend/src/app/workspaces/dashboard/trade-drawer.ts` (the `:host` rule and its comment)
- Modify: `frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts` (one appended `describe`)

**Interfaces:**
- Consumes: `Page` (`sb-page`, `ui/page.ts`, V195-21); `RouteTitleService.detail()`, `setDetail(detail)`, `set(title, subtitle, path)` (V195-15); `detailCrumb(ticker, id)` (`shell/nav.ts`, V195-15); `button[sb-button]` `variant="danger-quiet"`, `ConfirmDialog.dangerVariant` default `danger-quiet` (V195-8; `trade-detail.ts` already binds `[variant]="kind === 'delete' ? 'danger-quiet' : 'secondary'"`); `MINUS` in `trade-detail.ts` (V195-7b, untouched here); the existing `TradeDetail` members (`store`, `actionsFor`, `actionLabels`, `ask`, `arrival`, `side`, `stripTiles`, `tabs`, `activeTab`, `goToTab`, `async`, `pending`, `confirmTitle`, `confirmConsequence`, `confirmLabel`, `working`, `runPending`) and `PlanDetail` members (`store`, `id`, `async`, `timing`, `strategyLine`, `createdAt`, `orderNotes`, `stopLabel`).
- Produces (nothing a later task consumes beyond V195-33's `workspace-consistency` check that `trade-detail.ts` and `plan-detail.ts` contain `<sb-page` and import `Page`):
  - `trade-detail.ts` exports `tradeCrumb(ticker: string | null, id: string | null): string` — `detailCrumb(ticker, <id's last six characters, or the whole id when it is six or fewer>)`, the same short id the Trades table's ID column shows (`trades.ts` `shortId`): `tradeCrumb('NVDA', 'ffffffffff000812')` → `'NVDA #000812'`, `tradeCrumb('NVDA', null)` → `'NVDA'`, `tradeCrumb(null, null)` → `''`. `plan-detail.ts` imports it.
  - Trade detail markup: `sb-page` > `div.page-actions[page-actions]` (the trade's commands, `Delete` last as `danger-quiet`, none before the trade loads); `div.summary[page-kpis]` (`header.head` with the arrival banner and the identity line or its error/loading line, then `sb-outcome-strip` once the trade loads, still adjacent); `div.tab-body[page-primary]` (`sb-tab-bar`, then the tab `sb-async`); the command `sb-confirm-dialog` in the default slot; no `[page-scope]`, no `a.back`. Host `--text-table: var(--text-body)`.
  - Plan detail markup: `sb-page` > `div.summary[page-kpis]` (`header.plan-head` without its back link); `sb-async[page-primary]` (the plan body, unchanged); no `[page-actions]`, no `[page-scope]`, no `a.back`. Host `--text-table: var(--text-body)`.
  - `sb-trade-drawer` host: `display: contents; --text-table: var(--text-body)`.
  - `RouteTitleService.detail()` reads `tradeCrumb(trade.ticker, trade.id)` on both pages once the record loads, re-asserted after a title update clears it while the page is open.

**What changes, and what is already there.** Spec Phase 4, §5.2 (detail routes use the template, with the breadcrumb detail segment and no scope bar), §3 (`Review / Trades / NVDA #812`), §1.4 (the trade drawer, `trades/:id` and `plans/:id` are order screens) and the index's Global Constraints (any delete lives only in `[page-actions]` and confirms as `danger-quiet`). Today the trade page opens with an `← Trades` link and a `header.head` whose identity row ends in the trade's commands (Close / Cancel plan / Delete, the last `danger-quiet` since V195-8), then the outcome strip, the tab bar and the tab body, then the command confirm. After this task it renders `sb-page`: the route title `Trade detail` is the page's one `h1`; the commands move to the header's right (the delete still opens the same confirm, `danger-quiet`); the identity row (ticker, side, status, tags, id, earnings and cohort chips, arrival banner) and the outcome strip become the summary in the KPI slot, in today's order, so `header.head + sb-outcome-strip` still holds; the tab bar and its body are the primary panel. The plan page (read-only on purpose: it places, edits and cancels nothing, so it has no header actions) loses its `← Trades` link the same way, its header becomes the summary and its body the primary panel. Both pages set the breadcrumb detail segment to `<ticker> #<short id>` once the record loads, the same six characters the Trades list shows in its ID column, so `Review / Trades / NVDA #a1b2c3` names what the list named; the `Trades` crumb links back, and on a phone the Trades tab is one tap away. Both page hosts and the Dashboard's trade drawer re-point `--text-table` to the 14px body step: the level, plan, position and sizing cards and the drawer's fields all size their figures with `--text-table`, so entry, stop, target, size and risk figures reach 14px in both densities without touching those shared components. Nothing is dropped: every card, banner, hint and caveat stays where it is inside its slot.

- [ ] **Step 1: Write the failing trade-detail tests**

In `$WT/frontend/src/app/workspaces/trades/trade-detail.spec.ts`:

1. Add `import { RouteTitleService } from '../../routing/route-title.service';` below the existing imports, and change `import { TradeDetail, arrivalBanner } from './trade-detail';` to `import { TradeDetail, arrivalBanner, tradeCrumb } from './trade-detail';`.

2. In `it.each([...])('offers the %s commands in the header', ...)`, replace

```ts
    const buttons = [...el.querySelectorAll<HTMLButtonElement>('.identity > .actions > button[sb-button]')];
```

   with

```ts
    const buttons = [...el.querySelectorAll<HTMLButtonElement>('sb-page [page-actions] button[sb-button]')];
```

   (the `danger-quiet` class assertion V195-8 left and the no-`Actions`-panel assertion stay as they are).

3. In `it('offers Close on a live position (SR48, through the real component)', ...)`, replace `el.querySelector<HTMLButtonElement>('.identity .actions button')` with `el.querySelector<HTMLButtonElement>('sb-page [page-actions] button')`.

4. Append at the end of the file:

```ts
/* -- v195 Phase 4, §5.2, §1.4 -- trade detail on sb-page -------------------- */

describe('tradeCrumb (v195 §3)', () => {
  it('names the ticker and the short id the Trades list shows', () => {
    expect(tradeCrumb('NVDA', 'ffffffffff000812')).toBe('NVDA #000812');
    expect(tradeCrumb('NVDA', 'abc812')).toBe('NVDA #abc812');
    expect(tradeCrumb('NVDA', '812')).toBe('NVDA #812');
  });

  it('drops a missing part and is empty with neither', () => {
    expect(tradeCrumb('NVDA', null)).toBe('NVDA');
    expect(tradeCrumb(null, '44444444-4444-4444-8444-444444444444')).toBe('#444444');
    expect(tradeCrumb(null, null)).toBe('');
  });
});

describe('TradeDetail on sb-page (v195 Phase 4, §5.2, §1.4)', () => {
  let backend: HttpTestingController;
  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
    TestBed.inject(RouteTitleService).set('Trade detail', 'One position, end to end');
  });

  function mount(status = 'ACTIVE', flush = true) {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', 'overview');
    fixture.detectChanges();
    if (flush) {
      backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(DETAIL, status));
      fixture.detectChanges();
    }
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('renders the route title as the one h1, from sb-page', () => {
    const { el } = mount();
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Trade detail');
  });

  it('names the trade as the breadcrumb detail segment once it loads', () => {
    const { fixture } = mount('ACTIVE', false);
    const titles = TestBed.inject(RouteTitleService);
    expect(titles.detail()).toBeNull();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(DETAIL, 'ACTIVE'));
    fixture.detectChanges();
    expect(titles.detail()).toBe('AAPL #ffffff');
  });

  it('puts the crumb back after a title update clears it while the page is open', () => {
    const { fixture } = mount();
    const titles = TestBed.inject(RouteTitleService);
    titles.set('Trade detail', null, '/somewhere-else');
    expect(titles.detail()).toBeNull();
    fixture.detectChanges();
    expect(titles.detail()).toBe('AAPL #ffffff');
  });

  it('renders no command before the trade has loaded', () => {
    const { fixture, el } = mount('ACTIVE', false);
    expect(el.querySelectorAll('sb-page [page-actions] button')).toHaveLength(0);
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(DETAIL, 'ACTIVE'));
    fixture.detectChanges();
    expect(el.querySelectorAll('sb-page [page-actions] button')).toHaveLength(2);
  });

  it('opens the delete confirm from the header', () => {
    const { fixture, el } = mount('CLOSED');
    const buttons = [...el.querySelectorAll<HTMLButtonElement>('sb-page [page-actions] button[sb-button]')];
    const del = buttons.at(-1)!;
    expect(del.textContent!.trim()).toBe('Delete');
    expect(del.classList).toContain('danger-quiet');
    expect(del.classList).not.toContain('danger');
    del.click();
    fixture.detectChanges();
    expect(el.querySelector('sb-page sb-confirm-dialog')!.textContent).toContain('AAPL');
  });

  it('has no scope bar and no in-page back link: the breadcrumb is the way back', () => {
    const { el } = mount();
    expect(el.querySelector('[page-scope]')).toBeNull();
    expect(el.querySelector('a.back')).toBeNull();
  });

  it('keeps identity then the outcome strip as the summary, and the tabs as the primary panel', () => {
    const { el } = mount();
    const summary = el.querySelector('sb-page [page-kpis]')!;
    expect(summary.querySelector('header.head > .identity > .trade-title .ticker')!.textContent).toBe('AAPL');
    expect(summary.querySelector('header.head + sb-outcome-strip')).toBeTruthy();
    expect(summary.querySelector('.actions')).toBeNull();
    const primary = el.querySelector('sb-page [page-primary]')!;
    expect(primary.querySelector('sb-tab-bar')).toBeTruthy();
    expect(primary.querySelector('sb-async')).toBeTruthy();
  });

  it('sets its order figures on the 14px body step, in both densities', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/trades/trade-detail.ts'), 'utf8');
    expect(src).toMatch(/:host \{[^}]*--text-table: var\(--text-body\);/);
  });
});
```

   `ID` (`'ffffffffffffffff'`), `DETAIL`, `tradeResponse`, `FakeEventStream`, `readFileSync` and `join` already exist in this file; `tradeResponse` serves ticker `AAPL`. The `no command before the trade has loaded` case flushes its pending request itself, so `HttpTestingController` verification stays clean; an `ACTIVE` trade offers Close and Delete.

- [ ] **Step 2: Write the failing plan-detail tests**

In `$WT/frontend/src/app/workspaces/plans/plan-detail.spec.ts`, add `import { RouteTitleService } from '../../routing/route-title.service';` below the existing imports and append at the end of the file:

```ts
/* -- v195 Phase 4, §5.2, §1.4 -- plan detail on sb-page --------------------- */

describe('PlanDetail on sb-page (v195 Phase 4, §5.2, §1.4)', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    backend = TestBed.inject(HttpTestingController);
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    TestBed.inject(RouteTitleService).set('Plan detail', 'Why this plan, and how it is going');
  });

  function mount(status = 'ACTIVE') {
    const fixture = TestBed.createComponent(PlanDetail);
    fixture.componentRef.setInput('id', PLAN_ID);
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${PLAN_ID}`).flush(planResponse(status));
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('renders the route title as the one h1, from sb-page', () => {
    const { el } = mount();
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Plan detail');
  });

  it('names the plan as the breadcrumb detail segment, with the short id the Trades list shows', () => {
    mount();
    expect(TestBed.inject(RouteTitleService).detail()).toBe('AAPL #444444');
  });

  it('puts the crumb back after a title update clears it while the page is open', () => {
    const { fixture } = mount('PENDING');
    const titles = TestBed.inject(RouteTitleService);
    titles.set('Plan detail', null, '/somewhere-else');
    fixture.detectChanges();
    expect(titles.detail()).toBe('AAPL #444444');
  });

  it('stays read-only: no header actions, no scope bar, no in-page back link', () => {
    const { el } = mount();
    expect(el.querySelector('[page-actions]')).toBeNull();
    expect(el.querySelector('[page-scope]')).toBeNull();
    expect(el.querySelector('a.back')).toBeNull();
    expect(el.querySelector('sb-page button.danger, sb-page button.danger-quiet')).toBeNull();
  });

  it('keeps the plan header as the summary and the plan body as the primary panel', () => {
    const { el } = mount('PENDING');
    const summary = el.querySelector('sb-page [page-kpis]')!;
    expect(summary.querySelector('header.plan-head .plan-title .ticker')!.textContent).toBe('AAPL');
    expect(summary.textContent).toContain('Expires 2026-10-12 at the close (ET) (3 bars left)');
    const primary = el.querySelector('sb-page [page-primary]')!;
    expect(primary.tagName.toLowerCase()).toBe('sb-async');
    expect(primary.querySelector('sb-levels-block')).toBeTruthy();
    expect(primary.querySelector('sb-sizing-panel')).toBeTruthy();
    expect(primary.querySelector('a.record-link')!.getAttribute('href')).toBe(`/trades/${PLAN_ID}`);
  });

  it('sets its order figures on the 14px body step, in both densities', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/plans/plan-detail.ts'), 'utf8');
    expect(src).toMatch(/:host \{[^}]*--text-table: var\(--text-body\);/);
  });
});
```

   `PLAN_ID`, `planResponse`, `FakeEventStream`, `readFileSync`, `join` and `vi` already exist in this file; `planResponse` serves ticker `AAPL`, and a `PENDING` plan carries the `Expires 2026-10-12 … (3 bars left)` line the existing PENDING case asserts.

- [ ] **Step 3: Write the failing trade-drawer test**

In `$WT/frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts`, append at the end of the file (`readFileSync` and `join` are already imported):

```ts
/* -- v195 §1.4 -- the drawer's order figures never shrink ------------------ */

describe('sb-trade-drawer order figures (v195 §1.4)', () => {
  it('sets entry, stop, targets and size on the 14px body step, in both densities', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/trade-drawer.ts'), 'utf8');
    expect(src).toMatch(/:host \{[^}]*display: contents;[^}]*--text-table: var\(--text-body\);/);
    // The fields read --text-table, so re-pointing it on the host is what
    // lifts them; a field on its own fixed size would escape the floor.
    expect(src).toMatch(/dd \{[^}]*font-size: var\(--text-table\)/);
  });
});
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/plans/plan-detail.spec.ts --include src/app/workspaces/dashboard/trade-drawer.spec.ts
```

Expected: FAIL. `trade-detail.spec.ts` does not compile until `tradeCrumb` exists (TS2305); once it does, no `sb-page`, so no `h1`, no slot elements, the two command cases find no `[page-actions]` buttons and `detail()` stays `null`; `a.back` exists on both pages; no source has the `--text-table` override.

- [ ] **Step 5: Move trade detail onto `sb-page`**

In `$WT/frontend/src/app/workspaces/trades/trade-detail.ts`:

1. Imports: add

```ts
import { RouteTitleService } from '../../routing/route-title.service';
import { detailCrumb } from '../../shell/nav';
import { Page } from '../../ui/page';
```

   Change `import { Router, RouterLink } from '@angular/router';` to `import { Router } from '@angular/router';` and, in the component's `imports` array, replace `RouterLink` with `Page` (the back link was the template's only `routerLink`; re-check with `grep -n "routerLink" trade-detail.ts` after step 3 and keep `RouterLink` if v194 added another).

2. Above the doc comment `* One trade — Overview, Why, Chart and Journal within a shared shell.`, add:

```ts
/**
 * The breadcrumb's detail segment for one trade or plan (v195 §3:
 * `Review / Trades / NVDA #a1b2c3`): the ticker and the same six-character
 * id the Trades table's ID column shows (`trades.ts` `shortId`), so the
 * crumb names what the list named. `plan-detail.ts` uses it too.
 */
export function tradeCrumb(ticker: string | null, id: string | null): string {
  if (id === null) return detailCrumb(ticker, null);
  return detailCrumb(ticker, id.length > 6 ? id.slice(-6) : id);
}

```

3. Template: replace everything from `<header class="head">` through the closing `</sb-async>` with the structure below, and close `</sb-page>` after the `sb-confirm-dialog`, so the dialog sits in the default slot. Each `<!-- MOVE: … -->` line is an instruction to this step, not template text: cut the named block (with its own comments) and paste it verbatim there; none of the `MOVE` lines stays in the file.

```html
    <!-- v195 Phase 4: the route title is the page's one h1; the
         breadcrumb's detail segment names the trade (tradeCrumb), and its
         Trades crumb is the way back, so there is no back link and no scope
         bar (spec §5.2). -->
    <sb-page>
      <!-- The trade's commands, at the header's right: Delete last, as
           danger-quiet, each behind the confirm below (Global Constraints:
           any delete lives here). None until the trade has loaded. -->
      <div page-actions class="page-actions">
        @if (store.trade(); as trade) {
          @for (kind of actionsFor(trade.status); track kind) {
            <button
              sb-button
              [variant]="kind === 'delete' ? 'danger-quiet' : 'secondary'"
              type="button"
              (click)="ask(kind)"
            >
              {{ actionLabels[kind] }}
            </button>
          }
        }
      </div>

      <!-- The summary: who the trade is, then how it stands. One element,
           so the identity line and the outcome strip stay adjacent. -->
      <div page-kpis class="summary">
        <header class="head">
          <!-- MOVE: the @if (arrival(); as message) { <p class="arrival" role="status"> } block -->
          <!-- MOVE: the @if (store.trade(); as trade) { <div class="identity"> … } @else if (store.error(); as message) { … } @else { … }
               chain, unchanged except that the <div class="actions"> … </div> block at the end of .identity is deleted
               (its buttons are the page-actions above) -->
        </header>

        @if (store.trade()) {
          <sb-outcome-strip [tiles]="stripTiles()" />
        }
      </div>

      <!-- v195 §5.2: the tabs and their body are the primary panel. -->
      <div page-primary class="tab-body">
        <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="goToTab($event)" />

        <!-- MOVE: the comment that starts "Not in the plan's own file list for this wave" and the whole
             <sb-async …> … </sb-async> around the @switch (activeTab()) body, unchanged -->
      </div>

      <!-- MOVE: the <sb-confirm-dialog [open]="pending() !== null" … /> block, unchanged -->
    </sb-page>
```

   The `<a class="back" routerLink="/trades">← Trades</a>` line is deleted, not moved.

4. Styles:

   - Replace `:host { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: var(--section-gap); }` with

```css
    /* v195 Phase 4: sb-page owns the page rhythm. §1.4: entry, stop,
       targets, size and risk are order figures and never shrink below the
       14px body step, in either density; the plan, position and outcome
       cards read --text-table, so this page re-points it on its own host. */
    :host { display: block; min-width: 0; --text-table: var(--text-body); }
    .summary, .tab-body { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }
```

   - Delete the `.back { … }` and `.back:hover { … }` rules.
   - Replace the `.actions { display: flex; flex-wrap: wrap; gap: var(--space-8); margin-left: auto; }` rule with

```css
    .page-actions {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: var(--space-8);
    }
```

5. In the class: add `private readonly titles = inject(RouteTitleService);` after `protected readonly chart = inject(ChartStore);`, and at the end of the constructor, after the `this.chart.setTarget(...)` effect, add:

```ts

    // v195: the breadcrumb's detail segment (Review / Trades / NVDA #a1b2c3),
    // once the trade has loaded. From an effect, never the constructor body:
    // the router writes the title after it activates the route. Reading
    // detail() as well puts the crumb back if a title update cleared it.
    effect(() => {
      const trade = this.store.trade();
      const crumb = trade ? tradeCrumb(trade.ticker, trade.id) : '';
      this.titles.detail();
      untracked(() => this.titles.setDetail(crumb));
    });
```

6. In the class doc comment (`One trade — Overview, Why, Chart and Journal within a shared shell.`), append:

```ts
 *
 * On sb-page since v195: the commands sit in the header's actions, the
 * identity line and outcome strip are the summary, the tabs the primary
 * panel; every figure reads the 14px body step (spec §1.4).
```

- [ ] **Step 6: Move plan detail onto `sb-page`**

In `$WT/frontend/src/app/workspaces/plans/plan-detail.ts`:

1. Imports: add

```ts
import { RouteTitleService } from '../../routing/route-title.service';
import { Page } from '../../ui/page';
import { tradeCrumb } from '../trades/trade-detail';
```

   and add `Page` to the component's `imports` array (first entry). `RouterLink` stays: the `Open the full trade record` link uses it.

2. Template: wrap it as below. `<!-- MOVE: … -->` lines are instructions, not template text.

```html
    <!-- v195 Phase 4: the route title is the page's one h1; the
         breadcrumb's detail segment names the plan (tradeCrumb), and its
         Trades crumb is the way back. Read-only on purpose, so the header
         carries no actions; no scope bar (spec §5.2). -->
    <sb-page>
      <div page-kpis class="summary">
        <header class="plan-head">
          <!-- MOVE: the @if (store.trade(); as trade) { <div class="plan-title" …> … timing lines }
               @else if (store.error(); as message) { … } @else { … } chain, unchanged -->
        </header>
      </div>

      <!-- MOVE: the whole <sb-async …> … </sb-async> block, unchanged, with the attribute page-primary
           added to its opening tag: <sb-async page-primary [loading]="async().loading" … > -->
    </sb-page>
```

   The `<a class="back sb-hit" routerLink="/trades">← Trades</a>` line is deleted, not moved.

3. Styles:

   - Replace `:host { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: var(--section-gap); }` with

```css
    /* v195 Phase 4: sb-page owns the page rhythm. §1.4: the levels, the
       sizing panel and the short-order notes are order figures and never
       shrink below the 14px body step, in either density; they read
       --text-table, so this page re-points it on its own host. */
    :host { display: block; min-width: 0; --text-table: var(--text-body); }
```

   - Replace the selector list `.back, .record-link {` with `.record-link {` and `.back:hover, .record-link:hover {` with `.record-link:hover {` (the rule bodies stay).

4. In the class: add `private readonly titles = inject(RouteTitleService);` after `protected readonly store = inject(TradeDetailStore);`, and at the end of the constructor, after the redirect effect, add:

```ts

    // v195: the breadcrumb's detail segment (Review / Trades / NVDA #a1b2c3),
    // once the plan has loaded; read detail() so a title update that clears
    // it while the page is open puts it back. A redirect navigates away, and
    // that title update clears it for good.
    effect(() => {
      const trade = this.store.trade();
      const crumb = trade ? tradeCrumb(trade.ticker, trade.id) : '';
      this.titles.detail();
      untracked(() => this.titles.setDetail(crumb));
    });
```

5. In the class doc comment (`One open plan, end to end (spec v151): …`), append:

```ts
 *
 * On sb-page since v195: the plan header is the summary, the plan body the
 * primary panel, and every figure reads the 14px body step (spec §1.4).
```

- [ ] **Step 7: Lift the drawer's figures**

In `$WT/frontend/src/app/workspaces/dashboard/trade-drawer.ts`, replace `:host { display: contents; }` with:

```css
    /* v195 §1.4: entry, stop, targets and size are order figures and never
       shrink below the 14px body step, in either density. Every field reads
       --text-table; display: contents still passes custom properties down. */
    :host { display: contents; --text-table: var(--text-body); }
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/plans/plan-detail.spec.ts --include src/app/workspaces/dashboard/trade-drawer.spec.ts --include src/app/ui/button.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/title-usage.spec.ts --include src/app/ui/async-coverage.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. The existing identity cases (`header.head > .identity > .trade-title`, `.identity > .tags`) and the outcome-strip cases (`header.head + sb-outcome-strip`) still pass, because the summary keeps both elements adjacent. The plan page's baseline case still finds `.plan-title` and `.tags` with `align-items: baseline`. `async-coverage.spec.ts` still finds no banned skeleton class: the `loading-title` lines moved unchanged. If the crumb case reads `null`, the effect is not reading `this.titles.detail()`; a loop (`NG0103`) means `setDetail` is outside `untracked`. If `plan-detail.ts` fails to compile on a circular import, `trade-detail.ts` imports something from `plans/`: it must not.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 9: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`, click to Trades and open the first row's full trade page. At 1440, 768 and 390: one `h1` `Trade detail`; the breadcrumb reads `Review / Trades / <ticker> #<the six characters in that row's ID cell>` at 768 and 1440 (only the last crumb at 390); the commands sit at the header's right, Delete bordered red text on no fill; open Delete, read the confirm, press **Cancel** (never confirm). Identity, then the outcome strip, then the tabs. On Overview, `getComputedStyle(document.querySelector('sb-trade-plan-card table')).fontSize` is `14px` at 1440 dense, 1440 comfortable, 768 and 390. Click the `Trades` crumb and land back on the list. Then open a live plan's page (`/plans/<a PENDING or ACTIVE row's plan id>`, if one exists; else note "no open plan to check"): `h1` `Plan detail`, crumb `<ticker> #<last six>`, no header buttons, and `getComputedStyle(document.querySelector('sb-levels-block dd')).fontSize` is `14px` at the same four settings. Finally on the Dashboard at 390, tap an open position's ticker to open the trade drawer and read `getComputedStyle(document.querySelector('sb-trade-drawer dd')).fontSize` = `14px`. No horizontal page scroll anywhere. Save the PNGs under the session scratchpad.

- [ ] **Step 10: Close**

Close: standard (test: `frontend/src/app/workspaces/trades/trade-detail.spec.ts`), plus `frontend/src/app/workspaces/plans/plan-detail.spec.ts` and `frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts frontend/src/app/workspaces/plans/plan-detail.ts frontend/src/app/workspaces/plans/plan-detail.spec.ts frontend/src/app/workspaces/dashboard/trade-drawer.ts frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts
git -C "$WT" commit -m "feat(v195): trade and plan detail on sb-page, order figures at 14px (V195-30)" -m "Spec Phase 4, §5.2, §3 and §1.4. Trade detail: the commands move to the header's actions (Delete danger-quiet, same confirm), identity and the outcome strip are the summary, the tabs the primary panel. Plan detail: read-only, header as summary, body as primary. Both set the breadcrumb detail segment to <ticker> #<short id> (tradeCrumb, the id the Trades list shows) and drop the back link; both hosts and the trade drawer re-point --text-table to the 14px body step." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

