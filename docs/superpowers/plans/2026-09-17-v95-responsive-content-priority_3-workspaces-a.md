# v95 — Part 3: Workspaces A (trades, dashboard, calendar, watchlist)

Part of `2026-09-17-v95-responsive-content-priority`. Header block, goal,
global constraints, parallelisation map and exit criteria live in
`_0-index.md` — read that first.

# Phase C — Workspace adoption, the four worst

**Group C-i (parallel):** C1+C2 (trades), C3+C4 (dashboard), C5+C6 (calendar),
C7 (watchlist). Four workspace directories, no shared file. Within each pair
the tasks are sequential.

**One exception to the disjoint-files rule:** C4 edits
`ui/data-table/data-table.ts` for the duplicate-pager fix. No other Phase C
task touches that file, but C4 must not run concurrently with any Phase D task
that does. Nothing in Phase D does.

**Every task in this phase carries a mandatory visual pass at 390 / 768 /
1024.** The audit behind this spec found defects the suite does not catch; a
green narrow run is necessary and not sufficient here.

---

### Task C1: Trades — the toolbar collapses

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.ts`
- Test: `frontend/src/app/workspaces/trades/trades.spec.ts`

Observed at 390px: roughly 1,700px of controls above the first trade row, and
the top ~450px near-empty because the bar right-aligns one item per row. Eight
filter selects, a date range, `Export CSV`, `Columns 12/29`, a Compact/Full
toggle, eight filter chips and two destructive buttons.

**What stays inline at `xs`:** the status filter chips (the primary way anyone
narrows this table) and `Columns`. Everything else demotes.

**Interfaces:**
- Consumes: `Toolbar`, `ToolbarControl` (B4).
- Produces: `TRADES_CONTROLS: ToolbarControl[]`, exported so E1 can walk it.

- [x] **Step 1: Write the failing test**

```ts
import { TRADES_CONTROLS } from './trades';

