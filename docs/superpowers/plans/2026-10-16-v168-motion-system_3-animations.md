# v168 Motion system, part 3: the shared-primitive animations (MO9..MO11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `grep -n "^### Task MO10:" -A 400 docs/superpowers/plans/2026-10-16-v168-motion-system_3-animations.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v168-motion-system-design.md`](../specs/2026-10-16-v168-motion-system-design.md) (its `## Amendments from the plan brief` bind and override earlier sections).
**Index:** [`2026-10-16-v168-motion-system_0-index.md`](2026-10-16-v168-motion-system_0-index.md): `## Global Constraints`, `## Where to work` (`$WT`, `$R`, the narrow-run command, `GATES`), `## Parallelisation` and the `## Task ledger` apply to every task below and are not repeated.

**Scope of this part:** skeleton shimmer and the `shape` input on `sb-async` (MO9); hover and press on the panel primitives and the primary button, G3 extended to `motion.css` (MO10); the sliding nav indicator (MO11). **MO12..MO14** (drawer and confirm-dialog in and out with the phone sheet; toasts; the flash refinement) moved whole to [`2026-10-16-v168-motion-system_3b-dialogs-toasts-flash.md`](2026-10-16-v168-motion-system_3b-dialogs-toasts-flash.md) at the 1500-line cap; ids, files and contracts are unchanged.

**Consumed from earlier parts (contracts from the index ledger):**
- MO3, `frontend/src/styles/motion.css`: the keyframes `sb-pulse-soft` (still used by `async.ts` until MO9), `sb-shimmer` (`from { background-position: 100% 0; } to { background-position: -100% 0; }`), `sb-pop-in`, `sb-fade-out`, `sb-drawer-in`, `sb-drawer-out`, `sb-sheet-in`, `sb-sheet-out`; the classes `.sb-lift` (with its `@media (hover: hover)` lift on `[data-motion] .sb-lift:hover { border-color: var(--border-strong); box-shadow: var(--panel-shadow-lift); }` and the `@media (hover: none)` inset tint), `.sb-pop-in`, `.sb-drawer-in`, `.sb-drawer-out` (phone: `sb-drawer dialog.sb-drawer-in` / `.sb-drawer-out` switch to the sheet keyframes), `.sb-fade-out`, the backdrop fade on `sb-drawer dialog[open]::backdrop` / `sb-confirm-dialog dialog[open]::backdrop`, the per-mode rules for `sb-async .skeleton-cell` and `sb-nav-indicator .nav-indicator`, and the Off/pending `animation: none` on every new class. `frontend/src/app/ui/motion-css.spec.ts` exports nothing but defines `KEYFRAMES`, `keyframeList`, `bodiesFor`, `blocksOf`, `rules` at module level, and the case `merges the four pulse copies by shape, each shape unchanged (amendment 7)`.
- MO4: `MotionService` (`mode`, `full`, `active`), `provideMotion`, `MotionStarts` from `frontend/src/app/ui/motion/motion.service.ts` and `frontend/src/app/ui/motion/motion-starts.ts`; every spec runs under `provideMotion('off')` unless it provides its own.
- MO2: `--panel-shadow-lift` (tier 3). v167: `--glow-accent`, `--btn-fill`, `--btn-fill-hover`, `--panel-radius`, `--radius-sm`, `--accent-soft`, the `.sb-panel` class on `layout.ts` `.panel`, `figure.ts`'s host and `chart-container.ts` `.frame`, and G3 `describe('G3: only the two elevation rules cast a shadow', ...)` in `primitives.spec.ts` with its `shadows(source)` helper.
- MO6: `motion.css` ends with the Off/Reduced fallback block. MO7: `shell.ts` imports `RouteEntrance`; `shell.html`'s `div.workspace-content` carries `sbRouteEntrance`. MO8: `figure.ts`, `stat-tile.ts`, `metric-card.ts` templates carry `[sbCountUp]`.

**Line numbers below are pre-v167.** v167 and parts 1-2 move lines around; every edit is anchored on quoted text, never on a line number alone. If an anchor is missing, stop and report it rather than guessing.

---

# Phase 3 -- The shared-primitive animations

### Task MO9: Skeleton shimmer and the `shape` input on `sb-async`

**Model:** sonnet — one keyframe swap and one input with three layouts

**Files:**
- Modify: `frontend/src/app/ui/async.ts` (doc comment `:22-25`, the skeleton template `:46-55`, `.skeleton-cell` CSS `:102-109`, the class's `rows`/`cols` computeds)
- Modify: `frontend/src/app/ui/async.spec.ts` (imports, `Host`, plus a new `describe`)
- Modify: `frontend/src/styles/motion.css` (delete the `sb-pulse-soft` keyframe line)
- Modify: `frontend/src/app/ui/motion-css.spec.ts` (`KEYFRAMES`, the pulse-merge case)

**Interfaces:**
- Consumes: MO3's `sb-shimmer` keyframe and its `[data-motion=reduced|off] sb-async .skeleton-cell { animation: none; }` rules (a static tint under Reduced and Off: with the animation gone, the gradient stays put).
- Produces: `export type SkeletonShape = 'table' | 'panel' | 'figure'` and `export function skeletonGrid(shape: SkeletonShape, rows: number, cols: number): string[][]` from `async.ts` (rows of per-cell modifier classes; `''` is a plain cell); `Async.shape = input<SkeletonShape>('table')`; the `.skeleton` element carries `shape-<shape>`; `.skeleton-cell` animates `sb-shimmer 1.6s linear infinite`. `sb-pulse-soft` no longer exists anywhere.

**Not in this task:** the branch order (error > loading > empty > content), `emptyReason`, `aria-busy` and the live region stay byte-identical (known-traps: empty tables are measured answers). No call site passes `shape` yet (v169 adopts it per workspace). Cell heights stay `var(--control-h)` in every shape, so the no-layout-shift guarantee holds.

- [ ] **Step 1: Write the failing specs**

In `frontend/src/app/ui/async.spec.ts`:

1. Replace the imports block at the top (lines 1-5) with:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { asyncInputs, Async, skeletonGrid, type AsyncEmptyReason, type SkeletonShape } from './async';
```

2. In the `Host` template, add `[shape]="shape"` on the line after `[skeletonCols]="2"`:

```html
      [skeletonCols]="2"
      [shape]="shape"
```

3. In `class Host`, add after `retried = 0;`:

```ts
  shape: SkeletonShape = 'table';
```

4. Append after the closing `});` of `describe('Async', ...)` (before `const at = () => ...`):

```ts
/* Spec v168 §3 #4: the skeleton was already shaped (rows x cols); v168 swaps
 * its pulse for a moving shimmer and adds `shape` for placeholders that are
 * not tables. Every cell keeps the table-row height, so nothing reflows when
 * the content replaces it. */
