# v167 Arctic Navy token foundation. Implementation Plan, part 2: palette swap and geometry (AN7..AN10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `grep -n "^### Task AN7:" -A 300 docs/superpowers/plans/2026-10-16-v167-arctic-navy-token-foundation_2-palette-geometry.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md`](../specs/2026-10-16-v167-arctic-navy-token-foundation-design.md) (§2 palette, §3 geometry and elevation, §4 chart lockstep, §6 superseded rules; `## Amendments from the plan brief` overrides)
**Index:** [`2026-10-16-v167-arctic-navy-token-foundation_0-index.md`](2026-10-16-v167-arctic-navy-token-foundation_0-index.md). Its `## Global Constraints`, `## Where to work` (`$WT`, `$R`, `GATES`, the no-`cd` rule), `## Parallelisation` and `## Task ledger` bind every task here.

**Scope of this part:** the Arctic Navy palette lands in one lockstep commit with the chart PNGs (AN7); the tier-3 component tokens follow (AN8); then the two consumers that can run in parallel: the `.sb-panel` two-level elevation with the three panel primitives (AN9) and the gradient primary button (AN10).

**What part 1 hands this part (from the ledger, not from the part 1 file):**
- `scripts/dev/dump_tokens.py` (AN2): no flag writes `tests/charts/resolved_tokens.json`; `--check` exits 1 when the fixture is stale. `parse_root` reads every top-level `:root { }` block, drops `@media`/`@supports`, collapses whitespace.
- `frontend/src/styles/palette.css` (AN2): a header comment and an empty `:root {\n}`, imported by `styles.css` before `tokens.css` and linked by `frontend/chart-harness/index.html`.
- `tests/charts/test_chart_theme.py` (AN2, AN5): `_resolve() -> dict[str, str]` (lower-cased resolved values), `test_resolver_reproduces_the_committed_fixture`, `_theme_digest()`, `STYLE_PINS = (("fb0f840658155cd0", "v80"),)`, `test_style_version_is_pinned_to_the_theme_digest`, `test_style_pins_never_reuse_a_version_or_digest`.
- `swingbot/core/charts/chart_style.py` (AN5): `STYLE_VERSION = "v80"` beside `THEME`.
- `frontend/src/app/ui/testing/resolve-token.ts` (AN3): `resolveToken(name: string): string` (accepts `--x` or `x`, reads `palette.css` + `tokens.css` from disk, follows `var()` to a literal); `test-setup.ts` injects the flattened fixture, so jsdom's `getComputedStyle` sees literals only.
- `frontend/src/app/ui/contrast.spec.ts` (AN4): its `token(name)` helper returns `resolveToken(name)`.

---

# Phase 2: palette swap and geometry

### Task AN7: Arctic Navy palette swap in lockstep with the chart PNGs

**Model:** sonnet — one lockstep colour change across the admin and one core package, values fixed by the spec

**Files:**
- Modify: `frontend/src/styles/palette.css` (whole file; AN2 left it an empty `:root`)
- Modify: `frontend/src/styles/tokens.css:43-53` (the ground block) and `:77-115` (text, valence, accent, soft tints)
- Modify: `frontend/src/app/ui/tokens.spec.ts:1-3` (imports) and `:240-275` (the `v80 D1` block)
- Modify: `frontend/src/app/ui/contrast.spec.ts` (one new case at the end of `accent legibility`)
- Modify: `frontend/src/app/ui/confidence-cell.spec.ts:83-86` (pins `--info` at the old lavender; not in the ledger row, see the note below)
- Modify: `swingbot/core/charts/chart_style.py:1-9` (docstring), `:25-55` (banner + `THEME`), `:61` (`MUTED_TEXT_COLOR` comment), the `STYLE_VERSION` line AN5 added
- Modify: `tests/charts/test_chart_theme.py` (`STYLE_PINS`, added by AN5)
- Modify: `tests/charts/resolved_tokens.json` (regenerated, never hand-edited)

