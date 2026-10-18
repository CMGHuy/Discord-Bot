# v168 Motion system. Part 1: foundations (MO1..MO4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task MO3:" -A 400 docs/superpowers/plans/2026-10-16-v168-motion-system_1-foundations.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v168-motion-system-design.md`](../specs/2026-10-16-v168-motion-system-design.md) (this part: §1 durations and `--motion-scale`, persistence, the OS setting; §2 one keyframe home; §3 the class catalogue the later tasks wire; §6 `will-change`; Testing "Test-environment default"; Amendments 5, 7, 8, 9)
**Index:** [`2026-10-16-v168-motion-system_0-index.md`](2026-10-16-v168-motion-system_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v168-motion-system` (created in MO1). Never `cd`; use `git -C $WT`, `python $WT/scripts/dev/testrun.py file <test>` and `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>`. All file paths below are relative to `$WT` unless they say `$R`.

**`GATES`** (from the index) = `--include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/motion-home.spec.ts` (the last exists from MO3 on; before that, drop it).

**Order.** MO1, then MO2. MO3 and MO4 may run in parallel after MO2 (disjoint files; MO3's CSS reads only the `data-motion` attribute, MO4's TS never reads CSS).

**Line numbers below are from `main` before v167.** v167 (merged first, MO1 checks) re-wrapped and re-radiused several of these files, so every edit says what text to find; re-read the region before editing and match by text, not by line.

**What this part leaves for later on purpose.** MO3 only *moves* keyframes and renames their references; the component `@media (prefers-reduced-motion: reduce)` blocks stay where they are until MO6 replaces them with `[data-motion]` rules, and the global reduced-motion block in `tokens.css` stays until MO6 too. Nothing here writes `data-motion` on `<html>` (MO5), so after this part the app still looks exactly as before except for the refined cell flash (1.1s, MO3).

---

# Phase 1 — Precondition, tokens, keyframe home, motion service

### Task MO1: v167 merged precondition; worktree

**Model:** haiku — runs fixed git checks, no code

**Files:**
- Modify (only on a stop): `$R/docs/superpowers/plans/2026-10-16-v168-motion-system_0-index.md` (`## Handoff`, one appended line)

**Interfaces:**
- Consumes: nothing from this plan. From `main`: v167's artefacts (`frontend/src/styles/palette.css`, the tier-3 banner in `frontend/src/styles/tokens.css`, `scripts/dev/dump_tokens.py`, `frontend/src/app/ui/testing/all-sources.ts`).
- Produces: the worktree `$WT` on branch `2026-10-16-v168-motion-system` with `frontend/node_modules` installed and a green `GATES` baseline (every later task uses it). On a stop: one dated `## Handoff` line in the index, nothing else.

- [ ] **Step 1: Check that v167 is merged to `main`**

Run each line from the main tree (no `cd`):

```bash
git -C E:/Documents/Private/Projects/Discord-Bot show main:frontend/src/styles/tokens.css | grep -c "Tier 3: component tokens (spec v167"
git -C E:/Documents/Private/Projects/Discord-Bot cat-file -e main:frontend/src/styles/palette.css && echo palette-ok
git -C E:/Documents/Private/Projects/Discord-Bot cat-file -e main:scripts/dev/dump_tokens.py && echo dump-ok
git -C E:/Documents/Private/Projects/Discord-Bot cat-file -e main:frontend/src/app/ui/testing/all-sources.ts && echo walker-ok
git -C E:/Documents/Private/Projects/Discord-Bot show main:frontend/src/styles/tokens.css | grep -cE "^\s*--radius(-chip)?:"
git -C E:/Documents/Private/Projects/Discord-Bot show main:frontend/src/app/ui/primitives.spec.ts | grep -c "TIER3_RGB"
git -C E:/Documents/Private/Projects/Discord-Bot rev-list --count main..2026-10-16-v167-arctic-navy-token-foundation 2>/dev/null || echo "no-v167-branch"
```

Expected when v167 is merged: `1`, `palette-ok`, `dump-ok`, `walker-ok`, `0` (AN13 deleted `--radius`/`--radius-chip`), a count of at least `2` (`TIER3_RGB` is declared and used), and either `0` or `no-v167-branch`.

- [ ] **Step 2 (only if any Step 1 check differs): record the stop and end the task**

Append one line under `## Handoff` at the end of `$R/docs/superpowers/plans/2026-10-16-v168-motion-system_0-index.md`, with today's date and the checks that failed, for example:

```markdown
- **2026-10-17, MO1:** v167 not merged (tier-3 banner missing on main; `dump_tokens.py` missing). v168 waits; nothing else changed.
```

Then commit that one file on `main` and stop. Do not create the worktree, do not touch v167's worktree, branch or plan text.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/plans/2026-10-16-v168-motion-system_0-index.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v168): handoff -- v167 not merged yet, plan waits (MO1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Report `BLOCKED: v167 not merged` with the failing check lines. The controller decides when to resume.

- [ ] **Step 3: Create (or reuse) the worktree**

Invoke the `worktree-lifecycle` skill. If `git -C E:/Documents/Private/Projects/Discord-Bot worktree list` already shows `2026-10-16-v168-motion-system`, reuse it and skip to Step 4. Otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-16-v168-motion-system -b 2026-10-16-v168-motion-system main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v168-motion-system log --oneline -1
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v168-motion-system/frontend ci
```

Expected: the log line is the current `main` HEAD (it carries v167 and this plan); `npm ci` ends without `ERR!`.

- [ ] **Step 4: Baseline the gates in the worktree**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/flash.spec.ts --include src/app/ui/pnl-cell.spec.ts
python $WT/scripts/dev/dump_tokens.py --check
```

Expected: `Tests  N passed (N)`, 0 failed; `--check` exits 0. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once. If anything else fails, stop and report it: the plan assumes a green start.

- [ ] **Step 5: Report**

No commit (the worktree is the deliverable). Report the worktree path, the HEAD line and the baseline verdict line.

### Task MO2: Motion tokens in the tier-3 block, `calc()` durations, `--panel-shadow-lift` on the rgb allow-list, fixture

**Model:** sonnet — token block, fixture regen and two gate edits, values fixed by the spec

**Files:**
- Modify: `frontend/src/styles/tokens.css` (the three `--dur-*` lines in the tier-2 `-- radii, motion --` section, today `:271-273`; the tier-3 header comment; the end of the tier-3 `:root` block)
- Modify: `frontend/src/app/ui/tokens.spec.ts` (`REQUIRED`; one `describe` appended)
- Modify: `frontend/src/app/ui/primitives.spec.ts` (`TIER3_RGB` and the title of the case that uses it)
- Modify: `tests/charts/resolved_tokens.json` (regenerated, never hand-edited)

**Interfaces:**
- Consumes: MO1's worktree. From v167 on `main`: `TIER3_BANNER`/`TIER3` and `resolveToken` (imported) in `tokens.spec.ts`; `TIER3_RGB = new Set(['--panel-shadow', '--shadow-overlay', '--scrim-soft'])` in `primitives.spec.ts`; `scripts/dev/dump_tokens.py [--check]`.
- Produces (every later task reads these names; values verbatim from the index Global Constraints):
  - tier 2, changed in place: `--dur-instant: calc(90ms * var(--motion-scale))`, `--dur-base: calc(160ms * var(--motion-scale))`, `--dur-slow: calc(260ms * var(--motion-scale))`.
  - tier 3, new, inside the block: `--motion-scale: 1`, `--dur-enter: calc(420ms * var(--motion-scale))`, `--dur-count: calc(900ms * var(--motion-scale))`, `--dur-draw: calc(1200ms * var(--motion-scale))`, `--flash-up-text: var(--pos)`, `--flash-down-text: var(--neg)`, `--panel-shadow-lift: 0 10px 28px rgba(0, 0, 0, .35)`.
  - `TIER3_RGB` gains `--panel-shadow-lift`.
  - `tokens.spec.ts` `REQUIRED` gains the seven names above; new case `scales every duration by --motion-scale`.

**Not in this task:** `[data-motion=off] { --motion-scale: 0; }` (MO3, in `motion.css`, never in `tokens.css`); deleting the global `prefers-reduced-motion` block and rewriting the "nothing on entrance" comment (MO6). `--ease-out` and `--ease-spring` are not edited.

- [ ] **Step 1: Write the failing tests in `tokens.spec.ts`**

In `frontend/src/app/ui/tokens.spec.ts`, in `REQUIRED`, add this group just before the closing `];` (after v167's `// v167 §3, tier 3` group):

```ts

  // v168 §1, motion (tier 3)
  '--motion-scale',
  '--dur-enter',
  '--dur-count',
  '--dur-draw',
  '--flash-up-text',
  '--flash-down-text',
  '--panel-shadow-lift',
```

Append at the very end of the file:

```ts
/**
 * v168 §1: every duration is a calc() over --motion-scale, so one declaration
 * in styles/motion.css ([data-motion=off] { --motion-scale: 0; }) zeroes them
 * all. The scale's default and every new v168 token sit INSIDE v167's tier-3
 * block (spec v168 amendment 9): dump_tokens.py and resolve-token.ts read
 * every top-level :root, and motion.css is outside both, so the default must
 * live here. Reduced is not a multiplier (spec §1): the scale is only ever 1
 * or 0.
 */
describe('v168 §1: motion tokens', () => {
  const declared = (source: string, name: string) =>
    source.match(new RegExp(`^\\s*${name}:\\s*([^;]+);`, 'm'))?.[1].replace(/\s+/g, ' ').trim();

  const DURATIONS: Record<string, string> = {
    '--dur-instant': '90ms',
    '--dur-base': '160ms',
    '--dur-slow': '260ms',
    '--dur-enter': '420ms',
    '--dur-count': '900ms',
    '--dur-draw': '1200ms',
  };

  it('scales every duration by --motion-scale', () => {
    for (const [name, ms] of Object.entries(DURATIONS)) {
      expect(declared(CSS, name), name).toBe(`calc(${ms} * var(--motion-scale))`);
    }
  });

  it('declares the scale once, as 1, in tier 3', () => {
    expect(declared(TIER3, '--motion-scale')).toBe('1');
    expect([...CSS.matchAll(/^\s*--motion-scale:/gm)]).toHaveLength(1);
  });

  it('puts every new v168 token inside the tier-3 block', () => {
    const NEW = ['--dur-enter', '--dur-count', '--dur-draw', '--flash-up-text', '--flash-down-text', '--panel-shadow-lift'];
    for (const name of NEW) {
      expect(TIER3, name).toMatch(new RegExp(`^\\s*${name}:`, 'm'));
      expect([...CSS.matchAll(new RegExp(`^\\s*${name}:`, 'gm'))], name).toHaveLength(1);
    }
  });

  it('keeps both easings exactly as they were', () => {
    expect(declared(CSS, '--ease-out')).toBe('cubic-bezier(0.2, 0.8, 0.3, 1)');
    expect(declared(CSS, '--ease-spring')).toBe('cubic-bezier(0.34, 1.4, 0.64, 1)');
  });

  it('gives the flash text and the hover-lift shadow their spec values', () => {
    expect(declared(TIER3, '--flash-up-text')).toBe('var(--pos)');
    expect(declared(TIER3, '--flash-down-text')).toBe('var(--neg)');
    expect(declared(TIER3, '--panel-shadow-lift')).toBe('0 10px 28px rgba(0, 0, 0, .35)');
  });

  it('reaches jsdom with the scale already resolved', () => {
    expect(resolveToken('--dur-base')).toBe('calc(160ms * 1)');
    expect(resolveToken('--motion-scale')).toBe('1');
  });
});
```

(`CSS`, `TIER3` and `resolveToken` are already in scope from v167. If `resolveToken` is not imported at the top of the file, add it to the existing import from `./testing/resolve-token`.)

- [ ] **Step 2: Run it and watch it fail**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/tokens.spec.ts
```

Expected: FAIL. The seven new `defines --…` cases fail, and in `v168 §1: motion tokens` every case except `keeps both easings exactly as they were` fails (`declared` is `undefined`; `resolveToken('--dur-base')` is `160ms`, and `resolveToken('--motion-scale')` throws because the token does not exist).

- [ ] **Step 3: Allow the lift shadow's rgba in the colour gate**

In `frontend/src/app/ui/primitives.spec.ts`, find `const TIER3_RGB = new Set(['--panel-shadow', '--shadow-overlay', '--scrim-soft']);` and replace it with:

```ts
/* v168 amendment 8: the hover lift's deeper shadow is black at an alpha too. */
const TIER3_RGB = new Set(['--panel-shadow', '--shadow-overlay', '--scrim-soft', '--panel-shadow-lift']);
```

In the same file, rename the case `it('keeps rgb()/rgba() inside the three tier-3 tokens only', ...)` to `it('keeps rgb()/rgba() inside the four tier-3 shadow and scrim tokens only', ...)` (body unchanged). In the comment block just above `TOKENS_HEX_ALLOWED`, change "rgb()/rgba() only inside the three tier-3 shadow and scrim tokens" to "rgb()/rgba() only inside the four tier-3 shadow and scrim tokens". Do not touch G3 (MO10 extends it).

- [ ] **Step 4: Scale the three existing durations**

In `frontend/src/styles/tokens.css`, find

```css
  --dur-instant: 90ms;
  --dur-base: 160ms;
  --dur-slow: 260ms;
```

and replace it with

```css
  /* v168 §1: scaled by --motion-scale (tier 3, below), which is 1 and
   * becomes 0 only under [data-motion=off] in styles/motion.css. */
  --dur-instant: calc(90ms * var(--motion-scale));
  --dur-base: calc(160ms * var(--motion-scale));
  --dur-slow: calc(260ms * var(--motion-scale));
```

Leave `--ease-out`, `--ease-spring`, `--transition` and the `-- radii, motion --` comment as they are (MO6 rewrites that comment).

- [ ] **Step 5: Add the motion tokens inside the tier-3 block**

In the tier-3 header comment (the block right under `/* ===== Tier 3: component tokens (spec v167 §3) ===== */`), change

```css
 * are black or white at an alpha, inside --panel-shadow, --shadow-overlay
 * and --scrim-soft (the colour gate, primitives.spec.ts).
```

to

```css
 * are black or white at an alpha, inside --panel-shadow, --shadow-overlay,
 * --panel-shadow-lift and --scrim-soft (the colour gate, primitives.spec.ts).
```

Then, inside the same tier-3 `:root { … }`, directly before its closing `}` (after `--scrim-soft: rgb(0 0 0 / 0.5);`), insert:

```css

  /* -- motion (spec v168 §1) ---------------------------------------------
   * --motion-scale is 1 here and 0 only under [data-motion=off]
   * (styles/motion.css). Never a fraction: Reduced is written as
   * [data-motion=reduced] rules, not as a faster multiplier. Every
   * --dur-* token, here and in tier 2, is calc(<ms> * var(--motion-scale)).
   * The default must live in this file: motion.css is outside the token
   * resolver's STYLE_FILES, so the fixture would not see it. */
  --motion-scale: 1;
  --dur-enter: calc(420ms * var(--motion-scale));   /* route entrance, stagger */
  --dur-count: calc(900ms * var(--motion-scale));   /* first count-up */
  --dur-draw: calc(1200ms * var(--motion-scale));   /* chart draw-in */

  /* The text colour a changed cell takes while its tint fades (#8). */
  --flash-up-text: var(--pos);
  --flash-down-text: var(--neg);

  /* The hover lift's deeper shadow (#5), cast only from styles/motion.css;
   * primitives.spec.ts G3 holds that file to it and --glow-accent. */
  /* Box-shadow geometry (blur/offset) is intentionally exempt from the "px only for 1px/2px borders" rule per design spec D2 -- shadow values have no natural expression via the closed --space-* scale. */
  --panel-shadow-lift: 0 10px 28px rgba(0, 0, 0, .35);
```

The tier-3 block must stay the last top-level block and contain no `@media` (v167's `sits in one :root block` case).

- [ ] **Step 6: Regenerate the fixture and check it**

```bash
python $WT/scripts/dev/dump_tokens.py
python $WT/scripts/dev/dump_tokens.py --check
git -C $WT diff -- tests/charts/resolved_tokens.json
```

Expected: `--check` exits 0. The diff changes `dur-instant`, `dur-base`, `dur-slow` to `calc(90ms * 1)`, `calc(160ms * 1)`, `calc(260ms * 1)`, changes `transition` to `calc(160ms * 1) cubic-bezier(0.2, 0.8, 0.3, 1)`, and adds `motion-scale`, `dur-enter`, `dur-count`, `dur-draw`, `flash-up-text`, `flash-down-text` (the resolved `--pos`/`--neg` hex) and `panel-shadow-lift`. Nothing else moves. If the resolver writes the `calc` with different spacing than `calc(160ms * 1)`, copy the fixture's exact `dur-base` string into the `reaches jsdom` case: the fixture is what jsdom sees, and the case pins it.

- [ ] **Step 7: Run the narrow runs**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/flash.spec.ts --include src/app/ui/pnl-cell.spec.ts
python $WT/scripts/dev/testrun.py file tests/dev/test_dump_tokens.py
python $WT/scripts/dev/testrun.py file tests/charts/test_chart_theme.py
```

Expected: frontend `Tests  N passed (N)`, 0 failed; both Python runs `N passed`, 0 failed. Quote the three verdict lines.

- [ ] **Step 8: Commit**

```bash
git -C $WT add frontend/src/styles/tokens.css frontend/src/app/ui/tokens.spec.ts frontend/src/app/ui/primitives.spec.ts tests/charts/resolved_tokens.json
git -C $WT commit -m "feat(ui): v168 motion tokens -- --motion-scale, calc() durations, flash text, lift shadow (MO2)

--dur-instant/base/slow become calc(<ms> * var(--motion-scale)); tier 3
gains --motion-scale: 1, --dur-enter/count/draw, --flash-up-text/-down-text
and --panel-shadow-lift (black rgba, now on the colour gate's tier-3
allow-list). Easings unchanged. Fixture regenerated.

<frontend verdict line>
<test_dump_tokens.py verdict line>
<test_chart_theme.py verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO3: `styles/motion.css`: every keyframe moved and merged, the motion class catalogue and its mode rules; `motion-home` gate

**Model:** sonnet — a CSS catalogue plus a source gate, names fixed by the ledger

**Files:**
- Create: `frontend/src/styles/motion.css`
- Create: `frontend/src/app/ui/motion-home.spec.ts`
- Create: `frontend/src/app/ui/motion-css.spec.ts`
- Modify: `frontend/src/styles.css` (the `@import` list; the flash block, today `:231-237`)
- Modify: `frontend/src/app/shell/connection-status.ts` (`.dot.live` animation, today `:63`; `@keyframes pulse`, today `:88`)
- Modify: `frontend/src/app/shell/scan-progress.css` (`.strip` animation `:22`, `.fill.sweeping` animation `:62`, two `@keyframes` `:77-85`)
- Modify: `frontend/src/app/shell/shell.css` (`.route-loading-mark` animation and `@keyframes route-spin`, today `:371-372`)
- Modify: `frontend/src/app/shell/tape/tape.css` (`.track` `animation-name`, `@keyframes tape-slide`, today `:56`, `:60-61`)
- Modify: `frontend/src/app/ui/data-table/data-table.ts` (`.loading-spinner` animation `:235`, `@keyframes spin` `:238-240`, `@keyframes sb-row-blink` `:332-335`)
- Modify: `frontend/src/app/ui/chart-container.ts` (`.spinner` animation `:138`, `@keyframes spin` `:140-144`)
- Modify: `frontend/src/app/ui/status-indicator.ts` (`.open` animation `:76`, `@keyframes pulse` `:79`)
- Modify: `frontend/src/app/ui/status-cell.ts` (`.dot` `animation-name` `:145`, `@keyframes pulse` `:153`)
- Modify: `frontend/src/app/ui/async.ts` (`.skeleton-cell` animation `:107`, `@keyframes pulse` `:109`)

**Interfaces:**
- Consumes: MO2's tokens (`--motion-scale`, `--dur-base`, `--dur-enter`, `--dur-draw`, `--ease-out`, `--ease-spring`, `--flash-up-text`, `--flash-down-text`, `--panel-shadow-lift`); v167's `--border-strong`, `--accent-soft`, `--pos-soft`, `--neg-soft`, `--warn`.
- Produces (binding for MO6..MO17; names verbatim from the ledger):
  - `styles.css`: `@import './styles/motion.css';` directly after `@import './styles/tokens.css';`; the flash block is gone from `styles.css`.
  - Keyframes, each defined once in `motion.css` and nowhere else: moved `sb-pulse-soft`, `sb-pulse-dim`, `sb-pulse-blink`, `sb-spin`, `sb-route-spin`, `sb-scan-sweep`, `sb-scan-strip-in`, `sb-flash-up`, `sb-flash-down`, `sb-row-blink`, `sb-tape-slide`; new `sb-enter`, `sb-fade-in`, `sb-pop-in`, `sb-drawer-in`, `sb-drawer-out`, `sb-sheet-in`, `sb-sheet-out`, `sb-fade-out`, `sb-ping`, `sb-shimmer`, `sb-draw-inset`, `sb-draw-circle`, `sb-ambient-drift`.
  - Classes: `.sb-enter`; `.sb-entering` (route host state, MO7 adds and removes it) with the stagger on `.sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > *` (60ms steps, cap 8 from 640px; 40ms steps, cap 4 below); `.sb-stagger` (a marker for that selector, no rule of its own); `.sb-lift`; `.sb-pop-in`; `.sb-drawer-in`; `.sb-drawer-out`; `.sb-sheet-in`; `.sb-fade-out`; `.sb-draw-in`; `.sb-draw-in-radial`; `.flash-up` / `.flash-down` (`calc(1100ms * var(--motion-scale))`, `--flash-*-text`).
  - `[data-motion=off] { --motion-scale: 0; }`, and the reduced/off/pending rules for every new class, on the contracted selectors `sb-drawer dialog`, `sb-confirm-dialog dialog`, `.ambient`, `sb-connection-status .dot.live::after`, `sb-async .skeleton-cell`, `sb-nav-indicator .nav-indicator`.
  - `motion-home.spec.ts`: `const KEYFRAME_HOME = 'styles/motion.css'`; `function sourceFiles(): { name: string; source: string }[]` (every `.ts`/`.css` under `frontend/src`, `/`-separated names relative to `frontend/src`, `*.spec.ts` excluded). MO6 appends a case to its `describe`.
  - `motion-css.spec.ts`: helpers `read`, `uncomment`, `bodyAt`, `blocksOf`, `rules`, `splitList`, `bodiesFor`, `keyframeList`, constant `KEYFRAMES` (the list above) and `STAGGER`; MO6 appends `describe('Off keeps every fallback')`, MO9 drops `sb-pulse-soft` from `KEYFRAMES`, MO10 nothing here (G3 lives in `primitives.spec.ts`).
  - **Timing contract for MO7:** the last staggered child ends at 420ms delay + 420ms = 840ms (phone: 120 + 420 = 540ms), later than the host's own 420ms `animationend`. `.sb-entering` must stay on the host until then; `ENTRANCE_FALLBACK_MS = 1000` covers it, the host's own `animationend` alone does not.
  - **For MO11:** `sb-nav-indicator`'s own styles declare no `transition` on `.nav-indicator`; its motion lives here, per mode.

**Not in this task:** the nine `prefers-reduced-motion` fallback sites stay exactly as they are (MO6 turns them into `[data-motion]` rules here and deletes them); the global block in `tokens.css` stays (MO6). No component adopts a new class yet (MO7..MO16). The flash keeps adding its class under every mode until MO14.

- [ ] **Step 1: Write the keyframe-home gate**

Create `frontend/src/app/ui/motion-home.spec.ts`:

```ts
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Spec v168 §2: every @keyframes in the app lives in styles/motion.css, and
 * every animation names one of them.
 *
 * Before v168, `pulse` was declared four times in three different shapes
 * and `spin` twice; a fifth copy would have been one more silent variant.
 * Keyframe names are global, so a component references motion.css's names
 * directly.
 *
 * The walk covers every .ts and .css under src/ (styles/ included, which
 * v167's allSources() skips), names relative to src/ with `/`. Spec files
 * are excluded, this one included: they quote CSS on purpose. Sources are
 * read with readFileSync from process.cwd(), never `?raw` (tokens.spec.ts
 * records why).
 */
const SRC = join(process.cwd(), 'src');
const KEYFRAME_HOME = 'styles/motion.css';

function sourceFiles(): { name: string; source: string }[] {
  const found: { name: string; source: string }[] = [];
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(path);
        continue;
      }
      if (!/\.(ts|css)$/.test(entry.name) || entry.name.endsWith('.spec.ts')) continue;
      found.push({ name: relative(SRC, path).split(sep).join('/'), source: readFileSync(path, 'utf8') });
    }
  };
  walk(SRC);
  return found.sort((a, b) => a.name.localeCompare(b.name));
}

