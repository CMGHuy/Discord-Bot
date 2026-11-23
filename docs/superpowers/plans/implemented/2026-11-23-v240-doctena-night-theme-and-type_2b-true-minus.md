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

V240-12b and V240-12c (added 2026-11-23, Decision 10 widened) carry the
same rule to the thirteen local signed formatters outside `format.ts`
that a hand-built `'+'`/`MINUS` scan found: they route each through a
`format.ts` helper (`rMultiple`, `pct`, `signed`, `fixed`) or, where the
magnitude's own format must stay byte-identical, through `signFor` (made
public by V240-12b) and the new loss-only `lossSign`. Both run after
V240-11; V240-12c after V240-12b.

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


### Task V240-12b: No signed zero I: `signFor` public, `lossSign`; partials `rText`, runner-endings, calendar `cellValue`, benchmark, trade-detail cohort tooltip
**Model:** sonnet — six files each with a pinned spec to move, two exported helpers other tasks consume; no design judgement.

**Files:**
- Modify: `frontend/src/app/ui/format.ts` (`signFor`, added private by V240-11 after `fixed`)
- Modify: `frontend/src/app/ui/format.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/tabs/partials.ts` (import line 13, `rText` lines 44–45)
- Modify: `frontend/src/app/workspaces/analytics/tabs/partials.spec.ts` (`describe('rText', …)`, line 190)
- Modify: `frontend/src/app/workspaces/analytics/tabs/runner-endings.ts` (import line 6, `signedR`/`plainR` lines 55–58)
- Modify: `frontend/src/app/workspaces/analytics/tabs/runner-endings.spec.ts`
- Modify: `frontend/src/app/workspaces/calendar/calendar.helpers.ts` (import line 14, `plusOrMinus` lines 24–25, `cellValue` lines 45–52)
- Modify: `frontend/src/app/workspaces/calendar/calendar.helpers.spec.ts` (lines 70–80)
- Modify: `frontend/src/app/workspaces/analytics/tabs/benchmark.ts` (import line 11, `signedPct` lines 41–45, local `money` lines 100–102)
- Modify: `frontend/src/app/workspaces/analytics/tabs/benchmark.spec.ts`
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (import line 26, `cohortTooltip` line 815)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (`describe('TradeDetail — the cohort risk chip (v86 C8)', …)`)

**Interfaces:**
- Consumes (V240-11): `fixed(value, decimals)`, the private
  `signFor(value, magnitude)`, and `pct`/`rMultiple`/`signed` printing an
  unsigned zero for a value that rounds to zero.
- Produces (V240-12c consumes both):
  `export function signFor(value: number, magnitude: string): string` —
  `'+'` on a gain, `MINUS` on a loss, `''` on zero, and `''` whenever
  `magnitude` holds no non-zero digit.
  `export function lossSign(value: number, magnitude: string): string` —
  `MINUS` for a loss whose `magnitude` holds a non-zero digit, otherwise
  `''` (never a `+`): for sites that print a loss signed and a gain bare.

Why: index Decision 10 (partner, 2026-11-23) — no figure anywhere prints a
signed zero. These five files build their own sign: `partials.ts` `rText`,
`runner-endings.ts` `signedR` and the calendar cell print `+0.00R` (and
`+0`) for an exact zero; every one of them, plus `runner-endings.ts`
`plainR`, `benchmark.ts` `signedPct`/`money` and the trade-detail cohort
tooltip, prints `+0.00` or `−0.00` for a value that rounds to zero. Each
site's text is already what a `format.ts` helper prints (`rMultiple`,
`pct`, `signed`, `fixed`) except `benchmark.ts`'s money, whose currency
sits between sign and digits, so it takes `lossSign`. Only the text moves;
a cell's tone (`pos`/`neg`) is unchanged.

- [ ] **Step 1: Write the failing helper tests**

In `frontend/src/app/ui/format.spec.ts`, add `lossSign` and `signFor` to
the import from `'./format'` (alphabetical: `lossSign` after `held`,
`signFor` after `signed`). Append at the end of the file:

```ts
/* v240 V240-12b: signFor and lossSign are the sign rule the local
 * formatters outside format.ts share (index Decision 10). */
describe('v240: signFor and lossSign', () => {
  it('signFor signs a printed magnitude only when it holds a non-zero digit', () => {
    expect(signFor(1.2, '1.20')).toBe('+');
    expect(signFor(-1.2, '1.20')).toBe(MINUS);
    expect(signFor(-0.004, '0.00')).toBe('');
    expect(signFor(0.004, '0.00')).toBe('');
    expect(signFor(0, '0')).toBe('');
    expect(signFor(-0, '0.00')).toBe('');
    expect(signFor(-0.001, '<0.01')).toBe(MINUS);
  });

  it('lossSign puts a true minus on a visible loss and nothing else', () => {
    expect(lossSign(-1.2, '1.20')).toBe(MINUS);
    expect(lossSign(-1234.5, '1,234.50')).toBe(MINUS);
    expect(lossSign(1.2, '1.20')).toBe('');
    expect(lossSign(-0.004, '0.00')).toBe('');
    expect(lossSign(-0.4, '0 $')).toBe('');
    expect(lossSign(0, '0.00')).toBe('');
    expect(lossSign(-0, '0.00')).toBe('');
  });
});
```

- [ ] **Step 2: Write the failing site tests**

`frontend/src/app/workspaces/analytics/tabs/partials.spec.ts`, in
`describe('rText', …)`: replace `expect(rText(0)).toBe('+0.00R');`
(line 190) with:

```ts
    // v240 Decision 10: a zero, or a value that rounds to zero, has no sign.
    expect(rText(0)).toBe('0.00R');
    expect(rText(-0.004)).toBe('0.00R');
    expect(rText(0.004)).toBe('0.00R');
```

`frontend/src/app/workspaces/analytics/tabs/runner-endings.spec.ts`,
inside `describe('runner endings helpers', …)`, directly after the test
`it('lays out the scorecard: four endings summing to 100%, then the set-apart Giveback row', …)`:

```ts
  it('prints a zero or rounded-away R unsigned (v240 Decision 10)', () => {
    const row = { ...BLOCK.rows[0], avg_r: 0, median_r: -0.004, total_r: 0.004, gave_back: -0.004 };
    const cells = scorecardRows({ ...BLOCK, rows: [row] })[0].cells;
    expect(cells.slice(0, 3)).toEqual(['0.00R', '0.00R', '0.00R']);
    expect(cells[6]).toBe('0.00R');
    const loss = scorecardRows({ ...BLOCK, rows: [{ ...row, avg_r: -0.3, gave_back: -0.3 }] })[0].cells;
    expect([loss[0], loss[6]]).toEqual(['−0.30R', '−0.30R']);
  });
```

`frontend/src/app/workspaces/calendar/calendar.helpers.spec.ts`: replace
the test
`it('signs a losing day with the true minus; zero and a gain keep the plus', …)`
(lines 70–80) with:

```ts
  it('signs a losing day with the true minus and a gain with a plus; a zero has no sign (v240 Decision 10)', () => {
    const loss = { ...DAY, net_r: -0.6, net_pnl_amount: -1234 };
    expect(cellValue(loss, 'r').text).toBe('−0.60R');
    expect(cellValue(loss, 'currency').text).toBe('−1,234');
    expect(cellValue(loss, 'r').text).not.toContain('-');
    expect(cellValue(loss, 'currency').text).not.toContain('-');
    const flat = { ...DAY, net_r: 0, net_pnl_amount: 0 };
    expect(cellValue(flat, 'r').text).toBe('0.00R');
    expect(cellValue(flat, 'currency').text).toBe('0');
    const tiny = { ...DAY, net_r: -0.004, net_pnl_amount: -0.4 };
    expect(cellValue(tiny, 'r').text).toBe('0.00R');
    expect(cellValue(tiny, 'currency').text).toBe('0');
    expect(cellValue({ ...DAY, net_r: 0.004, net_pnl_amount: 0.4 }, 'r').text).toBe('0.00R');
    expect(cellValue(DAY, 'currency').text).toBe('+480');
  });
```

`frontend/src/app/workspaces/analytics/tabs/benchmark.spec.ts`: in the
`signedPct` test (lines 29–30), directly after its `.toEqual([...]);` add:

```ts
    // v240 Decision 10: a value that rounds to zero prints unsigned.
    expect([signedPct(-0.004), signedPct(0.004), signedPct(-0.04, 1)]).toEqual(['0.00%', '0.00%', '0.0%']);
```

and append at the end of the file:

```ts
describe('benchmark drawdowns that round to zero (v240 Decision 10)', () => {
  it('prints the money and percentage drawdown unsigned', () => {
    const account = BENCHMARK_FIXTURE.stats['bot_account']!;
    const p = {
      ...BENCHMARK_FIXTURE,
      stats: {
        ...BENCHMARK_FIXTURE.stats,
        bot_account: { ...account, money_dd: { value: -0.004, n: 4, reason: null }, max_dd_pct: { value: -0.004, n: 4, reason: null } },
      },
    };
    const tiles = statGroups(p, new Set(['bot_account']), '$')[0].tiles;
    const value = (label: string) => tiles.find((t) => t.label === label)!.value;
    expect(value('Drawdown ($)')).toBe('$0.00');
    expect(value('Max drawdown')).toBe('0.00%');
  });
});
```

(`statGroups` and `BENCHMARK_FIXTURE` are already imported by the file;
the existing `'−$41.50'` pin stays.)

`frontend/src/app/workspaces/trades/trade-detail.spec.ts`, inside
`describe('TradeDetail — the cohort risk chip (v86 C8)', …)`, directly
after `it('renders a danger-toned chip for COHORT_POOR', …)`:

```ts
  it('prints a zero cohort expectancy unsigned (v240 Decision 10)', () => {
    const el = renderHeader('COHORT_POOR', {
      win_rate: 50, expectancy_r: 0, n_live: 10, n_backtest: 40, run_date: '2026-09-14',
    });
    const hint = el.querySelector('.tags > sb-chip + sb-hint [role="tooltip"]')!.textContent!;
    expect(hint).toContain('50.0% WR / 0.00R');
    expect(hint).not.toContain('+0.00R');
  });

  it('prints a rounded-away cohort loss unsigned (v240 Decision 10)', () => {
    const el = renderHeader('COHORT_POOR', {
      win_rate: 50, expectancy_r: -0.004, n_live: 10, n_backtest: 40, run_date: '2026-09-14',
    });
    const hint = el.querySelector('.tags > sb-chip + sb-hint [role="tooltip"]')!.textContent!;
    expect(hint).toContain('50.0% WR / 0.00R');
    expect(hint).not.toContain('−0.00R');
  });
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/format.spec.ts --include src/app/workspaces/analytics/tabs/partials.spec.ts --include src/app/workspaces/analytics/tabs/runner-endings.spec.ts --include src/app/workspaces/calendar/calendar.helpers.spec.ts --include src/app/workspaces/analytics/tabs/benchmark.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts`
Expected: FAIL — `format.spec.ts` does not compile (`signFor` is not
exported, `lossSign` does not exist); `rText(0)` is `'+0.00R'`; the
runner-endings cells read `'+0.00R'`/`'−0.00R'`; the flat calendar cell
reads `'+0.00R'` and `'+0'`; `signedPct(0.004)` is `'+0.00%'`; the
drawdown tile reads `'−$0.00'`; the cohort hint reads `'+0.00R'` and
`'−0.00R'`.

- [ ] **Step 4: Export `signFor` and add `lossSign`**

In `frontend/src/app/ui/format.ts`, change V240-11's
`function signFor(value: number, magnitude: string): string {` to
`export function signFor(value: number, magnitude: string): string {`
(its doc comment and body stay), and directly after it add:

```ts
/** The sign for a figure that shows a loss signed and a gain bare (a
 *  drawdown, an expectancy, a plain number): a true minus on a loss whose
 *  printed magnitude holds a non-zero digit, nothing otherwise -- so a loss
 *  that rounds away prints an unsigned zero (v240, index Decision 10). */
export function lossSign(value: number, magnitude: string): string {
  return value < 0 ? signFor(value, magnitude) : '';
}
```

- [ ] **Step 5: Route the five sites through `format.ts`**

`frontend/src/app/workspaces/analytics/tabs/partials.ts`: change line 13
`import { MINUS } from '../../../ui/format';` to
`import { rMultiple } from '../../../ui/format';` and replace `rText`
(lines 44–45) with:

```ts
/** Signed R to two places, the shared `rMultiple`: no sign on a zero or a
 *  value that rounds to zero (v240, index Decision 10). */
export const rText = (v: number | null): string => rMultiple(v);
```

`frontend/src/app/workspaces/analytics/tabs/runner-endings.ts`: change
line 6 to `import { ABSENT, fixed, rMultiple } from '../../../ui/format';`
and replace `signedR` and `plainR` (lines 55–58) with:

```ts
/** v240 Decision 10: the shared rules, so a zero or a value that rounds to
 *  zero prints unsigned. `signedR` signs both ways (`rMultiple`); `plainR`
 *  signs only a loss (`fixed`). `rMultiple(null)` is ABSENT. */
const signedR = (v: number | null): string => rMultiple(v);
const plainR = (v: number | null): string => (v === null ? ABSENT : `${fixed(v, 2)}R`);
```

`frontend/src/app/workspaces/calendar/calendar.helpers.ts`: change line 14
to `import { rMultiple, signed } from '../../ui/format';`, delete
`plusOrMinus` and its comment (lines 24–25), and in `cellValue` replace
the two returns after `if (value === null) …`:

```ts
  if (metric === 'r') return {
    value, text: rMultiple(value),
    tone: value > 0 ? 'pos' : value < 0 ? 'neg' : 'neutral',
  };
  return {
    value, text: signed(value, 0),
    tone: value > 0 ? 'pos' : value < 0 ? 'neg' : 'neutral',
  };
```

(`signed` groups like `num`, so `+480` and `−1,234` are unchanged; a zero
or a value that rounds away prints `0.00R` / `0`.)

`frontend/src/app/workspaces/analytics/tabs/benchmark.ts`: change line 11
to `import { lossSign, num, pct as formatPct } from '../../../ui/format';`
(aliased: the file destructures a `pct` field at line 389). Replace
`signedPct` (lines 41–45) with:

```ts
export function signedPct(value: number | null, dp = 2): string {
  // v240 Decision 10: format.ts's `pct`, so a value that rounds to zero
  // prints unsigned; `pct(null)` is the em dash this always returned.
  return formatPct(value, dp);
}
```

and the local `money` (lines 100–102) with:

```ts
function money(value: number, currency: string): string {
  const magnitude = num(Math.abs(value), 2);
  return `${lossSign(value, magnitude)}${currency}${magnitude}`;
}
```

`frontend/src/app/workspaces/trades/trade-detail.ts`: change line 26
`import { MINUS } from '../../ui/format';` to
`import { rMultiple } from '../../ui/format';` and in `cohortTooltip`
replace line 815 with:

```ts
      `${rMultiple(expectancyR)} (n=${n}, frozen ${runDate})`
```

