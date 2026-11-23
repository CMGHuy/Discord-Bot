# v241 — Doctena night, plan 1 of 5: Theme and type — Part 1: fonts and colours

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V241-3" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) (§1, §2, §11; its `### Corrections from the plan 1 code brief` section wins over the text above it)
**Index:** [2026-11-23-v241-doctena-night-theme-and-type_0-index.md](2026-11-23-v241-doctena-night-theme-and-type_0-index.md) holds the Goal, Global Constraints, the "Decisions this index fixes", `## Parallelisation` and the task ledger. Every task below implicitly includes the index's Global Constraints.

Tasks V241-1..V241-6: vendor Jost and pin `tnum` in a Python test; Jost in
`fonts.css` with metric-matched fallbacks and JetBrains Mono removed; the
doctena palette and the 20-token Navy block; Navy as the runtime default;
the Navy cold load; the shared `styleRules` parser and `--control-border` on
inputs, selects and segmented controls.

Conventions for every task in this part:

- Frontend commands run from `frontend/`:
  `cd frontend && npx ng test --watch=false --include <spec> [--include <spec>]`.
  A 60s `Timeout waiting for worker` is machine load: re-run once.
- Python: `python scripts/dev/testrun.py file <test>` from the repo root.
- A task that changes a bare-`:root` declaration in `palette.css` or
  `tokens.css` runs `python scripts/dev/dump_tokens.py` and commits
  `tests/charts/resolved_tokens.json` in the same commit; then
  `python scripts/dev/dump_tokens.py --check` must exit 0.
- No task runs the full suite (CI does). Commits are scoped; stage only the
  files the task names.

# Phase 1: Fonts

### Task V241-1: Vendor Jost and pin `tnum` in a Python test

**Model:** haiku — copy three files and write one self-contained Python test; no design choice left.

**Files:**
- Create: `swingbot/admin/static/vendor/jost/jost-latin-wght-normal.woff2`
- Create: `swingbot/admin/static/vendor/jost/jost-latin-ext-wght-normal.woff2`
- Create: `swingbot/admin/static/vendor/jost/LICENSE.txt`
- Create: `tests/dev/test_vendored_fonts.py`
- Modify: `requirements.txt` (one test-only line)

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/dev/test_vendored_fonts.py` with module constants
  `ROOT`, `VENDOR = ROOT / "swingbot/admin/static/vendor"`, `JOST_LATIN`,
  `JOST_LATIN_EXT`, `JOST_LICENSE`. V241-2 appends a "JetBrains Mono is gone"
  test to this file. The two woff2 paths are what `fonts.css` (V241-2) points
  at as `/static/vendor/jost/<file>`.

Why: spec v240 §2 replaces Inter and JetBrains Mono with Jost, self-hosted
(no CDN, spec v13). Jost is proportional, so numeric columns only stay
aligned through its `tnum` (tabular figures) OpenType feature. The brief ran
the check once by hand; this test makes it permanent, so a future file swap
cannot silently drop `tnum`, the 100–900 weight axis or the true minus
(U+2212) every loss prints. Index Decision 8: woff2 decoding needs Brotli,
which `fontTools` (already installed with matplotlib) does not pull in, so
`requirements.txt` gains it as a test-only line. The test asserts the import
and never skips.

- [ ] **Step 1: Install Brotli locally and add it to `requirements.txt`**

Run: `python -m pip install "Brotli>=1.1.0"`

In `requirements.txt`, under the existing `# Test-only dependencies (not needed at bot runtime)` block, directly after the `pytest-xdist>=3.8` line, add:

```text
# v240 §2: fontTools (installed with matplotlib) needs Brotli to open the
# vendored Jost woff2 files in tests/dev/test_vendored_fonts.py.
Brotli>=1.1.0
```

- [ ] **Step 2: Write the failing test**

Create `tests/dev/test_vendored_fonts.py`:

```python
"""The vendored admin fonts (spec v240 §2, §11).

Jost is the one face of the SPA. It is proportional, so tables keep their
digits aligned only through its `tnum` (tabular figures) feature, and every
loss prints a true minus (U+2212). These tests open the vendored woff2
files with fontTools, so a future swap of the files cannot silently lose
either. The latin-ext subset holds no digits: figures always come from the
latin file, which is the one checked for `tnum`, digits and U+2212.

`vendor/inter/` stays while swingbot/core/charts/chart_style.py names
`inter-500.woff2` for the Discord chart PNGs.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "swingbot/admin/static/vendor"
JOST_LATIN = VENDOR / "jost" / "jost-latin-wght-normal.woff2"
JOST_LATIN_EXT = VENDOR / "jost" / "jost-latin-ext-wght-normal.woff2"
JOST_LICENSE = VENDOR / "jost" / "LICENSE.txt"
TRUE_MINUS = 0x2212


def _font(path: Path):
    from fontTools.ttLib import TTFont
    return TTFont(str(path))


def _gsub_features(font) -> set[str]:
    if "GSUB" not in font:
        return set()
    return {record.FeatureTag for record in font["GSUB"].table.FeatureList.FeatureRecord}


def test_brotli_is_installed_so_woff2_can_be_read():
    import brotli  # noqa: F401  (requirements.txt, test-only)


@pytest.mark.parametrize("path", [JOST_LATIN, JOST_LATIN_EXT], ids=lambda p: p.name)
def test_each_jost_subset_is_a_real_woff2(path):
    assert path.is_file(), path
    assert path.stat().st_size > 10_000, path
    assert path.read_bytes()[:4] == b"wOF2", path


def test_the_licence_is_the_sil_ofl_1_1_naming_jost():
    text = JOST_LICENSE.read_text(encoding="utf-8")
    assert "The Jost Project Authors" in text
    assert "SIL Open Font License, Version 1.1" in text


def test_the_latin_subset_carries_tabular_figures():
    assert "tnum" in _gsub_features(_font(JOST_LATIN))


@pytest.mark.parametrize("path", [JOST_LATIN, JOST_LATIN_EXT], ids=lambda p: p.name)
def test_each_subset_is_variable_from_100_to_900(path):
    axes = {axis.axisTag: (axis.minValue, axis.maxValue) for axis in _font(path)["fvar"].axes}
    assert axes.get("wght") == (100, 900)


def test_the_latin_subset_maps_every_digit_and_the_true_minus():
    cmap = _font(JOST_LATIN).getBestCmap()
    for code in [ord(d) for d in "0123456789"] + [TRUE_MINUS]:
        assert code in cmap, hex(code)


def test_the_inter_file_the_discord_charts_name_is_still_vendored():
    assert (VENDOR / "inter" / "inter-500.woff2").is_file()
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/dev/test_vendored_fonts.py`
Expected: FAIL — the Jost files do not exist yet (`AssertionError` on
`path.is_file()`, `FileNotFoundError` on the licence and the font opens).
`test_brotli_is_installed_so_woff2_can_be_read` and the Inter test pass.

- [ ] **Step 4: Vendor the files**

The source is the `@fontsource-variable/jost` 5.3.0 package (SIL OFL 1.1).
It sits in a sibling project's `node_modules` on this machine:

```bash
SRC="/e/Documents/Private/Projects/SystemDesignVisualization/frontend/node_modules/@fontsource-variable/jost"
DEST="/e/Documents/Private/Projects/Discord-Bot/swingbot/admin/static/vendor/jost"
mkdir -p "$DEST"
cp "$SRC/files/jost-latin-wght-normal.woff2" "$DEST/"
cp "$SRC/files/jost-latin-ext-wght-normal.woff2" "$DEST/"
cp "$SRC/LICENSE" "$DEST/LICENSE.txt"
ls -l "$DEST"
```

Expected sizes: 26576 B (latin), 17104 B (latin-ext), 4497 B (licence).
If that directory is missing (a worktree on another machine), fetch the same
package instead: `cd "$(mktemp -d)" && npm pack @fontsource-variable/jost@5.3.0 && tar xzf fontsource-variable-jost-5.3.0.tgz`
and copy from `package/files/` and `package/LICENSE`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/dev/test_vendored_fonts.py`
Expected: PASS, 9 passed (the two parametrised tests count twice each).

- [ ] **Step 6: Commit**

```bash
git add swingbot/admin/static/vendor/jost/ tests/dev/test_vendored_fonts.py requirements.txt
git commit -m "feat(v241): vendor Jost (OFL 1.1) and pin tnum, wght 100-900 and U+2212 in a fontTools test

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V241-2: Jost in `fonts.css` with metric-matched fallbacks; font tokens; JetBrains Mono removed

