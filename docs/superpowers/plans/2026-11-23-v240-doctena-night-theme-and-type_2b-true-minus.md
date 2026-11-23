# v240 — Doctena night, plan 1 of 5: Theme and type — Part 2b: the true minus

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V240-11" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) (§1 "Every loss carries a true minus", §11; its `### Corrections from the plan 1 code brief` section wins over the text above it)
**Index:** [2026-11-23-v240-doctena-night-theme-and-type_0-index.md](2026-11-23-v240-doctena-night-theme-and-type_0-index.md) holds the Goal, Global Constraints, the "Decisions this index fixes", `## Parallelisation` and the task ledger. Every task below implicitly includes the index's Global Constraints.

Part 2 would have passed the 1500-line cap, so its last two tasks live
here, unchanged in id and contract: V240-11 (`fixed()`, four sites and the
unsigned zero in the four signed helpers) and
V240-12 (three more sites, consuming `fixed()`). V240-11 may run in
parallel with V240-10 (index `## Parallelisation`); V240-12 runs after
V240-11. Conventions:

- Frontend commands run from `frontend/`:
  `cd frontend && npx ng test --watch=false --include <spec> [--include <spec>]`.
  A 60s `Timeout waiting for worker` is machine load: re-run once.
- No task runs the full suite (CI does). Commits are scoped; stage only the
  files the task names.

Scope note for both tasks: spec §1 names seven sites that can print an
ASCII hyphen on a loss; these two tasks fix exactly those. The existing
signed helpers (`pct`, `money`, `rMultiple`, `signed`) already print U+2212.
The new `fixed()` prints no sign on a value that rounds to zero (index
Decision 9), and by partner decision (2026-11-23, index Decision 10) that
zero rule extends to every formatter: V240-11 also teaches the four signed
helpers to print an unsigned zero (`pct(-0.004)` is `0.00%`, never
`−0.00%` or `+0.00%`) and moves the pins that assert today's signed zero
(`format.spec.ts`, `status-cell.spec.ts`).

# Phase 6: The true minus

### Task V240-11: True minus I: `fixed()`, `riskPct`, no signed zero in `pct`/`money`/`rMultiple`/`signed`, `metric-card`, `metric-chip`, `plan-cell` `formatR`

**Model:** sonnet — a new shared formatter, an app-wide change to the four signed helpers and four call sites, each with tests; it sets the contract V240-12 consumes.

