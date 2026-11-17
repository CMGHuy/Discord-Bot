# v228 — Intraday MFE/MAE for the journal: Part 3, readers (V228-11 .. V228-14)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V228-12" -A 400 <this file>`); never read the part whole.

**Spec:** [2026-11-14-v228-intraday-excursion-design.md](../specs/2026-11-14-v228-intraday-excursion-design.md)
**Index:** [2026-11-14-v228-intraday-excursion_0-index.md](2026-11-14-v228-intraday-excursion_0-index.md) — Goal, Architecture, **Global Constraints**, Review Focus, Parallelisation and the Task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: the admin SPA readers (trade detail V228-11, calendar day card and drawer V228-12, analytics execution tab V228-13) and the Discord trade-view chart (V228-14).

Cross-part contracts consumed here:
- V228-9 (part 2): `swingbot.core.analytics.exit_quality.is_daily_estimate(entry: dict) -> bool` — `excursion_source == "daily"` and `holding_days < 2`, where a missing, `None`, non-numeric or NaN `holding_days` counts as a short hold. `GET /api/v1/analytics/exit-quality` returns `"excursion": {"sources": {...}, "included": int, "excluded": int, "total": int}`; `excluded` counts only short daily holds, and `total - included - excluded` are entries with no source and a short hold, which carry no figures.
- V228-10 (part 2): calendar rows carry `"excursion_source": str | None` beside the existing `held_hours`.
- V228-4 (part 1): journal entries carry `"excursion_source"`; `GET /trades/<id>/journal` returns the entry unfiltered.

**The one rule, everywhere in this part:** a figure is an estimate when its source is `daily` and the hold is under two days (`holding_days < 2`, or `held_hours < 48` on a calendar row); an unknown hold on a `daily` source is a short hold. The SPA's `isDailyEstimate` and the backend's `is_daily_estimate` must agree on every input.

**SPA test command** (vitest through the Angular builder, one spec at a time; run from the worktree root):
`(cd frontend && npx ng test --watch=false --include <spec path relative to frontend/>)`

**Layout check for SPA tasks** (`docs/claude/ui-design.md` § UI tasks): sign in once with `node frontend/scripts/browse.mjs login --base http://localhost:1234`, run `node frontend/scripts/layout-audit.mjs --base http://localhost:1234` before editing and again at the end; the task is done when it exits 0 at 390, 768 and 1440 (the audit's desktop width; the spec's 1280 sits in the same band). Read at most 4 clipped screenshots per task (`node frontend/scripts/browse.mjs shots --path <route> --widths <w> --clip <selector>`), never a full page. The marker only appears on entries stamped `daily` with a short hold; if the local replica has none (V228-7 not applied to it), say so in the task report — never seed fake rows into the shared `swing-db`.

Branch rule for every task: implement in the plan's worktree, never on `main`; each task ends with its own scoped commit there. Per-task verification is the narrow run named in each task; no task runs the full suite (CI does).

# Phase 5 — Readers

### Task V228-11: SPA trade detail: shared `sb-excursion-est`, models, `estimate` flag on MFE/MAE/efficiency

**Model:** sonnet — a new shared UI primitive, three model fields and one store/template change across files that must agree on one rule; no new architecture.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`JournalEntry` ~l.824-848, `AnalyticsExitQuality` ~l.921-931, `CalendarTrade` ~l.2305)
- Create: `frontend/src/app/ui/excursion-estimate.ts`
- Create: `frontend/src/app/ui/excursion-estimate.spec.ts`
- Modify: `frontend/src/app/stores/trade-detail.store.ts` (`excursions` computed ~l.518-535)
- Modify: `frontend/src/app/stores/trade-detail.store.spec.ts` (SR55 block ~l.230-265)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (imports ~l.27-28 and ~l.131-153; Journal tab `.excursions` ~l.314-325; styles `.excursions` ~l.607-612)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (new `describe` block at the end of the file)

**Interfaces:**
- Consumes: `JournalEntry.excursion_source` from `GET /api/v1/trades/:id/journal` (V228-4 writes it; the route returns the entry unfiltered); `JournalEntry.holding_days` (exists). `Hint` (`frontend/src/app/ui/hint.ts`, selector `sb-hint`, inputs `text`, `label`, `align`) — its trigger is a real `<button>` with `aria-label` that opens on tap, focus and hover.
- Produces (later SPA tasks import these; names are final):
  - `frontend/src/app/ui/excursion-estimate.ts`:
    - `export const EXCURSION_EST_LABEL = 'est. (daily bars)';`
    - `export const EXCURSION_EST_EXPLANATION = 'Held under 2 days, intraday bars unavailable, the range may be overstated.';`
    - `export function isDailyEstimate(source: string | null | undefined, heldDays: number | null | undefined): boolean` — `source === 'daily'` and (`heldDays` null, undefined, NaN or `< 2`). Same answer as V228-9's `is_daily_estimate` on every input.
    - `export class ExcursionEstimate` — selector `sb-excursion-est`, no inputs; renders the visible text `est. (daily bars)` in `.est` and an `sb-hint` carrying the explanation.
  - `models.ts`: `JournalEntry.excursion_source?: string | null`; `CalendarTrade.excursion_source?: string | null`; `AnalyticsExitQuality.excursion?: { sources: Record<string, number>; included: number; excluded: number; total: number }`. All optional, so the fixtures that spell out a full `CalendarTrade`/`JournalEntry` (`stores/calendar-day.store.spec.ts:31`, `workspaces/calendar/calendar.spec.ts:339`, `workspaces/calendar/day/calendar-day.spec.ts:61`, `day-trade-card.spec.ts:12`) keep compiling untouched.
  - `TradeDetailStore.excursions` rows gain `estimate: boolean` (the same value on all three rows: efficiency is derived from MFE, so it carries the marker too).

**Why no hover:** the spec and the ux-designer panel item rule out a `title` tooltip: a phone never shows it. The visible text carries the meaning; the explanation is in an `sb-hint`, whose button is reachable by tap and by Tab and is named by its `aria-label`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/excursion-estimate.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  EXCURSION_EST_EXPLANATION,
  EXCURSION_EST_LABEL,
  ExcursionEstimate,
  isDailyEstimate,
} from './excursion-estimate';

describe('isDailyEstimate (v228, mirrors exit_quality.is_daily_estimate)', () => {
  it.each([
    ['daily', 0.5, true],
    ['daily', 1.99, true],
    ['daily', 0, true],
    ['daily', 2, false],
    ['daily', 3.2, false],
    // An unknown hold on daily bars is a short hold (V228-9's rule): every
    // daily figure is either trusted or marked, never neither.
    ['daily', null, true],
    ['daily', undefined, true],
    ['daily', Number.NaN, true],
    ['5min', 0.5, false],
    ['15min', null, false],
    ['hourly', 0.1, false],
    [null, 0.5, false],
    [undefined, undefined, false],
    ['', 0.5, false],
  ] as const)('source %s held %s days -> %s', (source, held, expected) => {
    expect(isDailyEstimate(source, held)).toBe(expected);
  });
});