**Interfaces:**
- Consumes: `dump_tokens.py` and its `--check` (AN2); `_resolve()`, `_theme_digest()`, `STYLE_PINS` and the two pin tests in `test_chart_theme.py` (AN2, AN5); `chart_style.STYLE_VERSION = "v80"` (AN5); `resolveToken(name: string): string` from `frontend/src/app/ui/testing/resolve-token.ts` (AN3); `contrast.spec.ts`'s `token()` already delegating to `resolveToken` (AN4); the flattened-fixture `:root` that `test-setup.ts` injects (AN3).
- Produces: the 24 tier-1 names (18 colours + 6 alpha entries) in `palette.css`, exactly as `## Global Constraints`; tier 2 as `var(--<palette-name>)`; the new tier-2 token `--accent-fill-hi: var(--sky-550)` (consumed by AN8's `--btn-fill`); `chart_style.STYLE_VERSION = "v167"`; `STYLE_PINS[-1] == ("96d64692ba7c2abf", "v167")`; the regenerated fixture.

**Why one commit.** Review focus 2: `palette.css`, `tokens.css`, `THEME`, `STYLE_VERSION`, `STYLE_PINS` and the fixture change together. Any subset fails `test_theme_matches_the_admin_tokens_byte_for_byte`, `test_resolver_reproduces_the_committed_fixture`, the style-pin test or `resolve-token.spec.ts`. Do not commit between steps.

**Pre-verified numbers** (the plan writer ran them against today's `test_chart_theme.py` helpers): the new `THEME` digest is `96d64692ba7c2abf`; every `COLOUR_CONSTANTS` role stays >= dE 10 from gain and loss and inside every `CO_OCCURRING` group (closest pair 10.10); `MUTED_TEXT_COLOR` `#8f9db5` on `CHART_BG` `#0c1320` is 6.78:1; white is 5.06:1 on `#1c6dd0` and 4.66:1 on `#2474d2`. If a run disagrees, stop and report: the spec's table reopens, no threshold moves.

**Note on `confidence-cell.spec.ts`.** Its case `keeps info off the quality ramp (v80 D1: lavender, not blue)` reads `--info` through `getComputedStyle` and pins `#b39ddb`. Under the flattened jsdom `:root` (AN3) it now sees the new violet `#c3a6ff`. No other task touches the file, so editing it here creates no contract conflict; name it in the commit body.

- [ ] **Step 1: Write the failing frontend tests**

In `frontend/src/app/ui/tokens.spec.ts`, add the resolver import below the existing three imports (line 3):

```ts
import { resolveToken } from './testing/resolve-token';
```

Replace the whole `describe('v80 D1: the TradingView Blue palette', ...)` block (`:240-275`) with:

```ts
/**
 * v167 §2: the Arctic Navy palette. Supersedes the v80 D1 block that pinned
 * literal hexes here: tier 2 no longer holds a colour, it references a
 * tier-1 palette entry in styles/palette.css. Two assertions per token --
 * the reference as written (the tier contract) and the value it resolves to
 * (the spec's table) -- so a palette edit that keeps the names but drifts a
 * value fails here as well as in contrast.spec.ts.
 */
describe('v167 §2: the Arctic Navy palette', () => {
  const EXPECTED: [token: string, palette: string, value: string][] = [
    ['--bg', '--navy-950', '#070b14'],
    ['--surface', '--navy-900', '#0c1320'],
    ['--surface-raised', '--navy-850', '#121b2d'],
    ['--surface-overlay', '--navy-800', '#1a2540'],
    ['--overlay-dim', '--navy-950-a72', 'rgba(7, 11, 20, 0.72)'],
    ['--border', '--navy-750', '#1d2940'],
    ['--border-strong', '--navy-700', '#2a3a58'],
    ['--text', '--slate-100', '#e8eef8'],
    ['--text-secondary', '--slate-300', '#b3bfd3'],
    ['--text-muted', '--slate-400', '#8f9db5'],
    ['--text-faint', '--navy-600', '#3a4a66'],
    ['--accent', '--sky-300', '#7cc4ff'],
    ['--accent-fill', '--sky-600', '#1c6dd0'],
    ['--accent-fill-hi', '--sky-550', '#2474d2'],
    ['--on-accent', '--white', '#ffffff'],
    ['--pos', '--mint-400', '#3ddc97'],
    ['--neg', '--coral-400', '#ff6f7d'],
    ['--warn', '--amber-300', '#ffc266'],
    ['--info', '--violet-300', '#c3a6ff'],
    ['--pos-soft', '--mint-400-a12', 'rgba(61, 220, 151, 0.12)'],
    ['--neg-soft', '--coral-400-a12', 'rgba(255, 111, 125, 0.12)'],
    ['--warn-soft', '--amber-300-a12', 'rgba(255, 194, 102, 0.12)'],
    ['--accent-soft', '--sky-600-a18', 'rgba(28, 109, 208, 0.18)'],
    ['--info-soft', '--violet-300-a14', 'rgba(195, 166, 255, 0.14)'],
  ];

  for (const [name, palette, value] of EXPECTED) {
    it(`${name} references ${palette}`, () => {
      expect(CSS).toMatch(new RegExp(`^\\s*${name}:\\s*var\\(${palette}\\);`, 'm'));
    });

    it(`${name} resolves to ${value}`, () => {
      expect(resolveToken(name)).toBe(value);
    });
  }

  it('leaves --quality-4 and the six chart series literal (spec §1 exception)', () => {
    expect(CSS).toMatch(/^\s*--quality-4:\s*#9acd32;/m);
    for (let i = 1; i <= 6; i++) {
      expect(CSS).toMatch(new RegExp(`^\\s*--chart-${i}:\\s*#[0-9a-f]{6};`, 'mi'));
    }
  });
});
```

In `frontend/src/app/ui/contrast.spec.ts`, add a case inside `describe('accent legibility (v80 D1)', ...)`, right after `--on-accent on --accent-fill clears 4.5:1`:

```ts
  /* v167 §2: --accent-fill-hi is the TOP stop of the primary button's
   * gradient (tier 3 --btn-fill), so white ink sits on it too. It clears
   * with the thinnest margin in the palette (4.66:1), which is why it is
   * checked by name rather than assumed from --accent-fill. */
  it('--on-accent on --accent-fill-hi clears 4.5:1', () => {
    expect(ratio(token('--on-accent'), token('--accent-fill-hi'))).toBeGreaterThanOrEqual(4.5);
  });
```

In `frontend/src/app/ui/confidence-cell.spec.ts`, replace the case at `:83-86` with:

```ts
  it('keeps info off the quality ramp (v167 §2: violet, not blue)', () => {
    const root = getComputedStyle(document.documentElement);
    expect(root.getPropertyValue('--info').trim().toLowerCase()).toBe('#c3a6ff');
  });
```

- [ ] **Step 2: Write the failing Python pin**

In `tests/charts/test_chart_theme.py`, extend the `STYLE_PINS` tuple AN5 added to:

```python
STYLE_PINS: tuple[tuple[str, str], ...] = (
    ("fb0f840658155cd0", "v80"),
    ("96d64692ba7c2abf", "v167"),  # v167 §4: Arctic Navy
)
```

- [ ] **Step 3: Run both sides and watch them fail**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/confidence-cell.spec.ts
python $WT/scripts/dev/testrun.py file tests/charts/test_chart_theme.py
```
Expected: `tokens.spec.ts` fails every `references` case (tier 2 is still hex) and every `resolves to` case; `contrast.spec.ts` fails `--on-accent on --accent-fill-hi` with `--accent-fill-hi is not a token` (or `is not defined`); `confidence-cell.spec.ts` fails on `#b39ddb`; `test_style_version_is_pinned_to_the_theme_digest` fails (`('fb0f840658155cd0', 'v80') != ('96d64692ba7c2abf', 'v167')`).

- [ ] **Step 4: Fill `palette.css` (tier 1)**

Replace the whole of `frontend/src/styles/palette.css` with:

```css
/* Tier 1: the Arctic Navy palette -- spec v167 §1-§2
 * (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md).
 *
 * THE ONLY FILE under frontend/src that holds hued colour literals (the
 * exceptions are named in the spec: --chart-1..6 and --quality-4 stay
 * literal in tokens.css, and index.html / manifest.webmanifest carry copies
 * of --bg for the cold load).
 *
 * A palette name says what a colour IS (hue and step), never what it is
 * FOR. Meaning lives in tokens.css tier 2 (--bg, --accent, --pos ...), which
 * references these with var(). A component never reads a palette name.
 *
 * The -aNN entries are the soft tints and the overlay dim: literal rgba of a
 * palette hue at NN% alpha. They live here, not as color-mix() in
 * tokens.css, so jsdom and lightweight-charts receive a plain colour string
 * (spec v167, amendment 2).
 *
 * Change a value here, then run `python scripts/dev/dump_tokens.py` and
 * commit tests/charts/resolved_tokens.json with it. If the token is one
 * chart_style.THEME names, THEME and STYLE_VERSION change in the same
 * commit (tests/charts/test_chart_theme.py pins the pair).
 */
:root {
  /* ground and structure, darkest first */
  --navy-950: #070b14;
  --navy-900: #0c1320;
  --navy-850: #121b2d;
  --navy-800: #1a2540;
  --navy-750: #1d2940;
  --navy-700: #2a3a58;
  --navy-600: #3a4a66;

  /* ink */
  --slate-400: #8f9db5;
  --slate-300: #b3bfd3;
  --slate-100: #e8eef8;
  --white: #ffffff;

  /* the blue: interactive only */
  --sky-300: #7cc4ff;
  --sky-550: #2474d2;
  --sky-600: #1c6dd0;

  /* valence hues */
  --mint-400: #3ddc97;
  --coral-400: #ff6f7d;
  --amber-300: #ffc266;
  --violet-300: #c3a6ff;

  /* alpha entries: tints and the overlay dim */
  --navy-950-a72: rgba(7, 11, 20, 0.72);
  --mint-400-a12: rgba(61, 220, 151, 0.12);
  --coral-400-a12: rgba(255, 111, 125, 0.12);
  --amber-300-a12: rgba(255, 194, 102, 0.12);
  --sky-600-a18: rgba(28, 109, 208, 0.18);
  --violet-300-a14: rgba(195, 166, 255, 0.14);
}
```