**Files:**
- Modify: `frontend/src/app/ui/format.ts` (new `fixed` after `signOf`, ~line 25; `riskPct`, lines 77–86; new private `signFor` after `fixed`; `pct` lines 30–36, `money` lines 94–99, `rMultiple` lines 111–114, `signed` lines 210–213, before Step 3's insertion shifts them)
- Modify: `frontend/src/app/ui/format.spec.ts` (import line 3; `riskPct` describe ~lines 175–178; the `prints no hyphen-minus from any signed helper` loop, ~line 225; two new describes at the end)
- Modify: `frontend/src/app/ui/status-cell.spec.ts` (line 75: the `−0.0%` pin of a best P&L of −0.04 becomes `0.0%`)
- Modify: `frontend/src/app/ui/metric-card.ts` (import; `format`, line 159)
- Modify: `frontend/src/app/ui/metric-card.spec.ts` (new describe at the end)
- Modify: `frontend/src/app/ui/metric-chip.ts` (import; `format`, line 76)
- Create: `frontend/src/app/ui/metric-chip.spec.ts`
- Modify: `frontend/src/app/ui/plan-cell.ts` (import line 5; `formatR`, line 353)
- Modify: `frontend/src/app/ui/plan-cell.spec.ts` (one test after `shows an em dash for unavailable trail R values`, ~line 288)

**Interfaces:**
- Consumes: `MINUS` (`frontend/src/app/ui/format.ts:16`), `ABSENT`,
  private `grouped(value, decimals)` (same file).
- Produces: `export function fixed(value: number, decimals: number): string`
  in `frontend/src/app/ui/format.ts`. A loss prints `MINUS` +
  `Math.abs(value).toFixed(decimals)`; a gain or zero prints no sign; a
  value that rounds to zero at `decimals` prints an unsigned zero
  (`fixed(-0.004, 2)` is `'0.00'`). No grouping (it replaces `toFixed`
  one for one). V240-12 consumes it.
- Produces (behaviour, app-wide): `pct`, `money`, `rMultiple` and `signed`
  print no sign when the formatted magnitude holds no non-zero digit
  (`pct(-0.004)` → `'0.00%'`, `money(0.004, '€')` → `'0.00 €'`,
  `rMultiple(-0.004)` → `'0.00R'`, `signed(-0.04, 1)` → `'0.0'`). A value
  that survives the rounding keeps `+`/`MINUS` as today. Private helper
  `signFor(value: number, magnitude: string): string` in `format.ts`.

Why: spec §1: every loss carries a true minus (U+2212), so a loss never
reads by hue alone. These four sites format with `toFixed` or a literal
`'-'`, which prints an ASCII hyphen-minus. Index Decision 9: one shared
`fixed(value, decimals)` for the plain-number sites, printing no `+` on
gains (those sites never printed one) and never `−0.00`. `riskPct` keeps
its own shape (grouped, `<0.01%`) and only swaps its hyphen for `MINUS`.
The `metric-card`/`metric-chip` format function also runs on every
count-up frame, so an animating negative figure carries the true minus
too. `metric-chip.spec.ts` does not exist yet (the ledger said Modify), so
this task creates it.

Index Decision 10 (partner, 2026-11-23): a value that rounds to zero prints
unsigned app-wide, not only in `fixed()`, `formatFigureText` and the tape.
Today `pct(-0.004)` prints `−0.00%` and `pct(0.004)` prints `+0.00%`: a
sign on a figure that reads as zero claims a loss or gain the reader cannot
see. The four signed helpers share `signOf`, so one private `signFor`
(sign only when the printed magnitude has a non-zero digit) fixes all four.
It tests the formatted text, not the number, so it agrees with whatever
rounding `toFixed` or `toLocaleString` applied.
`git grep -n "−0\.0\|-0\.0\|+0\.0" frontend/src` finds one other pin
of a signed zero from these helpers: `status-cell.spec.ts:75`
(`pct(-0.04, 1)` → `'−0.0%'`). The grep's other hits are data values,
letter-spacing, or local formatters outside `format.ts` (`partials.ts`
`rText`, `calendar.helpers.ts` `cellValue`), which print `+0.00R` for an
exact zero and are not in this task.

- [ ] **Step 1: Write the failing `fixed` and `riskPct` tests**

In `frontend/src/app/ui/format.spec.ts`, change line 3 to:

```ts
import { MINUS, amount, fixed, held, money, pct, quantity, rMultiple, riskPct, shareCount, signed, timeInZone } from './format';
```

Replace the test `it('keeps the sign of a negative value, tiny or not', …)`
in the `riskPct` describe with:

```ts
  it('keeps the sign of a negative value, tiny or not, as a true minus (v240 §1)', () => {
    expect(riskPct(-1.234)).toBe('−1.23%');
    expect(riskPct(-0.002)).toBe('−<0.01%');
    expect(riskPct(-1234.5)).toBe('−1,234.50%');
    expect(riskPct(-1.234)).not.toContain('-');
  });
```

Append at the end of the file:

```ts
/* v240 §1 (index Decision 9): the plain-number sites (metric cards and
 * chips, R labels, chart tooltips) print a true minus on a loss, no plus on
 * a gain, and no sign on a value that rounds to zero. */
describe('fixed (v240: a true minus on plain numbers)', () => {
  it('prints a loss with U+2212 and keeps the decimals', () => {
    expect(fixed(-2.5, 2)).toBe('−2.50');
    expect(fixed(-0.26, 1)).toBe('−0.3');
    expect(fixed(-1234.567, 0)).toBe('−1235');
    expect(fixed(-2.5, 2)).not.toContain('-');
  });

  it('prints a gain and zero without a sign', () => {
    expect(fixed(2.5, 2)).toBe('2.50');
    expect(fixed(0, 2)).toBe('0.00');
    expect(fixed(-0, 2)).toBe('0.00');
  });

  it('never prints a signed zero for a loss that rounds away', () => {
    expect(fixed(-0.004, 2)).toBe('0.00');
    expect(fixed(-0.04, 1)).toBe('0.0');
    expect(fixed(-0.4, 0)).toBe('0');
    expect(fixed(-0.005, 2)).toBe('−0.01');
  });

  it('does not group thousands, like the toFixed it replaces', () => {
    expect(fixed(12345.6, 1)).toBe('12345.6');
    expect(fixed(-12345.6, 1)).toBe(`${MINUS}12345.6`);
  });
});
```

(`(0.005).toFixed(2)` is `'0.01'` in V8, so `fixed(-0.005, 2)` is a real
loss and keeps its sign. If that line fails on a different engine, the
rounding of `toFixed` moved, not `fixed`: replace `-0.005` with `-0.006`.)

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/format.spec.ts`
Expected: FAIL — `fixed` is not exported; `riskPct(-1.234)` is `'-1.23%'`.

- [ ] **Step 3: Add `fixed` and fix `riskPct`**

In `frontend/src/app/ui/format.ts`, directly after `signOf` (after line
24) add:

```ts
/** A plain number at fixed decimals, with a true minus on a loss (spec
 *  v240 §1): the drop-in for `value.toFixed(decimals)` wherever a loss can
 *  appear. No `+` on a gain (the sites it replaces never printed one) and
 *  no grouping. A loss that rounds to zero at these decimals prints an
 *  unsigned zero, never "−0.00", because a zero has no sign. */
export function fixed(value: number, decimals: number): string {
  const magnitude = Math.abs(value).toFixed(decimals);
  return value < 0 && Number(magnitude) !== 0 ? `${MINUS}${magnitude}` : magnitude;
}
```

Replace `riskPct` (lines 77–86, doc comment included) with:

```ts
/** v194 B5: the one percentage formatter for portfolio heat, per-position
 *  risk and their totals. Unsigned like `share` (a budget is a level, not a
 *  movement); a negative keeps its sign, as a true minus (v240 §1). A
 *  non-zero value under 0.01 renders "<0.01%": at two decimals it printed
 *  "0.00%", claiming no risk where there is some. An exact zero (or -0) is
 *  "0.00%". */
export function riskPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return ABSENT;
  if (value === 0) return '0.00%';
  const sign = value < 0 ? MINUS : '';
  if (Math.abs(value) < 0.01) return `${sign}<0.01%`;
  return `${sign}${grouped(Math.abs(value), 2)}%`;
}
```

- [ ] **Step 4: Run the format spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/format.spec.ts --include src/app/ui/risk-units.spec.ts`
Expected: PASS. (`risk-units.ts` calls `riskPct` on a magnitude, never a
negative, so its spec does not move. If `risk-units.spec.ts` does not
exist, drop that `--include`.)

