# v80 — Terminal foundation, part 1: tokens

Part of `2026-09-10-v80-terminal-foundation_0-index.md`. Read its Global
Constraints and the v77 precondition before starting any task here.

# Phase 1 — Tokens

## Parallelisation

- **Sequential throughout: F1 → F2 → F3.** All three edit
  `frontend/src/styles/tokens.css`.
- **F1 goes first** so the chart-1/2/3 pin is gone before F2 changes
  `--accent` and `--info`.
- **Nothing in Phase 2 starts until F3 is committed.**

---

### Task F1: Six validated chart series

**Files:**
- Modify: `frontend/src/styles/tokens.css`: the `-- chart series --` comment
  and `--chart-1` … `--chart-8` (lines 125–165 today)
- Modify: `frontend/src/app/ui/line-chart.ts:77` (`SERIES`)
- Modify: `frontend/src/app/ui/tokens.spec.ts`: the `REQUIRED` list, plus a new test
- Test: `frontend/src/app/ui/chart-palette.spec.ts` (full rewrite)

**Interfaces:**
- Consumes: nothing.
- Produces: `--chart-1` … `--chart-6` as literal hex in `tokens.css`, and
  `--chart-7`/`--chart-8` removed. `line-chart.ts`'s `SERIES` has length 6
  (`seriesColour(index)` keeps its signature and still wraps by modulo).

- [ ] **Step 1: Write the failing tests**

Replace the whole of `frontend/src/app/ui/chart-palette.spec.ts` with:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

function token(name: string): string {
  const m = CSS.match(new RegExp(`^\\s*${name}:\\s*(#[0-9a-fA-F]{6});`, 'm'));
  if (!m) throw new Error(`${name} is not defined as a hex literal`);
  return m[1];
}

/** sRGB hex -> OKLab: the space the dataviz palette validator measures in
 *  (spec v80 D2). One metric for every colour gate: under the CIE76 formula
 *  this spec used before, the old pink resistance line sat 15.4 from --neg and
 *  passed, though it reads as a loss (5.9 in OKLab). Thresholds are unchanged. */
