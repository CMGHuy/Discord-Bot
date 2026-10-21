# v181 — Dashboard range chart: Part 2b — scope controls, the two-way link, check and close-out (V181-14..V181-17)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V181-15:" -A 400 <this file>`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-10-21-v181-dashboard-range-chart-design.md](../specs/2026-10-21-v181-dashboard-range-chart-design.md)
**Index:** [2026-10-21-v181-dashboard-range-chart_0-index.md](2026-10-21-v181-dashboard-range-chart_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there and bind every task below.

Tasks V181-14..V181-17. V181-14 adds the preset control (chips, plus a native dropdown on phones), the "now" sub-labels, stale dimming and the Closed tab window. V181-15 adds the two-way link: a preset moves the chart, and a hand pan or zoom sets Range. V181-16 is the Playwright check at three widths. V181-17 runs the full suite, merges, runs the panel and closes out. Spec sections covered: § 1 (scope control, phone dropdown, both directions of the link, the programmatic guard, page-wide scope), § 5 ("now" sub-labels), § 6 (the Closed tab sends `closed_from`/`closed_to`), § 8 (data flow), § 9 (stale KPIs keep the Range chip), Testing § Frontend (programmatic-move guard, dropdown below 640 px) and Testing § Visual.

**Paths.** `R=E:/Documents/Private/Projects/Discord-Bot`, `WT=$R/.claude/worktrees/2026-10-21-v181-dashboard-range-chart` (created in V181-1), `SCRATCH` = the session scratchpad directory. Every repo path below is relative to `$WT`. Never `cd` in Bash: use `git -C $WT …` and `npm --prefix $WT/frontend exec -- …`.

**Frontend runner:** `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>` (paths relative to `frontend/`). Never bare `npx vitest run` (it skips `TestBed.initTestEnvironment()`). A run that dies after exactly 60 s with `Timeout waiting for worker to respond` ran nothing: re-run it.

**The app is dark only** (`frontend/src/styles/tokens.css:7`: "Dark only. There is no light theme"). The spec's and index's "light and dark" checks therefore cover the one dark theme, as part 1b already records. No light palette is invented here.

**Contracts consumed from earlier tasks** (ledger rows; this part relies on exactly these and on nothing else from part 2a's text):

- V181-2 / V181-3 / V181-12 (`frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts`):
  - range model: `LogicalWindow {from: number; to: number}`, `TimeWindow {from: string; to: string}` (ISO UTC, `[from, to)`), `inWindowCandles`, `bucketStartInstant(t, tf): Date`, `bucketEndInstant(t, tf): Date`, `windowBounds(candles, tf): TimeWindow | null`;
  - scope model: `ScopePreset`, `SCOPE_PRESETS` (re-exported from `equity-chart-prefs.ts`), `ScopeSelection = {kind: 'preset'; preset} | {kind: 'range'; window}`, `ChartTarget {window: TimeWindow | null; seq: number}` (a null window means all history), `rangeChipLabel(window): string`, `showsNowLabel(scope: ScopeSelection): boolean`.
- V181-12 (`frontend/src/app/api/models.ts`): `DashboardScope` includes `'range'`; `TradeQuery` gains `closedFrom?: string | null; closedTo?: string | null`, which `ApiClient.trades()` sends as `closed_from` / `closed_to`.
- V181-13 (`DashboardStore`): `selection()`, `stale()`, `scope()`, `preset()`, `closedWindow()`, `chartTarget()`, `setPreset(preset)`, `setRange(window)` (debounced 300 ms).
- V181-3 (`EquityCandlesStore` and `equityCandlesStoreStub`): `hasMore`, `pageLoading`, `pageError` (writable signals in the stub), `loadOlder()`, `calls.loadOlder`.
- V181-7 / V181-8 (`equity-candles.ts`): `onVisibleRange(range)`, `inWindow`, `programmatic`, `moveProgrammatically(fn)`, `pendingSpan`, `fitWhenVisible()`. Spec helpers in `equity-candles.spec.ts`: `render`, `response`, `at`, `dailyCandles`, `scaleOf`, `Scale`.
- V181-9 (`trading-performance.ts`): the tone computeds, `tinted()`, `.account` caption, and the spec helpers `card()`, `tint()`, `row()`.

---

# Phase 6 — Scope controls and the link

### Task V181-14: Preset control, phone dropdown, "now" labels, stale dimming, Closed tab window

**Model:** sonnet — three components and their specs: template and wiring work over pinned contracts, with one viewport branch.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/positions-table.ts`
- Modify: `frontend/src/app/workspaces/dashboard/positions-table.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes:
  - V181-12: `ScopePreset`, `SCOPE_PRESETS`, `ScopeSelection`, `TimeWindow`, `rangeChipLabel(window: TimeWindow): string`, `showsNowLabel(scope: ScopeSelection): boolean` (all from `./equity-range.model`), plus `TradeQuery.closedFrom` / `closedTo`.
  - V181-13: `DashboardStore.selection()`, `stale()`, `scope()`, `preset()`, `closedWindow()`, `setPreset(preset)`. `closedWindow()` is `null` on 1D and All, and a window on every other preset and on Range. That is `scopeToRequest(…).window`: 1D is `mode=today`, All is `mode=all`.
  - V181-9: `TradingPerformance` tone computeds and `tinted()`; the spec helpers `card()`, `tint()`, `row()`.
  - Existing code: `ViewportService.isPhone` (`frontend/src/app/ui/breakpoints.ts`), `Select` / `SelectOption` (`frontend/src/app/ui/form-controls.ts`, selector `sb-select`, model `value`, inputs `options`, `ariaLabel`).
- Produces:
  - `TradingPerformance`: input `selection = input<ScopeSelection>({ kind: 'preset', preset: '1D' })`, input `stale = input(false)`, output `presetChange = output<ScopePreset>()`. These replace `scope` / `scopeChange`, and the exported type `DashboardScopeMode` is deleted (its only user was this file).
  - `PositionsTable`: input `closedWindow = input<TimeWindow | null>(null)`.
  - DOM hooks that V181-16's Playwright script reads: `[data-preset="<preset>"]` chips, `.range-chip`, `sb-select.preset-select select`, `.stale-hint`. V181-15 edits `trading-performance.ts` and `dashboard.ts` next and keeps every name above.

Rules (spec § 1, § 5, § 6, § 9; index Global Constraints):
- **Chips at 640 px and up:** `1D · 5D · 1M · 3M · 6M · YTD · 1Y · All` as `sb-button`s, the active one `secondary` with `aria-pressed="true"`. While the scope is Range there is no active preset, and a `.range-chip` shows `Range <rangeChipLabel(window)>`. It is marked `aria-current="true"` and is not a button, because there is nothing to press: a preset leaves Range. The row wraps (`sb-control-row` is `flex-wrap: wrap`) and never scrolls the page sideways.
- **Phone, below 640 px:** one `sb-select` with the same eight entries. While the scope is Range it gets a ninth entry, `Range · <label>`, and that entry is selected. The select is 44 px tall (`--control-h: 44px` set on its host and inherited). `ViewportService.isPhone` decides which control renders, so the unit test can pin it. CSS alone would leave jsdom unable to tell the two apart.
- **"now"** prefixes the sub line of Open P&L, Open trades and Risk used, and suffixes the phone summary's Open and Risk rows (`Open · now`), whenever `showsNowLabel(selection)` is true.
- **No-close hint:** `none closed today` on 1D, `none closed in range` on 5D…1Y and Range, none on All.
- **Stale:** `.grid` and `.mobile-summary` get `.stale` (opacity 0.55). A `.stale-hint` reading "Couldn't refresh for this range · showing the last figures" appears above the figures. The Range chip stays as it is.
- **Closed tab:** on the Closed and Cancelled tabs, a non-null `closedWindow` is sent as `closedFrom` / `closedTo`, with `today` left undefined. With no window, `today` behaves as before. Other tabs get neither.
- **Dashboard:** `closedToday` is `true` only for `scope() === 'today'`. The Realised card label is `Realised today` / `Realised, all days` / `Realised in range` for `today` / `all` / `range`.

- [ ] **Step 1: Write the failing panel tests**

In `trading-performance.spec.ts`:

1. Drop the old scope input from every `render` call. This one-liner leaves every other argument untouched:

```bash
sed -i "s/, scope: 'today'//" $WT/frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts
grep -n "scope" $WT/frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts
```

Expected: the only `scope` hits left are inside the test `'emits the scope the user picked'`, which item 3 deletes.

2. Extend the imports. `provideZonelessChangeDetection` is already imported from `@angular/core`: add `signal` to that same line rather than writing a second import.

```ts
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { ViewportService } from '../../../ui/breakpoints';
import { SCOPE_PRESETS, ScopePreset, ScopeSelection, TimeWindow, rangeChipLabel } from './equity-range.model';
```

3. Delete the test `'emits the scope the user picked'`. Put these fixtures above the first `describe`:

```ts
const preset = (value: ScopePreset): ScopeSelection => ({ kind: 'preset', preset: value });
/** 3 Sep – 18 Oct on the New York clock: `to` is the exclusive 19 Oct midnight. */
const RANGE_WINDOW: TimeWindow = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
const RANGE: ScopeSelection = { kind: 'range', window: RANGE_WINDOW };
```

and add, inside the first `describe` (after V181-9's tests, so `card()` and `row()` are in scope):

```ts
  it('offers the eight presets as chips above phone width, the active one pressed', () => {
    const el = render({ selection: preset('3M'), currency: '€' });
    const chips = [...el.querySelectorAll<HTMLButtonElement>('[data-preset]')];
    expect(chips.map((c) => c.textContent!.trim())).toEqual([...SCOPE_PRESETS]);
    expect(chips.filter((c) => c.getAttribute('aria-pressed') === 'true')
      .map((c) => c.getAttribute('data-preset'))).toEqual(['3M']);
    expect(el.querySelector('sb-select')).toBeNull();
    expect(el.querySelector('.range-chip')).toBeNull();
  });

  it('emits the preset the partner picked', () => {
    const f = TestBed.createComponent(TradingPerformance);
    f.detectChanges();
    let picked: ScopePreset | undefined;
    f.componentInstance.presetChange.subscribe((value: ScopePreset) => (picked = value));
    (f.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('[data-preset="YTD"]')!.click();
    expect(picked).toBe('YTD');
  });

  it('shows a Range chip with the visible dates while the scope is a hand-picked range', () => {
    const el = render({ selection: RANGE, currency: '€' });
    const chip = el.querySelector('.range-chip')!;
    expect(chip.textContent!.replace(/\s+/g, ' ').trim()).toBe(`Range ${rangeChipLabel(RANGE_WINDOW)}`);
    expect(chip.getAttribute('aria-current')).toBe('true');
    expect(el.querySelectorAll('[data-preset][aria-pressed="true"]')).toHaveLength(0);
  });

  it('marks the point-in-time cards "now" outside 1D', () => {
    const subs = (selection: ScopeSelection) => {
      const el = render({ selection, openTrades: 2, openPnlPct: 1, openPnlAmount: 10,
                          riskUsedPct: 1, riskCapPct: 6, currency: '€' });
      return ['Open P&L', 'Open trades', 'Risk used']
        .map((label) => card(el, label).querySelector('.sub')?.textContent?.trim() ?? null);
    };
    const day = subs(preset('1D'));
    expect(day[1]).toBeNull();
    expect(subs(preset('1M'))).toEqual([`now · ${day[0]}`, 'now', `now · ${day[2]}`]);
    expect(subs(RANGE)[1]).toBe('now');
    expect(subs(preset('All'))[1]).toBe('now');
  });

  it('marks the phone summary\'s Open and Risk rows "now" outside 1D', () => {
    const labels = (selection: ScopeSelection) =>
      [...render({ selection, currency: '€' }).querySelectorAll('.mobile-summary > div > span')]
        .map((s) => s.textContent!.replace(/\s+/g, ' ').trim());
    expect(labels(preset('5D'))).toEqual(expect.arrayContaining(['Open · now', 'Risk · now']));
    expect(labels(preset('1D'))).toEqual(expect.arrayContaining(['Open', 'Risk']));
  });

  it('says why a figure is absent, in the scope\'s own words', () => {
    const hint = (selection: ScopeSelection) =>
      card(render({ selection, payoffRatio: null, currency: '€' }), 'Payoff ratio')
        .querySelector('.sub')?.textContent?.trim() ?? null;
    expect(hint(preset('1D'))).toBe('none closed today');
    expect(hint(preset('3M'))).toBe('none closed in range');
    expect(hint(RANGE)).toBe('none closed in range');
    expect(hint(preset('All'))).toBeNull();
  });

  it('dims the last figures with a hint while a range refetch has failed, keeping the Range chip', () => {
    const el = render({ selection: RANGE, stale: true, currency: '€' });
    expect(el.querySelector('.grid')!.classList.contains('stale')).toBe(true);
    expect(el.querySelector('.mobile-summary')!.classList.contains('stale')).toBe(true);
    expect(el.querySelector('.stale-hint')!.textContent).toContain('showing the last figures');
    expect(el.querySelector('.range-chip')).not.toBeNull();
    expect(render({ currency: '€' }).querySelector('.stale-hint')).toBeNull();
  });
```

4. Append a second `describe` for the phone, after the first one:

```ts
describe('trading performance scope on a phone (v181 §1)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: EquityCandlesStore, useValue: equityCandlesStoreStub() },
        { provide: ViewportService, useValue: { isPhone: signal(true) } },
      ],
    });
  });

  function mount(selection: ScopeSelection) {
    const f = TestBed.createComponent(TradingPerformance);
    f.componentRef.setInput('selection', selection);
    f.detectChanges();
    return f;
  }

  it('is one native dropdown below 640px, never the chip row', () => {
    const el = mount(preset('1D')).nativeElement as HTMLElement;
    const select = el.querySelector<HTMLSelectElement>('sb-select.preset-select select')!;
    expect([...select.options].map((o) => o.value)).toEqual([...SCOPE_PRESETS]);
    expect(el.querySelector('[data-preset]')).toBeNull();
  });

  it('lists the hand-picked range as its own entry and emits a preset picked from the list', () => {
    const f = mount(RANGE);
    const select = (f.nativeElement as HTMLElement)
      .querySelector<HTMLSelectElement>('sb-select.preset-select select')!;
    const last = select.options[select.options.length - 1];
    expect([last.value, last.textContent!.trim()])
      .toEqual(['Range', `Range · ${rangeChipLabel(RANGE_WINDOW)}`]);
    let picked: ScopePreset | undefined;
    f.componentInstance.presetChange.subscribe((value: ScopePreset) => (picked = value));
    select.value = '6M';
    select.dispatchEvent(new Event('change'));
    expect(picked).toBe('6M');
  });
});
```

- [ ] **Step 2: Write the failing table and dashboard tests**

In `positions-table.spec.ts`, append inside the `describe` (`clickTab` already exists there; the tab ids are `CLOSED` and `CANCELLED`, `positions-table.ts:28-29`):

```ts
  it('sends the range window, not the Today flag, to the closed and cancelled tabs (v181 §6)', () => {
    const window = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
    const f = mount({ today: null, closedWindow: window });
    // ACTIVE is all-time regardless of the page scope.
    expect(setQuery.mock.calls.at(-1)![0]).not.toHaveProperty('closedFrom');

    clickTab(f, 'CLOSED');
    const closed = setQuery.mock.calls.at(-1)![0];
    expect(closed).toMatchObject({ status: 'CLOSED', closedFrom: window.from, closedTo: window.to });
    expect(closed.today).toBeUndefined();

    clickTab(f, 'CANCELLED');
    expect(setQuery.mock.calls.at(-1)![0]).toMatchObject({ closedFrom: window.from, closedTo: window.to });
  });

  it('lets the window win over a stale Today flag', () => {
    const window = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
    const f = mount({ today: true, closedWindow: window });
    clickTab(f, 'CLOSED');
    expect(setQuery.mock.calls.at(-1)![0].today).toBeUndefined();
  });
```

In `dashboard.spec.ts`, add the imports:

```ts
import { By } from '@angular/platform-browser';
import { TradingPerformance } from './panels/trading-performance';
import { PositionsTable } from './positions-table';
```

and replace the test `'routes the panel scope control back into the store'` with:

```ts
  it('routes the panel presets back into the store (v181 §1)', async () => {
    const fixture = await loaded();
    const el = fixture.nativeElement as HTMLElement;
    const store = TestBed.inject(DashboardStore);
    el.querySelector<HTMLButtonElement>('[data-preset="All"]')!.click();
    fixture.detectChanges();
    expect(store.scope()).toBe('all');
    el.querySelector<HTMLButtonElement>('[data-preset="1M"]')!.click();
    fixture.detectChanges();
    expect(store.preset()).toBe('1M');
    expect(store.scope()).toBe('range');
  });

  it('names the realised window and narrows the Closed tab to it (v181 §6)', async () => {
    const fixture = await loaded();
    const store = TestBed.inject(DashboardStore);
    const panel = fixture.debugElement.query(By.directive(TradingPerformance))
      .componentInstance as TradingPerformance;
    const table = fixture.debugElement.query(By.directive(PositionsTable))
      .componentInstance as PositionsTable;
    expect([panel.realizedLabel(), table.today(), table.closedWindow()])
      .toEqual(['Realised today', true, null]);

    store.setPreset('3M');
    fixture.detectChanges();
    expect(panel.realizedLabel()).toBe('Realised in range');
    expect(panel.selection()).toEqual({ kind: 'preset', preset: '3M' });
    expect(table.today()).toBeNull();
    expect(table.closedWindow()).not.toBeNull();
    expect(table.closedWindow()).toEqual(store.closedWindow());

    store.setPreset('All');
    fixture.detectChanges();
    expect([panel.realizedLabel(), table.today(), table.closedWindow()])
      .toEqual(['Realised, all days', null, null]);
  });
```

- [ ] **Step 3: Run them to see them fail**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts
```

Expected: FAIL. The panel tests hit `NG0303: Can't set value of the 'selection' input`, and there is no `[data-preset]`. The table test fails on `closedFrom` (undefined). The dashboard tests find no `[data-preset="All"]`. V181-9's tests now pass no `scope`, so they still pass.

- [ ] **Step 4: Implement the panel**

In `trading-performance.ts`:

Imports. Replace the `@angular/core` line, drop the `DashboardScope` import, add the select and the viewport, and merge V181-9's `./equity-range.model` import into one:

```ts
import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { ViewportService } from '../../../ui/breakpoints';
import { Button } from '../../../ui/button';
import { Select, SelectOption } from '../../../ui/form-controls';
import { ControlRow, Panel } from '../../../ui/layout';
import { MetricCard } from '../../../ui/metric-card';
import { PortfolioValue } from './portfolio-value';
import { amount, pct } from '../../../ui/format';
import { ACCOUNT_LABEL } from './equity-candles.model';
import {
  SCOPE_PRESETS,
  ScopePreset,
  ScopeSelection,
  breakevenPairTone,
  rangeChipLabel,
  riskTone as riskToneOf,
  showsNowLabel,
  signTone,
} from './equity-range.model';
```

Delete the `DashboardScopeMode` type and its comment. Below the imports add:

```ts
/** The dropdown's value for a hand-picked range: never a preset, never persisted. */
const RANGE_OPTION = 'Range';
```

In the class docstring, replace the paragraph that begins "The scope control sits in this panel's header (D10)" with:

```ts
 * The scope control sits in this panel's header (D10) and is page-wide: it
 * also re-scopes the Closed tab below. v181 §1 widens it from Today / All
 * days to the presets 1D · 5D · 1M · 3M · 6M · YTD · 1Y · All, plus a Range
 * chip that a hand pan or zoom of the chart turns on. Below 640px the same
 * entries are one native dropdown.
```

Set `imports: [Panel, MetricCard, ControlRow, Button, PortfolioValue, Select]`.

In the template, replace the whole `<sb-control-row panel-actions …>…</sb-control-row>` block with:

```html
      <div panel-actions class="scope">
        @if (phone()) {
          <sb-select class="preset-select" ariaLabel="Date scope"
                     [options]="presetOptions()" [value]="selectValue()"
                     (valueChange)="onSelect($event)" />
        } @else {
          <sb-control-row role="group" aria-label="Date scope">
            @for (option of presets; track option) {
              <button
                sb-button
                type="button"
                [attr.data-preset]="option"
                [variant]="activePreset() === option ? 'secondary' : 'ghost'"
                [attr.aria-pressed]="activePreset() === option"
                (click)="presetChange.emit(option)"
              >{{ option }}</button>
            }
            @if (rangeLabel(); as label) {
              <span class="range-chip" aria-current="true"><span class="range-word">Range</span> {{ label }}</span>
            }
          </sb-control-row>
        }
      </div>

      @if (stale()) {
        <p class="stale-hint" role="status">Couldn't refresh for this range · showing the last figures</p>
      }
```

In V181-9's markup, make these four edits:
- `<div class="grid">` becomes `<div class="grid" [class.stale]="stale()">`.
- `<sb-metric-card label="Open trades" [value]="openTrades()" [decimals]="0" />` becomes `<sb-metric-card label="Open trades" [value]="openTrades()" [decimals]="0" [sub]="openTradesSub()" />`.
- `<div class="mobile-summary" aria-label="Portfolio summary">` becomes `<div class="mobile-summary" [class.stale]="stale()" aria-label="Portfolio summary">`.
- In the summary, `<span>Open</span>` becomes `<span>Open{{ nowSuffix() }}</span>` and `<span>Risk</span>` becomes `<span>Risk{{ nowSuffix() }}</span>`.

Styles. Add after `.portfolio { … }`:

```css
    .scope { min-width: 0; max-width: 100%; }
    /* v181 §1: the phone dropdown is a 44px target; --control-h is 28px on a
       fine pointer and the select's own height reads it. */
    .preset-select { display: block; --control-h: 44px; }
    .range-chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      border: 1px solid var(--border-strong);
      border-radius: var(--control-radius);
      background: var(--surface-raised);
      color: var(--text);
      font-size: var(--text-chip);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .range-word { color: var(--text-secondary); }
    /* v181 §9: a failed range refetch keeps the last figures, dimmed. */
    .grid.stale, .mobile-summary.stale { opacity: 0.55; }
    .stale-hint { margin: 0 0 var(--space-10); font-size: var(--text-chip); color: var(--warn); }
```

Class. Replace the `scope` / `scopeChange` inputs and the `scopes` array with:

```ts
  readonly selection = input<ScopeSelection>({ kind: 'preset', preset: '1D' });
  /** v181 §9: the last range refetch failed; the figures are the previous ones. */
  readonly stale = input(false);
  readonly presetChange = output<ScopePreset>();

  /** Below 640px the presets are one native dropdown (v181 §1). */
  protected readonly phone = inject(ViewportService).isPhone;
  protected readonly presets = SCOPE_PRESETS;
  protected readonly activePreset = computed(() => {
    const selection = this.selection();
    return selection.kind === 'preset' ? selection.preset : null;
  });
  protected readonly rangeLabel = computed(() => {
    const selection = this.selection();
    return selection.kind === 'range' ? rangeChipLabel(selection.window) : null;
  });
  protected readonly presetOptions = computed<SelectOption[]>(() => {
    const options = SCOPE_PRESETS.map((value) => ({ value, label: value }));
    const label = this.rangeLabel();
    return label === null ? options : [...options, { value: RANGE_OPTION, label: `Range · ${label}` }];
  });
  protected readonly selectValue = computed(() => this.activePreset() ?? RANGE_OPTION);
  /** Only a preset leaves the dropdown; picking the Range entry changes nothing. */
  protected onSelect(value: string): void {
    const picked = SCOPE_PRESETS.find((option) => option === value);
    if (picked) this.presetChange.emit(picked);
  }

  /** v181 §5: open P&L, open trades and risk used are always "now"; outside
   *  1D a tinted card must not read as that window's exposure. */
  protected readonly nowLabel = computed(() => showsNowLabel(this.selection()));
  protected readonly nowSuffix = computed(() => (this.nowLabel() ? ' · now' : ''));
  protected readonly openTradesSub = computed(() => (this.nowLabel() ? 'now' : null));
  private withNow(text: string | null): string | null {
    if (!this.nowLabel()) return text;
    return text === null ? 'now' : `now · ${text}`;
  }
```

Replace `noCloseHint`, `openPnlSub` and `riskSub` with:

```ts
  /** An em dash alone reads as broken: say why, in the scope's own words.
   *  All has no hint: nothing closed at all is its own answer. */
  protected noCloseHint(value: number | null): string | null {
    if (value !== null) return null;
    const active = this.activePreset();
    if (active === '1D') return 'none closed today';
    return active === 'All' ? null : 'none closed in range';
  }
  protected readonly openPnlSub = computed(() => {
    const value = this.openPnlAmount();
    return this.withNow(value === null ? null : amount(value, this.currency()));
  });
  protected readonly riskSub = computed(() => {
    const cap = this.riskCapPct();
    return this.withNow(cap === null ? null : `of ${cap.toFixed(1)}% cap`);
  });
```

- [ ] **Step 5: Implement the table and the dashboard wiring**

In `positions-table.ts`, add `TradeQuery` to the existing `import { TradeRow } from '../../api/models';` line, and add:

```ts
import { TimeWindow } from './panels/equity-range.model';
```

Add the input beside `today`:

```ts
  /** v181 §6: the scope's `[from, to)` window outside 1D and All. On the
   *  Closed and Cancelled tabs it replaces `today`. */
  readonly closedWindow = input<TimeWindow | null>(null);
```

Add the method above `goToPage`:

```ts
  /** The close-time filter for one tab: the window when there is one, else
   *  the Today flag, and nothing for the tabs that are all-time. */
  private closedScope(scoped: boolean): Pick<TradeQuery, 'today' | 'closedFrom' | 'closedTo'> {
    if (!scoped) return { today: undefined };
    const window = this.closedWindow();
    if (window) return { today: undefined, closedFrom: window.from, closedTo: window.to };
    return { today: this.today() ?? undefined };
  }
```

and change the query effect to spread it in place of the `today:` line:

```ts
      this.trades.setQuery({
        status: tab?.status ?? 'ACTIVE',
        ...this.closedScope(tab?.scoped ?? false),
        // Closed reads newest close first; every other tab by when it opened.
        sort: tab?.status === 'CLOSED' ? '-closed_at' : '-opened_at',
        page: this.page(),
        per_page: perPageForApi(this.perPage()),
      });
```

Update the effect's comment to read "Reading `active`/`today`/`closedWindow`/`perPage`/`page` here IS the subscription".

In `dashboard.ts`, replace the two scope lines on `<sb-trading-performance>`:

```html
      [scope]="store.scope()"
      (scopeChange)="store.setScope($event)"
```

with:

```html
      [selection]="store.selection()"
      [stale]="store.stale()"
      (presetChange)="store.setPreset($event)"
```

and add `[closedWindow]="store.closedWindow()"` after `[today]="closedToday()"` on `<sb-positions-table>`. Add `DashboardScope` to the existing `import { CloseScope, TradeRow } from '../../api/models';` line, and at module level above the `@Component` decorator:

```ts
/** v181 §6: the Realised card's label per applied scope. */
const REALIZED_LABEL: Partial<Record<DashboardScope, string>> = {
  today: 'Realised today',
  all: 'Realised, all days',
  range: 'Realised in range',
};
```

Replace `closedToday` and `realizedLabel` with:

```ts
  /** The Closed tab's `today` input: `true` on 1D (trades closed today,
   *  the rule the lifecycle strip's CLOSED count already used), `null`
   *  otherwise. On All that means unfiltered; on a range the
   *  `closedWindow` input narrows it instead (v181 §6). PositionsTable
   *  applies both to CLOSED/CANCELLED only. */
  protected readonly closedToday = computed(() =>
    this.store.scope() === 'today' ? true : null,
  );
```

```ts
  /** Names the window in the card itself, so a figure cannot be read as
   *  today's when the scope is All or a range. */
  protected readonly realizedLabel = computed(() =>
    REALIZED_LABEL[this.store.scope()] ?? 'Realised today',
  );
```

- [ ] **Step 6: Run the three specs and their neighbours**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts --include src/app/stores/dashboard.store.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/contrast.spec.ts
```

Expected: PASS, 0 failed. The tablet-band source tests in `trading-performance.spec.ts` still pass because no media query was added. If `primitives.spec.ts` or `contrast.spec.ts` objects to a new rule, change the rule, never the gate. Then check that nothing still uses the removed names:

```bash
git -C $WT grep -n "DashboardScopeMode\|scopeChange\|data-scope" -- frontend/src/app/workspaces/dashboard
```

Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C $WT add frontend/src/app/workspaces/dashboard/panels/trading-performance.ts \
  frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts \
  frontend/src/app/workspaces/dashboard/positions-table.ts \
  frontend/src/app/workspaces/dashboard/positions-table.spec.ts \
  frontend/src/app/workspaces/dashboard/dashboard.ts \
  frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git -C $WT commit -m "feat(v181): dashboard scope presets (chips, phone dropdown, Range chip), now labels, stale KPIs, Closed tab window" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V181-15: Two-way link: preset moves the chart, a hand pan sets Range

**Model:** sonnet — timing-sensitive wiring over the existing programmatic flag; small pure helpers carry the decisions and the guard is pinned by tests.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes:
  - V181-2 / V181-12: `LogicalWindow`, `TimeWindow`, `ChartTarget`, `inWindowCandles`, `bucketStartInstant`, `bucketEndInstant`, `windowBounds` (`./equity-range.model`).
  - V181-3: store `hasMore()`, `pageLoading()`, `pageError()`, `loadOlder()`; stub `calls.loadOlder` and its writable `hasMore` / `pageLoading` / `pageError` signals.
  - V181-7: `onVisibleRange`, `inWindow`.
  - V181-8: `programmatic`, `moveProgrammatically(fn)`, `pendingSpan`, `fitWhenVisible()`. Spec helpers `render`, `response`, `at`, `dailyCandles`, `scaleOf`, `Scale`.
  - V181-13: `DashboardStore.chartTarget()`, `setRange(window)` (debounced 300 ms, never bumps `targetSeq`), `setPreset(preset)`.
  - V181-14: `TradingPerformance` / `dashboard.ts` as that task left them.
- Produces:
  - `EquityCandles`: input `target = input<ChartTarget | null>(null)` and output `rangeChange = output<TimeWindow>()`. The output fires on user gestures only.
  - Pure exports from `equity-candles.ts`: `targetLogicalRange(window: TimeWindow, candles: readonly EquityCandle[], tf: EquityTimeframe): LogicalWindow | null` and `targetNeedsOlder(window: TimeWindow | null, candles: readonly EquityCandle[], tf: EquityTimeframe): boolean`. They sit beside the component, not in `equity-range.model.ts`, because the ledger keeps this task out of that file.
  - Pass-through on `sb-portfolio-value` and on `sb-trading-performance`: input `chartTarget = input<ChartTarget | null>(null)` and output `chartRangeChange = output<TimeWindow>()`.

Behaviour (spec § 1, § 7, § 8):
- **Preset → chart.** Each new `target.seq` is applied once. If the window opens before the oldest loaded bucket, or the target is all history, and the store says `hasMore`, the component calls `loadOlder()` and waits. The effect re-runs as pages land. After that it moves under `moveProgrammatically`:
  - a window that loaded candles meet becomes `setVisibleLogicalRange({first − 0.4, last + 0.4})`. `inWindowCandles` reads that back as exactly those whole buckets, so the readout, the baseline and the KPIs agree;
  - a window that no loaded candle meets becomes `scrollToRealTime()`;
  - all history becomes `fitContent()`.

  A failed page (`pageError`) stops the paging, and the move shows what is loaded. Nothing applies while a page is in flight, while the host has no width, or before the chart exists. The ResizeObserver retries a pending target once the host has width.
- **Chart → scope.** `onVisibleRange` emits `rangeChange(windowBounds(inWindow(), tf))` only when `programmatic` is false. Every move the component makes runs under the flag:
  - fit and restore (V181-8);
  - the preset move (above);
  - every `series.setData` (scan refresh, prepended page, new timeframe);
  - the ResizeObserver callback.

  Only a pan, a zoom, or the "↦ Latest" click reaches the scope. The latter is the partner's own move.
- **No loop.** A Range never comes back as a target, because `setRange` does not bump `targetSeq`. A preset never comes back as a Range, because its move is flagged. A timeframe step changes candles only, and its restore is flagged.

- [ ] **Step 1: Write the failing chart tests**

In `equity-candles.spec.ts`, change the component import and add the model import:

```ts
import { EquityCandles, targetLogicalRange, targetNeedsOlder } from './equity-candles';
import { TimeWindow, inWindowCandles } from './equity-range.model';
```

(If V181-7 or V181-8 already import from `./equity-range.model`, merge into that line.) Add these helpers below V181-8's `scaleOf`:

```ts
type LinkScale = Scale & { setVisibleLogicalRange(range: unknown): void; scrollToRealTime(): void };
const linkScale = (fixture: { componentInstance: EquityCandles }) => scaleOf(fixture) as unknown as LinkScale;

/** 2026-08-01 .. 2026-08-31: the page older than `dailyCandles`' 2026-09-01 start. */
function augustCandles(): EquityCandle[] {
  return Array.from({ length: 31 }, (_, i) =>
    candle(new Date(Date.UTC(2026, 7, 1) + i * 86_400_000).toISOString().slice(0, 10)));
}

const W = (from: string, to: string): TimeWindow => ({ from, to });
/** New York midnights (EDT, UTC-4) of 3 Sep and 6 Sep: buckets 3, 4 and 5 Sep. */
const SEP_3_TO_6 = W('2026-09-03T04:00:00.000Z', '2026-09-06T04:00:00.000Z');

type Linked = { programmatic: boolean; series: { setData(points: unknown): void } };
const linked = (fixture: { componentInstance: EquityCandles }) => fixture.componentInstance as unknown as Linked;
```

and append inside the `describe`:

```ts
  describe('preset target helpers (v181 §1)', () => {
    it('selects the whole buckets that meet the window, read back by inWindowCandles', () => {
      const candles = dailyCandles(10);
      const range = targetLogicalRange(SEP_3_TO_6, candles, '1D')!;
      expect(range.from).toBeCloseTo(1.6);
      expect(range.to).toBeCloseTo(4.4);
      expect(inWindowCandles(range, candles).map((c) => c.t))
        .toEqual(['2026-09-03', '2026-09-04', '2026-09-05']);
    });

    it('has no range for a window no loaded candle meets', () => {
      expect(targetLogicalRange(W('2026-12-01T05:00:00.000Z', '2026-12-02T05:00:00.000Z'),
        dailyCandles(10), '1D')).toBeNull();
    });

    it('needs older history while the window opens before the oldest bucket, and always for all history', () => {
      const candles = dailyCandles(10);
      expect(targetNeedsOlder(W('2026-08-20T04:00:00.000Z', '2026-09-05T04:00:00.000Z'), candles, '1D')).toBe(true);
      expect(targetNeedsOlder(W('2026-09-01T04:00:00.000Z', '2026-09-05T04:00:00.000Z'), candles, '1D')).toBe(false);
      expect(targetNeedsOlder(null, candles, '1D')).toBe(true);
      expect(targetNeedsOlder(null, [], '1D')).toBe(false);
    });
  });

  describe('two-way scope link (v181 §1)', () => {
    let widthSpy: ReturnType<typeof vi.spyOn>;
    beforeEach(() => {
      widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => 600);
    });
    afterEach(() => widthSpy.mockRestore());

    function emitted(fixture: { componentInstance: EquityCandles }): TimeWindow[] {
      const seen: TimeWindow[] = [];
      fixture.componentInstance.rangeChange.subscribe((window: TimeWindow) => seen.push(window));
      return seen;
    }

    it('reports a pan or zoom the partner made as whole New York buckets', () => {
      const { fixture } = render(response(dailyCandles(40)));
      const seen = emitted(fixture);
      linked(fixture).programmatic = false;
      at(fixture, 4.6, 24.4);
      // Buckets 5..24 = 6 Sep .. 25 Sep; the window ends at 26 Sep's NY midnight.
      expect(seen).toEqual([{ from: '2026-09-06T04:00:00.000Z', to: '2026-09-26T04:00:00.000Z' }]);
    });

    it('never reports a move the component made itself', () => {
      const { fixture } = render(response(dailyCandles(40)));
      const seen = emitted(fixture);
      linked(fixture).programmatic = true;
      at(fixture, 4.6, 24.4);
      expect(seen).toEqual([]);
    });

    it('redraws candles under the flag, so a refresh or a prepended page is never a gesture', () => {
      const { fixture, stub } = render(response(dailyCandles(40)));
      const component = linked(fixture);
      component.programmatic = false;
      let flagged: boolean | null = null;
      const original = component.series.setData.bind(component.series);
      vi.spyOn(component.series, 'setData').mockImplementation((points: unknown) => {
        flagged = component.programmatic;
        original(points);
      });
      stub.data.set(response([...augustCandles(), ...dailyCandles(40)]));
      fixture.detectChanges();
      expect(flagged).toBe(true);
    });

    it('moves to a preset window under the flag, once per seq', () => {
      const { fixture, stub } = render(response(dailyCandles(40)));
      const component = linked(fixture);
      let flagged: boolean | null = null;
      const move = vi.spyOn(linkScale(fixture), 'setVisibleLogicalRange')
        .mockImplementation(() => { flagged = component.programmatic; });
      fixture.componentRef.setInput('target', { window: SEP_3_TO_6, seq: 1 });
      fixture.detectChanges();
      expect(move).toHaveBeenCalledTimes(1);
      expect(move.mock.calls[0][0]).toEqual({ from: expect.closeTo(1.6), to: expect.closeTo(4.4) });
      expect(flagged).toBe(true);

      stub.data.set(response(dailyCandles(40)));
      fixture.detectChanges();
      expect(move).toHaveBeenCalledTimes(1);
      fixture.componentRef.setInput('target', { window: SEP_3_TO_6, seq: 2 });
      fixture.detectChanges();
      expect(move).toHaveBeenCalledTimes(2);
    });

    it('pages in older history before moving to a window that opens before it', () => {
      const { fixture, stub } = render(response(dailyCandles(40)));
      stub.hasMore.set(true);
      const move = vi.spyOn(linkScale(fixture), 'setVisibleLogicalRange').mockImplementation(() => {});
      fixture.componentRef.setInput('target',
        { window: W('2026-08-01T04:00:00.000Z', '2026-09-03T04:00:00.000Z'), seq: 1 });
      fixture.detectChanges();
      expect(stub.calls.loadOlder).toBe(1);
      expect(move).not.toHaveBeenCalled();

      // The older page lands and was the last one.
      stub.hasMore.set(false);
      stub.data.set(response([...augustCandles(), ...dailyCandles(40)]));
      fixture.detectChanges();
      expect(move).toHaveBeenCalledTimes(1);
      expect(move.mock.calls[0][0]).toEqual({ from: expect.closeTo(-0.4), to: expect.closeTo(32.4) });
    });

    it('pages to the start for all history, then fits', () => {
      const { fixture, stub } = render(response(dailyCandles(40)));
      stub.hasMore.set(true);
      const fit = vi.spyOn(linkScale(fixture), 'fitContent');
      fixture.componentRef.setInput('target', { window: null, seq: 1 });
      fixture.detectChanges();
      expect(stub.calls.loadOlder).toBe(1);
      expect(fit).not.toHaveBeenCalled();
      stub.hasMore.set(false);
      fixture.detectChanges();
      expect(fit).toHaveBeenCalledTimes(1);
    });

    it('shows what is loaded when the older page failed, and waits while one is in flight', () => {
      const { fixture, stub } = render(response(dailyCandles(40)));
      const move = vi.spyOn(linkScale(fixture), 'setVisibleLogicalRange').mockImplementation(() => {});
      stub.hasMore.set(true);
      stub.pageLoading.set(true);
      fixture.componentRef.setInput('target',
        { window: W('2026-08-01T04:00:00.000Z', '2026-09-03T04:00:00.000Z'), seq: 1 });
      fixture.detectChanges();
      expect([stub.calls.loadOlder, move.mock.calls.length]).toEqual([0, 0]);

      stub.pageLoading.set(false);
      stub.pageError.set(true);
      fixture.detectChanges();
      expect(stub.calls.loadOlder).toBe(0);
      expect(move).toHaveBeenCalledTimes(1);
    });

    it('falls back to the newest candles when no loaded candle meets the window', () => {
      const { fixture } = render(response(dailyCandles(40)));
      const latest = vi.spyOn(linkScale(fixture), 'scrollToRealTime').mockImplementation(() => {});
      fixture.componentRef.setInput('target',
        { window: W('2026-12-01T05:00:00.000Z', '2026-12-02T05:00:00.000Z'), seq: 1 });
      fixture.detectChanges();
      expect(latest).toHaveBeenCalledTimes(1);
    });
  });
```

Add `beforeEach` to the spec's `vitest` import if it is not there yet (V181-8 added `afterEach`).

- [ ] **Step 2: Run them to see them fail**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts
```

Expected: FAIL. `targetLogicalRange` is not exported, `NG0303: Can't set value of the 'target' input` is raised, and `rangeChange` is undefined.

- [ ] **Step 3: Implement the link in the chart**

In `equity-candles.ts`:

Imports. Add `output` to the `@angular/core` import and `EquityCandle` to the `../../../api/models` import. Extend the `./equity-range.model` import with `ChartTarget, TimeWindow, bucketEndInstant, bucketStartInstant, windowBounds`.

Above the `@Component` decorator, beside `PROGRAMMATIC_SETTLE_MS`:

```ts
/** v181 §1: the logical range that shows exactly the loaded candles whose
 *  bucket meets `window`. ±0.4 so `inWindowCandles` reads back the same
 *  whole buckets (it counts a candle from half a bar in). Null when no
 *  loaded candle meets the window. */
export function targetLogicalRange(
  window: TimeWindow,
  candles: readonly EquityCandle[],
  tf: EquityTimeframe,
): LogicalWindow | null {
  const from = Date.parse(window.from);
  const to = Date.parse(window.to);
  const meets = (candle: EquityCandle) =>
    bucketStartInstant(candle.t, tf).getTime() < to && bucketEndInstant(candle.t, tf).getTime() > from;
  const first = candles.findIndex(meets);
  if (first < 0) return null;
  const last = candles.length - 1 - [...candles].reverse().findIndex(meets);
  return { from: first - 0.4, to: last + 0.4 };
}

/** True while the window opens before the oldest loaded bucket, or is all
 *  history (null); false with nothing loaded. The caller also needs `hasMore`. */
export function targetNeedsOlder(
  window: TimeWindow | null,
  candles: readonly EquityCandle[],
  tf: EquityTimeframe,
): boolean {
  const oldest = candles[0];
  if (!oldest) return false;
  if (window === null) return true;
  return bucketStartInstant(oldest.t, tf).getTime() > Date.parse(window.from);
}
```

In the class, below `readonly currency = input('€');`:

```ts
  /** v181 §1 preset → chart: where `DashboardStore` wants the view. A new
   *  `seq` is a new request, even for the same window. */
  readonly target = input<ChartTarget | null>(null);
  /** v181 §1 chart → scope: a pan or zoom the partner made, never a move
   *  this component made itself. */
  readonly rangeChange = output<TimeWindow>();
```

Field, beside `pendingSpan`:

```ts
  /** The `seq` of the last target shown, so a refresh never re-applies it. */
  private appliedSeq: number | null = null;
```

In the constructor, after the existing effects (the render effect must run first, so a first-load fit cannot undo the move):

```ts
    // v181 §1: re-checked whenever the target, the candles or the paging
    // state change, so a preset that needs older history lands once it has.
    effect(() => {
      const target = this.target();
      this.store.data();
      this.store.hasMore();
      this.store.pageLoading();
      this.store.pageError();
      untracked(() => this.applyTarget(target));
    });
```

`onVisibleRange`: add as its last line `this.reportUserRange(range);`, then add these methods below `moveProgrammatically`:

```ts
  /** v181 §1 chart → scope, in whole New York buckets. Every move this
   *  component makes (fit, restore, redraw, preset) runs under
   *  `programmatic` and stops here, which is what keeps the link from looping. */
  private reportUserRange(range: LogicalWindow | null): void {
    const tf = this.store.data()?.tf;
    if (this.programmatic || range === null || !tf) return;
    const bounds = windowBounds(this.inWindow(), tf);
    if (bounds) this.rangeChange.emit(bounds);
  }

  /** v181 §1 preset → chart, once per `seq`: page in the history the window
   *  needs, then move there under the programmatic flag. */
  private applyTarget(target: ChartTarget | null): void {
    const data = this.store.data();
    if (!target || !data || !this.readyFor(target, data)) return;
    if (this.needsOlderFor(target, data)) {
      this.store.loadOlder();
      return;
    }
    this.appliedSeq = target.seq;
    this.pendingSpan = null;
    const range = target.window ? targetLogicalRange(target.window, data.candles, data.tf) : null;
    this.moveProgrammatically(() => this.moveTo(range, target.window !== null));
  }

  /** Not yet: already shown, nothing loaded, no chart, hidden, or a page in flight. */
  private readyFor(target: ChartTarget, data: EquityCandlesResponse): boolean {
    return target.seq !== this.appliedSeq && data.candles.length > 0 && this.chart !== null
      && this.host().nativeElement.clientWidth > 0 && !this.store.pageLoading();
  }

  /** More history is needed and can come; after a failed page the move shows what is loaded. */
  private needsOlderFor(target: ChartTarget, data: EquityCandlesResponse): boolean {
    return this.store.hasMore() && !this.store.pageError()
      && targetNeedsOlder(target.window, data.candles, data.tf);
  }

  /** A window with candles in it is shown whole; one with none falls back to
   *  the newest candles; all history is fitted. */
  private moveTo(range: LogicalWindow | null, windowed: boolean): void {
    const scale = this.chart?.timeScale();
    if (!scale) return;
    if (range) scale.setVisibleLogicalRange(range);
    else if (windowed) scale.scrollToRealTime();
    else scale.fitContent();
  }
```

`render()`: replace `series.setData(points);` with:

```ts
    // A redraw (scan refresh, prepended page, new timeframe) can move the
    // logical range; it is never the partner's gesture.
    this.moveProgrammatically(() => series.setData(points));
```

`create()`: replace the ResizeObserver line with:

```ts
      // A resize moves the visible range too, and is not a gesture; it is
      // also when a target that waited for the host's width can land.
      this.resizeObserver = new ResizeObserver(() => this.moveProgrammatically(() => {
        this.fitWhenVisible();
        this.applyTarget(this.target());
      }));
```

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`
Expected: PASS, 0 failed, including V181-7's and V181-8's tests.

- [ ] **Step 4: Write the failing dashboard test**

In `dashboard.spec.ts`, add `import { EquityCandles } from './panels/equity-candles';` (`By` came in V181-14) and append:

```ts
describe('Dashboard v181 scope link', () => {
  function flushDashboard(): void {
    for (const req of TestBed.inject(HttpTestingController).match((r) => r.url === '/api/v1/dashboard')) {
      req.flush(payload());
    }
  }

  it('passes the preset target to the chart and a hand-picked range back to the store', async () => {
    const fixture = await loaded();
    const store = TestBed.inject(DashboardStore);
    const chart = fixture.debugElement.query(By.directive(EquityCandles)).componentInstance as EquityCandles;

    store.setPreset('1M');
    fixture.detectChanges();
    flushDashboard();
    expect(chart.target()).toEqual(store.chartTarget());
    expect(chart.target()!.window).not.toBeNull();
    const seq = store.chartTarget().seq;

    const window = { from: '2026-09-06T04:00:00.000Z', to: '2026-09-26T04:00:00.000Z' };
    chart.rangeChange.emit(window);
    await new Promise((resolve) => setTimeout(resolve, 350));
    flushDashboard();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(store.selection()).toEqual({ kind: 'range', window });
    // The loop guard: a hand-picked range never comes back to the chart as a target.
    expect(store.chartTarget().seq).toBe(seq);
    expect((fixture.nativeElement as HTMLElement).querySelector('.range-chip')).not.toBeNull();
  });
});
```

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: FAIL. `chart.target` is not a function: the input does not exist on the rendered chart yet, or it stays `null` because nothing passes it through.

- [ ] **Step 5: Pass the link through the panels and wire the dashboard**

In `portfolio-value.ts`, add `output` to the `@angular/core` import. Merge `ChartTarget, TimeWindow` into V181-9's `./equity-range.model` import. Change the chart tag to:

```html
    <sb-equity-candles [currency]="currency()" [target]="chartTarget()"
                       (rangeChange)="chartRangeChange.emit($event)" />
```

and add to the class:

```ts
  /** v181 §1: passed straight through; `DashboardStore` owns both ends. */
  readonly chartTarget = input<ChartTarget | null>(null);
  readonly chartRangeChange = output<TimeWindow>();
```

In `trading-performance.ts`, add `ChartTarget, TimeWindow` to the `./equity-range.model` import. On `<sb-portfolio-value …>` add:

```html
          [chartTarget]="chartTarget()"
          (chartRangeChange)="chartRangeChange.emit($event)"
```

and add to the class, below `presetChange`:

```ts
  /** v181 §1 pass-through to the equity chart (see `sb-portfolio-value`). */
  readonly chartTarget = input<ChartTarget | null>(null);
  readonly chartRangeChange = output<TimeWindow>();
```

In `dashboard.ts`, add to `<sb-trading-performance>` after `(presetChange)=…`:

```html
      [chartTarget]="store.chartTarget()"
      (chartRangeChange)="store.setRange($event)"
```

- [ ] **Step 6: Run the chart, the panels and the dashboard**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/stores/dashboard.store.spec.ts
```

Expected: PASS, 0 failed.

- [ ] **Step 7: Commit**

```bash
git -C $WT add frontend/src/app/workspaces/dashboard/panels/equity-candles.ts \
  frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts \
  frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts \
  frontend/src/app/workspaces/dashboard/panels/trading-performance.ts \
  frontend/src/app/workspaces/dashboard/dashboard.ts \
  frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git -C $WT commit -m "feat(v181): presets move the equity chart and a hand pan or zoom sets the Range scope" \
  -m "Every viewport change the chart makes itself (fit, restore, redraw, resize, preset move) runs under the programmatic flag, so the link never loops." \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 7 — Check, merge and close out

### Task V181-16: Playwright check at 375 / 768 / 1280, light and dark

**Model:** sonnet — run the app in a real browser and judge the layout at three widths; the script is given, the judgement is the work.

**Files:**
- Create (session scratchpad only, never committed): `$SCRATCH/v181-widths.cjs`
- Modify only if a check fails: the style block of the component at fault (`trading-performance.ts`, `equity-candles.ts` or `metric-card.ts`), re-running that component's spec

**Interfaces:**
- Consumes: every UI task. The DOM hooks it reads:
  - V181-14: `[data-preset]`, `.range-chip`, `sb-select.preset-select select`, `.stale-hint`, `.mobile-summary`;
  - V181-7: `sb-equity-candles .readout .part`, `.chart`;
  - V181-9: `sb-metric-card.tint-pos` / `.tint-neg`, `[data-tone]`, `.account`;
  - the positions table's `[role="tab"]` strip.
- Produces: the measurement lines and screenshots named in the task report (V181-17 records them).

**What is real and what is stubbed.** `/api/v1/equity/candles` is served from a fixture through `page.route`, and the fixture honours `tf`, `limit` and `before` and answers `has_more`. That makes paging, the auto timeframe step and the preset moves visible whatever the local database holds. `/api/v1/dashboard?mode=range` and `/api/v1/trades?closed_from=&closed_to=` stay **real**: the local admin answers them, so this is also the first end-to-end run of V181-10/11. No figure the local book returns is quoted as the book's.

**Sign-in.** `ADMIN_USERNAME` / `ADMIN_PASSWORD` are read from `$R/.env` inside the script (`process.loadEnvFile`), kept in that process, and never printed, logged or put on a command line. The local admin reads the same `.env`: its config falls back from `$WT/.env` to a `load_dotenv()` search that walks up from `$WT/swingbot` to `$R`. The local instance is therefore built from those values, never from an `admin`/`admin` default.

**Light and dark.** The app is dark only (`tokens.css:7`), so each width is checked once, in the dark theme.

- [ ] **Step 1: Start the local admin and the dev server**

If the local database is not a current replica, run `/replicate-prod-db` first. Then start both servers in the background (Bash `run_in_background: true`, one call each):

```bash
python $WT/admin_ui.py
```

```bash
npm --prefix $WT/frontend exec -- ng serve --port 4123
```

Wait until `curl -s -o /dev/null -w "%{http_code}" http://localhost:4123/app/` prints `200`. If the admin cannot reach a database and exits, stop here and say so in the task report, with the error line. Do not skip the check silently.

- [ ] **Step 2: Write the check script**

Create `$SCRATCH/v181-widths.cjs`:

```js
// v181 three-width check of the dashboard scope. Usage: node v181-widths.cjs <R> <WT> <outDir>
const { createRequire } = require('node:module');
const { mkdirSync, writeFileSync } = require('node:fs');
const [repo, wt, out] = process.argv.slice(2);
const { chromium } = createRequire(`${wt}/frontend/package.json`)('playwright');
mkdirSync(out, { recursive: true });

const BASE = 'http://localhost:4123';
const DEVICES = {
  375: { viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true },
  768: { viewport: { width: 768, height: 1024 }, hasTouch: true },
  1280: { viewport: { width: 1280, height: 900 } },
};

/** The .env admin credentials, kept in this process only: never printed. */
function credentials() {
  process.loadEnvFile(`${repo}/.env`);
  const { ADMIN_USERNAME: username, ADMIN_PASSWORD: password } = process.env;
  if (!username || !password) throw new Error('ADMIN_USERNAME / ADMIN_PASSWORD missing from .env');
  return { username, password };
}

/** Weekday candles per timeframe: ~17 months of 1D/1W, intraday since 1 Sep (EDT, -04:00). */
function series(tf) {
  const out = [];
  const step = { '1H': 1, '4H': 4 }[tf];
  const start = tf === '1D' || tf === '1W' ? Date.UTC(2025, 5, 2) : Date.UTC(2026, 8, 1);
  const end = Date.UTC(2026, 9, 21, 20);
  const inc = tf === '1W' ? 7 * 86400000 : step ? step * 3600000 : 86400000;
  let close = 10000;
  for (let at = start, i = 0; at <= end; at += inc, i++) {
    const day = new Date(at).getUTCDay();
    if (tf !== '1W' && (day === 0 || day === 6)) continue;
    const t = step ? `${new Date(at).toISOString().slice(0, 19)}-04:00` : new Date(at).toISOString().slice(0, 10);
    const open = close;
    close = Math.round((open + Math.sin(i / 3) * 60 + 4) * 100) / 100;
    const change = Math.round((close - open) * 100) / 100;
    out.push({ t, o: open, h: Math.max(open, close) + 30, l: Math.min(open, close) - 30, c: close, change,
               change_pct: Math.round((change / open) * 10000) / 100, samples: 4, skipped: 0, approx: false });
  }
  return out;
}

function candlesResponse(url) {
  const tf = url.searchParams.get('tf') ?? '1D';
  const limit = Number(url.searchParams.get('limit') ?? 120);
  const before = url.searchParams.get('before');
  const all = series(tf).filter((c) => !before || c.t < before);
  return { tf, basis: url.searchParams.get('basis') ?? 'mtm', currency_symbol: '€',
           candles: all.slice(-limit), has_more: all.length > limit,
           recording_since: '2026-09-01T13:30:00Z', as_of: new Date().toISOString() };
}

async function pick(page, preset, phone) {
  if (phone) await page.selectOption('sb-trading-performance sb-select.preset-select select', preset);
  else await page.click(`sb-trading-performance [data-preset="${preset}"]`);
}

async function measure(page) {
  return page.evaluate(() => {
    const panel = document.querySelector('sb-trading-performance');
    const doc = document.documentElement;
    const height = (el) => Math.round(el.getBoundingClientRect().height);
    const chips = [...panel.querySelectorAll('[data-preset]')];
    const select = panel.querySelector('sb-select.preset-select select');
    return {
      pageOverflowPx: Math.max(doc.scrollWidth - doc.clientWidth, document.body.scrollWidth - document.body.clientWidth),
      chips: chips.length,
      pressed: chips.filter((c) => c.getAttribute('aria-pressed') === 'true').map((c) => c.dataset.preset),
      smallestChipPx: chips.length ? Math.min(...chips.map(height)) : null,
      selectPx: select ? height(select) : null,
      selectValue: select ? select.value : null,
      rangeChip: panel.querySelector('.range-chip')?.textContent.replace(/\s+/g, ' ').trim() ?? null,
      readout: [...panel.querySelectorAll('sb-equity-candles .readout .part')].map((p) => p.textContent.trim()).slice(0, 4),
      nowSubs: [...panel.querySelectorAll('sb-metric-card .sub')].filter((s) => s.textContent.trim().startsWith('now')).length,
      nowRows: [...panel.querySelectorAll('.mobile-summary > div > span')].filter((s) => s.textContent.includes('· now')).length,
      tinted: panel.querySelectorAll('sb-metric-card.tint-pos, sb-metric-card.tint-neg, .mobile-summary [data-tone]').length,
      realised: [...panel.querySelectorAll('sb-metric-card .label, .mobile-summary span')]
        .map((l) => l.textContent.trim()).find((t) => t.startsWith('Realised')) ?? null,
      accounts: [...panel.querySelectorAll('.account')].filter((el) => el.getBoundingClientRect().height > 0).length,
      stale: !!panel.querySelector('.stale-hint'),
    };
  });
}

async function drag(page) {
  const box = await page.locator('sb-equity-candles .chart').boundingBox();
  const [x, y] = [box.x + box.width / 2, box.y + box.height / 2];
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 150, y, { steps: 12 });
  await page.mouse.up();
}

async function checkWidth(browser, width) {
  const phone = width < 640;
  const context = await browser.newContext(DEVICES[width]);
  const page = await context.newPage();
  const log = [];
  page.on('request', (r) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/v1/')) log.push(`${url.pathname}${url.search}`);
  });
  await page.route('**/api/v1/equity/candles**', (route) =>
    route.fulfill({ json: candlesResponse(new URL(route.request().url())) }));
  await page.goto(`${BASE}/app/`, { waitUntil: 'domcontentloaded' });
  const ok = await page.evaluate(async (body) => (await fetch('/api/v1/session', {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })).ok, credentials());
  if (!ok) throw new Error('local sign-in with the .env credentials was refused');
  await page.goto(`${BASE}/app/dashboard`, { waitUntil: 'load' });
  await page.waitForSelector('sb-equity-candles .chart canvas', { timeout: 60000 });

  await pick(page, '1D', phone);
  await page.waitForTimeout(1500);
  const day = await measure(page);

  let mark = log.length;
  await pick(page, '1Y', phone);
  await page.waitForTimeout(4000);
  const year = await measure(page);
  const yearLog = log.slice(mark);
  await page.locator('sb-trading-performance').screenshot({ path: `${out}/year-${width}.png` });

  mark = log.length;
  await page.locator('[role="tab"]').nth(3).click();
  await page.waitForTimeout(1000);
  const closedLog = log.slice(mark);

  mark = log.length;
  await page.locator('sb-equity-candles').scrollIntoViewIfNeeded();
  await drag(page);
  await page.waitForTimeout(1500);
  const dragged = await measure(page);
  const dragLog = log.slice(mark);
  await page.locator('sb-trading-performance').screenshot({ path: `${out}/range-${width}.png` });
  await page.screenshot({ path: `${out}/page-${width}.png`, fullPage: true });

  await pick(page, '1D', phone);   // leave the local preference where it started
  await page.waitForTimeout(800);
  await context.close();
  const has = (lines, pattern) => lines.some((line) => pattern.test(line));
  return {
    width, day, year, dragged,
    yearRangeKpis: has(yearLog, /^\/api\/v1\/dashboard\?.*mode=range.*from=.*to=/),
    yearPaged: has(yearLog, /^\/api\/v1\/equity\/candles\?.*before=/),
    yearTimeframes: [...new Set(yearLog.filter((l) => l.startsWith('/api/v1/equity/candles'))
      .map((l) => new URLSearchParams(l.split('?')[1]).get('tf')))],
    closedTabWindow: has(closedLog, /^\/api\/v1\/trades\?.*closed_from=.*closed_to=/),
    dragRangeKpis: has(dragLog, /^\/api\/v1\/dashboard\?.*mode=range/),
  };
}

(async () => {
  const browser = await chromium.launch({ headless: false });
  const report = [];
  for (const width of [375, 768, 1280]) {
    const result = await checkWidth(browser, width);
    report.push(result);
    console.log(JSON.stringify(result));
  }
  writeFileSync(`${out}/report.json`, JSON.stringify(report, null, 2));
  await browser.close();
})();
```

- [ ] **Step 3: Run it**

Install Chromium once per machine first if Playwright asks (`npm --prefix $WT/frontend exec -- playwright install chromium`). Then run:

```bash
node "$SCRATCH/v181-widths.cjs" "$R" "$WT" "$SCRATCH/v181-widths"
```

Expected, one JSON line per width:

- **Every width:**
  - `pageOverflowPx` is 0 in `day`, `year` and `dragged`, and `accounts` is 2: one under the chart readout, one under the KPI figures.
  - `stale` is false.
  - `year.readout[0]` starts with `Equity change`, and `year.realised` is `Realised in range`.
  - `yearRangeKpis`, `yearPaged`, `closedTabWindow` and `dragRangeKpis` are all true.
  - `yearTimeframes` includes `1W`: about 261 weekday bars is more than 250, so the chart steps up a timeframe on its own.
- **375:**
  - `chips` is 0 and `selectPx` is at least 44;
  - `year.selectValue` is `1Y` and `year.nowRows` is 2;
  - `dragged.selectValue` is `Range`.
- **768 and 1280:**
  - `chips` is 8 and `year.pressed` is `["1Y"]`;
  - `year.nowSubs` is 3;
  - `dragged.pressed` is `[]` and `dragged.rangeChip` starts with `Range `;
  - at 768, `smallestChipPx` is at least 44 (a touch device class).

`tinted` depends on the local book. Record it; it is not a pass/fail figure. If the drag at 375 yields no Range, Chromium's mobile emulation dropped the mouse events. Re-run that width once with `hasTouch: false` and note it in the report. The unit tests of V181-15 pin the guard; this check is about layout.

- [ ] **Step 4: Judge the screenshots**

Open `year-375.png`, `year-768.png`, `year-1280.png`, `range-768.png` and `range-1280.png` with the Read tool and confirm by eye:

- at 375, one dropdown sits in the panel header and the summary rows carry their tints;
- at 768, the eight chips wrap inside the header without clipping the heading;
- at 1280, the chips sit on one row;
- the Range chip reads `Range <d Mon> – <d Mon>`;
- the KPI cards that are judged good or bad are tinted, and the em-dash cards are not;
- the dashed baseline and the wash sit behind the candles;
- "now" shows on the three point-in-time cards in 1Y.

Fix any failed expectation in the component's styles, re-run its spec (`npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>`), and re-run the script. Stop both background servers afterwards. Record the three JSON lines and the eye check in the task report.

- [ ] **Step 5: Commit (only if a style was fixed)**

Nothing to commit when every expectation held on the first run. Otherwise commit the fixed file and its spec:

```bash
git -C $WT add <the fixed component> <its spec>
git -C $WT commit -m "fix(v181): <what the three-width check found>" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: `$R` shows no change from this task. The script and screenshots stay in `$SCRATCH`.

### Task V181-17: Full suite, merge, panel, close-out

**Model:** sonnet — run and record the one full suite, then a merge and panel findings that need judgement; the close-out itself is the skill's checklist.

**Files:**
- None in code. A failure is fixed in the file that broke, as its own scoped commit.
- `/close-out` modifies `VERSION.json` and `swingbot/admin/version_history.json`, and moves every `docs/superpowers/plans/2026-10-21-v181-dashboard-range-chart_*.md` file plus `docs/superpowers/specs/2026-10-21-v181-dashboard-range-chart-design.md` into their `implemented/` folders.

**Interfaces:**
- Consumes: every commit of V181-1..V181-16 on the branch `2026-10-21-v181-dashboard-range-chart`, and V181-16's three measurement lines.
- Produces: `main` carrying the merge, any panel fixes and the release commits, pushed. The plan leaves the live set, and the SessionStart `PLAN WIP` line stops naming it.

- [ ] **Step 1: Check the branch is complete and clean**

```bash
git -C $WT status --short
git -C $WT log --oneline main..HEAD
```

Expected: no uncommitted change, and at least one commit for each code task V181-1..V181-15. V181-16 has a commit only if it fixed a style.

- [ ] **Step 2: Run the Python full suite once**

Run `/replicate-prod-db` first (CLAUDE.md: a task that runs tests against the database). Then dispatch the `test-runner` subagent, so none of the output lands in this context. Its brief: run `python $WT/scripts/dev/testrun.py full` with the local test Postgres (`db-test`) up, and report the pass / fail / xfail / skip counts plus the first failure's node id and assertion only.

Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`testing-cost.md`). A run that skipped the database tests because `db-test` was down does not count: start `db-test` and re-run. `testrun.py full` also runs `complexity_gate.py`, so the gate passes here or the run is not green.

- [ ] **Step 3: Run the frontend suite and the production build once**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false
npm --prefix $WT/frontend run build
```

Expected: Vitest `0 failed`, and the build ends without errors. These are the two commands CI runs.

- [ ] **Step 4: Record the complexity figures**

```bash
python -m radon cc -s $WT/swingbot/admin/api_v1/dashboard.py | cat
python -m radon cc -s -n C $WT/swingbot/admin/api_v1/closed_window.py $WT/swingbot/admin/api_v1/equity.py $WT/swingbot/core/tracking/equity_candles.py | cat
python -m radon cc -s $WT/swingbot/admin/api_v1/trades.py | grep -E "list_trades|_in_closed_scope" | cat
git -C $WT diff main...HEAD -- scripts/dev/complexity_baseline.json
```

Expected:
- `dashboard` scores below 21, the figure V181-10 recorded.
- The second command lists nothing: no new or changed function in those files reaches C (11+), let alone 15.
- `list_trades` reads 34 or less, and `_in_closed_scope` is A or B.
- The baseline diff lowers or removes the `swingbot.admin.api_v1.dashboard:dashboard` entry and raises none.

`| cat` keeps radon's colorama from crashing on a closed pipe (brief § 4).

- [ ] **Step 5: Fix any failure alone**

A failing test is fixed in its own scoped commit on the branch (`fix(<area>): … (v181)`). Then it is re-run alone with `python $WT/scripts/dev/testrun.py file <test>` or a single `ng test --include <spec>`, never with the whole suite. Record in the task report:
- the Python counts (passed / skipped / 0 failed / 0 xfailed);
- the Vitest count and the build result;
- the radon lines for `dashboard` before and after.

- [ ] **Step 6: Bring `main` into the branch, then merge it into `main`**

Follow the `worktree-lifecycle` skill, because other sessions share `$R`:

```bash
git -C $R status --short
git -C $WT merge main -m "merge: main into v181 dashboard range chart before release"
```

Expected: `$R` has no pending change to this plan's files, and the merge is clean or its conflicts are resolved file by file. v181 adds no Alembic revision. Re-run alone the tests of any file the merge conflicted in. No full suite here: it ran in Step 2.

Write `$SCRATCH/v181-17-merge-msg.txt`:

```text
merge: v181 dashboard range chart (history paging, auto timeframe, range readout, presets and the two-way scope link, P&L colour)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $R switch main
git -C $R merge --no-ff 2026-10-21-v181-dashboard-range-chart -F "$SCRATCH/v181-17-merge-msg.txt"
git -C $R log --oneline -3
```

Expected: a merge commit on `main`. No full suite after this merge (CLAUDE.md).

- [ ] **Step 7: Run the panel on `main`**

The spec carries `**Panel:** financial-advisor, senior-engineer, quant-engineer`. With `<merge>` the sha from Step 6, run:

```
/panel financial-advisor,senior-engineer,quant-engineer <merge>^1..<merge>
```

Give it Steps 2-4's recorded results and V181-16's three lines as context. Each seat checks that its own findings in the spec's `## Panel review` landed:
- **financial-advisor:** the `ACCOUNT_LABEL` caption under the readout and the KPI grid; neutral colour below 5 closes; "within range" on the drawdown; "now" on the point-in-time cards.
- **senior-engineer:**
  - one `ClosedWindow` through every `mode` consumer, with one test each;
  - `dashboard()` below 21;
  - the pure functions in `equity-range.model.ts`, with store ownership as § 7 names it;
  - the `250 / ratio > 15` test;
  - the programmatic-move guard.
- **quant-engineer:**
  - whole New York buckets for every range window, and 1D's Berlin-day exception;
  - first `o` → last `c` over in-window candles;
  - the `before` cursor round-trip per `tf`, the DST paging tests, and `has_more` before slicing;
  - the drawdown null on a peak ≤ 0;
  - `to` snapped to a bucket end.

A `BLOCKING` finding is fixed on `main` as its own scoped commit (`fix(<area>): … (v181 panel)`). Then re-run only the tests of the files it touched, and re-run the panel for that role. Each `ADVISORY` finding is either applied the same way or recorded with a one-line reason in the task report. Expected: no unresolved `BLOCKING` finding.

- [ ] **Step 8: Close out**

Invoke `/close-out` (standing permission, CLAUDE.md). It does four things:
- resolves the header's `**Bump:** ui minor, bot patch` from the current `VERSION.json`;
- regenerates `swingbot/admin/version_history.json` after each release commit;
- moves the plan files and the spec to `implemented/`;
- removes the worktree.

Before it moves anything, add to the index `docs/superpowers/plans/2026-10-21-v181-dashboard-range-chart_0-index.md` a `## Progress` section holding one line filled from the task reports:

```markdown
Done <YYYY-MM-DD>. V181-1..V181-17 complete. Full suite (V181-17): Python <passed> passed, <skipped> skipped, 0 failed, 0 xfailed; Vitest <n> passed; production build green. dashboard() complexity <before> -> <after> (baseline shrunk). Panel: <n> BLOCKING resolved, <n> ADVISORY (<applied>/<recorded>). Released ui <version>, bot <version>. Three-width check (V181-16): page-scroll-x 0 at 375/768/1280, dark only.
```

The skill's checks, which must hold:
- `ls docs/superpowers/plans/2026-10-21-v181-dashboard-range-chart_*.md` lists exactly the files in the index's Parts table (`_0-index`, `_1a`, `_1b`, `_1c`, `_2a`, `_2b`, and `_2c` if part 2a moved a task there). A missing or extra file is checked before moving.
- The branch name contains no `backup` and is not `stable-*`. `git -C $R rev-list --count main..2026-10-21-v181-dashboard-range-chart` prints `0` before `git worktree remove` and `git branch -d` (never `-D`; non-zero means stop and ask the partner).
- After the bump, `python $R/scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py` passes.

- [ ] **Step 9: Push and confirm**

```bash
git -C $R status --short
git -C $R push origin main
gh run list --branch main --limit 1
```

Expected: no pending change to this plan's paths; the push is accepted; a workflow run for the new `main` head is listed. If another session pushed first and the push is rejected, run `git -C $R pull --no-rebase origin main` and push again, never by force. No full suite after this: it ran once, in Step 2.

- [ ] **Step 10: Commit**

This task's commits are the ones made in Steps 5-8: any fix commits, the merge, any panel fixes, and `/close-out`'s release, regeneration and move commits. Each message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Afterwards `git -C $R log --oneline -8` shows them and `git -C $R worktree list` no longer lists the v181 worktree.