describe('ExcursionEstimate', () => {
  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  const render = (): HTMLElement => {
    const fixture = TestBed.createComponent(ExcursionEstimate);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  };

  it('shows the meaning as visible text, not behind a hover', () => {
    const el = render();
    expect(el.querySelector('.est')?.textContent?.trim()).toBe(EXCURSION_EST_LABEL);
    expect(EXCURSION_EST_LABEL).toBe('est. (daily bars)');
    expect(el.querySelector('[title]')).toBeNull();
  });

  it('puts the explanation in a tap- and keyboard-reachable hint with an aria-label', () => {
    const el = render();
    const trigger = el.querySelector<HTMLButtonElement>('sb-hint button.trigger');
    expect(trigger).not.toBeNull();
    expect(trigger!.tagName).toBe('BUTTON');            // focusable by Tab, opens on tap
    expect(trigger!.getAttribute('aria-label')).toBe('About this estimate');
    expect(el.querySelector('sb-hint [role="tooltip"]')?.textContent?.trim())
      .toBe(EXCURSION_EST_EXPLANATION);
    expect(EXCURSION_EST_EXPLANATION)
      .toBe('Held under 2 days, intraday bars unavailable, the range may be overstated.');
  });
});
```

In `frontend/src/app/stores/trade-detail.store.spec.ts`, directly after the test `'carries the tags and the auto-lesson through'` (inside the same `describe`, so `open`, `store` and `ENTRY` are in scope), add:

```ts
  it('marks all three figures as estimates for a short hold on daily bars', () => {
    open(null, 'RSI Divergence', { ...ENTRY, excursion_source: 'daily', holding_days: 0.4 });

    const rows = store.excursions();
    expect(rows.map((r) => r.estimate)).toEqual([true, true, true]);
  });

  it('marks a daily figure whose hold is unknown, like the backend rule', () => {
    open(null, 'RSI Divergence', { ...ENTRY, excursion_source: 'daily', holding_days: null });
    expect(store.excursions().every((r) => r.estimate)).toBe(true);
  });

  it.each([
    ['5min', 0.4],
    ['hourly', 0.4],
    ['daily', 3.2],
  ])('leaves %s figures held %s days unmarked', (source, held) => {
    open(null, 'RSI Divergence', { ...ENTRY, excursion_source: source, holding_days: held });
    expect(store.excursions().map((r) => r.estimate)).toEqual([false, false, false]);
  });

  it('leaves an entry written before v228 (no source field) unmarked', () => {
    open(null, 'RSI Divergence', ENTRY);
    expect(store.excursions().map((r) => r.estimate)).toEqual([false, false, false]);
  });
```

At the end of `frontend/src/app/workspaces/trades/trade-detail.spec.ts`, add a new block. It reuses what the file already has at module scope or imports for its other `describe` blocks: `ID`, `DETAIL`, `tradeResponse`, `signInAs`, `role`, `FakeLiveValues`, `LiveValuesStore`, `EventStream`, `FakeEventStream`, `ChartStore`, `TradeDetailStore`, the three interceptors, `provideHttpClientTesting`, `HttpTestingController`, `patchState`, `unprotected`. If one of them is not imported (grep the top of the file), import it from the path the existing blocks use.

```ts
describe('TradeDetail — excursion estimates on the Journal tab (v228)', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
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

  const JOURNAL = {
    trade_id: ID, ticker: 'AAPL', strategy: 'RSI Divergence', horizon_key: '1m',
    direction: 'bullish', tier: 'A', badge: 'VALIDATED', quality_score: 72,
    outcome: 'loss', r_realized: -1.0, mfe_r: 1.4, mae_r: 0.2,
    exit_efficiency: 0.31, holding_days: 0.3, tags: [], auto_lesson: null, note: '',
    opened_at: null, closed_at: null, created_at: null,
  };

  function mountJournal(entry: object): HTMLElement {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', 'journal');
    fixture.detectChanges();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(DETAIL, 'CLOSED'));
    // Set the journal half directly: the journal request's timing is the
    // store spec's business; this block pins only what the template draws.
    patchState(unprotected(TestBed.inject(TradeDetailStore)), {
      journal: entry as never, journalAnswered: true, journalError: null,
    });
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('puts the marker under MFE, MAE and Exit efficiency for a short daily hold', () => {
    const el = mountJournal({ ...JOURNAL, excursion_source: 'daily' });
    const cells = [...el.querySelectorAll('.excursions .excursion')];
    expect(cells).toHaveLength(3);
    for (const cell of cells) {
      expect(cell.querySelector('sb-metric-chip')).not.toBeNull();
      expect(cell.querySelector('sb-excursion-est .est')?.textContent?.trim()).toBe('est. (daily bars)');
    }
  });

  it('draws no marker for figures measured on intraday bars', () => {
    const el = mountJournal({ ...JOURNAL, excursion_source: '5min' });
    expect(el.querySelectorAll('.excursions .excursion')).toHaveLength(3);
    expect(el.querySelector('sb-excursion-est')).toBeNull();
  });

  it('draws no marker on a daily figure for a hold of two days or more', () => {
    const el = mountJournal({ ...JOURNAL, excursion_source: 'daily', holding_days: 2.5 });
    expect(el.querySelector('sb-excursion-est')).toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include src/app/ui/excursion-estimate.spec.ts)`
Expected: FAIL — cannot resolve `./excursion-estimate`.

Run: `(cd frontend && npx ng test --watch=false --include src/app/stores/trade-detail.store.spec.ts)`
Expected: FAIL — the new tests see `estimate` as `undefined`.

Run: `(cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts)`
Expected: FAIL — `.excursions .excursion` has length 0.

- [ ] **Step 3: Implement**

Run `node frontend/scripts/layout-audit.mjs --base http://localhost:1234` first and keep its findings for `/trades/:id?tab=journal` as the baseline (a finding already there is not this task's to fix, but must not get worse).

In `frontend/src/app/api/models.ts`, in `interface JournalEntry`, directly after `holding_days: number | null;` add:

```ts
  /** v228 -- the bars the excursion was measured on: '5min', '15min',
   *  'hourly' or 'daily'; null when no bars covered the trade. Absent on a
   *  server older than v228. A 'daily' figure on a hold under two days is
   *  an estimate (ui/excursion-estimate.ts). */
  excursion_source?: string | null;
```

In `interface CalendarTrade`, directly after `exit_efficiency: number | null;` add:

```ts
  /** v228 -- see JournalEntry.excursion_source; null for an unjournaled
   *  trade. With `held_hours` it decides the day card's estimate marker. */
  excursion_source?: string | null;
```

In `interface AnalyticsExitQuality`, directly after `min_cell_n: number;` add:

```ts
  /** v228 -- how many scoped entries the trust rule kept (`included`:
   *  intraday source or held two days or more) and dropped (`excluded`:
   *  short holds measured on daily bars). `total` is every scoped entry;
   *  the remainder carry no figures. Absent on a server older than v228. */
  excursion?: { sources: Record<string, number>; included: number; excluded: number; total: number };
```

Create `frontend/src/app/ui/excursion-estimate.ts`:

```ts
import { ChangeDetectionStrategy, Component } from '@angular/core';

import { Hint } from './hint';

/**
 * v228 -- the marker for an MFE/MAE figure measured on daily bars for a
 * trade held under two days. The daily bar's range includes price before the
 * fill and after the exit, so the figure may be overstated (measured on
 * production 2026-11-14: median loser MFE 1.24R stored vs 0.31R on 5-minute
 * bars). One rule everywhere -- this file, exit_quality.is_daily_estimate on
 * the server and the Discord chart suffix.
 *
 * The visible text carries the meaning, so nothing depends on hover; the
 * explanation sits in an sb-hint, whose trigger is a real button (Tab, tap)
 * named by its aria-label.
 */
export const EXCURSION_EST_LABEL = 'est. (daily bars)';
export const EXCURSION_EST_EXPLANATION =
  'Held under 2 days, intraday bars unavailable, the range may be overstated.';

/** Holds this long or longer are trusted even on daily bars
 *  (exit_quality.TRUSTED_MIN_HOLD_DAYS). */
const TRUSTED_MIN_HOLD_DAYS = 2;

/** True when a figure came from daily bars on a hold under two days. An
 *  unknown hold (null, undefined, NaN) on daily bars counts as short, as on
 *  the server: every daily figure is either trusted or marked. */
export function isDailyEstimate(
  source: string | null | undefined,
  heldDays: number | null | undefined,
): boolean {
  if (source !== 'daily') return false;
  if (heldDays === null || heldDays === undefined || Number.isNaN(heldDays)) return true;
  return heldDays < TRUSTED_MIN_HOLD_DAYS;
}

@Component({
  selector: 'sb-excursion-est',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hint],
  template: `<span class="est">{{ label }}</span><sb-hint [text]="explanation" label="About this estimate" align="left" />`,
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      color: var(--warn);
      font-size: var(--text-micro);
      white-space: nowrap;
    }
  `,
})
export class ExcursionEstimate {
  protected readonly label = EXCURSION_EST_LABEL;
  protected readonly explanation = EXCURSION_EST_EXPLANATION;
}
```

(`white-space: nowrap` keeps `est. (daily bars)` and its glyph together; the host is inline, so the line around it still wraps before it. The hint's own `::after` gives the 14px glyph its 44px hit area on phone and tablet.)

In `frontend/src/app/stores/trade-detail.store.ts`, add to the imports:

```ts
import { isDailyEstimate } from '../ui/excursion-estimate';
```

and replace the `excursions` computed (~l.518-535) with:

```ts
    excursions: computed<{ label: string; value: number | null; unit: string; decimals: number; estimate: boolean }[]>(
      () => {
        const entry = journal();
        if (!entry) return [];
        // v228: a short hold measured on daily bars is an estimate. All three
        // rows carry it -- efficiency is realized R over MFE, so it inherits
        // MFE's overstatement.
        const estimate = isDailyEstimate(entry.excursion_source, entry.holding_days);
        return [
          { label: 'MFE', value: entry.mfe_r, unit: 'R', decimals: 2, estimate },
          { label: 'MAE', value: entry.mae_r, unit: 'R', decimals: 2, estimate },
          {
            // Stored 0-1; shown as a percentage, because "captured 31% of the
            // favourable move" is the sentence a reader is trying to form.
            label: 'Exit efficiency',
            value: entry.exit_efficiency === null ? null : entry.exit_efficiency * 100,
            unit: '%',
            decimals: 0,
            estimate,
          },
        ];
      }),