describe('Trades toolbar priorities', () => {
  it('declares a floor for every control', () => {
    // A control with no floor is inline everywhere, which is how the 1700px
    // stack happened. Requiring the declaration makes the choice deliberate.
    expect(TRADES_CONTROLS.every((c) => c.inlineFrom !== undefined)).toBe(true);
  });

  it('keeps the status filter and the column picker inline on a phone', () => {
    const inlineAtXs = TRADES_CONTROLS.filter((c) => c.inlineFrom === 'xs').map((c) => c.id);
    expect(inlineAtXs).toEqual(expect.arrayContaining(['status', 'columns']));
  });

  it('demotes the eight field filters and the date range below md', () => {
    const demoted = ['ticker', 'origin', 'strategy', 'horizon', 'confidence', 'tier', 'badge', 'note', 'dates'];
    for (const id of demoted) {
      const control = TRADES_CONTROLS.find((c) => c.id === id);
      expect(control, `missing control ${id}`).toBeDefined();
      expect(isInline(control!.inlineFrom, 'sm')).toBe(false);
      expect(isInline(control!.inlineFrom, 'md')).toBe(true);
    }
  });

  it('reports a filter as active when it is not at its default', () => {
    // Guard 1: a hidden filter that is narrowing the table must be counted.
    const component = TestBed.createComponent(Trades).componentInstance;
    component.tickerFilter.set('AAPL');
    expect(component.toolbarControls().find((c) => c.id === 'ticker')!.active).toBe(true);
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/trades/trades.spec.ts`
Expected: FAIL — `TRADES_CONTROLS` is not exported.

- [x] **Step 3: Write the implementation**

Export the declaration:

```ts
/**
 * What the Trades bar shows where — v95 C1.
 *
 * `status` and `columns` stay inline at every width: status is how anyone
 * narrows this table, and the column picker is the only way to make 29
 * columns fit anything. The eight field filters and the date range are
 * precise tools used occasionally — exactly what a sheet is for.
 *
 * The two destructive controls demote furthest (`lg`). They were the first
 * thing under a thumb at 390px, above the data they destroy.
 */
export const TRADES_CONTROLS: ToolbarControl[] = [
  { id: 'status', label: 'Status', inlineFrom: 'xs' },
  { id: 'columns', label: 'Columns', inlineFrom: 'xs' },
  { id: 'density', label: 'Density', inlineFrom: 'sm' },
  { id: 'export', label: 'Export CSV', inlineFrom: 'md' },
  { id: 'dates', label: 'Date range', inlineFrom: 'md' },
  { id: 'ticker', label: 'Ticker', inlineFrom: 'md' },
  { id: 'origin', label: 'Origin', inlineFrom: 'md' },
  { id: 'strategy', label: 'Strategy', inlineFrom: 'md' },
  { id: 'horizon', label: 'Horizon', inlineFrom: 'md' },
  { id: 'confidence', label: 'Confidence', inlineFrom: 'md' },
  { id: 'tier', label: 'Tier', inlineFrom: 'md' },
  { id: 'badge', label: 'Badge', inlineFrom: 'md' },
  { id: 'note', label: 'Note', inlineFrom: 'md' },
  { id: 'clear-open', label: 'Clear open', inlineFrom: 'lg' },
  { id: 'clear-history', label: 'Clear history', inlineFrom: 'lg' },
];
```

Add a computed that stamps `active` from live filter state:

```ts
  /** Guard 1 (v95 §5): the sheet must say when something inside it is
   *  narrowing the table. Recomputed from the filters themselves, never from
   *  a flag someone has to remember to set. */
  readonly toolbarControls = computed<ToolbarControl[]>(() =>
    TRADES_CONTROLS.map((control) => ({
      ...control,
      active: this.isFilterEngaged(control.id),
    })),
  );
```

Wrap the existing bar markup in `<sb-toolbar [controls]="toolbarControls()">`
and give every projected control a `slot` attribute matching its `id`. Delete
the workspace's own responsive rules for the bar — the toolbar owns that now.

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/trades/trades.spec.ts`
Expected: PASS.

- [x] **Step 5: Verify visually — mandatory**

At 390px: the first trade row is above the fold or close to it; the sheet
button reads `Filters 13`; opening it reveals every demoted control; setting a
ticker filter and closing the sheet leaves a visible active marker. At 768 and
1024: confirm nothing that used to be inline has vanished without a sheet.

- [x] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/trades/trades.spec.ts
git commit -m "feat(v95): Trades toolbar collapses -- 1700px of chrome becomes a sheet"
```

---

### Task C2: Trades — 29 columns get floors

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.columns.ts`
- Test: `frontend/src/app/workspaces/trades/trades.columns.spec.ts` (create if absent)

**Interfaces:**
- Consumes: `ColumnDef.inlineFrom` (B1).
- Produces: every column in the Trades set carries an explicit `inlineFrom`.

- [ ] **Step 1: Write the failing test**

```ts
describe('Trades column floors', () => {
  it('declares a floor on every column', () => {
    expect(TRADE_COLUMNS.filter((c) => c.inlineFrom === undefined)).toEqual([]);
  });

  it('keeps identity and outcome inline on a phone', () => {
    // What a trader opens a phone to check: which trade, and how is it doing.
    const xs = TRADE_COLUMNS.filter((c) => c.inlineFrom === 'xs').map((c) => c.key);
    expect(xs).toEqual(expect.arrayContaining(['ticker', 'pnl', 'r']));
  });

  it('demotes the progress bar, which ate 40% of a 390px row', () => {
    expect(isInline(TRADE_COLUMNS.find((c) => c.key === 'status')!.inlineFrom, 'xs'))
      .toBe(false);
  });

  it('leaves at most four columns inline at xs', () => {
    // Five 60px columns plus a detail toggle does not fit 390px.
    expect(TRADE_COLUMNS.filter((c) => isInline(c.inlineFrom, 'xs')).length)
      .toBeLessThanOrEqual(4);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/trades/trades.columns.spec.ts`
Expected: FAIL — no column declares a floor.

- [ ] **Step 3: Write the implementation**

Add `inlineFrom` to every entry in `trades.columns.ts`. The four inline at `xs`
are `ticker`, `pnl`, `r` and the row-id link; `now`, `plan` and `held` take
`'sm'`; `status`, `confidence` and `opened` take `'md'`; everything the column
picker exposes beyond the default twelve takes `'lg'`.

Write the reasoning once, above the array:

```ts
/* Column floors — v95 C2.
 *
 * Measured at 390px before this change: the visible four were #, STATUS,
 * TICKER and CONFIDENCE, with NOW, PLAN, P&L %, R, HELD and OPENED pushed off
 * the right edge behind a horizontal scroller. The columns a trader opens a
 * phone to check were exactly the hidden ones, while the status progress bar
 * took ~40% of the width.
 *
 * So: identity and outcome inline, the progress bar demoted, everything the
 * picker adds beyond the default twelve demoted furthest. Demoted means one
 * tap into the row detail, never gone. */
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/trades/trades.columns.spec.ts`
Expected: PASS.

- [ ] **Step 5: Verify visually — mandatory, and this is the interaction change**

At 390px: a row shows ticker, P&L% and R with a detail chevron; expanding shows
every other column labelled. Confirm v80's pinned identity column is still
pinned and the sort select still lists only inline columns. Check on a real
phone if one is to hand — spec §12 flags this as the change most likely to feel
wrong on contact.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/trades/trades.columns.ts frontend/src/app/workspaces/trades/trades.columns.spec.ts
git commit -m "feat(v95): Trades columns declare floors -- P&L and R inline, the rest one tap away"
```

---

### Task C3: Dashboard — panel order moves into `sb-panel-grid`

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts:527-534`
- Test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

`dashboard.ts:527` reorders panels in a hand-rolled `max-width: 720px` block —
undeclared breakpoint, and **backwards**: it puts Open Positions first at
390px, pushing every headline number below a very tall table. At 768px the
order is already correct (summary first). This task deletes the block and
declares the order instead, summary-first at every width.

**Interfaces:**
- Consumes: `PanelGrid.order` (B6).
- Produces: `DASHBOARD_PANEL_ORDER`, exported for E1.

- [ ] **Step 1: Write the failing test**

```ts
describe('Dashboard panel order', () => {
  it('leads with performance at every band', () => {
    // Observed: at 390px positions came first and the portfolio figure was
    // below a 900px table. At 768px performance came first. The phone case
    // was the odd one out, and it was the wrong way round.
    for (const band of ['xs', 'sm', 'md', 'lg', 'xl'] as const) {
      expect(DASHBOARD_PANEL_ORDER[band]?.[0] ?? 'performance').toBe('performance');
    }
  });

  it('no longer carries an undeclared breakpoint', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/dashboard.ts'), 'utf8');
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: FAIL — `DASHBOARD_PANEL_ORDER` undefined, and `720` still present.

- [ ] **Step 3: Write the implementation**

```ts
/**
 * Panel order per band — v95 C3, replacing the max-width:720px block.
 *
 * Performance leads everywhere. The old rule put positions first on phones,
 * which meant the portfolio figure, win rate and expectancy sat below a table
 * that is ~900px tall with five rows. "What is my account doing" is the
 * question a phone is opened to answer; "which six trades are open" is the
 * follow-up.
 */
export const DASHBOARD_PANEL_ORDER = {
  xs: ['performance', 'positions', 'activity', 'movers'],
  sm: ['performance', 'positions', 'activity', 'movers'],
} satisfies Partial<Record<Viewport, string[]>>;
```

Delete lines 527–534 entirely. Wrap the panels in
`<sb-panel-grid [order]="DASHBOARD_PANEL_ORDER">` and give each panel a
`data-panel-id`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: PASS.

- [ ] **Step 5: Verify visually — mandatory**

At 390px: Trading Performance is the first panel; the portfolio figure is
visible without scrolling. At 768 and 1024: order unchanged from before.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git commit -m "fix(v95): Dashboard leads with the summary on phones, not the table"
```

---

### Task C4: Dashboard — column floors, tab counts, one pager

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts`
- Modify: `frontend/src/app/ui/data-table/data-table.ts` (single pager below `md`)
- Modify: `frontend/src/app/ui/layout.ts` (tab counts at `xs`)
- Test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`
- Test: `frontend/src/app/ui/layout.spec.ts`

Three observed defects with one cause — things that fit at 1440px being left
to fend for themselves below it:

1. Six rows bracketed by **two** six-control pagers, ~250px of vertical space.
2. Status tabs render as five bare glyphs at 390px — `Open 6 · Pending 0 ·
   Partial 0 · Closed 3 · Cancelled 0` becomes ⊙ ⧗ ◐ □ ✕, no labels, no counts.
   The accessible names survive; the visible information does not.
3. Open Positions' ten columns with no floors.

**Interfaces:**
- Consumes: `ColumnDef.inlineFrom` (B1), `isInline` (A1).
- Produces: `DASHBOARD_COLUMNS` with floors; `sb-tab-bar` renders counts at
  every width; `sb-data-table` renders one pager below `md`.

- [ ] **Step 1: Write the failing tests**

In `dashboard.spec.ts`:

```ts
it('shows one pager below md, two above', () => {
  // Six rows between two six-control pagers is ~250px of chrome for ~200px
  // of data.
  host.viewportAt.set('sm'); fixture.detectChanges();
  expect(el().querySelectorAll('sb-pagination')).toHaveLength(1);
  host.viewportAt.set('lg'); fixture.detectChanges();
  expect(el().querySelectorAll('sb-pagination')).toHaveLength(2);
});
```

In `layout.spec.ts`:

```ts
it('keeps the count visible when the tab bar goes icon-only', () => {
  // An icon-only tab that drops "6" answers none of the question the tab
  // exists to answer. The icon may replace the word; it must not replace
  // the number.
  host.viewportAt.set('xs'); fixture.detectChanges();
  const tabs = [...el().querySelectorAll('[role="tab"]')].map((t) => t.textContent!.trim());
  expect(tabs.join(' ')).toContain('6');
  expect(tabs.join(' ')).toContain('3');
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- --include src/app/ui/layout.spec.ts`
Expected: FAIL — icon-only tabs render no text.

- [ ] **Step 3: Write the implementation**

In `layout.ts`, in the icon-only block at roughly line 154, stop hiding the
count. Keep hiding the word:

```css
    /* v95 C4: the label collapses to its icon below sm, the COUNT does not.
       A row of five bare glyphs answers none of the question the tab bar
       exists to answer, and the counts are the whole reason it is there. */
    .tab-label { display: none; }
    .tab-count { display: inline; }
```

In `data-table.ts`, render the header pager only at `md` and above:

```ts
  /** One pager below md — v95 C4. Two pagers cost ~250px on a phone, more
   *  than the five rows between them. */
  protected readonly showHeaderPager = computed(
    () => isInline('md', this.viewport()),
  );
```

In `dashboard.ts`, lift the ten Open Positions columns into an **exported**
`DASHBOARD_COLUMNS: ColumnDef<Position>[]` — E1 imports it by that name — and
add `inlineFrom`: `ticker`, `pnl`, `r` at `'xs'`; `now`, `held` at `'sm'`;
`id`, `status`, `confidence`, `plan`, `opened` at `'md'`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- --include src/app/ui/layout.spec.ts`
Run: `cd frontend && npm test -- --include src/app/workspaces/dashboard/dashboard.spec.ts`
Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: PASS for all three. The data-table run is the regression check —
v80's phone-mode tests must still pass.

- [ ] **Step 5: Verify visually — mandatory**

At 390px: tabs read as icon + number; one pager below the table; a row shows
ticker, P&L% and R with a detail chevron. At 768: two-column KPI grid from A5
still correct, one pager. At 1024: two pagers, all ten columns.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/layout.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts frontend/src/app/ui/layout.spec.ts
git commit -m "fix(v95): Dashboard keeps tab counts, drops the duplicate pager, gives columns floors"
```

---

### Task C5: Calendar — stat tiles collapse to a digest

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts`
- Test: `frontend/src/app/workspaces/calendar/calendar.spec.ts`

Observed at 390px: filters plus six stat tiles push the month grid — the reason
the page exists — past 1,400px. Four of the six tiles are dimmed `thin sample`
and repeat `N=12 · thin sample` five times.

**Interfaces:**
- Consumes: `Panel.inlineFrom`, `Panel.digest`, `Panel.problem` (B7, B8).
- Produces: `calendarDigest()` — one line standing in for the six tiles.

- [ ] **Step 1: Write the failing test**

```ts
describe('Calendar stat digest', () => {
  it('summarises the month in one line', () => {
    expect(component.calendarDigest()).toBe('+70.87 € · 53 trades · 26.7% win');
  });

  it('carries the thin-sample warning into the digest rather than losing it', () => {
    // Guard 2: five of six tiles say "N=12 · thin sample". A digest that
    // dropped that would present a thin number as a settled one.
    component.sampleSize.set(12);
    expect(component.calendarProblem()).toContain('thin sample');
  });

  it('reports no problem once the sample is adequate', () => {
    component.sampleSize.set(400);
    expect(component.calendarProblem()).toBeNull();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/calendar/calendar.spec.ts`
Expected: FAIL — neither member exists.

- [ ] **Step 3: Write the implementation**

```ts
  /** The six tiles in one line — v95 C5. Net, count, win rate: the three a
   *  trader would read first, in the order they read them. */
  readonly calendarDigest = computed(() => {
    const net = this.monthNet();
    const sign = net >= 0 ? '+' : '';
    return `${sign}${net.toFixed(2)} € · ${this.monthTrades()} trades · ${this.monthWinRate().toFixed(1)}% win`;
  });

  /** Guard 2 (v95 §5). Five of the six tiles carry "thin sample"; collapsing
   *  them behind a digest that showed only the headline figure would present
   *  an N=12 number as a settled one. */
  readonly calendarProblem = computed(() =>
    this.sampleSize() < MIN_CELL_N ? `thin sample — N=${this.sampleSize()}` : null,
  );
```

Wrap the six tiles in one `<sb-panel inlineFrom="md" [digest]="calendarDigest()"
[problem]="calendarProblem()">`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/calendar/calendar.spec.ts`
Expected: PASS.

- [ ] **Step 5: Verify visually — mandatory**

At 390px with a thin sample: the tiles stay expanded and the warning is
visible (guard 2 fires). With an adequate sample: one digest line, and the
month grid is reachable in roughly one screen instead of four.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/calendar.spec.ts
git commit -m "feat(v95): Calendar stat tiles collapse to a digest that keeps the thin-sample warning"
```

---

### Task C6: Calendar — the month grid becomes an agenda

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts:361-400`
- Test: `frontend/src/app/workspaces/calendar/calendar.spec.ts`

`calendar.ts:361` keeps `repeat(7, minmax(0,1fr))` at every width. At 390px
each day is ~44px wide holding a currency figure and a trade count with no
separation — `+71 10` reads as one number. `earnings-calendar.ts:180-195`
already solved this in the same repo; copy its shape.

**Interfaces:**
- Consumes: nothing new.
- Produces: an `.agenda` list rendering only days with trades, below `sm`.

- [ ] **Step 1: Write the failing test**

```ts
it('renders an agenda, not a 7-column grid, below sm', () => {
  host.viewportAt.set('xs'); fixture.detectChanges();
  expect(el().querySelector('.week')).toBeNull();
  expect(el().querySelector('.agenda')).not.toBeNull();
});

it('lists only days that traded', () => {
  host.viewportAt.set('xs'); fixture.detectChanges();
  expect(el().querySelectorAll('.agenda-day')).toHaveLength(TRADED_DAYS.length);
});

it('separates the value from the count', () => {
  // At 390px the grid rendered "+71 10" with no separator; two numbers
  // touching read as one.
  host.viewportAt.set('xs'); fixture.detectChanges();
  const day = el().querySelector('.agenda-day')!;
  expect(day.querySelector('.agenda-value')).not.toBeNull();
  expect(day.querySelector('.agenda-count')).not.toBeNull();
});

it('keeps the grid at sm and above', () => {
  host.viewportAt.set('sm'); fixture.detectChanges();
  expect(el().querySelector('.week')).not.toBeNull();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/calendar/calendar.spec.ts`
Expected: FAIL — `.agenda` does not exist.

- [ ] **Step 3: Write the implementation**

```html
@if (viewport() === 'xs') {
  <ul class="agenda">
    @for (day of tradedDays(); track day.date) {
      <li class="agenda-day">
        <span class="agenda-date">{{ day.label }}</span>
        <span class="agenda-value" [class.pos]="day.net >= 0">{{ day.net | currency }}</span>
        <span class="agenda-count">{{ day.count }} trades</span>
      </li>
    }
  </ul>
} @else {
  <!-- the existing .weekhead / .week grid, unchanged -->
}
```

```css
    /* v95 C6, after earnings-calendar.ts:180. Seven columns at 390px gives
       ~44px per day for a currency figure and a count; the two ran together
       as "+71 10". An agenda drops empty days, which on a swing book is most
       of them, and gives each traded day a readable row. */
    .agenda { list-style: none; margin: 0; padding: 0; }
    .agenda-day {
      display: flex; align-items: baseline; gap: var(--space-10);
      min-height: var(--row-h); padding: 0 var(--space-10);
      border-bottom: 1px solid var(--line);
    }
    .agenda-date { flex: 0 0 4.5rem; color: var(--text-faint); }
    .agenda-value { flex: 1 1 auto; text-align: right; font-family: var(--font-mono); }
    .agenda-count { flex: 0 0 auto; color: var(--text-faint); font-size: var(--text-chip); }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/calendar/calendar.spec.ts`
Expected: PASS.

- [ ] **Step 5: Verify visually — mandatory**

At 390px: an agenda of traded days, value and count clearly separate. At 768
and 1024: the month grid, unchanged.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/calendar.spec.ts
git commit -m "feat(v95): Calendar becomes an agenda on phones, matching earnings-calendar"
```

---

### Task C7: Watchlist — floors and the toolbar

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts`
- Test: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`

**Interfaces:**
- Consumes: `Toolbar` (B4), `ColumnDef.inlineFrom` (B1).
- Produces: two **exported** symbols, both imported by name in E1 —
  `WATCHLIST_CONTROLS: ToolbarControl[]` and
  `WATCHLIST_COLUMNS: ColumnDef<WatchRow>[]`.

**v80 note:** Watchlist's identity column is `symbol`, and v80 pins it
specifically because a narrow Tape toggle sits before it. Do not put a floor on
`symbol`; B2's exemption would ignore it anyway, and declaring one would be a
lie in the source.

- [ ] **Step 1: Write the failing test**

```ts
describe('Watchlist priorities', () => {
  it('declares a floor on every column but the pinned symbol', () => {
    const undeclared = WATCHLIST_COLUMNS
      .filter((c) => c.key !== 'symbol' && c.inlineFrom === undefined);
    expect(undeclared).toEqual([]);
  });

  it('leaves symbol undeclared — v80 pins it regardless', () => {
    expect(WATCHLIST_COLUMNS.find((c) => c.key === 'symbol')!.inlineFrom).toBeUndefined();
  });

  it('keeps last price and change inline on a phone', () => {
    for (const key of ['last', 'change']) {
      expect(isInline(WATCHLIST_COLUMNS.find((c) => c.key === key)!.inlineFrom, 'xs'))
        .toBe(true);
    }
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/watchlist/watchlist.spec.ts`
Expected: FAIL — no floors declared.

- [ ] **Step 3: Write the implementation**

Add `inlineFrom` to the watchlist columns: `last` and `change` at `'xs'`;
the tape toggle at `'sm'`; everything else at `'md'`. Leave `symbol`
undeclared, with a comment saying why. Wrap the search box and filters in
`<sb-toolbar>` with `WATCHLIST_CONTROLS`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/watchlist/watchlist.spec.ts`
Expected: PASS.

- [ ] **Step 5: Verify visually — mandatory**

At 390 / 768 / 1024. Confirm `symbol` stays pinned at every width and the
`.box` search field still reaches its 420px max without overflowing.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/watchlist/watchlist.spec.ts
git commit -m "feat(v95): Watchlist columns and controls declare floors"
```

---

## Phase C exit criteria

- Trades' first data row is reachable without four screens of scrolling at 390px.
- Every Trades and Dashboard column declares a floor; at most four are inline at `xs`.
- Dashboard leads with Trading Performance at every width, and
  `dashboard.ts` contains no undeclared breakpoint.
- Status tabs show their counts at every width.
- One pager below `md`, two above.
- Calendar renders an agenda at `xs` and keeps its thin-sample warning visible
  through the digest.
- v80 D4's phone-mode tests still pass unmodified.
- All four workspaces looked at, by a person, at 390 / 768 / 1024.