- [ ] **Step 5: Point tier 2 at the palette (`tokens.css`)**

Re-read `tokens.css:40-116` first; the lines below are from the brief. Replace `:43-53` (from `/* v80 D1: direction C, "TradingView Blue".` through `--border-strong: #363a45;`) with:

```css
  /* Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §2):
   * v80 D1: direction C, "TradingView Blue". The surface ladder steps far
   * enough apart (0c0f16 -> 131722 -> 1c212d -> 242936) that panels read as
   * separate objects without a shadow; --surface is TradingView's own chart
   * pane, so the admin and the Discord charts sit on one ground. */
  /* v167 §2, Arctic Navy. The ground steps 070b14 -> 0c1320 -> 121b2d ->
   * 1a2540. Every colour in this tier is a var() into styles/palette.css
   * (tier 1): a tier-2 token names a MEANING and never holds a hue.
   * --surface is still the Discord chart ground (chart_style.CHART_BG). */
  --bg: var(--navy-950);
  --surface: var(--navy-900);
  --surface-raised: var(--navy-850);
  --surface-overlay: var(--navy-800);
  --overlay-dim: var(--navy-950-a72);
  --border: var(--navy-750);
  --border-strong: var(--navy-700);
```

Leave `:55-75` (the elevation comment, `--shadow-overlay`, `--scrim`) exactly as it is; AN8 owns them.

Replace `:77-115` (from `--text: #d9dce4;` through `--info-soft: rgba(179, 157, 219, 0.14);`) with:

```css
  --text: var(--slate-100);
  --text-secondary: var(--slate-300);
  /* v80 D1: direction C's first muted grey (#888c97) measured 4.32:1 on
   * --surface-overlay -- under the 4.5:1 gate contrast.spec.ts enforces on
   * all four surfaces, for real readable labels at --text-micro (nav group
   * headers, chip captions, .sb-label). #9195a0 is the smallest lift that
   * clears it with v54's safety margin: worst case 4.85:1 on
   * --surface-overlay. v54 Task 42 made the same kind of measured,
   * single-token change for the previous palette.
   * v167 §2: now --slate-400, worst case 5.54:1 (on --surface-overlay). */
  --text-muted: var(--slate-400);
  /* --text-faint is a RULE AND DIVIDER colour (~2:1 on --surface) -- never
   * text that must be read. contrast.spec.ts's `no-text-uses-text-faint`
   * assumes this and this comment is what it checks for. */
  --text-faint: var(--navy-600);

  --pos: var(--mint-400);
  --neg: var(--coral-400);
  --warn: var(--amber-300);
  /* v80 D1: the accent is two tokens. --accent is the colour of interactive
   * TEXT and state -- links, the active tab, the sort arrow, focus -- and
   * #5593ff clears 4.85:1 on every surface. --accent-fill is the deeper
   * TradingView blue a filled button paints, with --on-accent on top at
   * 4.90:1; the text-safe blue is too light to carry white ink.
   * v167 §2: --accent is --sky-300 (8.10:1 worst case); --accent-fill is
   * --sky-600 (white 5.06:1); --accent-fill-hi (new) is --sky-550, the top
   * stop of the primary button's gradient (tier 3 --btn-fill), white 4.66:1.
   * That margin is thin, so contrast.spec.ts checks it by name. */
  --accent: var(--sky-300);
  --accent-fill: var(--sky-600);
  --accent-fill-hi: var(--sky-550);
  --on-accent: var(--white);
  /* v80 D1: info moved off sky blue. Under direction C the accent took the
   * blue, and two blues would make "neutral" read as "interactive".
   * v167 §2: still violet (--violet-300), 7.39:1 worst case. */
  --info: var(--violet-300);

  /* 12% tints, for cell and chip backgrounds, hover states and the chart's
   * risk/reward bands; --info-soft is 14%. --accent-soft is 18% of the FILL
   * blue: the selected-segment ground needs to separate from
   * --surface-raised. v167 amendment 2: each is a tier-1 alpha entry in
   * palette.css (literal rgba of the hue), so jsdom and lightweight-charts
   * still receive a plain colour string and this file holds no hued rgba. */
  --pos-soft: var(--mint-400-a12);
  --neg-soft: var(--coral-400-a12);
  --warn-soft: var(--amber-300-a12);
  --accent-soft: var(--sky-600-a18);
  --info-soft: var(--violet-300-a14);
```

The old comments that quote former hexes (`#888c97`, `#9195a0`, `#5593ff`) sit inside `/* */` and are kept as history; AN11's gate strips comments before matching. Check that the `rule and divider` phrase still sits within 400 characters after the first `--text-faint` in the file (it is in the comment directly above the declaration): `contrast.spec.ts`'s `--text-faint is documented as non-text` case reads it.

- [ ] **Step 6: Move `chart_style.THEME` in the same change**

In `swingbot/core/charts/chart_style.py`, replace the module docstring (`:1-9`) with:

```python
"""
Shared visual constants for every trade-chart module (trade_chart.py and
its sibling chart_*.py drawing helpers) -- the dark "TradingView/Bloomberg
terminal" theme (colors, mplfinance style object) plus a handful of sizing/
layout constants that more than one of those modules needs. Split out of
trade_chart.py so the theme/config lives in exactly one place regardless of
which drawing module needs it, instead of being duplicated or imported
awkwardly between sibling modules.

Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §4):
the theme is now the admin's Arctic Navy palette, a refined terminal rather
than the TradingView one; the layout constants are unchanged.
"""
```

Replace the banner and `THEME` (`:25-55`, from the first `# ----` rule through the closing `}` of `THEME`) with the block below. Keep the `STYLE_VERSION` line AN5 placed beside `THEME` where it is, and set its value to `"v167"`:

```python
# ---------------------------------------------------------------------------
# Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §4):
# the palette is no longer v80 D5's direction C, and the token source is no
# longer one file. Original text, kept:
#
# The admin palette, on every Discord chart -- spec v80 D5, direction C
# ("TradingView Blue").
#
# THEME copies, byte for byte, the tokens it names from
# frontend/src/styles/tokens.css: D1's colours and D2's chart series. Every
# colour constant below is one of them. tests/charts/test_chart_theme.py reads
# that file, maps each constant to its token, and holds three rules:
#   1. roles drawn together are distinct (OKLab dE >= 10);
#   2. indicator panes may reuse a series;
#   3. nothing but the gain/loss constants sits within dE 10 of gain or loss.
# Change a colour in tokens.css and that test names the constant to follow.
#
# v167 §4: THEME copies, byte for byte, the RESOLVED value of each token it
# names. Tier 2 in tokens.css is var(--<palette-name>) into palette.css, so
# the test resolves both files through scripts/dev/dump_tokens.py, which
# also writes the committed fixture tests/charts/resolved_tokens.json. The
# three rules above still hold. A THEME change bumps STYLE_VERSION in the
# same commit: cache.py folds it into every chart-cache key, and
# test_chart_theme.py pins the (THEME digest, STYLE_VERSION) pair.
# ---------------------------------------------------------------------------
THEME = {
    "bg": "#070b14",
    "surface": "#0c1320",
    "surface-raised": "#121b2d",
    "border": "#1d2940",
    "border-strong": "#2a3a58",
    "text": "#e8eef8",
    "text-muted": "#8f9db5",
    "text-faint": "#3a4a66",
    "pos": "#3ddc97",
    "neg": "#ff6f7d",
    "warn": "#ffc266",
    "info": "#c3a6ff",
    "chart-1": "#4c8dff",
    "chart-2": "#c97a22",
    "chart-3": "#a868e0",
    "chart-5": "#1a9db3",
}
```