```

In `frontend/src/app/workspaces/trades/trade-detail.ts`, add the import next to `MetricChip`:

```ts
import { ExcursionEstimate } from '../../ui/excursion-estimate';
```

add `ExcursionEstimate,` to the component's `imports: [...]` array directly after `MetricChip,`, and replace the `.excursions` block (~l.315-325) with:

```html
                <div class="excursions">
                  @for (figure of store.excursions(); track figure.label) {
                    <div class="excursion">
                      <sb-metric-chip
                        [label]="figure.label"
                        [value]="figure.value"
                        [unit]="figure.unit"
                        [decimals]="figure.decimals"
                        tone="plain"
                      />
                      @if (figure.estimate) {
                        <sb-excursion-est />
                      }
                    </div>
                  }
                </div>
```

In the same file's styles, directly after the `.excursions { ... }` rule (~l.607-612), add:

```css
    /* v228: the chip and, under it, the est. (daily bars) marker. sb-metric-chip
       has no marker slot, so the cell stacks them; min-width: 0 lets the
       auto-fit grid cell shrink on a 390px phone instead of overflowing. */
    .excursion {
      display: flex;
      flex-direction: column;
      gap: var(--space-4);
      min-width: 0;
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include src/app/ui/excursion-estimate.spec.ts)`
Expected: PASS (14 parametrised + 2).

Run: `(cd frontend && npx ng test --watch=false --include src/app/stores/trade-detail.store.spec.ts)`
Expected: PASS (existing + 6 new).

Run: `(cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/trade-detail.spec.ts)`
Expected: PASS (existing + 3 new).

Run: `(cd frontend && npx tsc -p tsconfig.app.json --noEmit)`
Expected: no errors (the new model fields are optional, so no other fixture breaks).

- [ ] **Step 5: Check the page at phone, tablet and desktop**

Rebuild the SPA the local instance serves, then run `node frontend/scripts/layout-audit.mjs --base http://localhost:1234`. Expected: exit 0 at 390, 768 and 1440, and no new finding on `/trades/:id?tab=journal` against the Step 3 baseline (the `hint` check opens the new `sb-hint` by tap at 390/768 and by hover at 1440; the `tap` check counts its 44px `::after`).

If the audited trade's journal entry is a short daily hold, read one clipped shot per width at most: `node frontend/scripts/browse.mjs shots --path "/trades/<id>?tab=journal" --widths 390 --clip ".excursions"` (then 768, 1440). Confirm the marker sits under each chip, wraps inside its grid cell and nothing scrolls sideways. If no such entry exists locally, say so in the task report.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/ui/excursion-estimate.ts frontend/src/app/ui/excursion-estimate.spec.ts
git commit -m "feat(v228): shared est. (daily bars) marker and excursion_source in the SPA models"
git add frontend/src/app/stores/trade-detail.store.ts frontend/src/app/stores/trade-detail.store.spec.ts frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts
git commit -m "feat(v228): trade detail marks short-hold daily MFE, MAE and exit efficiency"
```

### Task V228-12: SPA calendar day card: marker inside the `MFE · MAE` line

**Model:** sonnet — template and test edits on one page's two renderings of the same calendar row, consuming V228-11's primitive; the rule is already written.

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/day/day-trade-card.ts` (imports l.1-12; new exported `rowIsEstimate`; `.stats` line l.58-61; component `imports` l.37; styles)
- Modify: `frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts`
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts` (day drawer meta line l.362-369; component `imports` l.38-41)
- Modify: `frontend/src/app/workspaces/calendar/calendar.spec.ts` (`describe('Calendar day drawer')` ~l.370)

**Scope note:** the ledger row names only the day card. The spec (§5 *Calendar day card*, and its panel line "the older calendar drawer was unnamed -- applied (marked like the card)") also marks the older MFE/MAE drawer in `calendar.ts`, which renders the same `CalendarTrade` row; it is the same calendar workspace and the same rule, so it is done here, with its own test. No other task touches either file.

**Interfaces:**
- Consumes (V228-11): `ExcursionEstimate` (selector `sb-excursion-est`, no inputs) and `isDailyEstimate(source, heldDays)` from `frontend/src/app/ui/excursion-estimate.ts`; `CalendarTrade.excursion_source?: string | null` in `models.ts`. (V228-10): calendar rows carry `excursion_source`; `held_hours` already exists (`held_hours < 48` is the two-day rule).
- Produces: `export function rowIsEstimate(trade: CalendarTrade): boolean` in `day-trade-card.ts` — true when the row shows an MFE or MAE figure and `isDailyEstimate(trade.excursion_source, held_hours / 24)`; a null `held_hours` passes `null` (unknown hold, so a `daily` row is marked). `calendar.ts` imports it; nothing outside this task does.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts`, change the import line `import { DayTradeCard, heldLabel, tradeLinkId } from './day-trade-card';` to:

```ts
import { DayTradeCard, heldLabel, rowIsEstimate, tradeLinkId } from './day-trade-card';
```

Inside `describe('day-trade-card helpers', ...)`, after the `'links to the plan when there is one, else the trade'` test, add:

```ts
  it.each([
    ['daily', 5.5, true],
    ['daily', 47.9, true],
    ['daily', 48, false],
    ['daily', 53.5, false],
    ['daily', null, true],          // unknown hold on daily bars counts as short (V228-9)
    ['5min', 5.5, false],
    ['hourly', 30, false],
    [null, 5.5, false],
    [undefined, 5.5, false],        // a server older than v228 sends no field
  ] as const)('rowIsEstimate: source %s held %s h -> %s', (source, hours, expected) => {
    expect(rowIsEstimate({ ...TRADE, excursion_source: source, held_hours: hours })).toBe(expected);
  });

  it('never marks a row that shows no excursion figure', () => {
    expect(rowIsEstimate({ ...TRADE, excursion_source: 'daily', held_hours: 3, mfe_r: null, mae_r: null }))
      .toBe(false);
  });
```

Inside `describe('DayTradeCard', ...)`, after the `'renders every missing figure as a dash, never 0'` test, add:

```ts
  it('puts the marker inside the MFE · MAE line for a short hold on daily bars', async () => {
    const el = await render({ ...TRADE, excursion_source: 'daily', held_hours: 5.5 });
    const marker = el.querySelector('.stats sb-excursion-est');
    expect(marker).not.toBeNull();
    expect(marker!.querySelector('.est')?.textContent?.trim()).toBe('est. (daily bars)');
    // The line still reads in order; the marker follows MAE.
    expect(text(el, '.stats')).toMatch(/^Held 5h 30m · Shares 10 · MFE \+2\.40R · MAE −0\.30R ?est\. \(daily bars\)/);
    // Its explanation is a hint reachable by tap and keyboard.
    expect(el.querySelector('.stats sb-excursion-est sb-hint button')?.getAttribute('aria-label'))
      .toBe('About this estimate');
  });

  it('marks a daily row whose held time is unknown', async () => {
    const el = await render({ ...TRADE, excursion_source: 'daily', held_hours: null });
    expect(el.querySelector('.stats sb-excursion-est')).not.toBeNull();
  });

  it('leaves the line unmarked on intraday bars or a hold of two days or more', async () => {
    const intraday = await render({ ...TRADE, excursion_source: '5min', held_hours: 5.5 });
    expect(intraday.querySelector('sb-excursion-est')).toBeNull();
    expect(text(intraday, '.stats')).toBe('Held 5h 30m · Shares 10 · MFE +2.40R · MAE −0.30R');
    const long = await render({ ...TRADE, excursion_source: 'daily', held_hours: 53.5 });
    expect(long.querySelector('sb-excursion-est')).toBeNull();
  });
```

The two existing exact-text tests (`'shows held time, shares and MFE/MAE'`, `'renders every missing figure as a dash, never 0'`) stay as they are: `TRADE` has no `excursion_source` and `held_hours: 53.5`, so it is unmarked and the line is byte-identical.

In `frontend/src/app/workspaces/calendar/calendar.spec.ts`, inside `describe('Calendar day drawer', ...)`, after the `'omits the journal half for an unjournaled trade rather than showing blanks'` test, add:

```ts
  it('marks the drawer MFE · MAE line for a short hold on daily bars (v228)', async () => {
    const fixture = seed();
    await openDay(fixture, [{ ...TRADE, excursion_source: 'daily', held_hours: 5.5 }]);

    const row = el(fixture).querySelector('.day-row');
    const marker = row?.querySelector('p.meta sb-excursion-est');
    expect(marker).not.toBeNull();
    expect(marker!.querySelector('.est')?.textContent?.trim()).toBe('est. (daily bars)');
  });

  it('leaves the drawer unmarked for intraday bars, long holds and unjournaled rows (v228)', async () => {
    const fixture = seed();
    await openDay(fixture, [
      { ...TRADE, excursion_source: '5min', held_hours: 5.5 },
      { ...TRADE, trade_id: 'b'.repeat(16), excursion_source: 'daily', held_hours: 53.5 },
      { ...TRADE, trade_id: 'c'.repeat(16), excursion_source: null, held_hours: 5.5,
        mfe_r: null, mae_r: null, exit_efficiency: null },
    ]);

    expect(el(fixture).querySelectorAll('.day-row')).toHaveLength(3);
    expect(el(fixture).querySelector('sb-excursion-est')).toBeNull();
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include src/app/workspaces/calendar/day/day-trade-card.spec.ts)`
Expected: FAIL — `rowIsEstimate` is not exported; the marker tests find no `sb-excursion-est`.

Run: `(cd frontend && npx ng test --watch=false --include src/app/workspaces/calendar/calendar.spec.ts)`
Expected: FAIL — the first new drawer test finds no `sb-excursion-est`.

- [ ] **Step 3: Implement**

Run `node frontend/scripts/layout-audit.mjs --base http://localhost:1234` first and keep its findings for `/trades/calendar` and `/trades/calendar/:date` as the baseline.

In `frontend/src/app/workspaces/calendar/day/day-trade-card.ts`, add to the imports (after the `Hint` import):

```ts
import { ExcursionEstimate, isDailyEstimate } from '../../../ui/excursion-estimate';
```

Below `tradeLinkId` add:

```ts
/** v228 -- whether this row's MFE/MAE came from daily bars on a hold under
 *  two days (`held_hours < 48`), and so may be overstated. An unknown hold
 *  on daily bars counts as short (the server's is_daily_estimate rule). A
 *  row with no MFE and no MAE shows no figure, so it carries no marker. The
 *  calendar drawer (calendar.ts) uses the same function. */
export function rowIsEstimate(trade: CalendarTrade): boolean {
  if (trade.mfe_r === null && trade.mae_r === null) return false;
  const days = trade.held_hours === null ? null : trade.held_hours / 24;
  return isDailyEstimate(trade.excursion_source, days);
}
```

Change the component's `imports` to:

```ts
  imports: [Chip, ExcursionEstimate, Hint, LegName, RouterLink, TradeSparkline],
```

Replace the `.stats` paragraph (l.58-61) with:

```html
      <p class="stats">
        Held {{ heldText() }} · Shares {{ sharesText() }} ·
        MFE {{ r(t.mfe_r) }} · MAE {{ r(t.mae_r) }}
        @if (estimate()) {
          <sb-excursion-est />
        }
      </p>
```

Add, after the `.prices, .stats { ... }` rule in the styles:

```css
    /* v228: the marker rides in the MFE · MAE line and wraps with it on a
       390px phone (the line already has overflow-wrap: anywhere). */
    .stats sb-excursion-est { margin-left: var(--space-4); }
```

Add, after `sharesText` in the class body:

```ts
  protected readonly estimate = computed(() => rowIsEstimate(this.trade()));
```

In `frontend/src/app/workspaces/calendar/calendar.ts`, add to the imports (next to the existing `LegName` import):

```ts
import { ExcursionEstimate } from '../../ui/excursion-estimate';
import { rowIsEstimate } from './day/day-trade-card';
```

