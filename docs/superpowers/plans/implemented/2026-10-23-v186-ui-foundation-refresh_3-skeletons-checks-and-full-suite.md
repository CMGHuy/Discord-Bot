# v186 — UI foundation refresh, part 3: skeletons, checks and the full suite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-23-v186-ui-foundation-refresh-design.md](../specs/2026-10-23-v186-ui-foundation-refresh-design.md) (D5, Testing, Rollout)
**Index:** [2026-10-23-v186-ui-foundation-refresh_0-index.md](2026-10-23-v186-ui-foundation-refresh_0-index.md). The Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

V186-9 and V186-10 use paths relative to the worktree root `.claude/worktrees/2026-10-23-v186-ui-foundation-refresh` (created in V186-1). Their frontend commands run from its `frontend/` directory, exactly as the index's Global Constraints give them. A Vitest "Timeout waiting for worker to respond" at 60 s is machine load: re-run the same command. If `ng test` rejects a repeated `--include`, run one `--include` per command.

V186-11 and V186-12 drive a server, a browser and git across two trees, so they use absolute paths through three names:
- `R`: the main checkout, `E:/Documents/Private/Projects/Discord-Bot`;
- `WT`: `$R/.claude/worktrees/2026-10-23-v186-ui-foundation-refresh`;
- `SCRATCH`: the session scratchpad directory.

Set them once per shell call (`R=...; WT=$R/.claude/worktrees/...; SCRATCH=...`). Never `cd` in Bash: the guardrail hooks stop working after it.

**Edits are anchored on rule text, not line numbers.** V186-4 adds rules to `motion.css` before V186-9 runs, so a line number quoted from `main` at `a5cf0434` may have moved. The rule text named in each step has not.

# Phase 5 — Shaped, quiet skeletons (D5)

### Task V186-9: Shaped, quiet skeletons: bars, `'tiles'`, `sb-skeleton-pulse`

**Model:** sonnet — one shared primitive's template, styles and two gate specs, with specificity-sensitive motion-mode rules.

**Files:**
- Modify: `frontend/src/app/ui/async.ts` (`SkeletonShape`, `SKELETON_SHAPES`, `skeletonGrid`, the loading branch of the template, the skeleton styles, the class doc comment, `Async.grid`)
- Modify: `frontend/src/app/ui/async.spec.ts` (`Host`, the `Async skeleton shapes (v168 #4)` describe)
- Modify: `frontend/src/styles/motion.css` (`@keyframes sb-shimmer`, the Reduced and Off `sb-async .skeleton-cell` rules, two comments)
- Modify: `frontend/src/app/ui/motion-css.spec.ts` (`KEYFRAMES`, the `gives the skeleton a static tint under Reduced and Off (#4)` test)

**Interfaces:**
- Consumes (V186-4): the global classes `.sb-strip-grid` and `.sb-strip-grid.sb-strip-fixed` in `frontend/src/styles.css`. With `.sb-strip-fixed`, the grid shows `var(--strip-cols, 4)` columns from 1024 px, `var(--strip-cols-md, 2)` from 640–1023 px and 2 below 640 px. The `'tiles'` skeleton sets only `--strip-cols`, so it shows 2 columns from 640–1023 px.
- Consumes (tokens, unchanged): `--control-h`, `--radius-sm`, `--surface-raised`, `--border-strong`, `--motion-scale` (tier 3; `[data-motion=off]` zeroes it), `--space-10`, `--space-14`.
- Produces (ledger):
  - `export type SkeletonShape = 'table' | 'panel' | 'figure' | 'tiles';`
  - `export type GridShape = Exclude<SkeletonShape, 'tiles'>;`
  - `export function skeletonGrid(shape: GridShape, rows: number, cols: number): string[][]`
  - `export const BAR_WIDTHS = ['40%', '65%', '30%', '55%'] as const;`
  - `export function barWidth(col: number): string`
  - the keyframe `sb-skeleton-pulse` in `motion.css`; `sb-shimmer` is deleted.
- No later task consumes these. V186-11 looks at the result on screen.

**What changes, in one paragraph.** Each `.skeleton-cell` keeps its `--control-h` box, so nothing reflows when the content lands. It now paints nothing itself and draws an 8 px bar through `::before`, centred vertically in the cell. The bar's width comes from `--bar-w`, set per cell from its column index (40%, 65%, 30%, 55%, repeating). The `head` / `label` / `value` cells of the `panel` and `figure` shapes already take their width from a fixed flex basis (40% / 35% / 65%), so their bar fills the cell and the outline stays as today. The new `'tiles'` shape is its own branch: a `.sb-strip-grid.sb-strip-fixed` of `skeletonRows × skeletonCols` tiles. Each tile is a 35% label bar above a 60% value bar. Every bar pulses its opacity 0.5 → 0.9 → 0.5 over `calc(1800ms * var(--motion-scale))`. The sweeping `sb-shimmer` gradient is gone. Under Reduced and Off the bars are still and sit at a quiet resting opacity of 0.7. `emptyReason`, `aria-hidden` on the skeleton, `aria-busy` and the single `aria-live` region are untouched (known-traps.md).

- [ ] **Step 1: Write the failing tests in `async.spec.ts`**

Change the import line at the top to bring in the two new exports:

```ts
import { asyncInputs, Async, BAR_WIDTHS, barWidth, skeletonGrid, type AsyncEmptyReason, type SkeletonShape } from './async';
```

Give `Host` a column count, so a test can ask for a 4- or 6-column grid. In the template, replace `[skeletonCols]="2"` with `[skeletonCols]="cols"`. In the class, add the field after `shape`:

```ts
  shape: SkeletonShape = 'table';
  cols = 2;
```

Every existing test keeps passing: `cols` defaults to the old literal `2`.

In the `Async skeleton shapes (v168 #4)` describe, **delete** the test `'shimmers with a moving gradient instead of pulsing (source text)'`. It pins `animation: sb-shimmer 1.6s linear infinite;` and `background-size: 200% 100%;`, both of which this task removes. That is the gate-spec edit the spec's Testing section names. Then append these tests at the end of the same describe (before its closing `});`):