The `STYLE_VERSION` line reads, after this step:

```python
STYLE_VERSION = "v167"
```

Replace the `MUTED_TEXT_COLOR` line (it was `:61`; the longer banner moves it down, so find it with `grep -n "MUTED_TEXT_COLOR =" $WT/swingbot/core/charts/chart_style.py`) with:

```python
MUTED_TEXT_COLOR = THEME["text-muted"]  # tick labels, fine print: 6.78:1 on CHART_BG (#666666 was 3.6:1)
```

`THEME` keeps exactly its 16 keys; `D1_TOKENS` in `test_chart_theme.py` is not touched. No function changes, so there is nothing for radon here.

- [ ] **Step 7: Regenerate the fixture and check it**

Run:
```bash
python $WT/scripts/dev/dump_tokens.py
python $WT/scripts/dev/dump_tokens.py --check
git -C $WT diff --stat -- tests/charts/resolved_tokens.json
```
Expected: `--check` exits 0. The fixture diff changes the tier-2 colour values and adds the 24 palette names and `accent-fill-hi`. It changes no `radius`, `dur-*`, `font-*` or `space-*` line.

- [ ] **Step 8: Run the narrow runs**

Run:
```bash
python $WT/scripts/dev/testrun.py file tests/charts/test_chart_theme.py
python $WT/scripts/dev/testrun.py file tests/dev/test_dump_tokens.py
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/confidence-cell.spec.ts --include src/app/ui/chart/chart-theme.spec.ts
```
Expected: both Python runs `N passed`, 0 failed; the frontend run `Tests  N passed`, 0 failed. `chart-palette.spec.ts`'s G9 cases (each series dE > 10 from the new `--pos`/`--neg`) and AN4's `>= 3:1 on --surface` cases must pass on the new values. A failure there reopens the spec's §2 table: stop and report, never loosen a threshold. Quote both verdict lines.

- [ ] **Step 9: Commit (one commit, every file above)**

```bash
git -C $WT add frontend/src/styles/palette.css frontend/src/styles/tokens.css frontend/src/app/ui/tokens.spec.ts frontend/src/app/ui/contrast.spec.ts frontend/src/app/ui/confidence-cell.spec.ts swingbot/core/charts/chart_style.py tests/charts/test_chart_theme.py tests/charts/resolved_tokens.json
git -C $WT commit -m "feat(ui,charts): v167 AN7 -- Arctic Navy palette in lockstep with the chart PNGs

palette.css holds the 24 tier-1 entries; tier 2 in tokens.css references
them by var() and gains --accent-fill-hi. chart_style.THEME moves to the
resolved values with STYLE_VERSION v167 and a new STYLE_PINS row; the
fixture is regenerated. confidence-cell.spec.ts pinned the old --info
lavender and moves with the palette.

<test_chart_theme.py verdict line>
<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task AN8: Tier-3 component tokens; `--shadow-overlay` takes the new geometry

**Model:** sonnet — a token block plus its spec, values verbatim from the spec

**Files:**
- Modify: `frontend/src/styles/tokens.css:55-70` (elevation comment superseded; `--shadow-overlay` and its geometry comment leave tier 2) and the end of the file (new tier-3 block after the `prefers-reduced-motion` block)
- Modify: `frontend/src/app/ui/tokens.spec.ts:26-78` (`TIER3` helper, `REQUIRED`), `:120-122` (the one-shadow case), end of file (new describe)
- Modify: `tests/charts/resolved_tokens.json` (regenerated)

**Interfaces:**
- Consumes: AN7's `--accent-fill-hi` and the tier-2 names; `resolveToken` (AN3, already imported into `tokens.spec.ts` by AN7); `dump_tokens.py` / `--check` (AN2), whose `parse_root` reads every top-level `:root` block and drops `@media` blocks, so a second `:root` at the end of the file is picked up.
- Produces (tier 3, consumed later): `--panel-radius`, `--control-radius`, `--chip-radius`, `--radius-sm` (AN9, AN12, AN13); `--panel-bg`, `--panel-border`, `--panel-shadow` (AN9); `--panel-inner-bg`, `--panel-inner-radius` (v169); `--shadow-overlay` with the new geometry (AN9's `.elev-overlay`); `--btn-fill`, `--btn-fill-hover` (AN10); `--glow-accent` (v168); `--glow-ambient` (AN9's body rule); `--scrim-soft` (AN11). In `tokens.spec.ts`: `TIER3_BANNER` and `TIER3` constants (file-local).

`--radius` and `--radius-chip` are NOT touched here; AN13 deletes them after the last call site moves.

- [ ] **Step 1: Write the failing tests in `tokens.spec.ts`**

Directly below `const CSS = readFileSync(...)` (`:26`) add:

```ts
/** Tier 3 is the LAST top-level block of tokens.css, under this banner (spec v167 §3). */
const TIER3_BANNER = '/* ===== Tier 3: component tokens (spec v167 §3) ===== */';
/** Everything from the tier-3 banner to the end of the file; '' while the banner is missing. */
const TIER3 = CSS.includes(TIER3_BANNER) ? CSS.slice(CSS.indexOf(TIER3_BANNER)) : '';
```

In `REQUIRED`, add `'--accent-fill-hi',` on the line after `'--accent-fill',`, delete the `'--shadow-overlay',` line from the first group, and add this group just before the closing `];`:

```ts

  // v167 §3, tier 3
  '--panel-radius',
  '--control-radius',
  '--chip-radius',
  '--radius-sm',
  '--panel-bg',
  '--panel-border',
  '--panel-shadow',
  '--panel-inner-bg',
  '--panel-inner-radius',
  '--shadow-overlay',
  '--btn-fill',
  '--btn-fill-hover',
  '--glow-accent',
  '--glow-ambient',
  '--scrim-soft',
```

Replace the case `defines exactly one elevation shadow, for L3` (`:120-122`) with:

```ts
  /* v167 §3 supersedes v54 D2's one-shadow law: two levels, both in tier 3. */
  it('defines the two elevation shadows', () => {
    expect(TIER3).toMatch(/^\s*--panel-shadow:\s*inset 0 1px 0 rgba\(255, 255, 255, \.03\), 0 6px 18px rgba\(0, 0, 0, \.25\);/m);
    expect(TIER3).toMatch(/^\s*--shadow-overlay:\s*0 16px 40px rgba\(0, 0, 0, \.55\), 0 2px 8px rgba\(0, 0, 0, \.4\);/m);
    // declared once, in tier 3 -- not left behind in tier 2 as well
    expect([...CSS.matchAll(/^\s*--shadow-overlay:/gm)]).toHaveLength(1);
  });