- [ ] **Step 6: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/format.spec.ts --include src/app/workspaces/analytics/tabs/partials.spec.ts --include src/app/workspaces/analytics/tabs/runner-endings.spec.ts --include src/app/workspaces/calendar/calendar.helpers.spec.ts --include src/app/workspaces/calendar/calendar.spec.ts --include src/app/workspaces/analytics/tabs/benchmark.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts`
Expected: PASS. (`calendar.spec.ts` renders `cellValue` and carries no
`+0` pin at b00e9859; it runs here as the consumer.)

Then confirm no hand-built sign is left in these five files:
`cd frontend && git grep -n "MINUS\|'+'" -- src/app/workspaces/analytics/tabs/partials.ts src/app/workspaces/analytics/tabs/runner-endings.ts src/app/workspaces/calendar/calendar.helpers.ts src/app/workspaces/analytics/tabs/benchmark.ts src/app/workspaces/trades/trade-detail.ts`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/format.ts frontend/src/app/ui/format.spec.ts \
  frontend/src/app/workspaces/analytics/tabs/partials.ts frontend/src/app/workspaces/analytics/tabs/partials.spec.ts \
  frontend/src/app/workspaces/analytics/tabs/runner-endings.ts frontend/src/app/workspaces/analytics/tabs/runner-endings.spec.ts \
  frontend/src/app/workspaces/calendar/calendar.helpers.ts frontend/src/app/workspaces/calendar/calendar.helpers.spec.ts \
  frontend/src/app/workspaces/analytics/tabs/benchmark.ts frontend/src/app/workspaces/analytics/tabs/benchmark.spec.ts \
  frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts
git commit -m "fix(v240): no signed zero in partials, runner endings, calendar cells, benchmark tiles and the cohort tooltip -- signFor public, lossSign

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V240-12c: No signed zero II: override-fidelity model, live activity, equity drawdown, trading-performance figure, risk drawdown R, `riskUnits`
**Model:** sonnet — six small formatter swaps across model, component and shared files, each with a spec to extend; two go through mounted components.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.ts` (import line 4, local `MINUS`/`sign` lines 40–43, `magnitude` lines 46–48, `fixed2` lines 50–52, `signedUsd` lines 57–59, `signedR` lines 61–63)
- Modify: `frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts`
- Modify: `frontend/src/app/shell/live/live-activity-section.ts` (import line 4, `signOf` lines 22–25, `pnlParts` lines 27–34)
- Modify: `frontend/src/app/shell/live/live-activity-section.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.ts` (import line 4, `drawdownPart` line 181)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` (import line 17, `fmtFigure` lines 374–379)
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (import line 23, `fmtDrawdownR` lines 1019–1023)
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts`
- Modify: `frontend/src/app/ui/risk-units.ts` (import line 1, `riskUnits` body lines 25–31)
- Modify: `frontend/src/app/ui/risk-units.spec.ts`

**Interfaces:**
- Consumes: `signFor(value, magnitude)` and `lossSign(value, magnitude)`
  (V240-12b, exported from `ui/format.ts`); `fixed(value, decimals)`
  (V240-11); `signed(value, decimals)` with V240-11's unsigned zero.
- Produces: none.

Why: index Decision 10 — no figure anywhere prints a signed zero. These six
sites build a sign by hand and print `+0.00`/`−0.00` (or `−0 $`) for a
value that rounds to zero: the override-fidelity model's `sign` (behind
`fixed2`, `signedUsd`, `signedR`), the live activity R (`+0.0R`), the
equity-range drawdown (`−0.00%`), the trading-performance expectancy
(`−0.00R`), the Risk page's R drawdown (`−0.00R`) and `riskUnits`'s money
part (`−0 $`). Where a `format.ts` helper prints the same text (`fixed`,
`signed`), the site calls it; where the magnitude's own format must stay
byte-identical (currency in front, one decimal, a space before `R`), it
keeps its magnitude and takes the sign from `signFor`/`lossSign`. Only
the text moves; tones are unchanged.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts`,
inside `describe('override-fidelity model', …)`, directly after the test
that pins `signedUsd(59.35, '$')` (line 23):

```ts
  it('prints a delta that rounds to zero unsigned (v240 Decision 10)', () => {
    expect(signedUsd(-0.004, '$')).toBe('$0.00');
    expect(signedUsd(0.004, '€')).toBe('€0.00');
    expect(signedR(-0.004)).toBe('0.00 R');
    expect(signedR(0.004)).toBe('0.00 R');
    expect(signedR(0.006)).toBe('+0.01 R');
    expect(recordedLine({ ...VERDICT_RECORDED_COST, mean_delta_r: -0.004 })).toContain('mean 0.00 R per override');
  });
```

(`recordedLine` and `VERDICT_RECORDED_COST`, a recorded verdict, are
already imported.)

`frontend/src/app/shell/live/live-activity-section.spec.ts`, directly after
`it('signs a loss with a true minus and keeps the amount unsigned', …)`:

```ts
  it('prints an R that rounds to zero unsigned (v240 Decision 10)', () => {
    expect(pnlParts({ r: -0.04, amount: -3 }, '€')!.r).toBe('0.0R');
    expect(pnlParts({ r: 0.04, amount: 3 }, '€')!.r).toBe('0.0R');
    expect(pnlParts({ r: 0, amount: 0 }, '€')!.r).toBe('0.0R');
    expect(pnlParts({ r: 0.05, amount: 3 }, '€')!.r).toBe('+0.1R');
  });