```ts
  /* v186 D5: thin bars by column index, a 'tiles' shape on the strip grid,
   * and a quiet opacity pulse in place of the shimmer. */
  const barWidths = (row: Element) =>
    cells(row).map((cell) => (cell as HTMLElement).style.getPropertyValue('--bar-w'));

  it('sizes the bars by column index: 40, 65, 30, 55 per cent, repeating', () => {
    expect([...BAR_WIDTHS]).toEqual(['40%', '65%', '30%', '55%']);
    expect([0, 1, 2, 3, 4, 5, 8].map(barWidth)).toEqual(['40%', '65%', '30%', '55%', '40%', '65%', '40%']);
  });

  it('gives a 4-column grid the four widths on every row', () => {
    const { el } = render({ loading: true, cols: 4 });
    const rows = [...el.querySelectorAll('.skeleton-row')];
    expect(rows.length).toBe(3);
    for (const row of rows) expect(barWidths(row)).toEqual(['40%', '65%', '30%', '55%']);
  });

  it('repeats the sequence across a 6-column grid', () => {
    const { el } = render({ loading: true, cols: 6 });
    for (const row of el.querySelectorAll('.skeleton-row')) {
      expect(barWidths(row)).toEqual(['40%', '65%', '30%', '55%', '40%', '65%']);
    }
  });

  it('keeps the cell classes exact while it sets the bar width', () => {
    const { el } = render({ loading: true, shape: 'figure' });
    const label = el.querySelector('.skeleton-cell.label') as HTMLElement;
    expect(label.className).toBe('skeleton-cell label');
    expect(label.style.getPropertyValue('--bar-w')).toBe('40%');
  });

  it('draws tiles as label and value bars on the strip grid', () => {
    const { el } = render({ loading: true, shape: 'tiles', cols: 2 });
    const skeleton = el.querySelector('.skeleton')!;
    expect(skeleton.classList).toContain('shape-tiles');
    expect(skeleton.getAttribute('aria-hidden')).toBe('true');
    expect(el.querySelector('.skeleton-row')).toBeNull();
    const grid = skeleton.querySelector(':scope > .sb-strip-grid') as HTMLElement;
    expect(grid.classList).toContain('sb-strip-fixed');
    expect(grid.style.getPropertyValue('--strip-cols')).toBe('2');
    const tiles = [...grid.querySelectorAll(':scope > .skeleton-tile')];
    expect(tiles.length).toBe(6); // skeletonRows 3 x skeletonCols 2
    for (const tile of tiles) {
      expect([...tile.children].map((bar) => bar.className)).toEqual(['skeleton-bar label', 'skeleton-bar value']);
    }
  });

  it('keeps aria-busy and the one live region for tiles', () => {
    const { el } = render({ loading: true, shape: 'tiles', announce: 'Loading' });
    expect(el.querySelector('sb-async')!.getAttribute('aria-busy')).toBe('true');
    expect(el.querySelectorAll('[aria-live]').length).toBe(1);
  });

  it('keeps each cell a table row tall and moves the paint onto a thin bar (source text)', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/ui/async.ts'), 'utf8');
    const cell = source.match(/\.skeleton-cell\s*\{[^}]*\}/)![0];
    expect(cell).toContain('height: var(--control-h);');
    expect(cell).not.toContain('animation');
    expect(cell).not.toContain('background');
    const bar = source.match(/\.skeleton-cell::before,\s*\.skeleton-bar\s*\{[^}]*\}/)![0];
    expect(bar).toContain('height: 8px;');
    expect(bar).toContain('border-radius: var(--radius-sm);');
    expect(bar).toContain('animation: sb-skeleton-pulse calc(1800ms * var(--motion-scale)) ease-in-out infinite;');
    expect(source.match(/\.skeleton-cell::before\s*\{[^}]*\}/)![0]).toContain('width: var(--bar-w, 60%);');
    expect(source.match(/\.skeleton-bar\.label\s*\{[^}]*\}/)![0]).toContain('width: 35%;');
    expect(source.match(/\.skeleton-bar\.value\s*\{[^}]*\}/)![0]).toContain('width: 60%;');
    expect(source).not.toContain('sb-shimmer');
    expect(source).not.toContain('sb-pulse-soft');
  });
```

The `skeletonGrid` purity test (`'computes the grid as a pure table of shapes'`) stays exactly as it is: the three grid shapes keep their `string[][]` contract.

- [ ] **Step 2: Write the failing tests in `motion-css.spec.ts`**

In the `KEYFRAMES` const, remove `'sb-shimmer'` from the `// new (v168 §3)` list and add a v186 line at the end. The new keyframe must sit after `'sb-enter'`, so the compositor-only test (`NEW_KEYFRAMES`) covers it:

```ts
const KEYFRAMES = [
  // moved (v168 §2, amendment 7)
  'sb-pulse-dim', 'sb-pulse-blink', 'sb-spin', 'sb-route-spin', 'sb-scan-sweep',
  'sb-scan-strip-in', 'sb-flash-up', 'sb-flash-down', 'sb-row-blink', 'sb-tape-slide',
  // new (v168 §3)
  'sb-enter', 'sb-fade-in', 'sb-pop-in', 'sb-drawer-in', 'sb-drawer-out', 'sb-sheet-in', 'sb-sheet-out',
  'sb-fade-out', 'sb-ping', 'sb-draw-inset', 'sb-draw-circle', 'sb-ambient-drift', 'sb-halo-blink',
  // new (v186 D5): the skeleton's quiet pulse replaced sb-shimmer
  'sb-skeleton-pulse',
];
```

Replace the test `'gives the skeleton a static tint under Reduced and Off (#4)'` with:

```ts
  it('stills the skeleton bars under Reduced and Off (#4, v186 D5)', () => {
    for (const mode of ['reduced', 'off']) {
      expect(bodiesFor(MOTION, `[data-motion=${mode}] sb-async .skeleton-cell::before`), mode).toContain('animation: none;');
      expect(bodiesFor(MOTION, `[data-motion=${mode}] sb-async .skeleton-bar`), mode).toContain('animation: none;');
      // The cell box paints nothing any more, so the old target is gone.
      expect(bodiesFor(MOTION, `[data-motion=${mode}] sb-async .skeleton-cell`), mode).toEqual([]);
    }
  });

  it('pulses the skeleton bars gently, opacity 0.5 to 0.9 and back (v186 D5)', () => {
    const body = Object.fromEntries(keyframeList(MOTION));
    expect(body['sb-shimmer']).toBeUndefined();
    expect(body['sb-skeleton-pulse']).toBe('0%, 100% { opacity: 0.5; } 50% { opacity: 0.9; }');
  });
```

The two rules are specific enough to win. The component's bar rule compiles to `.skeleton-cell[_ngcontent-…]::before` (0,2,1) and `.skeleton-bar[_ngcontent-…]` (0,2,0). The mode rules are `[data-motion=…] sb-async .skeleton-cell::before` (0,2,2) and `[data-motion=…] sb-async .skeleton-bar` (0,2,1). Each mode rule beats its component rule, as the header comment of `motion.css` requires.

