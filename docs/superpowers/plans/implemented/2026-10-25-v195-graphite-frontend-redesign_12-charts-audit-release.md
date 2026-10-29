# v195 — Graphite, Part 12: chart theme and alert image, the `rail-label` audit check, release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-35:" -A 400 <this file>`.

**Scope of this part (V195-34..V195-36), the plan's last.** Spec Phase 6 (in-app charts and SVG primitives read tokens only; the before/after Discord alert image recorded) and Phase 7 (one new layout-audit check, `rail-label`, plus `ROUTES` learning `?tab=providers`; the full suite once; the audit at 390 / 768 / 1440 against a local replica; the merge; the post-deploy production audit). V195-34 needs only V195-2 and may run beside Phases 3–5; it creates the results doc V195-36 appends to. V195-35 needs only V195-16's rail markup and may run beside V195-17..V195-34. V195-36 runs last, after every other ledger task is committed on the branch.

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/` (V195-34 Step 6 reads `$MAIN` once, read-only, to render the "before" image; V195-36 Step 8 merges into `$MAIN`). Frontend runs through `npm --prefix "$WT/frontend" ...`; Node scripts by absolute path; Python as `python "$WT/scripts/dev/testrun.py" file "$WT/<path>"`.

**The state earlier tasks leave (read before editing).**

- `swingbot/core/charts/chart_style.py` (V195-1, V195-2): `THEME` holds the Graphite values (`bg #0d0f12`, `surface #15181d`, `pos #3fb68b`, `neg #f06e66`, `accent #6ea8fe`, …), `ENTRY_COLOR = THEME["accent"]`, `STYLE_VERSION = "v195"`; `tests/charts/test_chart_theme.py` ends `STYLE_PINS` with `("f04168edd2b2e287", "v195")` after the `v195a` row. `$MAIN` (until V195-36 merges) still holds the pre-v195 theme: `STYLE_VERSION = "v181"`, `bg #070b14`, `pos #00e5a0`, `neg #ff4d5e`, entry on `chart-1 #4c8dff`. No task in this part edits either Python file.
- `tests/charts/resolved_tokens.json` is the regenerated Graphite fixture; `src/test-setup.ts` injects it, so `resolveToken('--accent')` is `#6ea8fe` and `resolveToken('--text-faint')` is `#6b7280` under Vitest. `--text-micro` / `--text-chip` floor at 12px (V195-3). `--text-faint` is a rule, divider and disabled-glyph colour, never text (correction 13; `tokens.css` says so above the token).
- `frontend/src/app/ui/chart/chart-theme.ts`, `chart-frame.ts`, `plan-lines.ts`, `price-pane.ts`: no v194 or v195 task edits them. Candles already read `palette.up` / `palette.down`; plan lines already draw entry in `palette.accent` solid, stop `down` dashed, targets `up` dashed, working stop `warn` dotted; `chartOptions` sizes tick text with `tokenPx(CHART_CHROME.tickSize, 11)`.
- The SVG primitives under `frontend/src/app/ui/` (`sparkline`, `histogram`, `heat-grid`, `gauge`, `waterfall`, `donut`, `dot-plot`, `strip-plot`, `matrix`, `small-multiples` and the `line-chart` it draws with, `timeline`) are unchanged by v195 so far; v194 may have converted `title` attributes in some of them, so every edit below is by quoted string, never by line number. `heat-grid.ts`, `small-multiples.ts`, `donut.ts`, `dot-plot.ts`, `strip-plot.ts` and `waterfall.ts` are minified onto a few long lines.
- `frontend/scripts/layout-audit-lib.mjs` and `layout-audit.mjs` as v194 left them (V194-3): `CHECKS` ends `'vcenter', 'hint'` (eight); `hintVerdict(rect, viewport, hits)` follows `vcenterGeometry` in the lib; the driver has `HINT_SETTLE_MS`, `measureHint(id)`, `hintFinding`, `closeHint`, `auditHints(page, width)` before the page-ready rule, and `auditWidth` runs `auditHints` after each screenshot. `ROUTES` has 28 entries ending `'/system', '/system?tab=logs', '/system?tab=scan'`, … `'/ui'`. `docs/claude/ui-design.md` § Checklist and `AGENTS.md` name the `hint` check (V194-16b).
- Rail (V195-16, V195-18): at widths ≥ 640 the shell shows `nav.rail[aria-label="Primary"]` with eleven `a.rail-link.sb-hit[aria-label=<label>]` entries (icon only), each followed by an `sb-hint` in anchor mode (`Hint.anchor`, V195-14): no trigger button, opens on the link's hover and focus, closes on `mouseleave` / `blur` / Escape, and sets the link's `aria-describedby` to its `role="tooltip"` popover's id while bound. Below 640px the rail is hidden and `sb-phone-tab-bar` navigates. The gallery's `a.rail-demo` (V195-33) sits outside `nav.rail`, so a check scoped to `nav.rail a.rail-link` never counts it. `sb-hint`'s anchor mode renders no `button.trigger`, so v194's `auditHints` never opens a rail label.
- Every route renders exactly one `h1` (`sb-page`'s `h1.title`, V195-21..V195-33); `sb-breadcrumb` (V195-15) renders `nav[aria-label="Breadcrumb"] > ol > li`, the page crumb an `a` (`routerLink`, class `sb-hit`) whenever a detail crumb follows it, and keeps only the last crumb below 640px. Partner decision (2026-10-27): detail pages have no in-page back link; the breadcrumb's page crumb (and the phone tab bar) is the way back.
- No task edits `VERSION.json` or `version_history.json`; `/close-out` resolves the `Bump:` line after the merge.

---

# Phase 6 — Charts

### Task V195-34: Charts: in-app chart chrome and plan lines read tokens (entry accent solid, target/stop dashed pos/neg); SVG primitives hold no chart-local colour (source-scan spec); before/after Discord alert image recorded
**Model:** sonnet — a small token-read change, two pinning specs, one new source-scan spec with a balanced-paren scanner, six one-property CSS edits and a scripted before/after render; the care is in a scanner that sees through comments and minified styles without false alarms.

**Files:**
- Modify: `frontend/src/app/ui/chart/chart-theme.ts` (`TICK_FALLBACK_PX`; `chartOptions` uses it)
- Modify: `frontend/src/app/ui/chart/chart-theme.spec.ts` (import; one appended `describe`)
- Modify: `frontend/src/app/ui/chart/plan-lines.spec.ts` (imports; one appended `describe`)
- Create: `frontend/src/app/ui/svg-colour.spec.ts`
- Modify: `frontend/src/app/ui/gauge.ts`, `frontend/src/app/ui/heat-grid.ts`, `frontend/src/app/ui/line-chart.ts`, `frontend/src/app/ui/matrix.ts`, `frontend/src/app/ui/small-multiples.ts`, `frontend/src/app/ui/timeline.ts` (text set in `--text-faint` moves to `--text-muted`)
- Create: `docs/superpowers/results/2026-10-25-v195-layout-audit.md`
- Create: `docs/superpowers/results/v195/alert-before.png`
- Create: `docs/superpowers/results/v195/alert-after.png`

**Interfaces:**
- Consumes: `chartPalette()`, `chartOptions(palette)`, `ChartPalette`, `tokenPx`, `CHART_CHROME` (exist; `chart-theme.ts`, `chart-frame.ts`); `planLineSpecs(levels, palette)` (exists; `plan-lines.ts`); `resolveToken(name)` (`ui/testing/resolve-token.ts`); `stripComments(source)` (`ui/testing/all-sources.ts`); `THEME`, `ENTRY_COLOR`, `STYLE_VERSION` (`chart_style.py`, V195-1/V195-2, read only); `generate_trade_chart` through `scripts/dev/render_chart_fixtures.py --out DIR` (exists; renders one PNG per fixture, `secondary_sources.png` among them).
- Produces:
  - `TICK_FALLBACK_PX = 12` (exported from `chart-theme.ts`): the tick-text size `chartOptions` uses when `--text-micro` cannot be resolved, equal to the 12px micro floor.
  - `docs/superpowers/results/2026-10-25-v195-layout-audit.md` with exactly three level-2 sections, `## Alert image` (filled here), `## Layout audit` and `## Notes` (V195-36 fills both).
  - `svg-colour.spec.ts`: `SVG_PRIMITIVES` (12 file stems), `FAINT_ALLOWED` (`{ matrix: ['.missing'] }`). Nothing else consumes them; V195-36's full suite runs them.

**What changes, and what is already there.** Spec Phase 6. The canvas chart (`lightweight-charts`) already takes every colour from `chartPalette()`, which reads tokens at chart creation: candles and the MACD histogram on `--pos` / `--neg`, entry on `--accent` solid, stop `--neg` dashed, targets `--pos` dashed, working stop `--warn` dotted, grid `--border`, axes `--border-strong`, volume greyscale `--text-faint`. On the Graphite tokens that is already the spec's look, so the chart code changes in one place only: `chartOptions` falls back to 11px tick text when `--text-micro` cannot be resolved, below the 12px floor V195-3 set, and now falls back to `TICK_FALLBACK_PX` (12). The specs gain the pins Phase 6 states and nothing yet asserts: entry solid and the other levels dashed or dotted (`planLineSpecs` was checked for colours only), the plan lines on the real Graphite palette, the entry accent distinct from `--chart-1` (the Discord image's entry line reads `accent` too since V195-1), and chart chrome that carries no valence or accent hue.