```

`frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`,
directly after `it('shows drawdown as a loss whichever sign the stats carry', …)`:

```ts
  it('prints a drawdown that rounds to zero unsigned (v240 Decision 10)', () => {
    const parts = rangeReadoutParts(
      { change: 0, changePct: 0, high: 1, low: 1, maxDrawdownPct: 0.004 }, '€');
    expect(parts[3].text).toBe(`${RANGE_LABELS.drawdown} 0.00%`);
  });
```

`frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`,
in `describe('trading performance panel', …)`, directly after the test
whose body asserts `expect(text).toContain('−0.16R');` (line 184):

```ts
  it('prints an expectancy that rounds to zero unsigned (v240 Decision 10)', () => {
    const el = render({
      winRate: 49.1, winRateN: 12, expectancyR: -0.004, payoffRatio: 2.34,
      todayRealized: TODAY_BLOCK, currency: '€',
    });
    const text = el.querySelector('.mobile-summary')!.textContent ?? '';
    expect(text).toContain('0.00R');
    expect(text).not.toContain('−0.00R');
  });
```

`frontend/src/app/workspaces/risk/risk.spec.ts`, inside
`describe('Risk metric basis and money drawdown (v194 B8)', …)`, directly
after `it('shows the money drawdown under the R figure, negative, in the account currency', …)`:

```ts
  it('prints an R drawdown that rounds to zero unsigned, a real one with a true minus (v240 Decision 10)', async () => {
    const tiny = await renderWithMetrics({ max_drawdown_r: { value: 0.004, n: 782 } });
    const tinyText = tileHost(tiny, RISK_DRAWDOWN_LABEL).querySelector('.value')!.textContent!;
    expect(tinyText).toContain('0.00R');
    expect(tinyText).not.toMatch(/[−-]0\.00R/);
    const real = await renderWithMetrics();
    expect(tileHost(real, RISK_DRAWDOWN_LABEL).querySelector('.value')!.textContent!).toContain('−8.40R');
  });
```

`frontend/src/app/ui/risk-units.spec.ts`, inside `describe('riskUnits', …)`,
directly after
`it('puts one true minus on each part of a negative figure (headroom past the cap)', …)`:

```ts
  it('prints a money part that rounds to zero unsigned (v240 Decision 10)', () => {
    expect(riskUnits(-0.001, 10_000, '$')).toBe(`0 $ · ${MINUS}<0.01%`);
    expect(riskUnits(-1.42, 100_000, '$')).toBe(`${MINUS}1,420 $ · ${MINUS}1.42%`);
  });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts --include src/app/shell/live/live-activity-section.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/ui/risk-units.spec.ts`
Expected: FAIL — `signedUsd(-0.004, '$')` is `'−$0.00'`, `signedR(0.004)`
is `'+0.00 R'`, the recorded line reads `mean −0.00 R`; `pnlParts` gives
`'−0.0R'`/`'+0.0R'`; the drawdown reads `−0.00%`; the summary holds
`'−0.00R'`; the Risk tile holds `'−0.00R'`; `riskUnits` gives
`'−0 $ · −<0.01%'`. (Each "real loss" line already passes.)

- [ ] **Step 3: Implement**

`frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.ts`:
change line 4 to `import { num, signFor } from '../../../ui/format';`,
delete the local `const MINUS = '−';` (line 40), `const sign = …` (line
43) and `function magnitude` (lines 46–48), then replace `fixed2`,
`signedUsd` and `signedR` with:

```ts
/** A signed figure from a magnitude already formatted: `signFor` gives '+'
 *  on a gain, a true minus on a loss and nothing on a zero or a value that
 *  rounds to zero (v240, index Decision 10). */
const signedText = (x: number, magnitude: string): string => `${signFor(x, magnitude)}${magnitude}`;

function fixed2(x: number | null): string {
  return known(x) ? signedText(x, Math.abs(x).toFixed(2)) : '—';
}

export function signedUsd(x: number | null, currency: string): string {
  if (!known(x)) return '—';
  const digits = num(Math.abs(x), 2);
  return `${signFor(x, digits)}${currency}${digits}`;
}