function oklab(hex: string): [number, number, number] {
  const to = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  const r = to(parseInt(hex.slice(1, 3), 16) / 255);
  const g = to(parseInt(hex.slice(3, 5), 16) / 255);
  const b = to(parseInt(hex.slice(5, 7), 16) / 255);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

/** OKLab distance x100, the validator's scale. */
function deltaE(a: string, b: string): number {
  const [l1, a1, b1] = oklab(a);
  const [l2, a2, b2] = oklab(b);
  return 100 * Math.hypot(l1 - l2, a1 - a2, b1 - b2);
}

/** OKLCH lightness and chroma, for the validator's band and floor. */
function oklch(hex: string): { l: number; c: number } {
  const [L, A, B] = oklab(hex);
  return { l: L, c: Math.hypot(A, B) };
}

const SERIES = Array.from({ length: 6 }, (_, i) => `--chart-${i + 1}`);

describe('the chart series namespace', () => {
  for (const name of SERIES) {
    it(`defines ${name}`, () => expect(() => token(name)).not.toThrow());
  }

  // G9. Green means gain and red means loss everywhere else in this app; a
  // series that happened to be either would be lying.
  for (const name of SERIES) {
    for (const valence of ['--pos', '--neg']) {
      it(`${name} is not confusable with ${valence}`, () => {
        expect(deltaE(token(name), token(valence))).toBeGreaterThan(10);
      });
    }
  }

  it('keeps adjacent series distinguishable at 1px stroke', () => {
    for (let i = 0; i < SERIES.length - 1; i++) {
      expect(deltaE(token(SERIES[i]), token(SERIES[i + 1]))).toBeGreaterThan(15);
    }
  });

  // v80 D2. The band and floor the dataviz validator applies for a dark
  // surface. A series outside the band is either too dim to find at 1px or
  // bright enough to read as a highlight; below the chroma floor it reads
  // as grey. Series are no longer pinned to --accent/--info/--warn: C's
  // lavender info fails this floor and its amber fails the band.
  for (const name of SERIES) {
    it(`${name} sits inside the dark-surface lightness band`, () => {
      const { l } = oklch(token(name));
      expect(l).toBeGreaterThanOrEqual(0.48);
      expect(l).toBeLessThanOrEqual(0.67);
    });

    it(`${name} clears the chroma floor`, () => {
      expect(oklch(token(name)).c).toBeGreaterThanOrEqual(0.1);
    });
  }
});
```

In `frontend/src/app/ui/tokens.spec.ts`, replace the eight entries in `REQUIRED`:

```ts
  '--chart-1',
  '--chart-2',
  '--chart-3',
  '--chart-4',
  '--chart-5',
  '--chart-6',
  '--chart-7',
  '--chart-8',
```

with six:

```ts
  '--chart-1',
  '--chart-2',
  '--chart-3',
  '--chart-4',
  '--chart-5',
  '--chart-6',
```

Then add this test inside `describe('design tokens', …)`, after
`'has dropped the old greyscale quality tokens'`:

```ts
  it('has dropped --chart-7 and --chart-8 (v80 D2: six series)', () => {
    expect(CSS).not.toMatch(/^\s*--chart-7:/m);
    expect(CSS).not.toMatch(/^\s*--chart-8:/m);
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/chart-palette.spec.ts' --include='**/tokens.spec.ts')`

Expected: FAIL. `--chart-2 sits inside the dark-surface lightness band` fails
(`#46c2ff`), as does `--chart-3` (`#ffb43d`, L ≈ 0.82). `has dropped
--chart-7 and --chart-8` fails too.

- [ ] **Step 3: Implement**

In `frontend/src/styles/tokens.css`, replace everything from the line
`  /* -- chart series ------------------------------------------------------`
through `  --chart-8: #c9a227;` with:

```css
  /* -- chart series ------------------------------------------------------
   * A SEPARATE NAMESPACE from the valence hues above, in meaning AND, since
   * v80, in value.
   *
   * The valence rule ("a sixth hue is a review defect") governs SEMANTIC
   * colour: --pos means good, --neg means bad, on every surface. A
   * categorical series colour carries no meaning at all -- it is an
   * identifier, telling you which line is AAPL -- so it must not overlap the
   * valence hues: a green series in an app where green means gain would lie
   * to a reader every other screen has trained.
   *
   * v80 D2: six hues validated against --surface (#131722) with the dataviz
   * palette validator -- OKLCH L 0.48-0.67, chroma >= 0.10, adjacent CVD
   * dE >= 8, normal-vision dE >= 15, contrast >= 3:1. Eight hues that avoid
   * both the gain-green and loss-red families inside that band do not
   * validate, so a seventh series folds into "Other" at its call site.
   * Rejected, and recorded so nobody reintroduces them: a pink (10.8 from
   * --neg) and an olive (12.6 from --pos). They clear a bare dE 10 gate and
   * still read as loss and gain on a P&L chart.
   *
   * No longer pinned to --accent/--info/--warn: under direction C the
   * lavender info fails the chroma floor and amber fails the band.
   *
   * Literal hex, never var(): line-chart.ts reads these through
   * getComputedStyle under vitest, and jsdom does not substitute a nested
   * var() inside a custom property; chart-palette.spec.ts also parses this
   * file as text. That spec is the gate. */
  --chart-1: #4c8dff;
  --chart-2: #c97a22;
  --chart-3: #a868e0;
  --chart-4: #b08c14;
  --chart-5: #1a9db3;
  --chart-6: #7076e8;
```

In `frontend/src/app/ui/line-chart.ts`, replace:

```ts
const SERIES = Array.from({ length: 8 }, (_, i) => `--chart-${i + 1}`);
```

with:

```ts
// Six, not eight (v80 D2). A seventh series wraps back to --chart-1 here;
// a chart that genuinely needs more should fold the tail into "Other"
// before it reaches this component.
const SERIES = Array.from({ length: 6 }, (_, i) => `--chart-${i + 1}`);
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/chart-palette.spec.ts' --include='**/tokens.spec.ts' --include='**/line-chart.spec.ts')`

Expected: PASS.

Measured values, for reading a failure:
- OKLCH L runs 0.617–0.658 and chroma 0.107–0.182.
- OKLab ΔE (×100) from `--pos` and from `--neg` is at least 15.6.
- The closest adjacent pair (`--chart-5` and `--chart-6`) is 15.9 apart.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/app/ui/line-chart.ts frontend/src/app/ui/chart-palette.spec.ts frontend/src/app/ui/tokens.spec.ts
git commit -m "feat(v80): six validated chart series, unpinned from accent/info/warn"
```

---

### Task F2: TradingView Blue colour tokens

**Files:**
- Modify: `frontend/src/styles/tokens.css`:
  - the header comment (lines 13–15 today);
  - the colour and elevation block from `--bg` through `--info-soft` (lines 42–105);
  - the `--quality-4` comment (lines 119–121).
- Modify: `frontend/src/app/ui/contrast.spec.ts`
- Modify: `frontend/src/app/ui/confidence-cell.spec.ts:79-82`. It pins `--info`
  to `#46c2ff` and would go red the moment this task lands.
- Test: `frontend/src/app/ui/tokens.spec.ts`

**Interfaces:**
- Consumes: F1's series block (untouched here).
- Produces: every D1 value as a literal. `--accent` (text-safe, `#5593ff`) and
  `--accent-fill` (`#2962ff`) are two separate tokens, plus the new
  `--on-accent` (`#ffffff`). F4 consumes `--accent-fill`/`--on-accent`; F21
  asserts all of these from Python.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/tokens.spec.ts`, add to `REQUIRED` directly after
`'--accent',`:

```ts
  '--accent-fill',
  '--on-accent',
```

Append this block at the end of the file:

```ts
describe('v80 D1: the TradingView Blue palette', () => {
  const EXPECTED: Record<string, string> = {
    '--bg': '#0c0f16',
    '--surface': '#131722',
    '--surface-raised': '#1c212d',
    '--surface-overlay': '#242936',
    '--border': '#2a2e39',
    '--border-strong': '#363a45',
    '--text': '#d9dce4',
    '--text-secondary': '#9ea2ad',
    '--text-muted': '#9195a0',
    '--text-faint': '#4e5361',
    '--accent': '#5593ff',
    '--accent-fill': '#2962ff',
    '--on-accent': '#ffffff',
    '--info': '#b39ddb',
    '--pos': '#17c98e',
    '--neg': '#ff5470',
    '--warn': '#ffb43d',
  };

  for (const [name, hex] of Object.entries(EXPECTED)) {
    it(`${name} is ${hex}`, () => {
      expect(CSS).toMatch(new RegExp(`^\\s*${name}:\\s*${hex};`, 'mi'));
    });
  }

  it('dims the overlay from the new ground', () => {
    expect(CSS).toMatch(/^\s*--overlay-dim:\s*rgba\(12, 15, 22, \.72\);/m);
  });

  it('tints accent-soft from the fill blue and info-soft from lavender', () => {
    expect(CSS).toMatch(/^\s*--accent-soft:\s*rgba\(41, 98, 255, 0\.18\);/m);
    expect(CSS).toMatch(/^\s*--info-soft:\s*rgba\(179, 157, 219, 0\.14\);/m);
  });
});
```

In `frontend/src/app/ui/contrast.spec.ts`, append at the end of the file:

```ts
/**
 * v80 D1. The accent is two tokens: --accent is interactive TEXT and state
 * (links, active tab, sort arrow) and must read on every surface;
 * --accent-fill is what a filled button paints, carrying --on-accent.
 */
describe('accent legibility (v80 D1)', () => {
  for (const bg of SURFACES) {
    it(`--accent as text on ${bg} clears 4.5:1`, () => {
      expect(ratio(token('--accent'), token(bg))).toBeGreaterThanOrEqual(4.5);
    });
  }

  it('--on-accent on --accent-fill clears 4.5:1', () => {
    expect(ratio(token('--on-accent'), token('--accent-fill'))).toBeGreaterThanOrEqual(4.5);
  });
});
```

In `frontend/src/app/ui/confidence-cell.spec.ts`, replace:

```ts
  it('leaves info alone for the chart series namespace', () => {
    const root = getComputedStyle(document.documentElement);
    expect(root.getPropertyValue('--info').trim().toLowerCase()).toBe('#46c2ff');
  });
```

with:

```ts
  it('keeps info off the quality ramp (v80 D1: lavender, not blue)', () => {
    const root = getComputedStyle(document.documentElement);
    expect(root.getPropertyValue('--info').trim().toLowerCase()).toBe('#b39ddb');
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/tokens.spec.ts' --include='**/contrast.spec.ts' --include='**/confidence-cell.spec.ts')`

Expected: FAIL.
- Every `v80 D1` value test fails.
- `defines --accent-fill` and `defines --on-accent` fail.
- `--on-accent on --accent-fill clears 4.5:1` throws: `token()` finds no match.
- `--accent as text on --surface-overlay` fails (the old `#7b5cfa` measures about 3.5:1).
- `keeps info off the quality ramp` fails: `#46c2ff` is not `#b39ddb`.

- [ ] **Step 3: Implement**

In `frontend/src/styles/tokens.css`, replace the three header-comment lines:

```css
 * This file is NOT `swingbot/admin/static/tokens.css`. That one still drives
 * the Jinja UI *and* the bot's Discord chart colours. The two coexist until
 * Jinja is deleted, and this is the SPA's only palette.
```

with:

```css
 * The bot's Discord chart PNGs share this palette (spec v80 D5):
 * `swingbot/core/charts/chart_style.py`'s THEME names these tokens and
 * tests/charts/test_chart_theme.py compares the two byte for byte. Change a
 * colour here and that test names the chart constant that must follow.
```

Replace everything from `  --bg: #0a0b10;` through
`  --info-soft: rgba(70, 194, 255, 0.12);` with:

```css
  /* v80 D1: direction C, "TradingView Blue". The surface ladder steps far
   * enough apart (0c0f16 -> 131722 -> 1c212d -> 242936) that panels read as
   * separate objects without a shadow; --surface is TradingView's own chart
   * pane, so the admin and the Discord charts sit on one ground. */
  --bg: #0c0f16;
  --surface: #131722;
  --surface-raised: #1c212d;
  --surface-overlay: #242936;
  --overlay-dim: rgba(12, 15, 22, .72);
  --border: #2a2e39;
  --border-strong: #363a45;

  /* -- elevation --------------------------------------------------------
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
  /* Box-shadow geometry (blur/offset) is intentionally exempt from the "px only for 1px/2px borders" rule per design spec D2 — shadow values have no natural expression via the closed --space-* scale. */
  --shadow-overlay: 0 8px 24px rgba(0, 0, 0, .55), 0 2px 6px rgba(0, 0, 0, .4);

  /* Alias for the dim behind a MODAL L3 element. --overlay-dim is the raw
   * colour; this names what it is for, so a scrim stops being hand-rolled
   * (versions.ts faked one with a 9999px spread). */
  --scrim: var(--overlay-dim);

  --text: #d9dce4;
  --text-secondary: #9ea2ad;
  /* v80 D1: direction C's first muted grey (#888c97) measured 4.32:1 on
   * --surface-overlay -- under the 4.5:1 gate contrast.spec.ts enforces on
   * all four surfaces, for real readable labels at --text-micro (nav group
   * headers, chip captions, .sb-label). #9195a0 is the smallest lift that
   * clears it with v54's safety margin: worst case 4.85:1 on
   * --surface-overlay. v54 Task 42 made the same kind of measured,
   * single-token change for the previous palette. */
  --text-muted: #9195a0;
  /* --text-faint is a RULE AND DIVIDER colour (~2.3:1 on --surface) -- never
   * text that must be read. contrast.spec.ts's `no-text-uses-text-faint`
   * assumes this and this comment is what it checks for. */
  --text-faint: #4e5361;

  --pos: #17c98e;
  --neg: #ff5470;
  --warn: #ffb43d;
  /* v80 D1: the accent is two tokens. --accent is the colour of interactive
   * TEXT and state -- links, the active tab, the sort arrow, focus -- and
   * #5593ff clears 4.85:1 on every surface. --accent-fill is the deeper
   * TradingView blue a filled button paints, with --on-accent on top at
   * 4.90:1; the text-safe blue is too light to carry white ink. */
  --accent: #5593ff;
  --accent-fill: #2962ff;
  --on-accent: #ffffff;
  /* v80 D1: info moved off sky blue. Under direction C the accent took the
   * blue, and two blues would make "neutral" read as "interactive". */
  --info: #b39ddb;

  /* 12% tints, for cell and chip backgrounds, hover states and the chart's
   * risk/reward bands. Literal rgba rather than colour-mix() so the values
   * survive without a fallback path. --accent-soft is 18% of the FILL blue:
   * the selected-segment ground needs to separate from --surface-raised. */
  --pos-soft: rgba(23, 201, 142, 0.12);
  --neg-soft: rgba(255, 84, 112, 0.12);
  --warn-soft: rgba(255, 180, 61, 0.12);
  --accent-soft: rgba(41, 98, 255, 0.18);
  --info-soft: rgba(179, 157, 219, 0.14);
```

In the quality-ramp block, replace:

```css
  /* v62 D2: level 4 is ordinal yellow-green, not informational blue.
   * Keep this literal in lockstep with presentation.tokens.ACCENT_RAMP[4];
   * --info remains the chart-series colour used by --chart-2. */
```

with:

```css
  /* v62 D2: level 4 is ordinal yellow-green, not informational blue.
   * Keep this literal in lockstep with presentation.tokens.ACCENT_RAMP[4].
   * (v80: --info is lavender and no longer doubles as a chart series.) */
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/tokens.spec.ts' --include='**/contrast.spec.ts' --include='**/chart-palette.spec.ts' --include='**/elevation.spec.ts' --include='**/confidence-cell.spec.ts' --include='**/chart-theme.spec.ts')`

Expected: PASS. The chart palette is unaffected: F1 already removed the pin,
and the new `--pos`/`--neg` values are unchanged. `chart-theme.spec.ts` reads
`--info` through `tokenValue`, so it follows the new value without an edit.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/app/ui/tokens.spec.ts frontend/src/app/ui/contrast.spec.ts frontend/src/app/ui/confidence-cell.spec.ts
git commit -m "feat(v80): TradingView Blue colour tokens, split accent, lavender info"
```

---

### Task F3: Type, shape and touch tokens, and the one label and help style

**Files:**
- Modify: `frontend/src/styles/tokens.css`: type block (lines 167–198),
  controls block (lines 216–230), radii (lines 254–255), and a new touch
  media block after `:root`'s closing brace
- Modify: `frontend/src/styles.css`: new `.sb-label` and `.sb-help` after
  `.panel-subtitle`
- Modify: `frontend/src/app/ui/tokens.spec.ts`
- Create: `frontend/src/app/ui/text-styles.spec.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - tokens `--row-h` (32px base, 44px touch) and `--text-control` (14px base,
    16px touch);
  - `--text-metric` becomes 28px, and `--radius`/`--radius-chip` become 2px;
  - `--control-h` becomes 44px inside the touch block;
  - global classes `.sb-label` and `.sb-help`.

  Every Group A task consumes these.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/ui/tokens.spec.ts`:

```ts
describe('v80 D3: type, shape and touch', () => {
  it('sets the headline figure to 28px', () => {
    expect(CSS).toMatch(/^\s*--text-metric:\s*calc\(28px \* var\(--text-scale\)\);/m);
  });

  it('tightens both radii to 2px', () => {
    expect(CSS).toMatch(/^\s*--radius:\s*2px;/m);
    expect(CSS).toMatch(/^\s*--radius-chip:\s*2px;/m);
  });

  it('defines one row height and one form-control text size', () => {
    expect(CSS).toMatch(/^\s*--row-h:\s*32px;/m);
    expect(CSS).toMatch(/^\s*--text-control:\s*calc\(14px \* var\(--text-scale\)\);/m);
  });

  it('grows controls, rows and control text for touch and narrow screens', () => {
    const block = CSS.match(/@media \(pointer: coarse\), \(max-width: 639px\)\s*\{([\s\S]*?)\n\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toMatch(/--control-h:\s*44px;/);
    expect(block![1]).toMatch(/--row-h:\s*44px;/);
    expect(block![1]).toMatch(/--text-control:\s*calc\(16px \* var\(--text-scale\)\);/);
  });
});
```

Create `frontend/src/app/ui/text-styles.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * v80 D3: one label style and one help-text style, defined once in the
 * global stylesheet so a component or a workspace applies the class rather
 * than restating the typography. Asserted as text, like tokens.spec.ts:
 * jsdom does not resolve the cascade well enough to assert computed styles.
 */
const GLOBAL = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');

const rule = (name: string) =>
  GLOBAL.match(new RegExp(`\\.${name}\\s*\\{[^}]*\\}`, 's'))?.[0] ?? '';

describe('v80 D3: the shared text styles', () => {
  it('.sb-label is 11px monospace capitals at 0.08em in muted text', () => {
    const r = rule('sb-label');
    expect(r).toContain('font-family: var(--font-mono)');
    expect(r).toContain('font-size: var(--text-micro)');
    expect(r).toContain('font-weight: 500');
    expect(r).toContain('letter-spacing: 0.08em');
    expect(r).toContain('text-transform: uppercase');
    expect(r).toContain('color: var(--text-muted)');
  });

  it('.sb-help is chip-sized secondary text capped at a readable measure', () => {
    const r = rule('sb-help');
    expect(r).toContain('font-size: var(--text-chip)');
    expect(r).toContain('color: var(--text-secondary)');
    expect(r).toContain('max-width: 65ch');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/tokens.spec.ts' --include='**/text-styles.spec.ts')`

Expected: FAIL. Every `v80 D3` test fails, and both `text-styles` tests fail on
an empty rule.

- [ ] **Step 3: Implement**

In `frontend/src/styles/tokens.css`, in the `-- type --` comment, replace
`the scale is closed (11/12/13/14/16/20/25)` with
`the scale is closed (11/12/13/14/16/20/28)`.

Replace:

```css
  --text-body: calc(14px * var(--text-scale));      /* body */
```

with:

```css
  --text-body: calc(14px * var(--text-scale));      /* body */
  --text-control: calc(14px * var(--text-scale));   /* form-control text; 16px on touch, below */
```

Replace:

```css
  --text-metric: calc(25px * var(--text-scale));    /* primary metric */
```

with:

```css
  --text-metric: calc(28px * var(--text-scale));    /* primary metric -- v80 D3, was 25px */
```

Replace:

```css
  --control-h: 28px;
```

with:

```css
  --control-h: 28px;

  /* v80 D3: one row height for every table row, so a table beside a list
   * lines up. Grows with --control-h in the touch block below. */
  --row-h: 32px;
```

Replace:

```css
  --radius: 4px;
  --radius-chip: 3px;
```

with:

```css
  /* v80 D3: 2px, was 4px / 3px -- a pro terminal's corners, not a card's. */
  --radius: 2px;
  --radius-chip: 2px;
```

Directly after the `:root` block's closing `}` (the line after
`  --transition: var(--dur-base) var(--ease-out);`), insert:

```css

/* v80 D3 -- touch. A finger needs about 44px; a mouse row of 28px controls
 * shows more data. `pointer: coarse` catches touch at any width, and 639px
 * (breakpoints.ts's sm floor, less one) catches a narrow window driven by a
 * mouse too. Only these three move: gutters stay put, so this is a
 * hit-target change, not a zoom. 16px control text is also the size below
 * which mobile browsers zoom into a focused field. */
@media (pointer: coarse), (max-width: 639px) {
  :root {
    --control-h: 44px;
    --row-h: 44px;
    --text-control: calc(16px * var(--text-scale));
  }
}
```

In `frontend/src/styles.css`, insert directly after the `.panel-subtitle { … }` rule:

```css

/* v80 D3 -- the one label style. Eleven files hand-built uppercase labels
 * with four different letter-spacings; this is the single definition every
 * component uses now and every workspace moves to in Migration. Mono 500:
 * JetBrains Mono is self-hosted at 400/500/700, and a 600 would be
 * synthesised. */
.sb-label {
  font-family: var(--font-mono);
  font-size: var(--text-micro);
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
}

/* v80 D3 -- the one help-text style. Replaces .section-help, .explain, .help
 * and .legend as Migration moves their call sites; .section-help stays until
 * the last one has moved. */
.sb-help {
  margin: 0;
  max-width: 65ch;
  color: var(--text-secondary);
  font-size: var(--text-chip);
  line-height: 1.5;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/tokens.spec.ts' --include='**/text-styles.spec.ts' --include='**/register.spec.ts' --include='**/breakpoints.spec.ts')`

Expected: PASS. `sizes controls with a single height token` still matches the
base `--control-h: 28px;`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/styles.css frontend/src/app/ui/tokens.spec.ts frontend/src/app/ui/text-styles.spec.ts
git commit -m "feat(v80): 28px figures, 2px radii, touch sizing, one label and help style"
```
