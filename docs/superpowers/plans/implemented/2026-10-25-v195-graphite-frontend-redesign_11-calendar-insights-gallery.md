# v195 — Graphite, Part 11: Calendar, calendar day and Cancels; Analytics, Research and Reports

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-32:" -A 400 <this file>`.

**Scope of this part (V195-31..V195-32):** spec Phase 4 and §5.2 for the rest of the Review group (Calendar, the calendar day page, Cancels) and the Insights group (Analytics with its Overview tab, Research, Reports): each workspace mapped onto `sb-page`, the calendar day page given the breadcrumb detail segment (its long date), and the performance strips on Calendar and Analytics Overview brought to the §5.2 rule (ExpR before win rate, `N=` on every performance KPI with the small-N cue, the paper / pre-cost / pre-tax basis in each About hint). V195-33 (Versions, the `/ui` gallery and the `workspace-consistency` gate) is in Part 11b (`2026-10-25-v195-graphite-frontend-redesign_11b-versions-gallery-gate.md`), split for the 1500-line cap. V195-31 closes the Review lane after V195-30 (the index allows it in parallel: no shared file); V195-32 is the Insights lane. The two tasks share no file.

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave (read before editing).** Part 10's list binds these tasks (the `sb-page` contract, `RouteTitleService.detail`/`setDetail`, `detailCrumb`, the `--text-table` floor mechanism, `MINUS` and the signing helpers, `StatTile` with `sample`/`hint`/`secondary`/`about` and `PERFORMANCE_CAVEAT`, V195-8's `danger-quiet`, the `primitives.spec.ts` button and form-control gates, the `title` rule: no new `title`, `[title]` or `[attr.title]` on a native element). On top of that:

- `frontend/src/app/ui/page.ts` (V195-21): `Page` (`sb-page`), inputs `heading` and `description` (null or empty falls back to `RouteTitleService.title()` / `subtitle()`). Markup `header.bar` > `div.heading` (`h1.title`, optional `p.description`) + `div.actions.slot`; `div.scope.slot`; `div.kpis.slot`; `div.primary.slot`; `div.secondary.slot` (one column, two from 1440px); then the default `<ng-content />`. **Each slot's content is ONE element carrying the slot attribute** (one element per secondary panel); conditionals go inside that element; a panel that must disappear on one state is hidden with `[style.display]="… ? null : 'none'"` so the slot node stays stable. Dialogs, drawers and `ng-template`s go in the default slot (a `viewChild` still resolves there). Projected elements carry the workspace's own encapsulation attribute, so the workspace's stylesheet may give a secondary panel `grid-column: 1 / -1`. Specs query by slot attribute (`[page-primary]`), never bare `.primary` / `.secondary` (`sb-page`'s slot divs and `StatTile`'s `.secondary` line collide).
- Detail crumb pattern (V195-28, V195-30): `effect(() => { const crumb = …; this.titles.detail(); untracked(() => this.titles.setDetail(crumb)); });` in the constructor, never the constructor body; a spec proves it with `titles.set(title, null, '/somewhere-else')`, `fixture.detectChanges()`, `detail()` restored. Detail pages drop their in-page `← …` back link: the breadcrumb's page crumb links back.
- Spec patterns (Parts 9–10): read KPI tiles through `fixture.debugElement.queryAll(By.css('[page-kpis] sb-stat-tile'))` and their inputs (`label()`, `value()`, `sample()`, `about()`), not their text; set the `h1` with `TestBed.inject(RouteTitleService).set(title, subtitle)`.
- `frontend/src/app/ui/stat-strip.ts`: `StatStrip` (`sb-stat-strip`, inputs `cols: number | null` (null = auto-fit at 140px), `colsMd` (default 2), `fillLast`); outside a panel it is its own bordered surface (V195-11).
- V195-7 already moved `calendar.spec.ts`, `calendar-day.spec.ts` and `day-trade-card.spec.ts` expectations to the true minus (`'−60.00 €'`, `'−0.60R'`); V195-7b moved `cancels.helpers.ts` `rText` and `reports/attribution-tab.ts` `formatR` to it. Quoted expectations below that carry a negative use `−` (U+2212).
- v194: `analytics/tabs/overview.ts` exports `ANALYTICS_SHARPE_LABEL`, `ANALYTICS_DRAWDOWN_LABEL`, `ANALYTICS_SHARPE_ABOUT`, `ANALYTICS_DRAWDOWN_ABOUT` (both ABOUT texts end in `PERFORMANCE_CAVEAT`); `KpiTile` has `about?: string`; the tile binding passes `[about]="tile.about"`; `kpiTiles()` returns Total R, ExpR, Win rate, Profit factor, then the drawdown and Sharpe objects spread from `tile`/`fixedTile` with `about`. v194 V194-12b touched the Calendar day drawer (leg labels) and v194's title conversions may have replaced `[attr.title]="rTooltip"` / `[title]="rTooltip"` in `calendar-day.ts` with `sb-hint`s or `about`; keep whatever v194 left and make the same structural edit.

v194 and V195-1..V195-30 edited files below. Each step names its edit by symbol or quoted string, never by line number; re-read each file before editing it. Where a quoted string differs because v194 reworded it, keep v194's wording and make the same structural edit.

---

# Phase 5 — Workspaces: Calendar, Cancels and Insights