**Model:** sonnet — several files and a generated fixture move together; the values are all given, but the fixture and two test languages must stay in step.

**Files:**
- Modify: `frontend/src/styles/fonts.css` (whole file replaced)
- Modify: `frontend/src/styles/tokens.css` (the `-- type --` font block, ~lines 209–225)
- Modify: `frontend/src/styles.css` (the `.sb-label` comment, ~lines 113–117)
- Modify: `frontend/src/app/ui/layout.ts` (comment at ~line 116)
- Modify: `frontend/src/app/ui/metric-card.ts` (comment at ~line 112)
- Create: `frontend/src/app/ui/fonts.spec.ts`
- Modify: `frontend/src/app/ui/tokens.spec.ts` (the `v179: one numeric face` describe, ~line 677)
- Modify: `tests/dev/test_vendored_fonts.py` (one test appended)
- Modify: `tests/charts/resolved_tokens.json` (regenerated)
- Delete: `swingbot/admin/static/vendor/jetbrains-mono/` (3 woff2 + `LICENSE.txt`)

**Interfaces:**
- Consumes: the vendored files and `VENDOR`, `ROOT` from V241-1.
- Produces: `--font-sans: "Jost", "Jost Fallback", "Jost Fallback Android", system-ui, sans-serif;`
  and `--font-mono: var(--font-sans);` in the bare `:root`. `--font-num:
  var(--font-mono);` and `--font-figure: var(--font-sans);` are unchanged.
  `.sb-label` keeps `font-family: var(--font-mono)` (pinned by
  `text-styles.spec.ts:20`).

Why: spec v240 §2. `fonts.css` declares `Jost` once per subset (variable,
`font-weight: 100 900`, `font-display: swap`, `unicode-range` verbatim from
the package) and doctena's four metric-matched fallback faces, so a slow
font load does not shift the layout (§8). The tokens change once and no
component changes its `font-family`. JetBrains Mono has no reader once
`fonts.css` drops it, and V241-1's `tnum` test now exists, so its files go
(spec §2 "Owners of the old files"). `vendor/inter/` stays for
`chart_style.py:20`. The bare `:root` font tokens change, so the fixture is
regenerated in this commit.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/ui/fonts.spec.ts`:

```ts
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { stripComments } from './testing/all-sources';
import { resolveToken } from './testing/resolve-token';

/**
 * Spec v240 §2: Jost is the one face of the SPA, self-hosted, with doctena's
 * metric-matched fallback faces. Read as TEXT from process.cwd() (frontend/),
 * like tokens.spec.ts: an Angular `?raw` import of a .css returns a style
 * object, not the source.
 */
const FONTS = stripComments(readFileSync(join(process.cwd(), 'src/styles/fonts.css'), 'utf8'));
const TOKENS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

/** Every @font-face body, in file order. */
const FACES = [...FONTS.matchAll(/@font-face\s*\{([^}]*)\}/g)].map(([, body]) => body);

/** One declaration's value inside a face body, trimmed; undefined when absent. */
const prop = (body: string, name: string) =>
  body.match(new RegExp(`(?:^|[;\\s])${name}:\\s*([^;]+);`))?.[1].trim();

/** Verbatim from @fontsource-variable/jost 5.3.0 wght.css. */
const LATIN =
  'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD';
const LATIN_EXT =
  'U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF';

