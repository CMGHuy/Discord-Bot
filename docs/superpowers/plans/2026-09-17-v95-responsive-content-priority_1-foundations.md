# v95 — Part 1: Foundations

Part of `2026-09-17-v95-responsive-content-priority`. Header block, goal,
global constraints, parallelisation map and exit criteria live in
`_0-index.md` — read that first.

# Phase A — Foundations

Nothing downstream is trustworthy until the breakpoints are honest and the
resolver exists. A1 gates the whole plan; A2/A3/A4 are independent of each
other; A5 and A6 follow.

---

### Task A1: `ui/priority.ts` — the resolver

**Files:**
- Create: `frontend/src/app/ui/priority.ts`
- Create: `frontend/src/app/ui/priority.spec.ts`

**Interfaces:**
- Consumes: `Viewport` and `BREAKPOINTS` from `frontend/src/app/ui/breakpoints.ts`.
- Produces:
  - `VIEWPORT_ORDER: readonly Viewport[]` — `['xs','sm','md','lg','xl']`.
  - `rankOf(viewport: Viewport): number`
  - `isInline(inlineFrom: Viewport | undefined, viewport: Viewport): boolean`
  - `type DemotionTarget = 'expansion' | 'sheet' | 'digest'`
  - `interface PriorityDecl { id: string; inlineFrom?: Viewport; demotesTo: DemotionTarget }`

  Every later task imports `isInline` and at least one of these types. B1 puts
  `inlineFrom` on `ColumnDef<T>`; B4 puts it on the toolbar's control
  descriptors; B6 puts it on the panel descriptors; E1 walks `PriorityDecl`.

- [x] **Step 1: Write the failing test**

Create `frontend/src/app/ui/priority.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { BREAKPOINTS, Viewport, viewportFor } from './breakpoints';
import { VIEWPORT_ORDER, isInline, rankOf } from './priority';

/* The resolver is pure for the same reason viewportFor is: an off-by-one in
 * the comparison is invisible until someone is at exactly one breakpoint and
 * a column vanishes that should not have. Test the boundaries, and test that
 * the order agrees with the breakpoints rather than restating them. */

describe('VIEWPORT_ORDER', () => {
  it('is every viewport, narrowest first', () => {
    expect(VIEWPORT_ORDER).toEqual(['xs', 'sm', 'md', 'lg', 'xl']);
  });

  it('agrees with viewportFor across the declared breakpoints', () => {
    // The order must be the order viewportFor actually produces as width
    // grows, or `isInline` compares against a scale the app does not use.
    const widths = [0, ...Object.values(BREAKPOINTS)];
    expect(widths.map(viewportFor)).toEqual([...VIEWPORT_ORDER]);
  });
});

describe('rankOf', () => {
  it('ranks ascending from xs', () => {
    expect(VIEWPORT_ORDER.map(rankOf)).toEqual([0, 1, 2, 3, 4]);
  });
});

describe('isInline', () => {
  it('treats an undeclared floor as always inline', () => {
    for (const viewport of VIEWPORT_ORDER) {
      expect(isInline(undefined, viewport)).toBe(true);
    }
  });

  it("inlineFrom 'xs' is inline everywhere", () => {
    for (const viewport of VIEWPORT_ORDER) {
      expect(isInline('xs', viewport)).toBe(true);
    }
  });

  it('is inline at its own floor and above, demoted below', () => {
    const cases: Array<[Viewport, Viewport, boolean]> = [
      ['md', 'xs', false],
      ['md', 'sm', false],
      ['md', 'md', true],
      ['md', 'lg', true],
      ['md', 'xl', true],
    ];
    for (const [floor, viewport, expected] of cases) {
      expect(isInline(floor, viewport)).toBe(expected);
    }
  });

  it('is inline at its own floor for every floor — the boundary case', () => {
    // A floor is inclusive. Reading it as exclusive hides every item at
    // exactly the width it was declared for.
    for (const floor of VIEWPORT_ORDER) {
      expect(isInline(floor, floor)).toBe(true);
    }
  });

  it("inlineFrom 'xl' is demoted at every width but xl", () => {
    expect(VIEWPORT_ORDER.map((v) => isInline('xl', v)))
      .toEqual([false, false, false, false, true]);
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/priority.spec.ts`
Expected: FAIL — `Failed to resolve import "./priority"`.