### Task V195-31: Calendar, calendar day (detail segment = long date) and Cancels on `sb-page`
**Model:** sonnet — three workspaces re-slotted onto an existing template plus one breadcrumb effect; the care is in the month totals keeping the async gate they had inside `sb-async`, the day page keeping one stable node per slot across its loaded, empty and loading states, and the filtered-month return surviving the back link's removal.

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts` (template on `sb-page`; `showTotals`, `monthTrades`, `netAbout`, `winRateAbout`; imports; styles)
- Modify: `frontend/src/app/workspaces/calendar/calendar.spec.ts` (imports; one appended `describe`)
- Modify: `frontend/src/app/workspaces/calendar/day/calendar-day.ts` (template on `sb-page` with `[heading]="title()"` and `[description]="caption"`; the detail-crumb effect; `backMonth` removed; imports; styles)
- Modify: `frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts` (imports; four selectors in existing cases; one replaced case; one appended `describe`)
- Modify: `frontend/src/app/workspaces/cancels/cancels.ts` (template on `sb-page`; imports; styles)
- Modify: `frontend/src/app/workspaces/cancels/cancels.spec.ts` (imports; one appended `describe`)

**Interfaces:**
- Consumes: `Page` (`sb-page`, `ui/page.ts`, V195-21: `heading`, `description`, slots, default slot); `RouteTitleService.detail()`, `setDetail(detail)`, `set(title, subtitle, path)` (V195-15); `StatStrip` (`sb-stat-strip`, `ui/stat-strip.ts`); `StatTile` (`sample`, `about`) and `PERFORMANCE_CAVEAT` (`ui/stat-tile.ts`, v194); `asyncInputs` (`ui/async.ts`: no data → `loading` or `error`; data → `loading: false`, `error: null`, `empty`); the existing `Calendar` members (`store`, `async`, `label`, `metrics`, `calendarDigest`, `calendarProblem`, the eight tile label methods, `showGrid`, the drawer members), `CalendarDayPage` members (`store`, `date`, `title`, `monthName`, `backParams`, `caption`, `rTooltip`, `legsNote`, `emptyTitle`, the breakdown members) and `Cancels` members (`store`, `async`, `filterText`, `reload`).
- Produces (nothing a later task consumes beyond V195-33's `workspace-consistency` gate, which reads `<sb-page` and the `Page` import in `calendar/calendar.ts`, `calendar/day/calendar-day.ts` and `cancels/cancels.ts`, and finds no destructive control in any of them):
  - Calendar markup: `sb-page` > `div.head-status[page-actions]` (the store's error, if any); `sb-control-row[page-scope]` (month stepper, metric toggle, Strategy and Horizon selects); `div.month-kpis[page-kpis]` (while `showTotals()`: the `inlineFrom="md"` digest panel holding `sb-stat-strip.totals` with the eight tiles); `sb-async[page-primary]` (the grid or agenda panel, `sb-panel.calendar-panel`); `sb-panel.weekday-panel[page-secondary]` (`By weekday (all history)`, both columns); the day `sb-drawer` in the default slot. `Calendar.showTotals` (`computed<boolean>`: `!loading && error === null && !empty`), `Calendar.monthTrades` (`computed<number | null>`: `store.totals()?.trade_count ?? null`); the Net this month and Win rate tiles carry `[sample]="monthTrades()"` and an `about` ending in `PERFORMANCE_CAVEAT`.
  - Calendar day markup: `sb-page [heading]="title()" [description]="caption"` > `div.page-actions[page-actions]` (stale line, then `nav.steps`: `a.prev` / `span.prev.off`, `a.month` back to the filtered month, `a.next` / `span.next.off`); `div.summary[page-kpis]` (once the day loads: `sb-stat-strip.tiles` with the seven tiles, `p.r-note`, the legs note); `div.day-body[page-primary]` (`Trades (n)` panel, or the empty state, or the loading line); three `sb-panel[page-secondary]` (`How this day compares`, `Month so far`, `What drove it` spanning both columns), each `display: none` until a day has loaded. No `[page-scope]`, no `a.back`, no `h2.long-date`, no `p.caption`.
  - `RouteTitleService.detail()` reads the long date (`'Wednesday, August 5, 2026'`) while a day page is open, re-asserted after a title update clears it.
  - Cancels markup: `sb-page` > `sb-async[page-primary]` (the summary, then the `Cancelled plans` panel, unchanged). No actions, scope, KPI or secondary slot.

**What changes, and what is already there.** Spec Phase 4 and §5.2 (detail routes use the template with the breadcrumb detail segment and no scope bar; performance KPIs show `N=` and their basis). Today Calendar stacks a heading-less `sb-section-head` (the only error surface the all-history table has), the filter row, one `sb-async` around the month's eight-tile strip and the grid, the all-history weekday table and the day drawer. After this task it renders `sb-page`: the route title is the page's one `h1`; the error notice moves to the header's right; the filter row is the scope bar (filters only); the eight month totals are the KPI strip, still inside their phone digest panel, shown only when the old `sb-async` would have shown them (not while loading, not on a first-load error, not on a measured-zero month, so the empty month still reads "No closed trades this month" with no invented totals); the grid is the primary panel inside the same `sb-async`; the weekday table is the one secondary panel, still outside the month's empty gate. Net this month and Win rate gain the month's closed-trade count as `N=` (with the thin-sample cue below 30) and an About hint carrying v194's basis sentence; the strip leads with money, not win rate, so §5.2's order rule already holds. The calendar's own cells, colours and digest are unchanged.

The day page today opens with a `header.day-head` (`← Calendar · August 2026` back link, the long date as an `h2`, the prev/next steps), the paper caption, the seven tiles in a hand-made grid, two panels side by side, *What drove it* and *Trades (n)*. After this task the long date is the page's one `h1` (the route title `Calendar day` names nothing; ticker detail made the same call with its symbol) and the paper caption is its description line, so both still show on a 404 day. The breadcrumb's detail segment is the long date (`Review / Calendar / Wednesday, August 5, 2026`) and its `Calendar` crumb links back, so the `←` link goes, as on every detail page. But the crumb opens `/calendar` bare, while the back link carried the month and the filters (`?month=2026-08&strategy=EMA20`, v165 D6); that return is kept as a plain month link, `August 2026`, between the prev and next steps in the header's actions (navigation, not a destructive control). The seven tiles become one `sb-stat-strip` in the KPI slot (spec Phase 2: one KPI-strip look). *Trades (n)*, the day's rows, is the primary panel; *How this day compares*, *Month so far* and *What drove it* (full width) are the secondary grid, hidden with `display: none` until a day has loaded so each slot stays one stable node. Below 1440px the secondary grid is one column where the two comparison panels used to sit side by side from 640px; that is the template's rule. Every caption, caveat, note and the R explanation stay word for word.

Cancels today is one `sb-async` around the summary (four panels: whether the bot's cancels were right, by reason, right/wrong/unresolved, splits) and the *Cancelled plans* table. After this task it renders `sb-page` with that `sb-async` as the primary element, unchanged: the summary's cards are the table's filters (a click narrows the rows), so they stay directly above it; lifting them into the KPI slot would mean editing `cancels-summary.ts`, outside this task. The page is read-only and has no header action.

- [ ] **Step 1: Write the failing Calendar tests**

In `$WT/frontend/src/app/workspaces/calendar/calendar.spec.ts`:

1. Add below the existing imports:

```ts
import { By } from '@angular/platform-browser';
import { RouteTitleService } from '../../routing/route-title.service';
import { PERFORMANCE_CAVEAT, StatTile } from '../../ui/stat-tile';
```

2. Append at the end of the file:

```ts
/* -- v195 Phase 4 and §5.2 -- Calendar on sb-page --------------------------- */

describe('Calendar on sb-page (v195 Phase 4, §5.2)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/workspaces/calendar/calendar.ts'), 'utf8');

  /** The KPI tiles by label, read through their inputs, not their text. */
  function kpis(fixture: ComponentFixture<Calendar>): Map<string, StatTile> {
    return new Map(fixture.debugElement.queryAll(By.css('[page-kpis] sb-stat-tile'))
      .map((d) => d.componentInstance as StatTile)
      .map((tile) => [tile.label(), tile] as const));
  }

  it('renders the route title as the one h1, from sb-page', async () => {
    const fixture = seed();
    TestBed.inject(RouteTitleService).set('Calendar', 'P&L by day');
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el(fixture).querySelectorAll('h1')).toHaveLength(1);
    expect(el(fixture).querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Calendar');
    expect(el(fixture).querySelector('sb-section-head')).toBeNull();
  });

  it('puts the month filters in the scope bar, and nothing destructive', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();
    const scope = el(fixture).querySelector('sb-page [page-scope]')!;
    expect(scope.tagName.toLowerCase()).toBe('sb-control-row');
    expect(scope.querySelector('.months')).not.toBeNull();
    expect(scope.querySelector('.metric')).not.toBeNull();
    expect(scope.querySelectorAll('sb-select')).toHaveLength(2);
    expect(scope.querySelector('.danger, .danger-quiet')).toBeNull();
  });

  it('puts the month totals in the KPI strip and the grid in the primary slot', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();
    const strip = el(fixture).querySelector('sb-page [page-kpis] sb-stat-strip.totals')!;
    expect(strip.querySelectorAll('sb-stat-tile')).toHaveLength(8);
    const primary = el(fixture).querySelector('sb-page [page-primary]')!;
    expect(primary.tagName.toLowerCase()).toBe('sb-async');
    expect(primary.querySelector('sb-panel.calendar-panel')).not.toBeNull();
    expect(primary.querySelector('.totals')).toBeNull();
  });

  it('shows N and the paper basis on the two performance tiles, and on no count', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();
    const tiles = kpis(fixture);
    // RESPONSE.totals.trade_count is 3: below MIN_SAMPLE_N, so the thin cue shows.
    for (const label of ['Net this month', 'Win rate']) {
      expect(tiles.get(label)!.sample(), label).toBe(3);
      expect(tiles.get(label)!.about(), label).toContain(PERFORMANCE_CAVEAT);
    }
    expect(tiles.get('Trades')!.about()).toBeUndefined();
    expect(el(fixture).querySelector('[page-kpis] .totals sb-stat-tile .thin')).not.toBeNull();
  });

  it('keeps the KPI slot but no totals while the month loads, then fills it', async () => {
    const { fixture, backend } = seedUnflushed();
    fixture.detectChanges();
    expect(el(fixture).querySelector('sb-page [page-kpis]')).not.toBeNull();
    expect(el(fixture).querySelector('.totals')).toBeNull();
    backend.expectOne((r) => r.url === '/api/v1/calendar/pnl').flush(RESPONSE);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el(fixture).querySelector('[page-kpis] .totals')).not.toBeNull();
  });

  it('keeps the all-history weekday table as the one secondary panel, the drawer in the default slot', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();
    const secondary = el(fixture).querySelectorAll('sb-page [page-secondary]');
    expect(secondary).toHaveLength(1);
    expect(secondary[0].textContent).toContain('By weekday (all history)');
    expect(secondary[0].querySelectorAll('.dow-row')).toHaveLength(RESPONSE.day_of_week.length);
    expect(el(fixture).querySelector('sb-page > sb-drawer')).not.toBeNull();
  });

  it('imports Page and no SectionHead', () => {
    expect(SOURCE).toContain('<sb-page');
    expect(SOURCE).toMatch(/import \{ Page \} from '\.\.\/\.\.\/ui\/page';/);
    expect(SOURCE).not.toContain('<sb-section-head');
    expect(SOURCE).not.toMatch(/import \{ SectionHead \}/);
  });
});
```

   `seed`, `seedUnflushed`, `el`, `RESPONSE`, `readFileSync`, `join`, `ComponentFixture` and `TestBed` already exist in this file. The existing `does not turn a no-trade month into invented summary values` case (`.totals` is `null` on a measured-zero month) and `shows the measured-zero empty state … does not hide the all-history weekday table` stay as they are and must stay green: they are the empty-month half of `showTotals`.

- [ ] **Step 2: Write the failing calendar-day tests**

In `$WT/frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts`:

1. Add below the existing imports:

```ts
import { RouteTitleService } from '../../../routing/route-title.service';
```

2. In `it('shows the paper caption, the long date and the seven tiles, R explained', ...)` replace

```ts
    expect(text(el(fixture), '.caption')).toBe(PAPER_CAPTION);
    expect(text(el(fixture), '.long-date')).toBe('Wednesday, August 5, 2026');