describe('v240 §2: Jost is the one face', () => {
  const jost = FACES.filter((body) => prop(body, 'font-family') === '"Jost"');

  it('declares six faces: two Jost subsets and four fallbacks', () => {
    expect(FACES).toHaveLength(6);
    expect(jost).toHaveLength(2);
  });

  it.each([
    ['jost-latin-wght-normal.woff2', LATIN],
    ['jost-latin-ext-wght-normal.woff2', LATIN_EXT],
  ])('declares %s as variable 100-900, swap, with its unicode-range', (file, range) => {
    const face = jost.find((body) => body.includes(`/static/vendor/jost/${file}`)) ?? '';
    expect(prop(face, 'src')).toBe(`url("/static/vendor/jost/${file}") format("woff2")`);
    expect(prop(face, 'font-style')).toBe('normal');
    expect(prop(face, 'font-weight')).toBe('100 900');
    expect(prop(face, 'font-display')).toBe('swap');
    expect(prop(face, 'unicode-range')).toBe(range);
  });

  it('declares no Inter and no JetBrains Mono face', () => {
    expect(FONTS).not.toMatch(/Inter|JetBrains/);
  });

  it('points every url() at a vendored file Flask serves from swingbot/admin/static', () => {
    const urls = [...FONTS.matchAll(/url\("([^"]+)"\)/g)].map(([, url]) => url);
    expect(urls).toHaveLength(2);
    for (const url of urls) {
      expect(url.startsWith('/static/vendor/jost/'), url).toBe(true);
      expect(existsSync(join(process.cwd(), '..', 'swingbot/admin', url)), url).toBe(true);
    }
  });
});

/** Spec v240 §2 table, measured from doctena.de's stylesheet 2026-11-23. */
describe('v240 §2: the metric-matched fallback faces', () => {
  const FALLBACKS: [family: string, weight: string, src: string, size: string, ascent: string, descent: string][] = [
    ['"Jost Fallback"', '100 500', 'local("Arial"), local("ArialMT")', '95.87%', '111.61%', '39.12%'],
    ['"Jost Fallback"', '600 900', 'local("Arial Bold"), local("Arial-BoldMT")', '95.49%', '112.06%', '39.27%'],
    ['"Jost Fallback Android"', '100 500', 'local("Roboto"), local("Roboto Regular"), local("Roboto-Regular")', '96.08%', '111.37%', '39.03%'],
    ['"Jost Fallback Android"', '600 900', 'local("Roboto Bold"), local("Roboto-Bold")', '101.36%', '105.57%', '37%'],
  ];

  for (const [family, weight, src, size, ascent, descent] of FALLBACKS) {
    it(`${family} ${weight} matches Jost's metrics`, () => {
      const face = FACES.find((body) => prop(body, 'font-family') === family && prop(body, 'font-weight') === weight) ?? '';
      expect(face, `${family} ${weight}`).not.toBe('');
      expect(prop(face, 'src')).toBe(src);
      expect(prop(face, 'size-adjust')).toBe(size);
      expect(prop(face, 'ascent-override')).toBe(ascent);
      expect(prop(face, 'descent-override')).toBe(descent);
      expect(prop(face, 'line-gap-override')).toBe('0%');
    });
  }
});

describe('v240 §2: the font tokens', () => {
  const SANS = '"Jost", "Jost Fallback", "Jost Fallback Android", system-ui, sans-serif';

  it('sets --font-sans to Jost, then its fallbacks', () => {
    expect(TOKENS).toMatch(/^\s*--font-sans: "Jost", "Jost Fallback", "Jost Fallback Android", system-ui, sans-serif;/m);
    expect(resolveToken('--font-sans')).toBe(SANS);
  });

  it('makes --font-mono an alias of --font-sans: there is no mono face', () => {
    expect(TOKENS).toMatch(/^\s*--font-mono: var\(--font-sans\);/m);
    expect(resolveToken('--font-mono')).toBe(SANS);
  });

  it('leaves --font-num and --font-figure reading those tokens, so no component changes', () => {
    expect(resolveToken('--font-num')).toBe(SANS);
    expect(resolveToken('--font-figure')).toBe(SANS);
  });
});
```

In `frontend/src/app/ui/tokens.spec.ts`, replace the `v179: one numeric face` describe (~lines 676–682) with:

```ts
/** v179 §3.3: every numeric value uses one face, named once. v240 §2: that
 *  face is Jost through --font-mono, which is now an alias of --font-sans. */
describe('v179: one numeric face', () => {
  it('declares --font-num through --font-mono, which resolves to --font-sans', () => {
    expect(CSS).toMatch(/^\s*--font-num:\s*var\(--font-mono\);/m);
    expect(resolveToken('--font-num')).toBe(resolveToken('--font-mono'));
    expect(resolveToken('--font-mono')).toBe(resolveToken('--font-sans'));
  });
});
```

Append to `tests/dev/test_vendored_fonts.py`:

```python
def test_jetbrains_mono_is_gone_with_its_last_reader():
    """Spec v240 §2: fonts.css was its only reader; deleted after the tnum check."""
    assert not (VENDOR / "jetbrains-mono").exists()
    fonts_css = (ROOT / "frontend/src/styles/fonts.css").read_text(encoding="utf-8")
    assert "jetbrains" not in fonts_css.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/fonts.spec.ts --include src/app/ui/tokens.spec.ts`
Expected: FAIL — `fonts.spec.ts` finds seven Inter/JetBrains faces and no
Jost; `tokens.spec.ts` `v179` fails on `--font-mono` ≠ `--font-sans`.

Run: `python scripts/dev/testrun.py file tests/dev/test_vendored_fonts.py`
Expected: FAIL — `test_jetbrains_mono_is_gone_with_its_last_reader`.

- [ ] **Step 3: Replace `frontend/src/styles/fonts.css`**

```css
/* The admin's one family, Jost, declared for the SPA (spec v240 §2).
 *
 * The woff2 files are served by Flask out of `swingbot/admin/static/vendor/`
 * and are NOT bundled: absolute `/static/...` URLs, which the build leaves
 * alone. Zero CDN (spec v13) -- the admin has to work on a box with no
 * outbound internet, so nothing here may reach fonts.googleapis.com.
 *
 * Jost is variable (one file per subset carries every weight 100-900), from
 * @fontsource-variable/jost 5.3.0, SIL OFL 1.1 (vendor/jost/LICENSE.txt).
 * The latin file holds the digits, the `tnum` feature and U+2212;
 * tests/dev/test_vendored_fonts.py pins all three. The old sans and mono
 * faces are no longer declared; vendor/inter/ stays only because
 * swingbot/core/charts/chart_style.py names it for the Discord PNGs.
 *
 * "Jost Fallback" (Arial) and "Jost Fallback Android" (Roboto) are local
 * faces scaled to Jost's metrics, measured from doctena.de's stylesheet on
 * 2026-11-23, so text set in a fallback while Jost loads takes the same box
 * and nothing shifts when Jost swaps in (font-display: swap).
 *
 * Declared here rather than `<link>`-ed from index.html on purpose: the build
 * tries to resolve a `<link rel=stylesheet>` at build time to inline it,
 * cannot find `/static/...` on disk, and warns on every single build -- which
 * is how a project teaches itself to ignore build warnings.
 */

@font-face {
  font-family: "Jost";
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url("/static/vendor/jost/jost-latin-ext-wght-normal.woff2") format("woff2");
  unicode-range: U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF;
}
@font-face {
  font-family: "Jost";
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url("/static/vendor/jost/jost-latin-wght-normal.woff2") format("woff2");
  unicode-range: U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD;
}

@font-face {
  font-family: "Jost Fallback";
  font-style: normal;
  font-weight: 100 500;
  src: local("Arial"), local("ArialMT");
  size-adjust: 95.87%;
  ascent-override: 111.61%;
  descent-override: 39.12%;
  line-gap-override: 0%;
}
@font-face {
  font-family: "Jost Fallback";
  font-style: normal;
  font-weight: 600 900;
  src: local("Arial Bold"), local("Arial-BoldMT");
  size-adjust: 95.49%;
  ascent-override: 112.06%;
  descent-override: 39.27%;
  line-gap-override: 0%;
}
@font-face {
  font-family: "Jost Fallback Android";
  font-style: normal;
  font-weight: 100 500;
  src: local("Roboto"), local("Roboto Regular"), local("Roboto-Regular");
  size-adjust: 96.08%;
  ascent-override: 111.37%;
  descent-override: 39.03%;
  line-gap-override: 0%;
}
@font-face {
  font-family: "Jost Fallback Android";
  font-style: normal;
  font-weight: 600 900;
  src: local("Roboto Bold"), local("Roboto-Bold");
  size-adjust: 101.36%;
  ascent-override: 105.57%;
  descent-override: 37%;
  line-gap-override: 0%;
}
```

The latin-ext face is declared first, as in the fontsource package. The
browser picks a face by `unicode-range`, so the order does not change
rendering.

- [ ] **Step 4: Change the font tokens and the comments that name the old faces**

In `frontend/src/styles/tokens.css`, replace the lines from
`--font-sans: "Inter", ...` through the end of the `v186 D4` comment (the
line before `--font-figure: var(--font-sans);`) with:

```css
  /* v240 §2 -- Jost, self-hosted (styles/fonts.css), is the one face for
     every piece of text, numbers included. The two fallback families are
     local faces scaled to Jost's metrics, so a slow load does not shift the
     layout. --font-mono stays as a name (labels and code samples read it)
     but is an alias now: there is no mono face. */
  --font-sans: "Jost", "Jost Fallback", "Jost Fallback Android", system-ui, sans-serif;
  --font-mono: var(--font-sans);
  /* v179 §3.3 -- the one face for every numeric value (.num, stat values,
     key/value figures). Named separately from --font-mono so a figure says
     "I am a number", not "I am code". Jost is proportional: digits align
     down a column only through `font-variant-numeric: tabular-nums` (its
     tnum feature, pinned by tests/dev/test_vendored_fonts.py), which every
     rule that reads this token sets (v240 §2 gate). */
  --font-num: var(--font-mono);
  /* v186 D4 -- the face for DISPLAY figures: a tile value, a panel total,
     the portfolio hero. Jost 600 with slight negative tracking; each
     figure rule also sets tabular-nums so a count-up does not jitter.
     Columns, N= and table cells keep --font-num so digits align.
     There is no global class: a global .x loses to a component's scoped
     selector, so each component's own figure rule reads these three. */
```

In `frontend/src/styles.css`, rewrite the `.sb-label` comment so it reads:

```css
/* v80 D3 -- the one label style. Eleven files hand-built uppercase labels
 * with four different letter-spacings; this is the single definition every
 * component uses now and every workspace moves to in Migration. Weight 500
 * in --font-mono, which is Jost since v240 (a variable face: every weight
 * exists, nothing is synthesised). */
```

The `.sb-label` rule itself is unchanged.

In `frontend/src/app/ui/layout.ts` (~line 116) change
`sentence case as given, Inter 600.` to `sentence case as given, Jost 600.`

In `frontend/src/app/ui/metric-card.ts` (~lines 112–113) change the comment
tail `v186 D4: Inter 600 like every display figure (was 700` /
`in the code face). */` to `v186 D4: 600 like every display figure (was 700` /
`in the old code face); Jost since v240. */`

- [ ] **Step 5: Delete JetBrains Mono and regenerate the fixture**

```bash
cd /e/Documents/Private/Projects/Discord-Bot
git rm -r -q swingbot/admin/static/vendor/jetbrains-mono
python scripts/dev/dump_tokens.py
python scripts/dev/dump_tokens.py --check
git grep -n -i --untracked "jetbrains" -- frontend swingbot scripts tests
```

Expected: `git grep` prints only the two tests that assert its absence
(`tests/dev/test_vendored_fonts.py` and `frontend/src/app/ui/fonts.spec.ts`);
`--check` exits 0. The fixture's
`font-sans`, `font-mono`, `font-num` and `font-figure` now all read
`"Jost", "Jost Fallback", "Jost Fallback Android", system-ui, sans-serif`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/fonts.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/text-styles.spec.ts`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/dev/test_vendored_fonts.py`
Expected: PASS (10 passed).

Run: `python scripts/dev/testrun.py file tests/dev/test_dump_tokens.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/styles/fonts.css frontend/src/styles/tokens.css frontend/src/styles.css \
  frontend/src/app/ui/layout.ts frontend/src/app/ui/metric-card.ts \
  frontend/src/app/ui/fonts.spec.ts frontend/src/app/ui/tokens.spec.ts \
  tests/dev/test_vendored_fonts.py tests/charts/resolved_tokens.json
git commit -m "feat(v241): Jost with metric-matched fallbacks as the one face; --font-mono aliases --font-sans; JetBrains Mono deleted

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

The `git rm` in Step 5 already staged the JetBrains Mono deletion.

# Phase 2: Colours and the default theme

### Task V241-3: Doctena night palette: `doctena-*` ramp, the 20-token Navy block, `--control-border`, contrast

**Model:** sonnet — token, palette, fixture and two specs move together under exact contrast gates; values are given, but the specs must be rewritten coherently.

**Files:**
- Modify: `frontend/src/styles/palette.css` (header note; `midnight-*`/`frost-*` out, `doctena-*` in; alpha entries)
- Modify: `frontend/src/styles/tokens.css` (`--control-border` in the bare `:root`; the Navy block and its comment; the header is V241-3b)
- Modify: `frontend/src/app/ui/testing/theme-tokens.ts` (`GROUND_INK_TOKENS` → `NAVY_TOKENS`)
- Modify: `frontend/src/app/ui/tokens.spec.ts` (import, `REQUIRED`, the `v225: the Navy ground` describe)
- Modify: `frontend/src/index.html` (the `NAVY_BG` literal and the comment naming its palette entry only)
- Modify: `frontend/src/app/ui/primitives.spec.ts` (the `HEX_ALLOWLIST` `index.html` entry and the three `--midnight-950` pins only)
- Modify: `tests/charts/resolved_tokens.json` (regenerated)

**Interfaces:**
- Consumes: nothing from earlier tasks (runs after V241-2 because both regenerate the fixture).
- Produces:
  - `export const NAVY_TOKENS: readonly string[]` in `frontend/src/app/ui/testing/theme-tokens.ts`,
    exactly `['--bg', '--surface', '--surface-raised', '--surface-overlay', '--overlay-dim', '--border', '--border-strong', '--text', '--text-secondary', '--text-muted', '--text-faint', '--accent', '--accent-fill', '--accent-fill-hi', '--accent-soft', '--control-border', '--pos', '--neg', '--pos-soft', '--neg-soft']`.
    `GROUND_INK_TOKENS` is deleted (its only reader is `tokens.spec.ts`).
  - Token `--control-border`: bare `:root` `var(--border-strong)`, Navy `var(--doctena-blue-600)` (`#0072b0`). V241-6 points controls at it.
  - Palette names and values exactly as in the index's Global Constraints (`--doctena-950` … `--doctena-coral-400-a14`).
  - `index.html` `var NAVY_BG = '#00131f';` (V241-5 rewrites the rest of the script).

Why: spec v240 §1 and its corrections. The Navy block grows from the eleven
ground and ink tokens to twenty: doctena's blue ground and ink, a lifted
accent, the fills, the new control border, mint gains and a lifted coral
for losses, and their 14% tints (without the tints Navy would keep the old
green/red tint under the new hues). The `midnight-*`/`frost-*` ramps lose
their last reader and are deleted. `--text-faint` keeps its divider contract
(corrections): it is held to the non-text 3:1 threshold here, and the text
reads that move to `--text-muted` are V241-9 and part 3. `--control-border`
must clear 3:1 on `--bg` and `--surface` in Navy (WCAG 1.4.11). Black's
value is `--border-strong` (about 1.5:1), a known gap the spec keeps with
Black's colours (index Decision 1), so that gate is Navy-only. Every value
was measured before planning and passes its existing gate (lowest margins:
`--neg` on `--surface-overlay` 4.68:1, `--neg` on its tint over `--surface-raised` 4.62:1,
`--accent` on `--surface-overlay` 4.87:1, `--control-border` on `--surface`
3.28:1). If one fails anyway, move it in `palette.css` (lighter text, darker
fill) and record the new value in the commit message; never lower a
threshold. The bare `:root` gains `--control-border` and the palette
changes, so the fixture is regenerated. The existing `contrast.spec.ts`
gates already run over both themes, so they measure the new Navy values in
this task; V241-3b adds the two new gates (faint as a divider,
`--control-border` at 3:1) and rewrites the `tokens.css` header.

- [ ] **Step 1: Rewrite the tests (they fail)**

In `frontend/src/app/ui/tokens.spec.ts`:

1. Line 6 import becomes:

```ts
import { NAVY_SELECTOR, NAVY_TOKENS, navyRepoints, resolveTokenIn } from './testing/theme-tokens';
```

2. In `REQUIRED`, directly after `'--border-strong',` add `'--control-border',`.

3. Replace the whole `v225: the Navy ground` block (the JSDoc above it
   through its closing `});`, ~lines 368–463) with:

```ts
/**
 * v225, v240: Dark blue (Navy) beside Graphite. One tier-2 block,
 * `:root[data-theme="navy"]`, re-points exactly NAVY_TOKENS -- the ground,
 * ink, accent, control border and P&L tokens -- to the doctena-* palette
 * (spec v240 §1). Every other colour is shared, so a warning, an info chip
 * or a chart series reads the same in both themes.
 */
describe('v240: the Navy block (doctena night)', () => {
  const NAVY: [token: string, palette: string, value: string][] = [
    ['--bg', '--doctena-950', '#00131f'],
    ['--surface', '--doctena-900', '#001e30'],
    ['--surface-raised', '--doctena-850', '#032a42'],
    ['--surface-overlay', '--doctena-800', '#073652'],
    ['--overlay-dim', '--doctena-950-a72', 'rgba(0, 19, 31, 0.72)'],
    ['--border', '--doctena-750', '#0d3d59'],
    ['--border-strong', '--doctena-700', '#1d5373'],
    ['--text', '--doctena-50', '#fafdff'],
    ['--text-secondary', '--doctena-200', '#c8e1ef'],
    ['--text-muted', '--doctena-300', '#8fb3c8'],
    ['--text-faint', '--doctena-500', '#6e94a8'],
    ['--accent', '--doctena-sky-400', '#5aa9d6'],
    ['--accent-fill', '--doctena-blue-600', '#0072b0'],
    ['--accent-fill-hi', '--doctena-blue-700', '#005b8c'],
    ['--accent-soft', '--doctena-blue-500-a24', 'rgba(50, 142, 192, 0.24)'],
    ['--control-border', '--doctena-blue-600', '#0072b0'],
    ['--pos', '--doctena-mint-400', '#53ceb5'],
    ['--neg', '--doctena-coral-400', '#f07a7a'],
    ['--pos-soft', '--doctena-mint-400-a14', 'rgba(83, 206, 181, 0.14)'],
    ['--neg-soft', '--doctena-coral-400-a14', 'rgba(240, 122, 122, 0.14)'],
  ];
  /* Shared by both themes. --quality-3 is absent on purpose: it is
   * var(--text-secondary), so it follows the ink. */
  const SHARED = [
    '--on-accent', '--warn', '--info', '--warn-soft', '--info-soft',
    '--quality-2', '--quality-4',
    '--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5', '--chart-6',
    '--scrim-soft', '--shadow-overlay',
  ];
  /* var() of a re-pointed token, so they follow it into Navy untouched. */
  const FOLLOWERS: [token: string, source: string][] = [
    ['--quality-1', '--neg'], ['--quality-5', '--pos'],
    ['--flash-up-text', '--pos'], ['--flash-down-text', '--neg'],
    ['--btn-fill', '--accent-fill'], ['--btn-fill-hover', '--accent-fill-hi'],
    ['--scrim', '--overlay-dim'],
  ];
  const NAVY_OPEN = /^:root\[data-theme="navy"\] \{/m;
  const block = CSS.slice(CSS.search(NAVY_OPEN)).match(/\{([^}]*)\}/)?.[1] ?? '';
  const PALETTE = readFileSync(join(process.cwd(), 'src/styles/palette.css'), 'utf8');

  it('declares one Navy block, after the tier-2 ground and before the tier-3 banner', () => {
    expect(NAVY_SELECTOR).toBe(':root[data-theme="navy"]');
    expect(stripComments(CSS).match(/:root\[data-theme="navy"\]/g)).toHaveLength(1);
    const at = CSS.search(NAVY_OPEN);
    expect(at).toBeGreaterThan(CSS.search(/^\s*--text-faint:\s*var\(--graphite-500\);/m));
    expect(at).toBeLessThan(CSS.indexOf(TIER3_BANNER));
  });

  it('re-points exactly NAVY_TOKENS, in that order, and every one of them', () => {
    expect([...NAVY_TOKENS]).toEqual(NAVY.map(([name]) => name));
    expect(Object.keys(navyRepoints())).toEqual([...NAVY_TOKENS]);
  });

  for (const [name, palette, value] of NAVY) {
    it(`${name} re-points to ${palette}, which is ${value}`, () => {
      expect(navyRepoints()[name]).toBe(`var(${palette})`);
      expect(resolveToken(palette)).toBe(value);
      expect(resolveTokenIn('navy', name)).toBe(value);
    });

    it(`${name} stays Graphite outside the Navy block`, () => {
      expect(resolveTokenIn('graphite', name)).toBe(resolveToken(name));
      expect(resolveToken(name)).not.toBe(value);
    });
  }

  it('holds var() references only, never a literal', () => {
    expect(block).not.toBe('');
    expect(stripComments(block)).not.toMatch(/#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?)\(/i);
  });

  it.each(SHARED)('%s resolves the same in both themes', (name) => {
    expect(resolveTokenIn('navy', name)).toBe(resolveToken(name));
  });

  it.each(FOLLOWERS)('%s follows %s into Navy', (name, source) => {
    expect(resolveTokenIn('navy', name)).toBe(resolveTokenIn('navy', source));
  });

  it('gives Black a --control-border equal to its strong hairline, so Black controls look as before', () => {
    expect(CSS).toMatch(/^\s*--control-border:\s*var\(--border-strong\);/m);
    expect(resolveToken('--control-border')).toBe(resolveToken('--border-strong'));
  });

  it('carries tier-3 tokens built on the ground over to Navy', () => {
    expect(resolveTokenIn('navy', '--panel-bg')).toBe('#001e30');
  });

  it('deletes the v225 midnight and frost ramps: nothing reads them', () => {
    expect(PALETTE).toMatch(/^\s*--doctena-950:\s*#00131f;/m);
    for (const source of [stripComments(CSS), stripComments(PALETTE)]) {
      expect(source).not.toMatch(/--(?:midnight|frost)-\d/);
    }
    for (const { name, source } of allSources()) {
      expect(stripComments(source), name).not.toMatch(/--(?:midnight|frost)-\d/);
    }
  });

  it('keeps the Arctic Navy guard clean of the new palette names', () => {
    for (const source of [CSS, PALETTE, block]) {
      expect(source).not.toMatch(/--(?:navy|slate|sky|teal)-\d/);
    }
  });

  it('states the ground/ink rule in the tokens.css header', () => {
    const header = CSS.slice(0, CSS.indexOf(':root {'));
    expect(header).toMatch(/ground and ink/i);
    expect(header).toContain('data-theme');
    expect(header).toContain('v225');
    expect(header).toMatch(/no light theme/i);
  });
});
```

In `frontend/src/app/ui/primitives.spec.ts`:

1. The `HEX_ALLOWLIST` entry becomes (comment above it unchanged):

```ts
  ['index.html', ['#0d0f12', '#00131f', '#0d0f12']],
```

2. In `describe('the Dark blue cold load (v225)')`, the first test becomes:

```ts
  it('holds the Navy --bg once, equal to the resolved --doctena-950 and Navy --bg', () => {
    const literal = script.match(/var NAVY_BG = '([^']+)';/)?.[1].toLowerCase();
    expect(literal).toBe(resolveToken('--doctena-950').toLowerCase());
    expect(literal).toBe(resolveTokenIn('navy', '--bg').toLowerCase());
    expect(script.match(/#[0-9a-f]{6}/gi)).toHaveLength(1);
  });
```

3. In `'paints Navy when ui.theme is navy: attribute, meta and a scoped ground'`,
   replace both `resolveToken('--midnight-950')` with `resolveToken('--doctena-950')`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/primitives.spec.ts`
Expected: FAIL — `NAVY_TOKENS` is not exported yet, so the `tokens.spec.ts`
Navy-block tests throw on an undefined list; `primitives.spec.ts` fails on `--doctena-950`
(not a token yet) and the `#00131f` allowlist entry.

- [ ] **Step 3: Rename the token list in `theme-tokens.ts`**

In `frontend/src/app/ui/testing/theme-tokens.ts`, replace the
`GROUND_INK_TOKENS` JSDoc and constant with:

```ts
/**
 * The tokens the Navy block re-points, in tokens.css order: the ground and
 * ink (v225), then the accent, the control border and P&L (v240 §1). Every
 * other token is shared by both themes (tokens.css header).
 */
export const NAVY_TOKENS: readonly string[] = [
  '--bg', '--surface', '--surface-raised', '--surface-overlay', '--overlay-dim',
  '--border', '--border-strong', '--text', '--text-secondary', '--text-muted', '--text-faint',
  '--accent', '--accent-fill', '--accent-fill-hi', '--accent-soft',
  '--control-border', '--pos', '--neg', '--pos-soft', '--neg-soft',
];
```

Run `cd frontend && git grep -n "GROUND_INK_TOKENS" -- src` — expected: no output.

- [ ] **Step 4: Replace the Navy ramps in `palette.css`**

In the header comment of `frontend/src/styles/palette.css`, replace
`literal in tokens.css, and index.html / manifest.webmanifest carry copies`
/ `of --bg for the cold load, and index.html one of the Navy --bg (spec v225)).`
with:

```css
 * literal in tokens.css, and index.html / manifest.webmanifest carry copies
 * of the two grounds for the cold load (spec v225, v240; primitives.spec.ts
 * pins each copy to its palette entry)).
```

Delete the `v225 Dark blue (Navy) ground` group (`--midnight-950` …
`--midnight-500` and its two comments) and the `v225 Navy ink` group
(`--frost-400`, `--frost-300`, `--frost-100` and its comment). In their
place, directly after `--graphite-500: #6b7280;`, add:

```css

  /* v240 doctena night, the Dark blue (Navy) look, darkest first.
     tokens.css's :root[data-theme="navy"] block re-points the ground, ink,
     accent, control border and P&L tokens to these. Hues from doctena.de,
     lifted where a contrast gate needed it (spec v240 §1). */
  --doctena-950: #00131f;
  --doctena-900: #001e30;
  --doctena-850: #032a42;
  --doctena-800: #073652;
  --doctena-750: #0d3d59;
  --doctena-700: #1d5373;
  /* rules, dividers and disabled glyphs only -- never text */
  --doctena-500: #6e94a8;
  --doctena-300: #8fb3c8;
  --doctena-200: #c8e1ef;
  --doctena-50: #fafdff;
  /* doctena blue: sky-400 is the text-safe accent (doctena's #328ec0 is
     4.1:1 on the raised surface); blue-600 and blue-700 are the fills
     under white ink (5.21:1 and 7.30:1) and blue-600 the control border. */
  --doctena-sky-400: #5aa9d6;
  --doctena-blue-600: #0072b0;
  --doctena-blue-700: #005b8c;
  /* doctena mint for gains; a coral lifted from doctena's error #c52020
     so a loss reads on a dark ground */
  --doctena-mint-400: #53ceb5;
  --doctena-coral-400: #f07a7a;
```

In the `alpha entries` group, replace the line
`--midnight-950-a72: rgba(7, 12, 24, 0.72);` with:

```css
  --doctena-950-a72: rgba(0, 19, 31, 0.72);
  --doctena-blue-500-a24: rgba(50, 142, 192, 0.24);
  --doctena-mint-400-a14: rgba(83, 206, 181, 0.14);
  --doctena-coral-400-a14: rgba(240, 122, 122, 0.14);
```

(`#328ec0` is doctena's blue-500, the accent-soft hue; it has no solid
entry because nothing paints it at full alpha.)

- [ ] **Step 5: Add `--control-border` and rewrite the Navy block in `tokens.css`**

In the bare `:root`, directly after `--border-strong: var(--graphite-700);`, add:

```css
  /* v240 §1 -- the outline of inputs, selects and segmented controls, a
   * UI component that WCAG 1.4.11 wants at 3:1 against its ground. Black
   * keeps its strong hairline (about 1.5:1, a known gap the spec keeps
   * with Black's colours); Navy re-points it to doctena blue, 3.28:1 on
   * --surface. --border stays the decorative panel and rule colour. */
  --control-border: var(--border-strong);
```

Replace the comment above the Navy block and the block itself with:

```css
/* v225, v240 -- the Dark blue (Navy) look, "doctena night" (spec v240 §1).
 * Re-points exactly the twenty tokens named in the header to the doctena-*
 * palette and nothing else; var() references only, the hues live in
 * palette.css. Outside the bare :root on purpose -- dump_tokens.py and
 * resolve-token.ts read only `:root`, so the fixture and the Discord PNGs
 * stay Graphite. Never write this selector as part of a `:root, ...` list,
 * and never put a closing brace in a comment inside it
 * (tests/dev/test_dump_tokens.py reads the block up to the first one). */
:root[data-theme="navy"] {
  --bg: var(--doctena-950);
  --surface: var(--doctena-900);
  --surface-raised: var(--doctena-850);
  --surface-overlay: var(--doctena-800);
  --overlay-dim: var(--doctena-950-a72);
  --border: var(--doctena-750);
  --border-strong: var(--doctena-700);
  --text: var(--doctena-50);
  --text-secondary: var(--doctena-200);
  --text-muted: var(--doctena-300);
  --text-faint: var(--doctena-500);
  --accent: var(--doctena-sky-400);
  --accent-fill: var(--doctena-blue-600);
  --accent-fill-hi: var(--doctena-blue-700);
  --accent-soft: var(--doctena-blue-500-a24);
  --control-border: var(--doctena-blue-600);
  --pos: var(--doctena-mint-400);
  --neg: var(--doctena-coral-400);
  --pos-soft: var(--doctena-mint-400-a14);
  --neg-soft: var(--doctena-coral-400-a14);
}
```

- [ ] **Step 6: Re-point the pre-paint script literal in `index.html`**

In `frontend/src/index.html`, change `var NAVY_BG = '#070c18';` to
`var NAVY_BG = '#00131f';`, and in the comment above the script change
`NAVY_BG is a copy of palette.css` / `--midnight-950; primitives.spec.ts pins it.`
to `NAVY_BG is a copy of palette.css` / `--doctena-950; primitives.spec.ts pins it.`
Nothing else in `index.html` changes in this task (V241-5 rewrites the cold load).

- [ ] **Step 7: Regenerate the fixture**

```bash
cd /e/Documents/Private/Projects/Discord-Bot
python scripts/dev/dump_tokens.py
python scripts/dev/dump_tokens.py --check
git diff --stat tests/charts/resolved_tokens.json
```

Expected: `--check` exits 0. The diff adds `control-border` and the
nineteen `doctena-*` entries and removes the eleven `midnight-*`/`frost-*`
entries; no Graphite tier-2 colour changes.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/theme.service.spec.ts`
Expected: PASS. If a contrast case fails, move that palette value (lighter
text, darker fill) until it passes, update the `NAVY` row, regenerate the
fixture, and name the new value in the commit message.

Run: `python scripts/dev/testrun.py file tests/dev/test_dump_tokens.py`
Expected: PASS (the Navy block is still invisible to the resolver).

Run: `python scripts/dev/testrun.py file tests/charts/test_chart_theme.py`
Expected: PASS (Graphite, and so the Discord PNG colours, unchanged).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/styles/palette.css frontend/src/styles/tokens.css \
  frontend/src/app/ui/testing/theme-tokens.ts frontend/src/app/ui/tokens.spec.ts \
  frontend/src/index.html \
  frontend/src/app/ui/primitives.spec.ts tests/charts/resolved_tokens.json
git commit -m "feat(v241): doctena night -- the 20-token Navy block, --control-border, doctena-* palette; midnight/frost deleted

All Navy values pass their existing gates as specified (no value moved).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V241-3b: Contrast gates for the divider and the control border; the tokens.css header names the Navy list

**Model:** haiku — two table-driven contrast gates, one header assertion and a comment rewrite, all given verbatim; no value changes.

**Files:**
- Modify: `frontend/src/app/ui/contrast.spec.ts` (faint divider gate, `--control-border` gate, tint comment)
- Modify: `frontend/src/app/ui/tokens.spec.ts` (the header test in `v240: the Navy block (doctena night)`)
- Modify: `frontend/src/styles/tokens.css` (the header comment, lines 7–27, only)

**Interfaces:**
- Consumes: `--control-border`, the 20-token Navy block and `NAVY_TOKENS` from V241-3; `resolveTokenIn`, `TOKEN_THEMES` from `frontend/src/app/ui/testing/theme-tokens.ts`.
- Produces: nothing a later task consumes.

Why: split from V241-3 to keep each task under 20 KB. Spec v240 §1 and its
corrections: `--text-faint` keeps its divider contract, so it is held to the
non-text 3:1 threshold (WCAG 1.4.11) on all four surfaces, in both themes
(measured: Navy 3.90:1 at worst, on `--surface-overlay`; Graphite 3.23:1).
`--control-border` must clear 3:1 on `--bg` (3.62:1) and `--surface`
(3.28:1) in Navy. That gate is Navy-only: Black's value is `--border-strong`,
about 1.5:1, a known gap the spec keeps with Black's colours (index
Decision 1). The `tokens.css` header still says "eleven ground and ink
tokens". It is rewritten to name the twenty-token Navy list, and the tokens
spec pins `v240` and `--control-border` in it. The header is a comment, so
the fixture does not change.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/contrast.spec.ts`:

1. Inside the `for (const theme of TOKEN_THEMES)` loop, after the `v181`
   describe, add:

```ts
  /**
   * v240 §1: --text-faint stays a rule and divider colour (never text), held
   * to the non-text threshold of WCAG 1.4.11 on every surface. Doctena's
   * #4B748A was lifted to #6E94A8 so dividers read on all four in Navy.
   */
  describe(`--text-faint reads as a divider on every surface (${theme})`, () => {
    for (const bg of SURFACES) {
      it(`--text-faint on ${bg} clears 3:1`, () => {
        expect(ratio(tok('--text-faint'), tok(bg))).toBeGreaterThanOrEqual(3);
      });
    }
  });
```

2. In the `v181` describe, replace the comment line
   `// --neg on --neg-soft over --surface-overlay is 4.48:1 in both themes (spec v225 § Palette): out of scope, not gated.`
   with
   `// --neg on --neg-soft over --surface-overlay is 4.48:1 (Graphite) and about 4.1:1 (Navy, spec v240 §1): out of scope, not gated.`

3. After the closing `}` of the theme loop (before the `V186_FILES` JSDoc), add:

```ts
/**
 * v240 §1: --control-border outlines inputs, selects and segmented controls,
 * so it is a non-text UI component colour and needs 3:1 against the ground
 * it sits on (WCAG 1.4.11). Navy only (index Decision 1): Black keeps its
 * strong hairline (about 1.5:1), a known gap the spec keeps with Black's
 * colours.
 */
describe('v240: --control-border clears 3:1 (navy)', () => {
  for (const bg of ['--bg', '--surface']) {
    it(`--control-border on ${bg} clears 3:1`, () => {
      expect(ratio(resolveTokenIn('navy', '--control-border'), resolveTokenIn('navy', bg))).toBeGreaterThanOrEqual(3);
    });
  }

  it('is the strong hairline under Black, so Black controls look as before', () => {
    expect(resolveTokenIn('graphite', '--control-border')).toBe(resolveTokenIn('graphite', '--border-strong'));
  });
});
```

In `frontend/src/app/ui/tokens.spec.ts`, inside
`describe('v240: the Navy block (doctena night)', ...)`, replace the test
`'states the ground/ink rule in the tokens.css header'` (written by V241-3) with:

```ts
  it('states the Navy rule in the tokens.css header', () => {
    const header = CSS.slice(0, CSS.indexOf(':root {'));
    expect(header).toMatch(/ground and ink/i);
    expect(header).toContain('data-theme');
    expect(header).toContain('v225');
    expect(header).toContain('v240');
    expect(header).toContain('--control-border');
    expect(header).toMatch(/twenty tokens/i);
    expect(header).toMatch(/no light theme/i);
  });
```

- [ ] **Step 2: Run them to see which fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/contrast.spec.ts --include src/app/ui/tokens.spec.ts`
Expected: the header test FAILS (no `v240`, `--control-border` or "twenty
tokens" in the header yet). The new contrast gates PASS at once, because
V241-3 already set values that clear them. If a contrast gate fails, move
that palette value in `palette.css` (a lighter divider, a lighter control
border), update its `NAVY` row in `tokens.spec.ts`, run
`python scripts/dev/dump_tokens.py`, stage `palette.css` and
`tests/charts/resolved_tokens.json` with this commit, and name the new value
in the commit message. Never lower the threshold.

- [ ] **Step 3: Rewrite the tokens.css header**

In the `frontend/src/styles/tokens.css` header comment (lines 7–27), replace the paragraph from
`**Dark only. Two dark grounds, no light theme**` through
`gets its Navy value in the same commit (tokens.spec.ts checks both ways).`
with:

```css
 * **Dark only. Two dark looks, no light theme** (spec v225,
 * docs/superpowers/specs/2026-11-10-v225-dark-blue-theme-design.md, and
 * spec v240, docs/superpowers/specs/2026-11-23-v240-doctena-night-restyle-design.md):
 * Black (Graphite, the bare :root below) and Dark blue (Navy, "doctena
 * night"), selected by <html data-theme="navy">. In CSS, no attribute or
 * any other value is Graphite; ui/theme.service.ts writes the attribute,
 * and spec v240 makes Navy the default look. There is
 * still no light theme and no `prefers-color-scheme` block.
 *
 * The Navy list is named, twenty tokens: the ground and ink (--bg,
 * --surface, --surface-raised, --surface-overlay, --overlay-dim, --border,
 * --border-strong, --text, --text-secondary, --text-muted, --text-faint),
 * then the accent (--accent, --accent-fill, --accent-fill-hi,
 * --accent-soft), --control-border, and P&L (--pos, --neg, --pos-soft,
 * --neg-soft). Every token on that list has a Navy value in the
 * :root[data-theme="navy"] block; every token off it is shared by both
 * themes. A token joins the list with its Navy value in the same commit
 * (tokens.spec.ts and ui/testing/theme-tokens.ts NAVY_TOKENS check both ways).
```

Keep the rest of the header (the Discord chart paragraph) as it is.

- [ ] **Step 4: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/contrast.spec.ts --include src/app/ui/tokens.spec.ts`
Expected: PASS.

Run: `python scripts/dev/dump_tokens.py --check`
Expected: exit 0 (a comment-only change to `tokens.css`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/contrast.spec.ts frontend/src/app/ui/tokens.spec.ts frontend/src/styles/tokens.css
git commit -m "test(v241): --text-faint held to 3:1 as a divider in both themes, --control-border to 3:1 in Navy; tokens.css header names the Navy list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V241-4: Navy is the default at runtime: `readTheme`, profile menu, shell and palette specs

**Model:** sonnet — a one-line logic inversion whose ripple runs through six spec files; each flipped expectation must be rewritten, not deleted.

**Files:**
- Modify: `frontend/src/app/ui/theme.service.ts` (`readTheme` and two doc comments)
- Modify: `frontend/src/app/ui/theme.service.spec.ts`
- Modify: `frontend/src/app/shell/profile-menu.ts` (`THEME_OPTIONS` order, `theme` input default, `onTheme`)
- Modify: `frontend/src/app/shell/profile-menu.spec.ts` (`Theme control (v225)` describe)
- Modify: `frontend/src/app/shell/shell.spec.ts` (~lines 845–870 and 942–981)
- Modify: `frontend/src/app/shell/palette/command-palette.spec.ts` (~lines 222–241)
- Modify: `frontend/src/app/ui/chart/trade-chart.spec.ts` (the two `THEME_STORAGE` stubs, lines 38 and 81)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts` (the `THEME_STORAGE` stub, line 41)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `readTheme(storage: ThemeStorage): Theme` returns `'graphite'`
  only for a stored value of exactly `'graphite'`, otherwise `'navy'`
  (missing, junk, or a throwing storage). `ProfileMenu.theme = input<Theme>('navy')`.
  `THEME_OPTIONS` lists Dark blue first; the labels stay `Black` / `Dark blue`.
  V241-5's pre-boot script mirrors this rule.

Why: spec v240 §1 "Navy is the default" and §8: anything but exactly
`'graphite'` is Navy, so a browser that never chose opens in doctena night
and one that explicitly chose Black keeps Black. A junk stored value is
still not rewritten until the user chooses. The profile menu lists Dark blue
first because it is now the default. `ThemeService.toggle()` is symmetric
and does not change.

Two chart specs (`trade-chart.spec.ts`, `equity-candles.spec.ts`) stub
`THEME_STORAGE.get` to `null` and then flip to Navy, expecting a repaint.
Under the new default they would already start in Navy, the flip would be a
no-op and the repaint assertions would fail. Their stubs return `'graphite'`
so they keep testing a Black-to-Navy flip. (These two files are not in the
index ledger row; the controller adds them to it.)

- [ ] **Step 1: Rewrite the `readTheme` and `ThemeService` specs (they fail)**

In `frontend/src/app/ui/theme.service.spec.ts`, replace the
`describe('readTheme (v225)', ...)`, `describe('ThemeService (v225)', ...)`
and `describe('the default storage is localStorage, guarded', ...)` blocks
with:

```ts
describe('readTheme (v225, v240: Navy is the default)', () => {
  it('defaults to navy when nothing is stored', () => {
    expect(readTheme(new MapStorage())).toBe('navy');
  });

  it('restores a stored graphite (Black) choice', () => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, 'graphite');
    expect(readTheme(storage)).toBe('graphite');
  });

  it('restores a stored navy choice', () => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, 'navy');
    expect(readTheme(storage)).toBe('navy');
  });

  it.each(['GRAPHITE', 'graphite ', ' graphite', '', 'black', 'dark', '{"theme":"graphite"}'])('reads %j as navy', (value) => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, value);
    expect(readTheme(storage)).toBe('navy');
  });

  it('falls back to navy when the storage throws', () => {
    expect(readTheme(refusing)).toBe('navy');
  });

  it('stores under the per-browser key ui.theme', () => {
    expect(THEME_PREF_KEY).toBe('ui.theme');
  });
});