- [ ] **Step 3: Run the tests to verify they fail**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/ui/async.spec.ts --include src/app/ui/motion-css.spec.ts
```
Expected: FAIL. Vitest may first report a compile error, because `BAR_WIDTHS` and `barWidth` are not exported from `./async`. Once they exist, the failures are:
- the new async tests: no `--bar-w`, no `shape-tiles`, and the source still has the shimmer;
- `defines every keyframe exactly once, and no others`: `sb-shimmer` is defined but not listed, and `sb-skeleton-pulse` is listed but not defined;
- the two new motion tests.

- [ ] **Step 4: Rewrite the skeleton in `async.ts`**

4a. Replace the shape type, the shape table and `skeletonGrid` (from `/** The placeholder's outline` down to the closing `}` of `skeletonGrid`) with:

```ts
/** The placeholder's outline: a table (default), a panel, one figure, or a
 *  row of stat tiles on the strip grid (v186 D5). */
export type SkeletonShape = 'table' | 'panel' | 'figure' | 'tiles';

/** The shapes drawn as rows of cells. `'tiles'` has its own template branch. */
export type GridShape = Exclude<SkeletonShape, 'tiles'>;

/**
 * Rows of cell modifier classes for each grid shape (`''` is a plain cell).
 * Every cell keeps the table-row height (`--control-h`), so whatever
 * replaces the skeleton lands in the space it held and nothing reflows.
 */
const SKELETON_SHAPES: Record<GridShape, (rows: number, cols: number) => string[][]> = {
  table: (rows, cols) => Array.from({ length: rows }, () => Array.from({ length: cols }, () => '')),
  panel: (rows) => [['head'], ...Array.from({ length: Math.max(rows - 1, 0) }, () => [''])],
  figure: () => [['label'], ['value']],
};

export function skeletonGrid(shape: GridShape, rows: number, cols: number): string[][] {
  return SKELETON_SHAPES[shape](rows, cols);
}

/**
 * Bar widths by column index (v186 D5), repeating. A fixed sequence rather
 * than a random one, so a 4- and a 6-column skeleton are both deterministic
 * and a ragged right edge still reads as text, not as a progress bar.
 */
export const BAR_WIDTHS = ['40%', '65%', '30%', '55%'] as const;

export function barWidth(col: number): string {
  return BAR_WIDTHS[col % BAR_WIDTHS.length];
}
```

4b. In the class doc comment, replace these three lines:

```ts
 * the page. `shape` picks the outline (a table by default, a panel, or a
 * single figure); a moving shimmer marks it as loading (spec v168 §3 #4),
 * frozen to a static tint under Motion = Reduced or Off (styles/motion.css).
```

with:

```ts
 * the page. `shape` picks the outline (a table by default, a panel, a
 * single figure, or a row of stat tiles); thin bars pulsing quietly mark it
 * as loading (spec v186 D5, after v168 §3 #4's shimmer), still under
 * Motion = Reduced or Off (styles/motion.css).
```

4c. Replace the whole `} @else if (loading()) { … }` branch of the template, up to the line before `} @else if (empty()) {`, with:

```html
    } @else if (loading()) {
      @if (shape() === 'tiles') {
        <div class="skeleton shape-tiles" aria-hidden="true">
          <div class="sb-strip-grid sb-strip-fixed" [style.--strip-cols]="skeletonCols()">
            @for (tile of tiles(); track $index) {
              <div class="skeleton-tile">
                <span class="skeleton-bar label"></span>
                <span class="skeleton-bar value"></span>
              </div>
            }
          </div>
        </div>
      } @else {
        <div class="skeleton" [class]="'shape-' + shape()" aria-hidden="true">
          @for (row of grid(); track $index) {
            <div class="skeleton-row">
              @for (cell of row; track $index) {
                <span class="skeleton-cell" [class]="cell" [style.--bar-w]="barWidth($index)"></span>
              }
            </div>
          }
        </div>
      }
```

Inside the inner `@for`, `$index` is the cell's column index. `[style.--bar-w]` sets a custom property and adds no class, so the exact `className` assertions (`'skeleton-cell head'`) keep holding.

4d. In `styles`, replace everything from the comment `/* A highlight band sweeps across a static base` (and the `.skeleton` / `.skeleton-row` rules just above it) through `.skeleton-cell.value { flex: 0 0 65%; }` with:

```css
    .skeleton { display: flex; flex-direction: column; gap: var(--space-6); }
    .skeleton-row { display: flex; gap: var(--space-10); }
    /* The cell is a table row's height so the swap costs no layout shift; it
       paints nothing itself and centres a thin bar (spec v186 D5). */
    .skeleton-cell {
      flex: 1;
      display: flex;
      align-items: center;
      min-width: 0;
      height: var(--control-h);
    }
    .skeleton-cell.head { flex: 0 0 40%; }
    .skeleton-cell.label { flex: 0 0 35%; }
    .skeleton-cell.value { flex: 0 0 65%; }
    /* One quiet bar: an opacity pulse only, so no layout or neighbour paint.
       Under Motion = Reduced or Off the animation is dropped
       (styles/motion.css) and the bar rests at the base opacity. */
    .skeleton-cell::before,
    .skeleton-bar {
      content: '';
      display: block;
      height: 8px;
      border-radius: var(--radius-sm);
      background: color-mix(in srgb, var(--surface-raised) 55%, var(--border-strong));
      opacity: 0.7;
      animation: sb-skeleton-pulse calc(1800ms * var(--motion-scale)) ease-in-out infinite;
    }
    .skeleton-cell::before { width: var(--bar-w, 60%); }
    /* The shaped cells already carry their width in flex-basis. */
    .skeleton-cell.head::before,
    .skeleton-cell.label::before,
    .skeleton-cell.value::before { width: 100%; }

    /* 'tiles': the strip's own grid (styles.css .sb-strip-grid), so the
       placeholder breaks at the same widths the tiles will. The wrapper clips
       the grid's -1px start-edge offset, as sb-stat-strip does. */
    .shape-tiles { overflow: hidden; }
    .skeleton-tile {
      display: flex;
      flex-direction: column;
      gap: var(--space-10);
      min-width: 0;
      padding: var(--space-14);
    }
    .skeleton-bar.label { width: 35%; }
    .skeleton-bar.value { width: 60%; }
```

4e. In the `Async` class, replace the `grid` computed and expose the two helpers to the template:

```ts
  protected readonly grid = computed(() => {
    const shape = this.shape();
    return shape === 'tiles' ? [] : skeletonGrid(shape, this.skeletonRows(), this.skeletonCols());
  });

  /** 'tiles': skeletonRows rows of skeletonCols tiles (v186 D5). */
  protected readonly tiles = computed(() =>
    Array.from({ length: Math.max(this.skeletonRows(), 1) * Math.max(this.skeletonCols(), 1) }, (_, i) => i),
  );

  protected readonly barWidth = barWidth;
```

- [ ] **Step 5: Swap the keyframe and retarget the mode rules in `motion.css`**

5a. Replace the line

```css
@keyframes sb-shimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }
```

with

```css
@keyframes sb-skeleton-pulse { 0%, 100% { opacity: 0.5; } 50% { opacity: 0.9; } }  /* sb-async skeleton bars (v186 D5) */
```

5b. Replace `[data-motion=reduced] sb-async .skeleton-cell { animation: none; }` with:

```css
[data-motion=reduced] sb-async .skeleton-cell::before,
[data-motion=reduced] sb-async .skeleton-bar { animation: none; }
```

5c. Replace `[data-motion=off] sb-async .skeleton-cell { animation: none; }` with:

```css
[data-motion=off] sb-async .skeleton-cell::before,
[data-motion=off] sb-async .skeleton-bar { animation: none; }
```

5d. Bring two comments up to date (text only):
- in the header comment, `` name the host element too (`sb-async .skeleton-cell`). `` becomes `` name the host element too (`sb-async .skeleton-cell::before`). ``;
- above the moved keyframes, `skeleton's soft one became the shimmer (MO9), so two shapes remain. */` becomes `skeleton's soft one became the shimmer (MO9), now sb-skeleton-pulse (v186), so two shapes remain. */`.

Do not touch the `.sb-lift` rules or the in-strip lift override that V186-4 added after them.

- [ ] **Step 6: Run the tests to verify they pass**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/ui/async.spec.ts --include src/app/ui/motion-css.spec.ts
```
Expected: PASS, 0 failed.