```

   with

```ts
    expect(text(el(fixture), 'sb-page p.description')).toBe(PAPER_CAPTION);
    expect(text(el(fixture), 'sb-page h1.title')).toBe('Wednesday, August 5, 2026');
```

   (the `.tiles sb-stat-tile` lines stay: the strip keeps the `tiles` class).

3. In `it('shows a 404 day as the empty state, with working prev/next and the caption', ...)` replace `expect(text(root, '.caption')).toBe(PAPER_CAPTION);` with `expect(text(root, 'sb-page p.description')).toBe(PAPER_CAPTION);`.

4. Replace the whole case `it('goes back to the same filtered month', ...)` with (the pin moves to the link that now carries the return; it is not deleted):

```ts
  it('links back to the same filtered month from the day stepper, with no ← link', async () => {
    const root = el(await open('2026-08-05'));
    expect(text(root, 'nav.steps a.month')).toBe('August 2026');
    expect(root.querySelector('nav.steps a.month')?.getAttribute('href')).toBe('/calendar?month=2026-08&strategy=EMA20');
    expect(root.querySelector('a.back')).toBeNull();
  });
```

5. In `it('asks for the new day when the date in the URL changes', ...)` replace `expect(text(harness.routeNativeElement!, '.long-date')).toBe('Monday, August 10, 2026');` with `expect(text(harness.routeNativeElement!, 'sb-page h1.title')).toBe('Monday, August 10, 2026');`.

6. Append at the end of the file:

```ts
/* -- v195 Phase 4 and §5.2 -- the day page on sb-page ----------------------- */

describe('CalendarDayPage on sb-page (v195 Phase 4, §5.2)', () => {
  it('renders the long date as the one h1', async () => {
    const root = el(await open('2026-08-05'));
    expect(root.querySelectorAll('h1')).toHaveLength(1);
    expect(root.querySelector('h2.long-date')).toBeNull();
    expect(root.querySelector('p.caption')).toBeNull();
  });

  it('names the day as the breadcrumb detail segment', async () => {
    await open('2026-08-05');
    expect(TestBed.inject(RouteTitleService).detail()).toBe('Wednesday, August 5, 2026');
  });

  it('puts the crumb back after a title update clears it while the page is open', async () => {
    const fixture = await open('2026-08-05');
    const titles = TestBed.inject(RouteTitleService);
    titles.set('Calendar', null, '/somewhere-else');
    expect(titles.detail()).toBeNull();
    fixture.detectChanges();
    expect(titles.detail()).toBe('Wednesday, August 5, 2026');
  });

  it('steps days from the header, with no scope bar', async () => {
    const root = el(await open('2026-08-05'));
    const actions = root.querySelector('sb-page [page-actions]')!;
    expect(actions.querySelector('nav.steps a.prev')).not.toBeNull();
    expect(actions.querySelector('nav.steps a.month')).not.toBeNull();
    expect(root.querySelector('[page-scope]')).toBeNull();
    expect(actions.querySelector('.danger, .danger-quiet')).toBeNull();
  });

  it('rules the seven tiles as one strip in the KPI slot, R explained beneath', async () => {
    const root = el(await open('2026-08-05'));
    const summary = root.querySelector<HTMLElement>('sb-page [page-kpis]')!;
    expect(summary.querySelectorAll('sb-stat-strip.tiles sb-stat-tile')).toHaveLength(7);
    expect(text(summary, '.r-note')).toBe(R_TOOLTIP);
  });

  it('makes the trades the primary panel and the comparisons the secondary grid', async () => {
    const root = el(await open('2026-08-05'));
    const primary = root.querySelector('sb-page [page-primary]')!;
    expect(primary.querySelectorAll('sb-day-trade-card').length).toBeGreaterThan(0);
    const secondary = [...root.querySelectorAll<HTMLElement>('sb-page [page-secondary]')];
    expect(secondary).toHaveLength(3);
    expect(secondary[0].textContent).toContain('How this day compares');
    expect(secondary[1].textContent).toContain('Month so far');
    expect(secondary[2].textContent).toContain('What drove it');
    expect(secondary.every((panel) => panel.style.display !== 'none')).toBe(true);
  });

  it('keeps every slot node on a 404 day, the empty state primary and the comparisons hidden', async () => {
    const root = el(await open('2026-08-04', 404));
    expect(root.querySelector('sb-page [page-kpis]')).not.toBeNull();
    expect(root.querySelector('[page-kpis] .tiles')).toBeNull();
    expect(root.querySelector('sb-page [page-primary] sb-empty-state')).not.toBeNull();
    const secondary = [...root.querySelectorAll<HTMLElement>('sb-page [page-secondary]')];
    expect(secondary).toHaveLength(3);
    expect(secondary.every((panel) => panel.style.display === 'none')).toBe(true);
  });
});
```

   `open`, `el`, `text`, `R_TOOLTIP`, `PAPER_CAPTION` and `TestBed` already exist in this file; `open` resets the TestBed, so `RouteTitleService` (root) is fresh in each case.

- [ ] **Step 3: Write the failing Cancels tests**

In `$WT/frontend/src/app/workspaces/cancels/cancels.spec.ts`, add `import { RouteTitleService } from '../../routing/route-title.service';` below the existing imports and append at the end of the file:

```ts
/* -- v195 Phase 4 -- Cancels on sb-page ------------------------------------- */