- [ ] **Step 5: Write the failing unsigned-zero tests for the signed helpers**

In `frontend/src/app/ui/format.spec.ts`, in the test
`it('prints no hyphen-minus from any signed helper', …)` change the loop's
values from `[-0.004, -1, -2.5, -1234.567]` to:

```ts
    for (const value of [-1, -2.5, -1234.567]) {
```

(`-0.004` rounds to zero at every decimals that loop uses, so it now
prints unsigned and moves to the describe below.)

Append at the end of the file:

```ts
/* v240 (index Decision 10, partner 2026-11-23): a value that rounds to zero
 * prints unsigned in every signed helper, as in fixed(): never "−0.00" or
 * "+0.00", because a zero has no sign. */
describe('v240: no signed zero from any signed helper', () => {
  it('prints a loss that rounds to zero unsigned', () => {
    expect(pct(-0.004)).toBe('0.00%');
    expect(pct(-0.4, 0)).toBe('0%');
    expect(money(-0.004, '€')).toBe('0.00 €');
    expect(money(-0.4, '$', 0)).toBe('0 $');
    expect(rMultiple(-0.004)).toBe('0.00R');
    expect(signed(-0.004)).toBe('0.00');
    expect(signed(-0.04, 1)).toBe('0.0');
  });

  it('prints a gain that rounds to zero unsigned', () => {
    expect(pct(0.004)).toBe('0.00%');
    expect(money(0.004, '€')).toBe('0.00 €');
    expect(rMultiple(0.004)).toBe('0.00R');
    expect(signed(0.004)).toBe('0.00');
  });

  it('keeps the sign on the smallest value that does not round away', () => {
    expect(pct(-0.006)).toBe('−0.01%');
    expect(money(-0.006, '€')).toBe('−0.01 €');
    expect(rMultiple(0.006)).toBe('+0.01R');
    expect(signed(-0.006)).toBe('−0.01');
    expect(money(-1234567.891, '$')).toBe('−1,234,567.89 $');
  });

  it('prints no sign at all on any rounded-away value', () => {
    for (const value of [-0.004, 0.004, -0, 0]) {
      for (const text of [pct(value), pct(value, 0), money(value, '$'), money(value, '€', 0), rMultiple(value), signed(value)]) {
        expect(text, `${value} -> ${text}`).not.toMatch(/^[+−-]/);
      }
    }
  });
});
```

