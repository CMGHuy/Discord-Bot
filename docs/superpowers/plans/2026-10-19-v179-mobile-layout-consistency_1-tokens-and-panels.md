# v179 Mobile layout consistency. Part 1: worktree, text floor, numeric font, 44px hit areas, panel baseline, one stat tile (V179-1..V179-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier. **Never read this part whole**: `grep -n "^### Task V179-3:" -A 300 docs/superpowers/plans/2026-10-19-v179-mobile-layout-consistency_1-tokens-and-panels.md`.

**Spec:** [`2026-10-19-v179-mobile-layout-consistency-design.md`](../specs/2026-10-19-v179-mobile-layout-consistency-design.md) (this part: §2.3, §2.4, §2.5, §3.3 stat tiles and panels, §3.4, §6b.6; §6a and §6b override the earlier sections)
**Index:** [`2026-10-19-v179-mobile-layout-consistency_0-index.md`](2026-10-19-v179-mobile-layout-consistency_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, `## Parallelisation`, the Contracts block and the task ledger. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-19-v179-mobile-layout-consistency` (branch `2026-10-19-v179-mobile-layout-consistency`, created in V179-1). Every task edits files **inside `$WT`**; the `Create:`/`Modify:` paths below are relative to the worktree root. Use `git -C "$WT"` for git; run the Angular tests from `$WT/frontend` in a subshell: `(cd "$WT/frontend" && npx ng test --watch=false --include <spec>)`.

**Test facts every task here relies on (brief §4).** Vitest under `@angular/build:unit-test`, jsdom, `cwd` = `frontend/`. Component styles are not laid out and `matchMedia` never matches, so CSS is asserted as **source text** (`readFileSync(join(process.cwd(), '<path>'))` + a `rule(selector)` regex), the way `ui/layout.spec.ts` and `ui/tokens.spec.ts` already do. The jsdom `:root` tokens come from `tests/charts/resolved_tokens.json`: after any `frontend/src/styles/tokens.css` edit run `python scripts/dev/dump_tokens.py` from `$WT` and commit the fixture in the same commit. `allSources()` (`frontend/src/app/ui/testing/all-sources.ts`) returns every non-spec `.ts/.css/.html` under `frontend/src` except `styles/`, named `app/...` with forward slashes. The global stylesheet sets `box-sizing: border-box` on everything (`styles.css:12`).

**Produced here for later parts (ledger):** `--font-num`; floored `--text-micro`/`--text-chip`; `--hit-min` (24px, 44px under `@media (pointer: coarse), (max-width: 1023px)`); the global `.sb-hit` class; `.num { font-family: var(--font-num) }`; `sb-control-row` on `align-items: last baseline`; the `sb-panel` header rule (one height, baseline); the single stacked `sb-stat-tile`; the workspace guard against `::ng-deep` into `sb-stat-tile`/`sb-metric-card`.

# Phase 1: Tokens and global styles

### Task V179-1: Worktree, 11px text floor and numeric font token

**Model:** sonnet — token and stylesheet edits with source-text tests and a regenerated fixture; no judgement beyond the spec's exact values.

**Files:**
- Modify: `frontend/src/styles/tokens.css` (the size block ~l.210-223, after `--font-mono` ~l.195)
- Modify: `frontend/src/styles.css` (`.num` ~l.60)
- Modify: `frontend/src/app/ui/strip-plot.ts` (the one literal `font-size:10px`)
- Modify: `frontend/src/app/ui/tokens.spec.ts` (append two `describe` blocks)
- Modify: `frontend/src/app/ui/text-styles.spec.ts` (append two `describe` blocks)
- Modify: `tests/charts/resolved_tokens.json` (regenerated, never hand-edited)

**Interfaces:**
- Consumes: existing `resolveToken(name)` (`frontend/src/app/ui/testing/resolve-token.ts`), `allSources()` (`frontend/src/app/ui/testing/all-sources.ts`), `scripts/dev/dump_tokens.py`.
- Produces: `--font-num: var(--font-mono)` in the first `:root` block; `--text-micro: max(11px, calc(11px * var(--text-scale)))`; `--text-chip: max(11px, calc(12px * var(--text-scale)))`; `.num { font-family: var(--font-num); font-variant-numeric: tabular-nums; }`. V179-4 and V179-17 consume `--font-num`; every later task relies on no text token resolving below 11px at the 90% zoom step (`ZOOM_CHOICES = [90, 100, 110, 125]`, `frontend/src/app/shell/shell.ts:60`).

**Why (spec §2.5, §6b.6).** The 9.9px labels are `--text-micro: calc(11px * var(--text-scale))` at the 90% zoom preference (11 × 0.9); `--text-chip` gives 10.8px there. The floor goes inside the token so zoom still scales everything above it. Numbers render mono only through `.num`; one `--font-num` token names that face so stat values and key/value cells (V179-4, V179-17) can take it without the class. The only literal sub-11px size in the app is `strip-plot.ts`'s `.sub{font-size:10px}` (`grep -rnoE "font-size:\s*[0-9.]+px" frontend/src` finds it and two 11px ones); it is fixed here because the guard below would otherwise fail on it.

- [ ] **Step 1: Create the worktree and install the frontend**

```bash
R="E:/Documents/Private/Projects/Discord-Bot"
WT="$R/.claude/worktrees/2026-10-19-v179-mobile-layout-consistency"
git -C "$R" status --short          # expect: clean main (plan files committed)
git -C "$R" worktree add "$WT" -b 2026-10-19-v179-mobile-layout-consistency main
(cd "$WT/frontend" && npm ci)
git -C "$WT" branch --show-current  # expect: 2026-10-19-v179-mobile-layout-consistency
```

If `git -C "$R" worktree list` already shows `$WT` (a resumed run), skip the `add` and `npm ci` and continue at the first unchecked step.

- [ ] **Step 2: Write the failing token tests**

Append to `frontend/src/app/ui/tokens.spec.ts` (it already defines `CSS` and imports `resolveToken`, `describe`, `expect`, `it`):

```ts
/**
 * v179 §3.4 / §6b.6: no text-size token falls below 11px, even at the 90%
 * zoom preference (shell.ts ZOOM_CHOICES), while every size above the floor
 * still scales with --text-scale. The 9.9px labels the audit found were
 * --text-micro at 90%; the floor lives inside the token, as max(11px, ...).
 */
describe('v179: the 11px text floor', () => {
  /** Every size token: a --text-* declaration whose value reads --text-scale
   *  (the colour tokens --text-muted/--text-secondary/... never do). */
  const SIZE = /^\s*(--text-[a-z]+):\s*(.*var\(--text-scale\).*);/gm;
  const sizes = [...CSS.matchAll(SIZE)].map((m) => ({ name: m[1], value: m[2].trim() }));

  /** Pixels at `scale` for `calc(Npx * var(--text-scale))`, optionally
   *  wrapped in `max(Fpx, ...)`. */
  function px(value: string, scale: number): number {
    const base = Number(value.match(/calc\((\d+(?:\.\d+)?)px \* var\(--text-scale\)\)/)![1]) * scale;
    const floor = value.match(/^max\((\d+)px,/);
    return floor ? Math.max(Number(floor[1]), base) : base;
  }

  it('finds the size tokens', () => {
    expect(sizes.map((s) => s.name)).toEqual(expect.arrayContaining(['--text-micro', '--text-chip', '--text-table']));
  });

  it.each([0.9, 1, 1.1, 1.25])('keeps every size token at or above 11px at scale %s', (scale) => {
    const below = sizes
      .filter((s) => px(s.value, scale) < 11)
      .map((s) => `${s.name}=${px(s.value, scale)}px`);
    expect(below).toEqual([]);
  });

  it('floors the two tokens that could fall below it, inside the token', () => {
    expect(CSS).toMatch(/^\s*--text-micro:\s*max\(11px, calc\(11px \* var\(--text-scale\)\)\);/m);
    expect(CSS).toMatch(/^\s*--text-chip:\s*max\(11px, calc\(12px \* var\(--text-scale\)\)\);/m);
  });

  it('still grows a floored token above 100%', () => {
    const micro = sizes.find((s) => s.name === '--text-micro')!;
    expect(px(micro.value, 1.25)).toBeCloseTo(13.75);
  });

  it('reaches jsdom through the regenerated fixture', () => {
    expect(resolveToken('--text-micro')).toBe('max(11px, calc(11px * 1))');
    expect(resolveToken('--text-chip')).toBe('max(11px, calc(12px * 1))');
  });
});

/** v179 §3.3: every numeric value uses one tabular face, named once. */
describe('v179: one numeric face', () => {
  it('declares --font-num as the mono family', () => {
    expect(CSS).toMatch(/^\s*--font-num:\s*var\(--font-mono\);/m);
    expect(resolveToken('--font-num')).toBe(resolveToken('--font-mono'));
  });
});
```

Append to `frontend/src/app/ui/text-styles.spec.ts` (it already defines `GLOBAL` and `rule(name)`). Add the import next to the existing ones at the top:

```ts
import { allSources } from './testing/all-sources';
```

and at the end of the file:

```ts
describe('v179: numbers in one face', () => {
  it('.num takes the numeric font token, tabular', () => {
    const r = rule('num');
    expect(r).toContain('font-family: var(--font-num)');
    expect(r).toContain('font-variant-numeric: tabular-nums');
  });
});

describe('v179: no literal text size below 11px', () => {
  it('sets no px font-size under 11px anywhere in the app', () => {
    const offenders = allSources().flatMap(({ name, source }) =>
      [...source.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)]
        .filter((m) => Number(m[1]) < 11)
        .map((m) => `${name}: ${m[0]}`));
    expect(offenders).toEqual([]);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
(cd "$WT/frontend" && npx ng test --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/text-styles.spec.ts)
```

Expected: FAIL — `keeps every size token at or above 11px at scale 0.9` lists `--text-micro=9.9px` and `--text-chip=10.8px`; the `max(11px` regexes, `--font-num`, `.num … var(--font-num)` and the literal-size guard (`app/ui/strip-plot.ts: font-size:10px`) fail.

- [ ] **Step 4: Floor the two tokens and add `--font-num`**

In `frontend/src/styles/tokens.css`, directly after the `--font-mono: …;` line, add:

```css
  /* v179 §3.3 -- the one face for every numeric value (.num, stat values,
     key/value figures). Mono, tabular: digits align down a column. Named
     separately from --font-mono so a figure says "I am a number", not "I am
     code", and the two can part later without a sweep. */
  --font-num: var(--font-mono);
```

Replace the two size lines

```css
  --text-micro: calc(11px * var(--text-scale));      /* micro-label */
  --text-chip: calc(12px * var(--text-scale));      /* chip */
```

with:

```css
  /* v179 §6b.6 -- an 11px floor inside the two tokens the 90% zoom step
     would push below it (9.9px and 10.8px). Zoom still scales every size
     above the floor; a zoomed-out view fits more, but never drops its
     smallest labels below legibility. tokens.spec.ts checks every size
     token at 90/100/110/125%. */
  --text-micro: max(11px, calc(11px * var(--text-scale)));  /* micro-label */
  --text-chip: max(11px, calc(12px * var(--text-scale)));   /* chip */
```

- [ ] **Step 5: Point `.num` at the token and lift the strip-plot caption**

In `frontend/src/styles.css`, the `.num` rule becomes (keep the comment above it):

```css
.num {
  font-family: var(--font-num);
  font-variant-numeric: tabular-nums;
}
```

`frontend/src/app/ui/strip-plot.ts` is one minified line; change its single `font-size:10px` (inside `.sub{…}`) to `font-size:11px`:

```bash
sed -i 's/font-size:10px}/font-size:11px}/' "$WT/frontend/src/app/ui/strip-plot.ts"
grep -c "font-size:10px" "$WT/frontend/src/app/ui/strip-plot.ts"   # expect 0
```

- [ ] **Step 6: Regenerate the jsdom token fixture**

```bash
(cd "$WT" && python scripts/dev/dump_tokens.py && python scripts/dev/dump_tokens.py --check)
git -C "$WT" diff --stat -- tests/charts/resolved_tokens.json
```

Expected: `wrote N tokens …`, then `resolved_tokens.json is current`; the diff adds `font-num` and turns `text-micro`/`text-chip` into `max(11px, calc(… * 1))`.

- [ ] **Step 7: Run the tests to verify they pass**

```bash
(cd "$WT/frontend" && npx ng test --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/text-styles.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/strip-plot.spec.ts)
(cd "$WT" && python scripts/dev/testrun.py file tests/charts/test_chart_theme.py)
```

Expected: all PASS; `0 failed`.

- [ ] **Step 8: Commit**

```bash
git -C "$WT" add frontend/src/styles/tokens.css frontend/src/styles.css frontend/src/app/ui/strip-plot.ts frontend/src/app/ui/tokens.spec.ts frontend/src/app/ui/text-styles.spec.ts tests/charts/resolved_tokens.json
git -C "$WT" commit -m "feat(v179): 11px floor in the text tokens, --font-num for every numeral

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V179-2: 44px hit areas on phone and tablet

**Model:** sonnet — one media-query widening, one global utility and a table of small per-control CSS/template edits, each pinned by a source-text test.

**Files:**
- Modify: `frontend/src/styles/tokens.css` (`:root` after `--row-h`; the touch block ~l.320-336)
- Modify: `frontend/src/styles.css` (append `.sb-hit`)
- Modify: `frontend/src/app/ui/button.ts` (touch media block ~l.196-200)
- Modify: `frontend/src/app/ui/hint.ts` (touch media block ~l.121-124)
- Modify: `frontend/src/app/shell/profile-menu.ts` (touch media block ~l.144-149)
- Modify: `frontend/src/app/shell/shell.css` (`.nav a` ~l.207)
- Modify: `frontend/src/app/ui/filter-bar.ts` (`FilterChips` `.chip` ~l.99)
- Modify: `frontend/src/app/ui/column-picker.ts` (`.trigger`, `label`, `.reset` ~l.86-140)
- Modify: `frontend/src/app/ui/row-link.ts` (template)
- Modify: `frontend/src/app/ui/segmented.ts` (`.segment`)
- Modify: `frontend/src/app/ui/form-controls.ts` (`Checkbox` `.box` ~l.193)
- Modify: `frontend/src/app/ui/panel-header.ts` (template: the `Table` toggle)
- Modify: `frontend/src/app/workspaces/dashboard/positions-table.ts` (template ~l.66: "View in Trades →")
- Modify: `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts` (template ~l.29: "View all")
- Modify: `frontend/src/app/ui/tokens.spec.ts` (the touch-block test)
- Modify: `frontend/src/app/ui/button.spec.ts` (~l.81-87)
- Modify: `frontend/src/app/ui/hint.spec.ts` (~l.95-100)
- Create: `frontend/src/app/ui/hit-area.spec.ts`
- Modify: `tests/charts/resolved_tokens.json` (regenerated)

**Interfaces:**
- Consumes: V179-1's regenerated fixture; existing `--control-h`, `allSources()`, `resolveToken()`.
- Produces (ledger): `--hit-min` (`24px` in `:root`, `44px` in the touch block); the touch condition `@media (pointer: coarse), (max-width: 1023px)` (the only touch condition left in the app; V179-9's sort buttons, V179-5's toolbar button, V179-14's activity rows and V179-19's audit use it); the global class `.sb-hit` (a centred transparent `::after` of `max(100%, var(--hit-min))` in both axes). Later tasks add `sb-hit` to a control's `class` and nothing else.

**Design (spec §2.5, §3.4).**
- **Phone and tablet.** The 44px touch block widens from `(pointer: coarse), (max-width: 639px)` to `(pointer: coarse), (max-width: 1023px)` (1023 = `BREAKPOINTS.md` − 1, allowed by `ui/breakpoint-guard.spec.ts`). It already raises `--control-h`/`--row-h` to 44px and control text to 16px; it now also sets `--hit-min: 44px`. Every component touch block uses the same condition, so `profile-menu.ts`'s bare `(pointer: coarse)` and the two `639px` copies in `button.ts`/`hint.ts` change with it.
- **Two ways to 44px, chosen per control.** A control whose visible box may grow (side-menu links, filter chips, the `Columns` trigger) takes `min-height: var(--control-h)` (border-box, so 44px total under the touch block, 28px — about today's size — on a desktop mouse). A control whose look must stay small (row links, "View all" links, the panel-header `Table` toggle) takes `class="… sb-hit"`: the visible element is unchanged and a transparent `::after` reaches `--hit-min`. Segments keep `min-height: var(--control-h)` and gain `min-width: var(--hit-min)`; a checkbox's target is its whole `<label class="field">`, whose `.box` band is `--control-h` tall and now at least `--hit-min` wide; the picker's checkbox rows and reset button get `min-height: var(--hit-min)`.
- **Not here:** `sb-data-table` header sort buttons (V179-9, same file as the compact rows), the toolbar's "Filters N" button (V179-5), Recent-activity rows (V179-14).
- `.sb-hit` is never put on an element that draws its own `::after`; none of the elements above does (`grep -n "::after" ui/row-link.ts ui/panel-header.ts workspaces/dashboard/positions-table.ts workspaces/dashboard/panels/recent-activity.ts` is empty today).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/hit-area.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { allSources } from './testing/all-sources';
import { resolveToken } from './testing/resolve-token';

/**
 * v179 §3.4: every interactive control has a 44x44px hit area on phone and
 * tablet. Asserted as source text: jsdom evaluates no media query and lays
 * nothing out (see tokens.spec.ts for why the stylesheet is read from disk).
 */
const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
const TOKENS = read('src/styles/tokens.css');
const GLOBAL = read('src/styles.css');
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
/** The first rule whose selector STARTS a line, so `.nav a` does not match
 *  `.shell.railed:not(.overlay) .nav a`. '' when absent. */
const rule = (source: string, selector: string) =>
  source.match(new RegExp(`^\\s*${esc(selector)}\\s*\\{[^}]*\\}`, 'm'))?.[0] ?? '';

describe('v179: --hit-min and the touch block', () => {
  it('defaults --hit-min to 24px (WCAG 2.2 minimum target)', () => {
    expect(TOKENS).toMatch(/^\s*--hit-min:\s*24px;/m);
    expect(resolveToken('--hit-min')).toBe('24px');
  });

  it('raises --hit-min to 44px on phone and tablet', () => {
    const block = TOKENS.match(/@media \(pointer: coarse\), \(max-width: 1023px\)\s*\{([\s\S]*?)\n\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toMatch(/--hit-min:\s*44px;/);
  });

  it('leaves no phone-only or bare coarse-pointer touch block anywhere', () => {
    const sources = [...allSources(), { name: 'styles/tokens.css', source: TOKENS }];
    const offenders = sources
      .filter(({ source }) => /@media \(pointer: coarse\), \(max-width: 639px\)/.test(source)
        || /@media \(pointer: coarse\)\s*\{/.test(source))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });
});

describe('v179: the .sb-hit utility', () => {
  it('makes the control the containing block', () => {
    expect(rule(GLOBAL, '.sb-hit')).toContain('position: relative');
  });

  it('centres a transparent box of at least --hit-min on the control', () => {
    const after = rule(GLOBAL, '.sb-hit::after');
    for (const declaration of [
      'content: ""', 'position: absolute', 'top: 50%', 'left: 50%',
      'width: max(100%, var(--hit-min))', 'height: max(100%, var(--hit-min))',
      'transform: translate(-50%, -50%)',
    ]) {
      expect(after).toContain(declaration);
    }
  });
});

describe('v179: controls that grow to the hit size', () => {
  const GROWN: [file: string, selector: string, declaration: string][] = [
    ['src/app/shell/shell.css', '.nav a', 'min-height: var(--control-h)'],
    ['src/app/ui/filter-bar.ts', '.chip', 'min-height: var(--control-h)'],
    ['src/app/ui/column-picker.ts', '.trigger', 'min-height: var(--control-h)'],
    ['src/app/ui/column-picker.ts', 'label', 'min-height: var(--hit-min)'],
    ['src/app/ui/column-picker.ts', '.reset', 'min-height: var(--hit-min)'],
    ['src/app/ui/segmented.ts', '.segment', 'min-width: var(--hit-min)'],
    ['src/app/ui/form-controls.ts', '.box', 'min-width: var(--hit-min)'],
  ];

  it.each(GROWN)('%s %s sets %s', (file, selector, declaration) => {
    expect(rule(read(file), selector)).toContain(declaration);
  });
});

describe('v179: controls that keep their look and take .sb-hit', () => {
  const PADDED: [file: string, markup: RegExp][] = [
    ['src/app/ui/row-link.ts', /<a class="row-link sb-hit"/],
    ['src/app/ui/panel-header.ts', /<button type="button" class="table sb-hit"/],
    ['src/app/workspaces/dashboard/positions-table.ts', /<a class="all-link sb-hit"/],
    ['src/app/workspaces/dashboard/panels/recent-activity.ts', /<a panel-actions class="all-link sb-hit"/],
  ];

  it.each(PADDED)('%s pads its control with .sb-hit', (file, markup) => {
    expect(read(file)).toMatch(markup);
  });
});
```

In `frontend/src/app/ui/tokens.spec.ts`, replace the test `grows controls, rows and control text for touch and narrow screens` with:

```ts
  it('grows controls, rows, control text and the hit area on phone and tablet (v179 §3.4)', () => {
    const block = CSS.match(/@media \(pointer: coarse\), \(max-width: 1023px\)\s*\{([\s\S]*?)\n\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toMatch(/--control-h:\s*44px;/);
    expect(block![1]).toMatch(/--row-h:\s*44px;/);
    expect(block![1]).toMatch(/--text-control:\s*calc\(16px \* var\(--text-scale\)\);/);
    expect(block![1]).toMatch(/--hit-min:\s*44px;/);
  });
```

In `frontend/src/app/ui/button.spec.ts`, the test `grows both icon variants to a square touch target` reads the new condition:

```ts
  it('grows both icon variants to a square touch target', () => {
    const block = SOURCE.match(/@media \(pointer: coarse\), \(max-width: 1023px\) \{([\s\S]*?)\n {4}\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain(':host(.icon), :host(.danger-icon)');
    expect(block![1]).toContain('min-width: var(--control-h)');
    expect(block![1]).toContain('min-height: var(--control-h)');
  });
```

In `frontend/src/app/ui/hint.spec.ts`, the test `gives the trigger a 44px target on touch and narrow screens` becomes:

```ts
  it('gives the trigger a 44px target on phone and tablet', () => {
    const block = SOURCE.match(/@media \(pointer: coarse\), \(max-width: 1023px\) \{([\s\S]*?)\n    \}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain('min-width: var(--control-h)');
    expect(block![1]).toContain('min-height: var(--control-h)');
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
(cd "$WT/frontend" && npx ng test --watch=false --include src/app/ui/hit-area.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/button.spec.ts --include src/app/ui/hint.spec.ts)
```

Expected: FAIL — no `--hit-min`, no `1023px` block (tokens, button, hint), offenders `app/shell/profile-menu.ts`, `app/ui/button.ts`, `app/ui/hint.ts`, `styles/tokens.css`; no `.sb-hit`; every row of the two control tables.

- [ ] **Step 3: Tokens — `--hit-min` and the widened touch block**

In `frontend/src/styles/tokens.css`, directly after the `--row-h: 32px;` line in `:root`, add:

```css

  /* v179 §3.4 -- the smallest hit area an interactive control may have.
     24px is WCAG 2.2's minimum target for a mouse; the touch block below
     raises it to 44px. Read by the global .sb-hit (styles.css), which pads a
     control to this size without growing what you see. */
  --hit-min: 24px;
```

Replace the comment and block that start `/* v80 D3 -- touch. A finger needs about 44px;` (through the block's closing `}`) with:

```css
/* v80 D3, widened by v179 §3.4 -- touch, phone AND tablet. A finger needs
 * about 44px; a mouse row of 28px controls shows more data. `pointer:
 * coarse` catches touch at any width, and 1023px (breakpoints.ts's md
 * floor, less one) catches a phone or tablet-width window driven by a mouse
 * too -- v179 asks for 44px targets on both device classes, and a tablet in
 * a desktop browser is still held in the hand often enough. Only these four
 * move: gutters stay put, so this is a hit-target change, not a zoom. 16px
 * control text is also the size below which mobile browsers zoom into a
 * focused field. Every component's own touch block uses this exact
 * condition (ui/hit-area.spec.ts). */
@media (pointer: coarse), (max-width: 1023px) {
  :root {
    --control-h: 44px;
    --row-h: 44px;
    --text-control: calc(16px * var(--text-scale));
    --hit-min: 44px;
  }
}
```

- [ ] **Step 4: The global `.sb-hit` utility**

Append to `frontend/src/styles.css`:

```css

/* v179 §3.4 -- a hit area of at least --hit-min (24px; 44px on phone and
 * tablet, tokens.css) without growing the visible control. The ::after box
 * is transparent and centred on the element, so a 17px "View all" link
 * looks the same and a thumb still lands on it. Global, because the class
 * goes on elements inside many components' templates. For a control whose
 * look may grow instead (a chip, a nav link), prefer
 * min-height: var(--control-h). Never on an element that draws its own
 * ::after. */
.sb-hit {
  position: relative;
}

.sb-hit::after {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  width: max(100%, var(--hit-min));
  height: max(100%, var(--hit-min));
  transform: translate(-50%, -50%);
}
```

- [ ] **Step 5: One touch condition in the components**

`frontend/src/app/ui/button.ts` — the block becomes:

```css
    /* v80 D4 -- a finger needs a square target. The same condition as the
       tokens.css touch block (phone and tablet since v179), where
       --control-h is already 44px. */
    @media (pointer: coarse), (max-width: 1023px) {
      :host(.icon), :host(.danger-icon) { min-width: var(--control-h); min-height: var(--control-h); }
    }
```

`frontend/src/app/ui/hint.ts` — the block becomes:

```css
    /* A fingertip needs 44px around a 14px glyph (v80 D4; phone and tablet
       since v179). */
    @media (pointer: coarse), (max-width: 1023px) {
      .trigger { min-width: var(--control-h); min-height: var(--control-h); }
    }
```

`frontend/src/app/shell/profile-menu.ts` — the block becomes:

```css
    /* Spec v168 §1 and §5: 44px targets on touch -- phone and tablet since
       v179, the tokens.css touch condition. --control-h already gives the
       height there; this gives a short label like "On" the same width. */
    @media (pointer: coarse), (max-width: 1023px) {
      :host ::ng-deep .motion-control .segment { min-width: 44px; justify-content: center; }
    }
```

- [ ] **Step 6: Controls that grow**

`frontend/src/app/shell/shell.css` — add one declaration to the `.nav a` rule (after `padding: …;`):

```css
  /* v179 §3.4: 44px on phone and tablet (--control-h), unchanged on a
     desktop mouse, where the 34px the padding gives already exceeds 28px. */
  min-height: var(--control-h);
```

`frontend/src/app/ui/filter-bar.ts` — in `FilterChips`' `.chip` rule, after `gap: var(--space-6);` add:

```css
      min-height: var(--control-h);
```

`frontend/src/app/ui/column-picker.ts` — add `min-height: var(--control-h);` to `.trigger` (after `gap: var(--space-6);`), `min-height: var(--hit-min);` to `label` (after `gap: var(--space-8);`) and `min-height: var(--hit-min);` to `.reset` (after `margin-top: var(--space-6);`).

`frontend/src/app/ui/segmented.ts` — in the one-line `.segment { … }` rule, after `min-height: var(--control-h);` insert ` min-width: var(--hit-min); justify-content: center;` so it reads `… min-height: var(--control-h); min-width: var(--hit-min); justify-content: center; padding: 0 var(--space-10); …`.

`frontend/src/app/ui/form-controls.ts` — the `Checkbox` `.box` rule becomes:

```css
    .box { display: inline-flex; align-items: center; gap: var(--space-6); height: var(--control-h); min-width: var(--hit-min); }
```

- [ ] **Step 7: Controls that keep their look**

`frontend/src/app/ui/row-link.ts` — template:

```ts
  template: `<a class="row-link sb-hit" [routerLink]="link()"><ng-content /></a>`,
```

`frontend/src/app/ui/panel-header.ts` — the toggle button's opening tag becomes `<button type="button" class="table sb-hit" [attr.aria-pressed]="tableOpen()" (click)="tableOpen.set(!tableOpen())">Table</button>` (only `sb-hit` is added).

`frontend/src/app/workspaces/dashboard/positions-table.ts` — `<a class="all-link" routerLink="/trades" [queryParams]="{ status: active() }">` becomes `<a class="all-link sb-hit" routerLink="/trades" [queryParams]="{ status: active() }">`.

`frontend/src/app/workspaces/dashboard/panels/recent-activity.ts` — `<a panel-actions class="all-link" routerLink="/trades">View all</a>` becomes `<a panel-actions class="all-link sb-hit" routerLink="/trades">View all</a>`.

- [ ] **Step 8: Regenerate the fixture**

```bash
(cd "$WT" && python scripts/dev/dump_tokens.py && python scripts/dev/dump_tokens.py --check)
```

Expected: `hit-min` added (`"24px"`), fixture current.

- [ ] **Step 9: Run the tests to verify they pass**

```bash
(cd "$WT/frontend" && npx ng test --watch=false --include src/app/ui/hit-area.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/button.spec.ts --include src/app/ui/hint.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/row-link.spec.ts --include src/app/ui/segmented.spec.ts --include src/app/ui/filter-bar.spec.ts --include src/app/ui/column-picker.spec.ts --include src/app/ui/form-controls.spec.ts --include src/app/ui/panel-header.spec.ts --include src/app/shell/profile-menu.spec.ts --include src/app/shell/shell.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts)
(cd "$WT" && python scripts/dev/testrun.py file tests/charts/test_chart_theme.py)
```

Expected: all PASS. Also run `--include src/app/workspaces/dashboard/panels/recent-activity.spec.ts` (same command) — it exercises the template the `View all` edit touched.

- [ ] **Step 10: Commit** (two scoped commits; the first leaves every test green on its own, because the component touch blocks still read 639px until the second)

```bash
git -C "$WT" add frontend/src/styles/tokens.css frontend/src/styles.css tests/charts/resolved_tokens.json frontend/src/app/ui/tokens.spec.ts
git -C "$WT" commit -m "feat(v179): --hit-min and .sb-hit; the touch block covers tablets

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "$WT" add frontend/src/app/ui/button.ts frontend/src/app/ui/hint.ts frontend/src/app/shell/profile-menu.ts frontend/src/app/shell/shell.css frontend/src/app/ui/filter-bar.ts frontend/src/app/ui/column-picker.ts frontend/src/app/ui/row-link.ts frontend/src/app/ui/segmented.ts frontend/src/app/ui/form-controls.ts frontend/src/app/ui/panel-header.ts frontend/src/app/workspaces/dashboard/positions-table.ts frontend/src/app/workspaces/dashboard/panels/recent-activity.ts frontend/src/app/ui/button.spec.ts frontend/src/app/ui/hint.spec.ts frontend/src/app/ui/hit-area.spec.ts
git -C "$WT" commit -m "feat(v179): 44px hit areas on nav links, chips, pickers, segments, row and all-links

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 2: Panels and tiles

### Task V179-3: Panel, panel-header and control-row baseline with one header height

**Model:** sonnet — CSS-only changes to three shared primitives plus their docstrings, each pinned by a source-text test; the alignment choice is fixed by the spec.

**Files:**
- Modify: `frontend/src/app/ui/layout.ts` (`Panel` styles ~l.66-96; `ControlRow` docstring ~l.290-293 and styles ~l.306-326 — **only these two components**; `TabBar` is V179-6's, `Drawer` is V179-15's)
- Modify: `frontend/src/app/ui/panel-header.ts` (the one-line `styles`)
- Modify: `frontend/src/app/ui/layout.spec.ts` (append a `describe`)
- Modify: `frontend/src/app/ui/panel-header.spec.ts` (append a `describe`)

**Interfaces:**
- Consumes: `--control-h`, `--space-*` tokens; V179-2's `sb-hit` on the panel-header `Table` toggle (template untouched here).
- Produces (ledger): `sb-control-row`'s `.row` on `align-items: last baseline`; the `sb-panel` header rule — `display: flex; flex-wrap: wrap; align-items: baseline; align-content: center; min-height: calc(var(--control-h) + 2 * var(--space-10) + 1px)` — with `.actions` on `align-items: baseline`; the first projected child of a panel body loses its top margin; `sb-panel-header` on `align-items: baseline` with `min-height: var(--control-h)`. V179-18 relies on the baseline control row for the Versions "Running now" line and the Dashboard performance header; V179-17 and V179-18 rely on the panel header rule.

**Design (spec §2.3 panel headers, §2.4, §3.3 `sb-panel`, §3.4).**
- **One header height.** Every `sb-panel` header is at least one control tall plus its padding and border: `min-height: calc(var(--control-h) + 2 * var(--space-10) + 1px)` under the global `box-sizing: border-box`. A header with only a label and one with a button or `sb-segmented` are now the same height (28 + 21 = 49px on a desktop mouse, 65px on phone/tablet).
- **One baseline.** `align-items: baseline` puts the 11px label, an `N=` count, a 14px action and the ⓘ glyph on one text line; `flex-wrap: wrap` + `align-content: center` centres that line inside the minimum height (`align-content` needs a multi-line flex container to act), and lets the actions wrap below the label on a narrow panel instead of squeezing it.
- **One gap to the first row.** The body keeps `padding: var(--space-14)`; a first child's own top margin no longer adds to it (`:host ::ng-deep .panel > .body > :first-child { margin-top: 0; }` — `.panel > .body` is this component's own structure, so the reach is one level).
- **Control row on the last baseline.** `align-items: flex-end` aligned bottoms, which lands a labelled control and a bare button on one line but leaves a plain text item (a "Running now" label, a count) on the controls' bottom border. `last baseline` gives the same line for controls (both end in a `--control-h` control with centred text) and puts text items on the controls' text line. The phone `flex-direction: column` rule is unchanged (`layout.spec.ts` pins it).
- `sb-panel-header`'s `header` and `.heading` move from `align-items:center` to `baseline` (the Analytics Equity header "Equity N=972 −2,150.95 € ⓘ"), and the header is one control tall.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/ui/layout.spec.ts` (it already defines `SOURCE`, `esc`, `TestBed`, `Panel`, `provideZonelessChangeDetection`):

```ts
/** One component's styles: the source between its selector and its class. */
function stylesOf(selector: string, className: string): string {
  return SOURCE.slice(SOURCE.indexOf(`selector: '${selector}'`), SOURCE.indexOf(`export class ${className}`));
}
const ruleIn = (styles: string, selector: string) =>
  styles.match(new RegExp(`(?:^|\\n)\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

describe('sb-panel header: one height, one baseline (v179 §3.3, §3.4)', () => {
  const PANEL = stylesOf('sb-panel', 'Panel');

  it('aligns label, counts, actions and hint on the text baseline, never their centres', () => {
    const header = ruleIn(PANEL, 'header');
    expect(header).toContain('align-items: baseline');
    expect(header).not.toContain('align-items: center');
    expect(ruleIn(PANEL, '.actions')).toContain('align-items: baseline');
  });

  it('gives every header one minimum height and centres its line in it', () => {
    const header = ruleIn(PANEL, 'header');
    expect(header).toContain('min-height: calc(var(--control-h) + 2 * var(--space-10) + 1px)');
    expect(header).toContain('flex-wrap: wrap');
    expect(header).toContain('align-content: center');
  });

  it('keeps one gap between the header and the first row of the body', () => {
    expect(PANEL).toContain(':host ::ng-deep .panel > .body > :first-child { margin-top: 0; }');
    expect(ruleIn(PANEL, '.body')).toContain('padding: var(--space-14)');
  });

  it('renders the actions slot inside the header, beside the label', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const f = TestBed.createComponent(Panel);
    f.componentRef.setInput('heading', 'Exposure');
    f.detectChanges();
    const header = (f.nativeElement as HTMLElement).querySelector('header')!;
    expect([...header.children].map((child) => child.tagName.toLowerCase() + '.' + child.className))
      .toEqual(['h2.sb-label', 'div.actions']);
  });
});

describe('sb-control-row on the last baseline (v179 §3.4)', () => {
  const ROW = stylesOf('sb-control-row', 'ControlRow');

  it('aligns controls and plain text on one text line', () => {
    const row = ruleIn(ROW, '.row');
    expect(row).toContain('align-items: last baseline');
    expect(row).not.toContain('flex-end');
  });

  it('still stacks below 640px', () => {
    expect(ROW).toMatch(/@media \(max-width: 639px\) \{\s*\.row \{ flex-direction: column; align-items: stretch; \}/);
  });
});
```

Append to `frontend/src/app/ui/panel-header.spec.ts`; add the two imports at the top next to the existing ones:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

```ts
describe('PanelHeader alignment (v179 §3.4)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/panel-header.ts'), 'utf8');

  it('puts title, N=, total and hint on one baseline, one control tall', () => {
    expect(SOURCE).toMatch(/[\s`]header \{[^}]*align-items:\s*baseline/);
    expect(SOURCE).toMatch(/[\s`]header \{[^}]*min-height:\s*var\(--control-h\)/);
    expect(SOURCE).toMatch(/\.heading \{[^}]*align-items:\s*baseline/);
    expect(SOURCE).not.toMatch(/align-items:\s*center/);
  });

  it('keeps N=, total and the hint inside the heading line', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(PanelHeader);
    fixture.componentRef.setInput('title', 'Equity');
    fixture.componentRef.setInput('n', 972);
    fixture.componentRef.setInput('total', '−2,150.95 €');
    fixture.componentRef.setInput('hint', 'Pre-tax, paper trades.');
    fixture.detectChanges();
    const heading = (fixture.nativeElement as HTMLElement).querySelector('.heading')!;
    for (const selector of ['h2', '.n', '.total', 'sb-hint']) {
      expect(heading.querySelector(selector), selector).not.toBeNull();
    }
  });
});
```

(`panel-header.spec.ts`'s outer `describe` has its own `beforeEach` configuring TestBed; the new `describe` sits after it at top level and configures its own module, as above.)

- [ ] **Step 2: Run the tests to verify they fail**

```bash
(cd "$WT/frontend" && npx ng test --watch=false --include src/app/ui/layout.spec.ts --include src/app/ui/panel-header.spec.ts)
```

Expected: FAIL — `align-items: center` in the panel header and panel-header, no `min-height`/`align-content`, no first-child rule, `flex-end` in the control row. The slot-order test and `still stacks below 640px` already PASS.

- [ ] **Step 3: The `sb-panel` header**

In `frontend/src/app/ui/layout.ts`, `Panel` styles: replace the `header { … }` rule and the `.actions` line with:

```css
    /* v179 §3.3/§3.4 -- one header height and one baseline on every panel.
       At least one control tall (plus padding and the 1px rule, border-box),
       so a header holding only its label and one holding a button or a
       segmented control are the same height. The label, an N= count, an
       action and the hint glyph sit on the text BASELINE -- centring put an
       11px label 2-3px off a 14px button's text. align-content centres that
       one line inside the minimum height; it needs flex-wrap to act, and
       wrapping also lets the actions drop below the label on a narrow panel
       rather than squeeze it. */
    header {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      align-content: center;
      justify-content: space-between;
      gap: var(--space-6) var(--space-10);
      min-height: calc(var(--control-h) + 2 * var(--space-10) + 1px);
      padding: var(--space-10) var(--space-14);
      border-bottom: 1px solid var(--border);
    }
```

```css
    .actions { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); }
```

and directly after the `.body { padding: var(--space-14); }` line add:

```css
    /* v179 §3.3 -- one gap to the first row: the body's padding, never the
       padding plus whatever top margin the first projected element brings
       (a <p>, a <dl>, a nested heading). .panel > .body is this component's
       own structure, so the reach is exactly one level. */
    :host ::ng-deep .panel > .body > :first-child { margin-top: 0; }
```

- [ ] **Step 4: `sb-control-row` on the last baseline**

In `ControlRow`'s docstring replace the paragraph

```
 * **`flex-end`, and the reason matters.** A labelled control is label-band +
 * control-band; a bare button is control-band only. Aligning on the BOTTOM
 * edge is the only rule under which both land on the same line, whatever the
 * label does above it.
```

with

```
 * **`last baseline`, and the reason matters** (v179 §3.4; it was
 * `flex-end`). A labelled control is label-band + control-band; a bare
 * button is control-band only. Both END in a --control-h control with its
 * text centred, so their last baselines coincide exactly where their bottom
 * edges did -- the two still land on one line whatever the label does above.
 * Unlike `flex-end`, a plain text item in the row (the Versions "Running
 * now" label, a count, an N=) now sits on the controls' text line instead
 * of on their bottom border.
```

and in its styles change the `.row` rule's `align-items: flex-end;` to `align-items: last baseline;` (nothing else in the rule or the phone media block changes).

- [ ] **Step 5: `sb-panel-header`**

In `frontend/src/app/ui/panel-header.ts` replace the first two rules of the one-line `styles` string — `header { display:flex; align-items:center; justify-content:space-between; gap:var(--space-8); } .heading { display:flex; align-items:center; flex-wrap:wrap; gap:var(--space-6); }` — with:

```css
header { display:flex; flex-wrap:wrap; align-items:baseline; align-content:center; justify-content:space-between; gap:var(--space-6) var(--space-8); min-height:var(--control-h); } .heading { display:flex; align-items:baseline; flex-wrap:wrap; gap:var(--space-6); }
```

The rest of the string (`h2`, `.n,.all-time`, `.total`, `.table`, `.table:focus-visible`) is unchanged. Add above the `@Component` a one-line comment: `/* v179 §3.4: title, N=, total and the hint share the text baseline; the header is one control tall. */`.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
(cd "$WT/frontend" && npx ng test --watch=false --include src/app/ui/layout.spec.ts --include src/app/ui/panel-header.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts --include src/app/workspaces/analytics/tabs/overview.spec.ts)
```

Expected: all PASS (`overview.spec.ts` mounts the Analytics Equity `sb-panel-header`).

- [ ] **Step 7: Commit**

```bash
git -C "$WT" add frontend/src/app/ui/layout.ts frontend/src/app/ui/layout.spec.ts frontend/src/app/ui/panel-header.ts frontend/src/app/ui/panel-header.spec.ts
git -C "$WT" commit -m "feat(v179): panel headers one height on one baseline; control rows on the last baseline

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V179-4: `sb-stat-tile` single variant; Calendar totals migrated

**Model:** sonnet — one primitive's CSS, one workspace's template/CSS migration with three small formatters, a gallery demo and a workspace guard; captions and figures must survive the move.

**Files:**
- Modify: `frontend/src/app/ui/stat-tile.ts` (styles)
- Modify: `frontend/src/app/ui/stat-tile.spec.ts` (append a `describe`)
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts` (`.totals` markup ~l.111-124; imports ~l.12-16 and `imports: [...]` l.26; `totalsTone` ~l.570-578; `totalUnit()` ~l.634-641; styles ~l.333-409)
- Modify: `frontend/src/app/workspaces/calendar/calendar.spec.ts` (append a `describe`)
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts` (v85 primitives panel ~l.463-468; styles)
- Modify: `frontend/src/app/workspaces/gallery/gallery.spec.ts` (append a `describe`)
- Modify: `frontend/src/app/workspaces/workspace-consistency.spec.ts` (one new `it`)

`frontend/src/app/workspaces/calendar/day/calendar-day.ts` (ledger) needs **no change**: its seven tiles already sit in `.tiles { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)) }` with no override of the tile's inside; the new guard covers it.

**Interfaces:**
- Consumes: V179-1's `--font-num`; existing `StatTile` inputs (`label`, `value: string | null`, `sample`, `tone: StatTone`, `hint`, `secondary`, `trend`), `allSources()`, Calendar's `ABSENT`, `money`, `rMultiple`, `CalendarMetric`, `this.currency()`, `this.totalValue()`.
- Produces (ledger): the one stacked `sb-stat-tile` — `:host { display: block; height: 100%; min-width: 0; }`, a `.tile` that fills it, value/sample/secondary in `--font-num`, long labels wrap instead of widening the grid (V179-8's Partials repro starts from this); the `workspace-consistency.spec.ts` guard `never restyles the inside of a shared tile` (any `::ng-deep … sb-stat-tile|sb-metric-card` under `app/workspaces/` fails).

**Design (spec §2.3 stat tiles, §2.4 Calendar rows, §3.3 `sb-stat-tile`, §4 captions anti-goal).**
- **The tile.** Analytics/Risk's layout everywhere: label, value, secondary, `N=`, hint, stacked, left-aligned (`text-align: start`, so a centring parent cannot reach in). The host was `display: inline` (a custom element has no display of its own), so a grid row's stretch never reached the visible box and tiles in one row differed in height (Analytics "Total R" vs "ExpR"); now the host is a block at `height: 100%` and `.tile` fills it. `min-width: 0` plus `overflow-wrap: anywhere` on label, value and captions stops a long label ("Closed runners that reached TP…") from widening its grid track.
- **Calendar.** `.totals` mixed three `sb-metric-card`s (centred) and four `sb-stat-tile`s that `::ng-deep` forced inline (label and value on one line, value shrunk to `--text-table`) inside a fixed `grid-auto-rows: 4.5rem` — the 4px "Win rate" vs "Winning days" offset and the "BEST DAY +173.48 €" inline variant. All seven become the same `sb-stat-tile`; every `::ng-deep` rule and the fixed row height go. The grid keeps exactly 4 columns (2 below 640px): the partner asked for "at most 2 rows" on 2026-09-14 and seven tiles at four per row is two rows; `minmax(0, 1fr)` cannot overflow. Rows size to their content and stretch their tiles to one height.
- **No figure or caption lost.** The three metric cards become stat tiles with the same labels and the same figures, pre-formatted (a stat tile never formats): "Net this month" in the metric on show with its unit (`totalLabel()`), "Trades" (`tradesLabel()`), "Win rate" to one decimal as the card showed it (`monthWinRate()`). The four existing tiles keep their `[sample]` (`N=`) and tone. `calendarDigest()`/`calendarProblem()` are untouched.
- **Tone.** `sb-metric-card`'s `pnl` tone coloured any non-null value by sign — including a trade count and a win rate (a 33% win rate rendered green). `totalsTone` now returns a `StatTone`: by sign for `r` and `currency`, `neutral` for `trades`, `win_rate`, zero and loading.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/ui/stat-tile.spec.ts`; add the imports at the top next to the existing ones:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

```ts
describe('StatTile: one variant everywhere (v179 §3.3)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/stat-tile.ts'), 'utf8');
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  /** The rule whose selector starts a line, so `.value` is not `.pos .value`. */
  const rule = (selector: string) =>
    SOURCE.match(new RegExp(`(?:^|\\n)\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

  beforeEach(() => {
    preferenceValues = {};
    TestBed.configureTestingModule({ providers: [
      provideZonelessChangeDetection(),
      { provide: PreferencesStore, useValue: { values: () => preferenceValues } },
    ] });
  });

  it('fills its grid cell, so tiles in one row share a height', () => {
    for (const declaration of ['display: block', 'height: 100%', 'min-width: 0']) {
      expect(rule(':host')).toContain(declaration);
    }
    expect(rule('.tile')).toContain('height: 100%');
    expect(rule('.tile')).toContain('box-sizing: border-box');
    expect(rule('.tile')).toContain('min-width: 0');
  });

  it('stacks its parts left-aligned and has no inline or centred variant', () => {
    expect(rule('.tile')).toContain('flex-direction: column');
    expect(rule('.tile')).toContain('text-align: start');
    expect(SOURCE).not.toMatch(/justify-content:\s*center|flex-direction:\s*row/);
  });

  it('sets the value, the secondary and N= in the numeric face', () => {
    expect(rule('.value')).toContain('font-family: var(--font-num)');
    expect(SOURCE).toMatch(/\.sample, \.secondary \{ font-family: var\(--font-num\); \}/);
  });

  it('wraps a long label or caption instead of widening its track', () => {
    expect(rule('.label')).toContain('overflow-wrap: anywhere');
    expect(rule('.value')).toContain('overflow-wrap: anywhere');
  });

  it('renders label, value, secondary, N= and hint in that order, captions kept', () => {
    const el = render({ secondary: '+1,240.00 €', sample: 412, hint: 'Pre-tax, paper trades.' });
    expect([...el.children].map((child) => child.className.split(' ')[0]))
      .toEqual(['label', 'value', 'secondary', 'sample', 'hint']);
    expect(el.querySelector('.hint')!.textContent).toContain('Pre-tax, paper trades.');
  });
});
```

Append to `frontend/src/app/workspaces/calendar/calendar.spec.ts`; add the imports at the top:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

```ts
describe('Calendar totals: one stat tile (v179 §3.3)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/workspaces/calendar/calendar.ts'), 'utf8');

  it('renders every summary figure as the same stacked sb-stat-tile, in reading order', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();
    const totals = el(fixture).querySelector('.totals')!;
    expect(totals.querySelectorAll('sb-metric-card')).toHaveLength(0);
    expect([...totals.querySelectorAll('sb-stat-tile .label')].map((n) => n.textContent!.trim()))
      .toEqual(['Net this month', 'Trades', 'Win rate', 'Winning days', 'Average day', 'Best day', 'Worst day']);
  });

  it('keeps the figures the metric cards showed, units included', async () => {
    const fixture = seed();
    await fixture.whenStable();
    const calendar = fixture.componentInstance as unknown as {
      totalLabel(): string; tradesLabel(): string; monthWinRate(): string;
    };
    // RESPONSE.totals: net_pnl_amount -60, net_r -0.6, trade_count 3, win_rate 33.33.
    expect(calendar.totalLabel()).toContain('60');
    expect(calendar.tradesLabel()).toBe('3');
    expect(calendar.monthWinRate()).toBe('33.3%');
  });

  it('restyles no tile from outside and fixes no row height', () => {
    expect(SOURCE).not.toMatch(/::ng-deep/);
    expect(SOURCE).not.toMatch(/grid-auto-rows/);
    // The doc comment on currency() still names `MetricCard` in prose; the
    // element and its import are what must be gone.
    expect(SOURCE).not.toMatch(/sb-metric-card|from '\.\.\/\.\.\/ui\/metric-card'/);
  });
});
```

Append to `frontend/src/app/workspaces/gallery/gallery.spec.ts` (it already reads the gallery source as `GALLERY`):

```ts
describe('the gallery shows the one stat tile (v179 §3.3)', () => {
  it('lays the tiles in an auto-fit grid and shows the full stack once', () => {
    expect(GALLERY).toMatch(/\.stat-grid \{[^}]*repeat\(auto-fit, minmax\(10rem, 1fr\)\)/);
    const from = GALLERY.slice(GALLERY.indexOf('<div class="stat-grid">'));
    const block = from.slice(0, from.indexOf('</div>'));
    expect(block.match(/<sb-stat-tile/g)).toHaveLength(4);
    expect(block).toMatch(/secondary="[^"]+"[^>]*hint="[^"]+"/);
  });
});
```

In `frontend/src/app/workspaces/workspace-consistency.spec.ts` add the import at the top:

```ts
import { allSources } from '../ui/testing/all-sources';
```

and, inside `describe('workspace consistency (v85)', …)`, after the `sizes metric grids with auto-fit` test:

```ts
  it('never restyles the inside of a shared tile (v179 §3.3)', () => {
    // Calendar's ::ng-deep rules forced sb-stat-tile into an inline,
    // centred variant that read differently from every other page. A page
    // places tiles in a grid; the tile owns its inside. allSources(), not
    // SOURCES: it also reaches nested folders such as calendar/day/.
    const offenders = allSources()
      .filter(({ name }) => name.startsWith('app/workspaces/'))
      .filter(({ source }) => /::ng-deep[^{]*sb-(stat-tile|metric-card)/.test(source))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
(cd "$WT/frontend" && npx ng test --watch=false --include src/app/ui/stat-tile.spec.ts --include src/app/workspaces/calendar/calendar.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts)
```

Expected: FAIL — no `:host` rule, no `height`/`text-align`/`--font-num`/`overflow-wrap` in the tile; Calendar shows three `sb-metric-card`s, `totalLabel`/`tradesLabel`/`monthWinRate` are not functions, `::ng-deep` and `grid-auto-rows` present; no `.stat-grid`; the guard lists `app/workspaces/calendar/calendar.ts`. The order test already PASSES.

- [ ] **Step 3: The one tile**

In `frontend/src/app/ui/stat-tile.ts` replace the whole `styles` string with:

```ts
  styles: `
    /* v179 §3.3 -- the one tile, everywhere: label, value, secondary, N=,
       hint, stacked and left-aligned. The host is a block that fills its
       grid cell: a custom element is inline by default, and an inline host
       never receives the row's stretched height, which is why two tiles in
       one row used to differ in height. min-width: 0 and overflow-wrap let
       a long label wrap instead of widening its grid track. No page
       restyles the inside of a tile -- workspace-consistency.spec.ts fails
       a ::ng-deep into sb-stat-tile. */
    :host { display: block; height: 100%; min-width: 0; }
    .tile {
      display: flex;
      flex-direction: column;
      gap: 2px;
      height: 100%;
      box-sizing: border-box;
      min-width: 0;
      padding: var(--space-14);
      text-align: start;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--panel-radius);
    }
    .label {
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-faint);
      overflow-wrap: anywhere;
    }
    .value {
      font-family: var(--font-num);
      font-size: var(--text-metric);
      font-variant-numeric: tabular-nums;
      color: var(--text);
      overflow-wrap: anywhere;
    }
    .pos .value { color: var(--pos); }
    .neg .value { color: var(--neg); }
    .sample,
    .secondary,
    .hint {
      font-size: var(--text-micro);
      font-variant-numeric: tabular-nums;
      color: var(--text-faint);
      overflow-wrap: anywhere;
    }
    /* Figures in the numeric face; the hint is prose and stays in the UI font. */
    .sample, .secondary { font-family: var(--font-num); }
    .secondary { color: var(--text-secondary); }
    /* The second cue. Opacity alone would be a colour-only signal, which the
       plan forbids; the .flag span puts the same fact in words. */
    .thin .value { opacity: 0.62; }
    .thin .flag { font-style: italic; }
  `,
```

- [ ] **Step 4: Calendar — seven tiles, no overrides**

In `frontend/src/app/workspaces/calendar/calendar.ts`:

1. Imports: delete `import { MetricCard } from '../../ui/metric-card';`, change the stat-tile import to `import { MIN_SAMPLE_N, StatTile, StatTone } from '../../ui/stat-tile';`, and remove `MetricCard, ` from the component's `imports: [...]` array.

2. Template: replace the three `<sb-metric-card …/>` elements at the top of `<div class="totals">` (the four `sb-stat-tile` lines after them stay as they are) with:

```html
          <sb-stat-tile label="Net this month" [value]="totalLabel()" [tone]="totalsTone()" />
          <sb-stat-tile label="Trades" [value]="tradesLabel()" />
          <sb-stat-tile label="Win rate" [value]="monthWinRate()" />
```

3. Above `export class Calendar` add:

```ts
/** Metrics whose sign means up or down; a count or a rate never does. */
const SIGNED_METRICS: ReadonlySet<CalendarMetric> = new Set<CalendarMetric>(['r', 'currency']);
```

4. Replace the `totalsTone` computed (its doc comment included) with:

```ts
  /** Net this month's tone (v179): by sign for R and money; neutral for a
   *  trade count or a win rate -- the old metric card's `pnl` tone used to paint
   *  a 33% win rate green -- and neutral while loading, so a pending strip
   *  is not briefly coloured. */
  protected readonly totalsTone = computed<StatTone>(() => {
    const value = this.totalValue();
    if (value === null || value === undefined || value === 0) return 'neutral';
    if (!SIGNED_METRICS.has(this.store.metric())) return 'neutral';
    return value > 0 ? 'pos' : 'neg';
  });
```

5. Delete `protected totalUnit(): string { … }` (its only caller was the metric card). Directly after `totalValue()` add:

```ts
  /** "Net this month" as text in the metric on show. sb-stat-tile never
   *  formats a number (stat-tile.ts), so the unit travels in the string --
   *  what the old metric card's [unit] and [decimals] did before v179. */
  protected totalLabel(): string {
    const value = this.totalValue();
    return value === null || value === undefined ? ABSENT : this.metricText(value);
  }

  protected tradesLabel(): string {
    const count = this.store.totals()?.trade_count;
    return count === null || count === undefined ? ABSENT : String(count);
  }

  /** One decimal, as the Win rate card showed it ("33.3%"). */
  protected monthWinRate(): string {
    const rate = this.store.totals()?.win_rate;
    return rate === null || rate === undefined ? ABSENT : `${rate.toFixed(1)}%`;
  }

  private metricText(value: number): string {
    switch (this.store.metric()) {
      case 'r': return rMultiple(value);
      case 'currency': return money(value, this.currency(), 2);
      case 'win_rate': return `${value.toFixed(1)}%`;
      case 'trades': return String(value);
    }
  }
```

6. Styles: delete everything from the comment that starts `/* Exactly 4 columns, not auto-fit (2026-09-14):` through the end of the `:host ::ng-deep .totals sb-metric-card .value, :host ::ng-deep .totals sb-stat-tile .value { … }` rule (the line before `/* The calendar table's own panel, not .totals`), and put in its place:

```css
    /* Exactly 4 columns, 2 below sm -- on request (2026-09-14, "at most 2
       rows"): seven tiles at four per row is two rows. minmax(0, 1fr)
       cannot overflow. v179 §3.3: no fixed row height and no reaching into
       the tiles any more -- the 4.5rem row is what forced the inline
       label-and-value variant, and every tile here is now the same stacked
       sb-stat-tile as Analytics and Risk. A grid row stretches its tiles to
       one height on its own (stat-tile.ts fills its cell). */
    .totals {
      display: grid;
      gap: var(--space-14);
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    @media (max-width: 639px) {
      .totals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
```

7. Check: `grep -n "ng-deep\|grid-auto-rows\|sb-metric-card\|totalUnit" "$WT/frontend/src/app/workspaces/calendar/calendar.ts"` prints nothing.

- [ ] **Step 5: Gallery — show the one tile**

In `frontend/src/app/workspaces/gallery/gallery.ts`, in the v85 primitives panel replace

```html
      <sb-control-row>
        <sb-stat-tile label="Win rate" [value]="'68%'" [sample]="412" />
        <sb-stat-tile label="Payoff ratio" [value]="'1.80'" [sample]="7" tone="pos" />
        <sb-stat-tile label="Expectancy" [value]="null" />
      </sb-control-row>
```

with

```html
      <!-- v179 §3.3: the one stat tile -- label, value, secondary, N=, hint,
           stacked and left-aligned -- in an auto-fit grid whose rows share
           one height. -->
      <div class="stat-grid">
        <sb-stat-tile label="Win rate" [value]="'68%'" [sample]="412" />
        <sb-stat-tile label="Payoff ratio" [value]="'1.80'" [sample]="7" tone="pos" />
        <sb-stat-tile label="Expectancy" [value]="null" />
        <sb-stat-tile label="Net P&L" [value]="'+1,240.00 €'" secondary="+12.4R" [sample]="412" tone="pos" hint="Pre-tax, paper trades." />
      </div>
```

and add to its `styles`, after the `.tooltip-demo` rule:

```css
    /* v179 §3.3 -- the stat-tile grid every page uses. */
    .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: var(--space-14); }
```

(`ControlRow` stays imported: the gallery uses `sb-control-row` elsewhere.)

- [ ] **Step 6: Run the tests to verify they pass**

```bash
(cd "$WT/frontend" && npx ng test --watch=false --include src/app/ui/stat-tile.spec.ts --include src/app/workspaces/calendar/calendar.spec.ts --include src/app/workspaces/calendar/day/calendar-day.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/workspaces/analytics/tabs/overview.spec.ts --include src/app/workspaces/analytics/tabs/partials.spec.ts --include src/app/workspaces/risk/risk.spec.ts)
```

Expected: all PASS, including the existing Calendar summary-strip tests (`'60'`, `'3'`, `'33'`, "Winning days", "1 (50%)"). Overview, Partials and Risk mount `sb-stat-tile` and must not notice the new host rule.

- [ ] **Step 7: Commit**

```bash
git -C "$WT" add frontend/src/app/ui/stat-tile.ts frontend/src/app/ui/stat-tile.spec.ts
git -C "$WT" commit -m "feat(v179): one stacked sb-stat-tile that fills its grid cell

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "$WT" add frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/calendar.spec.ts frontend/src/app/workspaces/gallery/gallery.ts frontend/src/app/workspaces/gallery/gallery.spec.ts frontend/src/app/workspaces/workspace-consistency.spec.ts
git -C "$WT" commit -m "feat(v179): Calendar totals as seven stat tiles, no ::ng-deep; gallery shows the one tile

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