describe('ThemeService (v225, v240)', () => {
  it('writes data-theme="navy" at construction when nothing is stored, and paints the meta Navy', () => {
    serviceWith(new MapStorage());
    expect(attribute()).toBe('navy');
    expect(meta.content).toBe(resolveTokenIn('navy', '--bg'));
  });

  it('restores a stored graphite choice onto <html> and the theme-color meta', () => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, 'graphite');
    const service = serviceWith(storage);
    expect(service.theme()).toBe('graphite');
    expect(attribute()).toBe('graphite');
    expect(meta.content).toBe(resolveToken('--bg'));
  });

  it('set() moves the signal, the attribute, the stored key and the meta together', () => {
    const storage = new MapStorage();
    const service = serviceWith(storage);
    service.set('graphite');
    expect([service.theme(), attribute(), storage.map.get(THEME_PREF_KEY)]).toEqual(['graphite', 'graphite', 'graphite']);
    expect(meta.content).toBe(resolveToken('--bg'));
    service.set('navy');
    expect([service.theme(), attribute(), storage.map.get(THEME_PREF_KEY)]).toEqual(['navy', 'navy', 'navy']);
    expect(meta.content).toBe(resolveTokenIn('navy', '--bg'));
  });

  it('toggle() flips between the two themes, starting from Navy', () => {
    const service = serviceWith(new MapStorage());
    service.toggle();
    expect(service.theme()).toBe('graphite');
    service.toggle();
    expect(service.theme()).toBe('navy');
  });

  it('does not rewrite a junk stored value until the user chooses', () => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, 'GRAPHITE');
    const service = serviceWith(storage);
    expect(service.theme()).toBe('navy');
    expect(storage.map.get(THEME_PREF_KEY)).toBe('GRAPHITE');
  });

  it('starts navy, and still switches for the page life, when storage refuses both calls', () => {
    const service = serviceWith(refusing);
    expect(service.theme()).toBe('navy');
    expect(() => service.set('graphite')).not.toThrow();
    expect(service.theme()).toBe('graphite');
    expect(attribute()).toBe('graphite');
  });

  it('switches without a theme-color meta in the document', () => {
    meta.remove();
    const service = serviceWith(new MapStorage());
    expect(() => service.set('graphite')).not.toThrow();
    expect(attribute()).toBe('graphite');
  });
});