```

Append at the very end of the file:

```ts
/**
 * v167 §3: the component tokens. Values are asserted as DECLARED (whitespace
 * collapsed), because tier 3 is the contract components read; one resolved
 * case proves the gradient reaches the Arctic Navy fill blues through tier 2.
 */
describe('v167 §3: the tier-3 component tokens', () => {
  const declared = (name: string) =>
    TIER3.match(new RegExp(`^\\s*${name}:\\s*([^;]+);`, 'm'))?.[1].replace(/\s+/g, ' ').trim();

  const VALUES: Record<string, string> = {
    '--panel-radius': '8px',
    '--control-radius': '6px',
    '--chip-radius': '999px',
    '--radius-sm': '2px',
    '--panel-bg': 'linear-gradient(180deg, var(--surface-raised), var(--surface))',
    '--panel-border': '1px solid var(--border)',
    '--panel-shadow': 'inset 0 1px 0 rgba(255, 255, 255, .03), 0 6px 18px rgba(0, 0, 0, .25)',
    '--panel-inner-bg': 'var(--surface-raised)',
    '--panel-inner-radius': 'var(--control-radius)',
    '--shadow-overlay': '0 16px 40px rgba(0, 0, 0, .55), 0 2px 8px rgba(0, 0, 0, .4)',
    '--btn-fill': 'linear-gradient(180deg, var(--accent-fill-hi), var(--accent-fill))',
    '--btn-fill-hover':
      'linear-gradient(180deg, color-mix(in srgb, var(--accent-fill-hi) 88%, white), color-mix(in srgb, var(--accent-fill) 88%, white))',
    '--glow-accent': '0 4px 14px color-mix(in srgb, var(--accent-fill) 35%, transparent)',
    '--glow-ambient':
      'radial-gradient(120% 60% at 0% 0%, color-mix(in srgb, var(--accent-fill) 12%, transparent), transparent 60%)',
    '--scrim-soft': 'rgb(0 0 0 / 0.5)',
  };

  it('sits in one :root block after every other block, under its banner', () => {
    expect(TIER3).not.toBe('');
    expect(TIER3.match(/:root\s*\{/g)).toHaveLength(1);
    expect(TIER3).not.toContain('@media');
  });

  for (const [name, value] of Object.entries(VALUES)) {
    it(`${name} is ${value}`, () => {
      expect(declared(name)).toBe(value);
    });
  }

  it('resolves the button gradient to the two Arctic Navy fill blues', () => {
    expect(resolveToken('--btn-fill')).toBe('linear-gradient(180deg, #2474d2, #1c6dd0)');
  });

  /* A gradient is an image: as background-color it is invalid and the
   * declaration is dropped silently, leaving the element transparent. */
  it('never paints a gradient token as background-color (styles.css and ui/)', () => {
    const GRADIENT_AS_COLOUR = /background-color:\s*var\(--(?:panel-bg|btn-fill|btn-fill-hover|glow-ambient)\)/;
    const files = [
      join(process.cwd(), 'src/styles.css'),
      ...readdirSync(UI)
        .filter((file) => file.endsWith('.ts') && !file.endsWith('.spec.ts'))
        .map((file) => join(UI, file)),
    ];
    const offenders = files.filter((file) => GRADIENT_AS_COLOUR.test(readFileSync(file, 'utf8')));
    expect(offenders).toEqual([]);
  });
});
```

(`UI` is the `join(process.cwd(), 'src/app/ui')` constant already declared at `:125`; `readdirSync` is already imported.)

- [ ] **Step 2: Run it and watch it fail**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/tokens.spec.ts
```
Expected: FAIL. `defines --panel-radius` (and the other 13 new tier-3 names) fail, `defines the two elevation shadows` fails, every `v167 §3` value case fails (`declared` is `undefined`), `sits in one :root block` fails (`TIER3` is `''`), `resolves the button gradient` throws `--btn-fill is not a token`. The `background-color` case passes already (it is a guard).

- [ ] **Step 3: Supersede the elevation comment and take `--shadow-overlay` out of tier 2**

Re-read `tokens.css:55-71`. Replace `:55-70` (from `/* -- elevation ----` through `--shadow-overlay: 0 8px 24px rgba(0, 0, 0, .55), 0 2px 6px rgba(0, 0, 0, .4);`) with:

```css
  /* -- elevation --------------------------------------------------------
   * Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §3):
   * the one-shadow law below (spec v54 D2) is now two levels. In-flow
   * panels (L1/L2) cast --panel-shadow through the global .sb-panel class;
   * out-of-flow elements (L3) cast --shadow-overlay through .elev-overlay.
   * Both tokens live in tier 3 at the end of this file, and
   * primitives.spec.ts G3 holds styles.css to exactly those two. An inset
   * box-shadow is still a border, not elevation. Original text, kept:
   *
   * ONE shadow, and it means one thing: this element is not part of the
   * page flow.
   *
   * Depth in a dark UI is carried by surface LIGHTNESS, not by shadow --
   * the four surface tokens above step 0c0f16 -> 131722 -> 1c212d -> 242936,
   * which is the ladder. A shadow under a panel on near-black reads as
   * smudge rather than depth, so L1 and L2 have none and only L3
   * (dropdown, popover, tooltip, toast, drawer, dialog) takes this.
   *
   * An `inset` box-shadow is NOT this: it is a border drawn inside the box
   * (the active-nav indicator, a focus ring, the today marker) and stays
   * allowed. The gate in primitives.spec.ts checks non-inset shadows only.
   */
```

The `--scrim: var(--overlay-dim);` alias and its comment (`:72-75`) stay where they are.

- [ ] **Step 4: Append the tier-3 block**

Append to the very end of `frontend/src/styles/tokens.css`, after the closing `}` of the `@media (prefers-reduced-motion: reduce)` block, with one blank line before it:

```css

/* ===== Tier 3: component tokens (spec v167 §3) ===== */
/* What a panel, a control, a chip and a button LOOK like, named once, so a
 * component reads these instead of re-spelling background + border +
 * radius + shadow. Every colour here derives from tier 2 by var() or
 * color-mix(): a palette change reaches it. The only rgb()/rgba() literals
 * are black or white at an alpha, inside --panel-shadow, --shadow-overlay
 * and --scrim-soft (the colour gate, primitives.spec.ts).
 *
 * --panel-bg, --btn-fill, --btn-fill-hover and --glow-ambient are
 * GRADIENTS, i.e. images: `background` / `background-image` only, never
 * `background-color` (tokens.spec.ts checks styles.css and ui/). A
 * background between two gradients does not transition; v168 animates
 * button hover with filter and glow instead.
 *
 * Last block in the file on purpose: scripts/dev/dump_tokens.py and
 * resolve-token.ts read every top-level :root, and tokens.spec.ts slices
 * tier 3 from this banner to the end. */
:root {
  /* The four radius targets. Every border-radius in the app is one of
   * these, or 50% (dots), 0 (flush edges) or inherit. */
  --panel-radius: 8px;     /* panels, cards, drawers' inner sections, dialogs */
  --control-radius: 6px;   /* buttons, inputs, selects, segmented controls */
  --chip-radius: 999px;    /* pills */
  --radius-sm: 2px;        /* thin bars, cells, swatches, tracks: under ~12px tall */

  /* The panel (L1/L2), painted by sb-panel, sb-figure-strip and
   * sb-chart-container; the shadow comes from the global .sb-panel class. */
  --panel-bg: linear-gradient(180deg, var(--surface-raised), var(--surface));
  --panel-border: 1px solid var(--border);
  /* Box-shadow geometry (blur/offset) is intentionally exempt from the "px only for 1px/2px borders" rule per design spec D2 -- shadow values have no natural expression via the closed --space-* scale. */
  --panel-shadow: inset 0 1px 0 rgba(255, 255, 255, .03), 0 6px 18px rgba(0, 0, 0, .25);
  /* A panel nested in a panel: flat, no gradient, and no shadow -- one
   * level of elevation per stack. */
  --panel-inner-bg: var(--surface-raised);
  --panel-inner-radius: var(--control-radius);

  /* Out of flow (L3): dropdown, popover, tooltip, toast, drawer, dialog,
   * through the global .elev-overlay class. */
  --shadow-overlay: 0 16px 40px rgba(0, 0, 0, .55), 0 2px 8px rgba(0, 0, 0, .4);

  /* The primary button. Top stop --accent-fill-hi (white 4.66:1), bottom
   * --accent-fill (white 5.06:1); contrast.spec.ts checks both. */
  --btn-fill: linear-gradient(180deg, var(--accent-fill-hi), var(--accent-fill));
  --btn-fill-hover: linear-gradient(180deg, color-mix(in srgb, var(--accent-fill-hi) 88%, white), color-mix(in srgb, var(--accent-fill) 88%, white));

  /* Glows are hued, so they derive from the fill blue, never an rgba. */
  --glow-accent: 0 4px 14px color-mix(in srgb, var(--accent-fill) 35%, transparent);
  --glow-ambient: radial-gradient(120% 60% at 0% 0%, color-mix(in srgb, var(--accent-fill) 12%, transparent), transparent 60%);

  /* The mobile-nav scrim (shell.css), given a name. Softer than --scrim,
   * which dims behind a modal. */
  --scrim-soft: rgb(0 0 0 / 0.5);
}
```

Keep each declaration on one line: `tokens.spec.ts`'s `declared()` reads up to the first `;` and collapses whitespace, so a wrapped value would still pass, but one line keeps the fixture diff readable.

- [ ] **Step 5: Regenerate the fixture and check it**

Run:
```bash
python $WT/scripts/dev/dump_tokens.py
python $WT/scripts/dev/dump_tokens.py --check
git -C $WT diff -- tests/charts/resolved_tokens.json
```
Expected: `--check` exits 0. The diff adds the 14 new tier-3 names with every `var()` resolved (e.g. `"btn-fill": "linear-gradient(180deg, #2474d2, #1c6dd0)"`, `"panel-inner-radius": "6px"`) and changes `shadow-overlay` to `0 16px 40px rgba(0, 0, 0, .55), 0 2px 8px rgba(0, 0, 0, .4)`. Nothing else moves.

- [ ] **Step 6: Run the narrow runs**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts
python $WT/scripts/dev/testrun.py file tests/charts/test_chart_theme.py
python $WT/scripts/dev/testrun.py file tests/dev/test_dump_tokens.py
```
Expected: frontend `Tests  N passed`, 0 failed; both Python runs `N passed`, 0 failed (`test_resolver_reproduces_the_committed_fixture` proves the Python resolver read the second `:root`). Quote the verdict lines.

- [ ] **Step 7: Commit**

```bash
git -C $WT add frontend/src/styles/tokens.css frontend/src/app/ui/tokens.spec.ts tests/charts/resolved_tokens.json
git -C $WT commit -m "feat(ui): v167 AN8 -- tier-3 component tokens; two-level elevation geometry

A second :root at the end of tokens.css holds the four radius targets,
the panel, overlay and button tokens, the glows and --scrim-soft.
--shadow-overlay moves there with the new geometry; the v54 D2 one-shadow
comment is marked superseded. tokens.spec.ts asserts every tier-3 value and
that no gradient token is painted as background-color.

<frontend verdict line>
<test_chart_theme.py verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task AN9: `.sb-panel` and two-level elevation; the three panel primitives on the panel tokens

**Model:** sonnet — a global class, two gate edits and three primitives

**Files:**
- Modify: `frontend/src/styles.css:37-40` (`body` background), `:145-160` (elevation comment, new `.sb-panel`, `.elev-overlay` radius)
- Modify: `frontend/src/app/ui/elevation.spec.ts` (whole file, 23 lines today)
- Modify: `frontend/src/app/ui/primitives.spec.ts:137-161` (G3 comment, title and its `styles.css` case)
- Modify: `frontend/src/app/ui/layout.ts:34` (template root) and `:65-70` (`.panel`)
- Modify: `frontend/src/app/ui/figure.ts:13` (`sb-figure-strip`, one line)
- Modify: `frontend/src/app/ui/chart-container.ts:43` (template root) and `:84-92` (`.frame`)

**Interfaces:**
- Consumes: AN8's `--panel-bg`, `--panel-border`, `--panel-radius`, `--panel-shadow`, `--shadow-overlay`, `--glow-ambient`.
- Produces: the global class `.sb-panel { box-shadow: var(--panel-shadow); }` in `styles.css`, declared before `.elev-overlay`; `.elev-overlay` rounded at `var(--panel-radius)`; `body { background: var(--glow-ambient), var(--bg); }`; G3 asserting `['var(--panel-shadow)', 'var(--shadow-overlay)']` (AN11 edits other blocks of the same `primitives.spec.ts`; it must not touch G3). The three primitives already on `--panel-radius`, which AN12's table records as done.

**Not in this task:** the per-component G3 loop still covers `callSites()` only (spec: unchanged); `Figure`'s own `.figure { background: var(--surface) }` stays as it is (the spec names the strip, not the cell; any visual fallout is v169's sweep). Parallel with AN10 (disjoint files).