describe('Cancels on sb-page (v195 Phase 4)', () => {
  it('renders the route title as the one h1, from sb-page', () => {
    const f = create();
    TestBed.inject(RouteTitleService).set('Cancels', "Were the bot's own cancels right?");
    f.detectChanges();
    expect(host(f).querySelectorAll('h1')).toHaveLength(1);
    expect(text(host(f).querySelector('sb-page h1.title'))).toBe('Cancels');
  });

  it('keeps the summary directly above the table, in one primary element', () => {
    const f = create();
    const primary = host(f).querySelector('sb-page [page-primary]')!;
    expect(primary.tagName.toLowerCase()).toBe('sb-async');
    const summary = primary.querySelector('sb-cancels-summary')!;
    const table = primary.querySelector('sb-cancels-table')!;
    expect(summary.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('is read-only: no header action, no scope bar, no KPI or secondary slot', () => {
    const f = create();
    for (const slot of ['[page-actions]', '[page-scope]', '[page-kpis]', '[page-secondary]']) {
      expect(host(f).querySelector(slot), slot).toBeNull();
    }
    expect(host(f).querySelector('sb-page .danger, sb-page .danger-quiet')).toBeNull();
  });
});
```

   `create`, `host` and `text` already exist in this file.

- [ ] **Step 4: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/calendar/calendar.spec.ts --include src/app/workspaces/calendar/day/calendar-day.spec.ts --include src/app/workspaces/cancels/cancels.spec.ts
```

Expected: FAIL. No `sb-page`, so no `h1`, no slot elements, no `p.description`; the totals are inside `sb-async`; the two performance tiles have no `sample`/`about`; the day page still renders `a.back` and `h2.long-date`, has no `a.month`, and `detail()` stays `null`.

- [ ] **Step 5: Move Calendar onto `sb-page`**

In `$WT/frontend/src/app/workspaces/calendar/calendar.ts`:

1. Imports: delete `import { SectionHead } from '../../ui/section-head';`; add `import { Page } from '../../ui/page';`; add `PERFORMANCE_CAVEAT` to the stat-tile import (`import { MIN_SAMPLE_N, PERFORMANCE_CAVEAT, StatTile, StatTone } from '../../ui/stat-tile';`, keeping whatever else v194 left in it). In the component's `imports` array replace `SectionHead` with `Page`.

2. Template: replace the whole template with the structure below. Each `<!-- MOVE: … -->` line is an instruction to this step, not template text: cut the named block (with its own comments) and paste it verbatim there; none of the `MOVE` lines stays in the file.

```html
    <!-- v195 Phase 4: the route title is the page's one h1. -->
    <sb-page>
      <!-- The store's error, at the header's right. Kept unconditional:
           "By weekday (all history)" below stays outside the sb-async wrap --
           it answers a different, all-time question that a THIS MONTH empty
           state must not gate -- and has no error surface of its own, so
           this remains its only one. Duplicates the wrapped panel's own
           error/stale display on a first-load failure; accepted the same way
           Risk does. -->
      <div page-actions class="head-status">
        @if (store.error(); as message) {
          <span class="stale" role="status">{{ message }}</span>
        }
      </div>

      <!-- v195 §5.2: the scope bar holds the month and the filters only. -->
      <sb-control-row page-scope>
        <!-- MOVE: the four children of today's <sb-control-row> (div.months, div.metric, the two sb-select), unchanged -->
      </sb-control-row>

      <!-- v195 §5.2: the month's totals are the KPI strip. Shown exactly when
           the sb-async below shows its content (showTotals): not while the
           first load runs, not on a first-load error, not on a measured-zero
           month, so no invented totals ever sit beside the empty state. -->
      <div page-kpis class="month-kpis">
        @if (showTotals()) {
          <!-- MOVE: the v95 C5 comment and the whole <sb-panel inlineFrom="md" [digest]="calendarDigest()" [problem]="calendarProblem()"> … </sb-panel>
               element with its sb-stat-strip.totals, unchanged except the two tiles edited in item 3 -->
        }
      </div>

      <!-- MOVE: the whole <sb-async …> … </sb-async> element, with page-primary added to its opening tag
           (<sb-async page-primary [loading]="async().loading" …>) and the totals panel above removed from it,
           so it holds the "day-detail pane" comment and the <sb-panel [flush]="true" class="calendar-panel"> … </sb-panel> only -->

      <!-- MOVE: the "All-time, not this-month" comment, then the <sb-panel heading="By weekday (all history)" [divided]="true"> … </sb-panel>
           element, with page-secondary and class="weekday-panel" added to its opening tag:
           <sb-panel page-secondary class="weekday-panel" heading="By weekday (all history)" [divided]="true"> -->

      <!-- MOVE: the whole <sb-drawer …> … </sb-drawer> element, unchanged (the default slot) -->
    </sb-page>
```

   The `<sb-section-head> … </sb-section-head>` element is deleted (its comment is re-worded into the `head-status` comment above).

3. In the moved strip, change the two performance tiles (keep any attribute v194 added):

```html
          <sb-stat-tile label="Net this month" [value]="totalLabel()" [tone]="totalsTone()"
                        [sample]="monthTrades()" [about]="netAbout" />
          <sb-stat-tile label="Trades" [value]="tradesLabel()" />
          <sb-stat-tile label="Win rate" [value]="monthWinRate()" [sample]="monthTrades()" [about]="winRateAbout" />
```

4. In the class, after `protected readonly async = computed(() => … );`, add:

```ts

  /** v195 §5.2: the KPI strip sits outside the sb-async, so it carries the
   *  same gate the sb-async applies to its content: no totals while the
   *  first load runs, on a first-load error or for a measured-zero month. A
   *  refetch failure over loaded data keeps them (asyncInputs: error null). */
  protected readonly showTotals = computed(() => {
    const state = this.async();
    return !state.loading && state.error === null && !state.empty;
  });

  /** The month's closed trades: the N behind Net this month and Win rate. */
  protected readonly monthTrades = computed(() => this.store.totals()?.trade_count ?? null);

  /** v195 §5.2: every performance KPI states its basis (v194's caveat). */
  protected readonly netAbout = `The month's closed trades, summed in the metric on show. ${PERFORMANCE_CAVEAT}`;
  protected readonly winRateAbout = `Share of the month's closed trades that won. ${PERFORMANCE_CAVEAT}`;
```

5. Styles:

   - Replace the `:host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }` rule (and the v54 comment above it, which explains a gap this host no longer sets) with

```css
    /* v195 Phase 4: sb-page owns the page rhythm. */
    :host { display: block; min-width: 0; }
    .head-status { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-8); }
    /* All-time, so it reads across the whole width beside nothing. */
    .weekday-panel { grid-column: 1 / -1; }
```

   - Replace `sb-panel.calendar-panel { display: block; margin-top: 20px; }` with `sb-panel.calendar-panel { display: block; }`, and its comment's last sentence with `sb-page's slot gap now separates it from the strip above.`

   After the edit, `git -C "$WT" grep -n -E "page-(actions|scope|kpis|primary|secondary)" -- frontend/src/app/workspaces/calendar/calendar.ts` prints exactly five template lines (one of each) plus comment mentions.

- [ ] **Step 6: Move the calendar day page onto `sb-page`**

In `$WT/frontend/src/app/workspaces/calendar/day/calendar-day.ts`:

1. Imports: change the core import to `import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';`; add

```ts
import { RouteTitleService } from '../../../routing/route-title.service';
import { Page } from '../../../ui/page';
import { StatStrip } from '../../../ui/stat-strip';
```

   and add `Page` and `StatStrip` to the component's `imports` array (`RouterLink` stays: the steps and the month link use it).

2. Template: replace the whole template with the structure below (`<!-- MOVE: … -->` lines are instructions, not template text).

```html
    <!-- v195 Phase 4, §5.2: the long date is the page's one h1 and the paper
         caption its description, so both show on a day with no trades too.
         The breadcrumb's detail segment is the long date; its Calendar crumb
         links back. No scope bar on a detail route. -->
    <sb-page [heading]="title()" [description]="caption">
      <!-- The header's right: the stale notice, then the day stepper. The
           month link keeps the filtered-month return the old "← Calendar"
           link carried (v165 D6); the breadcrumb crumb opens /calendar bare. -->
      <div page-actions class="page-actions">
        @if (store.error(); as message) {
          <p class="stale" role="status">{{ message }}</p>
        }
        <nav class="steps" aria-label="Trading days">
          <!-- MOVE: the @if (store.prevDay(); as prev) { <a class="prev" …> } @else { <span class="prev off">…</span> } block, unchanged -->
          <a class="month" [routerLink]="['/calendar']" [queryParams]="backParams()">{{ monthName() ?? 'Calendar' }}</a>
          <!-- MOVE: the @if (store.nextDay(); as next) { <a class="next" …> } @else { <span class="next off">…</span> } block, unchanged -->
        </nav>
      </div>

      <!-- Spec Phase 2: the seven tiles are one KPI strip. -->
      <div page-kpis class="summary">
        @if (store.day(); as day) {
          <sb-stat-strip class="tiles">
            <!-- MOVE: the seven <sb-stat-tile> elements from <div class="tiles">, unchanged -->
          </sb-stat-strip>
          <!-- MOVE: the <p class="r-note"> line and the @if (store.hasLegs()) { <p class="sample-note"> } block, unchanged -->
        }
      </div>

      <!-- v195 §5.2: the day's trades are the primary panel. -->
      <div page-primary class="day-body">
        @if (store.day(); as day) {
          <!-- MOVE: the whole <sb-panel [heading]="'Trades (' + day.trade_count + ')'" class="trades-panel"> … </sb-panel> element, unchanged -->
        } @else if (store.empty()) {
          <sb-empty-state [title]="emptyTitle()" hint="Step to a neighbouring trading day, or widen the filters." />
        } @else if (store.loading()) {
          <p class="day-loading">Loading...</p>
        }
      </div>

      <!-- The comparisons: one node each, hidden until a day has loaded, so
           every slot stays a stable element across loaded, empty and loading. -->
      <sb-panel page-secondary heading="How this day compares" [style.display]="store.day() ? null : 'none'">
        @if (store.day(); as day) {
          <!-- MOVE: the <dl class="compare"> … </dl> and <p class="caveat"> from today's "How this day compares" panel, unchanged -->
        }
      </sb-panel>
      <sb-panel page-secondary heading="Month so far" class="month-panel" [style.display]="store.day() ? null : 'none'">
        <!-- MOVE: the body of today's "Month so far" panel (the @if (monthLine(); as line) svg, p.mtd, p.rank), unchanged -->
      </sb-panel>
      <sb-panel page-secondary heading="What drove it" class="drove-panel" [divided]="true" [style.display]="store.day() ? null : 'none'">
        <!-- MOVE: the body of today's "What drove it" panel (sb-tab-bar, div.table-wrap, p.win-note), unchanged -->
      </sb-panel>
    </sb-page>
```

   Deleted, not moved: the `<header class="day-head">` element with its `a.back` and `h2.long-date` (the stepper `nav` inside it is rebuilt above), the `<p class="caption">` line (now the description), the `<div class="tiles">` wrapper and the `<div class="panels">` wrapper. The *Month so far* and *What drove it* bodies read `monthLine()`, `store.monthCtx()`, `rankText()` and `breakdownRows()`, never `day`, so they need no `@if`; if v194 added a `day.` reference to either, wrap that body in `@if (store.day(); as day) { … }` like the first panel.

3. Class: delete the `backMonth` computed (its text is now the month link's). Add `private readonly titles = inject(RouteTitleService);` after `private readonly connection = inject(ConnectionStore);`, and a constructor after the `date` input:

```ts

  constructor() {
    // v195: the breadcrumb's detail segment (Review / Calendar / Wednesday,
    // August 5, 2026). From an effect, never the constructor body: the
    // router writes the title after it activates the route. Reading
    // detail() as well puts the crumb back if a title update cleared it.
    effect(() => {
      const crumb = this.title();
      this.titles.detail();
      untracked(() => this.titles.setDetail(crumb));
    });
  }
```

4. Styles:

   - Replace `:host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }` with

```css
    /* v195 Phase 4: sb-page owns the page rhythm. */
    :host { display: block; min-width: 0; }
    .page-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: var(--space-10); }
    .summary, .day-body { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-10); min-width: 0; }
    .drove-panel { grid-column: 1 / -1; }
```

   - Delete the `.day-head { … }`, `.back { … }`, `.back:hover, .back:focus-visible { … }`, `.long-date { … }`, `.tiles { … }` and `.panels { … }` rules and the `@media (max-width: 639px) { .panels { … } }` block.
   - `.back, .steps a, .steps .off { … }` becomes `.steps a, .steps .off { … }`; in `.steps { … }` delete `margin-left: auto;`.
   - `.caption, .sample-note, .caveat, .r-note, .win-note { … }` becomes `.sample-note, .caveat, .r-note, .win-note { … }`.

5. In the file's top comment (`v165 D5 -- one P&L calendar day as a page: …`), add the line ` * v195: on sb-page; the long date is the h1 and the breadcrumb's detail segment.` before the closing ` */`.

- [ ] **Step 7: Move Cancels onto `sb-page`**

In `$WT/frontend/src/app/workspaces/cancels/cancels.ts`:

1. Add `import { Page } from '../../ui/page';` and add `Page` to the component's `imports` array (first entry).

2. Template: wrap the existing `<sb-async …> … </sb-async>` in `<sb-page> … </sb-page>` and add `page-primary` to its opening tag (`<sb-async page-primary [loading]="async().loading" …`). Put this comment directly after `<sb-page>`:

```html
      <!-- v195 Phase 4: the route title is the page's one h1. One primary
           element: the summary's cards filter the table below them, so the
           two stay together. Read-only, so the header carries no action. -->
```

3. Styles: replace `:host { display: grid; gap: var(--space-14); }` with

```css
    /* v195 Phase 4: sb-page owns the page rhythm; the summary and the table
       keep the 14px gap the host used to give them. */
    :host { display: block; min-width: 0; }
    sb-async[page-primary] { display: grid; gap: var(--space-14); }
```

   (the projected `sb-async` carries this component's encapsulation attribute, so the rule applies to it; if `sb-async` renders its content inside an inner wrapper and the gap does not reach the summary and the panel, leave the rule and note it in the task notes: the summary's panels carry their own margins).

- [ ] **Step 8: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/calendar/calendar.spec.ts --include src/app/workspaces/calendar/day/calendar-day.spec.ts --include src/app/workspaces/cancels/cancels.spec.ts --include src/app/workspaces/cancels/cancels-summary.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/title-usage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. The existing Calendar strip cases (`sb-stat-strip.totals`, eight tiles, `--strip-cols` 4, one `<sb-stat-strip` in the source) still pass: the strip moved whole. `leaves the day drawer tiles out of any strip` reads `calendar.ts` only, not the day page. `workspace-consistency.spec.ts`'s auto-fit rule still passes (no new `repeat(<n>` grid). If the loading case finds `.totals`, `showTotals` is reading `store.data()` rather than `async()`. If a day-page crumb case reads `null`, the effect does not read `this.titles.detail()`; `NG0103` means `setDetail` is outside `untracked`. If the 404 case finds a secondary panel visible, a `[style.display]` binding is missing on it.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. Lint flags a leftover `SectionHead` import or the unused `backMonth`.

- [ ] **Step 9: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard` and click to Calendar. At 1440, 768 and 390: one `h1` `Calendar`; the month stepper, metric toggle and selects sit in the scope bar under it; the eight totals form one strip (one digest line below 1024px, as before), Net this month and Win rate show `N=` and their About glyph; the grid (agenda at 390) follows, then *By weekday (all history)*. Step to an empty month: the strip disappears and "No closed trades this month" shows, the weekday table stays. Step back, click a traded day, then *Open full day →*: the `h1` is the long date with the caption beneath it; the breadcrumb reads `Review / Calendar / <long date>` at 768 and 1440; the steps and the month link sit at the header's right; click the month link and land on that month with the same filters. Open `/app/cancels`: one `h1` `Cancels`, the summary then the table. No horizontal page scroll anywhere. Save the PNGs under the session scratchpad.

- [ ] **Step 10: Close**

Close: standard (test: `frontend/src/app/workspaces/calendar/calendar.spec.ts`), plus `frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts` and `frontend/src/app/workspaces/cancels/cancels.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/calendar.spec.ts frontend/src/app/workspaces/calendar/day/calendar-day.ts frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts frontend/src/app/workspaces/cancels/cancels.ts frontend/src/app/workspaces/cancels/cancels.spec.ts
git -C "$WT" commit -m "feat(v195): Calendar, calendar day and Cancels on sb-page (V195-31)" -m "Spec Phase 4 and §5.2. Calendar: filters in the scope bar, the month totals as the KPI strip (gated like the sb-async they left; Net and Win rate gain N= and the paper basis), the grid primary, the all-history weekday table secondary. Calendar day: the long date is the h1 and the breadcrumb detail segment, the caption the description, the seven tiles one strip, the trades primary, the comparisons secondary; the back link goes and a month link in the stepper keeps the filtered-month return. Cancels: one primary element, summary above table." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

### Task V195-32: Analytics (scope bar = `scope-bar.ts` + tabs), Research and Reports on `sb-page`; performance strips ExpR first with N
**Model:** sonnet — three workspace shells re-slotted onto an existing template and one KPI row reordered with basis hints; the care is in the Overview strip leading with ExpR while v194's basis-named Sharpe and drawdown tiles stay exactly as v194 left them, and in Research and Reports keeping their footer and drawer.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (template on `sb-page`; imports; styles)
- Modify: `frontend/src/app/workspaces/analytics/analytics.spec.ts` (imports; one replaced case; one appended `describe`)
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts` (four exported ABOUT constants; `kpiTiles()` order and `about`s; the KPI row as `sb-stat-strip.kpis`; imports; styles)
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts` (imports; one appended `describe`)
- Modify: `frontend/src/app/workspaces/research/research.ts` (template on `sb-page`; imports; styles)
- Modify: `frontend/src/app/workspaces/research/research.spec.ts` (imports; one appended `describe`)
- Modify: `frontend/src/app/workspaces/reports/reports.ts` (template on `sb-page`; imports; styles)
- Modify: `frontend/src/app/workspaces/reports/reports.spec.ts` (imports; one appended `describe`)

**Interfaces:**
- Consumes: `Page` (`sb-page`, `ui/page.ts`, V195-21); `RouteTitleService.set(title, subtitle)` (spec only); `StatStrip` (`ui/stat-strip.ts`); `StatTile` (`label`, `sample`, `about`), `PERFORMANCE_CAVEAT`, `MIN_SAMPLE_N` (`ui/stat-tile.ts`, v194); v194's `ANALYTICS_SHARPE_LABEL`, `ANALYTICS_DRAWDOWN_LABEL`, `ANALYTICS_SHARPE_ABOUT`, `ANALYTICS_DRAWDOWN_ABOUT`, `KpiTile.about` (`analytics/tabs/overview.ts`); the existing `Analytics` members (`store`, `tabs`, `horizons`, `strategyNames`, `goToTab`, `onScope`, `onUnit`), `OverviewTab.kpiTiles` and its local `tile` / `fixedTile` builders, `Research` members (`store`, `async`, `disclaimer`, the column and cell members) and `Reports` members (`store`, `async`, `tabs`, `neverStale`, `runHint`, `disclaimer`, `goToTab`).
- Produces (nothing a later task consumes beyond V195-33's `workspace-consistency` gate, which reads `<sb-page` and the `Page` import in `analytics/analytics.ts`, `research/research.ts` and `reports/reports.ts`):
  - Analytics markup: `sb-page` > `div.scope[page-scope]` (`sb-tab-bar`, then `sb-scope-bar`); `div.tab-body[page-primary]` (the `@switch` of the seven tabs). No actions, KPI or secondary slot.
  - `overview.ts` exports `ANALYTICS_EXPR_ABOUT`, `ANALYTICS_WIN_RATE_ABOUT`, `ANALYTICS_TOTAL_R_ABOUT`, `ANALYTICS_PROFIT_FACTOR_ABOUT` (each a definition sentence plus `' ' + PERFORMANCE_CAVEAT`). `kpiTiles()` order: `ExpR`, `Win rate`, `Total R`, `Profit factor`, `ANALYTICS_DRAWDOWN_LABEL`, `ANALYTICS_SHARPE_LABEL`; every tile has a non-null `sample` source and an `about` ending in `PERFORMANCE_CAVEAT`. The row renders as `sb-stat-strip.kpis` (auto-fit).
  - Research markup: `sb-page` > `div.research-body[page-primary]` (the `sb-async` with the Strategy registry panel then the Pre-registration ledger panel, unchanged; then `p.disclaimer`); the row `sb-drawer` and the three cell `ng-template`s in the default slot.
  - Reports markup: `sb-page` > `sb-freshness[page-actions]`; `sb-tab-bar[page-scope]`; `div.report-body[page-primary]` (the `sb-async` around the open tab, then `p.disclaimer`). No `sb-section-head`.

**What changes, and what is already there.** Spec Phase 4 and §5.2 (performance strips lead with expectancy; every performance KPI shows `N=` with the small-N cue and states its basis). Analytics today is a shell: the tab strip, the one scope bar (`scope-bar.ts`: range, side, horizon, strategy, unit, N), then the open tab; its spec says it renders no heading because the top bar owned the title. After this task the route title is its one `h1`, the tab strip and the scope bar together are the page's scope bar (filters and tabs only), and the open tab is the primary panel; each tab keeps its own panels. The Overview tab's KPI row today reads Total R, ExpR, Win rate, Profit factor, then v194's basis-named drawdown and Sharpe tiles; Total R, ExpR and Win rate carry `N=` but say nothing of their basis. After this task the row opens ExpR, then Win rate, then Total R and Profit factor, then drawdown and Sharpe unchanged; each of the first four gains an About hint with a one-line definition and v194's caveat sentence (`PERFORMANCE_CAVEAT`), so all six state paper, pre-cost, pre-tax (v194 already gave the last two theirs). Every tile already passes its sample to `StatTile`, whose thin cue fires below `MIN_SAMPLE_N`; Profit factor keeps its visible hint line. The row becomes one `sb-stat-strip` (spec Phase 2: one KPI-strip look), still auto-fit.

Research today stacks the registry and the ledger inside one `sb-async`, the fixed footer and the row drawer; its class comment explains that the registry (about a dozen rows) reads as context for the ledger below it. After this task the route title is its `h1`, and the `sb-async` and the footer are one primary element, unchanged in order: splitting the registry into the secondary grid would put it below a paged ledger, against that reason. The drawer and the cell templates sit in the default slot. Reports today is a heading-less `sb-section-head` holding the generated-at `sb-freshness`, the tab strip, the `sb-async` around the open report and the footer. After this task the freshness marker sits at the header's right (a status, not a command), the tab strip is the scope bar, and the `sb-async` with the footer is the primary element. Neither page has a destructive control or a KPI strip of its own; every caption, footer and "Not yet run" text stays word for word.

- [ ] **Step 1: Write the failing Analytics tests**

In `$WT/frontend/src/app/workspaces/analytics/analytics.spec.ts`:

1. Add below the existing imports:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { RouteTitleService } from '../../routing/route-title.service';
```

2. Replace the whole case `it('renders no in-page heading — the tab strip is the heading', ...)` with:

```ts
  it('renders the route title as the one h1, from sb-page', () => {
    const { fixture } = create();
    TestBed.inject(RouteTitleService).set('Analytics', 'What already happened, measured');
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Analytics');
  });
```

3. Append at the end of the file:

```ts
/* -- v195 Phase 4 -- Analytics on sb-page ----------------------------------- */

describe('Analytics on sb-page (v195 Phase 4)', () => {
  it('puts the tab strip and the one scope bar in the scope slot, in that order', () => {
    const { fixture } = create();
    fixture.detectChanges();
    const scope = (fixture.nativeElement as HTMLElement).querySelector('sb-page [page-scope]')!;
    expect([...scope.children].map((c) => c.tagName.toLowerCase())).toEqual(['sb-tab-bar', 'sb-scope-bar']);
    expect(scope.querySelector('.danger, .danger-quiet')).toBeNull();
  });

  it('mounts the open tab in the primary slot, and has no header action or KPI slot', () => {
    const { fixture } = create();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-page [page-primary] sb-overview-tab')).not.toBeNull();
    expect(el.querySelector('[page-actions]')).toBeNull();
    expect(el.querySelector('[page-kpis]')).toBeNull();
  });

  it('imports Page', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/analytics.ts'), 'utf8');
    expect(src).toContain('<sb-page');
    expect(src).toMatch(/import \{ Page \} from '\.\.\/\.\.\/ui\/page';/);
  });
});
```

   `create` and `TestBed` already exist in this file.

- [ ] **Step 2: Write the failing Overview tests**

In `$WT/frontend/src/app/workspaces/analytics/tabs/overview.spec.ts`:

1. Add below the existing imports:

```ts
import { By } from '@angular/platform-browser';
import { PERFORMANCE_CAVEAT, StatTile } from '../../../ui/stat-tile';
```

   and extend the `./overview` import v194 left (`import { ANALYTICS_DRAWDOWN_LABEL, ANALYTICS_SHARPE_LABEL, OverviewTab } from './overview';`) to `import { ANALYTICS_DRAWDOWN_LABEL, ANALYTICS_EXPR_ABOUT, ANALYTICS_SHARPE_LABEL, OverviewTab } from './overview';`.

2. Append at the end of the file:

```ts
/* -- v195 §5.2 -- the performance strip leads with expectancy --------------- */

describe('OverviewTab performance strip (v195 §5.2)', () => {
  beforeEach(() => TestBed.resetTestingModule());

  const tiles = (fixture: ReturnType<typeof render>['fixture']): StatTile[] =>
    fixture.debugElement.queryAll(By.css('sb-stat-tile')).map((d) => d.componentInstance as StatTile);

  it('leads with ExpR, win rate after it, never in the lead slot', () => {
    const { fixture } = render();
    expect(tiles(fixture).map((tile) => tile.label())).toEqual([
      'ExpR', 'Win rate', 'Total R', 'Profit factor', ANALYTICS_DRAWDOWN_LABEL, ANALYTICS_SHARPE_LABEL,
    ]);
  });

  it('shows N on every tile and states the paper, pre-cost, pre-tax basis in each About hint', () => {
    const { fixture } = render();
    for (const tile of tiles(fixture)) {
      expect(tile.sample(), tile.label()).not.toBeNull();
      expect(tile.about(), tile.label()).toContain(PERFORMANCE_CAVEAT);
      expect(tile.about()!.split(PERFORMANCE_CAVEAT), tile.label()).toHaveLength(2);
    }
    expect(tiles(fixture)[0].about()).toBe(ANALYTICS_EXPR_ABOUT);
  });

  it('marks a thin ExpR sample with the small-N cue', () => {
    const { el } = render();
    // The stub's expectancy_n is 34 (adequate); the equity points_n is 2 (thin).
    const total = Array.from(el.querySelectorAll('sb-stat-tile'))
      .find((tile) => tile.querySelector('.label')?.textContent?.trim() === 'Total R')!;
    expect(total.querySelector('.thin')).not.toBeNull();
    const expr = el.querySelector('sb-stat-tile')!;
    expect(expr.querySelector('.thin')).toBeNull();
  });

  it('rules the tiles as one auto-fit stat strip and declares no grid of its own', () => {
    const { el } = render();
    const strip = el.querySelector('sb-stat-strip.kpis')!;
    expect(strip.querySelectorAll('sb-stat-tile')).toHaveLength(6);
    expect(strip.querySelector('.sb-strip-grid')!.classList).not.toContain('sb-strip-fixed');
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/tabs/overview.ts'), 'utf8');
    expect(src).not.toMatch(/\.kpis\s*\{/);
  });
});
```

   `render`, `readFileSync`, `join`, `beforeEach` and `TestBed` already exist in this file. If v194's `ANALYTICS_*_LABEL` text puts the label's words in a different `.label` shape, read the Total R tile through `tiles(fixture)` and `fixture.debugElement` instead; the thin cue is the `.thin` class `StatTile` puts on its `.tile` below `MIN_SAMPLE_N`.

- [ ] **Step 3: Write the failing Research and Reports tests**

1. In `$WT/frontend/src/app/workspaces/research/research.spec.ts`, add `import { RouteTitleService } from '../../routing/route-title.service';` below the existing imports and append at the end of the file:

```ts
/* -- v195 Phase 4 -- Research on sb-page ------------------------------------ */

describe('Research on sb-page (v195 Phase 4)', () => {
  it('renders the route title as the one h1, from sb-page', () => {
    const { fixture } = create();
    TestBed.inject(RouteTitleService).set('Research', 'Every pre-registration and its verdict');
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('h1')).toHaveLength(1);
    expect(el.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Research');
  });

  it('keeps the registry above the ledger and the footer last, in one primary element', () => {
    const { fixture } = create();
    const primary = (fixture.nativeElement as HTMLElement).querySelector('sb-page [page-primary]')!;
    const text = primary.textContent ?? '';
    expect(text.indexOf('Strategy registry')).toBeLessThan(text.indexOf('Pre-registration ledger'));
    expect(primary.lastElementChild!.classList).toContain('disclaimer');
    expect(primary.querySelectorAll('sb-data-table')).toHaveLength(2);
  });

  it('keeps the row drawer in the default slot, with no header action or scope bar', () => {
    const { fixture } = create();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-page > sb-drawer')).not.toBeNull();
    expect(el.querySelector('[page-actions]')).toBeNull();
    expect(el.querySelector('[page-scope]')).toBeNull();
  });
});
```

   `create` and `TestBed` already exist in this file (import `TestBed` from `@angular/core/testing` is already there).

2. In `$WT/frontend/src/app/workspaces/reports/reports.spec.ts`, add `import { readFileSync } from 'node:fs';`, `import { join } from 'node:path';` and `import { RouteTitleService } from '../../routing/route-title.service';` below the existing imports and append at the end of the file:

```ts
/* -- v195 Phase 4 -- Reports on sb-page ------------------------------------- */

describe('Reports on sb-page (v195 Phase 4)', () => {
  function loaded() {
    const created = create();
    created.store.resolveTab('attribution').subscribe();
    created.http.expectOne(URLS.attribution).flush(ok(ATTRIBUTION));
    TestBed.inject(RouteTitleService).set('Reports', 'What the measurements say about entries and gates');
    created.fixture.detectChanges();
    return created;
  }

  it('renders the route title as the one h1, from sb-page', () => {
    const { fixture } = loaded();
    expect(host(fixture).querySelectorAll('h1')).toHaveLength(1);
    expect(host(fixture).querySelector('sb-page h1.title')!.textContent!.trim()).toBe('Reports');
    expect(host(fixture).querySelector('sb-section-head')).toBeNull();
  });

  it('puts the generated-at marker at the header right and the tabs in the scope bar', () => {
    const { fixture } = loaded();
    const actions = host(fixture).querySelector('sb-page [page-actions]')!;
    expect(actions.tagName.toLowerCase()).toBe('sb-freshness');
    expect(host(fixture).querySelector('sb-page [page-scope]')!.tagName.toLowerCase()).toBe('sb-tab-bar');
    expect(host(fixture).querySelector('sb-page .danger, sb-page .danger-quiet')).toBeNull();
  });

  it('keeps the report and the footer in one primary element', () => {
    const { fixture } = loaded();
    const primary = host(fixture).querySelector('sb-page [page-primary]')!;
    expect(primary.querySelector('sb-expectancy-attribution-tab')).not.toBeNull();
    expect(primary.lastElementChild!.classList).toContain('disclaimer');
  });

  it('imports Page and no SectionHead', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/reports/reports.ts'), 'utf8');
    expect(src).toMatch(/import \{ Page \} from '\.\.\/\.\.\/ui\/page';/);
    expect(src).not.toMatch(/import \{ SectionHead \}/);
  });
});
```

   `create`, `host`, `URLS`, `ok`, `ATTRIBUTION` and `TestBed` already exist in this file.

- [ ] **Step 4: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/analytics/analytics.spec.ts --include src/app/workspaces/analytics/tabs/overview.spec.ts --include src/app/workspaces/research/research.spec.ts --include src/app/workspaces/reports/reports.spec.ts
```

Expected: FAIL. `overview.spec.ts` does not compile until `ANALYTICS_EXPR_ABOUT` exists (TS2305); once it does, the strip starts with Total R, three tiles have no `about`, and the row is a `div.kpis`. No page renders `sb-page`, so no `h1` and no slot elements; Reports still has `sb-section-head`.

- [ ] **Step 5: Move Analytics onto `sb-page`**

In `$WT/frontend/src/app/workspaces/analytics/analytics.ts`:

1. Add `import { Page } from '../../ui/page';` and add `Page` to the component's `imports` array (first entry).

2. Template: replace it with the structure below (`<!-- MOVE: … -->` lines are instructions, not template text).

```html
    <!-- v195 Phase 4: the route title is the page's one h1. The tab strip
         and the one scope bar are the page's scope (filters and tabs only);
         the open tab is the primary panel and owns its own panels. -->
    <sb-page>
      <div page-scope class="scope">
        <!-- MOVE: the <sb-tab-bar …/> element and the <sb-scope-bar …/> element, unchanged, in that order -->
      </div>
      <div page-primary class="tab-body">
        <!-- MOVE: the @switch (store.tab()) { … } block, unchanged -->
      </div>
    </sb-page>
```

3. Styles: replace `:host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); }` with

```css
    :host { display: block; min-width: 0; }
    .scope, .tab-body { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); min-width: 0; }
