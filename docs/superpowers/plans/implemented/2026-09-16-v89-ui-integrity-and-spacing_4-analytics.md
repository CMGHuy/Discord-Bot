# v89 Admin UI Integrity and Spacing — Part 4: Analytics

> Header, global constraints, parallelisation and the task index live in `2026-09-16-v89-ui-integrity-and-spacing_0-index.md`. Every task here implicitly includes that file's Global Constraints. The spacing conventions at the top of `_3-workspaces.md` apply here too.

# Phase 4 — Analytics (worktree)

### Task UA13: Analytics — bar lists, N on Overall, rendered journal, exit-reason warning, honest labels, spacing

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`AnalyticsPerformance`, its `calendar` row type, `AnalyticsExitQuality`)
- Modify: `frontend/src/app/stores/analytics.store.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.columns.ts:111,127`
- Modify: `frontend/src/app/workspaces/analytics/sections/exit-quality.ts`
- Modify: `frontend/src/app/ui/spacing.spec.ts` (remove the six analytics entries)
- Create: `frontend/src/app/stores/analytics.bars.spec.ts`
- Create: `frontend/src/app/workspaces/analytics/sections/exit-quality.spec.ts`
- Test (modify): `frontend/src/app/stores/analytics.snapshot.spec.ts:285-297`, `frontend/src/app/workspaces/analytics/analytics.spec.ts:502-565`, `frontend/src/app/workspaces/analytics/analytics.columns.spec.ts`

**Interfaces:**
- Consumes:
  - UA2: `BarList`, `BarRow`.
  - UA3: `InlineMd`.
  - UA4: `win_rate_n`, `expectancy_n` on `/analytics/performance`.
  - UA5: `calendar[].pnl`, `return_pct: number | null`.
  - UA6: `unmapped_reasons`.
  - UA1: `.sb-stack`, `--section-gap`.
- Produces (in `analytics.store.ts`):
  - `export function rateBars(buckets: readonly HoldingBucket[]): BarRow[]`
  - `export function monthBars(rows: readonly { month: string; return_pct: number | null; n: number }[]): BarRow[]`
  - `export function zeroFilledBars(rows: BreakdownRow[], order: readonly (readonly [string, string])[], floor: number): BarRow[]`
  - Store computeds `holdingPeriodBars`, `riskRewardBars`, `monthBars`, `directionBars`, `dowBars` (all `BarRow[]`), plus `winRateN`, `expectancyN`.
  - The same five `*Histogram` computeds and `zeroFilledHistogram` are **deleted**.

- [ ] **Step 1: Write the failing pure-function spec**

Create `frontend/src/app/stores/analytics.bars.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { monthBars, rateBars, zeroFilledBars } from './analytics.store';

describe('analytics bar rows (v89 spec §3.1)', () => {
  it('keeps a month\'s return signed -- the bar list draws the sign', () => {
    expect(monthBars([
      { month: '2026-07', return_pct: -0.08, n: 300 },
      { month: '2026-09', return_pct: 0.01, n: 48 },
    ])).toEqual([
      { label: '2026-07', value: -0.08, n: 300 },
      { label: '2026-09', value: 0.01, n: 48 },
    ]);
  });

  it('maps a rate bucket to label, value and n, withholding a null rate', () => {
    expect(rateBars([
      { bucket: '0h-2h', n: 357, win_rate: 64.705882, avg_return_pct: null },
      { bucket: '<1.5', n: 0, win_rate: null, avg_return_pct: null },
    ])).toEqual([
      { label: '0h-2h', value: 64.705882, n: 357, withheld: false },
      { label: '<1.5', value: null, n: 0, withheld: true },
    ]);
  });

  it('zero-fills a segment and keeps n out of the label', () => {
    const rows = zeroFilledBars(
      [{ key: 'bullish', n: 30, wins: 16, losses: 14, win_rate: 53.3, expectancy_r: 0.1, avg_r: 0.1, profit_factor: 1.1, total_pnl: 10 }] as never,
      [['bullish', 'Long'], ['bearish', 'Short']],
      20,
    );
    expect(rows).toEqual([
      { label: 'Long', value: 53.3, n: 30, withheld: false },
      { label: 'Short', value: null, n: 0, withheld: true },
    ]);
  });
});
```