The SVG primitives already paint through tokens; `primitives.spec.ts` bans hex and `rgb()` / `hsl()` app-wide. What no gate sees is a named colour keyword (`fill="white"`), the other CSS colour functions (`oklch()`, `color()`), a `color-mix()` fed a literal, and text set in `--text-faint`, which correction 13 makes a rule, divider and disabled-glyph colour only (3.7:1 on `--surface`, under AA). `svg-colour.spec.ts` closes all four for the spec's list (sparkline, histogram, heat grid, gauge, waterfall, donut, dot and strip plot, matrix, small multiples with the `line-chart` it draws, timeline). Six of those files set readable text in `--text-faint` today (gauge's label and caption, heat grid's headers and `n` counts, the line chart's empty line, the matrix headers, small multiples' `n`, the timeline's meta line); each moves to `--text-muted` (6.2:1 or better on every surface). The matrix's missing-cell `—` stays faint: it is a disabled glyph, the one non-rule use correction 13 allows, and the spec lists it by selector with that reason.

The Discord side changed in V195-1 and V195-2 (`THEME`, `ENTRY_COLOR`, `STYLE_VERSION`, `STYLE_PINS`); this task only renders one alert chart from `$MAIN` (pre-v195 theme) and one from the branch (Graphite), commits the pair, and starts the results doc with them.

**What is left alone.** `bar-list.ts`, `share-bar.ts` and `scatter.ts` are charts outside the spec's Phase 6 list; `bar-list` and `share-bar` also set `n` text in `--text-faint`. They are named under `## Notes` in the results doc for a follow-up, not changed here (no scope added). `price-pane.ts`, `plan-lines.ts`, `indicator-panes.ts` and the Python chart code do not change.

- [ ] **Step 1: Write the failing chart-theme and plan-lines tests**

In `$WT/frontend/src/app/ui/chart/chart-theme.spec.ts`, replace the import line

```ts
import { chartOptions, chartPalette, tokenPx } from './chart-theme';
```

with

```ts
import { TICK_FALLBACK_PX, chartOptions, chartPalette, tokenPx } from './chart-theme';
```

and append at the end of the file:

```ts

/* -- v195 Phase 6 -- the canvas chart on the Graphite tokens ----------------- */

describe('chart theme on the Graphite tokens (v195 Phase 6)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('draws the entry in the accent, a hue no chart series uses', () => {
    // The Discord image's ENTRY_COLOR reads THEME["accent"] since V195-1, so
    // the entry line is one colour in the app and in an alert. --chart-1 was
    // the old Discord entry colour; the two must not converge again.
    const palette = chartPalette();
    expect(palette.accent).toBe(resolveToken('--accent'));
    expect(palette.accent).not.toBe(resolveToken('--chart-1'));
    expect(new Set([palette.up, palette.down, palette.accent]).size).toBe(3);
  });

  it('keeps the chrome neutral: no valence or accent hue on grid, axis, ground, ticks or volume', () => {
    const palette = chartPalette();
    const hued = new Set([palette.up, palette.down, palette.accent, palette.warn, palette.info]);
    for (const [name, value] of Object.entries({
      border: palette.border, axis: palette.axis, surface: palette.surface,
      textMuted: palette.textMuted, volume: palette.volume, separator: palette.separator,
    })) {
      expect(hued.has(value), `palette.${name} is ${value}`).toBe(false);
    }
  });

  it('falls back to the 12px micro floor when the tick size cannot be resolved', () => {
    const palette = chartPalette();
    const real = window.getComputedStyle.bind(window);
    vi.spyOn(window, 'getComputedStyle').mockImplementation((el, pseudo) => {
      if (el instanceof HTMLElement && el.style.fontSize.startsWith('var(')) {
        return { fontSize: 'var(--text-micro)' } as CSSStyleDeclaration;
      }
      return real(el, pseudo);
    });

    expect(TICK_FALLBACK_PX).toBe(12);
    expect(chartOptions(palette).layout?.fontSize).toBe(TICK_FALLBACK_PX);
  });
});
```

In `$WT/frontend/src/app/ui/chart/plan-lines.spec.ts`, replace the first two import lines

```ts
import { UTCTimestamp } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
```

with

```ts
import { LineStyle, UTCTimestamp } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';

import { resolveToken } from '../testing/resolve-token';
```

change `import { ChartPalette } from './chart-theme';` to `import { ChartPalette, chartPalette } from './chart-theme';`, and append at the end of the file:

```ts

/* -- v195 Phase 6 -- line styles, and the plan on the real palette ----------- */

describe('plan lines (v195 Phase 6)', () => {
  it('draws the entry solid, stop and targets dashed, the working stop dotted', () => {
    expect(byTitle(FULL, 'Entry')?.lineStyle).toBe(LineStyle.Solid);
    expect(byTitle(FULL, 'Stop')?.lineStyle).toBe(LineStyle.Dashed);
    expect(byTitle(FULL, 'Target 1')?.lineStyle).toBe(LineStyle.Dashed);
    expect(byTitle(FULL, 'Target 2')?.lineStyle).toBe(LineStyle.Dashed);
    expect(byTitle(FULL, 'Working stop')?.lineStyle).toBe(LineStyle.Dotted);
  });

  it('takes accent, loss and gain from the Graphite tokens through chartPalette()', () => {
    const colour = (title: string) => planLineSpecs(FULL, chartPalette()).find((s) => s.title === title)?.color;
    expect(colour('Entry')).toBe(resolveToken('--accent'));
    expect(colour('Stop')).toBe(resolveToken('--neg'));
    expect(colour('Target 1')).toBe(resolveToken('--pos'));
    expect(colour('Target 2')).toBe(resolveToken('--pos'));
    expect(colour('Working stop')).toBe(resolveToken('--warn'));
  });
});
```

- [ ] **Step 2: Write the failing SVG colour spec**

Create `$WT/frontend/src/app/ui/svg-colour.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { stripComments } from './testing/all-sources';

/**
 * Spec v195 Phase 6: the SVG chart primitives hold no chart-local colour --
 * every fill, stroke and text colour reads a token -- and none sets readable
 * text in --text-faint, the rule, divider and disabled-glyph colour
 * (correction 13). primitives.spec.ts already bans hex and rgb()/hsl()
 * literals app-wide; this closes what that pattern cannot see: a named colour
 * keyword, the other CSS colour functions, a color-mix() fed a literal, and
 * faint text. A SOURCE scan, because jsdom resolves neither a component's
 * var() chain nor an SVG presentation attribute. Comments are stripped first,
 * so prose like "green or red" in a doc comment is not a finding.
 */

/** The spec's list (sparkline .. timeline), plus the line chart small multiples draws with. */
const SVG_PRIMITIVES = [
  'sparkline', 'histogram', 'heat-grid', 'gauge', 'waterfall', 'donut', 'dot-plot', 'strip-plot',
  'matrix', 'small-multiples', 'line-chart', 'timeline',
] as const;

/** Selectors allowed to keep --text-faint, each with its reason. */
const FAINT_ALLOWED: Partial<Record<(typeof SVG_PRIMITIVES)[number], string[]>> = {
  // The '—' a matrix prints for a missing cell: a disabled glyph, the one
  // non-rule use correction 13 allows.
  matrix: ['.missing'],
};

const read = (stem: string) =>
  stripComments(readFileSync(join(process.cwd(), 'src/app/ui', `${stem}.ts`), 'utf8'));

/** A named colour keyword as the value of a colour property or an SVG paint attribute. */
const NAMED_COLOUR =
  /(?<![-\w])(?:color|fill|stroke|background(?:-color)?|stop-color|border(?:-\w+)?-color|outline-color)\s*[:=]\s*["'`]?\s*(?:red|green|blue|white|black|gr[ae]y|orange|yellow|purple|pink|cyan|magenta|lime|navy|teal|silver|maroon|olive|aqua|fuchsia)\b/gi;

/** CSS colour functions other than color-mix(), whose inputs colorMixArgs/residue check. */
const COLOUR_FUNCTION = /\b(?:oklch|oklab|lab|lch|hwb|color)\(/g;

/** `color:` as the whole property name (so `border-color:` stays a rule) set to --text-faint. */
const FAINT_TEXT = /(?<![-\w])color:\s*var\(--text-faint\)/g;

/** Every color-mix() call's argument list, matched by balanced parentheses. */
function colorMixArgs(source: string): string[] {
  const out: string[] = [];
  const head = 'color-mix(';
  for (let at = source.indexOf(head); at !== -1; at = source.indexOf(head, at + 1)) {
    let depth = 0;
    let end = at + head.length - 1;
    for (; end < source.length; end += 1) {
      if (source[end] === '(') depth += 1;
      else if (source[end] === ')' && --depth === 0) break;
    }
    out.push(source.slice(at + head.length, end));
  }
  return out;
}

/** What a color-mix() argument list holds besides tokens, its space, weights and `transparent`: '' when it mixes tokens only. */
function residue(args: string): string {
  return args
    .replace(/\$\{[^}]*\}/g, '')
    .replace(/var\(\s*(?:--[\w-]+)?\s*\)/g, '')
    .replace(/\bin\s+(?:srgb|oklab|oklch|lab|lch|hsl|hwb|display-p3)\b/g, '')
    .replace(/\b(?:transparent|currentColor)\b/g, '')
    .replace(/\d+(?:\.\d+)?%/g, '')
    .replace(/[\s,%]/g, '');
}