```

   (as a template-literal string: `styles: \`…\``, keeping the `register-instrument` host class).

4. In the class doc comment, replace `This file is a shell: the tab strip, the bar, and a switch.` with `This file is a shell: the tab strip and the bar (the page's scope bar since v195), and a switch.`

- [ ] **Step 6: Lead the Overview strip with ExpR**

In `$WT/frontend/src/app/workspaces/analytics/tabs/overview.ts`:

1. Imports: add `import { StatStrip } from '../../../ui/stat-strip';` and add `StatStrip` to the component's `imports` array after `StatTile`. `PERFORMANCE_CAVEAT` is already imported from `ui/stat-tile` (V194-11b).

2. Below v194's `ANALYTICS_DRAWDOWN_ABOUT` constant, add:

```ts

/** v195 §5.2: every performance KPI states its basis in its About hint
 *  (v194's caveat sentence), beside a one-line definition. The drawdown and
 *  Sharpe tiles already carry theirs (V194-11b). */
export const ANALYTICS_EXPR_ABOUT =
  'Mean R per closed trade in the selected range; N is the closed trades it averages. ' + PERFORMANCE_CAVEAT;
export const ANALYTICS_WIN_RATE_ABOUT =
  'Share of closed trades in the selected range that touched TP1; N is the closed trades it counts. '
  + PERFORMANCE_CAVEAT;
export const ANALYTICS_TOTAL_R_ABOUT =
  'Cumulative R over every closed trade in the selected range, in close order; N is the trades on the curve. '
  + PERFORMANCE_CAVEAT;
export const ANALYTICS_PROFIT_FACTOR_ABOUT =
  'Gross realised win ÷ gross realised loss over the selected range; N is the scoped closed trades. '
  + PERFORMANCE_CAVEAT;
```

   If v194's content audit (V194-16) already gave one of these four tiles an `about`, keep v194's definition sentence in place of the one above and append `' ' + PERFORMANCE_CAVEAT` only if it lacks it (the spec asserts the caveat appears exactly once).