const uncomment = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, '');
const KEYFRAME_DECL = /@keyframes\s+([\w-]+)\s*\{/g;
/** `animation: <name> …` and `animation-name: <name>`; keywords are not names. */
const ANIMATION_REF = /\banimation(?:-name)?:\s*([a-z][\w-]*)/g;
const NOT_A_NAME = new Set(['none', 'inherit', 'initial', 'unset', 'revert', 'var', 'calc']);

describe('one keyframe home (v168 §2)', () => {
  const files = sourceFiles();

  it('walks the sources it is meant to', () => {
    const names = files.map(({ name }) => name);
    expect(names).toContain(KEYFRAME_HOME);
    expect(names).toContain('styles.css');
    expect(names).toContain('app/ui/async.ts');
    expect(names).toContain('app/shell/scan-progress.css');
    expect(names.filter((name) => name.endsWith('.spec.ts'))).toEqual([]);
  });

  it('declares @keyframes only in styles/motion.css', () => {
    const offenders = files
      .filter(({ name, source }) => name !== KEYFRAME_HOME && /@keyframes\s+[\w-]+\s*\{/.test(uncomment(source)))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });

  it('names only keyframes that motion.css defines', () => {
    const home = files.find(({ name }) => name === KEYFRAME_HOME)!;
    const defined = new Set([...uncomment(home.source).matchAll(KEYFRAME_DECL)].map(([, name]) => name));
    const unknown = files.flatMap(({ name, source }) =>
      [...uncomment(source).matchAll(ANIMATION_REF)]
        .map(([, ref]) => ref)
        .filter((ref) => !NOT_A_NAME.has(ref) && !defined.has(ref))
        .map((ref) => `${name}: ${ref}`),
    );
    expect(unknown).toEqual([]);
  });
});
```

- [ ] **Step 2: Write the motion.css catalogue spec**

Create `frontend/src/app/ui/motion-css.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * styles/motion.css (spec v168 §1-§3), asserted as SOURCE TEXT. jsdom sees
 * flattened tokens and no @media (v167), so a computed-style read would
 * prove nothing; behaviour is asserted elsewhere through classes, attributes
 * and the MotionStarts log. Read with readFileSync from process.cwd(), never
 * `?raw` (tokens.spec.ts records why).
 */
const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
const uncomment = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '');
const MOTION = uncomment(read('src/styles/motion.css'));
const STYLES = uncomment(read('src/styles.css'));

/** The body of the block whose `{` is the first one at or after `from`, braces matched. */
function bodyAt(css: string, from: number): string {
  const open = css.indexOf('{', from);
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === '{') depth++;
    if (css[i] === '}' && --depth === 0) return css.slice(open + 1, i);
  }
  return css.slice(open + 1);
}