describe('the default storage is localStorage, guarded', () => {
  it('reads and writes ui.theme through localStorage', () => {
    localStorage.setItem(THEME_PREF_KEY, 'graphite');
    const service = serviceWith();
    expect(service.theme()).toBe('graphite');
    service.set('navy');
    expect(localStorage.getItem(THEME_PREF_KEY)).toBe('navy');
  });

  it('falls back to navy and keeps working when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('denied', 'SecurityError'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError'); });
    const service = serviceWith();
    expect(service.theme()).toBe('navy');
    service.set('graphite');
    expect(attribute()).toBe('graphite');
  });
});
```

The file's helpers, `beforeEach`/`afterEach` and the
`the app boots the theme service` describe stay as they are.

- [ ] **Step 2: Rewrite the profile-menu, shell and palette expectations (they fail)**

In `frontend/src/app/shell/profile-menu.spec.ts`, inside
`describe('Theme control (v225)', ...)`:

1. In `'offers Black and Dark blue under the label "Theme"'`, rename it to
   `'offers Dark blue and Black under the label "Theme", the default first'`
   and change the segment assertion to
   `expect(segments().map((b) => b.textContent!.trim())).toEqual(['Dark blue', 'Black']);`
2. Replace `'defaults to Black and marks the theme it is given'` with:

```ts
    it('defaults to Dark blue and marks the theme it is given', () => {
      openMenu();
      expect(pressed()).toBe('Dark blue');
      fixture.componentRef.setInput('theme', 'graphite');
      fixture.detectChanges();
      expect(pressed()).toBe('Black');
    });