In `frontend/src/app/ui/status-cell.spec.ts`, in the test
`it('signs a negative trailing stop and best P&L with the true minus; zero and positive unchanged', …)`,
replace line 75 with:

```ts
    // v240 Decision 10: a best P&L of −0.04 rounds to zero at one decimal,
    // so it prints unsigned.
    expect(neg.querySelector('.end.pos')!.textContent).toBe('0.0%');
```

- [ ] **Step 6: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/format.spec.ts --include src/app/ui/status-cell.spec.ts`
Expected: FAIL — `pct(-0.004)` is `'−0.00%'`, `pct(0.004)` is `'+0.00%'`,
`signed(-0.004)` is `'−0.00'`, and the status cell prints `'−0.0%'`.

- [ ] **Step 7: Add `signFor` and route the four helpers through it**

In `frontend/src/app/ui/format.ts`, directly after `fixed` (Step 3) add:

```ts
/** The sign for a magnitude already formatted: `signOf`, except none when
 *  the printed text holds no non-zero digit. A value that rounds to zero
 *  prints unsigned ("0.00", never "−0.00" or "+0.00"), because a zero has
 *  no sign (v240, index Decision 10). Testing the text, not the number,
 *  keeps it in step with whatever rounding toFixed or toLocaleString did. */
function signFor(value: number, magnitude: string): string {
  return /[1-9]/.test(magnitude) ? signOf(value) : '';
}
```

Replace the body of `pct` with:

```ts
  if (value === null || value === undefined) return ABSENT;
  const magnitude = Math.abs(value).toFixed(decimals);
  return `${signFor(value, magnitude)}${magnitude}%`;
```

Replace the body of `money` with (its v195 comment stays):

```ts
  if (value === null || value === undefined) return ABSENT;
  // v195 correction 5: the sign is ours (a true minus) and the magnitude is
  // toLocaleString's -- which would otherwise print a hyphen-minus itself.
  const magnitude = grouped(Math.abs(value), decimals);
  return `${signFor(value, magnitude)}${magnitude} ${unit}`;
```

Replace the body of `rMultiple` with:

```ts
  if (value === null || value === undefined) return ABSENT;
  const magnitude = Math.abs(value).toFixed(2);
  return `${signFor(value, magnitude)}${magnitude}R`;
```

Replace the body of `signed` with:

```ts
  if (typeof value !== 'number' || !Number.isFinite(value)) return ABSENT;
  const magnitude = num(Math.abs(value), decimals);
  return `${signFor(value, magnitude)}${magnitude}`;
```

`signOf` keeps its doc comment and is now called only by `signFor`.

- [ ] **Step 8: Run the format and status-cell specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/format.spec.ts --include src/app/ui/status-cell.spec.ts`
Expected: PASS.

Then confirm no other spec pins a signed zero from these helpers:
`git grep -n "−0\.0\|-0\.0\|+0\.0" -- "frontend/src/*.spec.ts"`
Expected: only data values, `letter-spacing`, and the two local
formatters named above (`partials.spec.ts:190`,
`calendar.helpers.spec.ts:77-78`); no `'−0.0…'` text pin left.

- [ ] **Step 9: Write the failing site tests**

Append to `frontend/src/app/ui/metric-card.spec.ts`:

```ts
/* v240 §1: a negative figure carries a true minus, never a hyphen. */
describe('sb-metric-card true minus (v240)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function valueText(inputs: Record<string, unknown>): string {
    const f = TestBed.createComponent(MetricCard);
    f.componentRef.setInput('label', 'Figure');
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return (f.nativeElement as HTMLElement).querySelector('.value')!.textContent!.trim();
  }

  it('prints a loss with U+2212 and its unit', () => {
    expect(valueText({ value: -2.5, decimals: 2, unit: 'R' })).toBe('−2.50R');
    expect(valueText({ value: -12, decimals: 0, unit: '%' })).toBe('−12%');
  });

  it('prints a gain and a rounded-away loss unsigned', () => {
    expect(valueText({ value: 2.5, decimals: 2, unit: 'R' })).toBe('2.50R');
    expect(valueText({ value: -0.004, decimals: 2, unit: '' })).toBe('0.00');
  });
});
```

Create `frontend/src/app/ui/metric-chip.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { MetricChip } from './metric-chip';

/* v240 §1: the chip's figure carries a true minus on a loss, the same
 * fixed() rule as sb-metric-card. */
describe('sb-metric-chip', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(inputs: Record<string, unknown>): HTMLElement {
    const f = TestBed.createComponent(MetricChip);
    f.componentRef.setInput('label', 'ExpR');
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  const valueText = (host: HTMLElement) => host.querySelector('.value')!.textContent!.trim();

  it('prints a loss with U+2212, never a hyphen', () => {
    const text = valueText(render({ value: -0.42, decimals: 2, unit: 'R' }));
    expect(text).toBe('−0.42R');
    expect(text).not.toContain('-');
  });

  it('prints a gain unsigned and a rounded-away loss as an unsigned zero', () => {
    expect(valueText(render({ value: 0.42, decimals: 2, unit: 'R' }))).toBe('0.42R');
    expect(valueText(render({ value: -0.004, decimals: 2, unit: 'R' }))).toBe('0.00R');
  });

  it('shows the label', () => {
    expect(render({ value: 1 }).querySelector('.label')!.textContent!.trim()).toBe('ExpR');
  });
});
```

In `frontend/src/app/ui/plan-cell.spec.ts`, directly after the test
`it('shows an em dash for unavailable trail R values', …)` add:

```ts
  it('prints a negative trail R with a true minus (v240 §1)', () => {
    const f = TestBed.createComponent(PlanCell);
    f.componentRef.setInput('entry', 121.0);
    f.componentRef.setInput('target', null);
    f.componentRef.setInput('stop', 113.33);
    f.componentRef.setInput('stopKind', 'trailing');
    f.componentRef.setInput('targetIsBankedTp1', true);
    f.componentRef.setInput('floorR', 1.33);
    f.componentRef.setInput('priceR', 0.9);
    f.componentRef.setInput('headroomR', -0.43);
    f.detectChanges();
    const title = f.nativeElement.querySelector('[title]').getAttribute('title');
    expect(title).toContain('floor 1.3R · price 0.9R · headroom −0.4R');
    expect(title).not.toContain('-0.4R');
  });
```

- [ ] **Step 10: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/metric-card.spec.ts --include src/app/ui/metric-chip.spec.ts --include src/app/ui/plan-cell.spec.ts`
Expected: FAIL — `'-2.50R'` (hyphen) where `'−2.50R'` is expected,
`'-0.00'` for the rounded-away loss, and `headroom -0.4R` in the plan cell.

- [ ] **Step 11: Point the three sites at `fixed`**

`frontend/src/app/ui/metric-card.ts`: add `import { fixed } from './format';`
directly above `import { Hint } from './hint';`, and change line 159 to:

```ts
    return (value: number) => `${fixed(value, decimals)}${unit}`;
```

`frontend/src/app/ui/metric-chip.ts`: add `import { fixed } from './format';`
above `import { MetricTone } from './metric-card';`, and change line 76 to:

```ts
    return (value: number) => `${fixed(value, decimals)}${unit}`;
```

`frontend/src/app/ui/plan-cell.ts`: change line 5 to
`import { fixed, money, num, pct, rMultiple, share } from './format';` and
line 353 to:

```ts
const formatR = (value: number | null): string => value === null ? '—' : `${fixed(value, 1)}R`;
```

- [ ] **Step 12: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/format.spec.ts --include src/app/ui/status-cell.spec.ts --include src/app/ui/metric-card.spec.ts --include src/app/ui/metric-chip.spec.ts --include src/app/ui/plan-cell.spec.ts`
Expected: PASS.