add `ExcursionEstimate,` to the component's `imports: [...]` array (l.38-41, after `Drawer,`), and in the day drawer's meta paragraph (l.362-369) add the marker after the MAE line, so the paragraph reads:

```html
            <p class="meta">
              @if (legLabel(trade); as leg) {
                <span class="leg"><sb-leg-name [label]="leg" [help]="legHelp(trade)" /></span> ·
              }
              {{ trade.outcome }} · {{ rLabel(trade.r_multiple) }}
              @if (trade.mfe_r !== null) { · MFE {{ rLabel(trade.mfe_r) }} }
              @if (trade.mae_r !== null) { · MAE {{ rLabel(trade.mae_r) }} }
              @if (excursionEstimate(trade)) { <sb-excursion-est class="est-marker" /> }
            </p>
```

Add a protected member next to `legHelp` (~l.568):

```ts
  /** v228 -- the day card's rule (day/day-trade-card.ts rowIsEstimate). */
  protected readonly excursionEstimate = rowIsEstimate;
```

and to the component's styles:

```css
    .meta .est-marker { margin-left: var(--space-4); }
```

If `calendar.ts` already imports from `./day/day-trade-card` (grep it), extend that import instead of adding a second line.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include src/app/workspaces/calendar/day/day-trade-card.spec.ts)`
Expected: PASS (existing + 10 parametrised/plain helper tests + 3 card tests).

Run: `(cd frontend && npx ng test --watch=false --include src/app/workspaces/calendar/calendar.spec.ts)`
Expected: PASS (existing + 2 new).

Run: `(cd frontend && npx ng test --watch=false --include src/app/workspaces/calendar/day/calendar-day.spec.ts)`
Expected: PASS unchanged (the page that hosts the card; its full `CalendarTrade` fixture has no `excursion_source`, so nothing is marked).

- [ ] **Step 5: Check the page at phone, tablet and desktop**

Rebuild the SPA the local instance serves, then run `node frontend/scripts/layout-audit.mjs --base http://localhost:1234`. Expected: exit 0 at 390, 768 and 1440, and no new finding on `/trades/calendar` or `/trades/calendar/:date` against the Step 3 baseline: no `overflow` (no sideways scroll at 390), no `clipped` text in `.stats`, the marker's `sb-hint` passes the `hint` and `tap` checks.

If the audited day has a short daily hold, read at most one clipped shot per width: `node frontend/scripts/browse.mjs shots --path "/trades/calendar/<date>" --widths 390 --clip "sb-day-trade-card .stats"` (then 768, 1440), and confirm the marker wraps with the line. If no such row exists locally, say so in the task report.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/calendar/day/day-trade-card.ts frontend/src/app/workspaces/calendar/day/day-trade-card.spec.ts
git commit -m "feat(v228): calendar day card marks short-hold daily MFE/MAE"
git add frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/calendar.spec.ts
git commit -m "feat(v228): calendar day drawer takes the same est. (daily bars) marker"
```

### Task V228-13: SPA analytics execution tab: exclusion caption and verdict hint

**Model:** sonnet — one compact component and its spec: a caption and a hint built from an optional response block, with the wording rule from V228-9 to respect.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/execution.ts` (Exit efficiency panel in the template, l.22; `verdict` computed, l.29; styles; a new exported helper)
- Modify: `frontend/src/app/workspaces/analytics/tabs/execution.spec.ts` (`render()` gains an overrides argument; new tests)

**Interfaces:**
- Consumes (V228-11): `AnalyticsExitQuality.excursion?: { sources: Record<string, number>; included: number; excluded: number; total: number }` in `models.ts`. (V228-9): the endpoint builds `efficiency`, `mae` and `scatter` from trusted entries only and returns `excursion = excursion_summary(entries)`: `included` = trusted entries (intraday source, or held two days or more), `excluded` = short holds measured on daily bars **only**, `total` = every scoped entry. `total - included - excluded` are entries with no source and a short hold — no figures were recorded for them, so they are not "short holds on daily bars" and the caption must not count them as such.
- Produces: `export function exclusionCaption(excursion: AnalyticsExitQuality['excursion']): string | null` in `execution.ts` (used only by this component and its spec).

**What the tab says (spec §5, Global Constraints "Execution tab caption"):** the tab shows no per-trade MFE/MAE figure, so no marker. The Exit efficiency panel gets a plain-text caption under its histogram, visible on a phone: `"<included> of <total> trades; <excluded> short holds on daily bars excluded"`. When some entries carry no figures at all, the caption names them separately as `"; <k> without excursion figures"` rather than folding them into the excluded count. The Execution verdict card's `Exit efficiency` hint keeps `N=<n>` and adds `· <excluded> short holds on daily bars excluded`. A server older than v228 sends no `excursion` block: no caption, hint unchanged. An empty scope (`total` 0): no caption.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/analytics/tabs/execution.spec.ts`:

Change the import `import { ExecutionTab } from './execution';` to:

```ts
import { ExecutionTab, exclusionCaption } from './execution';
```

Change `function render() {` and the `const quality = {...};` line under it so the fixture takes overrides (the fixture's existing fields stay exactly as they are):

```ts
function render(overrides: Record<string, unknown> = {}) {
  const quality = { exit_reasons: [{ reason: 'tp1', n: 40 }, { reason: 'other', n: 60 }], unmapped_reasons: [{ status: 'closed', text: '', n: 60 }], hold_by_outcome: { ratio: .48, severity: 'low', avg_winner_days: .31, avg_loser_days: .64 }, hold_points: [{ outcome: 'win', days: .31 }, { outcome: 'loss', days: .64 }], efficiency: { bins: [], n: 324, median: .429 }, mae: { bins: [], n: 0, median: null }, scatter: [], coverage: { mfe_r: { non_null: 555, total: 591, pct: 93.9 } }, min_cell_n: 20, ...overrides };
```

(the rest of `render` is unchanged). Then add, after the existing `describe('ExecutionTab', ...)` block and before `describe('execution.ts breakpoints', ...)`:

```ts
const EXCURSION = { sources: { '5min': 300, daily: 280, none: 11 }, included: 340, excluded: 240, total: 591 };

describe('exclusionCaption (v228)', () => {
  it('says how many trades fed the panel and how many short daily holds it left out', () => {
    expect(exclusionCaption({ sources: {}, included: 351, excluded: 240, total: 591 }))
      .toBe('351 of 591 trades; 240 short holds on daily bars excluded');
  });

  it('names entries without figures apart, never as short daily holds', () => {
    // 591 - 340 - 240 = 11 entries had no bars at all: no source, short hold.
    expect(exclusionCaption(EXCURSION))
      .toBe('340 of 591 trades; 240 short holds on daily bars excluded; 11 without excursion figures');
  });

  it('still states a zero exclusion, so the reader knows the rule ran', () => {
    expect(exclusionCaption({ sources: { '5min': 12 }, included: 12, excluded: 0, total: 12 }))
      .toBe('12 of 12 trades; 0 short holds on daily bars excluded');
  });

  it('says nothing for an empty scope or a server older than v228', () => {
    expect(exclusionCaption({ sources: {}, included: 0, excluded: 0, total: 0 })).toBeNull();
    expect(exclusionCaption(undefined)).toBeNull();
  });
});

describe('ExecutionTab — trust-rule disclosure (v228)', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('captions the Exit efficiency panel under its histogram', () => {
    const { el } = render({ excursion: EXCURSION });
    const caption = el.querySelector('sb-histogram + .caption');
    expect(caption?.textContent?.trim())
      .toBe('340 of 591 trades; 240 short holds on daily bars excluded; 11 without excursion figures');
    // Inside the Exit efficiency panel, not the verdict card (which also says "Exit efficiency").
    const panel = caption!.closest('sb-panel')!;
    expect(panel.querySelector('sb-histogram')).not.toBeNull();
    expect(panel.querySelector('.verdict')).toBeNull();
  });

  it('carries the excluded count in the verdict card hint', () => {
    const { fixture } = render({ excursion: EXCURSION });
    const efficiency = (fixture.componentInstance.verdict() as { label: string; hint: string }[])
      .find((v) => v.label === 'Exit efficiency')!;
    expect(efficiency.hint).toBe('N=324 · 240 short holds on daily bars excluded');
  });

  it('keeps the old panel and hint when the server sends no excursion block', () => {
    const { fixture, el } = render();
    expect(el.querySelector('.caption')).toBeNull();
    const efficiency = (fixture.componentInstance.verdict() as { label: string; hint: string }[])
      .find((v) => v.label === 'Exit efficiency')!;
    expect(efficiency.hint).toBe('N=324');
  });

  it('shows no caption for an empty scope', () => {
    const { el } = render({ excursion: { sources: {}, included: 0, excluded: 0, total: 0 } });
    expect(el.querySelector('.caption')).toBeNull();
  });
});
```

The three existing `ExecutionTab` tests and the breakpoints test stay as they are (`render()` with no argument builds the same fixture as before).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/execution.spec.ts)`
Expected: FAIL — `exclusionCaption` is not exported; no `.caption`; the hint is `N=324`.

- [ ] **Step 3: Implement**

Run `node frontend/scripts/layout-audit.mjs --base http://localhost:1234` first and keep its findings for `/insights/analytics?tab=execution` as the baseline.