/** The bodies of every block opened by `header` (e.g. one media query), joined. */
function blocksOf(css: string, header: string): string {
  const found: string[] = [];
  for (let at = css.indexOf(header); at !== -1; at = css.indexOf(header, at + header.length)) {
    found.push(bodyAt(css, at));
  }
  return found.join('\n');
}

/** Every innermost rule, selector and body whitespace-collapsed. */
function rules(css: string): { selector: string; body: string }[] {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selector, body]) => ({
    selector: selector.replace(/\s+/g, ' ').trim(),
    body: body.replace(/\s+/g, ' ').trim(),
  }));
}

/** A selector list split on its top-level commas, not those inside `:is(…)`. */
function splitList(list: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < list.length; i++) {
    if (list[i] === '(') depth++;
    if (list[i] === ')') depth--;
    if (list[i] === ',' && depth === 0) {
      parts.push(list.slice(start, i).trim());
      start = i + 1;
    }
  }
  parts.push(list.slice(start).trim());
  return parts;
}

/** The bodies of the rules whose selector list contains `selector` verbatim. */
function bodiesFor(css: string, selector: string): string[] {
  return rules(css)
    .filter(({ selector: list }) => splitList(list).includes(selector))
    .map(({ body }) => body);
}

/** Every `@keyframes name { … }`, in source order. */
function keyframeList(css: string): [string, string][] {
  return [...css.matchAll(/@keyframes\s+([\w-]+)\s*\{/g)].map((match) => [
    match[1],
    bodyAt(css, match.index!).replace(/\s+/g, ' ').trim(),
  ]);
}

const KEYFRAMES = [
  // moved (v168 §2, amendment 7)
  'sb-pulse-soft', 'sb-pulse-dim', 'sb-pulse-blink', 'sb-spin', 'sb-route-spin', 'sb-scan-sweep',
  'sb-scan-strip-in', 'sb-flash-up', 'sb-flash-down', 'sb-row-blink', 'sb-tape-slide',
  // new (v168 §3)
  'sb-enter', 'sb-fade-in', 'sb-pop-in', 'sb-drawer-in', 'sb-drawer-out', 'sb-sheet-in', 'sb-sheet-out',
  'sb-fade-out', 'sb-ping', 'sb-shimmer', 'sb-draw-inset', 'sb-draw-circle', 'sb-ambient-drift',
];
const NEW_KEYFRAMES = KEYFRAMES.slice(KEYFRAMES.indexOf('sb-enter'));
const COMPOSITOR = new Set(['transform', 'opacity', 'filter', 'clip-path', 'background-position']);
const STAGGER = '.sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > ';
const ENTRANCES = ['.sb-enter', '.sb-entering', '.sb-pop-in', '.sb-drawer-in', '.sb-sheet-in', '.sb-draw-in', '.sb-draw-in-radial'];
const NEW_CLASSES = [...ENTRANCES, '.sb-drawer-out', '.sb-fade-out', `${STAGGER}*`];

describe('styles/motion.css: the one motion home (v168 §2)', () => {
  it('is imported by styles.css right after tokens.css', () => {
    const imports = [...STYLES.matchAll(/@import\s+'([^']+)';/g)].map(([, path]) => path);
    expect(imports).toContain('./styles/tokens.css');
    expect(imports.indexOf('./styles/motion.css')).toBe(imports.indexOf('./styles/tokens.css') + 1);
  });

  it('defines every keyframe exactly once, and no others', () => {
    const names = keyframeList(MOTION).map(([name]) => name);
    expect([...names].sort()).toEqual([...KEYFRAMES].sort());
  });

  it('took the flash out of styles.css', () => {
    expect(STYLES).not.toMatch(/@keyframes/);
    expect(STYLES).not.toMatch(/\.flash-(up|down)\s*\{/);
  });

  it('merges the four pulse copies by shape, each shape unchanged (amendment 7)', () => {
    const body = Object.fromEntries(keyframeList(MOTION));
    expect(body['sb-pulse-soft']).toBe('50% { opacity: 0.45; }');
    expect(body['sb-pulse-dim']).toBe('50% { opacity: 0.35; }');
    expect(body['sb-pulse-blink']).toBe('0%, 100% { opacity: 1; } 50% { opacity: 0.25; }');
    expect(body['sb-spin']).toBe('to { transform: rotate(360deg); }');
  });

  it('zeroes the scale only under Off', () => {
    const scaled = rules(MOTION).filter(({ body }) => body.includes('--motion-scale:'));
    expect(scaled).toEqual([{ selector: '[data-motion=off]', body: '--motion-scale: 0;' }]);
  });

  it('animates only compositor-friendly properties in the new keyframes', () => {
    const body = Object.fromEntries(keyframeList(MOTION));
    for (const name of NEW_KEYFRAMES) {
      const properties = [...body[name].matchAll(/([\w-]+)\s*:/g)].map(([, property]) => property);
      expect(properties.length, name).toBeGreaterThan(0);
      expect(properties.filter((property) => !COMPOSITOR.has(property)), name).toEqual([]);
    }
  });

  it('refines the cell flash: 1.1s, tint plus the tier-3 text colour (#8)', () => {
    const body = Object.fromEntries(keyframeList(MOTION));
    expect(bodiesFor(MOTION, '.flash-up')).toEqual(['animation: sb-flash-up calc(1100ms * var(--motion-scale)) var(--ease-out);']);
    expect(bodiesFor(MOTION, '.flash-down')).toEqual(['animation: sb-flash-down calc(1100ms * var(--motion-scale)) var(--ease-out);']);
    expect(body['sb-flash-up']).toBe('from { background: var(--pos-soft); color: var(--flash-up-text); } to { background: transparent; }');
    expect(body['sb-flash-down']).toBe('from { background: var(--neg-soft); color: var(--flash-down-text); } to { background: transparent; }');
  });
});

describe('the motion classes (v168 §3)', () => {
  it('holds every entrance at its first frame with fill-mode backwards', () => {
    for (const cls of [...ENTRANCES, `${STAGGER}*`]) {
      const animations = bodiesFor(MOTION, cls).filter((body) => body.includes('animation:'));
      expect(animations.length, cls).toBeGreaterThan(0);
      for (const body of animations) expect(body, cls).toMatch(/animation: [^;]*\bbackwards;/);
    }
  });

  it('holds every exit at its last frame', () => {
    expect(bodiesFor(MOTION, '.sb-drawer-out')[0]).toMatch(/animation: sb-drawer-out [^;]*\bforwards;/);
    expect(bodiesFor(MOTION, '.sb-fade-out')[0]).toMatch(/animation: sb-fade-out [^;]*\bforwards;/);
  });

  it('staggers 60ms apart from 640px, capped at the eighth child', () => {
    const delays = Object.fromEntries(
      rules(blocksOf(MOTION, '@media (min-width: 640px)'))
        .filter(({ selector }) => selector.startsWith(STAGGER))
        .map(({ selector, body }) => [selector.slice(STAGGER.length), body]),
    );
    const step = (ms: number) => `animation-delay: calc(${ms}ms * var(--motion-scale));`;
    expect(delays).toEqual({
      ':nth-child(2)': step(60),
      ':nth-child(3)': step(120),
      ':nth-child(4)': step(180),
      ':nth-child(5)': step(240),
      ':nth-child(6)': step(300),
      ':nth-child(7)': step(360),
      ':nth-child(n + 8)': step(420),
    });
  });

  it('staggers 40ms apart below 640px, capped at the fourth child', () => {
    const delays = Object.fromEntries(
      rules(blocksOf(MOTION, '@media (max-width: 639px)'))
        .filter(({ selector }) => selector.startsWith(STAGGER))
        .map(({ selector, body }) => [selector.slice(STAGGER.length), body]),
    );
    const step = (ms: number) => `animation-delay: calc(${ms}ms * var(--motion-scale));`;
    expect(delays).toEqual({ ':nth-child(2)': step(40), ':nth-child(3)': step(80), ':nth-child(n + 4)': step(120) });
  });

  it('lifts on hover only where hover exists, and moves only under On (#5)', () => {
    const hover = blocksOf(MOTION, '@media (hover: hover)');
    expect(bodiesFor(hover, '[data-motion] .sb-lift:hover')).toEqual([
      'border-color: var(--border-strong); box-shadow: var(--panel-shadow-lift);',
    ]);
    expect(bodiesFor(hover, '[data-motion=on] .sb-lift:hover')).toEqual(['transform: translateY(-2px);']);
    expect(MOTION.match(/translateY\(-2px\)/g)).toHaveLength(1);
    expect(bodiesFor(blocksOf(MOTION, '@media (hover: none)'), '[data-motion] .sb-lift:active')).toEqual([
      'box-shadow: inset 0 0 0 100vmax var(--accent-soft);',
    ]);
  });

  it('turns the drawer into a rising sheet below 640px (#7)', () => {
    const phone = blocksOf(MOTION, '@media (max-width: 639px)');
    expect(bodiesFor(phone, 'sb-drawer dialog.sb-drawer-in')).toEqual(['animation-name: sb-sheet-in;']);
    expect(bodiesFor(phone, 'sb-drawer dialog.sb-drawer-out')).toEqual(['animation-name: sb-sheet-out;']);
  });

  it('fades and blurs the dialog backdrops in (#7)', () => {
    for (const host of ['sb-drawer', 'sb-confirm-dialog']) {
      expect(bodiesFor(MOTION, `${host} dialog[open]::backdrop`)).toEqual([
        'backdrop-filter: blur(2px); animation: sb-fade-in calc(200ms * var(--motion-scale)) var(--ease-out) backwards;',
      ]);
    }
  });

  it('sets will-change only on classes that come off when their animation ends (§6)', () => {
    const TRANSIENT = new Set(['.sb-entering', '.sb-drawer-in', '.sb-sheet-in', '.sb-drawer-out', '.sb-draw-in', '.sb-draw-in-radial']);
    const holders = rules(MOTION)
      .filter(({ body }) => body.includes('will-change'))
      .flatMap(({ selector }) => splitList(selector));
    expect(holders.length).toBeGreaterThan(0);
    expect(holders.filter((selector) => !TRANSIENT.has(selector))).toEqual([]);
  });
});

describe('the mode rules for the new classes (v168 §1)', () => {
  it('stops every new animation under Off and while preferences load', () => {
    for (const mode of ['off', 'pending']) {
      for (const cls of NEW_CLASSES) {
        expect(bodiesFor(MOTION, `[data-motion=${mode}] ${cls}`), `${mode} ${cls}`).toContain('animation: none;');
      }
      for (const host of ['sb-drawer', 'sb-confirm-dialog']) {
        expect(bodiesFor(MOTION, `[data-motion=${mode}] ${host} dialog[open]::backdrop`)).toContain('animation: none;');
      }
    }
  });

  it('turns entrances and the dialogs into a plain fade under Reduced', () => {
    for (const cls of ['.sb-enter', '.sb-entering', `${STAGGER}*`, '.sb-pop-in', '.sb-drawer-in', '.sb-sheet-in']) {
      expect(bodiesFor(MOTION, `[data-motion=reduced] ${cls}`), cls).toContain(
        'animation-name: sb-fade-in; animation-duration: var(--dur-base);',
      );
    }
    expect(bodiesFor(MOTION, '[data-motion=reduced] .sb-drawer-out')).toContain('animation-name: sb-fade-out;');
  });

  it('draws no chart in under Reduced (#9)', () => {
    for (const cls of ['.sb-draw-in', '.sb-draw-in-radial']) {
      expect(bodiesFor(MOTION, `[data-motion=reduced] ${cls}`), cls).toContain('animation: none;');
    }
  });

  it('drifts the ambient glow under On only, and never on a phone (#10)', () => {
    expect(bodiesFor(MOTION, '[data-motion=on] .ambient')).toContain('animation: sb-ambient-drift 12s ease-in-out infinite alternate;');
    expect(bodiesFor(blocksOf(MOTION, '@media (max-width: 639px)'), '[data-motion=on] .ambient')).toEqual(['animation: none;']);
    const unscoped = rules(MOTION).filter(({ selector }) => selector.includes('.ambient') && !selector.includes('[data-motion=on]'));
    expect(unscoped).toEqual([]);
  });

  it('stills the live-dot ping outside On (#10)', () => {
    for (const mode of ['reduced', 'off', 'pending']) {
      expect(bodiesFor(MOTION, `[data-motion=${mode}] sb-connection-status .dot.live::after`), mode).toEqual([
        'animation: none; opacity: 0;',
      ]);
    }
  });

  it('gives the skeleton a static tint under Reduced and Off (#4)', () => {
    for (const mode of ['reduced', 'off']) {
      expect(bodiesFor(MOTION, `[data-motion=${mode}] sb-async .skeleton-cell`), mode).toContain('animation: none;');
    }
  });

  it('slides the nav indicator on a spring under On, fades it under Reduced (#6)', () => {
    expect(bodiesFor(MOTION, '[data-motion=on] sb-nav-indicator .nav-indicator')).toEqual([
      'transition: transform calc(350ms * var(--motion-scale)) var(--ease-spring), opacity var(--dur-base) var(--ease-out);',
    ]);
    expect(bodiesFor(MOTION, '[data-motion=reduced] sb-nav-indicator .nav-indicator')).toEqual([
      'transition: opacity var(--dur-base) var(--ease-out);',
    ]);
  });
});
```

- [ ] **Step 3: Run both and watch them fail**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion-home.spec.ts --include src/app/ui/motion-css.spec.ts
```

Expected: FAIL. `motion-css.spec.ts` fails to load (`ENOENT ... src/styles/motion.css`). In `motion-home.spec.ts`, `walks the sources it is meant to` fails (no `styles/motion.css`), `declares @keyframes only in styles/motion.css` lists the ten files (`app/shell/connection-status.ts`, `app/shell/scan-progress.css`, `app/shell/shell.css`, `app/shell/tape/tape.css`, `app/ui/async.ts`, `app/ui/chart-container.ts`, `app/ui/data-table/data-table.ts`, `app/ui/status-cell.ts`, `app/ui/status-indicator.ts`, `styles.css`), and `names only keyframes that motion.css defines` throws on the missing home.

- [ ] **Step 4: Create `frontend/src/styles/motion.css`**

```css
/* ===== Motion (spec v168) ==================================================
 * The one home for motion: every @keyframes in the app, the shared motion
 * classes, and every [data-motion=on|reduced|off|pending] rule.
 * ui/motion-home.spec.ts fails a @keyframes anywhere else, and an animation
 * that names a keyframe this file does not define; ui/motion-css.spec.ts
 * pins what is below.
 *
 * Imported by styles.css right after tokens.css. Keyframe names are global:
 * Angular's emulated encapsulation renames only keyframes a component
 * declares itself, so a component references these names directly.
 *
 * The mode is the data-motion attribute on <html>. The shell writes it from
 * MotionService (ui/motion/motion.service.ts); index.html starts it at
 * `pending`. TS reads the mode from MotionService, never from the attribute.
 *   on       everything (the default)
 *   reduced  no transform-based motion: entrances and dialogs fade, no
 *            count-up, no draw-in, no lift, no ping, no drift, tape frozen
 *   off      no decorative motion: --motion-scale is 0, so every
 *            calc(<ms> * var(--motion-scale)) duration is 0, and every site
 *            keeps its non-motion fallback. Spinners still turn.
 *   pending  before preferences load: no entrance, count-up or draw-in,
 *            tape frozen, so a user who chose Off never sees a cold-load
 *            burst
 * The OS reduced-motion setting is not read, by design (spec D2): the
 * Motion control in the profile menu is the switch, default On.
 *
 * Specificity: a mode rule that overrides a component's own rule has to
 * beat the component's emulated `.x[_ngcontent-…]` (0,2,0), so those rules
 * name the host element too (`sb-async .skeleton-cell`).
 *
 * New animations move only transform, opacity, filter, clip-path and
 * background-position (the flash keyframes paint background and color, as
 * they always did). will-change appears only on classes that come off when
 * their animation ends.
 */

/* -- the mode switch -------------------------------------------------------- */
[data-motion=off] { --motion-scale: 0; }

/* -- moved keyframes: one copy each, every call site keeps its duration ----- */
/* `pulse` was declared four times in three shapes (spec amendment 7). */
@keyframes sb-pulse-soft { 50% { opacity: 0.45; } }                            /* sb-async skeleton */
@keyframes sb-pulse-dim { 50% { opacity: 0.35; } }                             /* live dot, open-trade dot */
@keyframes sb-pulse-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }  /* status-cell dot */
/* `spin` was declared twice (data-table, chart-container), identically. */
@keyframes sb-spin { to { transform: rotate(360deg); } }
@keyframes sb-route-spin { to { transform: rotate(360deg); } }                 /* the shell's route spinner */
@keyframes sb-scan-sweep {
  0%   { margin-left: -35%; }
  100% { margin-left: 100%; }
}
@keyframes sb-scan-strip-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
@keyframes sb-row-blink {
  0%, 100% { background: transparent; }
  50% { background: color-mix(in srgb, var(--warn) 16%, transparent); }
}
@keyframes sb-tape-slide {
  from { transform: translateX(0); }
  to   { transform: translateX(-50%); }
}

/* -- #8 cell value flash ----------------------------------------------------
 * Scoped to the cell whose value changed, never the card: under real-time
 * push a card flash on every event would be a permanent flicker. ui/flash.ts
 * adds and removes these classes (the class names are asserted by
 * flash.spec.ts and pnl-cell.spec.ts). The tint fades over 1.1s (was
 * --dur-base) and the text briefly takes the tier-3 flash colour. */
@keyframes sb-flash-up { from { background: var(--pos-soft); color: var(--flash-up-text); } to { background: transparent; } }
@keyframes sb-flash-down { from { background: var(--neg-soft); color: var(--flash-down-text); } to { background: transparent; } }
.flash-up { animation: sb-flash-up calc(1100ms * var(--motion-scale)) var(--ease-out); }
.flash-down { animation: sb-flash-down calc(1100ms * var(--motion-scale)) var(--ease-out); }

/* -- new keyframes (spec v168 §3) ------------------------------------------- */
@keyframes sb-enter { from { opacity: 0; transform: translateY(8px); filter: blur(3px); } }
@keyframes sb-fade-in { from { opacity: 0; } }
@keyframes sb-pop-in { from { opacity: 0; transform: scale(0.96); } }
@keyframes sb-drawer-in { from { transform: translateX(100%); } }
@keyframes sb-drawer-out { to { transform: translateX(100%); } }
@keyframes sb-sheet-in { from { transform: translateY(100%); } }
@keyframes sb-sheet-out { to { transform: translateY(100%); } }
@keyframes sb-fade-out { to { opacity: 0; } }
@keyframes sb-ping { from { opacity: 0.6; transform: scale(1); } to { opacity: 0; transform: scale(2.6); } }
@keyframes sb-shimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }
@keyframes sb-draw-inset { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0); } }
@keyframes sb-draw-circle { from { clip-path: circle(0); } to { clip-path: circle(75%); } }
@keyframes sb-ambient-drift { from { transform: translate3d(0, 0, 0); } to { transform: translate3d(4%, 3%, 0); } }

/* -- #1 route entrance, #2 staggered panels ---------------------------------
 * Claimed once per route activation (RouteEntryService, MO7): the routed
 * host div.workspace-content gets .sb-entering, and the direct children of
 * the workspace's top-level .sb-stack / .sb-row / sb-panel-grid (or any
 * container marked .sb-stagger) follow it in, one step apart. Fill mode
 * `backwards`: nothing lingers after the animation, so no transform or
 * filter is left to become a containing block for position: fixed/sticky
 * descendants.
 * The last staggered child ends at 420 + 420 = 840ms (phone 540ms), after
 * the host's own animationend; the route host keeps .sb-entering for
 * ENTRANCE_FALLBACK_MS (1000ms) so no child is cut off. */
.sb-enter { animation: sb-enter var(--dur-enter) var(--ease-out) backwards; }
.sb-entering {
  animation: sb-enter var(--dur-enter) var(--ease-out) backwards;
  will-change: transform, opacity, filter;
}
.sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > * {
  animation: sb-enter var(--dur-enter) var(--ease-out) backwards;
}
@media (min-width: 640px) {
  .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > :nth-child(2) { animation-delay: calc(60ms * var(--motion-scale)); }
  .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > :nth-child(3) { animation-delay: calc(120ms * var(--motion-scale)); }
  .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > :nth-child(4) { animation-delay: calc(180ms * var(--motion-scale)); }
  .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > :nth-child(5) { animation-delay: calc(240ms * var(--motion-scale)); }
  .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > :nth-child(6) { animation-delay: calc(300ms * var(--motion-scale)); }
  .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > :nth-child(7) { animation-delay: calc(360ms * var(--motion-scale)); }
  .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > :nth-child(n + 8) { animation-delay: calc(420ms * var(--motion-scale)); }
}
@media (max-width: 639px) {
  .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > :nth-child(2) { animation-delay: calc(40ms * var(--motion-scale)); }
  .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > :nth-child(3) { animation-delay: calc(80ms * var(--motion-scale)); }
  .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > :nth-child(n + 4) { animation-delay: calc(120ms * var(--motion-scale)); }
}

/* -- #5 hover and press ------------------------------------------------------
 * Panels and cards (.sb-lift beside .sb-panel, MO10). The deeper shadow is
 * the tier-3 --panel-shadow-lift, cast only here (primitives.spec.ts G3).
 * `[data-motion]` lifts the specificity over .sb-panel's own shadow and a
 * component's border. Lift only where a pointer can hover; on touch a press
 * tints instead (an inset shadow is a border, not elevation, so G3 skips it). */
.sb-lift {
  transition: transform var(--dur-base) var(--ease-out), border-color var(--dur-base) var(--ease-out), box-shadow var(--dur-base) var(--ease-out);
}
@media (hover: hover) {
  [data-motion] .sb-lift:hover { border-color: var(--border-strong); box-shadow: var(--panel-shadow-lift); }
  [data-motion=on] .sb-lift:hover { transform: translateY(-2px); }
}
@media (hover: none) {
  [data-motion] .sb-lift:active { box-shadow: inset 0 0 0 100vmax var(--accent-soft); }
}

/* -- #7 drawer, dialog, toast ------------------------------------------------
 * In: 450ms on the spring; out: 200ms, held at the last frame until the
 * component closes the <dialog> on animationend (MO12) or Angular removes the
 * toast (MO13). Below 640px the drawer is a bottom sheet (MO12's geometry),
 * so it rises and sinks instead of sliding. */
.sb-pop-in { animation: sb-pop-in calc(450ms * var(--motion-scale)) var(--ease-spring) backwards; }
.sb-drawer-in {
  animation: sb-drawer-in calc(450ms * var(--motion-scale)) var(--ease-spring) backwards;
  will-change: transform;
}
.sb-sheet-in {
  animation: sb-sheet-in calc(450ms * var(--motion-scale)) var(--ease-spring) backwards;
  will-change: transform;
}
.sb-drawer-out {
  animation: sb-drawer-out calc(200ms * var(--motion-scale)) var(--ease-out) forwards;
  will-change: transform;
}
.sb-fade-out { animation: sb-fade-out calc(200ms * var(--motion-scale)) var(--ease-out) forwards; }
@media (max-width: 639px) {
  sb-drawer dialog.sb-drawer-in { animation-name: sb-sheet-in; }
  sb-drawer dialog.sb-drawer-out { animation-name: sb-sheet-out; }
}
sb-drawer dialog[open]::backdrop,
sb-confirm-dialog dialog[open]::backdrop {
  backdrop-filter: blur(2px);
  animation: sb-fade-in calc(200ms * var(--motion-scale)) var(--ease-out) backwards;
}

/* -- #9 chart draw-in --------------------------------------------------------
 * A clip-path reveal on the chart's host, the same for SVG and canvas
 * (sbDrawIn, MO15); the radial variant is for the gauge and the donut. */
.sb-draw-in {
  animation: sb-draw-inset var(--dur-draw) var(--ease-out) backwards;
  will-change: clip-path;
}
.sb-draw-in-radial {
  animation: sb-draw-circle var(--dur-draw) var(--ease-out) backwards;
  will-change: clip-path;
}

/* -- #10 ambient glow drift (the layer itself is MO16's) --------------------
 * On only, and static on a phone (battery). */
[data-motion=on] .ambient { animation: sb-ambient-drift 12s ease-in-out infinite alternate; }
@media (max-width: 639px) {
  [data-motion=on] .ambient { animation: none; }
}

/* -- #6 nav indicator (sb-nav-indicator, MO11) -------------------------------
 * The component declares no transition of its own; it lives here, per mode.
 * Off and pending: no rule, so the indicator jumps. */
[data-motion=on] sb-nav-indicator .nav-indicator {
  transition: transform calc(350ms * var(--motion-scale)) var(--ease-spring), opacity var(--dur-base) var(--ease-out);
}
[data-motion=reduced] sb-nav-indicator .nav-indicator { transition: opacity var(--dur-base) var(--ease-out); }

/* -- Reduced: no transform-based motion (spec §1) --------------------------- */
[data-motion=reduced] .sb-enter,
[data-motion=reduced] .sb-entering,
[data-motion=reduced] .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > *,
[data-motion=reduced] .sb-pop-in,
[data-motion=reduced] .sb-drawer-in,
[data-motion=reduced] .sb-sheet-in {
  animation-name: sb-fade-in;
  animation-duration: var(--dur-base);
}
[data-motion=reduced] .sb-drawer-out { animation-name: sb-fade-out; }
[data-motion=reduced] .sb-draw-in,
[data-motion=reduced] .sb-draw-in-radial { animation: none; }
[data-motion=reduced] sb-async .skeleton-cell { animation: none; }
[data-motion=reduced] sb-connection-status .dot.live::after { animation: none; opacity: 0; }

/* -- Off and pending: no decorative motion ----------------------------------
 * Off's fallbacks for the nine pre-v168 sites (spinners slowed, never
 * stopped) follow below this block (MO6). */
[data-motion=off] .sb-enter,
[data-motion=off] .sb-entering,
[data-motion=off] .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > *,
[data-motion=off] .sb-pop-in,
[data-motion=off] .sb-drawer-in,
[data-motion=off] .sb-sheet-in,
[data-motion=off] .sb-drawer-out,
[data-motion=off] .sb-fade-out,
[data-motion=off] .sb-draw-in,
[data-motion=off] .sb-draw-in-radial,
[data-motion=off] sb-drawer dialog[open]::backdrop,
[data-motion=off] sb-confirm-dialog dialog[open]::backdrop,
[data-motion=pending] .sb-enter,
[data-motion=pending] .sb-entering,
[data-motion=pending] .sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > *,
[data-motion=pending] .sb-pop-in,
[data-motion=pending] .sb-drawer-in,
[data-motion=pending] .sb-sheet-in,
[data-motion=pending] .sb-drawer-out,
[data-motion=pending] .sb-fade-out,
[data-motion=pending] .sb-draw-in,
[data-motion=pending] .sb-draw-in-radial,
[data-motion=pending] sb-drawer dialog[open]::backdrop,
[data-motion=pending] sb-confirm-dialog dialog[open]::backdrop {
  animation: none;
}
[data-motion=off] sb-async .skeleton-cell { animation: none; }
[data-motion=off] sb-connection-status .dot.live::after,
[data-motion=pending] sb-connection-status .dot.live::after { animation: none; opacity: 0; }
```

- [ ] **Step 5: Import it and take the flash out of `styles.css`**

In `frontend/src/styles.css`, directly after the line `@import './styles/tokens.css';` add:

```css
@import './styles/motion.css';
```

Then delete this block (today `:231-237`; find it by text) entirely, comment included (its text now lives in `motion.css`):

```css
/* Cell-level value feedback. Scoped to the cell, never the card -- see
   tokens.css on why a card flash under real-time push is a flicker. */
@keyframes flash-up { from { background: var(--pos-soft); } to { background: transparent; } }
@keyframes flash-down { from { background: var(--neg-soft); } to { background: transparent; } }
.flash-up { animation: flash-up var(--dur-base) var(--ease-out); }
.flash-down { animation: flash-down var(--dur-base) var(--ease-out); }
```

- [ ] **Step 6: Point every component at the moved keyframes and delete its copies**

Each edit keeps the call site's duration, easing and every other byte; only the keyframe name changes, and the local `@keyframes` goes. The `@media (prefers-reduced-motion: reduce)` blocks next to them stay untouched (MO6).

1. `frontend/src/app/shell/connection-status.ts`: in `.dot.live { background: var(--text); animation: pulse 2s ease-out infinite; }` change `pulse` to `sb-pulse-dim`. Delete the line `    @keyframes pulse { 50% { opacity: 0.35; } }`.
2. `frontend/src/app/ui/status-indicator.ts`: in `.open { background: var(--text); animation: pulse 2.2s ease-in-out infinite; }` change `pulse` to `sb-pulse-dim`. Delete the line `    @keyframes pulse { 50% { opacity: 0.35; } }`.
3. `frontend/src/app/ui/status-cell.ts`: change `animation-name: pulse;` to `animation-name: sb-pulse-blink;`. Delete the line `    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }`.
4. `frontend/src/app/ui/async.ts`: in `.skeleton-cell`, change `animation: pulse 1.4s var(--ease-out) infinite;` to `animation: sb-pulse-soft 1.4s var(--ease-out) infinite;`. Delete the line `    @keyframes pulse { 50% { opacity: 0.45; } }`.
5. `frontend/src/app/ui/data-table/data-table.ts`: in `.loading-spinner`, change `animation: spin 700ms linear infinite;` to `animation: sb-spin 700ms linear infinite;`. Delete the three lines `    @keyframes spin {` / `      to { transform: rotate(360deg); }` / `    }`. Further down, delete the four lines `    @keyframes sb-row-blink {` … `    }` (the name is already `sb-row-blink`; `.blink { animation: sb-row-blink 1.6s ease-in-out infinite; }` stays as it is).
6. `frontend/src/app/ui/chart-container.ts`: in `.spinner`, change `animation: spin 700ms linear infinite;` to `animation: sb-spin 700ms linear infinite;`. Delete the five lines `    @keyframes spin {` / `      to {` / `        transform: rotate(360deg);` / `      }` / `    }`.
7. `frontend/src/app/shell/shell.css`: in `.route-loading-mark { … animation: route-spin 700ms linear infinite; }` change `route-spin` to `sb-route-spin`. Delete the line `@keyframes route-spin { to { transform: rotate(360deg); } }`.
8. `frontend/src/app/shell/scan-progress.css`: change `animation: scan-strip-in var(--transition) ease-out;` to `animation: sb-scan-strip-in var(--transition) ease-out;` (byte-identical apart from the name: `var(--transition)` already carries a timing function, which is today's declaration too; fixing it is a visual change and out of scope). Change `animation: scan-sweep 1.4s ease-in-out infinite;` to `animation: sb-scan-sweep 1.4s ease-in-out infinite;`. Delete the two blocks `@keyframes scan-sweep { … }` and `@keyframes scan-strip-in { … }` with the blank line between them.
9. `frontend/src/app/shell/tape/tape.css`: change `animation-name: tape-slide;` to `animation-name: sb-tape-slide;`. Delete the two lines `@keyframes tape-slide { from { transform: translateX(0); }` / `                        to   { transform: translateX(-50%); } }`.

Then confirm nothing was missed:

```bash
git -C $WT grep -n "@keyframes" -- frontend/src ':!*.spec.ts'
git -C $WT grep -nE "animation(-name)?: *(pulse|spin|route-spin|scan-sweep|scan-strip-in|tape-slide|flash-up|flash-down)\b" -- frontend/src
```

Expected: the first lists only `frontend/src/styles/motion.css` lines; the second prints nothing.

- [ ] **Step 7: Run the new specs, the gates and the touched components**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion-home.spec.ts --include src/app/ui/motion-css.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/flash.spec.ts --include src/app/ui/pnl-cell.spec.ts --include src/app/ui/async.spec.ts --include src/app/ui/chart-container.spec.ts --include src/app/ui/status-cell.spec.ts --include src/app/ui/status.spec.ts --include src/app/ui/data-table/data-table.spec.ts --include src/app/shell/connection-status.spec.ts --include src/app/shell/scan-progress.spec.ts --include src/app/shell/tape/tape.spec.ts --include src/app/shell/shell.spec.ts
```

Expected: `Tests  N passed (N)`, 0 failed. If `primitives.spec.ts` G3 fails on `styles.css`, the flash block deletion took a shadow with it by mistake: G3's `styles.css` list must still be `['var(--panel-shadow)', 'var(--shadow-overlay)']`. Quote the verdict line.

- [ ] **Step 8: Check the build accepts the global stylesheet**

```bash
npm --prefix $WT/frontend exec -- ng build --configuration development
```

Expected: build succeeds with no new warning naming `motion.css` or a component style budget. (A CSS syntax error in `motion.css` only surfaces here; the specs read it as text.)

- [ ] **Step 9: Commit**

```bash
git -C $WT add frontend/src/styles/motion.css frontend/src/app/ui/motion-home.spec.ts frontend/src/app/ui/motion-css.spec.ts frontend/src/styles.css frontend/src/app/shell/connection-status.ts frontend/src/app/shell/scan-progress.css frontend/src/app/shell/shell.css frontend/src/app/shell/tape/tape.css frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/chart-container.ts frontend/src/app/ui/status-indicator.ts frontend/src/app/ui/status-cell.ts frontend/src/app/ui/async.ts
git -C $WT commit -m "feat(ui): v168 styles/motion.css -- one keyframe home, the motion class catalogue (MO3)

Every @keyframes moves into styles/motion.css (imported after tokens.css):
pulse x4 merged by shape into sb-pulse-soft/-dim/-blink, spin x2 into
sb-spin, the rest renamed sb-*; call sites keep their durations. The cell
flash moves out of styles.css and is refined to 1.1s with --flash-*-text.
New: the entrance, stagger, lift, drawer/sheet/dialog, draw-in, ambient
and nav-indicator classes, with their reduced/off/pending rules and
[data-motion=off] { --motion-scale: 0; }. Nothing adopts them yet.
Gates: motion-home.spec.ts (no @keyframes outside motion.css, no unknown
animation name), motion-css.spec.ts (the catalogue).

<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task MO4: `MotionService`, `provideMotion`, `MotionStarts`; global `provideMotion('off')` test default

**Model:** sonnet — a signal service over an existing store plus a test-setup hook

**Files:**
- Create: `frontend/src/app/ui/motion/motion.service.ts`
- Create: `frontend/src/app/ui/motion/motion.service.spec.ts`
- Create: `frontend/src/app/ui/motion/motion-starts.ts`
- Create: `frontend/src/app/ui/motion/motion-starts.spec.ts`
- Modify: `frontend/src/test-setup.ts` (one global `beforeEach` appended, two imports)
- Modify: `frontend/angular.json` (`projects.*.architect.test.options.setupFiles`) and `frontend/vitest.config.ts` (its `setupFiles` line and comment): **see Step 5 for why; not in the ledger's file list, no other task touches either file**

**Interfaces:**
- Consumes: MO1's worktree. From `main`: `PreferencesStore` (`frontend/src/app/stores/preferences.store.ts`; `isLoaded(): boolean`, `values(): Preferences`, `update(mutate: (prefs: Preferences) => Preferences): void`; `loaded` also turns true when the GET fails, so `pending` always ends); `installMatchMediaPolyfill()` (`frontend/src/app/testing/match-media-polyfill.ts`).
- Produces (verbatim from the ledger; MO5..MO17 import these from `ui/motion/motion.service` and `ui/motion/motion-starts`):
  - `type MotionMode = 'on' | 'reduced' | 'off'`; `type MotionState = MotionMode | 'pending'`; `MOTION_MODES: readonly MotionMode[] = ['on', 'reduced', 'off']`; `MOTION_PREF_KEY = 'shell.motion'`; `parseMotion(stored: unknown): MotionMode` (`'on'` fallback).
  - `MOTION_FIXED = new InjectionToken<MotionState | null>('MOTION_FIXED', { providedIn: 'root', factory: () => null })`; `provideMotion(mode: MotionState | 'live'): Provider` (`'live'` provides `null`).
  - `@Injectable({ providedIn: 'root' }) class MotionService { readonly mode: Signal<MotionState>; readonly full: Signal<boolean>; readonly active: Signal<boolean>; set(mode: MotionMode): void }`: `full` is `mode() === 'on'`, `active` is `'on'` or `'reduced'`. Fixed mode (any `provideMotion(<state>)`): never injects `PreferencesStore`, so a spec needs no `HttpClient`; `set()` changes only this service. Live mode (`MOTION_FIXED` is `null`): `'pending'` until `isLoaded()`, then `parseMotion(values()['shell.motion'])`; `set()` writes through `PreferencesStore.update`.
  - `type MotionStartKind = 'entrance' | 'count-first' | 'count-change' | 'draw-in' | 'flash'`; `interface MotionStart { kind: MotionStartKind; key: string }`; `@Injectable({ providedIn: 'root' }) class MotionStarts { record(kind: MotionStartKind, key: string): void; entries(): readonly MotionStart[]; count(kind: MotionStartKind): number; clear(): void }` (keeps the latest 200 entries).
  - Every spec runs with `provideMotion('off')` unless it provides its own (`provideMotion('on')`, `'reduced'`, `'pending'` or `'live'`): later providers win.

**Not in this task:** no consumer injects `MotionService` yet (the shell is MO5; directives MO7+). Nothing writes `data-motion`.

- [ ] **Step 1: Write the failing `MotionService` spec**

Create `frontend/src/app/ui/motion/motion.service.spec.ts`:

```ts
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PreferencesStore } from '../../stores/preferences.store';
import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import {
  MOTION_MODES,
  MOTION_PREF_KEY,
  MotionService,
  MotionState,
  parseMotion,
  provideMotion,
} from './motion.service';

type Prefs = Record<string, unknown>;

/** A stand-in for the signal store: the three members MotionService reads. */
function fakePreferences(loaded: boolean, values: Prefs = {}) {
  const isLoaded = signal(loaded);
  const current = signal<Prefs>(values);
  const update = vi.fn((mutate: (prefs: Prefs) => Prefs) => current.update(mutate));
  return { isLoaded, current, update, store: { isLoaded, values: current, update } };
}

function live(fake: ReturnType<typeof fakePreferences>): MotionService {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideMotion('live'),
      { provide: PreferencesStore, useValue: fake.store },
    ],
  });
  return TestBed.inject(MotionService);
}

function fixed(mode: MotionState): MotionService {
  TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion(mode)] });
  return TestBed.inject(MotionService);
}

describe('parseMotion', () => {
  it('accepts the three modes', () => {
    for (const mode of MOTION_MODES) expect(parseMotion(mode)).toBe(mode);
  });

  it('falls back to on for anything else (validated, not trusted)', () => {
    for (const junk of [undefined, null, '', 'pending', 'fast', 'ON', 42, {}]) {
      expect(parseMotion(junk), String(junk)).toBe('on');
    }
  });
});

describe('MotionService, live (spec v168 §1)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('is pending until preferences load, so a cold load plays nothing', () => {
    const fake = fakePreferences(false);
    const motion = live(fake);
    expect(motion.mode()).toBe('pending');
    fake.isLoaded.set(true);
    expect(motion.mode()).toBe('on');
  });

  it('defaults to on when nothing is stored', () => {
    expect(live(fakePreferences(true)).mode()).toBe('on');
  });

  it('restores a persisted value', () => {
    expect(live(fakePreferences(true, { [MOTION_PREF_KEY]: 'reduced' })).mode()).toBe('reduced');
  });

  it('restores off', () => {
    expect(live(fakePreferences(true, { 'shell.motion': 'off' })).mode()).toBe('off');
  });

  it('falls back to on for an unknown stored value', () => {
    expect(live(fakePreferences(true, { 'shell.motion': 'sparkly' })).mode()).toBe('on');
  });

  it('persists a choice through PreferencesStore under shell.motion, keeping other keys', () => {
    const fake = fakePreferences(true, { 'shell.zoom': 110 });
    const motion = live(fake);
    motion.set('off');
    expect(fake.update).toHaveBeenCalledTimes(1);
    expect(fake.current()).toEqual({ 'shell.zoom': 110, 'shell.motion': 'off' });
    expect(motion.mode()).toBe('off');
  });

  it('never consults the OS reduced-motion setting (spec D2)', () => {
    installMatchMediaPolyfill();
    const spy = vi.spyOn(window, 'matchMedia');
    const fake = fakePreferences(false);
    const motion = live(fake);
    motion.mode();
    fake.isLoaded.set(true);
    motion.mode();
    motion.full();
    motion.active();
    motion.set('reduced');
    motion.mode();
    expect(spy).not.toHaveBeenCalled();
  });
});

describe('MotionService, fixed', () => {
  it('derives full and active from the mode', () => {
    const table: [MotionState, boolean, boolean][] = [
      ['on', true, true],
      ['reduced', false, true],
      ['off', false, false],
      ['pending', false, false],
    ];
    for (const [mode, full, active] of table) {
      TestBed.resetTestingModule();
      const motion = fixed(mode);
      expect([motion.mode(), motion.full(), motion.active()], mode).toEqual([mode, full, active]);
    }
  });

  it('needs no PreferencesStore (and so no HttpClient), and set() stays local', () => {
    const motion = fixed('on');
    motion.set('reduced');
    expect(motion.mode()).toBe('reduced');
  });

  it('is off for every spec that does not ask (the global test default)', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    expect(TestBed.inject(MotionService).mode()).toBe('off');
  });
});
```

- [ ] **Step 2: Write the failing `MotionStarts` spec**

Create `frontend/src/app/ui/motion/motion-starts.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { MotionStarts } from './motion-starts';

/**
 * jsdom has no getAnimations() and fires no animationstart, so the no-replay
 * gate (spec v168 §4) observes this log instead: the route host, count-up,
 * draw-in and flash record every animation they START.
 */
describe('MotionStarts', () => {
  let starts: MotionStarts;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    starts = TestBed.inject(MotionStarts);
  });

  it('logs starts in order and counts them by kind', () => {
    starts.record('entrance', 'route');
    starts.record('count-first', 'stat:Win rate');
    starts.record('count-first', 'figure:Expectancy');
    starts.record('flash', 'flash');
    expect(starts.entries()).toEqual([
      { kind: 'entrance', key: 'route' },
      { kind: 'count-first', key: 'stat:Win rate' },
      { kind: 'count-first', key: 'figure:Expectancy' },
      { kind: 'flash', key: 'flash' },
    ]);
    expect(starts.count('count-first')).toBe(2);
    expect(starts.count('draw-in')).toBe(0);
  });

  it('hands out a copy, not its own log', () => {
    starts.record('draw-in', 'donut');
    const seen = starts.entries() as { kind: string; key: string }[];
    seen.length = 0;
    expect(starts.entries()).toHaveLength(1);
  });

  it('clears', () => {
    starts.record('entrance', 'route');
    starts.clear();
    expect(starts.entries()).toEqual([]);
    expect(starts.count('entrance')).toBe(0);
  });

  it('keeps only the latest 200, so a long-lived page cannot grow it', () => {
    for (let i = 0; i < 205; i++) starts.record('flash', `k${i}`);
    expect(starts.entries()).toHaveLength(200);
    expect(starts.entries()[0]).toEqual({ kind: 'flash', key: 'k5' });
  });
});
```

- [ ] **Step 3: Run both and watch them fail**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/motion.service.spec.ts --include src/app/ui/motion/motion-starts.spec.ts
```

Expected: FAIL at build: `Could not resolve "./motion.service"` and `Could not resolve "./motion-starts"`.

- [ ] **Step 4: Write the two services**

Create `frontend/src/app/ui/motion/motion.service.ts`:

```ts
import { Injectable, InjectionToken, Provider, Signal, computed, inject, signal } from '@angular/core';

import { PreferencesStore } from '../../stores/preferences.store';

/** The three choices the Motion control offers (spec v168 §1). */
export type MotionMode = 'on' | 'reduced' | 'off';
/** A mode, or `pending` until preferences have loaded. */
export type MotionState = MotionMode | 'pending';

export const MOTION_MODES: readonly MotionMode[] = ['on', 'reduced', 'off'];
/** Stored only through PreferencesStore, never localStorage (plan v21). */
export const MOTION_PREF_KEY = 'shell.motion';

/** A stored value, validated rather than trusted: anything unknown is On. */
export function parseMotion(stored: unknown): MotionMode {
  return MOTION_MODES.includes(stored as MotionMode) ? (stored as MotionMode) : 'on';
}

/**
 * A fixed mode, for tests. `null` (the root default) means "follow the
 * user's preference". src/test-setup.ts gives every spec `off`.
 */
export const MOTION_FIXED = new InjectionToken<MotionState | null>('MOTION_FIXED', {
  providedIn: 'root',
  factory: () => null,
});

/** Pin the mode (`'on'`, `'reduced'`, `'off'`, `'pending'`) or follow preferences (`'live'`). */
export function provideMotion(mode: MotionState | 'live'): Provider {
  return { provide: MOTION_FIXED, useValue: mode === 'live' ? null : mode };
}

/**
 * The one TS source of the motion mode (spec v168 §1). The shell writes it
 * to <html data-motion>, which is all the CSS reads; TS reads it here, never
 * from the attribute.
 *
 * **The OS reduced-motion setting is ignored by design (spec D2).** Windows
 * reports it whenever "Animation effects" is off, which is common on
 * laptops, and honouring it left the admin with no motion and no way back.
 * The Motion control (default On) is the switch, so this never asks the
 * browser for that media feature.
 *
 * `pending` until PreferencesStore has loaded (it also counts as loaded
 * when the GET fails), so a user who chose Off never sees a cold-load burst.
 */
@Injectable({ providedIn: 'root' })
export class MotionService {
  private readonly fixed = signal(inject(MOTION_FIXED));
  /** Injected only when following preferences: a fixed-mode spec needs no HttpClient. */
  private readonly preferences = this.fixed() === null ? inject(PreferencesStore) : null;

  readonly mode: Signal<MotionState> = computed(() => this.fixed() ?? this.stored());
  /** Everything runs: count-up, draw-in, lift, ping, drift. */
  readonly full: Signal<boolean> = computed(() => this.mode() === 'on');
  /** Entrances and dialog transitions run (as a fade under Reduced). */
  readonly active: Signal<boolean> = computed(() => this.mode() === 'on' || this.mode() === 'reduced');

  set(mode: MotionMode): void {
    if (this.preferences === null) {
      this.fixed.set(mode);
      return;
    }
    this.preferences.update((prefs) => ({ ...prefs, [MOTION_PREF_KEY]: mode }));
  }

  private stored(): MotionState {
    const preferences = this.preferences!;
    if (!preferences.isLoaded()) return 'pending';
    return parseMotion(preferences.values()[MOTION_PREF_KEY]);
  }
}
```

Create `frontend/src/app/ui/motion/motion-starts.ts`:

```ts
import { Injectable } from '@angular/core';

export type MotionStartKind = 'entrance' | 'count-first' | 'count-change' | 'draw-in' | 'flash';

export interface MotionStart {
  kind: MotionStartKind;
  key: string;
}

/** Enough for any gate; small enough that a page left open all day stays flat. */
const CAP = 200;

/**
 * Every animation START, recorded by the route host, count-up, draw-in and
 * flash (spec v168 §4). The no-replay gate reads it, because jsdom has no
 * getAnimations() and never fires animationstart. In the browser it is a
 * small ring of the latest starts and nothing reads it.
 */
@Injectable({ providedIn: 'root' })
export class MotionStarts {
  private readonly log: MotionStart[] = [];

  record(kind: MotionStartKind, key: string): void {
    this.log.push({ kind, key });
    if (this.log.length > CAP) this.log.shift();
  }

  entries(): readonly MotionStart[] {
    return [...this.log];
  }

  count(kind: MotionStartKind): number {
    return this.log.filter((start) => start.kind === kind).length;
  }

  clear(): void {
    this.log.length = 0;
  }
}
```

- [ ] **Step 5: Make `test-setup.ts` part of the test bundle, then add the global default**

**Why the extra two files.** Today `src/test-setup.ts` is registered in `vitest.config.ts` (`setupFiles: ['./src/test-setup.ts']`). The Angular builder merges that into its own list, but it does **not** bundle it: Vite loads it straight from source, and its bare imports resolve to `node_modules`, while every spec runs against the `@angular/core` copy bundled into the build output (`node_modules/@angular/build/src/builders/unit-test/runners/vitest/plugins.js`, `resolveId`, only build artefacts and test entry points are mapped). A `TestBed.configureTestingModule` called from that file would configure a second, never-initialised `TestBed` and silently do nothing. The builder's own `setupFiles` option (`build-options.js:88-97`) bundles a setup file with the specs, so its `TestBed` and `MOTION_FIXED` are the specs' own.

1. In `frontend/angular.json`, in `projects.<the app>.architect.test.options` (today it holds only `"runnerConfig": "vitest.config.ts"`), add:

```json
"setupFiles": ["src/test-setup.ts"]
```

2. In `frontend/vitest.config.ts`, delete the line `    setupFiles: ['./src/test-setup.ts'],` and replace the comment block above it (the one beginning `/* Injects \`src/styles/tokens.css\` into the test document`) with:

```ts
    /* src/test-setup.ts is registered in angular.json (test.options.setupFiles),
     * not here (v168 MO4). The builder bundles a setup file listed there with
     * the specs, after its own polyfills.js / init-testbed.js /
     * vitest-mock-patch.js, so the setup file's TestBed and injection tokens
     * are the very ones the specs use. A file listed HERE is loaded by Vite
     * straight from source, with its own copy of @angular/core: anything it
     * did to TestBed would configure a second, uninitialised one and change
     * nothing. */
```

3. Append to the end of `frontend/src/test-setup.ts`, and add the two imports at the top beside the existing `node:fs` / `node:path` imports (keep whatever v167 AN3 left in the file untouched):

```ts
import { TestBed } from '@angular/core/testing';
import { beforeEach } from 'vitest';

import { provideMotion } from './app/ui/motion/motion.service';
```

```ts
/**
 * Motion is Off in every spec unless the spec asks (spec v168, Testing).
 *
 * Off renders final values at once -- a count-up writes its text
 * synchronously, a draw-in never clips, an entrance never runs -- so a spec
 * that reads `.textContent` right after one detectChanges() keeps passing.
 * A motion spec opts in with provideMotion('on') (or 'reduced' / 'pending'),
 * and one that needs the preference-driven service uses provideMotion('live');
 * a provider the spec adds later wins over this one.
 *
 * configureTestingModule calls merge until the first inject or
 * createComponent, and this hook runs before every spec file's own
 * beforeEach, so it never trips "already instantiated". The builder resets
 * TestBed after each test, so it is re-applied before each one.
 */
beforeEach(() => {
  TestBed.configureTestingModule({ providers: [provideMotion('off')] });
});
```

- [ ] **Step 6: Run the new specs**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/motion/motion.service.spec.ts --include src/app/ui/motion/motion-starts.spec.ts
```

Expected: `Tests  N passed (N)`, 0 failed. **If `is off for every spec that does not ask` fails with `pending`**, the global hook reached a different `TestBed` (the setup file is still loaded from source): check that `vitest.config.ts` no longer lists it and `angular.json` does. If the builder rejects `setupFiles` in `angular.json`, stop and report it rather than moving the hook elsewhere.

- [ ] **Step 7: Prove the bundled setup file still injects the tokens, and that the default breaks nothing**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/chart/chart-theme.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/figure.spec.ts --include src/app/ui/flash.spec.ts --include src/app/ui/pnl-cell.spec.ts --include src/app/ui/controls.spec.ts --include src/app/shell/shell.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts
```

Expected: `Tests  N passed (N)`, 0 failed. `chart-theme.spec.ts` passing proves the token `<style>` still reaches jsdom from the bundled `test-setup.ts` (a missing injection shows as empty colours there first). If a 60 s worker timeout appears, re-run once.

Then the whole frontend once, because the setup file now runs for every spec through a different loader:

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false
```

Expected: `Tests  N passed (N)`, 0 failed, and N equal to the MO1 baseline count plus the new cases from MO2, MO3 and this task. A spec that fails here and passed at MO1 is a setup-loader difference: fix the cause (or stop and report), never weaken the spec.

- [ ] **Step 8: Commit**

```bash
git -C $WT add frontend/src/app/ui/motion/motion.service.ts frontend/src/app/ui/motion/motion.service.spec.ts frontend/src/app/ui/motion/motion-starts.ts frontend/src/app/ui/motion/motion-starts.spec.ts frontend/src/test-setup.ts frontend/angular.json frontend/vitest.config.ts
git -C $WT commit -m "feat(ui): v168 MotionService, provideMotion, MotionStarts; specs default to Off (MO4)

MotionService is the one TS source of the motion mode: a fixed mode for
tests, otherwise pending until PreferencesStore loads, then shell.motion
(validated, On by default). The OS reduced-motion setting is never read
(spec D2). MotionStarts logs every animation start for the no-replay gate.

test-setup.ts gives every spec provideMotion('off') through a global
beforeEach. It moves from vitest.config.ts to angular.json's
test.options.setupFiles so the builder bundles it with the specs: loaded
from source by Vite it had its own @angular/core, and its TestBed was not
the specs' TestBed.

<narrow verdict line>
<full frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