Then confirm the sites carry no `toFixed` left:
`cd frontend && git grep -n "toFixed" -- src/app/ui/metric-card.ts src/app/ui/metric-chip.ts src/app/ui/plan-cell.ts`
Expected: no `toFixed(decimals)` in metric-card/metric-chip and no
`toFixed(1)}R` in plan-cell. (Other `toFixed` calls in plan-cell that
format unsigned levels stay.)

- [ ] **Step 13: Commit**

```bash
git add frontend/src/app/ui/format.ts frontend/src/app/ui/format.spec.ts \
  frontend/src/app/ui/status-cell.spec.ts \
  frontend/src/app/ui/metric-card.ts frontend/src/app/ui/metric-card.spec.ts \
  frontend/src/app/ui/metric-chip.ts frontend/src/app/ui/metric-chip.spec.ts \
  frontend/src/app/ui/plan-cell.ts frontend/src/app/ui/plan-cell.spec.ts
git commit -m "fix(v240): a true minus on plain numbers and no signed zero -- fixed() and signFor() in format.ts; riskPct, metric card and chip, plan-cell R labels

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V240-12: True minus II: `figure-text` count-up, `attribution.ts`, `tape.ts` `signed`

**Model:** sonnet — three formatter sites outside `format.ts`, each with a negative-value test and one pinned string that changes.

**Files:**
- Modify: `frontend/src/app/ui/motion/figure-text.ts` (import; `formatFigureText`, lines 39–46)
- Modify: `frontend/src/app/ui/motion/figure-text.spec.ts` (`round-trips every shape…`, line 31; a new test)
- Modify: `frontend/src/app/workspaces/analytics/tabs/attribution.ts` (import line 10; `rFormat`/`heatFormat`/`measureFormat`, lines 187–198)
- Modify: `frontend/src/app/workspaces/analytics/tabs/attribution.spec.ts` (import; two tests at the end of `AttributionTab hint and tooltip copy (A4 audit)`)
- Modify: `frontend/src/app/shell/tape/tape.ts` (import line 14; `signed`, line 32)
- Modify: `frontend/src/app/shell/tape/tape.spec.ts` (`carries the headline numbers in its title`, line 173; one new test after `summarises a reading with no numbers as n/a`)

**Interfaces:**
- Consumes: `fixed(value: number, decimals: number): string` and `MINUS`
  from `frontend/src/app/ui/format.ts` (V240-11; `MINUS` exists, line 16).
- Produces: `export const rLabel: (v: number) => string` and
  `export const rateLabel: (v: number) => string` in
  `frontend/src/app/workspaces/analytics/tabs/attribution.ts` (module-level,
  test-visible; no later task consumes them).

Why: spec §1 lists these three as the last sites that can print an ASCII
hyphen on a loss, each to get a test with a negative value.

- `figure-text.ts`: `StatTile` counts a pre-formatted figure up by parsing
  it into prefix, number and suffix (`parseFigureText`) and re-printing
  each frame with `toLocaleString`. A page that hands it `-$12.50` keeps
  the hyphen at rest and while counting, and a negative frame value would
  print `toLocaleString`'s hyphen. The fix prints a leading hyphen-minus in
  the prefix as `MINUS`, and a negative value as `MINUS` + its magnitude
  (unsigned when it rounds to zero, as `fixed` does). The old round-trip
  case `-$12.50` now comes back as `−$12.50`, so it moves to its own test.
- `attribution.ts`: the waterfall, dot plot, bar lists and heat-grid
  tooltips print ExpR with `toFixed(2)R` and win rate with `toFixed(1)%`,
  so a negative ExpR shows `-0.25R`. Two module-level labels on `fixed`
  replace the four lambdas; gains stay unsigned, as before.
- `tape.ts`: the shock badge's title prints SPY/QQQ ATR moves and the VIX
  change with a local `signed` that writes a hyphen on a fall and `+0.00`
  on a flat reading. It now writes `+` on a rise, a true minus on a fall
  and no sign on zero (or a move that rounds to zero).

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/motion/figure-text.spec.ts`, replace the
`round-trips every shape a stat tile is given` test with:

```ts
  it('round-trips every shape a stat tile is given', () => {
    for (const text of ['68%', '+1.23R', '+$1,240', '1.80', '12 / 20', '−0.42R', '1,234,567.8 €']) {
      const parts = parseFigureText(text)!;
      expect(formatFigureText(parts, parts.value)).toBe(text);
    }
  });

  it('prints a loss with a true minus, at rest and while counting (v240 §1)', () => {
    const hyphenated = parseFigureText('-$12.50')!;
    expect(formatFigureText(hyphenated, hyphenated.value)).toBe('−$12.50');
    expect(formatFigureText(hyphenated, 6.25)).toBe('−$6.25');
    const plain = parseFigureText('12.5R')!;
    expect(formatFigureText(plain, -3.2)).toBe('−3.2R');
    expect(formatFigureText(plain, -0.04)).toBe('0.0R');
    const grouped = parseFigureText('1,240 €')!;
    expect(formatFigureText(grouped, -1240)).toBe('−1,240 €');
    for (const text of [formatFigureText(hyphenated, 3), formatFigureText(plain, -3.2)]) {
      expect(text).not.toContain('-');
    }
  });
```

In `frontend/src/app/workspaces/analytics/tabs/attribution.spec.ts`, add
`rLabel, rateLabel` to the import on line 11, so it reads
`import { AttributionTab, TAKEN_CAPTION, rLabel, rateLabel } from './attribution';`, and append
inside `describe('AttributionTab hint and tooltip copy (A4 audit)', …)`:

```ts
  it('labels a negative ExpR and rate with a true minus, a gain unsigned (v240 §1)', () => {
    expect(rLabel(-0.25)).toBe('−0.25R');
    expect(rLabel(0.25)).toBe('0.25R');
    expect(rLabel(-0.001)).toBe('0.00R');
    expect(rateLabel(-1.25)).toBe('−1.3%');
    expect(rateLabel(55)).toBe('55.0%');
  });

  it('Contribution tooltip prints a losing strategy with a true minus', async () => {
    const { fixture } = render({ strategies: signal({ contribution: [{ strategy: 'RSI', total_r: -2.5, n: 30 }],
      cumulative: {}, strategies: [], scope: {}, n: 30 }) });
    const text = await tooltipText(fixture, 'sb-waterfall rect.hit');
    expect(text).toContain('−2.50R');
    expect(text).not.toContain('-2.50R');
  });
```

(`rateLabel(-1.25)`: `(1.25).toFixed(1)` is `'1.3'` in V8, since 1.25 is
exact in binary and rounds half up.)

In `frontend/src/app/shell/tape/tape.spec.ts`, change the expected title
in `it('carries the headline numbers in its title', …)` to:

```ts
      'Market state SHOCK since 14:45 UTC · breadth 42% · sectors 5/8 · SPY −1.80 ATR · QQQ −2.30 ATR · VIX 21.13 (+27.2%)');
```

and directly after `it('summarises a reading with no numbers as n/a', …)`
add:

```ts
  it('signs a fall with a true minus and a flat reading with none (v240 §1)', () => {
    const text = shockSummary({ ...shockState, spy_atr_move: 0, qqq_atr_move: -0.004, vix_chg_pct: -3.4 });
    expect(text).toContain('SPY 0.00 ATR · QQQ 0.00 ATR · VIX 21.13 (−3.4%)');
    expect(text).not.toMatch(/-\d/);
  });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/motion/figure-text.spec.ts --include src/app/workspaces/analytics/tabs/attribution.spec.ts --include src/app/shell/tape/tape.spec.ts`
Expected: FAIL — `-$12.50` comes back with its hyphen; `rLabel` is not
exported; the tooltip shows `-2.50R`; the title shows `SPY -1.80 ATR`; the
flat reading shows `+0.00` and the fall `-3.4%`.

- [ ] **Step 3: Fix `formatFigureText`**

In `frontend/src/app/ui/motion/figure-text.ts`, add at the top of the file
(above the opening `/**` doc comment):

```ts
import { MINUS } from '../format';
```

and replace `formatFigureText` with:

```ts
/** A leading hyphen-minus in the prefix (a page that formatted its own
 *  loss) is printed as the true minus (spec v240 §1). */
const LEADING_HYPHEN = /^(\s*)-/;

export function formatFigureText(parts: FigureText, value: number): string {
  const body = Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: parts.decimals,
    maximumFractionDigits: parts.decimals,
    useGrouping: parts.grouped,
  });
  // A negative frame keeps a true minus; one that rounds to zero has no sign.
  const sign = value < 0 && Number(body.replaceAll(',', '')) !== 0 ? MINUS : '';
  return `${parts.prefix.replace(LEADING_HYPHEN, `$1${MINUS}`)}${sign}${body}${parts.suffix}`;
}
```

Update the file's header comment: replace
`` * it the suffix. `formatFigureText(parts, parts.value)` returns the original ``
/ `` * text exactly. `` with
`` * it the suffix. `formatFigureText(parts, parts.value)` returns the original ``
/ `` * text, except that a hyphen-minus sign comes back as U+2212 (v240 §1). ``

(`figure-text.ts` sits in `ui/motion/`; `format.ts` has no imports, so
the new import adds no cycle.)

- [ ] **Step 4: Fix the attribution labels**

In `frontend/src/app/workspaces/analytics/tabs/attribution.ts`, change
line 10 to `import { fixed, pct } from '../../../ui/format';`. Directly
above the `@Component(` decorator (line 55) add:

```ts
/** Chart and tooltip labels for ExpR and a rate, with a true minus on a
 *  loss (spec v240 §1, `fixed`) and no sign on a gain, as before. */
export const rLabel = (v: number): string => `${fixed(v, 2)}R`;
export const rateLabel = (v: number): string => `${fixed(v, 1)}%`;
```

Replace lines 187–198 (`rFormat` through `measureFormat`) with:

```ts
  protected readonly rFormat = rLabel;
  /** The cell figure with its unit, so the tooltip's "value" says what it is. */
  protected readonly heatFormat = computed<(v: number) => string>(() => {
    const which: HeatMeasure = this.store.heatCell();
    if (which === 'exp_r') return rLabel;
    return which === 'win_rate' ? rateLabel : (v: number) => String(Math.round(v));
  });

  protected readonly measureLabel = computed(
    () => this.measureOptions.find((o) => o.value === this.store.measure())?.label ?? 'ExpR');
  protected readonly measureFormat = computed<(v: number) => string>(
    () => (this.store.measure() === 'win_rate' ? rateLabel : rLabel));
```

(`pctFormat` and the lines after it are unchanged.)

- [ ] **Step 5: Fix the tape's `signed`**

In `frontend/src/app/shell/tape/tape.ts`, change line 14 to
`import { ABSENT, fixed, num, pct } from '../../ui/format';` and replace
line 32 (`const signed = …`) with:

```ts
/** A market move, signed both ways: '+' on a rise, a true minus on a fall
 *  (spec v240 §1, via `fixed`), no sign on a flat or rounded-away reading. */
const signed = (v: number, digits: number): string => {
  const text = fixed(v, digits);
  return v > 0 && Number(text) !== 0 ? `+${text}` : text;
};
```

- [ ] **Step 6: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/motion/figure-text.spec.ts --include src/app/ui/stat-tile.spec.ts --include src/app/workspaces/analytics/tabs/attribution.spec.ts --include src/app/shell/tape/tape.spec.ts`
Expected: PASS. (`stat-tile.spec.ts` is the count-up's consumer; none of
its figures is hyphen-signed.)

Then confirm no hyphen formatter is left at the seven spec §1 sites:
`cd frontend && git grep -n "toFixed" -- src/app/workspaces/analytics/tabs/attribution.ts src/app/shell/tape/tape.ts`
Expected: only `s.vix_level.toFixed(2)` in `tape.ts` (a level, never
negative); nothing in `attribution.ts`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/motion/figure-text.ts frontend/src/app/ui/motion/figure-text.spec.ts \
  frontend/src/app/workspaces/analytics/tabs/attribution.ts \
  frontend/src/app/workspaces/analytics/tabs/attribution.spec.ts \
  frontend/src/app/shell/tape/tape.ts frontend/src/app/shell/tape/tape.spec.ts
git commit -m "fix(v240): a true minus in the stat-tile count-up, attribution chart labels and the tape's shock title

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

