# v195 — Graphite, Part 1: palette and shape tokens

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-2:" -A 400 <this file>`.

**Scope of this part (V195-1..V195-3):** the worktree, proven to sit on a v194-merged `main`; the Discord chart `THEME` gains `accent` (on the old palette, so the cache bump is isolated) and the entry line reads it; the Graphite palette (tier 1 rewritten, tier 2 repointed, chart series and cold-load copies re-derived, Discord `THEME` moved in the same commit); the tier-3 shape tokens (6/4/2px radii, flat panels, flat button fill) and the 12px micro/chip floor.

**Where commands run.** Shell state does not persist between Bash calls and `cd` breaks the guardrail hooks, so every command below spells out the worktree path. In this part:

- `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`
- `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`

Start every Bash call with `MAIN=E:/Documents/Private/Projects/Discord-Bot; WT=$MAIN/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign;`. Python runs through `python "$WT/scripts/dev/testrun.py" ...` (it resolves the repo from its own path, so it tests the worktree); frontend runs through `npm --prefix "$WT/frontend" ...`. Edit files only under `$WT/`; never the main tree's copies.

**Palette values measured for this part (plan-time, WCAG 2.1 and OKLab ×100, the same formulas as `contrast.spec.ts`, `chart-palette.spec.ts` and `test_chart_theme.py`).** Two of the spec's §1.1 table values fail a gate and are adjusted in V195-2, which amends the spec table in the same commit (Global Constraints, Contrast):

| Token | Spec value | Used | Why |
|---|---|---|---|
| `--neg` (`--red-500`) | `#e5534b` | `#f06e66` | `#e5534b` measures 4.37:1 on `--surface-raised`, 4.21:1 on `--surface-overlay` and 3.85:1 on its own 12% tint over `--surface-raised` (all under 4.5). `#f06e66`: worst 5.30:1 on a surface, 4.68:1 on its tint. |
| `--info` (`--violet-400`) | `#b392f0` | `#c193ed` | The Discord entry line becomes `accent` `#6ea8fe`; `#b392f0` sits OKLab ΔE 9.7 from it, and the decision chart and price pane draw entry beside AVWAP / volume profile (`info`), so `test_roles_drawn_together_are_distinct` (ΔE ≥ 10) fails. `#c193ed`: ΔE 11.4 from accent, 11.2 from `chart-3`, AA worst 6.44:1. |
| `--chart-2` | `#c97a22` (v80) | `#bd6c18` | Re-derived for Graphite (spec §1.1): `#c97a22` is ΔE 8.0 from the new `warn` `#d29922`, and current price (`warn`) is drawn with the strategy target line (`chart-2`). `#bd6c18`: ΔE 12.0 from warn, 12.3 from neg, 22.5 from pos, OKLCH L 0.610 C 0.136, 4.51:1 on `--surface`. |
| `--accent-fill` / `--accent-fill-hi` | not in spec | `#2563c4` / `#2d6cd3` (`--steel-600` / `--steel-500`) | `--on-accent` white: 5.74:1 / 5.00:1. |

Every other spec value passes as written: `--text` 12.71:1 worst, `--text-secondary` 10.11:1, `--text-muted` 6.19:1, `--accent` 6.46:1, `--pos` 6.15:1 (5.22:1 on its tint), `--warn` 6.18:1; `--chart-1,3,4,5,6` and `--quality-4` keep their values (each still clears ΔE 10 from pos/neg, the lightness band, the chroma floor and 3:1 on `#15181d`).

---

# Phase 1 — Tokens (part 1 of 2)

### Task V195-1: Worktree (v194-merged precondition); Discord `THEME` gains `accent` on the old palette, `ENTRY_COLOR` reads it, `STYLE_PINS` row `v195a`
**Model:** sonnet — a worktree plus one theme key, one constant and two pin rows in a pinned test; mechanical, but the digest must be computed, not guessed.

**Files:**
- Modify: `swingbot/core/charts/chart_style.py` (`THEME` l.54-71, `STYLE_VERSION` l.77, the `ENTRY_COLOR` comment and line l.87-96)
- Modify: `tests/charts/test_chart_theme.py` (`STYLE_PINS` l.43-47, `COLOUR_CONSTANTS["ENTRY_COLOR"]` l.64, one new test)

**Interfaces:**
- Consumes: `chart_style.THEME`, `STYLE_VERSION`, `ENTRY_COLOR` (exist); `test_chart_theme.STYLE_PINS`, `COLOUR_CONSTANTS`, `_theme_digest`, `_resolve` (exist); `dump_tokens.resolve_tokens` (exists, `scripts/dev/dump_tokens.py:105`).
- Produces: the worktree and branch `2026-10-25-v195-graphite-frontend-redesign`; `THEME["accent"]` (the resolved `--accent`, `#7cc4ff` on the Arctic Navy palette until V195-2); `STYLE_VERSION = "v195a"`; `STYLE_PINS` row `("05dcbfb119a03e02", "v195a")`; `COLOUR_CONSTANTS["ENTRY_COLOR"] = "accent"`. V195-2 moves every `THEME` value and appends the `v195` row on top of this.

Why a separate step on the old palette: the entry line changes colour (from `chart-1` `#4c8dff` to `accent` `#7cc4ff`) independently of the palette swap, so a reviewer can reject one without the other, and the `v195a` pin isolates that cache-key change. On the old palette every co-occurrence rule still holds (plan-time: entry vs volume profile / AVWAP ΔE 11.0; entry vs current price, target 2, Keltner, path and both strategy colours all above 10; entry is ΔE ≥ 10 from gain and loss).

- [ ] **Step 1: Prove v194 is merged, then create the worktree**

Run:

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
git -C "$MAIN" fetch origin
git -C "$MAIN" status -sb
git -C "$MAIN" grep -n "hintVerdict" -- frontend/scripts/layout-audit-lib.mjs
git -C "$MAIN" grep -n "supportsPopover" -- frontend/src/app/ui/hint.ts
```

Expected: `status -sb` shows `## main...origin/main` with no `behind`; each `git grep` prints at least one line. If either `git grep` prints nothing, v194 is not merged: **stop**, change nothing, and report `BLOCKED: v194 is not merged into main (hintVerdict/supportsPopover missing)`. If `main` is behind `origin/main`, stop and report it; never pull into a tree another session may be using.

Then list the worktrees:

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
git -C "$MAIN" worktree list
```

If `.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign` is listed, reuse it and resume at its first uncommitted task (`git -C "$MAIN/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign" log --oneline main..HEAD`). Otherwise create it:

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
git -C "$MAIN" worktree add "$MAIN/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign" -b 2026-10-25-v195-graphite-frontend-redesign main
```

Install the frontend dependencies in the worktree (`node_modules` is untracked):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" ci
```

- [ ] **Step 2: Baseline the two suites this part touches**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
python "$WT/scripts/dev/testrun.py" file tests/charts/test_chart_theme.py
npm --prefix "$WT/frontend" test -- --watch=false
```