- [ ] **Step 2: Write the failing exit-quality spec**

Create `frontend/src/app/workspaces/analytics/sections/exit-quality.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ExitQualitySectionComponent } from './exit-quality';

const BASE = {
  hold_by_outcome: { n_winners: 1, n_losers: 1, ratio: null },
  efficiency: { bins: [], n: 0, median: null },
  mae: { bins: [], n: 0, median: null },
  scatter: [],
  coverage: {},
  min_cell_n: 20,
};

function render(data: object) {
  const f = TestBed.createComponent(ExitQualitySectionComponent);
  f.componentRef.setInput('data', data);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('Exit quality — unmapped reasons (v89 spec §3.5)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('warns and names the strings when "other" is over a fifth of exits', () => {
    const el = render({
      ...BASE,
      exit_reasons: [{ reason: 'stop', n: 10 }, { reason: 'other', n: 90 }],
      unmapped_reasons: [{ status: 'win', text: 'take profit reached', n: 60 }, { status: 'loss', text: '', n: 30 }],
    });
    const warning = el.querySelector('.unmapped')!;
    expect(warning.textContent).toContain('90%');
    expect(warning.textContent).toContain('take profit reached');
    expect(warning.textContent).toContain('(no reason recorded)');
  });

  it('stays quiet when "other" is a small share', () => {
    const el = render({ ...BASE, exit_reasons: [{ reason: 'stop', n: 90 }, { reason: 'other', n: 10 }], unmapped_reasons: [] });
    expect(el.querySelector('.unmapped')).toBeNull();
  });
});
```

- [ ] **Step 3: Update the existing specs to the new contract (failing)**

`frontend/src/app/stores/analytics.snapshot.spec.ts:295-296`: replace the two `expect(...)` lines with:

```ts
    expect(store.directionBars()).toEqual([
      { label: 'Long', value: 66.7, n: 6, withheld: false },
      { label: 'Short', value: null, n: 0, withheld: true },
    ]);
    expect(store.dowBars().map((row) => row.label)).toEqual(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']);
```

This fixture's floor is 0, so the old test expected Short (n=0) to be withheld; `zeroFilledBars` keeps that behaviour, because `rateOrWithheld` withholds when the rate is null.

`frontend/src/app/workspaces/analytics/analytics.spec.ts`: replace the `bar()` helper (~line 502) with

```ts
function bar(el: HTMLElement, key: string): HTMLElement {
  const panel = [...el.querySelectorAll<HTMLElement>('sb-panel')].find((p) => p.textContent?.includes('By horizon'));
  const found = [...(panel?.querySelectorAll<HTMLElement>('sb-bar-list li') ?? [])]
    .find((r) => r.querySelector('.label')?.textContent?.trim() === key);
  if (!found) throw new Error(`no horizon bar for ${key}`);
  return found;
}
```

and change `'renders the horizon bars diverging around zero'`'s assertion to

```ts
    expect(bar(el, '2w').querySelector('.fill')!.getAttribute('data-tone')).toBe('neg');
```

The other two horizon tests (`'labels each horizon bar…'` expecting `'40'`, and `'drives both panels from one toggle'` expecting `'90'`) keep working against `li.textContent`.

`frontend/src/app/workspaces/analytics/analytics.columns.spec.ts`: append

```ts
describe('win rate below the sample floor (v89)', () => {
  it('shows an em dash, not "n=17", in a win-rate column', () => {
    const column = breakdownColumns('Ticker', 20).find((c) => c.key === 'win_rate')!;
    expect(column.value!({ key: 'AXON', n: 17, wins: 8, losses: 9, win_rate: 47.1 } as never)).toBe('—');
  });
});
```

(Import `breakdownColumns` from `./analytics.columns` if the file does not already.)

- [ ] **Step 4: Run to verify they fail**

- `npm --prefix frontend test -- --include src/app/stores/analytics.bars.spec.ts` → FAIL (no exports)
- `npm --prefix frontend test -- --include src/app/workspaces/analytics/sections/exit-quality.spec.ts` → FAIL (no `.unmapped`)
- `npm --prefix frontend test -- --include src/app/stores/analytics.snapshot.spec.ts` → FAIL
- `npm --prefix frontend test -- --include src/app/workspaces/analytics/analytics.spec.ts` → FAIL (no `sb-bar-list`)
- `npm --prefix frontend test -- --include src/app/workspaces/analytics/analytics.columns.spec.ts` → FAIL (`n=17`)