- [ ] **Step 1: Write the failing elevation spec**

Replace the whole of `frontend/src/app/ui/elevation.spec.ts` with:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const GLOBAL = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');
const ui = (file: string) => readFileSync(join(process.cwd(), 'src/app/ui', file), 'utf8');

/**
 * The elevation ladder -- spec v167 §3, which supersedes v54 D2's one-shadow
 * law. In-flow panels cast --panel-shadow through the global .sb-panel
 * class; out-of-flow elements cast --shadow-overlay through .elev-overlay.
 * primitives.spec.ts G3 is the gate that nothing else casts a shadow.
 */
describe('the elevation ladder', () => {
  it('defines one in-flow panel rule carrying the panel shadow', () => {
    expect(GLOBAL).toMatch(/\.sb-panel\s*\{[^}]*box-shadow:\s*var\(--panel-shadow\)/s);
  });

  it('defines one overlay rule carrying the overlay shadow', () => {
    expect(GLOBAL).toMatch(/\.elev-overlay\s*\{[^}]*box-shadow:\s*var\(--shadow-overlay\)/s);
  });

  it('declares .sb-panel before .elev-overlay, so an overlay wins a tie', () => {
    const panel = GLOBAL.search(/\.sb-panel\s*\{/);
    expect(panel).toBeGreaterThan(-1);
    expect(panel).toBeLessThan(GLOBAL.search(/\.elev-overlay\s*\{/));
  });

  it('gives the overlay the raised surface, the strong border and the panel radius', () => {
    const rule = GLOBAL.match(/\.elev-overlay\s*\{[^}]*\}/s)![0];
    expect(rule).toContain('var(--surface-overlay)');
    expect(rule).toContain('var(--border-strong)');
    expect(rule).toContain('border-radius: var(--panel-radius)');
  });

  it('defines a scrim that uses the token rather than a raw rgba', () => {
    const rule = GLOBAL.match(/\.elev-scrim\s*\{[^}]*\}/s)![0];
    expect(rule).toContain('var(--scrim)');
    expect(rule).not.toMatch(/rgba?\(/);
  });

  it('grounds the page on the ambient glow over --bg', () => {
    expect(GLOBAL).toMatch(/body\s*\{[^}]*background:\s*var\(--glow-ambient\),\s*var\(--bg\);/s);
  });
});

/**
 * The three panel-painting primitives read the tier-3 panel tokens and take
 * their shadow from .sb-panel, never from a box-shadow of their own.
 */
describe('the panel primitives paint the panel tokens (v167 §3)', () => {
  const PANEL = [
    'background: var(--panel-bg);',
    'border: var(--panel-border);',
    'border-radius: var(--panel-radius);',
  ];
  const expectPanelRule = (rule: string) => {
    for (const declaration of PANEL) expect(rule).toContain(declaration);
    expect(rule).not.toContain('var(--surface)');
    expect(rule).not.toContain('box-shadow');
  };

  it('sb-panel puts .sb-panel on its section and paints .panel from the tokens', () => {
    const source = ui('layout.ts');
    expect(source).toContain('<section class="panel sb-panel">');
    expectPanelRule(source.match(/\.panel\s*\{[^}]*\}/)![0]);
  });

  it('sb-figure-strip carries .sb-panel on its host and paints :host from the tokens', () => {
    const line = ui('figure.ts').split('\n').find((l) => l.includes("selector: 'sb-figure-strip'"))!;
    expect(line).toMatch(/host:\s*\{\s*class:\s*'sb-panel'/);
    expectPanelRule(line.match(/:host\s*\{[^}]*\}/)![0]);
  });

  it('sb-chart-container puts .sb-panel on its frame and paints .frame from the tokens', () => {
    const source = ui('chart-container.ts');
    expect(source).toContain('<figure class="frame sb-panel"');
    expectPanelRule(source.match(/\.frame\s*\{[^}]*\}/)![0]);
  });
});
```

- [ ] **Step 2: Move G3 to two levels in `primitives.spec.ts`**

Re-read `primitives.spec.ts:137-161`. Replace the doc comment above G3 and the whole `describe('G3: only L3 casts a shadow', ...)` block with:

```ts
/**
 * G3 -- a non-inset box-shadow appears in exactly two rules, both global:
 * .sb-panel (in flow, --panel-shadow) and .elev-overlay (out of flow,
 * --shadow-overlay), in that order in styles.css.
 *
 * Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §3):
 * this gate used to allow exactly one shadow, the L3 rule (spec v54 D2's
 * one-shadow law).
 *
 * `inset` is deliberately exempt and is not a loophole: an inset shadow is a
 * border drawn inside the box, not elevation. The four in this codebase are
 * the active-nav indicator, two focus/selection rings and the today marker,
 * and rewriting them as borders would change layout for no gain.
 */