Expected: both green (`0 failed`, `0 xfailed`). A failure here predates v195: stop and report it rather than fixing it inside this task.

- [ ] **Step 3: Write the failing test**

In `$WT/tests/charts/test_chart_theme.py`:

1. Append one row to `STYLE_PINS` (append-only; never edit an existing row). The tuple becomes:

```python
STYLE_PINS: tuple[tuple[str, str], ...] = (
    ("fb0f840658155cd0", "v80"),
    ("96d64692ba7c2abf", "v167"),  # v167 §4: Arctic Navy
    ("4f15a0f1fb8a6d1e", "v181"),  # v181 §5: saturated teal/red valence pair
    ("05dcbfb119a03e02", "v195a"),  # v195 Phase 6: THEME gains accent, entry reads it
)
```

2. In `COLOUR_CONSTANTS`, change the `ENTRY_COLOR` row (spec correction 14):

```python
    "ENTRY_COLOR": "accent",
```

3. Add this test directly after `test_each_colour_constant_is_its_token`:

```python
def test_the_entry_line_is_the_app_accent():
    """v195 Phase 6: the alert image's entry line is the app's entry line.

    frontend/src/app/ui/chart/plan-lines.ts draws entry in --accent, so the
    PNG reads the same token instead of a chart series (it read chart-1)."""
    assert cs.THEME["accent"] == _resolve()["accent"]
    assert cs.ENTRY_COLOR == cs.THEME["accent"]
```

- [ ] **Step 4: Run it to make sure it fails**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
python "$WT/scripts/dev/testrun.py" file tests/charts/test_chart_theme.py
```

Expected: FAIL. `test_the_entry_line_is_the_app_accent` and `test_each_colour_constant_is_its_token[ENTRY_COLOR-accent]` raise `KeyError: 'accent'`; `test_style_version_is_pinned_to_the_theme_digest` fails because the live pair is still `v181`.

- [ ] **Step 5: Write the implementation**

In `$WT/swingbot/core/charts/chart_style.py`:

1. Add `accent` to `THEME`, after `text-faint` (the resolved Arctic Navy `--accent`, palette `--sky-300`):

```python
THEME = {
    "bg": "#070b14",
    "surface": "#0c1320",
    "surface-raised": "#121b2d",
    "border": "#1d2940",
    "border-strong": "#2a3a58",
    "text": "#e8eef8",
    "text-muted": "#8f9db5",
    "text-faint": "#3a4a66",
    "accent": "#7cc4ff",
    "pos": "#00e5a0",
    "neg": "#ff4d5e",
    "warn": "#ffc266",
    "info": "#c3a6ff",
    "chart-1": "#4c8dff",
    "chart-2": "#c97a22",
    "chart-3": "#a868e0",
    "chart-5": "#1a9db3",
}
```

2. Bump the version (the comment above it stays as it is):

```python
STYLE_VERSION = "v195a"
```

3. Replace the comment block that starts `# One green and one red across the whole image` together with the `ENTRY_COLOR = THEME["chart-1"]` line by:

```python
# One green and one red across the whole image, per the palette's first rule:
# green and red mean P&L direction and nothing else. A target IS the profit
# side and a stop IS the loss side, so they take the same two colours the
# candles do rather than near-miss shades of them -- the old #00c896 target
# against #26a69a candles was two greens that meant the same thing. Line
# weight, dashing and the labelled chip are what separate a level from a
# candle body, not a third hue.
#
# v195 Phase 6: entry is the interactive accent, the colour the admin app
# draws its entry line in (frontend/src/app/ui/chart/plan-lines.ts), so a
# plan reads the same in the Discord image and on bomeo-capital.com. It read
# chart-1, a series identifier, before.
ENTRY_COLOR = THEME["accent"]
```

Nothing else in the module changes: `chart_volume_profile.py`, `decision_chart.py` and `trade_chart.py` import `ENTRY_COLOR` by name and pick the new value up. Module-level constants add no branch, so `complexity_gate.py` is unaffected.

- [ ] **Step 6: Confirm the digest is the pinned one**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
python -c "import sys, hashlib, json; sys.path.insert(0, sys.argv[1]); from swingbot.core.charts import chart_style as cs; print(hashlib.sha256(json.dumps(cs.THEME, sort_keys=True).encode()).hexdigest()[:16], cs.STYLE_VERSION)" "$WT"
```

Expected: `05dcbfb119a03e02 v195a`. A different digest means `THEME` differs from Step 5's dict (a typo, an upper-case hex, a missing key): fix `THEME`, never the pin.

- [ ] **Step 7: Run the tests to make sure they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
python "$WT/scripts/dev/testrun.py" file tests/charts/test_chart_theme.py
python "$WT/scripts/dev/testrun.py" file tests/charts/test_chart_cache.py
```

Expected: PASS, `0 failed`, `0 xfailed` in both (the cache test monkeypatches `STYLE_VERSION` and does not depend on its value).

- [ ] **Step 8: Close**

Close: standard (test: `tests/charts/test_chart_theme.py`). One commit, backend only:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add swingbot/core/charts/chart_style.py tests/charts/test_chart_theme.py
git -C "$WT" commit -m "feat(v195): chart THEME gains accent and the entry line reads it (V195-1)" -m "STYLE_VERSION v195a pins the cache-key change on the Arctic Navy palette, before V195-2 swaps the values." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

### Task V195-2: Graphite palette: tier 1 rewritten, tier 2 repointed, `--chart-2` and alpha tints re-derived, cold-load `--bg`, fixture regenerated, Discord `THEME` values and `STYLE_PINS` row `v195` (one commit)
**Model:** sonnet — values are fixed by this task (measured at plan time); the work is a careful repoint across CSS, two pinned specs, the fixture and `THEME`, landing green in one commit.

**Files:**
- Modify: `frontend/src/styles/palette.css` (whole file)
- Modify: `frontend/src/styles/tokens.css` (tier-2 surface block l.48-58, text/valence/accent/soft block l.88-135, `--chart-2` l.183)
- Modify: `frontend/src/index.html` (l.25 comment, l.29, l.52)
- Modify: `frontend/public/manifest.webmanifest` (l.6-7)
- Modify: `tests/charts/resolved_tokens.json` (regenerated, never hand-edited)
- Modify: `swingbot/core/charts/chart_style.py` (`THEME`, `STYLE_VERSION`, the `MUTED_TEXT_COLOR` comment)
- Modify: `tests/charts/test_chart_theme.py` (`STYLE_PINS`)
- Modify: `frontend/src/app/ui/tokens.spec.ts` (the `v167 §2: the Arctic Navy palette` describe; the `--btn-fill` resolve case)
- Modify: `frontend/src/app/ui/contrast.spec.ts` (two measurement comments)
- Modify: `frontend/src/app/ui/primitives.spec.ts` (`HEX_ALLOWLIST`)
- Modify: `frontend/src/app/ui/chart-palette.spec.ts` (one measurement comment)
- Modify: `frontend/src/app/ui/confidence-cell.spec.ts` (the `--info` literal pin, l.83-86; found by the plan-time grep, not listed in the index ledger row)
- Modify: `docs/superpowers/specs/2026-10-25-v195-graphite-frontend-redesign.md` (§1.1 table: `neg` and `category / violet` amended)