```

3. In `'emits the chosen theme and keeps the menu open'`, change
   `expect(chosen).toEqual(['navy', 'graphite']);` to
   `expect(chosen).toEqual(['graphite', 'navy']);` (segment 1 is Black now,
   segment 0 Dark blue; the clicks stay `segments()[1]` then `segments()[0]`).
4. Replace `'reads anything but navy as graphite: ...'` with:

```ts
    it('reads anything but graphite as navy: the segmented control hands back a string', () => {
      const chosen: string[] = [];
      fixture.componentInstance.themeChanged.subscribe((theme) => chosen.push(theme));
      for (const value of ['graphite', 'GRAPHITE', 'graphite ', '', 'dark', 'navy']) fixture.componentInstance['onTheme'](value);
      expect(chosen).toEqual(['graphite', 'navy', 'navy', 'navy', 'navy', 'navy']);
    });
```

In `frontend/src/app/shell/shell.spec.ts`, replace the test
`'toggles Dark blue from the bar: aria-pressed, data-theme and ui.theme move together'`
with the version below, and add the Black test directly after the existing
`'starts pressed when this browser stored Dark blue'` test (which stays):

```ts
  it('toggles Dark blue from the bar: aria-pressed, data-theme and ui.theme move together', async () => {
    const { fixture, el } = await mount();
    const button = themeButton(el);
    expect(button.getAttribute('aria-label')).toBe('Dark blue theme');
    // v240: Dark blue is the default, so the bar starts pressed.
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(html.dataset['theme']).toBe('navy');

    button.click();
    await settle(fixture);
    expect(button.getAttribute('aria-pressed')).toBe('false');
    expect(html.dataset['theme']).toBe('graphite');
    expect(stored.get('ui.theme')).toBe('graphite');
    expect(button.getAttribute('aria-label')).toBe('Dark blue theme');

    button.click();
    await settle(fixture);
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(html.dataset['theme']).toBe('navy');
    expect(stored.get('ui.theme')).toBe('navy');
  });