describe('Async skeleton shapes (v168 #4)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  const cells = (row: Element) => [...row.querySelectorAll('.skeleton-cell')];

  it('defaults to the table shape it always had', () => {
    const { el } = render({ loading: true });
    const skeleton = el.querySelector('.skeleton')!;
    expect(skeleton.classList).toContain('shape-table');
    expect(el.querySelectorAll('.skeleton-row').length).toBe(3);
    for (const row of el.querySelectorAll('.skeleton-row')) expect(cells(row).length).toBe(2);
  });

  it('draws a panel as a heading bar over full-width rows', () => {
    const { el } = render({ loading: true, shape: 'panel' });
    const rows = [...el.querySelectorAll('.skeleton-row')];
    expect(el.querySelector('.skeleton')!.classList).toContain('shape-panel');
    expect(rows.length).toBe(3);
    expect(cells(rows[0]).map((cell) => cell.className)).toEqual(['skeleton-cell head']);
    expect(rows.slice(1).map((row) => cells(row).length)).toEqual([1, 1]);
  });

  it('draws a figure as a label over a value', () => {
    const { el } = render({ loading: true, shape: 'figure' });
    const rows = [...el.querySelectorAll('.skeleton-row')];
    expect(el.querySelector('.skeleton')!.classList).toContain('shape-figure');
    expect(rows.map((row) => cells(row).map((cell) => cell.className))).toEqual([
      ['skeleton-cell label'],
      ['skeleton-cell value'],
    ]);
  });

  it('keeps aria-busy and the live region whatever the shape', () => {
    const { el } = render({ loading: true, shape: 'figure', announce: 'Loading' });
    expect(el.querySelector('sb-async')!.getAttribute('aria-busy')).toBe('true');
    expect(el.querySelectorAll('[aria-live]').length).toBe(1);
    expect(el.querySelector('.skeleton')!.getAttribute('aria-hidden')).toBe('true');
  });

  it('computes the grid as a pure table of shapes', () => {
    expect(skeletonGrid('table', 2, 3)).toEqual([['', '', ''], ['', '', '']]);
    expect(skeletonGrid('panel', 3, 4)).toEqual([['head'], [''], ['']]);
    expect(skeletonGrid('panel', 1, 4)).toEqual([['head']]);
    expect(skeletonGrid('figure', 6, 4)).toEqual([['label'], ['value']]);
  });

  it('shimmers with a moving gradient instead of pulsing (source text)', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/ui/async.ts'), 'utf8');
    const cell = source.match(/\.skeleton-cell\s*\{[^}]*\}/)![0];
    expect(cell).toContain('animation: sb-shimmer 1.6s linear infinite;');
    expect(cell).toContain('background-size: 200% 100%;');
    expect(cell).toContain('height: var(--control-h);');
    expect(source).not.toContain('sb-pulse-soft');
  });
});
```

In `frontend/src/app/ui/motion-css.spec.ts`:

5. In `const KEYFRAMES = [`, change the first moved line from

```ts
  'sb-pulse-soft', 'sb-pulse-dim', 'sb-pulse-blink', 'sb-spin', 'sb-route-spin', 'sb-scan-sweep',
```

to

```ts
  'sb-pulse-dim', 'sb-pulse-blink', 'sb-spin', 'sb-route-spin', 'sb-scan-sweep',
```

6. Replace the case `merges the four pulse copies by shape, each shape unchanged (amendment 7)` whole with:

```ts
  it('merges the pulse copies by shape, each shape unchanged (amendment 7)', () => {
    /* Four copies in three shapes before v168. The skeleton's soft pulse
     * (.45) became the shimmer in MO9, so two shapes remain. */
    const body = Object.fromEntries(keyframeList(MOTION));
    expect(body['sb-pulse-soft']).toBeUndefined();
    expect(body['sb-pulse-dim']).toBe('50% { opacity: 0.35; }');
    expect(body['sb-pulse-blink']).toBe('0%, 100% { opacity: 1; } 50% { opacity: 0.25; }');
    expect(body['sb-spin']).toBe('to { transform: rotate(360deg); }');
  });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/async.spec.ts --include src/app/ui/motion-css.spec.ts`
Expected: FAIL at build: `"skeletonGrid" is not exported by "src/app/ui/async.ts"` (and `SkeletonShape`). Once that compiles, `motion-css.spec.ts` fails `defines every keyframe exactly once, and no others` (`sb-pulse-soft` is extra) and the pulse case (`sb-pulse-soft` is still defined).

- [ ] **Step 3: Implement the shapes and the shimmer in `async.ts`**

In `frontend/src/app/ui/async.ts`:

1. Below `export type AsyncEmptyReason = 'no-data-yet' | 'measured-zero';` add:

```ts

/** The placeholder's outline: a table (default), a panel, or one figure. */
export type SkeletonShape = 'table' | 'panel' | 'figure';

/**
 * Rows of cell modifier classes for each shape (`''` is a plain cell). Every
 * cell keeps the table-row height (`--control-h`), so whatever replaces the
 * skeleton lands in the space it held and nothing reflows.
 */
const SKELETON_SHAPES: Record<SkeletonShape, (rows: number, cols: number) => string[][]> = {
  table: (rows, cols) => Array.from({ length: rows }, () => Array.from({ length: cols }, () => '')),
  panel: (rows) => [['head'], ...Array.from({ length: Math.max(rows - 1, 0) }, () => [''])],
  figure: () => [['label'], ['value']],
};

export function skeletonGrid(shape: SkeletonShape, rows: number, cols: number): string[][] {
  return SKELETON_SHAPES[shape](rows, cols);
}
```

2. In the class doc comment, replace the paragraph

```ts
 * The loading branch is a SHAPED skeleton, not a spinner: it occupies the
 * geometry the loaded content will, so nothing reflows at the moment the
 * reader starts reading. A spinner swapped for a table moves every element on
 * the page.
```

with

```ts
 * The loading branch is a SHAPED skeleton, not a spinner: it occupies the
 * geometry the loaded content will, so nothing reflows at the moment the
 * reader starts reading. A spinner swapped for a table moves every element on
 * the page. `shape` picks the outline (a table by default, a panel, or a
 * single figure); a moving shimmer marks it as loading (spec v168 §3 #4),
 * frozen to a static tint under Motion = Reduced or Off (styles/motion.css).
```

3. Replace the skeleton block of the template

```html
      <div class="skeleton" aria-hidden="true">
        @for (row of rows(); track $index) {
          <div class="skeleton-row">
            @for (col of cols(); track $index) {
              <span class="skeleton-cell"></span>
            }
          </div>
        }
      </div>
```

with

```html
      <div class="skeleton" [class]="'shape-' + shape()" aria-hidden="true">
        @for (row of grid(); track $index) {
          <div class="skeleton-row">
            @for (cell of row; track $index) {
              <span class="skeleton-cell" [class]="cell"></span>
            }
          </div>
        }
      </div>
```

(Angular merges a static `class` with a `[class]` binding, so `skeleton` and `skeleton-cell` stay.)

4. In `styles`, replace the `.skeleton-cell` rule (after MO3 it animates `sb-pulse-soft 1.4s var(--ease-out) infinite`; MO3 already deleted the local `@keyframes pulse` line) with the block below. Keep the `border-radius` line exactly as v167 left it (it may read `var(--chip-radius)` or `var(--radius-sm)` by now; copy whatever is there instead of the `var(--radius-chip)` shown here).

```css
    /* A highlight band sweeps across a static base (spec v168 §3 #4). Only
       background-position moves, so it costs no layout or paint of
       neighbours. Under Motion = Reduced or Off the animation is dropped
       (styles/motion.css) and the gradient rests as a static tint. */
    .skeleton-cell {
      flex: 1;
      height: var(--control-h);
      border-radius: var(--radius-chip);
      background: linear-gradient(90deg, var(--surface-raised) 30%,
        color-mix(in srgb, var(--surface-raised) 55%, var(--border-strong)) 50%,
        var(--surface-raised) 70%);
      background-size: 200% 100%;
      animation: sb-shimmer 1.6s linear infinite;
    }
    .skeleton-cell.head { flex: 0 0 40%; }
    .skeleton-cell.label { flex: 0 0 35%; }
    .skeleton-cell.value { flex: 0 0 65%; }
```

5. In `class Async`, add after `readonly skeletonCols = input(4);`:

```ts
  /** The placeholder's outline while loading (v168 §3 #4). */
  readonly shape = input<SkeletonShape>('table');
```

and replace

```ts
  protected readonly rows = computed(() => Array.from({ length: this.skeletonRows() }));
  protected readonly cols = computed(() => Array.from({ length: this.skeletonCols() }));
```

with

```ts
  protected readonly grid = computed(() => skeletonGrid(this.shape(), this.skeletonRows(), this.skeletonCols()));
```

- [ ] **Step 4: Drop `sb-pulse-soft` from `motion.css`**

In `frontend/src/styles/motion.css`, delete the line

```css
@keyframes sb-pulse-soft { 50% { opacity: 0.45; } }                            /* sb-async skeleton */
```

and change the comment line just above the remaining pulse keyframes from

```css
/* `pulse` was declared four times in three shapes (spec amendment 7). */
```

to

```css
/* `pulse` was declared four times in three shapes (spec amendment 7); the
   skeleton's soft one became the shimmer (MO9), so two shapes remain. */
```

Then confirm nothing else names it:

```bash
git -C $WT grep -n "sb-pulse-soft" -- frontend/src
```

Expected: only `frontend/src/app/ui/async.spec.ts` (its `not.toContain` assertion) and `frontend/src/app/ui/motion-css.spec.ts` (its `toBeUndefined` case).

- [ ] **Step 5: Run the specs and the gates**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/async.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/motion-home.spec.ts --include src/app/ui/motion-css.spec.ts`
Expected: `Tests  N passed (N)`, 0 failed. If the v167 colour gate in `primitives.spec.ts` flags the gradient, a literal colour slipped in: every stop must be a `var(--…)` or a `color-mix` of two. Quote the verdict line.

- [ ] **Step 6: Commit**

```bash
git -C $WT add frontend/src/app/ui/async.ts frontend/src/app/ui/async.spec.ts frontend/src/styles/motion.css frontend/src/app/ui/motion-css.spec.ts
git -C $WT commit -m "feat(ui): v168 skeleton shimmer and sb-async shape input (MO9)

The skeleton's pulse becomes a moving-gradient shimmer (sb-shimmer, 1.6s
linear, background-position only), frozen to a static tint under Motion =
Reduced or Off. New shape input: table (default, unchanged), panel (heading
bar over full-width rows), figure (label over value); every cell keeps the
--control-h row height. sb-pulse-soft, now unused, leaves motion.css.
Branch order, emptyReason, aria-busy and the live region are unchanged.

<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO10: Hover and press: `.sb-lift` on panel primitives, primary-button brightness and glow, `:active` press; G3 extended to `motion.css`

**Model:** sonnet — class adoption on five primitives plus one gate extension

**Files:**
- Modify: `frontend/src/app/ui/layout.ts` (the `sb-panel` template's `<section class="panel sb-panel">`)
- Modify: `frontend/src/app/ui/figure.ts` (the `sb-figure` `host: { class: 'sb-panel' }`)
- Modify: `frontend/src/app/ui/chart-container.ts` (the `<figure class="frame …">` element)
- Modify: `frontend/src/app/ui/stat-tile.ts` (`<div class="tile" …>`)
- Modify: `frontend/src/app/ui/metric-card.ts` (`<div class="card">`)
- Modify: `frontend/src/app/ui/button.ts` (`:host` transition, the `.primary` hover rule, a new `:active` rule and a `@media (hover: none)` block)
- Modify: `frontend/src/app/ui/button.spec.ts` (one new `describe`)
- Modify: `frontend/src/app/ui/primitives.spec.ts` (G3's doc comment, one G3 case, one new `describe`)
- Modify: `frontend/src/styles/motion.css` (the primary-button glow and the Reduced press rule, inside the `#5 hover and press` section)

**Interfaces:**
- Consumes: MO3's `.sb-lift` rules in `motion.css` (transition, `@media (hover: hover)` lift with `var(--panel-shadow-lift)`, `@media (hover: none)` inset `--accent-soft` tint); MO2's `--panel-shadow-lift`; v167's `--glow-accent`, `--btn-fill-hover`, `.sb-panel` on the three panel primitives, G3's `shadows(source)` helper in `primitives.spec.ts`. MO8's templates on `figure.ts`, `stat-tile.ts`, `metric-card.ts` (this task only adds a class beside them).
- Produces: class `sb-lift` on `layout.ts` `.panel`, `figure.ts`'s host, `chart-container.ts` `.frame`, `stat-tile` `.tile`, `metric-card` `.card`. `button.ts`: `:host(.primary:not([disabled]):hover) { background: var(--btn-fill-hover); filter: brightness(1.1); }`, `:host(:not([disabled]):active) { transform: scale(.97); }`, `@media (hover: none) { :host(:not([disabled]):active) { box-shadow: inset 0 0 0 100vmax var(--accent-soft); } }`. `motion.css`: `@media (hover: hover) { button[sb-button].primary:not([disabled]):hover { box-shadow: var(--glow-accent); } }` and `[data-motion=reduced] button[sb-button]:not([disabled]):active { transform: none; }`. G3: `motion.css`'s non-inset shadows equal exactly `['var(--panel-shadow-lift)', 'var(--glow-accent)']`.

**Not in this task:** `metric-chip` gets no lift (a chip is inline text, not a card). Workspace-specific cards adopt `.sb-lift` in v169. Gradient backgrounds do not transition (v167 §3), so the button's hover is carried by `filter` and the glow, never by a background transition. `motion-css.spec.ts` is not edited: its `lifts on hover only where hover exists` case still sees exactly one `[data-motion] .sb-lift:hover` and one `translateY(-2px)`.

- [ ] **Step 1: Write the failing G3 case and the adoption gate**

In `frontend/src/app/ui/primitives.spec.ts`:

1. In the doc comment above `describe('G3: only the two elevation rules cast a shadow', ...)`, replace its first paragraph

```ts
 * G3 -- a non-inset box-shadow appears in exactly two rules, both global:
 * .sb-panel (in flow, --panel-shadow) and .elev-overlay (out of flow,
 * --shadow-overlay), in that order in styles.css.
```

with

```ts
 * G3 -- a non-inset box-shadow appears in exactly two rules of styles.css,
 * .sb-panel (in flow, --panel-shadow) and .elev-overlay (out of flow,
 * --shadow-overlay), in that order, plus exactly two interaction shadows in
 * styles/motion.css (spec v168 §3 #5): the hover lift (--panel-shadow-lift)
 * and the primary button's hover glow (--glow-accent), in that order. No
 * component casts one itself.
```

2. Inside that `describe`, after the case `styles.css casts exactly two, both tokens, the panel first`, add:

```ts
  it('motion.css casts exactly the hover lift and the primary-button glow (v168 #5)', () => {
    const motion = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '');
    expect(shadows(motion)).toEqual(['var(--panel-shadow-lift)', 'var(--glow-accent)']);
  });
```

3. Append at the end of the file:

```ts
/* Spec v168 §3 #5: the shared panels and cards lift on hover. The class only
 * marks them; styles/motion.css owns the motion (hover devices only, the
 * translate under Motion = On only). Asserted as source text: the class is
 * static markup, and jsdom has no hover. */
describe('v168 #5: panels and cards carry .sb-lift', () => {
  const source = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
  const CASES: [string, RegExp][] = [
    ['src/app/ui/layout.ts', /<section class="[^"]*\bpanel\b[^"]*\bsb-lift\b[^"]*">/],
    ['src/app/ui/figure.ts', /host: \{[^}]*class: '[^']*\bsb-panel sb-lift\b[^']*'/],
    ['src/app/ui/chart-container.ts', /<figure class="[^"]*\bframe\b[^"]*\bsb-lift\b[^"]*"/],
    ['src/app/ui/stat-tile.ts', /<div class="tile sb-lift"/],
    ['src/app/ui/metric-card.ts', /<div class="card sb-lift">/],
  ];
  for (const [path, marker] of CASES) {
    it(`${path} marks its surface`, () => expect(source(path)).toMatch(marker));
  }
});
```

(`readFileSync` and `join` are already imported at the top of `primitives.spec.ts`; G3 uses them.)

- [ ] **Step 2: Write the failing button cases**

Append to the end of `frontend/src/app/ui/button.spec.ts`:

```ts
/* Spec v168 §3 #5. The primary gradient cannot transition (v167 §3), so
 * hover brightens it with a filter and motion.css adds the accent glow; every
 * enabled button presses to .97; on touch the press also tints. */
describe('v168 #5: hover and press', () => {
  const MOTION = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\s+/g, ' ');

  it('brightens the primary gradient on hover', () => {
    const hover = rule(':host(.primary:not([disabled]):hover)');
    expect(hover).toContain('background: var(--btn-fill-hover)');
    expect(hover).toContain('filter: brightness(1.1)');
  });

  it('presses every enabled button to .97', () => {
    expect(rule(':host(:not([disabled]):active)')).toContain('transform: scale(.97)');
  });

  it('transitions the press and the brightness, not the gradient', () => {
    const host = rule(':host');
    expect(host).toContain('transform var(--dur-instant) var(--ease-out)');
    expect(host).toContain('filter var(--dur-base) var(--ease-out)');
  });

  it('tints the press on touch with an inset, so it is not elevation', () => {
    const block = SOURCE.match(/@media \(hover: none\) \{([\s\S]*?)\n    \}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain(':host(:not([disabled]):active) { box-shadow: inset 0 0 0 100vmax var(--accent-soft); }');
  });

  it('casts no elevation shadow itself: the glow lives in motion.css', () => {
    const own = [...SOURCE.matchAll(/box-shadow:\s*([^;]+);/g)]
      .map(([, value]) => value.trim())
      .filter((value) => !value.startsWith('inset'));
    expect(own).toEqual([]);
    expect(MOTION).toContain(
      '@media (hover: hover) { button[sb-button].primary:not([disabled]):hover { box-shadow: var(--glow-accent); } }',
    );
  });

  it('does not scale the press under Motion = Reduced', () => {
    expect(MOTION).toContain('[data-motion=reduced] button[sb-button]:not([disabled]):active { transform: none; }');
  });
});
```

(`readFileSync`, `join`, `SOURCE` and `rule` are already defined at module level in `button.spec.ts`. Note `rule(':host')` returns the first `:host {…}` block, the base rule at the top of the styles.)

- [ ] **Step 3: Run them to verify they fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/button.spec.ts`
Expected: FAIL. G3's new case gets `['var(--panel-shadow-lift)']` (no glow yet); the five `marks its surface` cases fail; in `button.spec.ts` every new case fails except `casts no elevation shadow itself`, which fails on its `MOTION` half.

- [ ] **Step 4: Add `.sb-lift` to the five surfaces**

Each is a static class added to markup that already exists; nothing else on those lines changes.

1. `frontend/src/app/ui/layout.ts`: `<section class="panel sb-panel">` becomes `<section class="panel sb-panel sb-lift">`.
2. `frontend/src/app/ui/figure.ts`: in the `sb-figure` `@Component` (not `sb-figure-strip`), `host: { class: 'sb-panel' }` becomes `host: { class: 'sb-panel sb-lift' }`. If v167 wrote the host object with more keys, change only the `class` value.
3. `frontend/src/app/ui/chart-container.ts`: in the `<figure class="frame …"` start tag, add `sb-lift` right after `sb-panel` inside the same `class` attribute (for example `<figure class="frame sb-panel sb-lift" [style.height.px]="height()">`).
4. `frontend/src/app/ui/stat-tile.ts`: `<div class="tile" [class.thin]="thin()" [class]="tone()">` becomes `<div class="tile sb-lift" [class.thin]="thin()" [class]="tone()">`. (The `[class]` binding merges with the static classes; it does not remove them.)
5. `frontend/src/app/ui/metric-card.ts`: `<div class="card">` becomes `<div class="card sb-lift">`.

None of the five rules declares its own `transition` (checked in the brief: only `layout.ts`'s tab rules do), so `.sb-lift`'s transition from `motion.css` applies unopposed.

- [ ] **Step 5: Press and hover on `button.ts`**

In `frontend/src/app/ui/button.ts` `styles`:

1. In the base `:host { … }` rule, replace

```css
      transition: background var(--transition), border-color var(--transition),
        color var(--transition);
```

with

```css
      transition: background var(--transition), border-color var(--transition),
        color var(--transition), filter var(--dur-base) var(--ease-out),
        transform var(--dur-instant) var(--ease-out), box-shadow var(--dur-base) var(--ease-out);
```

2. Replace v167's hover line

```css
    :host(.primary:not([disabled]):hover) { background: var(--btn-fill-hover); }
```

with

```css
    /* v168 §3 #5: a gradient cannot transition, so the hover's change is
       carried by brightness (which can) and by the accent glow that
       styles/motion.css casts -- a component never casts its own elevation
       shadow (primitives.spec.ts G3). */
    :host(.primary:not([disabled]):hover) { background: var(--btn-fill-hover); filter: brightness(1.1); }
```

3. Directly after the `:host([disabled]) { opacity: 0.45; cursor: default; }` line, add:

```css
    /* Press (v168 §3 #5), every device. On touch, where nothing hovers, the
       press also tints; an inset shadow is a fill, not elevation, so G3
       does not count it. */
    :host(:not([disabled]):active) { transform: scale(.97); }
    @media (hover: none) {
      :host(:not([disabled]):active) { box-shadow: inset 0 0 0 100vmax var(--accent-soft); }
    }
```

Keep the `@media (hover: none) {` block's closing brace on its own line indented four spaces, as above: the spec's block regex ends on `\n    }`.

- [ ] **Step 6: The glow and the Reduced press in `motion.css`**

In `frontend/src/styles/motion.css`, in the `-- #5 hover and press --` section, directly after the closing `}` of the existing `@media (hover: none) { [data-motion] .sb-lift:active { … } }` block (and before the `-- #7 drawer, dialog, toast --` banner), add:

```css
/* The primary button's hover glow (#5). Cast here, after the lift, because
   no component casts an elevation shadow (primitives.spec.ts G3: this file's
   two are the lift and this glow, in that order). Mode-agnostic: a glow is
   colour, not motion. Under Reduced the press does not scale. */
@media (hover: hover) {
  button[sb-button].primary:not([disabled]):hover { box-shadow: var(--glow-accent); }
}
[data-motion=reduced] button[sb-button]:not([disabled]):active { transform: none; }
```

`button[sb-button].primary:not([disabled]):hover` (0,4,1) out-ranks the component's emulated `:host(...)` rules, and the reduced rule (0,4,1) out-ranks `[_nghost-…]:not([disabled]):active` (0,3,0), so neither needs `!important`.

- [ ] **Step 7: Run the specs and the gates**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/button.spec.ts --include src/app/ui/figure.spec.ts --include src/app/ui/stat-tile.spec.ts --include src/app/ui/chart-container.spec.ts --include src/app/ui/layout.spec.ts --include src/app/ui/display.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/motion-home.spec.ts --include src/app/ui/motion-css.spec.ts`
Expected: `Tests  N passed (N)`, 0 failed. A failure in `elevation.spec.ts` naming `.sb-panel` means a class edit replaced `sb-panel` instead of adding beside it. Quote the verdict line.

- [ ] **Step 8: Check the component style budget**

Run: `npm --prefix $WT/frontend exec -- ng build --configuration development`
Expected: build succeeds; no `anyComponentStyle` budget warning names `button.ts` (warn 5 kB).

- [ ] **Step 9: Commit**

```bash
git -C $WT add frontend/src/app/ui/layout.ts frontend/src/app/ui/figure.ts frontend/src/app/ui/chart-container.ts frontend/src/app/ui/stat-tile.ts frontend/src/app/ui/metric-card.ts frontend/src/app/ui/button.ts frontend/src/app/ui/button.spec.ts frontend/src/app/ui/primitives.spec.ts frontend/src/styles/motion.css
git -C $WT commit -m "feat(ui): v168 hover lift on panels and cards, primary-button glow and press (MO10)

.sb-lift joins .sb-panel on sb-panel, sb-figure and sb-chart-container and
marks sb-stat-tile and sb-metric-card; motion.css lifts them on hover
devices only (translate under Motion = On only). The primary button
brightens on hover (filter, since the v167 gradient cannot transition) and
motion.css casts its --glow-accent; every enabled button presses to .97,
tinted with --accent-soft on touch, unscaled under Reduced. G3 now holds
motion.css to exactly the lift and the glow, in that order.

<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO11: Sliding nav indicator in the sidebar

**Model:** sonnet — one shell component with guarded ResizeObserver and router wiring

**Files:**
- Create: `frontend/src/app/shell/nav-indicator.ts`
- Create: `frontend/src/app/shell/nav-indicator.spec.ts`
- Modify: `frontend/src/app/shell/shell.html` (one element inside `<nav class="sidebar">`)
- Modify: `frontend/src/app/shell/shell.css` (`.nav a.active` loses its rail; host placement of `sb-nav-indicator`)
- Modify: `frontend/src/app/shell/shell.ts` (`imports` array)
- Modify: `frontend/src/app/shell/shell.spec.ts` (**not in the ledger's file list**: its case `marks the active entry with an accent rail rather than colour alone` asserts `border-left` on `.nav a.active`, which this task removes by design; MO5 edited this file earlier and MO16 edits it later, both serialised with MO11, so no parallel task collides)

**Interfaces:**
- Consumes: MO3's `[data-motion=on] sb-nav-indicator .nav-indicator { transition: transform calc(350ms * var(--motion-scale)) var(--ease-spring), opacity var(--dur-base) var(--ease-out); }` and `[data-motion=reduced] sb-nav-indicator .nav-indicator { transition: opacity var(--dur-base) var(--ease-out); }` (Off and pending: no transition, the indicator jumps). `Router` and `NavigationEnd` from `@angular/router`. MO7's edits to `shell.ts` (`RouteEntrance` in `imports`) and `shell.html` (`sbRouteEntrance` on `div.workspace-content`) stay as they are.
- Produces: `export interface IndicatorBox { top: number; height: number }`; `export function indicatorBox(container: HTMLElement): IndicatorBox | null` (first `.nav a.active` inside `container`; `top` = link rect top − container rect top − `container.clientTop` + `container.scrollTop`; `height` = link rect height; `null` when no link is active); `@Component({ selector: 'sb-nav-indicator' }) export class NavIndicator` rendering `<span class="nav-indicator" aria-hidden="true">` positioned by `transform: translateY(<top>px)` and `height`, hidden (`opacity: 0`) without an active link; it recomputes after first render, after every `NavigationEnd` (on the next macrotask, because `RouterLinkActive` sets `active` in a microtask), and from a guarded `ResizeObserver` over its parent `.sidebar`, every `.nav` list and every `.nav a`. MO16 does not touch it.

**Not in this task:** the tint and weight of `.nav a.active` stay (two of the three cues); only the per-link `border-left-color` rail moves into the single indicator. The `.nav a { border-left: 2px solid transparent; }` reservation stays so link geometry does not shift. No new token.

- [ ] **Step 1: Write the failing component spec**

Create `frontend/src/app/shell/nav-indicator.spec.ts`:

```ts
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { IndicatorBox, NavIndicator, indicatorBox } from './nav-indicator';

/** Pin an element's rect: jsdom lays nothing out, so every rect is zero. */
function rect(element: Element, top: number, height: number): void {
  vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({
    top, height, bottom: top + height, left: 0, right: 100, width: 100, x: 0, y: top, toJSON: () => ({}),
  } as DOMRect);
}

@Component({ template: '' })
class Blank {}

@Component({
  imports: [NavIndicator],
  template: `
    <nav class="sidebar">
      <sb-nav-indicator />
      <ul class="nav"><li><a class="first">One</a></li><li><a class="second">Two</a></li></ul>
      <ul class="nav"><li><a class="third">Three</a></li></ul>
    </nav>
  `,
})
class Host {}

describe('indicatorBox (v168 §3 #6)', () => {
  afterEach(() => vi.restoreAllMocks());

  function sidebar(): HTMLElement {
    const nav = document.createElement('nav');
    nav.innerHTML = '<ul class="nav"><li><a>One</a></li><li><a class="active">Two</a></li></ul>';
    document.body.append(nav);
    return nav;
  }

  it('measures the active link against the sidebar, scroll included', () => {
    const nav = sidebar();
    rect(nav, 100, 800);
    rect(nav.querySelector('a.active')!, 260, 36);
    Object.defineProperty(nav, 'scrollTop', { value: 40, configurable: true });
    expect(indicatorBox(nav)).toEqual<IndicatorBox>({ top: 200, height: 36 });
    nav.remove();
  });

  it('is null when no link is active', () => {
    const nav = sidebar();
    nav.querySelector('a.active')!.classList.remove('active');
    expect(indicatorBox(nav)).toBeNull();
    nav.remove();
  });
});

describe('NavIndicator (v168 §3 #6)', () => {
  let originalObserver: unknown;

  beforeEach(() => {
    originalObserver = (globalThis as { ResizeObserver?: unknown }).ResizeObserver;
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: 'a', component: Blank }, { path: 'b', component: Blank }]),
      ],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    (globalThis as { ResizeObserver?: unknown }).ResizeObserver = originalObserver;
  });

  async function mount() {
    const fixture = TestBed.createComponent(Host);
    const el = fixture.nativeElement as HTMLElement;
    const nav = el.querySelector<HTMLElement>('nav.sidebar')!;
    rect(nav, 0, 800);
    rect(el.querySelector('a.first')!, 80, 32);
    rect(el.querySelector('a.second')!, 114, 32);
    rect(el.querySelector('a.third')!, 220, 40);
    el.querySelector('a.second')!.classList.add('active');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const bar = () => el.querySelector<HTMLElement>('sb-nav-indicator .nav-indicator')!;
    return { fixture, el, bar };
  }

  it('renders one decorative bar on the active link after first render', async () => {
    const { el, bar } = await mount();
    expect(el.querySelectorAll('.nav-indicator').length).toBe(1);
    expect(bar().getAttribute('aria-hidden')).toBe('true');
    expect(bar().style.transform).toBe('translateY(114px)');
    expect(bar().style.height).toBe('32px');
    expect(bar().classList).not.toContain('hidden');
  });

  it('follows the active link after a navigation', async () => {
    const { fixture, el, bar } = await mount();
    el.querySelector('a.second')!.classList.remove('active');
    el.querySelector('a.third')!.classList.add('active');
    await TestBed.inject(Router).navigateByUrl('/b');
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();
    expect(bar().style.transform).toBe('translateY(220px)');
    expect(bar().style.height).toBe('40px');
  });

  it('hides when nothing is active', async () => {
    const { fixture, el, bar } = await mount();
    el.querySelector('a.second')!.classList.remove('active');
    await TestBed.inject(Router).navigateByUrl('/a');
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();
    expect(bar().classList).toContain('hidden');
  });

  it('works without ResizeObserver (jsdom has none)', async () => {
    (globalThis as { ResizeObserver?: unknown }).ResizeObserver = undefined;
    await expect(mount()).resolves.toBeTruthy();
  });

  it('observes the sidebar, every nav list and every link, and remeasures on a resize', async () => {
    const observed: Element[] = [];
    let fire: () => void = () => undefined;
    const disconnect = vi.fn();
    class FakeObserver {
      constructor(callback: () => void) { fire = callback; }
      observe(target: Element) { observed.push(target); }
      disconnect() { disconnect(); }
    }
    vi.stubGlobal('ResizeObserver', FakeObserver);
    const { fixture, el, bar } = await mount();
    expect(observed).toEqual([
      el.querySelector('nav.sidebar'),
      ...el.querySelectorAll('.nav'),
      ...el.querySelectorAll('.nav a'),
    ]);
    rect(el.querySelector('a.second')!, 130, 36);
    fire();
    fixture.detectChanges();
    expect(bar().style.transform).toBe('translateY(130px)');
    expect(bar().style.height).toBe('36px');
    fixture.destroy();
    expect(disconnect).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Rewrite the shell's active-rail case**

In `frontend/src/app/shell/shell.spec.ts`, replace the whole case `it('marks the active entry with an accent rail rather than colour alone', () => { … });` with:

```ts
  it('marks the active entry with a rail plus tint and weight, not colour alone', () => {
    // v168 §3 #6: the rail is one sliding sb-nav-indicator in the sidebar,
    // no longer a per-link border; the active link keeps the tint and the
    // weight, so the state still has three cues.
    const f = TestBed.createComponent(Shell);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelectorAll('.sidebar > sb-nav-indicator').length).toBe(1);
    const styles = [...document.styleSheets]
      .flatMap((sheet) => { try { return [...sheet.cssRules]; } catch { return []; } })
      .map((rule) => rule.cssText);
    // Not a single `.includes('.nav a.active')` -- emulated encapsulation
    // inserts an `[_ngcontent-*]` attribute between `.nav` and `a.active`.
    const active = styles.filter((text) => text.includes('.nav') && text.includes('a.active'));
    expect(active.some((text) => text.includes('background') && text.includes('font-weight'))).toBe(true);
    expect(active.some((text) => text.includes('border-left-color'))).toBe(false);
  });
```

- [ ] **Step 3: Run both to verify they fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/shell/nav-indicator.spec.ts --include src/app/shell/shell.spec.ts`
Expected: FAIL at build: `Could not resolve "./nav-indicator"`. With a stub file it would fail the new shell case (`sb-nav-indicator` count 0, and `border-left-color` still on `.nav a.active`).

- [ ] **Step 4: Create the component**

Create `frontend/src/app/shell/nav-indicator.ts`:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs';

/** Where the bar sits, in the sidebar's scrolled coordinate space. */
export interface IndicatorBox {
  top: number;
  height: number;
}

/**
 * The active link's box relative to `container` (the scrolling `.sidebar`):
 * rect difference, minus the container's top border, plus its scroll, so the
 * bar scrolls with the links. `null` when no link is active.
 */
export function indicatorBox(container: HTMLElement): IndicatorBox | null {
  const link = container.querySelector<HTMLElement>('.nav a.active');
  if (!link) return null;
  const outer = container.getBoundingClientRect();
  const inner = link.getBoundingClientRect();
  return { top: inner.top - outer.top - container.clientTop + container.scrollTop, height: inner.height };
}

/**
 * One sliding rail for the active nav entry (spec v168 §3 #6), replacing the
 * per-link left border. It lives in `.sidebar`, not in a `.nav` list, because
 * the nav is three lists with group labels between them; the shell places
 * the host (shell.css) and this component only moves the bar.
 *
 * It remeasures after first render, after every navigation, and whenever the
 * sidebar, a list or a link changes size: a sidebar collapse, a text-size
 * change (--text-scale) and a list growing all move the active link without
 * a navigation. The bar declares no transition here; styles/motion.css gives
 * it a spring under Motion = On and a fade under Reduced, and under Off it
 * jumps.
 */
@Component({
  selector: 'sb-nav-indicator',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="nav-indicator" aria-hidden="true" [class.hidden]="!box()"
    [style.transform]="'translateY(' + (box()?.top ?? 0) + 'px)'"
    [style.height.px]="box()?.height ?? 0"></span>`,
  styles: `
    .nav-indicator {
      position: absolute;
      top: 0;
      left: 0;
      width: 2px;
      background: var(--accent);
      pointer-events: none;
    }
    .nav-indicator.hidden { opacity: 0; }
  `,
})
export class NavIndicator {
  protected readonly box = signal<IndicatorBox | null>(null);

  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  private readonly destroyRef = inject(DestroyRef);
  private pending: ReturnType<typeof setTimeout> | undefined;

  constructor() {
    inject(Router).events.pipe(
      filter((event) => event instanceof NavigationEnd),
      takeUntilDestroyed(),
    ).subscribe(() => {
      // RouterLinkActive sets `active` in a microtask after NavigationEnd;
      // a macrotask runs after it.
      clearTimeout(this.pending);
      this.pending = setTimeout(() => this.measure(), 0);
    });
    this.destroyRef.onDestroy(() => clearTimeout(this.pending));
    afterNextRender(() => {
      this.measure();
      this.observe();
    });
  }

  private measure(): void {
    const container = this.host.parentElement;
    this.box.set(container ? indicatorBox(container) : null);
  }

  /** jsdom (and very old browsers) have no ResizeObserver: then only navigations remeasure. */
  private observe(): void {
    const container = this.host.parentElement;
    if (!container || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => this.measure());
    observer.observe(container);
    container.querySelectorAll('.nav').forEach((list) => observer.observe(list));
    container.querySelectorAll('.nav a').forEach((link) => observer.observe(link));
    this.destroyRef.onDestroy(() => observer.disconnect());
  }
}
```

- [ ] **Step 5: Mount it in the shell and drop the per-link rail**

1. `frontend/src/app/shell/shell.html`: directly after the opening tag `<nav class="sidebar" [attr.aria-hidden]="overlay() && !overlayOpen() ? 'true' : null">`, add:

```html
    <!-- v168 §3 #6: one rail that slides to the active entry. Absolutely
         placed (shell.css), so it takes no part in the sidebar's flex gap. -->
    <sb-nav-indicator />
```

2. `frontend/src/app/shell/shell.ts`: add `import { NavIndicator } from './nav-indicator';` beside `import { ProfileMenu } from './profile-menu';`, and add `NavIndicator` to the `@Component` `imports` array after `ProfileMenu` (leave whatever MO5/MO7 added there untouched).

3. `frontend/src/app/shell/shell.css`: replace

```css
/* An accent rail plus a background tint plus weight -- three cues, not
   colour alone, so the active entry survives a monochrome or low-vision
   reading. */
.nav a.active {
  border-left-color: var(--accent);
  background: var(--accent-soft);
  color: var(--text);
  font-weight: 600;
}
```

with

```css
/* An accent rail plus a background tint plus weight -- three cues, not
   colour alone, so the active entry survives a monochrome or low-vision
   reading. The rail is sb-nav-indicator (v168 §3 #6), one bar that slides
   between entries; each link still reserves its 2px transparent border
   (`.nav a`) so the bar lands on that strip and nothing shifts. */
.nav a.active {
  background: var(--accent-soft);
  color: var(--text);
  font-weight: 600;
}

/* The indicator's host, placed against .sidebar (sticky, so positioned;
   absolute children scroll with its content). `left` tracks the sidebar's
   inline padding, which is where every link's border strip starts. */
sb-nav-indicator {
  position: absolute;
  top: 0;
  left: var(--space-14);
  width: 2px;
  pointer-events: none;
}
.shell.railed:not(.overlay) sb-nav-indicator { left: var(--space-10); }
```

If v167 changed `.nav a`'s `border-radius` line, leave it; this step touches only `.nav a.active` and adds the two rules after it.

- [ ] **Step 6: Run the specs**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/shell/nav-indicator.spec.ts --include src/app/shell/shell.spec.ts --include src/app/shell/profile-menu.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/motion-home.spec.ts --include src/app/ui/motion-css.spec.ts`
Expected: `Tests  N passed (N)`, 0 failed. Quote the verdict line.

- [ ] **Step 7: Look at it once**

Run the dev server and drive it with Playwright only (`node $WT/frontend/scripts/browse.mjs`, never claude-in-chrome): open `/dashboard`, then `/trades`; screenshot the sidebar at 1440px expanded and railed. The bar must sit on the active link's left edge in both, and slide (On) between the two. If the bar is offset sideways in one layout, the `left` value in Step 5.3 is the only thing to change; record the shot names in the report. This is a sanity look, not MO18's evidence.

- [ ] **Step 8: Commit**

```bash
git -C $WT add frontend/src/app/shell/nav-indicator.ts frontend/src/app/shell/nav-indicator.spec.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.spec.ts
git -C $WT commit -m "feat(shell): v168 sliding nav indicator (MO11)

One sb-nav-indicator in the sidebar replaces the per-link border rail. It
measures the active link against the scrolling sidebar after first render,
after each NavigationEnd (next macrotask, after RouterLinkActive) and on a
guarded ResizeObserver over the sidebar, each nav list and each link.
motion.css springs it under On, fades under Reduced, jumps under Off. The
active link keeps its tint and weight. shell.spec's rail case is rewritten
for the indicator (file outside the ledger list; serialised after MO5).

<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