**Interfaces:**
- Consumes: `THEME["accent"]`, `STYLE_VERSION = "v195a"`, `STYLE_PINS` row `v195a` (V195-1); `resolveToken` (`frontend/src/app/ui/testing/resolve-token.ts`), `HEX_ALLOWLIST` (`primitives.spec.ts:121`), `dump_tokens.resolve_tokens` (exist).
- Produces (every later task reads tier 2 only; these names are for tests and the Discord theme):
  - tier 1 (`palette.css`): `--graphite-950 #0d0f12`, `--graphite-900 #15181d`, `--graphite-850 #1c2128`, `--graphite-800 #1f242b`, `--graphite-750 #23272e`, `--graphite-700 #2d333b`, `--graphite-500 #6b7280`, `--grey-400 #9aa4b2`, `--grey-300 #c9d1d9`, `--grey-100 #e6e8eb`, `--white #ffffff`, `--steel-400 #6ea8fe`, `--steel-500 #2d6cd3`, `--steel-600 #2563c4`, `--green-500 #3fb68b`, `--red-500 #f06e66`, `--amber-500 #d29922`, `--violet-400 #c193ed`; alpha `--graphite-950-a72`, `--green-500-a12`, `--red-500-a12`, `--amber-500-a12`, `--steel-400-a18`, `--violet-400-a14`.
  - tier 2 resolved: `--bg #0d0f12`, `--surface #15181d`, `--surface-raised #1c2128`, `--surface-overlay #1f242b`, `--border #23272e`, `--border-strong #2d333b`, `--text #e6e8eb`, `--text-secondary #c9d1d9`, `--text-muted #9aa4b2`, `--text-faint #6b7280`, `--accent #6ea8fe`, `--accent-fill #2563c4`, `--accent-fill-hi #2d6cd3`, `--on-accent #ffffff`, `--pos #3fb68b`, `--neg #f06e66`, `--warn #d29922`, `--info #c193ed`; `--chart-2 #bd6c18`.
  - `STYLE_VERSION = "v195"`; `STYLE_PINS` row `("f04168edd2b2e287", "v195")`.

The values are measured in this part's header table (`--neg` and `--info` differ from the spec's table; the spec is amended in this commit, Step 9). Tier-2 names do not change, so no component file changes in this task.

- [ ] **Step 1: Write the failing tests**

1. `$WT/frontend/src/app/ui/tokens.spec.ts` — replace the whole `describe('v167 §2: the Arctic Navy palette', () => { ... });` block with:

```ts
describe('v195 §1.1: the Graphite palette', () => {
  const EXPECTED: [token: string, palette: string, value: string][] = [
    ['--bg', '--graphite-950', '#0d0f12'],
    ['--surface', '--graphite-900', '#15181d'],
    ['--surface-raised', '--graphite-850', '#1c2128'],
    ['--surface-overlay', '--graphite-800', '#1f242b'],
    ['--overlay-dim', '--graphite-950-a72', 'rgba(13, 15, 18, 0.72)'],
    ['--border', '--graphite-750', '#23272e'],
    ['--border-strong', '--graphite-700', '#2d333b'],
    ['--text', '--grey-100', '#e6e8eb'],
    ['--text-secondary', '--grey-300', '#c9d1d9'],
    ['--text-muted', '--grey-400', '#9aa4b2'],
    ['--text-faint', '--graphite-500', '#6b7280'],
    ['--accent', '--steel-400', '#6ea8fe'],
    ['--accent-fill', '--steel-600', '#2563c4'],
    ['--accent-fill-hi', '--steel-500', '#2d6cd3'],
    ['--on-accent', '--white', '#ffffff'],
    ['--pos', '--green-500', '#3fb68b'],
    // Spec table said #e5534b; amended to #f06e66 for WCAG AA on the raised
    // and overlay surfaces and on its own tint (V195-2).
    ['--neg', '--red-500', '#f06e66'],
    ['--warn', '--amber-500', '#d29922'],
    // Spec table said #b392f0; amended to #c193ed to clear OKLab dE 10 from
    // the accent entry line in the Discord image (V195-2).
    ['--info', '--violet-400', '#c193ed'],
    ['--pos-soft', '--green-500-a12', 'rgba(63, 182, 139, 0.12)'],
    ['--neg-soft', '--red-500-a12', 'rgba(240, 110, 102, 0.12)'],
    ['--warn-soft', '--amber-500-a12', 'rgba(210, 153, 34, 0.12)'],
    ['--accent-soft', '--steel-400-a18', 'rgba(110, 168, 254, 0.18)'],
    ['--info-soft', '--violet-400-a14', 'rgba(193, 147, 237, 0.14)'],
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

  /* #c97a22 sat OKLab dE 8.0 from the new --warn, and the Discord price pane
   * draws current price (warn) beside the strategy target line (chart-2). */
  it('re-derives --chart-2 off the amber warn for the Graphite ground', () => {
    expect(resolveToken('--chart-2')).toBe('#bd6c18');
  });

  it('keeps no Arctic Navy palette name in either token file', () => {
    const PALETTE = readFileSync(join(process.cwd(), 'src/styles/palette.css'), 'utf8');
    for (const source of [CSS, PALETTE]) {
      expect(source).not.toMatch(/--(?:navy|slate|sky|teal)-\d/);
    }
  });
});
```

In the `describe('v167 §3: the tier-3 component tokens', ...)` block, change the gradient resolve case to the Graphite fills (V195-3 flattens it):

```ts
  it('resolves the button gradient to the two Graphite fill blues', () => {
    expect(resolveToken('--btn-fill')).toBe('linear-gradient(180deg, #2d6cd3, #2563c4)');
  });
```

2. `$WT/frontend/src/app/ui/primitives.spec.ts` — the `HEX_ALLOWLIST` entry (its comment stays):

```ts
  ['index.html', ['#0d0f12', '#0d0f12']],
```

3. `$WT/frontend/src/app/ui/confidence-cell.spec.ts` — the info pin:

```ts
  it('keeps info off the quality ramp (v195: violet, not blue)', () => {
    const root = getComputedStyle(document.documentElement);
    expect(root.getPropertyValue('--info').trim().toLowerCase()).toBe('#c193ed');
  });
```