In `frontend/src/app/workspaces/analytics/tabs/execution.ts`, add the model import after the `@angular/core` import:

```ts
import { AnalyticsExitQuality } from '../../../api/models';
```

Add, above the `@Component` decorator (below the imports):

```ts
/** v228 -- the Exit efficiency panel's disclosure. The server keeps only
 *  entries measured on intraday bars or held two days or more
 *  (exit_quality.is_trusted); `excluded` counts the short holds measured on
 *  daily bars, whose range may be overstated. Entries with no figures at all
 *  (`total - included - excluded`: no source, short hold) are named apart,
 *  never folded into the excluded short holds. Null for an empty scope or a
 *  server older than v228. */
export function exclusionCaption(excursion: AnalyticsExitQuality['excursion']): string | null {
  if (!excursion || excursion.total === 0) return null;
  const caption = `${excursion.included} of ${excursion.total} trades; `
    + `${excursion.excluded} short holds on daily bars excluded`;
  const unmeasured = excursion.total - excursion.included - excursion.excluded;
  return unmeasured > 0 ? `${caption}; ${unmeasured} without excursion figures` : caption;
}
```

In the template, replace the Exit efficiency panel (l.22):

```html
  <sb-panel><sb-panel-header title="Exit efficiency" [n]="store.scopeN()" /><sb-histogram [bins]="efficiencyBins()" /></sb-panel>
```

with:

```html
  <sb-panel><sb-panel-header title="Exit efficiency" [n]="store.scopeN()" /><sb-histogram [bins]="efficiencyBins()" />@if (efficiencyCaption(); as caption) {<p class="caption">{{ caption }}</p>}</sb-panel>
```

Append to the `styles` string (inside the backticks, before the existing `@media` rule):

```css
.caption{margin:var(--space-6) 0 0;font-size:var(--text-micro);color:var(--text-secondary);overflow-wrap:anywhere}
```

In the class body, add after `private readonly quality = ...;`:

```ts
  readonly efficiencyCaption = computed(() => exclusionCaption(this.quality()?.excursion));
  private readonly excludedHint = computed(() => {
    const excursion = this.quality()?.excursion;
    return excursion ? ` · ${excursion.excluded} short holds on daily bars excluded` : '';
  });
```

and in the `verdict` computed change the first item's hint from:

```ts
hint: `N=${q?.efficiency.n ?? 0}` }
```

to:

```ts
hint: `N=${q?.efficiency.n ?? 0}${this.excludedHint()}` }
```

(`verdict` gains no branch: the conditional lives in `excludedHint`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/execution.spec.ts)`
Expected: PASS (3 existing + 4 helper + 4 component + 1 breakpoints).

Run: `(cd frontend && npx tsc -p tsconfig.app.json --noEmit)`
Expected: no errors.

- [ ] **Step 5: Check the page at phone, tablet and desktop**

Rebuild the SPA the local instance serves, then run `node frontend/scripts/layout-audit.mjs --base http://localhost:1234`. Expected: exit 0 at 390, 768 and 1440, and no new finding on `/insights/analytics?tab=execution` against the Step 3 baseline (the caption must not be `clipped` or `offscreen` at 390, where the panels stack in one column, and its text is at least 11px).

Read at most one clipped shot per width once the local API serves V228-9's `excursion` block: `node frontend/scripts/browse.mjs shots --path "/insights/analytics?tab=execution" --widths 390 --clip ".panels sb-panel:nth-child(3)"` (then 768, 1440), and confirm the caption wraps under the histogram. If the local API predates V228-9, say so in the task report.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/execution.ts frontend/src/app/workspaces/analytics/tabs/execution.spec.ts
git commit -m "feat(v228): execution tab states the short-hold daily exclusion in caption and verdict"
```

# Phase 6 — Discord

### Task V228-14: Discord trade-view chart: `(daily est.)` suffix

**Model:** opus — a behaviour-preserving extraction out of `regenerate_chart_for_trade` plus a label change inside `generate_trade_chart` (complexity 191, legacy baseline row that must not grow); the alert surface has silent no-op traps (`alert-surface` skill).

**Files:**
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (`regenerate_chart_for_trade` l.27-70: the marker block l.46-64 moves into a new `_excursion_markers`)
- Modify: `swingbot/core/charts/trade_chart.py` (new module-level `_marker_label` above `generate_trade_chart` l.207; the label line in the markers block ~l.1021-1022)
- Modify: `tests/charts/test_plan_chart_overlays.py` (`test_markers_render_without_error` ~l.191; new tests after it)
- Create: `tests/scanning/test_v228_chart_markers.py` (joins the existing `scanning` suite via `paths = ["tests/scanning/"]`; that suite holds ~1,104 tests against `max_tests = 1200`, this adds 11)

**Interfaces:**
- Consumes (V228-9): `swingbot.core.analytics.exit_quality.is_daily_estimate(entry: dict) -> bool` — `excursion_source == "daily"` and `holding_days < 2`; a missing, `None`, non-numeric or NaN `holding_days` counts as a short hold (True). Imported, never re-implemented. `JournalStore().get(trade_id)` (exists, `swingbot/core/analytics/journal.py:29`).
- Produces: the `markers` dict handed to `generate_trade_chart` gains `"estimate": bool`; `generate_trade_chart` draws ` (daily est.)` after the R value on both the MFE and MAE annotation when it is truthy. A markers dict without the key (any other caller, every existing test) draws exactly what it draws today.
  - `lifecycle_embeds._excursion_markers(trade: dict, df: pd.DataFrame) -> dict | None` — keys `mfe`, `mfe_r`, `mae`, `mae_r` (unchanged values) plus `estimate`; `None` when there is no journal entry, its `mfe_r` is `None`, or the daily window is empty. May raise (the caller keeps today's `swallowed(...)` guard).
  - `trade_chart._marker_label(key: str, arrow: str, r_val: float | None, estimate: bool) -> str` — e.g. `"▲ MFE +2.0R (daily est.)"`.

**Behaviour preserved:** the marker dates and prices stay where today's code puts them (the daily window from the entry date to the close date, `trade.get("closed_at", trade["opened_at"])[:10]`); the cached-PNG early return (`lifecycle_embeds.py:32-34`) is untouched, so charts already rendered keep their old labels and the suffix appears only on charts drawn after this ships (spec §5). The marker's position for an upgraded intraday entry is out of scope (the spec changes only the label).

**Complexity:** `regenerate_chart_for_trade` is 12 today with no baseline row; the extraction takes it down (the marker block's `if`s move out). `generate_trade_chart` is 191 in `scripts/dev/complexity_baseline.json`; replacing its inline label ternary with a `_marker_label` call removes one branch, so it falls to 190 — never above its row. Leave the baseline file alone (the gate accepts a lower value; `--update` only shrinks, and that is the controller's call at close-out).

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_v228_chart_markers.py`:

```python
"""v228 -- the Discord trade-view chart marks a short-hold daily MFE/MAE.

`_excursion_markers` is the marker block that used to sit inline in
`regenerate_chart_for_trade`; these tests pin that its points are unchanged
and that it now carries `estimate`, decided by exit_quality.is_daily_estimate
(one rule with the admin SPA and the aggregates)."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.analytics import journal as journal_mod
from swingbot.core.scanning import lifecycle_embeds as embeds_mod


def _daily():
    idx = pd.bdate_range("2026-11-02", periods=10)
    highs = [101, 102, 103, 104, 105, 109, 104, 103, 102, 101]
    lows = [99, 98, 97, 96, 95, 94, 93, 97, 98, 99]
    return pd.DataFrame({"Open": 100.0, "High": [float(h) for h in highs],
                         "Low": [float(v) for v in lows], "Close": 100.0,
                         "Volume": 1_000.0}, index=idx)


def _trade(**overrides):
    trade = {
        "id": "t1", "ticker": "AAPL", "horizon_key": "4w", "strategy": "RSI",
        "entry": 100.0, "stop_loss": 98.0, "take_profit": 106.0,
        "direction": "bullish", "status": "loss",
        "opened_at": "2026-11-09T14:35:00+00:00",
        "closed_at": "2026-11-10T18:00:00+00:00",
    }
    trade.update(overrides)
    return trade


def _journal(monkeypatch, entry):
    class _Store:
        def get(self, trade_id):
            return entry
    monkeypatch.setattr(journal_mod, "JournalStore", _Store)


def _entry(**overrides):
    entry = {"trade_id": "t1", "mfe_r": 1.24, "mae_r": 1.0,
             "excursion_source": "daily", "holding_days": 1.1}
    entry.update(overrides)
    return entry


def test_markers_keep_todays_points_and_mark_a_short_daily_hold(monkeypatch):
    _journal(monkeypatch, _entry())
    markers = embeds_mod._excursion_markers(_trade(), _daily())
    # Window = 2026-11-09 .. 2026-11-10 (rows 5 and 6): High max 109 on the
    # 9th, Low min 93 on the 10th -- the same points the inline code chose.
    assert markers["mfe"] == (pd.Timestamp("2026-11-09"), 109.0)
    assert markers["mae"] == (pd.Timestamp("2026-11-10"), 93.0)
    assert markers["mfe_r"] == 1.24 and markers["mae_r"] == 1.0
    assert markers["estimate"] is True


def test_bearish_markers_mirror_the_points(monkeypatch):
    _journal(monkeypatch, _entry())
    markers = embeds_mod._excursion_markers(_trade(direction="bearish"), _daily())
    assert markers["mfe"] == (pd.Timestamp("2026-11-10"), 93.0)
    assert markers["mae"] == (pd.Timestamp("2026-11-09"), 109.0)


@pytest.mark.parametrize("overrides, expected", [
    ({"excursion_source": "5min"}, False),
    ({"excursion_source": "hourly"}, False),
    ({"excursion_source": "daily", "holding_days": 2.0}, False),
    ({"excursion_source": "daily", "holding_days": None}, True),   # unknown hold counts as short
    ({"excursion_source": None, "holding_days": 0.5}, False),
])
def test_estimate_follows_the_shared_rule(monkeypatch, overrides, expected):
    _journal(monkeypatch, _entry(**overrides))
    assert embeds_mod._excursion_markers(_trade(), _daily())["estimate"] is expected


def test_no_markers_without_an_entry_or_an_mfe(monkeypatch):
    _journal(monkeypatch, None)
    assert embeds_mod._excursion_markers(_trade(), _daily()) is None
    _journal(monkeypatch, _entry(mfe_r=None))
    assert embeds_mod._excursion_markers(_trade(), _daily()) is None


def test_no_markers_when_the_daily_window_is_empty(monkeypatch):
    _journal(monkeypatch, _entry())
    trade = _trade(opened_at="2026-12-01T14:35:00+00:00", closed_at="2026-12-02T15:00:00+00:00")
    assert embeds_mod._excursion_markers(trade, _daily()) is None


def test_regenerate_hands_the_estimate_flag_to_the_chart(monkeypatch, tmp_path):
    _journal(monkeypatch, _entry())
    monkeypatch.setattr(config, "TRADE_CHART_DIR", str(tmp_path))   # no cached PNG there
    monkeypatch.setattr(embeds_mod, "get_daily_data", lambda ticker: _daily())
    monkeypatch.setattr(embeds_mod, "get_currency_symbol", lambda ticker, default: default)
    captured = {}

    def _fake_generate(*args, **kwargs):
        captured.update(kwargs)
        return str(tmp_path / "fake_view.png")

    monkeypatch.setattr(embeds_mod, "generate_trade_chart", _fake_generate)
    embeds_mod.regenerate_chart_for_trade(_trade())
    assert captured["markers"]["estimate"] is True
    assert captured["markers"]["mfe"] == (pd.Timestamp("2026-11-09"), 109.0)


def test_a_marker_failure_still_draws_the_chart(monkeypatch, tmp_path):
    class _Broken:
        def get(self, trade_id):
            raise RuntimeError("journal down")
    monkeypatch.setattr(journal_mod, "JournalStore", _Broken)
    monkeypatch.setattr(config, "TRADE_CHART_DIR", str(tmp_path))
    monkeypatch.setattr(embeds_mod, "get_daily_data", lambda ticker: _daily())
    monkeypatch.setattr(embeds_mod, "get_currency_symbol", lambda ticker, default: default)
    captured = {}
    monkeypatch.setattr(embeds_mod, "generate_trade_chart",
                        lambda *a, **k: captured.update(k) or "x.png")
    assert embeds_mod.regenerate_chart_for_trade(_trade()) == "x.png"
    assert captured["markers"] is None
```

In `tests/charts/test_plan_chart_overlays.py`, change the import line `from swingbot.core.charts.trade_chart import generate_trade_chart` to:

```python
from swingbot.core.charts.trade_chart import _marker_label, generate_trade_chart
```

At the end of `test_markers_render_without_error`, inside its `try:` block, directly after the existing MFE assertion, add:

```python
        # A markers dict without "estimate" (every caller before v228) draws
        # no suffix: the label is exactly what it was.
        assert not any("daily est." in txt for txt in all_texts), all_texts
```

and append after that test:

```python
def test_marker_label_suffixes_only_estimates():
    assert _marker_label("mfe", "▲", 2.0, False) == "▲ MFE +2.0R"
    assert _marker_label("mae", "▼", -0.5, False) == "▼ MAE -0.5R"
    assert _marker_label("mfe", "▲", 1.24, True) == "▲ MFE +1.2R (daily est.)"
    assert _marker_label("mae", "▼", None, False) == "▼ MAE"
    assert _marker_label("mae", "▼", None, True) == "▼ MAE (daily est.)"


def test_estimate_markers_render_the_daily_est_suffix(tmp_path):
    """v228: a short hold measured on daily bars says so on the Discord
    chart, the same rule the admin SPA marks with est. (daily bars)."""
    df = _fixture_df()
    markers = {
        "mfe": (df.index[50], float(df["High"].iloc[50])), "mfe_r": 2.0,
        "mae": (df.index[45], float(df["Low"].iloc[45])), "mae_r": 0.5,
        "estimate": True,
    }
    captured_figs = []
    real_close = plt.close

    def _intercept_close(fig=None, *args, **kwargs):
        if fig is not None:
            captured_figs.append(fig)

    with patch("swingbot.core.charts.trade_chart.plt.close", side_effect=_intercept_close):
        generate_trade_chart(
            "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
            filename="with_estimate_markers.png", target2=118.0, markers=markers,
        )

    fig = captured_figs[0]
    try:
        all_texts = [t.get_text() for ax in fig.axes for t in ax.texts]
        assert "▲ MFE +2.0R (daily est.)" in all_texts, all_texts
        assert "▼ MAE +0.5R (daily est.)" in all_texts, all_texts
    finally:
        real_close(fig)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v228_chart_markers.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.scanning.lifecycle_embeds' has no attribute '_excursion_markers'` in the helper tests, and `KeyError: 'estimate'` in `test_regenerate_hands_the_estimate_flag_to_the_chart`. `test_a_marker_failure_still_draws_the_chart` already passes (today's inline block swallows the error the same way); it pins that the extraction keeps that guard.

Run: `python scripts/dev/testrun.py file tests/charts/test_plan_chart_overlays.py`
Expected: FAIL — `ImportError: cannot import name '_marker_label'` (collection error for the whole file).

- [ ] **Step 3: Implement**

In `swingbot/core/charts/trade_chart.py`, add directly above `def generate_trade_chart(` (l.207):

```python
#: v228 -- appended to the MFE/MAE annotation when the figure was measured on
#: daily bars for a hold under two days (exit_quality.is_daily_estimate).
DAILY_ESTIMATE_SUFFIX = " (daily est.)"


def _marker_label(key: str, arrow: str, r_val: float | None, estimate: bool) -> str:
    """The text of one MFE/MAE annotation: arrow, name, optional R value and,
    for a short hold measured on daily bars, the estimate suffix."""
    label = f"{arrow} {key.upper()}"
    if r_val is not None:
        label += f" {r_val:+.1f}R"
    return label + DAILY_ESTIMATE_SUFFIX if estimate else label
```

In the markers block of `generate_trade_chart` (~l.1021-1022), replace:

```python
                r_val = markers.get(f"{key}_r")
                label = f"{arrow} {key.upper()}" + (f" {r_val:+.1f}R" if r_val is not None else "")
```

with:

```python
                label = _marker_label(key, arrow, markers.get(f"{key}_r"), bool(markers.get("estimate")))
```

and add one line to the comment above `if markers:` (after "...scrolled out of frame."): `# v228: a truthy "estimate" key adds " (daily est.)" to both labels.`

In `swingbot/core/scanning/lifecycle_embeds.py`, add directly above `def regenerate_chart_for_trade(` (two blank lines before each `def`, PEP 8):

```python
def _excursion_markers(trade: dict, df) -> dict | None:
    """MFE/MAE marker points for a trade's chart, read from its journal entry.

    The points come from the daily window between the entry and close dates
    (unchanged since B33). v228: ``estimate`` is True when the entry's figures
    were measured on daily bars for a hold under two days, so the chart can
    say "(daily est.)" -- exit_quality.is_daily_estimate, the rule the admin
    SPA and the exit-quality aggregates use. None when the trade has no entry,
    no MFE, or no bars in the window. May raise; the caller logs and draws the
    chart without markers.
    """
    from swingbot.core.analytics.exit_quality import is_daily_estimate
    from swingbot.core.analytics.journal import JournalStore
    entry = JournalStore().get(trade["id"])
    if not entry or entry.get("mfe_r") is None:
        return None
    closed_key = trade.get("closed_at", trade["opened_at"])[:10]
    window = df.loc[trade["opened_at"][:10]:closed_key]
    if window.empty:
        return None
    is_bull = trade["direction"] == "bullish"
    mfe_date = window["High"].idxmax() if is_bull else window["Low"].idxmin()
    mae_date = window["Low"].idxmin() if is_bull else window["High"].idxmax()
    mfe_price = float(window.loc[mfe_date, "High" if is_bull else "Low"])
    mae_price = float(window.loc[mae_date, "Low" if is_bull else "High"])
    return {
        "mfe": (mfe_date, mfe_price), "mfe_r": entry.get("mfe_r"),
        "mae": (mae_date, mae_price), "mae_r": entry.get("mae_r"),
        "estimate": is_daily_estimate(entry),
    }
```

In `regenerate_chart_for_trade`, replace the whole marker block (from `markers = None` through the `except Exception as _je:` handler, l.46-64) with:

```python
        markers = None
        try:
            markers = _excursion_markers(trade, df)
        except Exception as _je:
            swallowed(log, "scan.regenerate_chart.markers", _je,
                      "Could not compute MFE/MAE markers for trade %s: %s", trade.get("id"), _je,
                      level=logging.DEBUG)
```

(The imports stay local, as the inline block had them: `lifecycle_embeds` is imported early by the scan facades and the analytics package pulls in the journal store.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v228_chart_markers.py`
Expected: PASS (11 tests).

Run: `python scripts/dev/testrun.py file tests/charts/test_plan_chart_overlays.py`
Expected: PASS (existing + 2 new).

Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py`
Expected: PASS unchanged — its `regenerate_chart_for_trade` tests (`test_regenerate_chart_passes_the_stored_trendline_fit`, `..._passes_none_without_a_stored_fit`) go through the new helper with whatever the local journal holds for `t1`, and the swallowed guard keeps them green either way.

Complexity: `python -m radon cc -s swingbot/core/scanning/lifecycle_embeds.py swingbot/core/charts/trade_chart.py | grep -E "regenerate_chart_for_trade|_excursion_markers|_marker_label|generate_trade_chart "` — expect `regenerate_chart_for_trade` and `_excursion_markers` each under 15, `_marker_label` 3, and `generate_trade_chart` at 190 or below (baseline row 191). Then `python scripts/dev/complexity_gate.py` exits 0.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/trade_chart.py tests/charts/test_plan_chart_overlays.py
git commit -m "feat(v228): trade chart labels a daily-bar estimate MFE/MAE with (daily est.)"
git add swingbot/core/scanning/lifecycle_embeds.py tests/scanning/test_v228_chart_markers.py
git commit -m "feat(v228): trade-view chart markers carry the shared daily-estimate flag"
```