- [ ] **Step 5: Models**

`frontend/src/app/api/models.ts`:
- In `AnalyticsPerformance`, after `expectancy_r: number | null;` add:

```ts
  /** v89: samples for the two all-time figures above. */
  win_rate_n: number;
  expectancy_n: number;
```

- Change `calendar: { month: string; return_pct: number; n: number }[];` to

```ts
  /** v89: account return per month -- realised P&L over the balance the month
   *  opened with. `pnl` is that P&L; `return_pct` is null for a non-positive
   *  opening balance. */
  calendar: { month: string; return_pct: number | null; pnl: number; n: number }[];
```

- In `AnalyticsExitQuality`, after `exit_reasons: unknown[];` add:

```ts
  /** v89: raw close-reason texts filed under "other", most frequent first. */
  unmapped_reasons: { status: string; text: string; n: number }[];
```

- [ ] **Step 6: Store**

`frontend/src/app/stores/analytics.store.ts`:
- Import `BarRow` from `'../ui/bar-list'`, and `HoldingBucket` from the models import if it is not already there.
- Replace `zeroFilledHistogram` with:

```ts
/** A segment's win rates in a fixed order, zero-filled, n kept OUT of the
 *  label (v89): the bar list prints n in its own column, and a label reading
 *  "Saturday (n=3 — below 20, rate withheld)" wrapped across six lines. */
export function zeroFilledBars(rows: BreakdownRow[], order: readonly (readonly [string, string])[], floor: number): BarRow[] {
  const byKey = new Map(rows.map((row) => [row.key, row]));
  return order.map(([key, label]) => {
    const row = byKey.get(key);
    const n = row?.n ?? 0;
    const value = rateOrWithheld(n, row?.win_rate, floor);
    return { label, value: value.withheld ? null : value.count, n, withheld: value.withheld };
  });
}

/** Holding-period and planned-R:R buckets: a win rate per bucket. */
export function rateBars(buckets: readonly HoldingBucket[]): BarRow[] {
  return buckets.map((b) => ({ label: b.bucket, value: b.win_rate, n: b.n, withheld: b.win_rate === null }));
}

/** Account return per month, signed. v89: this fed sb-histogram under labels
 *  like "2026-07", which never start with "-", so every month drew green. */
export function monthBars(rows: readonly { month: string; return_pct: number | null; n: number }[]): BarRow[] {
  return rows.map((m) => ({ label: m.month, value: m.return_pct, n: m.n }));
}
```

- In `withComputed`:
  - Replace `holdingPeriodHistogram` and `riskRewardHistogram` with `holdingPeriodBars: computed<BarRow[]>(() => rateBars(performance()?.holding_period_split ?? []))` and `riskRewardBars: computed<BarRow[]>(() => rateBars(performance()?.risk_reward_split ?? []))`.
  - Replace `monthHistogram` (and its incorrect doc comment) with `monthBars: computed<BarRow[]>(() => monthBars(performance()?.calendar ?? []))`.
  - Replace `directionHistogram`/`dowHistogram` with `directionBars`/`dowBars`, calling `zeroFilledBars` with the same arguments.
  - After `expectancyR: computed(…)` add `winRateN: computed(() => performance()?.win_rate_n ?? null),` and `expectancyN: computed(() => performance()?.expectancy_n ?? null),`.
- In `DERIVED_METRICS`, change `label: 'Volatility (ann)'` to `label: 'Volatility (per trade, ann.)'`. It is still computed from per-trade price returns (spec §3.4).
- Run `git grep -n "Histogram()" -- frontend/src/app`. Nothing may still read the five deleted computeds except the `sb-histogram` call sites that stay (`returnsHistogram`, `rHistogram`, `rMultipleBins`, `decileHistogram`, `funnelChart`, `badgeChart`, `tierChart`).

- [ ] **Step 7: Columns**

`frontend/src/app/workspaces/analytics/analytics.columns.ts`: in `TIER_COLUMNS` (line 111), change `` `n=${r.n}` `` to `ABSENT`. In `breakdownColumns` (line 127), change `` `n=${r.n ?? 0}` `` to `ABSENT`. Add a one-line comment on each: `// v89: the Trades column carries n; a win-rate column holds a rate or nothing.`