- [ ] **Step 7: Run the gates that read these files**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/ui/motion-home.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/ui/stat-strip.spec.ts
```
Expected: PASS, 0 failed, with no gate spec edited:
- `motion-home.spec.ts` requires every `animation:` name to be a keyframe that `motion.css` defines; `sb-skeleton-pulse` is one;
- `primitives.spec.ts` G3 sees no new `box-shadow:` and reads `border-radius: var(--radius-sm)` as a token;
- `stat-strip.spec.ts` (V186-4) still finds its `motion.css` lift rule.

A failure here means an edit went past the skeleton rules: undo that part.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/ui/async.ts frontend/src/app/ui/async.spec.ts frontend/src/styles/motion.css frontend/src/app/ui/motion-css.spec.ts
git commit -F- <<'MSG'
feat(ui): v186 D5 shaped, quiet skeletons

Skeleton cells keep their --control-h box and draw an 8px bar whose width
follows the column index (40/65/30/55%). A new 'tiles' shape lays label and
value bars on the shared .sb-strip-grid. sb-skeleton-pulse (opacity
0.5-0.9-0.5, 1.8s x --motion-scale) replaces the sb-shimmer sweep, and the
Reduced and Off rules now still the bars. motion-css.spec KEYFRAMES and the
async.spec source pin move with it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

# Phase 6 — Checks

### Task V186-10: Scoped faint-text source scan

**Model:** haiku — one new describe block in an existing spec, its code given whole.

**Files:**
- Modify: `frontend/src/app/ui/contrast.spec.ts` (imports, the `NON_TEXT` doc comment, one new `describe` at the end of the file)

**Interfaces:**
- Consumes the colour fixes of the earlier tasks:
  - V186-2: `layout.ts` `.panel-toggle` and `panel-header.ts` `.n, .all-time` → `--text-muted`;
  - V186-3: `stat-tile.ts` `.label`, `.sample, .secondary, .hint` and `metric-card.ts` `.absent` → off `--text-faint`;
  - V186-5: `portfolio-value.ts` `.figure.muted` → `--text-muted`.
- Consumes `stripComments(source: string): string` from `frontend/src/app/ui/testing/all-sources.ts` (exists; it strips `/* */`, `<!-- -->` and `//` comments).
- Produces: `describe('no faint text in the v186 primitives (source scan)')`. No later task consumes it.

**Why a source scan, and why only these files.** jsdom does not resolve a component's `var()` chain, so a computed-colour read proves nothing. The test reads each file's source, as `async.spec.ts` does. It covers only the six files v186 touched (spec § Testing). The ~100 other `--text-faint` uses in the app are later specs' work, and the comment-only `no-text-uses-text-faint` rule is not widened here. The test matches `color: var(--text-faint)` only where `color` is the whole property name. `border-color` and `border-bottom: 1px solid var(--text-faint)` paint rules, which is what the token is for, so they stay legal.

- [ ] **Step 1: Show that the scan would have failed before v186**

This task's code lands after V186-2, V186-3 and V186-5 have made the fixes, so its test passes on its first run. The evidence that it can fail comes from `main`, where the faint text still exists:

```bash
for f in frontend/src/app/ui/stat-tile.ts frontend/src/app/ui/metric-card.ts frontend/src/app/ui/layout.ts frontend/src/app/ui/panel-header.ts frontend/src/app/ui/figure.ts frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts; do
  echo "== $f"; git show "main:$f" | grep -nE "(^|[^-a-zA-Z0-9_])color: *var\(--text-faint\)"
done
```

Expected on `main`: hits in `stat-tile.ts` (`.label` and `.sample, .secondary, .hint`), `metric-card.ts` (`.absent`), `layout.ts` (`.panel-toggle`), `panel-header.ts` (`.n,.all-time`) and `portfolio-value.ts` (`.figure.muted`). `figure.ts` has none. Run the same loop on the branch's working tree, with `cat "$f"` in place of `git show "main:$f"`. Expected: no hits in any file. Any hit names a site that V186-2, V186-3 or V186-5 missed. Fix that one declaration in this task: change `var(--text-faint)` to `var(--text-muted)`, since the spec puts every one of these sites on `--text-muted`. Add the file to this task's commit and say so in the report.

- [ ] **Step 2: Write the test**

At the top of `contrast.spec.ts`, add the import under the existing `resolveToken` import:

```ts
import { resolveToken } from './testing/resolve-token';
import { stripComments } from './testing/all-sources';
```

In the doc comment above `const NON_TEXT`, replace the sentence ending `` and `no-text-uses-text-faint` below is what enforces it. `` with:

```ts
 * colour, never text that must be read — that is decision D6's binding rule
 * (`no-text-uses-text-faint`). The scoped source scan at the end of this
 * file enforces it for the primitives v186 touched.
```

(The lines before it, up to and including `` `--text-faint` measures ~2.3:1 on --surface. It is a RULE AND DIVIDER ``, stay as they are. The phrase "rule and divider" stays in `tokens.css`, so the existing `is documented as non-text` test is unaffected.)

Append at the end of the file:

```ts
/**
 * v186 (D2, D3, D4): no text in the primitives v186 touched is painted in
 * --text-faint, the rule and divider colour above. A SOURCE scan, because
 * jsdom does not resolve a component's var() chain. Scoped to these files on
 * purpose (spec v186 § Testing); the other --text-faint uses are later
 * specs' work.
 */
const V186_FILES = [
  'src/app/ui/stat-tile.ts',
  'src/app/ui/metric-card.ts',
  'src/app/ui/layout.ts',
  'src/app/ui/panel-header.ts',
  'src/app/ui/figure.ts',
  'src/app/workspaces/dashboard/panels/portfolio-value.ts',
];

/** `color:` as the whole property name, so `border-color:` is not text. */
const FAINT_TEXT = /(?<![-\w])color:\s*var\(--text-faint\)/;

describe('no faint text in the v186 primitives (source scan)', () => {
  it('flags a faint text colour and leaves a faint rule alone', () => {
    expect(FAINT_TEXT.test('.x { color: var(--text-faint); }')).toBe(true);
    expect(FAINT_TEXT.test('.n,.all-time{font-size:var(--text-micro);color:var(--text-faint);}')).toBe(true);
    expect(FAINT_TEXT.test('.x { border-color: var(--text-faint); }')).toBe(false);
    expect(FAINT_TEXT.test('.x { border-bottom: 1px solid var(--text-faint); }')).toBe(false);
    expect(FAINT_TEXT.test('.x { color: var(--text-muted); }')).toBe(false);
  });

  for (const file of V186_FILES) {
    it(`${file} paints no text in --text-faint`, () => {
      const source = stripComments(readFileSync(join(process.cwd(), file), 'utf8'));
      const hits = source.split('\n').filter((line) => FAINT_TEXT.test(line)).map((line) => line.trim());
      expect(hits, file).toEqual([]);
    });
  }
});
```

- [ ] **Step 3: Run the test**

Run (from `frontend/`):
```bash
npx ng test --watch=false --include src/app/ui/contrast.spec.ts
```
Expected: PASS, 0 failed. That is 7 new tests (the matcher self-test plus one per file), and every existing WCAG test still passes. If a file test fails, its message lists the offending lines. Fix them as Step 1 says, then re-run this one command.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/ui/contrast.spec.ts
git commit -F- <<'MSG'
test(ui): v186 scoped source scan for faint text in the touched primitives

stat-tile, metric-card, layout (panel header and toggle), panel-header,
figure and portfolio-value may not paint text in --text-faint, the rule
and divider colour. Scoped to v186's files; the app-wide rule stays a
comment until a later spec migrates the remaining uses.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

If Step 1 found a missed site, add its file to the `git add` line and add one line to the message body: `Also moves <file> <selector> from --text-faint to --text-muted (missed by V186-<n>).`

### Task V186-11: Three-width visual check and layout audit

**Model:** sonnet — drives a local server and Playwright, and judges screenshots against the spec; fixes, if any, are small and named by the finding.

**Files:**
- None committed unless a finding needs a fix. A fix goes into the file the finding names, with a unit test that pins it (the spec in the same directory), as its own scoped commit on the branch.
- Scratch only (never committed):
  - `$SCRATCH/v186-strips.mjs`;
  - `$SCRATCH/v186-before/`, `$SCRATCH/v186-after/`, `$SCRATCH/v186-audit/`;
  - the worktree's gitignored `$WT/.env` and `$WT/swingbot/admin/static/app/`.

**Interfaces:**
- Consumes every UI change of V186-1..V186-10 on the branch, and the selectors they fix. Those are `sb-stat-strip` with host classes `grid` (Dashboard), `metric-grid` (Risk) and `totals` (Calendar); its `.sb-strip-grid`; and the `sb-panel` / `sb-panel-header` `h2`.
- Produces the measurement lines V186-12 records in the index's `## Progress`.

**What "pass" means** (spec § Testing, Visual check; index Goal, success criteria):

| Check | 1440 | 1024 | 390 |
|---|---|---|---|
| page horizontal scroll (`scrollX`) on Dashboard, Analytics, Risk, Calendar | 0 | 0 | 0 |
| Dashboard `sb-stat-strip.grid` columns | 4 | 4 | hidden (the `.mobile-summary` shows instead) |
| Calendar `sb-stat-strip.totals` columns | 4 | 4 | 2 |
| Risk `sb-stat-strip.metric-grid` columns | same as the before shot | same as the before shot | same as the before shot |
| panel titles (`h2`) | Inter, 600, 14px, `text-transform: none` | same | same |

Risk keeps today's `auto-fit minmax(140px, 1fr)`, so its count depends on the panel width and has no fixed figure. "Same as before" is the test. The layout audit (`frontend/scripts/layout-audit.mjs`) exits 0 at 390, 768 and 1440.

- [ ] **Step 1: Take the "before" shots from production**

Production runs `main`, which is v186's baseline. This step is read-only:

```bash
R=E:/Documents/Private/Projects/Discord-Bot; SCRATCH=<scratchpad>
node $R/frontend/scripts/browse.mjs shots --out $SCRATCH/v186-before --path dashboard --path analytics --path risk --path calendar --widths 1440,1024,390
```

Expected: 12 PNGs and 12 `.txt` files. Every `.txt` starts with `page-scroll-x: 0`. Leave paths without a leading slash: Git Bash rewrites `/dashboard` into a Windows path. If the headed window asks for a sign-in, `browse.mjs` uses the `.env` credentials itself and never prints them. Close the window when it is done, because the profile allows one browser at a time.

- [ ] **Step 2: Bring up a local instance of the branch**

Run `/replicate-prod-db` first (CLAUDE.md: the local instance reads the database). Then:

```bash
R=E:/Documents/Private/Projects/Discord-Bot; WT=$R/.claude/worktrees/2026-10-23-v186-ui-foundation-refresh
npm --prefix $WT/frontend run build
mkdir -p $WT/swingbot/admin/static/app
cp -r $WT/frontend/dist/frontend/browser/. $WT/swingbot/admin/static/app/
test -f $WT/.env || cp $R/.env $WT/.env
python - "$WT/.env" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
new = re.sub(r"(?m)^(DATABASE_URL=postgres[\w+]*://[^@\s]+@)[^/\s]+/\S+", r"\g<1>127.0.0.1:56432/swingbot_prod_replica", text)
open(path, "w", encoding="utf-8").write(new)
print("DATABASE_URL pointed at the local replica" if new != text else "DATABASE_URL already local")
PY
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:1234/api/v1/session || true
```

The snippet prints one status line and never a value from `.env` (CLAUDE.md). `.env` wins over the process environment (memory: layout-audit stale-bundle trap), which is why the file itself is edited. The worktree copy is gitignored. If `curl` prints a status code, something already listens on 1234. That is another session's server: stop and ask the controller, never kill it.