- [x] **Step 3: Write the implementation**

Create `frontend/src/app/ui/priority.ts`:

```ts
import { Viewport } from './breakpoints';

/**
 * Content priority — spec v95 §3.
 *
 * One field, `inlineFrom`, on every displayable thing: the NARROWEST viewport
 * at which it appears inline. Below that floor it is **demoted, never
 * removed** — every demoted item has a named destination (`DemotionTarget`),
 * and the parity gate asserts it is reachable through one.
 *
 * Deliberately not a numeric rank. Reusing `Viewport` means there is one
 * scale in the app rather than two that have to be kept in step, and it makes
 * a declaration readable on its own: `inlineFrom: 'md'` says where it appears,
 * not how important someone thought it was.
 *
 * Pure, so it tests without a browser — jsdom lays nothing out, so a test that
 * asserted on a resolved width here would be theatre.
 */

/** Every viewport, narrowest first. The order comparisons are made in. */
export const VIEWPORT_ORDER: readonly Viewport[] = ['xs', 'sm', 'md', 'lg', 'xl'] as const;

/** Position in `VIEWPORT_ORDER`. `-1` is unreachable for a typed `Viewport`. */
export function rankOf(viewport: Viewport): number {
  return VIEWPORT_ORDER.indexOf(viewport);
}

/**
 * Does this item render inline at this viewport?
 *
 * The floor is INCLUSIVE — `isInline('md', 'md')` is `true` — matching the
 * min-width semantics `BREAKPOINTS` already uses. An undeclared floor means
 * always inline, so adding `inlineFrom` to an existing type changes nothing
 * until a call site opts in.
 */
export function isInline(inlineFrom: Viewport | undefined, viewport: Viewport): boolean {
  if (inlineFrom === undefined) return true;
  return rankOf(viewport) >= rankOf(inlineFrom);
}

/** Where a demoted item goes. One per kind — spec v95 §4. */
export type DemotionTarget =
  /** A column, into the row's existing `expansion` template. */
  | 'expansion'
  /** A control, into its toolbar's filter sheet. */
  | 'sheet'
  /** A panel, into its own collapsed digest. */
  | 'digest';

/** What the parity gate (E1) walks. */
export interface PriorityDecl {
  /** Unique within its surface — a column key, a control name, a panel id. */
  id: string;
  inlineFrom?: Viewport;
  demotesTo: DemotionTarget;
}
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/priority.spec.ts`
Expected: PASS, all cases.

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/ui/priority.ts frontend/src/app/ui/priority.spec.ts
git commit -m "feat(v95): content-priority resolver -- inlineFrom, isInline, DemotionTarget"
```

---

### Task A2: Correct the shell's breakpoint drift

**Files:**
- Modify: `frontend/src/app/shell/shell.css:368-382`
- Test: `frontend/src/app/shell/shell.spec.ts`

`shell.css` branches at 900px and 720px. Neither is a declared breakpoint, so
the stylesheet and `ViewportService.isNarrow()` can disagree about what
"narrow" means — the exact defect `breakpoints.ts`'s own docstring warns about.
900px becomes "below `md`" (`max-width: 1023px`); 720px becomes "below `sm`"
(`max-width: 639px`).

**This changes behaviour between 640px and 720px**, deliberately: the clock and
the wide tape now survive down to 640px instead of disappearing at 721px.

**Interfaces:**
- Consumes: `BREAKPOINTS` values as literals (an `@media` cannot read `var()` —
  see `breakpoints.ts`).
- Produces: no API change.

- [x] **Step 1: Write the failing test**

Append to `frontend/src/app/shell/shell.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('shell.css breakpoints', () => {
  const css = readFileSync(join(process.cwd(), 'src/app/shell/shell.css'), 'utf8');

  it('uses only declared breakpoint values in width queries', () => {
    // A media query at 900px or 720px puts the stylesheet and
    // ViewportService on different scales — see breakpoints.ts.
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...css.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)]
      .map((m) => m[1]);

    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/shell/shell.spec.ts`
Expected: FAIL — received `['900', '720']`.

- [x] **Step 3: Apply the change**

In `frontend/src/app/shell/shell.css`, replace lines 368–382 with:

```css
/* The drop order, widest trigger first -- spec v85 "Responsive behaviour",
   retriggered onto the declared breakpoints by v95 A2.
   Everything here is a removal: the bar never wraps to a second row, because
   a two-row bar changes the height of every page's content area. The title
   itself already truncates with an ellipsis (R1-05) and the tape already
   scrolls (R1-06), so below sm the bar degrades to
   mark - title - scrolling tape - status, with nothing overflowing.

   v95: these were 900px and 720px -- neither a declared breakpoint, so the
   stylesheet and ViewportService.isNarrow() disagreed between 640 and 720.
   The clock and the wide tape now survive down to 640px. */
@media (max-width: 1023px) {
  .page-subtitle { display: none; }
}
@media (max-width: 639px) {
  .clock { display: none; }
  .topbar { gap: var(--space-10); }
  .topbar-tape { flex-basis: 7rem; max-width: 7rem; }
  .topbar-lead { flex-basis: 9rem; }
}
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/shell/shell.spec.ts`
Expected: PASS.

- [x] **Step 5: Verify visually**

Load the shell at 390 / 768 / 1024 via Chrome DevTools MCP (`resize_page` or
`emulate`). Expected: subtitle hidden at 768 and 390, present at 1024; clock
present at 768, hidden at 390. Confirm the top bar is still one row at all
three.

- [x] **Step 6: Commit**

```bash
git add frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts
git commit -m "fix(v95): shell drops at the declared breakpoints, not 900/720"
```

---

### Task A3: Restore the 44px touch floor

**Files:**
- Modify: `frontend/src/app/ui/button.ts` (the `:host(.chip)` and `:host(.link)` blocks)
- Modify: `frontend/src/app/ui/chip.ts` (its `min-height: 28px` restoration)
- Modify: `frontend/src/app/ui/control-bar.ts` (`.clear`)
- Test: `frontend/src/app/ui/button.spec.ts`

`tokens.css` already raises `--control-h` to 44px under
`(pointer: coarse), (max-width: 639px)`. `button.ts` discards it with
`min-height: 0` on two host variants, and the components below inherit that.
The fix is to stop opting out, not to add new rules.

**Interfaces:**
- Consumes: `--control-h`, `--text-control` from `tokens.css`.
- Produces: no API change. `sb-chip` and `button[sb-button].link` become
  44px-tall targets under a coarse pointer and stay visually unchanged above it.

- [x] **Step 1: Write the failing test**

Append to `frontend/src/app/ui/button.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('button touch floor', () => {
  const read = (p: string) => readFileSync(join(process.cwd(), p), 'utf8');

  it.each([
    'src/app/ui/button.ts',
    'src/app/ui/chip.ts',
    'src/app/ui/control-bar.ts',
  ])('%s never sets min-height: 0 on an interactive host', (path) => {
    // tokens.css raises --control-h to 44px under a coarse pointer. A
    // component that sets min-height: 0 opts every one of its call sites out
    // of that floor, which is how chips reached ~28px on a phone.
    expect(read(path)).not.toMatch(/min-height:\s*0\b/);
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/button.spec.ts`
Expected: FAIL for `button.ts`.

- [x] **Step 3: Apply the change**

In `frontend/src/app/ui/button.ts`, in both the `:host(.chip)` and
`:host(.link)` blocks, delete the `min-height: 0;` declaration and replace it
with the shared floor:

```css
    min-height: var(--control-h);
```

In `frontend/src/app/ui/chip.ts`, delete the `min-height: 28px;` restoration in
its coarse-pointer block — it exists only to undo `button.ts`'s opt-out and now
fights the token.

In `frontend/src/app/ui/control-bar.ts`, add to the `.clear` rule:

```css
      min-height: var(--control-h);
      min-width: var(--control-h);
```

matching what `pagination.ts` already does for the same reason.

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/button.spec.ts`
Expected: PASS.

Then run the neighbouring suites these files feed, because this changes
rendered heights at three call sites:

Run: `cd frontend && npm test -- --include src/app/ui/chip.spec.ts`
Expected: PASS. If a test asserts a 28px height, update it to the token — the
assertion was pinning the opt-out.

- [x] **Step 5: Verify visually**

At 390px, confirm chips on Trades and the `.clear` control are comfortably
tappable and that no chip row now overflows its container. A taller chip may
wrap a row that previously fit; that is expected and acceptable.

- [x] **Step 6: Commit**

```bash
git add frontend/src/app/ui/button.ts frontend/src/app/ui/chip.ts frontend/src/app/ui/control-bar.ts frontend/src/app/ui/button.spec.ts
git commit -m "fix(v95): chips, link buttons and .clear stop opting out of --control-h"
```

---

### Task A4: Stop two grids overflowing on content

**Files:**
- Modify: `frontend/src/app/ui/histogram.ts` (the `.label` rule)
- Modify: `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts` (the `.detail` cell)
- Test: `frontend/src/app/ui/histogram.spec.ts`

Both are the same CSS bug: a grid track whose automatic minimum is `min-content`,
holding text longer than the track. `histogram.ts` gives `.label` a `4rem` track
with no ellipsis while callers feed it strings like
`12.34R · momentum_breakout (n=45)`. `recent-activity.ts` gives `.detail` a `1fr`
track with no `min-width: 0`.

**Interfaces:**
- Consumes: nothing new.
- Produces: no API change.

- [x] **Step 1: Write the failing test**

Append to `frontend/src/app/ui/histogram.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('histogram label overflow', () => {
  const css = readFileSync(join(process.cwd(), 'src/app/ui/histogram.ts'), 'utf8');

  it('lets the label shrink below its content width', () => {
    // A grid item's automatic minimum is min-content. Without min-width: 0
    // a long label pushes the bar column out of the panel instead of
    // ellipsising -- and every caller builds labels longer than the 4rem
    // track (strategy-contribution.ts, exit-quality.ts).
    const label = css.match(/\.label\s*\{[^}]*\}/s)?.[0] ?? '';
    expect(label).toMatch(/min-width:\s*0/);
    expect(label).toMatch(/text-overflow:\s*ellipsis/);
    expect(label).toMatch(/overflow:\s*hidden/);
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/ui/histogram.spec.ts`
Expected: FAIL — the `.label` rule has none of the three.

- [x] **Step 3: Apply the change**

In `frontend/src/app/ui/histogram.ts`, add to the `.label` rule:

```css
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
```

In `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts`, add to
the `.detail` rule:

```css
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/ui/histogram.spec.ts`
Expected: PASS.

- [x] **Step 5: Verify visually**

At 390px, load Risk (histograms) and the Dashboard's Recent Activity panel.
Expected: long labels ellipsise inside their track; neither panel scrolls
sideways.

- [x] **Step 6: Commit**

```bash
git add frontend/src/app/ui/histogram.ts frontend/src/app/workspaces/dashboard/panels/recent-activity.ts frontend/src/app/ui/histogram.spec.ts
git commit -m "fix(v95): histogram labels and activity detail ellipsise instead of overflowing"
```

---

### Task A5: Introduce the tablet band

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`
- Test: `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`
  (create if absent)

This is the defect that motivated the spec. `trading-performance.ts` has a
mobile treatment below 640px and a KPI grid of
`repeat(4, minmax(140px, 180px))` — a 560px hard floor — above it. Between 640
and 1024 the equity block beside that grid is starved to roughly 40px, and
`997,291.88 €` renders as four broken fragments.

The fix is a genuine tablet band: below `md`, the KPI grid drops to two columns
and the equity block takes a full row of its own.

**Interfaces:**
- Consumes: nothing new. (`inlineFrom` is not used here — this is a grid track
  fix, not a demotion.)
- Produces: no API change.

- [x] **Step 1: Write the failing test**

Create or append to
`frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('trading-performance tablet band', () => {
  const src = readFileSync(
    join(process.cwd(), 'src/app/workspaces/dashboard/panels/trading-performance.ts'),
    'utf8',
  );

  it('has a treatment between sm and md, not only below sm', () => {
    // 640 alone leaves iPad portrait on the desktop layout: the 4-up KPI
    // grid's 560px floor starves the equity block to ~40px and the portfolio
    // figure breaks into fragments.
    expect(src).toMatch(/@media\s*\(\s*max-width:\s*1023px\s*\)/);
  });

  it('never leaves a four-track KPI grid below md', () => {
    const tabletBlock = src.match(/@media\s*\(\s*max-width:\s*1023px\s*\)\s*\{[\s\S]*?\n\s{0,4}\}/)?.[0] ?? '';
    expect(tabletBlock).toMatch(/grid-template-columns:\s*repeat\(2,/);
  });

  it('uses only declared breakpoint values', () => {
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts`
Expected: FAIL — no 1023px query exists.

- [x] **Step 3: Apply the change**

In `trading-performance.ts`, add above the existing `max-width: 639px` block:

```css
    /* The tablet band -- v95 A5.
       Between sm and md the 4-up KPI grid's 560px floor and the equity block
       cannot both fit: measured at 768px the equity column collapsed to ~40px
       and '997,291.88 €' rendered as four fragments. Two KPI columns and a
       full-width equity row is the narrowest arrangement where both are
       readable. Above md the original four-up returns untouched. */
    @media (max-width: 1023px) {
      :host { display: block; }
      .equity { width: 100%; margin-bottom: var(--space-14); }
      .equity .figure { white-space: nowrap; }
      .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
```

Adjust the three class names (`.equity`, `.equity .figure`, `.kpis`) to the
selectors actually present in the file — read the existing `max-width: 639px`
block first and reuse its names.

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts`
Expected: PASS.

- [x] **Step 5: Verify visually — this is the task's real gate**

Load `/dashboard` at **768×1024**. Expected: `997,291.88 €` on one line, the
30-day equity sparkline visible, KPI tiles in two columns of four rows,
`REALISED TODAY -133.32 €` not wrapping its currency symbol. Then check 390 and
1024 are unchanged from before this task.

- [x] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/trading-performance.ts frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts
git commit -m "fix(v95): tablet band for trading performance -- the 768px equity collapse"
```

---

### Task A6: Delete the dead card-mode contract

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts:508-523`
- Modify: `frontend/src/app/ui/data-table/data-table.ts:460-467`
- Test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

v80 D4 removed `.card-value` and everything around it, and nothing has set
`--cell-wrap` or `--sep-wrap` since. `dashboard.ts` still reads both and still
carries a comment describing the deleted machinery; `data-table.ts:461` still
claims "Cards instead of a table, below `sm` — spec v18 Decision 9", which v80
superseded. Both are comments that lie about live code.

**This task changes no rendering.** `var(--cell-wrap, nowrap)` already resolves
to `nowrap` because nothing sets it; writing `nowrap` directly is the same
output with an honest source.

**Interfaces:**
- Consumes: nothing.
- Produces: `--cell-wrap` and `--sep-wrap` no longer appear in `frontend/src/`.

- [x] **Step 1: Write the failing test**

Append to `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('dead card-mode contract', () => {
  const read = (p: string) => readFileSync(join(process.cwd(), p), 'utf8');

  it('no longer reads variables nothing sets', () => {
    // v80 D4 removed card mode and with it .card-value; --cell-wrap and
    // --sep-wrap have been set by nothing since. Reading them made the
    // widest cell on the page permanently nowrap behind a comment claiming
    // it was handled.
    const src = read('src/app/workspaces/dashboard/dashboard.ts');
    expect(src).not.toMatch(/--cell-wrap/);
    expect(src).not.toMatch(/--sep-wrap/);
  });

  it('data-table no longer cites the superseded v18 decision', () => {
    expect(read('src/app/ui/data-table/data-table.ts'))
      .not.toMatch(/Cards instead of a table/);
  });
});
```

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: FAIL on both cases.

- [x] **Step 3: Apply the change**

In `dashboard.ts`, replace lines 511–523 with:

```css
    /* The widest cell on the page -- four figures in two units,
       '+2.34% (+118.20 USD) → +8.00% - −3.00%'. It measured 279px at 375px
       and must not wrap: a wrapped plan line reads as two separate trades.
       Below md the column demotes into the row expansion instead (v95 C4),
       which is what keeps it off a phone rather than a wrap rule.
       (v80 D4 removed card mode; the --cell-wrap hook it fed died with it.) */
    .pnl-plan {
      font-family: var(--font-mono);
      font-size: var(--text-table);
      white-space: nowrap;
    }
    .pnl-plan .sep { color: var(--text-faint); white-space: pre; }
```

In `data-table.ts`, replace the comment at lines 460–467 with:

```ts
  /**
   * Phone mode below `sm` — v80 D4.
   *
   * NOT cards: v80 replaced card mode with a pinned identity column and a
   * sort select, and removed `.card`/`.card-value` with it. The test
   * `'keeps the table below the breakpoint -- no cards'` is that decision's
   * record; v95 builds on it rather than reversing it (spec v95 §4.1, and
   * §13 for the comparison that could revisit it).
   *
   * Driven by the viewport rather than by an input, so no call site has to
   * remember to ask for it. `cardsAt` keeps its name and type for the same
   * reason it always had them: jsdom does not lay out, so forcing the mode is
   * the only way a test can reach it.
   */
```

- [x] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: PASS.

Run: `cd frontend && npm test -- --include src/app/ui/data-table/data-table.spec.ts`
Expected: PASS, unchanged — this task touched only a comment there.

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/ui/data-table/data-table.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git commit -m "chore(v95): delete the dead --cell-wrap contract v80 left behind"
```

---

### Task A7: Correct Analytics' breakpoint drift (added during execution)

**Why this task exists:** the plan as written excluded
`workspaces/analytics/` entirely, on the assumption that v94 (then still
open) would adopt this responsive model there. v94 has since merged and
closed without doing so — see the amended Global Constraint in
`_0-index.md`. The human partner chose, when this was surfaced, to bring
Analytics onto the declared breakpoint set inside v95 rather than open a
separate plan. This is the only file scope Analytics gets in this plan — no
other task may touch `workspaces/analytics/`.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/attribution.ts:149`
- Modify: `frontend/src/app/workspaces/analytics/tabs/edge.ts:10`
- Modify: `frontend/src/app/workspaces/analytics/tabs/execution.ts:22`
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts:158`
- Modify: `frontend/src/app/workspaces/analytics/tabs/pipeline.ts:19`
- Test: the five matching `*.spec.ts` files in the same directory.

All five files carry an identical, independently-authored pattern: a
two-column `.panels { grid-template-columns: repeat(2, minmax(0,1fr)) }`
grid that collapses to one column via `@media (max-width: 800px)`. 800px is
not a declared breakpoint. Following A2's precedent (map each drifted value
to the *numerically nearest* declared floor: 900px→md's 1023 because
`|900-1024| < |900-640|`; 720px→sm's 639 because `|720-640| < |720-1024|`),
800px maps to **sm's `639px`** (`|800-640|=160` vs `|800-1024|=224`).

**This changes behaviour between 640px and 800px**, deliberately, same shape
as A2: the two-column panel grid now survives down to 640px instead of
collapsing to one column at 801px.

**Interfaces:**
- Consumes: `BREAKPOINTS` values as literals (same `@media` cannot read
  `var()` constraint as every other width-query task).
- Produces: no API change; five independent style-only edits.

- [x] **Step 1: Write the failing tests**

Append the same shape of test to each of the five spec files (adjust the
component/file name per file — shown here for `overview.spec.ts`; repeat for
`attribution.spec.ts`, `edge.spec.ts`, `execution.spec.ts`, `pipeline.spec.ts`):

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('overview.ts breakpoints', () => {
  it('uses only declared breakpoint values in width queries', () => {
    // A media query at 800px puts this file and ViewportService on
    // different scales -- see breakpoints.ts. v95 A7.
    const src = readFileSync(
      join(process.cwd(), 'src/app/workspaces/analytics/tabs/overview.ts'),
      'utf8',
    );
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- --include "src/app/workspaces/analytics/tabs/*.spec.ts"`
Expected: FAIL on all five, each with `received ['800']`.

- [x] **Step 3: Apply the change**

In each file, replace `@media (max-width: 800px)` with
`@media (max-width: 639px)`. The rule body (`{ .panels { grid-template-columns: 1fr; } }`)
does not change — only the threshold. This is a one-line find/replace per
file; no other line in any of the five is touched.

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- --include "src/app/workspaces/analytics/tabs/*.spec.ts"`
Expected: PASS on all five.

- [x] **Step 5: Verify visually**

Load `/analytics` (each of the five tabs: Overview, Attribution, Edge,
Execution, Pipeline) at 390 / 768 / 1024 via Chrome DevTools MCP. Expected:
two-column panel grid at 768 and 1024 (was already two-column at 768 before
this change, since 768 > 640 either way); single column at 390. Confirm no
tab regresses to a broken layout at 800×any (the width that used to be the
threshold — it should now read as clearly "wide", two columns, not sit on an
edge).

- [x] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/attribution.ts frontend/src/app/workspaces/analytics/tabs/attribution.spec.ts frontend/src/app/workspaces/analytics/tabs/edge.ts frontend/src/app/workspaces/analytics/tabs/edge.spec.ts frontend/src/app/workspaces/analytics/tabs/execution.ts frontend/src/app/workspaces/analytics/tabs/execution.spec.ts frontend/src/app/workspaces/analytics/tabs/overview.ts frontend/src/app/workspaces/analytics/tabs/overview.spec.ts frontend/src/app/workspaces/analytics/tabs/pipeline.ts frontend/src/app/workspaces/analytics/tabs/pipeline.spec.ts
git commit -m "fix(v95): analytics panel grids drop at the declared breakpoints, not 800px"
```

---

## Phase A exit criteria

- `ui/priority.ts` exists and `priority.spec.ts` passes at every boundary.
- `shell.css` and `trading-performance.ts` contain no width query outside
  639/640/1023/1024/1439/1440/1919/1920.
- The five `workspaces/analytics/tabs/*.ts` files touched by A7 contain no
  width query outside that same set (A7, added during execution).
- No `min-height: 0` in `button.ts`, `chip.ts` or `control-bar.ts`.
- `--cell-wrap` and `--sep-wrap` appear nowhere in `frontend/src/`.
- `/dashboard` at 768×1024 shows the portfolio figure on one line.
- v80 D4's phone-mode tests pass unmodified.