- [ ] **Step 8: Exit quality**

`frontend/src/app/workspaces/analytics/sections/exit-quality.ts`:
- In the template, directly after `<p class="coverage">{{coverageText()}}</p>`, insert:

```html
@if(otherShare()>20){<div class="unmapped" role="note"><p>{{otherShare().toFixed(0)}}% of exits have a close reason the buckets do not recognise, so the reason mix below is mostly unclassified. Most frequent:</p><ul>@for(r of unmappedReasons();track r.status+r.text){<li>“{{r.text||'(no reason recorded)'}}” · {{r.status}} · ×{{r.n}}</li>}</ul></div>}
```

- Append to `styles`: `.unmapped{color:var(--warn);font-size:var(--text-table)}.unmapped p{color:var(--warn);font-size:var(--text-table);margin:0 0 var(--space-4)}.unmapped ul{margin:0;padding-left:var(--space-14)}`
- Add to the class:

```ts
  /** v89: share of exits in the "other" bucket; over 20% the donut is mostly
   *  a grey ring and says so in words instead. */
  protected readonly otherShare=computed(()=>{const rows=(this.data()?.exit_reasons??[]) as {reason:string;n:number}[];const total=rows.reduce((s,r)=>s+(r.n??0),0);const other=rows.find((r)=>r.reason==='other')?.n??0;return total?other/total*100:0;});
  protected readonly unmappedReasons=computed(()=>this.data()?.unmapped_reasons??[]);
```

- [ ] **Step 9: Analytics template — bar lists, Overall N, journal**

`frontend/src/app/workspaces/analytics/analytics.ts`:
- Imports:
  - Add `import { BarList, BarRow } from '../../ui/bar-list';` and `import { InlineMd } from '../../ui/inline-md';`, and add `BarList` and `InlineMd` to the component `imports` array.
  - Remove `Magnitude` from both places once nothing else uses it: `git grep -n "sb-magnitude" -- frontend/src/app/workspaces/analytics` must return only this task's deleted line.
  - Keep `pct` or `rate` imports as needed. `rate` comes from `./analytics.columns` (already exported). Add `pct` to the `../../ui/format` import.
- **By horizon** — replace the whole `<div class="horizon-bars"> … </div>` block with:

```html
              <sb-bar-list [rows]="horizonBars()" [format]="measureFormat()" />
```

and add to the class, replacing `horizonMax`:

```ts
  /** v89: signed bars around a centre zero. sb-magnitude is one-sided, which
   *  anchored losses at the right edge and drew the one gain as a dot on the left. */
  protected readonly horizonBars = computed<BarRow[]>(() =>
    this.store.horizonAgg().map((row) => ({ label: row.key, value: this.measureValue(row), n: row.n })));

  protected readonly measureFormat = computed(() => {
    const totals = this.measure() === 'total_r';
    return (value: number) => (totals ? rMultiple(value) : expectancy(value));
  });
```

  Delete the styles `.horizon-bars`, `.horizon-row`, `.horizon-key`, `.horizon-value`, `.horizon-row.neg .horizon-value`, `.horizon-n`.
- **Breakdowns** — replace the four `sb-histogram` call sites:

```html
            <sb-panel heading="By holding period">
              <sb-bar-list mode="rate" [rows]="store.holdingPeriodBars()" [format]="fmtRate" [reference]="store.derived().win_rate" />
            </sb-panel>

            <sb-panel heading="By month">
              @if (store.monthBars().length) {
                <sb-bar-list [rows]="store.monthBars()" [format]="fmtMonth" />
              } @else {
                <p class="stale">No months with closed trades.</p>
              }
            </sb-panel>
```
```html
            <sb-panel heading="By planned R:R">
              <sb-bar-list mode="rate" [rows]="store.riskRewardBars()" [format]="fmtRate" [reference]="store.derived().win_rate" />
            </sb-panel>
```
```html
            <sb-panel heading="By direction">
              <sb-bar-list mode="rate" [rows]="store.directionBars()" [format]="fmtRate" [reference]="store.winRate()" [withheldFloor]="store.minCellN()" />
            </sb-panel>
            <sb-panel heading="By day of week">
              <sb-bar-list mode="rate" [rows]="store.dowBars()" [format]="fmtRate" [reference]="store.winRate()" [withheldFloor]="store.minCellN()" />
            </sb-panel>
```

  Add to the class, beside `fmtRate`: `protected readonly fmtMonth = (value: number) => pct(value, 2);`