Start the server with the Bash tool's `run_in_background: true`:

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v186-ui-foundation-refresh/admin_ui.py
```

Then check that it serves this build, not a stale bundle:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v186-ui-foundation-refresh
ls $WT/frontend/dist/frontend/browser/ | grep -E '^main-.*\.js$'
curl -s http://localhost:1234/ | grep -oE 'main-[A-Za-z0-9]+\.js'
```

Expected: the same `main-*.js` name twice. Sign in once (headed; close the window afterwards):

```bash
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/browse.mjs login --base http://localhost:1234
```

- [ ] **Step 3: Measure strips, scroll and titles, and shoot the "after" pages**

`browse.mjs` does not block the service worker, so the profile's cached build could stand in for the one under test. This script launches the same persistent profile with `serviceWorkers: 'block'`, as `layout-audit.mjs` does. Write it with the Write tool to `$SCRATCH/v186-strips.mjs`:

```js
// v186 V186-11: strip column counts, page scroll and panel-title faces at three widths.
// Usage: node v186-strips.mjs <worktree frontend dir> <out dir>
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const [frontend, out] = process.argv.slice(2);
const { chromium } = createRequire(join(frontend, 'package.json'))('playwright');
const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const BASE = 'http://localhost:1234';
const PATHS = ['/dashboard', '/analytics', '/risk', '/calendar'];
const WIDTHS = [1440, 1024, 390];

function measure() {
  const scrollers = [document.documentElement, document.body, document.querySelector('main')].filter(Boolean);
  const scrollX = Math.max(...scrollers.map((el) => el.scrollWidth - el.clientWidth));
  const strips = [...document.querySelectorAll('sb-stat-strip')].map((strip) => {
    const grid = strip.querySelector('.sb-strip-grid');
    const tracks = grid ? getComputedStyle(grid).gridTemplateColumns.split(' ').filter((t) => t && t !== '0px') : [];
    return { host: strip.className.replace(/\s*ng-\S+/g, '').trim(), visible: strip.getClientRects().length > 0, cols: tracks.length, tiles: grid ? grid.children.length : 0 };
  });
  const titles = [...new Set([...document.querySelectorAll('sb-panel h2, sb-panel-header h2')].map((h) => {
    const s = getComputedStyle(h);
    return `${s.fontFamily.split(',')[0]} ${s.fontWeight} ${s.fontSize} ${s.textTransform}`;
  }))];
  return { scrollX, strips, titles };
}

mkdirSync(out, { recursive: true });
const report = [];
for (const width of WIDTHS) {
  const context = await chromium.launchPersistentContext(PROFILE, {
    headless: true, viewport: { width, height: 900 }, deviceScaleFactor: 1,
    serviceWorkers: 'block', hasTouch: width <= 1023, isMobile: width < 640,
  });
  const page = context.pages()[0] ?? (await context.newPage());
  for (const path of PATHS) {
    await page.goto(BASE + path, { waitUntil: 'networkidle' });
    await page.locator('sb-panel').first().waitFor({ timeout: 20000 });
    await page.waitForTimeout(1500);
    report.push({ width, path, ...(await page.evaluate(measure)) });
    await page.screenshot({ path: join(out, `${path.slice(1)}@${width}.png`), fullPage: true });
  }
  // The loading state: hold every API call but the session check, then shoot the skeleton.
  await page.route(/\/api\/v1\/(?!session)/, () => {});
  await page.goto(BASE + '/dashboard');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(out, `skeleton-dashboard@${width}.png`) });
  await context.close();
}
writeFileSync(join(out, 'facts.json'), JSON.stringify(report, null, 2));
for (const r of report) console.log(r.width, r.path, `scrollX=${r.scrollX}`, JSON.stringify(r.strips), JSON.stringify(r.titles));
```

Run it. `main` has no `sb-stat-strip`, so the Risk baseline is the tile column count you read off Step 1's `v186-before/risk@<width>.png` shots:

```bash
R=E:/Documents/Private/Projects/Discord-Bot; WT=$R/.claude/worktrees/2026-10-23-v186-ui-foundation-refresh; SCRATCH=<scratchpad>
node $SCRATCH/v186-strips.mjs $WT/frontend $SCRATCH/v186-after
```

Expected for the after run, line by line, as the pass table above says:
- `scrollX=0` everywhere;
- Dashboard `grid` with 4 / 4 columns and `visible: false` at 390;
- Calendar `totals` with 4 / 4 / 2 columns;
- Risk `metric-grid` with the before shots' counts;
- `titles` reads only `Inter 600 14px none`.

A Calendar strip has 7 tiles and a Dashboard strip 8. A strip that is missing because a page had no data at that moment is not a finding. Re-run once; if it is still missing, say so in the report.

- [ ] **Step 4: Look at every shot, before and after**

Open each `$SCRATCH/v186-after/<page>@<width>.png` with the Read tool, next to its `$SCRATCH/v186-before/` twin. Check, at each width:
1. Panel titles are one sentence-case line in Inter, with `N=`, `all-time` or a total beside them on the baseline. Field and tile labels are still mono caps.
2. The header rule shows only on flush panels and on the six `divided` panels: Calendar "By weekday", the two Attribution panels, the Calendar day trades panel, Market movers and the gallery demo. Other headers sit closer to their body (`.body.tight`).
3. The Dashboard, Risk and Calendar tile rows are split by single hairlines. They have no frames inside the panel, no doubled rule on the outer edges, no stray rule beside an empty last cell, and no tint inside the Dashboard strip.
4. Display figures are Inter 600 with tight tracking. Table cells and `N=` are still mono.
5. Tile labels, `N=` and hints read clearly (`--text-muted`, no longer the faint rule colour).
6. `skeleton-dashboard@<width>.png` shows thin, ragged bars at 40/65/30/55%, not full-height slabs. A static frame cannot show the pulse; Step 3's run already proved the bars render.
7. Page-level tiles (Analytics overview and partials) keep their own frame. They are outside v186's migration.

Hover lift inside a strip and the pulse are motion, so they are checked by the unit tests (V186-4, V186-9), not by these shots.

- [ ] **Step 5: Run the layout audit at three widths**

```bash
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/layout-audit.mjs --base http://localhost:1234 --out <scratchpad>/v186-audit
```

Expected: exit 0 at the default widths 390, 768 and 1440 (`ui-design.md` § Checklist). A finding is fixed, never allowed (`ui-design.md`).
- A finding on an element v186 changed (a panel header or `h2`, a tile, `sb-stat-strip`, a skeleton) is fixed in Step 6.
- A finding on anything else is pre-existing: list it in the report with its route, width and selector, and do not fix it here, because it is outside v186's scope.
- A `STALE` allow-list entry is reported, not pruned.

- [ ] **Step 6: Fix each v186 finding with a test**