export function signedR(x: number | null): string {
  return known(x) ? `${signedText(x, Math.abs(x).toFixed(2))} R` : '—';
}
```

(`plural` and `be`, between them today, stay where they are.)

`frontend/src/app/shell/live/live-activity-section.ts`: change line 4 to
`import { amount, signFor, timeInZone } from '../../ui/format';`, delete
`signOf` (lines 22–25) and replace `pnlParts`'s body with:

```ts
  if (pnl === null) return null;
  // v240 Decision 10: an R that rounds to zero at one decimal prints unsigned.
  const r = Math.abs(pnl.r).toFixed(1);
  return {
    r: `${signFor(pnl.r, r)}${r}R`,
    amount: pnl.amount === null ? null : amount(Math.abs(pnl.amount), currency, 0),
  };
```

`frontend/src/app/workspaces/dashboard/panels/equity-candles.model.ts`:
change line 4 to `import { money, num, pct, signed } from '../../../ui/format';`
and replace line 181 (with the `v195 §1.1` comment above it) with:

```ts
  // v195 §1.1 / v240 Decision 10: `signed` keeps num's Intl rounding, signs
  // the loss with a true minus, and prints a drawdown that rounds away as 0.00.
  return { text: `${RANGE_LABELS.drawdown} ${signed(loss)}%`, tone: drawdownTone(pctValue) };
```

`frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`:
change line 17 to `import { amount, fixed, pct } from '../../../ui/format';`
and replace `fmtFigure`'s last two lines with:

```ts
    // v195 §1.1 / v240 Decision 10: a true minus on a loss, none on a gain
    // or on a value that rounds to zero (`fixed`).
    return `${fixed(value, decimals)}${unit}`;
```

`frontend/src/app/workspaces/risk/risk.ts`: add `signed` to the line 23
import (after `shareCount`) and replace `fmtDrawdownR`'s return with:

```ts
    // v240 Decision 10: `signed` on the negated magnitude -- a true minus,
    // and no sign on a drawdown that rounds to 0.00.
    return value === null ? '—' : `${signed(-Math.abs(value), 2)}R`;
```

`frontend/src/app/ui/risk-units.ts`: change its import to
`import { ABSENT, MINUS, amount, lossSign, riskPct } from './format';`, and replace the `money` constant (the three lines from
`const money = isFiniteNumber(balance)`) with:

```ts
  // v240 Decision 10: the money part rounds to whole units, so a sliver of
  // headroom past the cap can print "0 $" -- unsigned, never "−0 $". The
  // percentage part is never a zero (riskPct floors at "<0.01%").
  const cash = isFiniteNumber(balance) ? amount((magnitude / 100) * balance, unit, 0) : null;
  const money = cash === null ? ABSENT : `${lossSign(pct, cash)}${cash}`;
```

(the `return` line is unchanged).

- [ ] **Step 4: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts --include src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts --include src/app/shell/live/live-activity-section.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/ui/risk-units.spec.ts`
Expected: PASS. (`override-fidelity-panel.spec.ts` renders the model's
text and runs here as its consumer.)

Then confirm no hand-built sign is left at the thirteen Decision 10 sites
(this task's six and V240-12b's five files):
`cd frontend && git grep -n "MINUS :\|? '+'\|'−'" -- src/app/workspaces/analytics/tabs/override-fidelity.model.ts src/app/shell/live/live-activity-section.ts src/app/workspaces/dashboard/panels/equity-candles.model.ts src/app/workspaces/dashboard/panels/trading-performance.ts src/app/workspaces/risk/risk.ts src/app/ui/risk-units.ts`
Expected: only `risk-units.ts`'s `const sign = pct < 0 ? MINUS : '';`
(the percentage part, which never prints a zero).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.ts \
  frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts \
  frontend/src/app/shell/live/live-activity-section.ts frontend/src/app/shell/live/live-activity-section.spec.ts \
  frontend/src/app/workspaces/dashboard/panels/equity-candles.model.ts \
  frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts \
  frontend/src/app/workspaces/dashboard/panels/trading-performance.ts \
  frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts \
  frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts \
  frontend/src/app/ui/risk-units.ts frontend/src/app/ui/risk-units.spec.ts
git commit -m "fix(v240): no signed zero in the override-fidelity text, live activity R, equity and Risk drawdowns, the expectancy figure and riskUnits

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