/** The selector a declaration sits under: the last line of the text between the previous `}` and its `{`. */
function selectorAt(source: string, index: number): string {
  const open = source.lastIndexOf('{', index);
  const close = source.lastIndexOf('}', open);
  return source.slice(close + 1, open).split('\n').pop()!.trim();
}

describe('the scanners (v195 Phase 6)', () => {
  it('catch a named colour and leave white-space and tokens alone', () => {
    expect('.x { fill: red; }'.match(NAMED_COLOUR)).toHaveLength(1);
    expect('<rect fill="white" />'.match(NAMED_COLOUR)).toHaveLength(1);
    expect('.x { white-space: nowrap; color: var(--text); fill: none; }'.match(NAMED_COLOUR)).toBeNull();
  });

  it('catch a colour function and leave color-mix() to the residue check', () => {
    expect('.x { color: oklch(70% 0.1 150); }'.match(COLOUR_FUNCTION)).toHaveLength(1);
    expect('.x { background: color-mix(in oklab, var(--pos) 70%, var(--surface)); }'.match(COLOUR_FUNCTION)).toBeNull();
    expect(colorMixArgs('a{b:color-mix(in oklab,var(--pos) 70%,var(--surface))}').map(residue)).toEqual(['']);
    expect(colorMixArgs('a{b:color-mix(in oklab,var(--text) ${Math.round(70-(n>1?i/(n-1):0)*45)}%,transparent)}').map(residue))
      .toEqual(['']);
    expect(colorMixArgs('a{b:color-mix(in srgb,#fff 10%,var(--bg))}').map(residue)).toEqual(['#fff']);
  });

  it('name the selector a faint text colour sits under, multi-line or minified', () => {
    const multi = '.b5 { background: var(--quality-5); }\n    .missing { color: var(--text-faint); background: none; }';
    expect(selectorAt(multi, multi.indexOf('color:'))).toBe('.missing');
    const mini = 'table{width:100%}th{font-size:var(--text-micro);color:var(--text-faint)}';
    expect(selectorAt(mini, mini.indexOf('color:'))).toBe('th');
    expect('.x { border-color: var(--text-faint); }'.match(FAINT_TEXT)).toBeNull();
  });
});