3. Template: replace `<div class="kpis">@for (tile of kpiTiles(); track tile.label) {` … `}</div>` with the same `@for` inside `<sb-stat-strip class="kpis">` … `</sb-stat-strip>`; the `sb-stat-tile` binding v194 left (`[label] [value] [secondary] [sample] [trend] [hint] [about]`) is unchanged.

4. In `kpiTiles()`, replace the first four entries of the returned array (`tile('Total R', …)`, `tile('ExpR', …)`, `fixedTile('Win rate', …)`, `fixedTile('Profit factor', …)`) with the four below, placed before v194's drawdown and Sharpe objects, which stay exactly as they are:

```ts
      // v195 §5.2: a performance strip leads with expectancy, win rate after
      // it, never in the lead slot. Each carries its N and its basis.
      { ...tile('ExpR', performance?.expectancy_r ?? null, null, expectancyMoney, expectancyN),
        about: ANALYTICS_EXPR_ABOUT },
      { ...fixedTile('Win rate', share(winRate, 2), performance?.win_rate_n ?? null, this.winRateTrend()),
        about: ANALYTICS_WIN_RATE_ABOUT },
      { ...tile('Total R', last?.cum_r ?? null, derived?.total_return_pct ?? null, last?.cum_pnl ?? null,
        equityCurve?.points_n ?? null, this.totalRTrend()), about: ANALYTICS_TOTAL_R_ABOUT },
      { ...fixedTile('Profit factor', num(profitFactor, 2), this.store.scopeN(), null,
        'Gross realised win ÷ gross realised loss.'), about: ANALYTICS_PROFIT_FACTOR_ABOUT },
```

   (if v194 reworded an argument of one of these four calls, keep v194's argument; only the order and the `about` change).

5. Styles: delete the `.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: var(--space-10); }` rule; the strip owns its columns (auto-fit at 140px with no `cols`).

- [ ] **Step 7: Move Research and Reports onto `sb-page`**

1. `$WT/frontend/src/app/workspaces/research/research.ts`:

   - Add `import { Page } from '../../ui/page';` and `Page` to the component's `imports` array (first entry).
   - Template: wrap it as below (`<!-- MOVE: … -->` lines are instructions).

```html
    <!-- v195 Phase 4: the route title is the page's one h1. One primary
         element: the registry stays above the ledger it gives context to
         (see the class comment), and the footer closes it. -->
    <sb-page>
      <div page-primary class="research-body">
        <!-- MOVE: the whole <sb-async …> … </sb-async> element, unchanged -->
        <!-- MOVE: the <p class="disclaimer">{{ disclaimer }}</p> line -->
      </div>

      <!-- MOVE: the whole <sb-drawer …> … </sb-drawer> element and the three <ng-template> elements (#tierCell, #verdictCell, #hypothesisCell), unchanged (the default slot) -->
    </sb-page>
```

   - Styles: replace `:host { display: grid; gap: var(--space-14); }` with `:host { display: block; min-width: 0; }` and add `.research-body { display: grid; gap: var(--space-14); min-width: 0; }`.

2. `$WT/frontend/src/app/workspaces/reports/reports.ts`:

   - Imports: delete `import { SectionHead } from '../../ui/section-head';`, add `import { Page } from '../../ui/page';`; in the component's `imports` array replace `SectionHead` with `Page`.
   - Template: replace it with:

```html
    <!-- v195 Phase 4: the route title is the page's one h1. -->
    <sb-page>
      <!-- A report has no cadence, so it is never flagged stale: the
           timestamp itself is the information. A status at the header's
           right, not a command. -->
      <sb-freshness page-actions [at]="store.generatedAt()" [staleAfterSec]="neverStale" />

      <sb-tab-bar page-scope [tabs]="tabs" [active]="store.tab()" (activeChange)="goToTab($event)" />

      <div page-primary class="report-body">
        <!-- MOVE: the whole <sb-async …> … </sb-async> element around the @switch (store.tab()) block, unchanged -->
        <p class="disclaimer">{{ disclaimer }}</p>
      </div>
    </sb-page>
```

   - Styles: replace `:host { display: grid; gap: var(--space-14); }` with `:host { display: block; min-width: 0; }` and add `.report-body { display: grid; gap: var(--space-14); min-width: 0; }`; the `.disclaimer` rule stays.
   - In the class doc comment, replace `A shell: the tab strip, the freshness marker, the not-yet-run state and the fixed footer.` with `A shell on sb-page: the freshness marker in the header, the tab strip as the scope bar, the not-yet-run state and the fixed footer.`

- [ ] **Step 8: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/analytics/analytics.spec.ts --include src/app/workspaces/analytics/tabs/overview.spec.ts --include src/app/workspaces/research/research.spec.ts --include src/app/workspaces/reports/reports.spec.ts --include src/app/workspaces/reports/attribution-tab.spec.ts --include src/app/workspaces/reports/gates-tab.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/title-usage.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. The existing Overview cases (`shows six KPI tiles, all six labelled`, `gives the R-multiple tiles a money line …`, v194's drawdown/Sharpe cases) match by label and still pass in the new order. Research's existing cases still index `tables(fixture)[0]` as the registry and `[1]` as the ledger: the order did not change. `workspace-consistency.spec.ts`'s freshness rule still finds `[staleAsOf]` in `research.ts` and `reports.ts`. If the Overview basis case finds the caveat twice on a tile, v194 already appended it to that tile's definition: drop the extra `' ' + PERFORMANCE_CAVEAT`. If the Analytics scope case finds a third child, a comment-free wrapper crept in: the two components must be the `div.scope`'s only element children.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. Lint flags a leftover `SectionHead` import in `reports.ts`.

- [ ] **Step 9: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard` and click to Analytics. At 1440, 768 and 390: one `h1` `Analytics`; the tab strip and the scope bar sit under it; on Overview the strip reads ExpR, Win rate, Total R, Profit factor, the drawdown tile, the Sharpe tile, each with `N=` and an About glyph whose text ends in the paper / pre-cost / pre-tax sentence (open one with the keyboard, read it, Escape). Switch to Edge and back; the scope bar stays put. Open `/app/research`: one `h1`, the registry, then the ledger, then the footer; tap a ledger row at 390 and the drawer opens. Open `/app/reports`: one `h1`, the generated-at marker at the header's right (it wraps under the title at 390), the two tabs, the report, the footer. No horizontal page scroll anywhere. Save the PNGs under the session scratchpad.

- [ ] **Step 10: Close**

Close: standard (test: `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts`), plus `frontend/src/app/workspaces/analytics/analytics.spec.ts`, `frontend/src/app/workspaces/research/research.spec.ts` and `frontend/src/app/workspaces/reports/reports.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/workspaces/analytics/analytics.ts frontend/src/app/workspaces/analytics/analytics.spec.ts frontend/src/app/workspaces/analytics/tabs/overview.ts frontend/src/app/workspaces/analytics/tabs/overview.spec.ts frontend/src/app/workspaces/research/research.ts frontend/src/app/workspaces/research/research.spec.ts frontend/src/app/workspaces/reports/reports.ts frontend/src/app/workspaces/reports/reports.spec.ts
git -C "$WT" commit -m "feat(v195): Analytics, Research and Reports on sb-page; Overview strip leads with ExpR (V195-32)" -m "Spec Phase 4 and §5.2. Analytics: the tab strip and the scope bar are the page's scope, the open tab the primary panel. Overview: the KPI row is one stat strip reading ExpR, Win rate, Total R, Profit factor, then v194's drawdown and Sharpe; every tile shows N with the thin cue and states the paper, pre-cost, pre-tax basis in its About hint. Research: registry, ledger and footer stay one primary element, the drawer in the default slot. Reports: the generated-at marker in the header, the tabs as the scope bar, report and footer primary." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