describe('G3: only the two elevation rules cast a shadow', () => {
  const shadows = (source: string) =>
    [...source.matchAll(/box-shadow:\s*([^;]+);/g)]
      .map(([, value]) => value.trim())
      .filter((value) => !value.startsWith('inset'));

  for (const { name, source } of callSites()) {
    it(`${name} casts no elevation shadow`, () => {
      expect(shadows(source)).toEqual([]);
    });
  }

  it('styles.css casts exactly two, both tokens, the panel first', () => {
    const global = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');
    expect(shadows(global)).toEqual(['var(--panel-shadow)', 'var(--shadow-overlay)']);
  });
});
```

- [ ] **Step 3: Run them and watch them fail**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/elevation.spec.ts --include src/app/ui/primitives.spec.ts
```
Expected: FAIL in `defines one in-flow panel rule`, `declares .sb-panel before .elev-overlay`, `... the panel radius`, `grounds the page on the ambient glow`, all three primitive cases, and G3's `styles.css casts exactly two` (`['var(--shadow-overlay)']`). The overlay-shadow and scrim cases pass.

- [ ] **Step 4: Edit `styles.css`**

In the `body` rule (`:37-40`), change `background: var(--bg);` to:

```css
  background: var(--glow-ambient), var(--bg);
```

Replace `:145-160` (the `/* L3 — the only level that casts a shadow.` comment through the closing `}` of `.elev-overlay`) with:

```css
/* Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §3):
 * the one-shadow law this comment stated (spec v54 D2). Original text, kept:
 *
 * L3 — the only level that casts a shadow.
 *
 * L0 --bg (the page, no border), L1 --surface (a panel, 1px border),
 * L2 --surface-raised (a thing on a panel, 1px border) and L3 (this) are the
 * whole ladder. Levels 0-2 are distinguished by surface lightness alone; a
 * shadow at those levels is mud on near-black, not depth.
 *
 * So a shadow here says exactly one thing: THIS ELEMENT IS NOT PART OF THE
 * PAGE FLOW. Dropdown, popover, tooltip, toast, drawer, dialog. Nothing else
 * may take it, and primitives.spec.ts enforces that.
 *
 * v167 §3, two levels. An in-flow panel (L1/L2) takes .sb-panel and casts
 * --panel-shadow: a 3% top highlight and a soft drop. An out-of-flow element
 * (L3: dropdown, popover, tooltip, toast, drawer, dialog) takes .elev-overlay
 * and casts --shadow-overlay. No component writes a non-inset box-shadow of
 * its own; primitives.spec.ts G3 holds this file to exactly these two, panel
 * first, so an element carrying both classes reads as the overlay. */
.sb-panel {
  box-shadow: var(--panel-shadow);
}

.elev-overlay {
  background: var(--surface-overlay);
  border: 1px solid var(--border-strong);
  border-radius: var(--panel-radius);
  box-shadow: var(--shadow-overlay);
}
```

`.drawer.elev-overlay { border-radius: 0; ... }` in `layout.ts:381` is more specific and keeps the drawer's flush edge; leave it.

- [ ] **Step 5: Move the three primitives onto the panel tokens**

`frontend/src/app/ui/layout.ts`: the template root (`:34`) becomes

```html
    <section class="panel sb-panel">
```

and the `.panel` rule (`:65-70`) becomes