```

```ts
  it('starts unpressed when this browser stored Black', async () => {
    stored.set('ui.theme', 'graphite');
    const { el } = await mount();
    expect(themeButton(el).getAttribute('aria-pressed')).toBe('false');
    expect(html.dataset['theme']).toBe('graphite');
  });
```

In the same file, inside `describe('v225: one theme across the bar button and the profile menu', ...)`,
replace the three tests with:

```ts
  it('writes ui.theme and data-theme from the menu row, and the bar button follows', async () => {
    const { fixture, el } = await mount();
    expect(html.dataset['theme']).toBe('navy');
    await openMenu(fixture, el);
    segment(el, 'Black').click();
    await settle(fixture);
    expect(html.dataset['theme']).toBe('graphite');
    expect(stored.get('ui.theme')).toBe('graphite');
    expect(pressedSegment(el)).toBe('Black');
    expect(barButton(el)!.getAttribute('aria-pressed')).toBe('false');
  });

  it('moves the pressed segment when the bar button is clicked, and the bar when the menu is', async () => {
    const { fixture, el } = await mount();
    await openMenu(fixture, el);
    expect(pressedSegment(el)).toBe('Dark blue');
    barButton(el)!.click();
    await settle(fixture);
    expect(html.dataset['theme']).toBe('graphite');
    // A click outside the menu closes it (ProfileMenu's document click); reopen to read it.
    if (!el.querySelector('sb-profile-menu [role=menu]')) await openMenu(fixture, el);
    expect(pressedSegment(el)).toBe('Black');
    segment(el, 'Dark blue').click();
    await settle(fixture);
    expect(barButton(el)!.getAttribute('aria-pressed')).toBe('true');
    expect(stored.get('ui.theme')).toBe('navy');
  });

  it('keeps the Theme row on a phone, where it is the only switch', async () => {
    TestBed.overrideProvider(ViewportService, {
      useValue: { isPhone: signal(true), isNarrow: signal(true), viewport: signal('xs') },
    });
    const { fixture, el } = await mount();
    expect(barButton(el)).toBeNull();
    await openMenu(fixture, el);
    segment(el, 'Black').click();
    await settle(fixture);
    expect(html.dataset['theme']).toBe('graphite');
    expect(stored.get('ui.theme')).toBe('graphite');
  });