For each finding from Steps 3–5 that v186 caused:
1. Write a failing assertion in the spec beside the file that causes it. Pin the source text the way the earlier tasks do, because jsdom does no layout.
2. Fix the one rule.
3. Re-run that spec alone, from `frontend/`: `npx ng test --watch=false --include <spec>`.
4. Rebuild, copy the bundle (Step 2's `npm run build` and `cp` lines) and re-run Steps 3–5 for the affected page only.
5. Commit the fix on its own:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v186-ui-foundation-refresh add <file> <spec>
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v186-ui-foundation-refresh commit -F- <<'MSG'
fix(ui): v186 <what the visual check found> at <width>

<One or two lines: the finding, the cause, the rule changed.>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

A finding that would change a decision in the spec (column counts, the conditional rule, the tint drop) is not fixed here. Stop and report it to the controller as a question.

- [ ] **Step 7: Stop the server and record the results**

Stop the background `admin_ui.py` (KillShell on its shell id). Leave the gitignored `$WT/.env` and `static/app/` as they are: `/close-out` removes the worktree. Report these lines; V186-12 copies them into `## Progress`:

```text
Visual check (V186-11): scrollX 0 on Dashboard/Analytics/Risk/Calendar at 1440/1024/390; strip columns Dashboard 4/4/hidden, Calendar 4/4/2, Risk <a>/<b>/<c> (= before); titles Inter 600 14px none; layout audit exit 0 at 390/768/1440 (<n> pre-existing findings reported, <n> v186 fixes committed).
```

- [ ] **Step 8: Commit**

Nothing to commit unless Step 6 made a fix; each fix is already its own commit. `git -C $WT status --short` shows no tracked change.

# Phase 7 — Full suite, merge and close-out

### Task V186-12: Full suite, merge, panel, close-out

**Model:** sonnet — run and record the one full suite, then a merge and panel findings that need judgement; the close-out itself is the skill's checklist.

**Files:**
- None in code. A failure is fixed in the file that broke, as its own scoped commit.
- `/close-out` modifies `VERSION.json` and `swingbot/admin/version_history.json`. It moves the four plan files into `docs/superpowers/plans/implemented/` and the spec into `docs/superpowers/specs/implemented/`:
  - `docs/superpowers/plans/2026-10-23-v186-ui-foundation-refresh_0-index.md`
  - `docs/superpowers/plans/2026-10-23-v186-ui-foundation-refresh_1-tokens-panel-title-and-strip.md`
  - `docs/superpowers/plans/2026-10-23-v186-ui-foundation-refresh_2-figure-face-and-migration.md`
  - `docs/superpowers/plans/2026-10-23-v186-ui-foundation-refresh_3-skeletons-checks-and-full-suite.md`
  - `docs/superpowers/specs/2026-10-23-v186-ui-foundation-refresh-design.md`
- Modifies the index `_0-index.md`: adds a `## Progress` section before the move.

**Interfaces:**
- Consumes every commit of V186-1..V186-11 on the branch `2026-10-23-v186-ui-foundation-refresh`, and V186-11's measurement line.
- Produces `main` carrying the merge, any panel fixes and the release commits, pushed. The plan leaves the live set, and the SessionStart `PLAN WIP` line stops naming it.

- [ ] **Step 1: Check the branch is complete and clean**

```bash
R=E:/Documents/Private/Projects/Discord-Bot; WT=$R/.claude/worktrees/2026-10-23-v186-ui-foundation-refresh
git -C $WT status --short
git -C $WT log --oneline main..HEAD
```

Expected: no uncommitted tracked change. The worktree's gitignored `.env` and `static/app/` do not show. There is at least one commit for each code task V186-1..V186-10. V186-11 has a commit only if it fixed something.

- [ ] **Step 2: Run the Python full suite once**

Run `/replicate-prod-db` first (CLAUDE.md: a task that runs tests against the database). Then dispatch the `test-runner` subagent, so none of the output lands in this context. Its brief: with the local test Postgres (`db-test`) up, run `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v186-ui-foundation-refresh/scripts/dev/testrun.py full`. Report the pass / fail / xfail / skip counts, plus the first failure's node id and assertion only.

Expected:
- `0 failed` and `0 xfailed`. A changed pass count is not a failure (`testing-cost.md`).
- `tests/dev/test_dump_tokens.py::test_the_committed_fixture_is_current` passes, because V186-1 committed the regenerated `tests/charts/resolved_tokens.json`.
- `testrun.py full` also runs `complexity_gate.py`. v186 changes no Python function, so the gate passes unchanged.
- A run that skipped the database tests because `db-test` was down does not count: start `db-test` and re-run.

- [ ] **Step 3: Run the frontend suite, the lint and the production build once**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v186-ui-foundation-refresh
npm --prefix $WT/frontend exec -- ng test --watch=false
npm --prefix $WT/frontend run lint
npm --prefix $WT/frontend run build
```

Expected: Vitest `0 failed`; `eslint src` reports no error; the build ends without errors. These are the commands CI runs (`.github/workflows/deploy.yml`). The Vitest run includes every gate the index names, and they must be green with no edit beyond what the spec allows:
- unchanged: `primitives.spec.ts` (G3, radius), `tokens.spec.ts`, `workspace-consistency.spec.ts`, `elevation.spec.ts` and `vertical-centre.spec.ts`;
- changed only where the spec says: `motion-css.spec.ts` and `async.spec.ts`.

A Vitest "Timeout waiting for worker to respond" at 60 s is load: re-run only the file it names.

- [ ] **Step 4: Prove the gate specs changed only where the spec allows**

```bash
R=E:/Documents/Private/Projects/Discord-Bot
git -C $R diff --stat main...2026-10-23-v186-ui-foundation-refresh -- frontend/src/app/ui/primitives.spec.ts frontend/src/app/ui/tokens.spec.ts frontend/src/app/workspaces/workspace-consistency.spec.ts frontend/src/app/ui/elevation.spec.ts frontend/src/app/ui/vertical-centre.spec.ts
git -C $R diff main...2026-10-23-v186-ui-foundation-refresh -- frontend/src/app/ui/motion-css.spec.ts frontend/src/app/ui/async.spec.ts | grep -E '^[-+][^-+]' | head -60
```

Expected:
- The first command lists only `tokens.spec.ts`, and only additions. That file gains V186-1's figure-token test. Its existing tests, including `declares --font-num as the mono family`, are untouched.
- The second shows only V186-9's edits: in `motion-css.spec.ts`, `KEYFRAMES` loses `sb-shimmer`, gains `sb-skeleton-pulse`, and the Reduced/Off test moves to the bars; in `async.spec.ts`, the shimmer source test is replaced, `Host` gains `cols`, and the new bar and `'tiles'` tests are added.

Any other change to a gate spec is a finding. Revert it and fix the code instead.

- [ ] **Step 5: Fix any failure alone**

A failing test is fixed in its own scoped commit on the branch (`fix(ui): … (v186)`). Then re-run it alone, never with the whole suite:
- a Python test: `python $WT/scripts/dev/testrun.py file <test>`;
- a frontend spec: from `$WT/frontend/`, `npx ng test --watch=false --include <spec>`.

Record in the task report:
- the Python counts (passed / skipped / 0 failed / 0 xfailed);
- the Vitest count, the lint result and the build result.

- [ ] **Step 6: Bring `main` into the branch, then merge it into `main`**

Follow the `worktree-lifecycle` skill, because other sessions share `$R`. The main checkout carries another session's uncommitted dashboard and `motion.css` edits. Never stash, reset or commit them. If the merge into `main` would touch a file that is dirty in `$R`, stop and ask the controller.

```bash
R=E:/Documents/Private/Projects/Discord-Bot; WT=$R/.claude/worktrees/2026-10-23-v186-ui-foundation-refresh
git -C $R status --short
git -C $WT merge main -m "merge: main into v186 UI foundation refresh before release"
```

Expected: the merge into the branch is clean, or its conflicts are resolved file by file. Re-run alone the specs of any file that conflicted. No full suite here: it ran in Steps 2–3.

Write `$SCRATCH/v186-12-merge-msg.txt`:

```text
merge: v186 UI foundation refresh (one panel title, stat strips, Inter figures, quiet skeletons)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $R switch main
git -C $R merge --no-ff 2026-10-23-v186-ui-foundation-refresh -F "$SCRATCH/v186-12-merge-msg.txt"
git -C $R log --oneline -3
```

Expected: a merge commit on `main`. No full suite after this merge (CLAUDE.md).

- [ ] **Step 7: Run the panel on `main`**

The spec carries `**Panel:** senior-engineer`. With `<merge>` the sha from Step 6, run:

```
/panel senior-engineer <merge>^1..<merge>
```

Give it Steps 2–4's recorded results and V186-11's measurement line as context. The seat checks that each of its findings in the spec's `## Panel review` landed:
- **1, 5:** the tiles read `--figure-rule` on their `:host` with start-edge borders and `box-sizing: border-box`. The strip sets the custom properties and clips its grid. No `::ng-deep` reaches into tiles or the strip.
- **2:** `--tile-tint-off` drops the metric-card tint inside a strip and keeps it outside, with a test.
- **3:** the portfolio hero gains only `letter-spacing: var(--figure-tracking)` and the muted dash.
- **4:** each D4 site's own scoped rule reads the figure tokens, with `num` removed from the `figure.ts`, `panel-header.ts` and `metric-card.ts` templates. There is no global figure class.
- **5 (lift):** `--panel-shadow-lift: none` is set on the strip host, and the `[data-motion=on] sb-stat-strip .sb-lift:hover { transform: none; }` rule exists. G3's exact shadow list is unchanged.
- **6:** the transparent bottom border keeps the header height, `.ruled` / `.tight` are bound, and a headingless panel keeps `--space-14`.
- **7:** the `h2.sb-label` selectors in `layout.spec.ts` are updated.
- **8:** the scoped faint-text source scan exists (V186-10).
- **9, 10:** the motion-css `KEYFRAMES` change, the `async.spec` pin, the Reduced/Off rules on the bars, and `'tiles'` on `.sb-strip-grid` with the column-index sequence.
- **11:** the `cols` / `colsMd` per site: Dashboard 4/2, Risk auto-fit, Calendar 4/4.
- **12:** metric-card's weight 700 → 600.

A `BLOCKING` finding is fixed on `main` as its own scoped commit (`fix(ui): … (v186 panel)`). Then re-run only the specs of the files it touched, and re-run the panel for that role. Each `ADVISORY` finding is either applied the same way or recorded with a one-line reason in the task report. Expected: no unresolved `BLOCKING` finding.

- [ ] **Step 8: Close out**

Before `/close-out` moves anything, add a `## Progress` section to the index `docs/superpowers/plans/2026-10-23-v186-ui-foundation-refresh_0-index.md`. It holds one line, filled from the task reports:

```markdown
## Progress

Done <YYYY-MM-DD>. V186-1..V186-12 complete. Full suite (V186-12): Python <passed> passed, <skipped> skipped, 0 failed, 0 xfailed; Vitest <n> passed; lint and production build green; gate specs unchanged except tokens.spec (additions) and the motion-css / async edits the spec names. <V186-11's measurement line>. Panel (senior-engineer): <n> BLOCKING resolved, <n> ADVISORY (<applied>/<recorded>). Released ui <version>, bot unchanged.
```

Commit it on `main`:

```bash
git -C $R add docs/superpowers/plans/2026-10-23-v186-ui-foundation-refresh_0-index.md
git -C $R commit -F- <<'MSG'
docs(v186): record progress before close-out

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
MSG
```

Then invoke `/close-out` (standing permission, CLAUDE.md). It does four things:
- resolves the header's `**Bump:** ui minor, bot none` from the current `VERSION.json`;
- regenerates `swingbot/admin/version_history.json` after the release commit (memory: a version bump needs the regeneration);
- moves the four plan files and the spec to `implemented/`;
- removes the worktree.

The skill's checks, which must hold:
- `ls docs/superpowers/plans/2026-10-23-v186-ui-foundation-refresh_*.md` lists exactly the four files in the index's Parts table (`_0-index`, `_1-…`, `_2-…`, `_3-…`).
- The branch name contains no `backup` and is not `stable-*`. `git -C $R rev-list --count main..2026-10-23-v186-ui-foundation-refresh` prints `0` before `git worktree remove` and `git branch -d`. Never use `-D`; a non-zero count means stop and ask the partner.
- After the bump, `python $R/scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py` passes.

- [ ] **Step 9: Push and confirm**

```bash
R=E:/Documents/Private/Projects/Discord-Bot
git -C $R status --short
git -C $R push origin main
gh run list --branch main --limit 1
```

Expected: no pending change to this plan's paths (another session's unrelated dirty files may still show); the push is accepted; a workflow run for the new `main` head is listed. If another session pushed first and the push is rejected, run `git -C $R pull --no-rebase origin main` and push again. Never force-push. No full suite after this: it ran once, in Steps 2–3.

- [ ] **Step 10: Commit**

This task's commits are the ones made in Steps 5–8:
- any fix commits;
- the merge;
- any panel fixes;
- the progress line;
- `/close-out`'s release, regeneration and move commits.

Each message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Afterwards `git -C $R log --oneline -8` shows them, and `git -C $R worktree list` no longer lists the v186 worktree.