```css
    .panel {
      background: var(--panel-bg);
      border: var(--panel-border);
      border-radius: var(--panel-radius);
      overflow: hidden;
    }
```

`frontend/src/app/ui/figure.ts`: replace line 13 (the `sb-figure-strip` `@Component` line) with this single line (only the `host` object and the `:host` rule change):

```ts
@Component({ selector: 'sb-figure-strip', changeDetection: ChangeDetectionStrategy.OnPush, host: { class: 'sb-panel', '[style.--figure-columns]': 'columns()' }, template: `<div class="strip"><ng-content /></div>`, styles: `:host { display: block; overflow: hidden; background: var(--panel-bg); border: var(--panel-border); border-radius: var(--panel-radius); container: figures / inline-size; } .strip { --figure-rule: 1px; display: grid; grid-template-columns: repeat(var(--figure-columns, 4), minmax(0, 1fr)); margin: -1px 0 0 -1px; } @container figures (max-width: 639px) { .strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } }`, })
```

`frontend/src/app/ui/chart-container.ts`: the template root (`:43`) becomes

```html
    <figure class="frame sb-panel" [style.height.px]="height()">
```

and the `.frame` rule (`:84-92`) becomes

```css
    .frame {
      position: relative;
      display: flex;
      flex-direction: column;
      background: var(--panel-bg);
      border: var(--panel-border);
      border-radius: var(--panel-radius);
      overflow: hidden;
    }
```

`.retry` in `chart-container.ts:121` keeps `var(--radius)` for now; AN12 moves it to `--control-radius`.

- [ ] **Step 6: Run the narrow runs**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/layout.spec.ts --include src/app/ui/figure.spec.ts --include src/app/ui/chart-container.spec.ts --include src/app/ui/panel-grid.spec.ts
```
Expected: `Tests  N passed`, 0 failed. `layout.spec.ts`, `figure.spec.ts`, `chart-container.spec.ts` and `panel-grid.spec.ts` prove the template edits broke no rendering (tag selectors such as `querySelectorAll('sb-panel')` are unaffected by the new `.sb-panel` class). Quote the verdict line.

- [ ] **Step 7: Commit**

```bash
git -C $WT add frontend/src/styles.css frontend/src/app/ui/elevation.spec.ts frontend/src/app/ui/primitives.spec.ts frontend/src/app/ui/layout.ts frontend/src/app/ui/figure.ts frontend/src/app/ui/chart-container.ts
git -C $WT commit -m "feat(ui): v167 AN9 -- .sb-panel and two-level elevation; panels on the panel tokens

styles.css gains .sb-panel (--panel-shadow) before .elev-overlay, rounds
the overlay at --panel-radius and grounds the body on --glow-ambient over
--bg; the v54 D2 one-shadow comment is marked superseded. G3 now allows
exactly the two token shadows; elevation.spec.ts checks .sb-panel and the
three panel primitives (sb-panel, sb-figure-strip, sb-chart-container),
which paint --panel-bg/--panel-border/--panel-radius.

<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task AN10: Primary button on `--btn-fill` / `--btn-fill-hover`

**Model:** haiku — a fixed two-declaration swap plus its spec lines

**Files:**
- Modify: `frontend/src/app/ui/button.ts:63-69` (the primary comment and its two rules)
- Modify: `frontend/src/app/ui/button.spec.ts:56-59` (the `fills primary` case, plus one new hover case)

**Interfaces:**
- Consumes: AN8's `--btn-fill` and `--btn-fill-hover` (tier-3 gradients) and AN7's `--accent-fill-hi`; `--on-accent` (unchanged name).
- Produces: `:host(.primary) { background: var(--btn-fill); color: var(--on-accent); }` and `:host(.primary:not([disabled]):hover) { background: var(--btn-fill-hover); }`. AN12 later changes `button.ts:52`'s radius; it does not touch these two rules.

Parallel with AN9 (disjoint files). The `:host` radius at `:52` (`var(--radius)`) and `:host(.chip)` at `:137` stay for AN12.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/button.spec.ts`, replace the case `fills primary with the fill blue and its own ink` (`:56-59`) with these two cases (same `describe('v80 D4: the button restyle', ...)` block, same `rule()` helper):

```ts
  /* v167 §3: the fill is the tier-3 gradient. A gradient is an image, so it
   * must be `background`, never `background-color` (which would drop it). */
  it('fills primary with the button gradient and its own ink', () => {
    const primary = rule(':host(.primary)');
    expect(primary).toContain('background: var(--btn-fill)');
    expect(primary).toContain('color: var(--on-accent)');
    expect(primary).not.toContain('background-color');
  });

  it('hovers primary onto the lighter gradient, not a flat color-mix', () => {
    const hover = rule(':host(.primary:not([disabled]):hover)');
    expect(hover).toContain('background: var(--btn-fill-hover)');
    expect(hover).not.toContain('color-mix');
  });
```

- [ ] **Step 2: Run them and watch them fail**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/button.spec.ts
```
Expected: FAIL. `fills primary with the button gradient` gets `background: var(--accent-fill)`; `hovers primary onto the lighter gradient` finds `color-mix(in srgb, var(--accent-fill) 85%, white)`.

- [ ] **Step 3: Swap the two rules and supersede the comment**

Re-read `button.ts:60-70`. Replace `:63-69` (the `/* Blue is interactive-only ...` comment through the `:host(.primary:not([disabled]):hover)` line) with:

```css
    /* Blue is interactive-only, which is exactly what a primary button is --
       the one place the accent is allowed to carry weight. v80 D1 split the
       accent: --accent (#5593ff) is the text-safe blue and too light to carry
       white ink, so a filled button paints --accent-fill (#2962ff) with
       --on-accent on top, 4.90:1.
       Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §3):
       the fill is the tier-3 gradient --btn-fill, from --accent-fill-hi
       (#2474d2, white 4.66:1) down to --accent-fill (#1c6dd0, white
       5.06:1); --accent is now #7cc4ff. A gradient is an image, so it goes
       in `background`, never `background-color`, and does not transition:
       hover swaps to --btn-fill-hover, and v168 animates it with filter and
       glow. */
    :host(.primary) { background: var(--btn-fill); color: var(--on-accent); }
    :host(.primary:not([disabled]):hover) { background: var(--btn-fill-hover); }
```

The hexes in this comment are documentary; the colour gate (AN11) strips `/* */` comments before matching.

- [ ] **Step 4: Run the narrow runs**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/button.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts
```
Expected: `Tests  N passed`, 0 failed (`tokens.spec.ts`'s `never paints a gradient token as background-color` now also covers `button.ts`'s new rules). Quote the verdict line.

- [ ] **Step 5: Commit**

```bash
git -C $WT add frontend/src/app/ui/button.ts frontend/src/app/ui/button.spec.ts
git -C $WT commit -m "feat(ui): v167 AN10 -- primary button on the --btn-fill gradient

:host(.primary) paints --btn-fill and hovers onto --btn-fill-hover instead
of a flat color-mix on --accent-fill; the v80 D1 comment is marked
superseded with the new stops and their contrast.

<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