```

In `frontend/src/app/shell/palette/command-palette.spec.ts`, replace
`'switches the theme in place, without navigating, and back again'` with:

```ts
  it('switches the theme in place, without navigating, and back again', async () => {
    const { fixture, el, host } = await mount();
    const router = TestBed.inject(Router);
    const before = router.url;
    await type(fixture, el, 'theme');
    expect(optionLabels(el)).toEqual(['Switch theme']);
    await press(fixture, el, 'Enter');
    // v240: Dark blue is the default, so the first switch goes to Black.
    expect(document.documentElement.dataset['theme']).toBe('graphite');
    expect(stored.get('ui.theme')).toBe('graphite');
    expect(router.url).toBe(before);
    expect(host.closes).toBe(1);

    host.open.set(true);
    await settle(fixture);
    await type(fixture, el, 'switch');
    await press(fixture, el, 'Enter');
    expect(document.documentElement.dataset['theme']).toBe('navy');
    expect(stored.get('ui.theme')).toBe('navy');
    expect(host.closes).toBe(2);
  });
```

In `frontend/src/app/ui/chart/trade-chart.spec.ts` (lines 38 and 81) and
`frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`
(line 41), change the stub
`{ provide: THEME_STORAGE, useValue: { get: () => null, set: () => {} } }` to
`{ provide: THEME_STORAGE, useValue: { get: () => 'graphite', set: () => {} } }`
and put this comment on the line above each one:
`// Start in Black: Navy is the default since v240, and these specs flip to Navy.`

- [ ] **Step 3: Run the specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/theme.service.spec.ts --include src/app/shell/profile-menu.spec.ts --include src/app/shell/shell.spec.ts --include src/app/shell/palette/command-palette.spec.ts`
Expected: FAIL — every rewritten default-theme expectation (navy expected,
graphite received; segment order `['Black', 'Dark blue']`).

- [ ] **Step 4: Invert the default in `theme.service.ts`**

In `frontend/src/app/ui/theme.service.ts`, replace the last paragraph of the
file JSDoc (`Anything unreadable is Graphite, and a junk stored value is not rewritten`
/ `until the user chooses.`) with:

```ts
 * Navy is the default since v240 (spec 2026-11-23-v240-doctena-night-restyle-design.md
 * §1): only the exact stored string `graphite` is Black. A missing, junk or
 * unreadable value is Navy, and a junk stored value is not rewritten until
 * the user chooses. index.html's pre-paint script applies the same rule.
```

Replace `readTheme` and its doc comment with:

```ts
/** Graphite only for the exact stored string `graphite`; everything else, a throwing storage included, is Navy (v240). */
export function readTheme(storage: ThemeStorage): Theme {
  try { return storage.get(THEME_PREF_KEY) === 'graphite' ? 'graphite' : 'navy'; } catch { return 'navy'; }
}
```

- [ ] **Step 5: Put Dark blue first in the profile menu**

In `frontend/src/app/shell/profile-menu.ts`, replace `THEME_OPTIONS` and its
comment with:

```ts
/** The two grounds, in the order the control shows them: Dark blue first,
 *  since it is the default (spec v240 §1). The stored values stay
 *  `graphite` | `navy`; the labels are what a user reads. */
const THEME_OPTIONS: SegmentOption[] = [
  { value: 'navy', label: 'Dark blue' },
  { value: 'graphite', label: 'Black' },
];
```

Replace the `theme` input line and `onTheme` (with their comments) with:

```ts
  /** The current ground, owned by the shell's ThemeService (spec v225); Navy by default (v240). */
  readonly theme = input<Theme>('navy');
```

```ts
  /** Validated, not trusted: anything but exactly 'graphite' is the default, Navy (v240). */
  protected onTheme(value: string): void {
    this.themeChanged.emit(value === 'graphite' ? 'graphite' : 'navy');
  }
```

(`readonly themeChanged = output<Theme>();` and `themeOptions` between them stay.)

- [ ] **Step 6: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/theme.service.spec.ts --include src/app/shell/profile-menu.spec.ts --include src/app/shell/shell.spec.ts --include src/app/shell/palette/command-palette.spec.ts --include src/app/ui/chart/trade-chart.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts`
Expected: PASS.

Then confirm no other spec reads the old default:
`cd frontend && git grep -n "THEME_STORAGE, useValue" -- src`
Expected: only the files above (shell, palette, chart and candle specs).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/theme.service.ts frontend/src/app/ui/theme.service.spec.ts \
  frontend/src/app/shell/profile-menu.ts frontend/src/app/shell/profile-menu.spec.ts \
  frontend/src/app/shell/shell.spec.ts frontend/src/app/shell/palette/command-palette.spec.ts \
  frontend/src/app/ui/chart/trade-chart.spec.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts
git commit -m "feat(v241): Navy is the default theme -- only an explicit 'graphite' is Black; Dark blue listed first

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