describe('the SVG chart primitives read tokens only (v195 Phase 6)', () => {
  for (const stem of SVG_PRIMITIVES) {
    describe(`${stem}.ts`, () => {
      const source = read(stem);

      it('names no colour keyword', () => expect(source.match(NAMED_COLOUR) ?? []).toEqual([]));

      it('calls no colour function but color-mix()', () => expect(source.match(COLOUR_FUNCTION) ?? []).toEqual([]));

      it('mixes tokens only', () => expect(colorMixArgs(source).map(residue).filter(Boolean)).toEqual([]));

      it('draws in tokens', () => expect(source).toMatch(/var\(\s*(?:--[\w-]+|\$\{CHART_CHROME\.\w+\})/));

      it('sets no readable text in --text-faint', () => {
        const hits = [...source.matchAll(FAINT_TEXT)].map((m) => selectorAt(source, m.index ?? 0));
        expect(hits).toEqual(FAINT_ALLOWED[stem] ?? []);
      });
    });
  }

  it('every FAINT_ALLOWED entry still matches a faint declaration (no stale allowance)', () => {
    for (const [stem, selectors] of Object.entries(FAINT_ALLOWED)) {
      const source = read(stem);
      const found = [...source.matchAll(FAINT_TEXT)].map((m) => selectorAt(source, m.index ?? 0));
      for (const selector of selectors ?? []) expect(found, stem).toContain(selector);
    }
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/chart/chart-theme.spec.ts --include src/app/ui/chart/plan-lines.spec.ts --include src/app/ui/svg-colour.spec.ts
```

Expected: FAIL. `chart-theme.spec.ts` does not compile (`TICK_FALLBACK_PX` is not exported). `svg-colour.spec.ts`: `sets no readable text in --text-faint` fails for `gauge.ts` (`['.label', '.caption']`), `heat-grid.ts` (`['th', '.n']`), `line-chart.ts` (`['.empty']`), `matrix.ts` (`['th', '.missing']` vs `['.missing']`), `small-multiples.ts` (`['.n']`) and `timeline.ts` (`['.meta']`); every other case passes. `plan-lines.spec.ts`'s new cases pass already (they pin behaviour Phase 6 requires that nothing asserted); that is expected, not a mistake. If a `names no colour keyword` or `calls no colour function` case fails, print the match: it is either a real literal (replace it with the token it stands for and say so in the commit body) or a scanner false positive (fix the regex and add the string to the scanner tests, never an allowance).

- [ ] **Step 4: Implement `TICK_FALLBACK_PX`**

In `$WT/frontend/src/app/ui/chart/chart-theme.ts`, insert directly above the doc comment that begins `/** Chart chrome shared with the other three charts (v54 D5,`:

```ts
/** Tick-text size when `--text-micro` cannot be resolved (a chart mounted
 *  before the stylesheet, or jsdom): the 12px micro floor tokens.css sets
 *  (spec v195 §1.3), so a fallback never paints below the type scale. */
export const TICK_FALLBACK_PX = 12;

```

and in `chartOptions`, old → new:

```ts
      fontSize: tokenPx(CHART_CHROME.tickSize, 11),
```

```ts
      fontSize: tokenPx(CHART_CHROME.tickSize, TICK_FALLBACK_PX),
```

- [ ] **Step 5: Move readable text off `--text-faint` in six primitives**

Re-read each file first; edit by the quoted string. Each edit is one property value, `--text-faint` → `--text-muted`; nothing else on the line changes.

`$WT/frontend/src/app/ui/gauge.ts`, inside the `.label { … }` rule (the block with `text-transform: uppercase;` and `letter-spacing: 0.1em;`): `      color: var(--text-faint);` → `      color: var(--text-muted);`. Then old → new:

```css
    .caption { font-size: var(--text-micro); color: var(--text-faint); text-align: center; }
```

```css
    .caption { font-size: var(--text-micro); color: var(--text-muted); text-align: center; }
```

`$WT/frontend/src/app/ui/line-chart.ts`, old → new:

```css
    .empty { color: var(--text-faint); font-size: var(--text-table); }
```

```css
    .empty { color: var(--text-muted); font-size: var(--text-table); }
```

`$WT/frontend/src/app/ui/matrix.ts`, inside the `th { … }` rule (the block with `text-transform: uppercase;`, `letter-spacing: 0.1em;` and `font-weight: 400;`): `      color: var(--text-faint);` → `      color: var(--text-muted);`. Leave `.missing { color: var(--text-faint); background: none; }` as it is.

`$WT/frontend/src/app/ui/timeline.ts`, old → new:

```css
    .meta { font-size: var(--text-micro); color: var(--text-faint); }
```

```css
    .meta { font-size: var(--text-micro); color: var(--text-muted); }
```

`$WT/frontend/src/app/ui/heat-grid.ts` (minified), two substring replacements, each occurring once:

- `th{font-size:var(--text-micro);color:var(--text-faint);font-weight:400;` → `th{font-size:var(--text-micro);color:var(--text-muted);font-weight:400;`
- `.n{color:var(--text-faint)}` → `.n{color:var(--text-muted)}`

`$WT/frontend/src/app/ui/small-multiples.ts` (minified), one substring replacement, occurring once:

- `.n{color:var(--text-faint)}` → `.n{color:var(--text-muted)}`

Confirm nothing else moved:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" diff --stat -- frontend/src/app/ui/gauge.ts frontend/src/app/ui/heat-grid.ts frontend/src/app/ui/line-chart.ts frontend/src/app/ui/matrix.ts frontend/src/app/ui/small-multiples.ts frontend/src/app/ui/timeline.ts
git -C "$WT" diff -U0 -- frontend/src/app/ui/gauge.ts frontend/src/app/ui/line-chart.ts frontend/src/app/ui/matrix.ts frontend/src/app/ui/timeline.ts | grep "^[-+] "
```

Expected: gauge 2 lines changed, line-chart 1, matrix 1, timeline 1, heat-grid and small-multiples 1 each (their one long line); every `-`/`+` pair differs only in `text-faint` → `text-muted`.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/chart/chart-theme.spec.ts --include src/app/ui/chart/plan-lines.spec.ts --include src/app/ui/svg-colour.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/gauge.spec.ts --include src/app/ui/heat-grid.spec.ts --include src/app/ui/matrix.spec.ts --include src/app/ui/small-multiples.spec.ts --include src/app/ui/timeline.spec.ts --include src/app/ui/line-chart.spec.ts
python "$WT/scripts/dev/testrun.py" file "$WT/tests/charts/test_chart_theme.py"
```

Expected: PASS, `0 failed`, `0 xfailed` on both. `test_chart_theme.py` is unchanged and confirms the Discord theme V195-1/V195-2 left (`THEME` equals the resolved tokens, `STYLE_PINS[-1]` is the `v195` row). If an `--include` path does not exist (a primitive without its own spec), drop that flag; do not create a spec for it.

- [ ] **Step 7: Render the before and after alert images**

`$MAIN` is pre-v195 until V195-36 merges, so its renderer draws the old theme and the branch's draws Graphite. Both runs only read their own tree and write under the branch's gitignored `.superpowers/`.

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
WT=$MAIN/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
OUT="$WT/.superpowers/v195-alert"
for ROOT in "$MAIN" "$WT"; do
  python -c "import sys; sys.path.insert(0, sys.argv[1]); from swingbot.core.charts import chart_style as cs; print(sys.argv[1][-40:], cs.STYLE_VERSION, cs.THEME['bg'], cs.THEME['pos'], cs.THEME['neg'], cs.ENTRY_COLOR)" "$ROOT"
done
python "$MAIN/scripts/dev/render_chart_fixtures.py" --out "$OUT/before"
python "$WT/scripts/dev/render_chart_fixtures.py" --out "$OUT/after"
mkdir -p "$WT/docs/superpowers/results/v195"
cp "$OUT/before/secondary_sources.png" "$WT/docs/superpowers/results/v195/alert-before.png"
cp "$OUT/after/secondary_sources.png" "$WT/docs/superpowers/results/v195/alert-after.png"
python -c "import hashlib, sys; [print(hashlib.sha256(open(p, 'rb').read()).hexdigest()[:16], p) for p in sys.argv[1:]]" "$WT/docs/superpowers/results/v195/alert-before.png" "$WT/docs/superpowers/results/v195/alert-after.png"
git -C "$MAIN" rev-parse --short HEAD
git -C "$WT" rev-parse --short HEAD
```

Expected: the first line (`$MAIN`) prints a `STYLE_VERSION` that does not start with `v195` (`v181 #070b14 #00e5a0 #ff4d5e #4c8dff` unless another plan moved it); the second (`$WT`) prints `v195 #0d0f12 #3fb68b #f06e66 #6ea8fe`. If `$MAIN` already prints `v195…`, v195 is merged and this step is being re-run: stop and report it, never commit two "after" images as a pair. Both renders print one `rendered … .png` line per fixture and exit 0; the digest command prints two different digests. Open both PNGs (Read tool) and note what changed: the ground, the candle colours, the entry line (steel blue `#6ea8fe` in "after"), the dashed target and stop lines.

- [ ] **Step 8: Start the results doc**

Create `$WT/docs/superpowers/results/2026-10-25-v195-layout-audit.md`, filling every `<…>` field from Step 7's output and your reading of the two images:

```markdown
# v195 Graphite — results: alert image and layout audit

**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) Phase 6 (alert image), Phase 7 (layout audit)
**Plan:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](../plans/2026-10-25-v195-graphite-frontend-redesign_0-index.md) — V195-34 (alert image), V195-36 (layout audit, notes)

## Alert image

The same fixture (`scripts/dev/render_chart_fixtures.py`, `secondary_sources`: FVG, volume-profile and EMA targets, Fib and VWAP stops, two targets) rendered by `generate_trade_chart` before and after the palette move. "Before" is `main` at `<main short sha>`; "after" is the branch at `<branch short sha>`.

| | Before | After |
|---|---|---|
| `STYLE_VERSION` | `<main STYLE_VERSION>` | `v195` |
| Ground (`bg`) | `<main bg>` | `#0d0f12` |
| Gain / loss (`pos` / `neg`) | `<main pos>` / `<main neg>` | `#3fb68b` / `#f06e66` |
| Entry line (`ENTRY_COLOR`) | `<main ENTRY_COLOR>` (`chart-1`) | `#6ea8fe` (`accent`, the app's entry colour) |
| File (SHA-256, first 16) | [`v195/alert-before.png`](v195/alert-before.png) (`<digest>`) | [`v195/alert-after.png`](v195/alert-after.png) (`<digest>`) |

![Alert chart before v195](v195/alert-before.png)

![Alert chart after v195](v195/alert-after.png)

What changed, read off the two images: <two or three sentences: the ground, the candles, the entry line, the dashed target and stop lines, anything that reads worse>.

The chart cache keys fold in `STYLE_VERSION` (`swingbot/core/charts/cache.py`), so the bump invalidates the old images by itself and a rollback reads the old keys again (spec § Rollback).

## Layout audit

(Filled by V195-36.)

## Notes

- Charts outside Phase 6's list: `ui/bar-list.ts` and `ui/share-bar.ts` still set their `n` counts in `--text-faint` (correction 13 makes it a rule colour); `ui/scatter.ts` was not scanned. Follow-up, not v195 scope.
```

- [ ] **Step 9: Close**

Close: standard (test: `frontend/src/app/ui/svg-colour.spec.ts`), plus `frontend/src/app/ui/chart/chart-theme.spec.ts`, `frontend/src/app/ui/chart/plan-lines.spec.ts` and `tests/charts/test_chart_theme.py` in step 2 of the close. Two commits, frontend first:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/ui/chart/chart-theme.ts frontend/src/app/ui/chart/chart-theme.spec.ts frontend/src/app/ui/chart/plan-lines.spec.ts frontend/src/app/ui/svg-colour.spec.ts frontend/src/app/ui/gauge.ts frontend/src/app/ui/heat-grid.ts frontend/src/app/ui/line-chart.ts frontend/src/app/ui/matrix.ts frontend/src/app/ui/small-multiples.ts frontend/src/app/ui/timeline.ts
git -C "$WT" commit -m "feat(v195): charts read tokens only -- 12px tick fallback, plan line styles pinned, SVG primitives scanned for chart-local colour and faint text (V195-34)" -m "Spec Phase 6 and correction 13. The canvas chart already took every colour from chartPalette(); its tick-text fallback rises to the 12px micro floor. plan-lines pins entry solid, stop and targets dashed, working stop dotted, on the real palette. svg-colour.spec bans named colours, non-color-mix colour functions, color-mix of literals and --text-faint text in the twelve SVG primitives; gauge, heat-grid, line-chart, matrix, small-multiples and timeline move their labels, counts and captions to --text-muted (the matrix's missing-cell dash stays faint, a disabled glyph)." -m "<Co-Authored-By trailer from the session's attribution reminder>"
git -C "$WT" add docs/superpowers/results/2026-10-25-v195-layout-audit.md docs/superpowers/results/v195/alert-before.png docs/superpowers/results/v195/alert-after.png
git -C "$WT" commit -m "docs(v195): results doc with the before/after Discord alert image (V195-34)" -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

# Phase 7 — Verification and release

### Task V195-35: Layout audit: `ROUTES` gains `/system?tab=providers`; `CHECKS` gains `rail-label` after v194's hint check; pure `railLabelVerdict`; Playwright focus pass over the rail at widths ≥ 640
**Model:** sonnet — a pure verdict with table tests plus a Playwright loop beside v194's hint pass in an existing script; the shape is fixed by spec Phase 7 and the ledger, and the care is in reusing the hint check's geometry rather than writing a second visibility rule.

**Files:**
- Modify: `frontend/scripts/layout-audit-lib.mjs` (`ROUTES`, `CHECKS`; `RAIL_MIN_WIDTH` and `railLabelVerdict` after `hintVerdict`)
- Modify: `frontend/scripts/layout-audit-lib.test.mjs` (imports; the `ROUTES`, `CHECKS` and `countByCheck` tests; new tests at the end)
- Modify: `frontend/scripts/layout-audit.mjs` (header doc; imports; `railEntry`, `railFinding`, `auditRailLabels` after `auditHints`; `auditWidth`)
- Modify: `docs/claude/ui-design.md` (§ Checklist, the layout-audit bullet)
- Modify: `AGENTS.md` (the condensed `ui-design.md` bullet)
- Test: `frontend/scripts/layout-audit-lib.test.mjs`, `tests/hooks/test_codex_mirror.py`

**Interfaces:**
- Consumes: `ROUTES`, `CHECKS`, `FULL_WIDTHS`, `hintVerdict(rect, viewport, hits)`, `countByCheck` (`layout-audit-lib.mjs`, v194); `HINT_SETTLE_MS`, `measureHint(id)`, `auditHints(page, width)`, `auditWidth(width, opts)` (`layout-audit.mjs`, v194); the rail markup (V195-16: `nav.rail a.rail-link[aria-label]`, each followed by an anchored `sb-hint` that sets the link's `aria-describedby` to its popover's id, V195-14); `SYSTEM_TABS` gaining `providers` (V195-22).
- Produces (V195-36 runs them):
  - `ROUTES` member `'/system?tab=providers'` (29 routes, right after `'/system?tab=scan'`).
  - `CHECKS` member `'rail-label'` (ninth, last).
  - `RAIL_MIN_WIDTH = 640` and `railLabelVerdict(entry: { name: string | null | undefined, hintVisible: boolean }) -> { ok: boolean, reason: 'no-name' | 'hint-hidden' | null }` (exported from `layout-audit-lib.mjs`).
  - `auditRailLabels(page, width)` in `layout-audit.mjs`: `[]` below `RAIL_MIN_WIDTH`; otherwise one finding `{ check: 'rail-label', selector: 'nav.rail a.rail-link[href="<href>"]', text: <name>, detail }` per failing entry, or one `no rail entries` finding when the rail has none.

**Decision order.** An entry whose accessible name (`aria-labelledby` text, else `aria-label`, else its text, trimmed) is empty is `no-name`, whatever its label does: a screen-reader user hears nothing either way. A named entry whose label the hint check's own verdict (`measureHint` on the popover its `aria-describedby` names, then `hintVerdict`) does not pass while the entry has keyboard focus is `hint-hidden`; the finding's detail carries `hintVerdict`'s reason (`zero-size` when the label never opened, `covered-center` when something paints over it). Otherwise it passes. Keyboard focus rather than hover, because the spec asks for focus and hover is the hint check's half; a rail at 768 is focused the same way (a tablet with a keyboard). A width with no rail entry at all is a finding too: a check that finds nothing to check must not pass silently. Like `hint`, a `rail-label` finding is fixed, never allow-listed; `validateAllow` is unchanged.

**What changes, and what is already there.** Spec Phase 7: "every rail entry has an accessible name, and its hint is visible when the entry has keyboard focus", appended after v194's `hint`, and the new `?tab=providers` route. v194's `auditHints` opens `sb-hint > button.trigger` only; an anchored rail label has no trigger (V195-14), so it is not covered today and `rail-label` covers it. The gallery's `a.rail-demo` sits outside `nav.rail` and is not counted. The phone (below 640px) navigates by `sb-phone-tab-bar`, whose tabs carry visible labels, so the check skips 390. The pass costs about 0.2s per rail entry per route and width (eleven entries, 29 routes, two widths: roughly two minutes per run); V195-36 records the measured run time.

- [ ] **Step 1: Write the failing tests**

Re-read `$WT/frontend/scripts/layout-audit-lib.test.mjs` first (v194 edited it). Imports, old → new:

```js
import {
  CHECKS, FULL_WIDTHS, ROUTES, classify, countByCheck, dedupe, formatFinding, hintVerdict, inScope, isVisuallyHidden, parseArgs,
  pickIds, resolveRoute, slug, validateAllow, vcenterGeometry,
} from './layout-audit-lib.mjs';
```

```js
import {
  CHECKS, FULL_WIDTHS, RAIL_MIN_WIDTH, ROUTES, classify, countByCheck, dedupe, formatFinding, hintVerdict, inScope, isVisuallyHidden,
  parseArgs, pickIds, railLabelVerdict, resolveRoute, slug, validateAllow, vcenterGeometry,
} from './layout-audit-lib.mjs';
```

The `ROUTES` test's first three lines, old → new:

```js
test('ROUTES visits every route and tab once (spec §2 plus v188 /cancels: 28)', () => {
  assert.equal(ROUTES.length, 28);
  assert.ok(ROUTES.includes('/cancels'));
```

```js
test('ROUTES visits every route and tab once (spec §2, v188 /cancels and v195 ?tab=providers: 29)', () => {
  assert.equal(ROUTES.length, 29);
  assert.ok(ROUTES.includes('/cancels'));
  assert.ok(ROUTES.includes('/system?tab=providers'));
```

The `CHECKS` test, old → new:

```js
test('CHECKS are the spec six plus vcenter and hint (v194 A2), in order', () => {
  assert.deepEqual([...CHECKS], ['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter', 'hint']);
});
```

```js
test('CHECKS are the spec six plus vcenter, hint (v194 A2) and rail-label (v195 Phase 7), in order', () => {
  assert.deepEqual([...CHECKS], ['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter', 'hint', 'rail-label']);
});
```

Inside the `countByCheck` test, old → new:

```js
    { overflow: 0, offscreen: 1, clipped: 0, tap: 2, text: 0, baseline: 0, vcenter: 0, hint: 0 });
```

```js
    { overflow: 0, offscreen: 1, clipped: 0, tap: 2, text: 0, baseline: 0, vcenter: 0, hint: 0, 'rail-label': 0 });
```

Append at the end of the file:

```js

// railLabelVerdict (v195 Phase 7): one icon-rail entry's accessible name, and whether its anchored
// label passed the hint check's own verdict while the entry had keyboard focus.
test('railLabelVerdict: a named entry whose label shows passes', () => {
  assert.deepEqual(railLabelVerdict({ name: 'Dashboard', hintVisible: true }), { ok: true, reason: null });
});

test('railLabelVerdict: an entry with no accessible name fails no-name, whatever its label does', () => {
  for (const name of ['', '   ', null, undefined]) {
    assert.deepEqual(railLabelVerdict({ name, hintVisible: true }), { ok: false, reason: 'no-name' }, String(name));
    assert.deepEqual(railLabelVerdict({ name, hintVisible: false }), { ok: false, reason: 'no-name' }, String(name));
  }
});

test('railLabelVerdict: a named entry whose label stays hidden on focus fails hint-hidden', () => {
  assert.deepEqual(railLabelVerdict({ name: 'Risk', hintVisible: false }), { ok: false, reason: 'hint-hidden' });
});

test('RAIL_MIN_WIDTH: the rail check runs at the tablet and desktop widths, never the phone', () => {
  assert.equal(RAIL_MIN_WIDTH, 640);
  assert.deepEqual(FULL_WIDTHS.filter((width) => width >= RAIL_MIN_WIDTH), [768, 1440]);
});

test('ROUTES: the providers tab sits with the other System tabs', () => {
  assert.equal(ROUTES[ROUTES.indexOf('/system?tab=providers') - 1], '/system?tab=scan');
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test "E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign/frontend/scripts/layout-audit-lib.test.mjs"`
Expected: FAIL. The module exports neither `RAIL_MIN_WIDTH` nor `railLabelVerdict`, so the import is a `SyntaxError` and every test in the file fails to load.

- [ ] **Step 3: Implement in `layout-audit-lib.mjs`**

Re-read the file first. In `ROUTES`, old → new:

```js
  '/system', '/system?tab=logs', '/system?tab=scan',
```

```js
  '/system', '/system?tab=logs', '/system?tab=scan', '/system?tab=providers',
```

`CHECKS`, old → new:

```js
export const CHECKS = Object.freeze(['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter', 'hint']);
```

```js
export const CHECKS = Object.freeze(['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline', 'vcenter', 'hint', 'rail-label']);
```

Directly after `hintVerdict`'s closing `}`, insert:

```js

/** Narrowest width the icon rail shows at: below it (the shell's 639px phone breakpoint) the bottom
 *  tab bar navigates, and its tabs carry visible labels. */
export const RAIL_MIN_WIDTH = 640;

/**
 * The rail-label check's verdict (spec v195 Phase 7) on one icon-rail entry: its accessible name and
 * whether its anchored sb-hint label passed hintVerdict while the entry had keyboard focus
 * (layout-audit.mjs auditRailLabels). No name fails first (a screen reader hears nothing whatever the
 * label does), then a hidden label. Runs in Node on the measured facts, never shipped into the page.
 */
export function railLabelVerdict(entry) {
  if (!String(entry.name ?? '').trim()) return { ok: false, reason: 'no-name' };
  if (!entry.hintVisible) return { ok: false, reason: 'hint-hidden' };
  return { ok: true, reason: null };
}
```

`countByCheck` and `validateAllow` derive from `CHECKS` and need no edit.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test "E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign/frontend/scripts/layout-audit-lib.test.mjs"`
Expected: PASS, every test (the existing ones apart from the three edited assertions, plus 5 new).

- [ ] **Step 5: Drive it from `layout-audit.mjs`**

Re-read the file first (v194 added the hint pass). Header doc, old → new:

```js
 * headless, on browse.mjs's persistent profile, and reports eight checks:
```

```js
 * headless, on browse.mjs's persistent profile, and reports nine checks:
```

After the three `hint` lines of the header (the last ends `(spec v194 A2; the trigger's aria-label names it). Never allowed.`), insert:

```js
 *   rail-label an icon-rail entry (nav.rail a.rail-link; widths >= 640 only, the phone navigates by
 *              its tab bar) with no accessible name, or whose anchored label does not pass the hint
 *              geometry while the entry has keyboard focus (spec v195 Phase 7). Never allowed.
```

Imports, old → new:

```js
  CHECKS, FULL_WIDTHS, MAX_BASELINE_OFFSET_PX, MAX_CENTER_OFFSET_PX, MIN_TAP_PX, MIN_TEXT_PX, ROUTES, TOUCH_MAX_WIDTH,
  classify, countByCheck, dedupe, formatFinding, hintVerdict, inScope, isVisuallyHidden, parseArgs, pickIds, resolveRoute, slug,
  validateAllow, vcenterGeometry,
```

```js
  CHECKS, FULL_WIDTHS, MAX_BASELINE_OFFSET_PX, MAX_CENTER_OFFSET_PX, MIN_TAP_PX, MIN_TEXT_PX, RAIL_MIN_WIDTH, ROUTES, TOUCH_MAX_WIDTH,
  classify, countByCheck, dedupe, formatFinding, hintVerdict, inScope, isVisuallyHidden, parseArgs, pickIds, railLabelVerdict,
  resolveRoute, slug, validateAllow, vcenterGeometry,
```

Directly after `auditHints`'s closing `}` (before `/** Same page-ready rule as browse.mjs ...`), insert:

```js
/** Runs inside the page (locator.evaluate): a rail link's accessible name, href and the id of the
 *  label describing it. Name precedence as the accessibility tree has it: aria-labelledby, aria-label, text. */
function railEntry(link) {
  const labelledBy = (link.getAttribute('aria-labelledby') ?? '').split(/\s+/).filter(Boolean)
    .map((id) => document.getElementById(id)?.textContent ?? '').join(' ').trim();
  const name = labelledBy || (link.getAttribute('aria-label') ?? '').trim() || (link.textContent ?? '').trim();
  return { name, href: link.getAttribute('href') ?? '', describedBy: link.getAttribute('aria-describedby') };
}

const railFinding = (entry, reason, extra) => ({
  check: 'rail-label',
  selector: entry.href ? `nav.rail a.rail-link[href="${entry.href}"]` : 'nav.rail a.rail-link',
  text: entry.name,
  detail: `rail entry ${entry.href || '(none)'}: ${reason}${extra ? ` (${extra})` : ''}`,
});

/**
 * The rail-label check (spec v195 Phase 7): focus every icon-rail entry and require an accessible name
 * and a visible anchored label, judged by the hint check's own geometry (measureHint + hintVerdict) on
 * the popover the link's aria-describedby names, so a clipped or covered label fails here as a hint does
 * there. Skipped below RAIL_MIN_WIDTH (the phone's tab bar navigates). The mouse is parked over the page
 * first: a hovered entry would hold its own label open and mask a focus failure.
 */
async function auditRailLabels(page, width) {
  if (width < RAIL_MIN_WIDTH) return [];
  const links = page.locator('nav.rail a.rail-link');
  const count = await links.count();
  if (count === 0) return [railFinding({ href: '', name: '' }, 'no rail entries found', `width ${width}`)];
  await page.mouse.move(Math.floor(width / 2), 890);
  const findings = [];
  for (let i = 0; i < count; i += 1) {
    const link = links.nth(i);
    const entry = await link.evaluate(railEntry);
    await link.focus();
    await page.waitForTimeout(HINT_SETTLE_MS);
    const geometry = await page.evaluate(measureHint, entry.describedBy);
    const hint = hintVerdict(geometry.rect, geometry.viewport, geometry.hits);
    const verdict = railLabelVerdict({ name: entry.name, hintVisible: hint.ok });
    if (!verdict.ok) findings.push(railFinding(entry, verdict.reason, hint.reason));
    await link.press('Escape').catch(() => undefined);
    await link.evaluate((el) => el.blur());
  }
  return findings;
}

```

`auditWidth`, old → new (the rail pass runs after the hint pass, both after the screenshot, so no shot shows an open label):

```js
      const hints = await auditHints(page, width);
      findings.push(...hints.map((f) => ({ route, width, ...f })));
      console.error(`${route} @${width}: ${raw.length + hints.length} raw finding(s)`);
```

```js
      const hints = await auditHints(page, width);
      const rails = await auditRailLabels(page, width);
      findings.push(...[...hints, ...rails].map((f) => ({ route, width, ...f })));
      console.error(`${route} @${width}: ${raw.length + hints.length + rails.length} raw finding(s)`);
```

`report()` takes the new check from `CHECKS`; no other edit.

- [ ] **Step 6: Syntax-check the driver**

Run: `node --check "E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign/frontend/scripts/layout-audit.mjs"`
Expected: exit 0, no output. The browser half is proven by V195-36's audit run against the replica (it needs the built bundle, the replica and a signed-in profile, which V195-36 sets up).

- [ ] **Step 7: Name the check in the UI checklist and its Codex mirror**

`$WT/docs/claude/ui-design.md`, § Checklist, the layout-audit bullet as V194-16b left it. Old → new:

```markdown
  and at its top-left + 8px; the finding names the trigger's `aria-label`.
  The `hint` check is the only tooltip probe: never an ad-hoc script. It
  runs on every route and tab. A finding is fixed, not allowed;
```

```markdown
  and at its top-left + 8px; the finding names the trigger's `aria-label`.
  The `hint` check is the only tooltip probe: never an ad-hoc script.
  (`rail-label`, v195) every icon-rail entry (`nav.rail a.rail-link`, at
  768 and 1440; the phone navigates by its tab bar) has an accessible name
  and shows its anchored label while it has keyboard focus. The checks run
  on every route and tab. A finding is fixed, not allowed;
```

`$WT/AGENTS.md`, the condensed `ui-design.md` bullet as V194-16b left it. Old → new:

```markdown
  exit 0 (allow-list entries carry a reason and a date); its `hint` check
  opens every `sb-hint` and fails a popover that is off-screen or covered,
  and a `hint` finding is fixed, never allowed.
```

```markdown
  exit 0 (allow-list entries carry a reason and a date); its `hint` check
  opens every `sb-hint` and fails a popover that is off-screen or covered,
  its `rail-label` check fails an icon-rail entry with no accessible name
  or no visible label on keyboard focus, and neither finding is ever allowed.
```

If either old text is not found verbatim (v194 worded it differently), re-read the bullet and insert the same `rail-label` clause directly after the sentence naming the `hint` check; keep the rest unchanged.

Run: `python "E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign/scripts/dev/testrun.py" file "E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign/tests/hooks/test_codex_mirror.py"`
Expected: PASS, `0 failed`. A failure names the drifting section: align the `AGENTS.md` wording, never weaken the test.

- [ ] **Step 8: Close**

Close: standard (test: `frontend/scripts/layout-audit-lib.test.mjs`), plus `tests/hooks/test_codex_mirror.py` in step 2 of the close; no frontend unit run (no `src/` file changes). Two commits:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs frontend/scripts/layout-audit.mjs
git -C "$WT" commit -m "feat(v195): layout audit rail-label check and the System providers route (V195-35)" -m "Spec Phase 7. rail-label (ninth check, after v194's hint) focuses every nav.rail a.rail-link at widths >= 640 and fails an entry with no accessible name or whose anchored label does not pass the hint check's geometry; a width with no rail entries is a finding too. ROUTES gains /system?tab=providers (29)." -m "<Co-Authored-By trailer from the session's attribution reminder>"
git -C "$WT" add docs/claude/ui-design.md AGENTS.md
git -C "$WT" commit -m "docs(v195): ui-design checklist names the rail-label audit check, AGENTS.md mirror (V195-35)" -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

### Task V195-36: Full suite; local layout audit at 390/768/1440 (every route, `rail-label` included); results doc (audit, orphaned `shell.sidebar`, before/after image); merge to `main`; post-deploy production audit recorded
**Model:** haiku — runs fixed commands and a given script and records their output; any failure, audit finding or failed page check escalates to sonnet per `docs/claude/model-routing.md` (a fix is never made at haiku tier).

**Files:**
- Modify: `docs/superpowers/results/2026-10-25-v195-layout-audit.md` (`## Layout audit` filled; `## Notes` extended; the post-deploy line on `main`)
- Modify: `frontend/scripts/layout-audit.allow.json` (only for a finding the task records as accepted: canvas or third-party chart internals and browser-native parts, each entry with its reason and date; a `hint` or `rail-label` finding is never allowed)
- No other file. A fix a step needs is made after escalation in the file of the task that owns it, committed as `fix(v195): <what> (V195-36)`, with that task's narrow test re-run alone.

**Interfaces:**
- Consumes: `railLabelVerdict`, `RAIL_MIN_WIDTH`, `CHECKS` (nine, ends `'hint', 'rail-label'`), `ROUTES` (29), `resolveRoute` (`layout-audit-lib.mjs`, V195-35); `audit.json` (`ids`, `unallowed`, `allowed`, `stale`) written by `layout-audit.mjs`; the results doc's three sections (V195-34); every ledger task's commit on the branch.
- Produces: the plan's verification record; the merged branch on `main`. `/close-out` runs next (standing permission, `docs/claude/document-lifecycle.md`): it resolves the `Bump:` line (`ui minor, bot patch`) from `VERSION.json`, regenerates `version_history.json`, moves the plan to `implemented/` and removes the worktree. This task does none of those.

**What this task checks beyond the audit.** The handoff from Parts 9–11b names layout points no unit test measures: Calendar's eight totals in the KPI area above the grid at 1440 (behind the digest below 1024px), the calendar day's secondary panels in one column below 1440 and two at 1440, Reports' generated-at marker on the header's right, and the gallery's two secondary panels side by side at 1440. The partner decided (2026-10-27) that detail pages have no in-page back link and the breadcrumb's page crumb leads back, so that is checked on trade, plan, ticker and calendar-day detail at 768 and 1440 (below 640 only the last crumb shows and the tab bar navigates). Every route must render exactly one `h1`, and the killswitch and freshness chips must show on every device. Step 6's script measures all of these with Playwright; Step 7 reads the audit's screenshots for what a script cannot judge.

- [ ] **Step 1: Every ledger task is committed on the branch**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
for id in 1 2 3 4 5 6 7 7b 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35; do
  git -C "$WT" log --oneline main..HEAD | grep -q "(V195-$id)" || echo "MISSING V195-$id"
done
git -C "$WT" status --short
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: no `MISSING` line; the worktree status is empty apart from untracked, gitignored files (`.superpowers/`, `.env`); the main tree shows nothing this plan wrote. A missing id: stop and report it to the controller.

- [ ] **Step 2: Sync the replica, then run the full suite once (dispatch `test-runner`)**

Run the `replicate-prod-db` skill first (partner rule: a task that runs tests against the database syncs production first) into the shared `swing-db` container's `swingbot_prod_replica`; skip it only if a sibling session synced it within the hour and is still testing (the skill says how to tell). Note the time and the alembic revision it reports.

A `.env` inside a checkout breaks the admin tests' login, so the suite runs without one:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
test -f "$WT/.env" && mv "$WT/.env" "$WT/.superpowers/env.aside" && echo "moved .env aside"
git -C "$WT" grep -n "shell\.sidebar" -- frontend/src
```

The grep's output is for Step 8's note (expected: no read or write of the key; at most a comment or a spec asserting it is no longer read).

Dispatch the `test-runner` subagent with worktree `$WT` and these commands, in order: `python "$WT/scripts/dev/testrun.py" full`; `npm --prefix "$WT/frontend" test -- --watch=false`; `npm --prefix "$WT/frontend" run lint`; `node --test "$WT/frontend/scripts/layout-audit-lib.test.mjs"`; `python "$WT/scripts/dev/complexity_gate.py"`.
Expected: `0 failed`, `0 xfailed` on the full suite; the frontend run green; lint clean; `node --test` all pass (its `CHECKS` test lists nine checks, its `ROUTES` test 29); complexity gate exit 0. Pass counts are higher than before v195 (new specs, among them `workspace-consistency`'s 16×2 `it.each` cases and `svg-colour.spec.ts`'s per-primitive cases); a changed pass count is not a failure (`docs/claude/testing-cost.md`). A failure: escalate; the fix goes in the owning task's file and **that test alone** is re-run (`testrun.py file …` or the narrow `--include` run), never the whole suite again. Record the full-suite summary line for Step 8.

- [ ] **Step 3: Rebuild the bundle and serve the replica**

Never audit a stale bundle: `npm run build` alone does not refresh `swingbot/admin/static/app`.

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
WT=$MAIN/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" run build
rm -rf "$WT/swingbot/admin/static/app"
cp -r "$WT/frontend/dist/frontend/browser" "$WT/swingbot/admin/static/app"
if test -f "$WT/.superpowers/env.aside"; then mv "$WT/.superpowers/env.aside" "$WT/.env"; else cp "$MAIN/.env" "$WT/.env"; fi
python - "$WT/.env" <<'PY'
import re
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    text = fh.read()
new, count = re.subn(r"^(DATABASE_URL=.*/)[^/?\s]+", r"\1swingbot_prod_replica", text, count=1, flags=re.M)
with open(path, "w", encoding="utf-8") as fh:
    fh.write(new)
print("DATABASE_URL pointed at the replica:", count == 1)
PY
```

Expected: the build exits 0; the last line prints `DATABASE_URL pointed at the replica: True`. The script prints no value from `.env`; never `cat`, `echo` or `git add` that file. Stop any `admin_ui.py` still running from an earlier task, then start `python "$WT/admin_ui.py"` with `run_in_background` and wait until `curl -s -o /dev/null -w "%{http_code}" http://localhost:1234/api/v1/session` prints `200`. The audit signs its Playwright profile in from `$WT/.env` itself (the values stay inside that process); no headed login is needed.

- [ ] **Step 4: Run the layout audit at three widths**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
date -u
node "$WT/frontend/scripts/layout-audit.mjs" --base http://localhost:1234 --widths 390,768,1440 --out "$WT/.superpowers/v195-audit"; echo "exit=$?"
date -u
node -e "const a=require(process.argv[1]);const by=(c)=>a.unallowed.filter((f)=>f.check===c).length;console.log('unallowed',a.unallowed.length,'hint',by('hint'),'rail-label',by('rail-label'),'allowed',a.allowed.length,'stale',a.stale.length,'ids',JSON.stringify(a.ids));for(const f of a.unallowed)console.log(f.route,f.width,f.check,f.selector,f.detail)" "$WT/.superpowers/v195-audit/audit.json"
```

Expected: `exit=0` and `unallowed 0 hint 0 rail-label 0`. The stderr log shows each route at 768 and 1440 (the rail pass ran; at 390 it is skipped by design). The two `date -u` lines give the run time for Step 8. Exit 2 (`cannot run`) means no session or no data for a placeholder: check `$WT/.env` points at the replica (Step 3) and the replica has a closed trade, a pending or open trade and a ticker with trades.

Any finding: escalate. Fix it in the owning file (a `hint` or `rail-label` finding is always fixed; an allow-list entry is only for canvas or third-party chart internals and browser-native parts, with its reason and today's date), commit `fix(v195): layout audit <check> -- <what> (V195-36)`, re-run the owning spec alone, rebuild (Step 3's first three commands, restart `admin_ui.py`), and re-run this step. Record each fix (commit, check, selector and routes, owning file) for Step 8. `STALE` allow-list lines are reported, not a failure; do not `--prune` here.

- [ ] **Step 5: Write the page-check script**

Create `$WT/.superpowers/v195-page-checks.mjs` (gitignored; not committed). It reuses the audit's signed-in Playwright profile and the ids the audit resolved, so it handles no credentials:

```js
// v195 V195-36 page checks: one h1 per route; the breadcrumb page crumb leads back from every
// detail page (partner decision 2026-10-27: no in-page back links); the killswitch and freshness
// chips on every device; four layout points no unit test measures. Run after the layout audit.
//   node v195-page-checks.mjs <worktree> <base> <audit.json>
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const [WT, BASE = 'http://localhost:1234', AUDIT_JSON] = process.argv.slice(2);
const { chromium } = createRequire(join(WT, 'frontend', 'package.json'))('playwright');
const { ROUTES, resolveRoute } = await import(pathToFileURL(join(WT, 'frontend', 'scripts', 'layout-audit-lib.mjs')).href);
const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const ids = JSON.parse(readFileSync(AUDIT_JSON, 'utf8')).ids;

/** Detail route -> the list its breadcrumb page crumb must lead back to (/plans reads as Trades). */
const DETAIL_BACK = { '/trades/:id': '/trades', '/plans/:plan': '/trades', '/watchlist/:symbol': '/watchlist', '/calendar/:date': '/calendar' };

const results = [];
function record(ok, check, route, width, detail) {
  results.push({ ok, check, route, width });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${check} ${route} @${width}${detail ? `: ${detail}` : ''}`);
}

/** The audit's page-ready rule. */
function ready() {
  const main = document.querySelector('main') ?? document.body;
  return main.innerText.trim().length > 200 && !/Loading/.test(document.body.innerText)
    && document.querySelector('.skeleton') === null;
}

function rects(page, selector) {
  return page.evaluate((sel) => [...document.querySelectorAll(sel)].map((el) => {
    const r = el.getBoundingClientRect();
    return { left: Math.round(r.left), top: Math.round(r.top), right: Math.round(r.right), bottom: Math.round(r.bottom), width: Math.round(r.width) };
  }), selector);
}

async function visit(page, route) {
  await page.goto(`${BASE}${resolveRoute(route, ids)}`, { waitUntil: 'load' });
  await page.waitForFunction(ready, null, { timeout: 30_000 }).catch(() => undefined);
  await page.waitForTimeout(400);
}

async function oneHeading(page, route, width) {
  const n = await page.evaluate(() => ({ all: document.querySelectorAll('h1').length, page: document.querySelectorAll('sb-page h1.title').length }));
  record(n.all === 1 && n.page === 1, 'one-h1', route, width, `h1=${n.all}, sb-page h1.title=${n.page}`);
}

async function topChips(page, route, width) {
  const seen = await page.evaluate(() => ['sb-killswitch-chip', 'sb-freshness-chip'].map((sel) => {
    const r = document.querySelector(sel)?.getBoundingClientRect();
    return [sel, Boolean(r && r.width > 0 && r.height > 0)];
  }));
  record(seen.every(([, shown]) => shown), 'top-chips', route, width, JSON.stringify(seen));
}

async function reportsMarker(page, route, width) {
  const [h1] = await rects(page, 'sb-page h1.title');
  const [marker] = await rects(page, 'sb-page sb-freshness[page-actions]');
  const ok = Boolean(h1 && marker && marker.left >= h1.right && marker.top < h1.bottom);
  record(ok, 'reports-marker-right', route, width, JSON.stringify({ h1, marker }));
}

async function secondaryColumns(page, route, width) {
  const panels = (await rects(page, 'sb-page [page-secondary]')).filter((r) => r.width > 0);
  const columns = new Set(panels.map((r) => r.left)).size;
  const want = width >= 1440 ? 2 : 1;
  record(panels.length >= 2 && columns === want, 'secondary-columns', route, width, `${panels.length} panels in ${columns} column(s), want ${want}`);
}

async function calendarTotals(page, route, width) {
  const tiles = (await rects(page, 'sb-page [page-kpis] sb-stat-strip.totals sb-stat-tile')).filter((r) => r.width > 0);
  const [kpis] = await rects(page, 'sb-page [page-kpis]');
  const [primary] = await rects(page, 'sb-page [page-primary]');
  const ok = tiles.length === 8 && Boolean(kpis && primary) && kpis.bottom <= primary.top + 1;
  record(ok, 'calendar-totals', route, width, `${tiles.length} tiles, kpis bottom ${kpis?.bottom}, primary top ${primary?.top}`);
}

async function crumbBack(page, route, width) {
  const backLinks = await page.evaluate(() => [...document.querySelectorAll('sb-page a')]
    .map((a) => a.textContent.trim()).filter((text) => /^(←|back\b)/i.test(text)));
  const crumb = page.locator('sb-breadcrumb nav[aria-label="Breadcrumb"] a').first();
  if ((await crumb.count()) === 0) {
    record(false, 'crumb-back', route, width, 'no linked page crumb');
    return;
  }
  await crumb.click();
  await page.waitForURL((url) => url.pathname.endsWith(DETAIL_BACK[route]), { timeout: 10_000 }).catch(() => undefined);
  const path = new URL(page.url()).pathname;
  const ok = path.endsWith(DETAIL_BACK[route]) && backLinks.length === 0;
  record(ok, 'crumb-back', route, width, `landed on ${path}; in-page back links ${JSON.stringify(backLinks)}`);
}

async function checkRoute(page, route, width) {
  await visit(page, route);
  await oneHeading(page, route, width);
  if (route === '/dashboard') await topChips(page, route, width);
  if (route === '/reports' && width >= 640) await reportsMarker(page, route, width);
  if (route === '/ui' || route === '/calendar/:date') await secondaryColumns(page, route, width);
  if (route === '/calendar' && width >= 1440) await calendarTotals(page, route, width);
  if (DETAIL_BACK[route] && width >= 640) await crumbBack(page, route, width); // navigates away: last
}

async function signedIn(page) {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  return page.evaluate(async (url) => {
    const res = await fetch(url, { credentials: 'include' });
    return res.ok && (await res.json()).authenticated === true;
  }, `${BASE}/api/v1/session`).catch(() => false);
}

for (const width of [390, 768, 1440]) {
  const context = await chromium.launchPersistentContext(PROFILE, {
    headless: true, viewport: { width, height: 900 }, deviceScaleFactor: 1, serviceWorkers: 'block',
    hasTouch: width <= 1023, isMobile: width < 640,
  });
  try {
    const page = context.pages()[0] ?? (await context.newPage());
    if (!(await signedIn(page))) throw new Error('profile not signed in: run the layout audit first (it signs in from .env)');
    for (const route of ROUTES) await checkRoute(page, route, width);
  } finally {
    await context.close();
  }
}
const failed = results.filter((r) => !r.ok).length;
console.log(`page checks: ${results.length - failed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
```

- [ ] **Step 6: Run the page checks**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
node "$WT/.superpowers/v195-page-checks.mjs" "$WT" http://localhost:1234 "$WT/.superpowers/v195-audit/audit.json"; echo "exit=$?"
```

Expected: `exit=0` and `page checks: <n> passed, 0 failed`, with `one-h1` PASS for all 29 routes at each width (87 lines), `top-chips` at three widths, `reports-marker-right` at 768 and 1440, `secondary-columns` for `/ui` and `/calendar/:date` at three widths, `calendar-totals` at 1440, and `crumb-back` for the four detail routes at 768 and 1440. Any FAIL: escalate. It is either an app defect (fix in the owning task's file as in Step 4, rebuild, re-run Steps 4 and 6) or a selector in this script that no longer matches the markup the owning task produced (fix the script, never the app, and say so in Step 8); a calendar day with fewer than two visible secondary panels on the replica's chosen date is a data shape, recorded as such, not a defect.

- [ ] **Step 7: Read the screenshots**

Open (Read tool) `$WT/.superpowers/v195-audit/<slug>@<width>.png` for `/dashboard`, `/calendar`, `/calendar/:date`, `/reports`, `/risk`, `/system?tab=providers` and `/ui` at 390, 768 and 1440 (the file names come from `slug(route)`; list the directory to find them). Note in one line each: Calendar's totals behind the digest at 390 and 768 and as eight tiles above the grid at 1440; the calendar day's panels one column at 768, two at 1440; Reports' generated-at marker on the header's right at 768 and 1440; the gallery's two secondary panels side by side at 1440; and anything that reads wrong (overlap, a figure under 14px on an order screen, a red button outside a page header). An observation that is a defect escalates like a finding; one that is a taste call goes to the controller as an open question, not a fix.

- [ ] **Step 8: Fill the results doc and commit it**

In `$WT/docs/superpowers/results/2026-10-25-v195-layout-audit.md`, replace the line `(Filled by V195-36.)` under `## Layout audit` with the following, every `<…>` filled from Steps 2–7 (Berlin time is `date -u` + 1h in winter, + 2h in summer):

```markdown
**Run:** <date and Berlin time>, local replica (`/replicate-prod-db` at <time>, alembic `<revision>`), branch at `<short sha>`, <m:ss> for the three widths
**Command:** `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440 --out <dir>`
**Ids the placeholders resolved to:** trade `<id>`, plan `<plan>`, symbol `<symbol>`, day `<date>`
**Full suite:** `<passed> passed, 0 failed, 0 xfailed` (`testrun.py full`); frontend `<n> passed`; lint clean; `layout-audit-lib.test.mjs` <n> passed; complexity gate exit 0

| Run | Unallowed | overflow | offscreen | clipped | tap | text | baseline | vcenter | hint | rail-label | Allowed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| First run | <n> | <n> | <n> | <n> | <n> | <n> | <n> | <n> | <n> | <n> | <n> |
| Final (390, 768, 1440) | **0** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | <n> |

### Fixes made by the audit

<"None." or one row per fix commit:>

| Commit | Check | Selector (routes) | Owning file |
|---|---|---|---|

### Page checks

`<n> passed, 0 failed` (`.superpowers/v195-page-checks.mjs`, not committed): one `h1` on every route at every width; the breadcrumb page crumb leads back to the list from trade, plan, ticker and calendar-day detail at 768 and 1440, with no in-page back link; killswitch and freshness chips at 390, 768 and 1440; Reports' generated-at marker right of the title; gallery and calendar-day secondary panels in two columns at 1440 and one below; Calendar's eight totals above the grid at 1440.

### Read off the screenshots

<one line per Step 7 observation>

### Post-deploy production audit

(Filled after deploy, Step 10.)
```

Then append to the `## Notes` list:

```markdown
- `shell.sidebar`: the server-side preference the old shell read and wrote is orphaned since V195-16 (no read or write in `frontend/src`: <grep result from Step 2, or "no match">). It stays in the stored preferences on purpose: a rollback to the previous image reads it again (spec § Rollback). Drop it in a later cleanup once v195 has soaked.
- `ui.density` (per device, `localStorage`) and `?tab=providers` (an unknown tab falls back to Settings) are ignored by the previous image, so a rollback needs no data step.
- Run time: the `rail-label` pass adds about <s> per route at 768 and 1440 (eleven entries, focus and measure each).
```

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add docs/superpowers/results/2026-10-25-v195-layout-audit.md
git -C "$WT" commit -m "docs(v195): layout audit, page checks and full-suite record (V195-36)" -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

If Step 4 added an allow-list entry, commit `frontend/scripts/layout-audit.allow.json` in its own commit before this one: `chore(v195): layout audit allow-list -- <selector>, <reason> (V195-36)`.

- [ ] **Step 9: Merge to `main` (skill `worktree-lifecycle`)**

Stop the background `admin_ui.py`. Leave `$WT/.env` in place (gitignored; `/close-out` removes the worktree with it). Invoke the `worktree-lifecycle` skill and follow its merge section; its concurrency check comes first:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -8
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline main --since="2 hours ago"
```

Uncommitted changes in the main tree to files the branch touches, or recent `main` commits from another session in `frontend/` or `swingbot/core/charts/`: pause and ask the controller, do not merge. Otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-10-25-v195-graphite-frontend-redesign -m "merge(v195): Graphite -- the whole frontend redesigned" -m "<Co-Authored-By trailer from the session's attribution reminder>"
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -1
```

Expected: a merge commit on `main`. A conflict: `git -C E:/Documents/Private/Projects/Discord-Bot merge --abort` and report it; never resolve a conflict in another session's work. No full suite after the merge (it ran once, in Step 2). Do not bump `VERSION.json`, regenerate `version_history.json`, move the plan or remove the worktree: hand back to the controller, which runs `/close-out` next by standing permission.

- [ ] **Step 10: Post-deploy production audit (after the partner deploys)**

Deploying is not this plan's step. Once the merged build is live on bomeo-capital.com (its footer or `GET /api/v1/version` shows the bumped ui version), from the main tree:

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
OUT="C:/Users/HuyCao/AppData/Local/Temp/v195-prod-audit"
node "$MAIN/frontend/scripts/layout-audit.mjs" --base https://bomeo-capital.com --widths 390,768,1440 --out "$OUT"; echo "exit=$?"
node -e "const a=require(process.argv[1]);const by=(c)=>a.unallowed.filter((f)=>f.check===c).length;console.log('unallowed',a.unallowed.length,'hint',by('hint'),'rail-label',by('rail-label'));for(const f of a.unallowed)console.log(f.route,f.width,f.check,f.selector,f.detail)" "$OUT/audit.json"
```

The audit signs in from `$MAIN/.env` inside its own process (never printed). Expected: `exit=0`, `unallowed 0 hint 0 rail-label 0`. Replace `(Filled after deploy, Step 10.)` in the results doc on `main` with one line (date, deployed ui version, `exit 0, unallowed 0, hint 0, rail-label 0`) and commit it there:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/results/2026-10-25-v195-layout-audit.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v195): post-deploy production layout audit (V195-36)" -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

If the deploy has not happened when Step 9 lands, write `post-deploy: pending deploy (<date>)` there instead, commit it the same way, and report it to the controller as open. A production finding is a new fix, escalated, never a re-run until it passes.

Close: standard (test: `frontend/scripts/layout-audit-lib.test.mjs`) — deviations: Step 2 replaces the narrow run (this is the plan's one full-suite run, which includes the complexity gate); the commits are Step 4's fixes (if any), Step 8's record, Step 9's merge and Step 10's post-deploy line; standard step 1 is Step 1 here and is re-checked before Step 9.