4. `$WT/tests/charts/test_chart_theme.py` — append the Graphite row (the tuple's earlier rows stay byte for byte):

```python
    ("f04168edd2b2e287", "v195"),  # v195 §1.1: Graphite
```

- [ ] **Step 2: Run them to make sure they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/tokens.spec.ts
python "$WT/scripts/dev/testrun.py" file tests/charts/test_chart_theme.py
```

Expected: FAIL. `tokens.spec.ts`: every `references --graphite-…`/`--grey-…`/`--steel-…` case and every `resolves to` case (the tokens still point at `--navy-*`), the `--chart-2` case and the no-Arctic-Navy case. `test_chart_theme.py`: `test_style_version_is_pinned_to_the_theme_digest` (live pair is `v195a`).

- [ ] **Step 3: Rewrite tier 1**

Replace the whole of `$WT/frontend/src/styles/palette.css` with:

```css
/* Tier 1: the Graphite palette -- spec v195 §1.1
 * (docs/superpowers/specs/2026-10-25-v195-graphite-frontend-redesign.md),
 * replacing v167's Arctic Navy.
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
 * (spec v167, amendment 2, still in force under v195).
 *
 * Two values differ from the v195 spec's first table, measured and amended
 * in the spec by V195-2: --red-500 (#e5534b failed WCAG AA on the raised
 * and overlay surfaces and on its own tint) and --violet-400 (#b392f0 sat
 * within OKLab dE 10 of the accent entry line in the Discord image).
 *
 * Change a value here, then run `python scripts/dev/dump_tokens.py` and
 * commit tests/charts/resolved_tokens.json with it. If the token is one
 * chart_style.THEME names, THEME and STYLE_VERSION change in the same
 * commit (tests/charts/test_chart_theme.py pins the pair).
 */
:root {
  /* ground and structure, darkest first */
  --graphite-950: #0d0f12;
  --graphite-900: #15181d;
  --graphite-850: #1c2128;
  --graphite-800: #1f242b;
  --graphite-750: #23272e;
  --graphite-700: #2d333b;
  /* rules, dividers and disabled glyphs only -- never text */
  --graphite-500: #6b7280;

  /* ink */
  --grey-400: #9aa4b2;
  --grey-300: #c9d1d9;
  --grey-100: #e6e8eb;
  --white: #ffffff;

  /* steel blue: interactive only. 400 is the text-safe accent; 500 and
     600 are the fills that carry white ink (5.00:1 and 5.74:1). */
  --steel-400: #6ea8fe;
  --steel-500: #2d6cd3;
  --steel-600: #2563c4;

  /* valence and category hues, muted for a calm surface */
  --green-500: #3fb68b;
  --red-500: #f06e66;
  --amber-500: #d29922;
  --violet-400: #c193ed;

  /* alpha entries: tints and the overlay dim */
  --graphite-950-a72: rgba(13, 15, 18, 0.72);
  --green-500-a12: rgba(63, 182, 139, 0.12);
  --red-500-a12: rgba(240, 110, 102, 0.12);
  --amber-500-a12: rgba(210, 153, 34, 0.12);
  --steel-400-a18: rgba(110, 168, 254, 0.18);
  --violet-400-a14: rgba(193, 147, 237, 0.14);
}
```

- [ ] **Step 4: Repoint tier 2 and re-derive `--chart-2`**

In `$WT/frontend/src/styles/tokens.css`:

1. Replace from the comment line `  /* v167 §2, Arctic Navy. The ground steps 070b14 -> 0c1320 -> 121b2d ->` through `  --border-strong: var(--navy-700);` with:

```css
  /* v195 §1.1, Graphite (supersedes v167 §2's Arctic Navy). A neutral
   * near-black ground stepping 0d0f12 -> 15181d -> 1c2128 -> 1f242b; depth
   * comes from these steps and 1px borders only (v195 §1.2). Every colour
   * in this tier is a var() into styles/palette.css (tier 1): a tier-2
   * token names a MEANING and never holds a hue. --surface is still the
   * Discord chart ground (chart_style.CHART_BG). */
  --bg: var(--graphite-950);
  --surface: var(--graphite-900);
  --surface-raised: var(--graphite-850);
  --surface-overlay: var(--graphite-800);
  --overlay-dim: var(--graphite-950-a72);
  --border: var(--graphite-750);
  --border-strong: var(--graphite-700);
```

2. Replace from `  --text: var(--slate-100);` through `  --info-soft: var(--violet-300-a14);` (every line between them included) with:

```css
  --text: var(--grey-100);
  --text-secondary: var(--grey-300);
  /* v80 D1 / v167 §2 measured this token against the 4.5:1 gate that
   * contrast.spec.ts enforces on all four surfaces, for readable labels at
   * --text-micro (KPI captions, table headers, .sb-label).
   * v195 §1.1: --grey-400, worst case 6.19:1 (on --surface-overlay). Micro
   * labels and captions use this, never --text-faint (correction 13). */
  --text-muted: var(--grey-400);
  /* --text-faint is a RULE AND DIVIDER colour (~3.7:1 on --surface) -- never
   * text that must be read. contrast.spec.ts's `no-text-uses-text-faint`
   * assumes this and this comment is what it checks for. v195: it is also
   * the disabled-glyph colour, and nothing else. */
  --text-faint: var(--graphite-500);

  --pos: var(--green-500);
  --neg: var(--red-500);
  --warn: var(--amber-500);
  /* v80 D1: the accent is two tokens. --accent is the colour of interactive
   * TEXT and state -- links, the active tab, the sort arrow, focus -- and
   * must read on every surface. --accent-fill is the deeper blue a filled
   * button paints, with --on-accent on top; the text-safe blue is too light
   * to carry white ink.
   * v195 §1.1: --accent is --steel-400 (6.46:1 worst case) and is used for
   * interactive state only; --accent-fill is --steel-600 (white 5.74:1);
   * --accent-fill-hi is --steel-500 (white 5.00:1), the hover fill.
   * contrast.spec.ts checks both fills by name. */
  --accent: var(--steel-400);
  --accent-fill: var(--steel-600);
  --accent-fill-hi: var(--steel-500);
  --on-accent: var(--white);
  /* v80 D1: info is off the blue, so "neutral" never reads as
   * "interactive". v195 §1.1: --violet-400, 6.44:1 worst case, moved from
   * the spec's #b392f0 to clear OKLab dE 10 from the accent entry line. */
  --info: var(--violet-400);

  /* 12% tints, for cell and chip backgrounds, hover states and the chart's
   * risk/reward bands; --info-soft is 14%; --accent-soft (the selected-
   * segment ground) is 18% of the accent. v167 amendment 2: each is a
   * tier-1 alpha entry in palette.css (literal rgba of the hue), so jsdom
   * and lightweight-charts still receive a plain colour string and this
   * file holds no hued rgba. */
  --pos-soft: var(--green-500-a12);
  --neg-soft: var(--red-500-a12);
  --warn-soft: var(--amber-500-a12);
  --accent-soft: var(--steel-400-a18);
  --info-soft: var(--violet-400-a14);
```

3. In the chart-series block, change the one line and add the note directly above `--chart-1`:

```css
  /* v195 §1.1: re-checked on the Graphite ground (#15181d) against the new
   * --pos/--neg/--warn. Five series keep their v80 values; --chart-2 moves
   * from #c97a22 (OKLab dE 8.0 from --warn) to #bd6c18 (12.0 from --warn,
   * 12.3 from --neg, L 0.610, C 0.136, 4.51:1 on --surface). */
  --chart-1: #4c8dff;
  --chart-2: #bd6c18;
```

`--quality-4: #9acd32` stays (plan-time: ΔE 14.5 from `--pos`, 15.0 from `--warn`, 8.29:1 worst case).

- [ ] **Step 5: Move the cold-load copies of `--bg`**

1. `$WT/frontend/src/index.html`: in the comment at l.25 change `palette.css --navy-950` to `palette.css --graphite-950`; l.29 becomes `<meta name="theme-color" content="#0d0f12">`; l.52 becomes `<style>html, body { background: #0d0f12; }</style>` (keep both literal shapes exactly: `primitives.spec.ts` matches them with fixed regexes).
2. `$WT/frontend/public/manifest.webmanifest`: `"theme_color": "#0d0f12",` and `"background_color": "#0d0f12",`.

- [ ] **Step 6: Regenerate the fixture**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
python "$WT/scripts/dev/dump_tokens.py"
python "$WT/scripts/dev/dump_tokens.py" --check
git -C "$WT" diff --stat -- tests/charts/resolved_tokens.json
```

Expected: the first writes `tests/charts/resolved_tokens.json`; `--check` exits 0; the diff shows the `navy-*`/`slate-*`/`sky-*`/`teal-*`/`red-400`/`amber-300`/`violet-300` keys replaced by the Graphite names and the tier-2 values changed.

- [ ] **Step 7: Move the Discord `THEME` to Graphite**

In `$WT/swingbot/core/charts/chart_style.py`:

```python
THEME = {
    "bg": "#0d0f12",
    "surface": "#15181d",
    "surface-raised": "#1c2128",
    "border": "#23272e",
    "border-strong": "#2d333b",
    "text": "#e6e8eb",
    "text-muted": "#9aa4b2",
    "text-faint": "#6b7280",
    "accent": "#6ea8fe",
    "pos": "#3fb68b",
    "neg": "#f06e66",
    "warn": "#d29922",
    "info": "#c193ed",
    "chart-1": "#4c8dff",
    "chart-2": "#bd6c18",
    "chart-3": "#a868e0",
    "chart-5": "#1a9db3",
}
```

```python
STYLE_VERSION = "v195"
```

and the muted-text comment (the measurement changed):

```python
MUTED_TEXT_COLOR = THEME["text-muted"]  # tick labels, fine print: 7.06:1 on CHART_BG (#666666 was 3.6:1)
```

Plan-time measurement of `test_chart_theme.py`'s rules on these values: every non-gain/loss constant is ΔE ≥ 10.7 from gain and loss; the closest co-drawn pairs are entry vs volume profile / AVWAP 11.4, target 2 vs volume profile 11.2, entry vs Keltner 11.7, Keltner vs stop strategy 11.8.

- [ ] **Step 8: Confirm the digest is the pinned one**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
python -c "import sys, hashlib, json; sys.path.insert(0, sys.argv[1]); from swingbot.core.charts import chart_style as cs; print(hashlib.sha256(json.dumps(cs.THEME, sort_keys=True).encode()).hexdigest()[:16], cs.STYLE_VERSION)" "$WT"
```

Expected: `f04168edd2b2e287 v195`. A different digest means `THEME` differs from Step 7: fix `THEME`, never the pin.

- [ ] **Step 9: Amend the spec table and the measurement comments**

1. `$WT/docs/superpowers/specs/2026-10-25-v195-graphite-frontend-redesign.md`, §1.1 table, two rows:

```markdown
| neg | `#f06e66` (amended by V195-2 from `#e5534b`, which measured 4.37:1 on raised, 4.21:1 on overlay and 3.85:1 on its own tint) |
| category / violet | `#c193ed` (amended by V195-2 from `#b392f0`, OKLab ΔE 9.7 from the accent entry line in the Discord image) |
```

and directly under the table, before the paragraph that starts `The alpha tints`:

```markdown
**Amended in V195-2 (plan v195, 2026-10-25).** Two table values failed a gate and were moved to the nearest passing value, per the rule below: `neg` (WCAG AA) and `category / violet` (`test_chart_theme.py`'s ΔE ≥ 10 between roles drawn together). `--chart-2` was re-derived to `#bd6c18` (it sat ΔE 8.0 from `warn`). The accent fills, not given above, are `#2563c4` (`--accent-fill`, white 5.74:1) and `#2d6cd3` (`--accent-fill-hi`, white 5.00:1).
```

2. `$WT/frontend/src/app/ui/contrast.spec.ts`: in the `NON_TEXT` doc comment change `` `--text-faint` measures ~2.3:1 on --surface. `` to `` `--text-faint` measures ~3.7:1 on --surface (v195 Graphite). ``; replace the comment above `'--on-accent on --accent-fill-hi clears 4.5:1'` with:

```ts
  /* v167 §2 / v195 §1.1: --accent-fill-hi is the hover fill of the primary
   * button, so white ink sits on it too. Under Graphite it measures 5.00:1
   * against --accent-fill's 5.74:1; the thinner margin is why it is checked
   * by name rather than assumed from --accent-fill. */
```

3. `$WT/frontend/src/app/ui/chart-palette.spec.ts`: in the doc comment above `describe('the chart series on the chart ground', ...)` change `on \`--surface-overlay\` chart-6 measures 3.94:1` to `on \`--surface-overlay\` (v195 Graphite) chart-2 measures 3.96:1 and chart-6 4.05:1`.

- [ ] **Step 10: Run the tests to make sure they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/confidence-cell.spec.ts --include src/app/ui/resolve-token.spec.ts
python "$WT/scripts/dev/testrun.py" file tests/charts/test_chart_theme.py
python "$WT/scripts/dev/testrun.py" file tests/dev/test_dump_tokens.py
```

Expected: PASS, `0 failed`, `0 xfailed`. If a contrast case fails, the value in Step 3 was mistyped: compare it with the table in this part's header, do not lower a gate.

Then the whole frontend and lint:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. The plan-time grep found no other spec pinning an Arctic Navy literal (`resolve-token.spec.ts` and `tests/dev/test_dump_tokens.py` use their own inline fixtures). A spec that still fails on an old literal is updated to the resolved Graphite value and named in the commit body.

- [ ] **Step 11: Close**

Close: standard (test: `frontend/src/app/ui/tokens.spec.ts`), plus `tests/charts/test_chart_theme.py` in step 2 of the close. Deviation: **one commit** for frontend and backend (Global Constraints: the regenerated fixture and `THEME` cannot be green apart):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/styles/palette.css frontend/src/styles/tokens.css frontend/src/index.html frontend/public/manifest.webmanifest tests/charts/resolved_tokens.json swingbot/core/charts/chart_style.py tests/charts/test_chart_theme.py frontend/src/app/ui/tokens.spec.ts frontend/src/app/ui/contrast.spec.ts frontend/src/app/ui/primitives.spec.ts frontend/src/app/ui/chart-palette.spec.ts frontend/src/app/ui/confidence-cell.spec.ts docs/superpowers/specs/2026-10-25-v195-graphite-frontend-redesign.md
git -C "$WT" commit -m "feat(v195): Graphite palette across the app and the Discord chart theme (V195-2)" -m "Tier 1 rewritten, tier 2 repointed (names unchanged), --chart-2 re-derived, cold-load --bg moved, resolved_tokens.json regenerated, THEME at STYLE_VERSION v195. Spec table amended: neg #f06e66 (AA), violet #c193ed (dE from the accent entry line)." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

### Task V195-3: Tier-3 shape and type: 6/4/2px radii, flat `--panel-bg`, no panel shadow, flat button fill, 12px micro/chip floor
**Model:** sonnet — token values and their pinning specs only, no component code; the care is in keeping the tier-3 block's single-`:root`, no-`@media` contract and the zoom-floor arithmetic.

**Files:**
- Modify: `frontend/src/styles/tokens.css` (the type-scale comment and `--text-micro`/`--text-chip` l.~208-225; the tier-2 radius comment l.~270; the whole tier-3 block from its banner to the end of the file)
- Modify: `tests/charts/resolved_tokens.json` (regenerated)
- Modify: `frontend/src/app/ui/tokens.spec.ts` (`v80 D3` radius case; `v167 §3` `VALUES` and the `--btn-fill` resolve case; the `v179: the 11px text floor` describe)
- Modify: `frontend/src/app/ui/text-styles.spec.ts` (`.sb-label` title; the literal floor rises to 12px over comment-stripped sources)
- Modify: `frontend/src/app/ui/elevation.spec.ts` (one new describe: panels are flat)

**Interfaces:**
- Consumes: the Graphite tier 2 from V195-2 (`--surface #15181d`, `--accent-fill #2563c4`, `--accent-fill-hi #2d6cd3`); `resolveToken` (`ui/testing/resolve-token.ts`); `stripComments` (`ui/testing/all-sources.ts:49`).
- Produces (every Phase 2 primitive reads these names; the names do not change, only the values):
  - `--panel-radius: 6px`, `--control-radius: 4px`, `--chip-radius: 4px`, `--radius-sm: 2px`
  - `--panel-bg: var(--surface)` (a colour, no longer a gradient), `--panel-shadow: none`
  - `--btn-fill: var(--accent-fill)`, `--btn-fill-hover: var(--accent-fill-hi)` (flat colours)
  - `--text-micro: max(12px, calc(12px * var(--text-scale)))`, `--text-chip: max(12px, calc(12px * var(--text-scale)))`
  - Unchanged here and deleted by V195-5: `--glow-accent`, `--glow-ambient`, `--panel-shadow-lift`, `--dur-enter`.

Every consumer of `--panel-bg` and `--btn-fill` uses the `background:` shorthand (`layout.ts:83`, `chart-container.ts:90`, `figure.ts:15`, `button.ts:83,88`; plan-time grep, no `background-image:` reader), so a flat colour in place of a gradient paints correctly with no component edit. `.sb-panel` in `styles.css` keeps `box-shadow: var(--panel-shadow)` (G3 and `elevation.spec.ts` pin that rule); the token being `none` is what flattens it.

The type floor: the spec's scale is 12/13/14/16/20/28 with micro and chip at 12. At the 90% zoom step `--text-table` (13px) computes to 11.7px; this task does not change `--text-table` (not in the spec), so the zoom test holds every token at ≥ 12px for 100/110/125% and at ≥ 11px for 90%, with micro and chip pinned at exactly 12px there. The layout audit's rendered `MIN_TEXT_PX` (11) is unchanged.

- [ ] **Step 1: Write the failing tests**

1. `$WT/frontend/src/app/ui/tokens.spec.ts`, in `describe('v80 D3: type, shape and touch', ...)`, replace the radius case:

```ts
  /* v167 §3 supersedes v80 D3's single 2px: four targets, all in tier 3,
   * and the two old tokens are gone so no unclassified corner survives.
   * v195 §1.5: 6px panels, 4px controls and chips, 2px cells. */
  it('defines the four radius targets', () => {
    expect(TIER3).toMatch(/^\s*--panel-radius:\s*6px;/m);
    expect(TIER3).toMatch(/^\s*--control-radius:\s*4px;/m);
    expect(TIER3).toMatch(/^\s*--chip-radius:\s*4px;/m);
    expect(TIER3).toMatch(/^\s*--radius-sm:\s*2px;/m);
    expect(CSS).not.toMatch(/^\s*--radius(?:-chip)?:/m);
  });
```

2. Same file, `describe('v167 §3: the tier-3 component tokens', ...)`: replace the `VALUES` map and the button resolve case (the other cases in the block stay):

```ts
  const VALUES: Record<string, string> = {
    '--panel-radius': '6px',
    '--control-radius': '4px',
    '--chip-radius': '4px',
    '--radius-sm': '2px',
    '--panel-bg': 'var(--surface)',
    '--panel-border': '1px solid var(--border)',
    '--panel-shadow': 'none',
    '--panel-inner-bg': 'var(--surface-raised)',
    '--panel-inner-radius': 'var(--control-radius)',
    '--shadow-overlay': '0 16px 40px rgba(0, 0, 0, .55), 0 2px 8px rgba(0, 0, 0, .4)',
    '--btn-fill': 'var(--accent-fill)',
    '--btn-fill-hover': 'var(--accent-fill-hi)',
    '--glow-accent': '0 4px 14px color-mix(in srgb, var(--accent-fill) 35%, transparent)',
    '--glow-ambient':
      'radial-gradient(120% 60% at 0% 0%, color-mix(in srgb, var(--accent-fill) 12%, transparent), transparent 60%)',
    '--scrim-soft': 'rgb(0 0 0 / 0.5)',
  };
```

```ts
  /* v195 §1.2: the primary button is one flat fill, no gradient. */
  it('resolves the flat button fill to the two Graphite fill blues', () => {
    expect(resolveToken('--btn-fill')).toBe('#2563c4');
    expect(resolveToken('--btn-fill-hover')).toBe('#2d6cd3');
  });
```

3. Same file: replace the whole `describe('v179: the 11px text floor', ...)` block, and its doc comment, with:

```ts
/**
 * v179 §3.4 / §6b.6, raised by v195 §1.3 (correction 12): the smallest two
 * size tokens, micro and chip, are 12px and floored there inside the token,
 * as max(12px, ...), so the 90% zoom preference (shell.ts ZOOM_CHOICES)
 * cannot push them below it. Every other size token scales freely: at 90%
 * --text-table is 11.7px, which stays above the 11px rendered floor the
 * layout audit measures (MIN_TEXT_PX).
 */
describe('v195: the 12px micro and chip floor', () => {
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

  const sizeOf = (name: string, scale: number) => px(sizes.find((s) => s.name === name)!.value, scale);

  it('finds the size tokens', () => {
    expect(sizes.map((s) => s.name)).toEqual(expect.arrayContaining(['--text-micro', '--text-chip', '--text-table']));
  });

  it.each([1, 1.1, 1.25])('keeps every size token at or above 12px at scale %s', (scale) => {
    const below = sizes
      .filter((s) => px(s.value, scale) < 12)
      .map((s) => `${s.name}=${px(s.value, scale)}px`);
    expect(below).toEqual([]);
  });

  it('keeps micro and chip at 12px and every other token at or above 11px at the 90% step', () => {
    expect(sizeOf('--text-micro', 0.9)).toBe(12);
    expect(sizeOf('--text-chip', 0.9)).toBe(12);
    const below = sizes
      .filter((s) => px(s.value, 0.9) < 11)
      .map((s) => `${s.name}=${px(s.value, 0.9)}px`);
    expect(below).toEqual([]);
  });

  it('floors the two smallest tokens at 12px, inside the token', () => {
    expect(CSS).toMatch(/^\s*--text-micro:\s*max\(12px, calc\(12px \* var\(--text-scale\)\)\);/m);
    expect(CSS).toMatch(/^\s*--text-chip:\s*max\(12px, calc\(12px \* var\(--text-scale\)\)\);/m);
  });

  it('still grows a floored token above 100%', () => {
    expect(sizeOf('--text-micro', 1.25)).toBeCloseTo(15);
  });

  it('reaches jsdom through the regenerated fixture', () => {
    expect(resolveToken('--text-micro')).toBe('max(12px, calc(12px * 1))');
    expect(resolveToken('--text-chip')).toBe('max(12px, calc(12px * 1))');
  });
});
```

4. `$WT/frontend/src/app/ui/text-styles.spec.ts`: change the import line to

```ts
import { allSources, stripComments } from './testing/all-sources';
```

rename the first case's title to `'.sb-label is 12px monospace capitals at 0.08em in muted text'` (its body is unchanged: it reads `var(--text-micro)`), and replace the last describe with:

```ts
describe('v195: no literal text size below 12px', () => {
  /* Comments are stripped: chart/chart-width.ts explains the old 11px
   * floor in prose ("font-size: 11px is 11px at every width"), which is
   * documentation, not a declaration. */
  it('sets no px font-size under 12px anywhere in the app', () => {
    const offenders = allSources().flatMap(({ name, source }) =>
      [...stripComments(source).matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)]
        .filter((m) => Number(m[1]) < 12)
        .map((m) => `${name}: ${m[0]}`));
    expect(offenders).toEqual([]);
  });
});
```

5. `$WT/frontend/src/app/ui/elevation.spec.ts`: add the import

```ts
import { resolveToken } from './testing/resolve-token';
```

and append this describe at the end of the file:

```ts
/**
 * v195 §1.2: depth comes only from the surface steps and 1px borders. The
 * panel is the --surface step with no gradient and no shadow; the overlay
 * shadow is the one shadow token left. .sb-panel still casts
 * var(--panel-shadow) (the rule above), and the token being `none` is what
 * makes it flat, so a later spec can restore depth in one place.
 */
describe('v195 §1.2: panels are flat', () => {
  const TOKENS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

  it('paints the panel on the surface step, not a gradient', () => {
    expect(TOKENS).toMatch(/^\s*--panel-bg:\s*var\(--surface\);/m);
    expect(resolveToken('--panel-bg')).toBe(resolveToken('--surface'));
  });

  it('casts no panel shadow', () => {
    expect(TOKENS).toMatch(/^\s*--panel-shadow:\s*none;/m);
  });

  it('keeps one shadow, on the overlay', () => {
    expect(resolveToken('--shadow-overlay')).not.toBe('none');
    expect(resolveToken('--shadow-overlay')).toMatch(/rgba\(0, 0, 0,/);
  });

  it('paints the primary button flat, with no gradient in either state', () => {
    expect(resolveToken('--btn-fill')).not.toMatch(/gradient/);
    expect(resolveToken('--btn-fill-hover')).not.toMatch(/gradient/);
  });
});
```

- [ ] **Step 2: Run them to make sure they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/text-styles.spec.ts --include src/app/ui/elevation.spec.ts
```

Expected: FAIL. `tokens.spec.ts`: the radius case, the `--panel-radius`/`--control-radius`/`--chip-radius`/`--panel-bg`/`--panel-shadow`/`--btn-fill`/`--btn-fill-hover` value cases, the flat-fill resolve case, the 90%-step case (micro is 11px there today), the floor regex and the fixture case. `elevation.spec.ts`: the four `panels are flat` cases. `text-styles.spec.ts` may already pass (no literal under 12px exists outside comments); that is fine, it pins the new floor.

- [ ] **Step 3: Raise the type floor**

In `$WT/frontend/src/styles/tokens.css`:

1. In the type comment, change `the scale is closed (11/12/13/14/16/20/28)` to `the scale is closed (12/13/14/16/20/28, plus the hero; v195 §1.3)`.
2. Replace from `  /* v179 §6b.6 -- an 11px floor inside the two tokens the 90% zoom step` through `  --text-chip: max(11px, calc(12px * var(--text-scale)));   /* chip */` with:

```css
  /* v179 §6b.6, raised by v195 §1.3 -- a 12px floor inside the two
     smallest tokens. Micro and chip are both 12px at 100% (v195's scale is
     12/13/14/16/20/28), and the floor keeps the 90% zoom step from pushing
     them to 10.8px. Zoom still scales every size above the floor: a
     zoomed-out view fits more, but never drops its smallest labels below
     12px. tokens.spec.ts checks every size token at 90/100/110/125%. */
  --text-micro: max(12px, calc(12px * var(--text-scale)));  /* micro-label */
  --text-chip: max(12px, calc(12px * var(--text-scale)));   /* chip */
```

3. In the tier-2 `-- radii, motion --` comment, change `(--panel-radius 8px, --control-radius 6px, --chip-radius 999px,` / `--radius-sm 2px)` to `(v195 §1.5: --panel-radius 6px, --control-radius 4px, --chip-radius 4px,` / `--radius-sm 2px)`.

- [ ] **Step 4: Flatten tier 3**

Replace everything from the banner line `/* ===== Tier 3: component tokens (spec v167 §3) ===== */` to the end of `$WT/frontend/src/styles/tokens.css` with the block below. The banner line is byte-identical (`tokens.spec.ts` slices on it); the block stays one `:root` with no `@media`; the motion section and `--panel-shadow-lift` are unchanged (V195-5 removes them).

```css
/* ===== Tier 3: component tokens (spec v167 §3) ===== */
/* What a panel, a control, a chip and a button LOOK like, named once, so a
 * component reads these instead of re-spelling background + border +
 * radius + shadow. Every colour here derives from tier 2 by var() or
 * color-mix(): a palette change reaches it. The only rgb()/rgba() literals
 * are black or white at an alpha, inside --shadow-overlay,
 * --panel-shadow-lift and --scrim-soft (the colour gate, primitives.spec.ts).
 *
 * v195 §1.2 / §1.5 (Graphite): flat. A panel is the --surface step and a
 * 1px --border, with no gradient and no shadow (--panel-shadow is none);
 * the primary button is one flat fill. Depth comes only from the surface
 * steps; the one shadow left is --shadow-overlay, for out-of-flow
 * elements. --glow-ambient is still a gradient, i.e. an image
 * (`background` / `background-image` only, never `background-color`;
 * tokens.spec.ts checks styles.css and ui/), until V195-5 deletes it.
 *
 * Last block in the file on purpose: scripts/dev/dump_tokens.py and
 * resolve-token.ts read every top-level :root, and tokens.spec.ts slices
 * tier 3 from this banner to the end. */
:root {
  /* The four radius targets (v195 §1.5). Every border-radius in the app is
   * one of these, or 50% (status dots), 0 (flush edges) or inherit. */
  --panel-radius: 6px;     /* panels, cards, drawers' inner sections, dialogs */
  --control-radius: 4px;   /* buttons, inputs, selects, segmented controls */
  --chip-radius: 4px;      /* chips and tags: squared like a control, not a pill */
  --radius-sm: 2px;        /* cells, thin bars, swatches, tracks: under ~12px tall */

  /* The panel (L1/L2), painted by sb-panel, sb-figure-strip and
   * sb-chart-container. The global .sb-panel class still casts
   * var(--panel-shadow), which is none under v195. */
  --panel-bg: var(--surface);
  --panel-border: 1px solid var(--border);
  --panel-shadow: none;
  /* A panel nested in a panel: one surface step up, no shadow. */
  --panel-inner-bg: var(--surface-raised);
  --panel-inner-radius: var(--control-radius);

  /* Out of flow (L3): dropdown, popover, tooltip, toast, drawer, dialog,
   * through the global .elev-overlay class -- the one shadow v195 keeps. */
  /* Box-shadow geometry (blur/offset) is intentionally exempt from the "px only for 1px/2px borders" rule per design spec D2 -- shadow values have no natural expression via the closed --space-* scale. */
  --shadow-overlay: 0 16px 40px rgba(0, 0, 0, .55), 0 2px 8px rgba(0, 0, 0, .4);

  /* The primary button: one flat fill, --accent-fill (white 5.74:1), and
   * --accent-fill-hi on hover (white 5.00:1); contrast.spec.ts checks
   * both. Colours now, not images, so they could transition. */
  --btn-fill: var(--accent-fill);
  --btn-fill-hover: var(--accent-fill-hi);

  /* Glows are hued, so they derive from the fill blue, never an rgba.
   * Deleted by V195-5, after V195-4 removes the ambient shell layer. */
  --glow-accent: 0 4px 14px color-mix(in srgb, var(--accent-fill) 35%, transparent);
  --glow-ambient: radial-gradient(120% 60% at 0% 0%, color-mix(in srgb, var(--accent-fill) 12%, transparent), transparent 60%);

  /* The mobile-nav scrim (shell.css), given a name. Softer than --scrim,
   * which dims behind a modal. */
  --scrim-soft: rgb(0 0 0 / 0.5);

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
}
```

`primitives.spec.ts`'s `TIER3_RGB` still lists `--panel-shadow`; with no `rgba()` in it any more the set only allows, it does not require, so it stays as is (V195-5 edits that file when `--panel-shadow-lift` goes). Its "only black or white" case still finds the overlay, lift and scrim channels.

- [ ] **Step 5: Regenerate the fixture**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
python "$WT/scripts/dev/dump_tokens.py"
python "$WT/scripts/dev/dump_tokens.py" --check
git -C "$WT" diff -- tests/charts/resolved_tokens.json
```

Expected: `--check` exits 0; the diff changes exactly `panel-radius`, `control-radius`, `chip-radius`, `panel-bg` (`#15181d`), `panel-shadow` (`none`), `panel-inner-radius` (`4px`), `btn-fill` (`#2563c4`), `btn-fill-hover` (`#2d6cd3`), `text-micro` and `text-chip` (`max(12px, calc(12px * 1))`). No `THEME` key changes, so `chart_style.py` and `STYLE_PINS` are untouched.

- [ ] **Step 6: Run the tests to make sure they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/text-styles.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/resolve-token.spec.ts
python "$WT/scripts/dev/testrun.py" file tests/charts/test_chart_theme.py
```

Expected: PASS, `0 failed`, `0 xfailed` (the Python file reruns `test_resolver_reproduces_the_committed_fixture` against the regenerated fixture).

Then the whole frontend and lint:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. The plan-time grep found no other spec pinning `999px`, an 8px/6px radius token value or the gradient strings (`column-picker.spec.ts` asserts `border-radius: var(--control-radius)`, the token name, which still holds).

- [ ] **Step 7: Check the look at three widths**

The full layout audit is V195-36's job. Here, take one Playwright screenshot of `/ui` (the gallery shows panels, chips, buttons and labels together) at 390, 768 and 1440 against `ng serve`, logged in from `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed. Enter at `/app/dashboard` and click through to the gallery (a cold `/app/<route>` bounces by design). Confirm: panels flat on `#15181d` with a hairline border and 6px corners, chips squared at 4px, primary buttons one flat blue, micro labels legible at 12px. Save the three PNGs under the session scratchpad, not the repo; report anything clipped or unreadable as a finding for V195-9..V195-12 rather than fixing a primitive here.

- [ ] **Step 8: Close**

Close: standard (test: `frontend/src/app/ui/tokens.spec.ts`), plus `tests/charts/test_chart_theme.py` in step 2 of the close. One frontend commit (the fixture is a test artifact and goes with the `:root` edit):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/styles/tokens.css tests/charts/resolved_tokens.json frontend/src/app/ui/tokens.spec.ts frontend/src/app/ui/text-styles.spec.ts frontend/src/app/ui/elevation.spec.ts
git -C "$WT" commit -m "feat(v195): flat panels, squared radii and a 12px micro floor (V195-3)" -m "Tier 3: 6/4/4/2px radii, --panel-bg the surface step, --panel-shadow none, one flat button fill. --text-micro and --text-chip floored at 12px." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