- **Overall** — change the two `dd`s to:

```html
                <div><dt>Win rate</dt><dd class="num">{{ fmtRate(store.winRate()) }} <span class="n">N={{ store.winRateN() ?? '—' }}</span></dd></div>
                <div>
                  <dt>Expectancy</dt>
                  <dd class="num">{{ fmtExpectancy(store.expectancyR()) }} <span class="n">N={{ store.expectancyN() ?? '—' }}</span></dd>
                </div>
```

  Add style: `dd .n { color: var(--text-faint); font-size: var(--text-chip); }`
- **Journal** — change `<li>{{ line }}</li>` to `<li><sb-inline-md [text]="line" /></li>`, and `<li>{{ lesson }}</li>` to `<li><sb-inline-md [text]="lesson" /></li>`.

- [ ] **Step 10: Analytics spacing**

In `analytics.ts` styles:
- Replace the comment and rule `sb-section-head { margin-bottom: var(--space-14); }` with:

```css
    /* v89: the page is one stack. Every @case body sits directly on this
       grid, and --section-gap is the only space between panels (spec §4.2). */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: var(--section-gap); }
```

- `sb-panel { display: block; margin-top: var(--space-14); }` → `sb-panel { display: block; }`
- `.section { margin: var(--space-20) 0 var(--space-10); …` → `margin: 0;`. Delete `.section:first-of-type { margin-top: 0; }`.
- `.alert { margin-top: var(--space-14); …` → delete that declaration.
- `.panels { … gap: var(--space-14); align-items: start; }` → `gap: var(--section-gap);`
- `.chart-grid { … gap: var(--space-14); }` → `gap: var(--section-gap); align-items: start;`
- `.kpi-row { … gap: var(--space-14); margin-bottom: var(--space-14); }` → `gap: var(--space-10);` and no margin.
- `.breakdowns { margin: var(--space-14) 0; }` → delete the rule. Delete `.breakdowns > * + * { margin-top: var(--space-14); }` and its comment.

In the template, wrap in `<div class="sb-stack">` … `</div>`:
- Inside `<details class="breakdowns" …>`: everything after `<summary>Breakdowns</summary>`, up to `</details>`.
- The content of every `<sb-async>` that holds more than one child element or `@if` block that renders one. These are:
  - The Record/Overall `sb-async` (the `@if (store.missingRelocated()…)` alert plus `.panels`).
  - The Breakdowns distributions `sb-async` (the `.chart-grid`s, `h2.section`, Streaks).
  - The Strategies tab `sb-async` (registry, heatmap, contribution).
  - The Calibration tab `sb-async`.
  - The Plans tab `sb-async` (funnel, `.panels`, `.chart-grid`).

  Open each wrapper right after the opening tag's `>` and close it right before `</sb-async>`.

`frontend/src/app/ui/spacing.spec.ts`: delete the six `app/workspaces/analytics/analytics.ts|…` entries.

Check the style budget: `npm --prefix frontend run build -- --configuration production` must not report `anyComponentStyle` over 8 kB for `analytics.ts`. If it does, the deleted horizon rules were not all removed.

- [ ] **Step 11: Run to verify everything passes**

Run the five specs from Step 4, plus:
- `npm --prefix frontend test -- --include src/app/stores/analytics.store.spec.ts`
- `npm --prefix frontend test -- --include src/app/ui/spacing.spec.ts`
- `npm --prefix frontend test -- --include src/app/workspaces/workspace-gaps.spec.ts`

Expected: PASS for all.

- [ ] **Step 12: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.bars.spec.ts frontend/src/app/stores/analytics.snapshot.spec.ts frontend/src/app/workspaces/analytics frontend/src/app/ui/spacing.spec.ts
git commit -m "fix(v89): analytics draws signed months and rates as bar lists, shows N, renders the journal, flags unmapped exits, stacks by the section gap"
```
