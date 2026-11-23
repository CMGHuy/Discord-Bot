# v240 — Doctena night, plan 1 of 5: Theme and type — Part 2: shapes and rules

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V240-9" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) (§1 "Mint never marks navigation" and "Every loss carries a true minus", §3, §11; its `### Corrections from the plan 1 code brief` section wins over the text above it)
**Index:** [2026-11-23-v240-doctena-night-theme-and-type_0-index.md](2026-11-23-v240-doctena-night-theme-and-type_0-index.md) holds the Goal, Global Constraints, the "Decisions this index fixes", `## Parallelisation` and the task ledger. Every task below implicitly includes the index's Global Constraints.

Tasks V240-7..V240-12 run after part 1b (V240-6 creates `styleRules`, which
V240-7, V240-9 and V240-10 consume). Conventions for every task in this part:

- Frontend commands run from `frontend/`:
  `cd frontend && npx ng test --watch=false --include <spec> [--include <spec>]`.
  A 60s `Timeout waiting for worker` is machine load: re-run once.
- No task runs the full suite (CI does). Commits are scoped; stage only the
  files the task names.
- File names in gate tables are relative to `frontend/src/`, forward
  slashes, exactly as `allSources()` (`ui/testing/all-sources.ts`) names them.

Two facts this part's writer found in the code, beyond the brief:

1. **`styleRules` stops at an escaped backtick.** `button.ts`'s `styles:`
   literal quotes code in its comments as `` \`icon\` `` (line ~142).
   V240-6's `literalAt` takes the first backtick as the literal's end, so
   every rule after that comment (`:host(.danger-icon)`, `:host(.chip)`,
   `:host(.segment)`, `:host(.link)`, the touch `@media`) is invisible to
   every gate. V240-7 fixes it (a backtick preceded by `\` does not close
   the literal) before its own gate relies on the parser.
2. **Eight components interpolate into their styles** (`${…}` becomes
   `__expr__` in `styleRules`): `bar-list`, `chart-tooltip`, `dot-plot`,
   `histogram`, `line-chart`, `strip-plot` and `waterfall` interpolate
   `CHART_CHROME` token names, and `market-value` interpolates a breakpoint
   into an `@media` prelude. V240-9 adds `withChartChrome(source)`, which
   substitutes the `CHART_CHROME` values before parsing, and pins that no
   rule anywhere keeps an `__expr__` afterwards. So the type and
   money-colour gates see every token read; a new interpolation fails that
   pin with its file named.

# Phase 4: Shapes and type treatment

### Task V240-7: Radius tokens, `--pill-radius`, thin bars on pills

**Model:** sonnet — token values, a new source gate and a parser fix, each pinned by tests across several files; no judgement call beyond the table below.

**Files:**
- Modify: `frontend/src/styles/tokens.css` (tier-3 radius block ~lines 470–485; the radii comment ~lines 320–325)
- Modify: `frontend/src/app/ui/tokens.spec.ts` (`REQUIRED` ~line 93; `defines the four radius targets` ~line 477; `VALUES` ~line 511)
- Modify: `frontend/src/app/ui/chip.spec.ts` (the comment above `Chip is flat (v195 Phase 2)`, ~line 76)
- Create: `frontend/src/app/ui/radius.spec.ts`
- Modify: `frontend/src/app/ui/testing/style-rules.ts` (`literalAt`: escaped backticks)
- Modify: `frontend/src/app/ui/testing/style-rules.spec.ts` (two tests)
- Modify: `frontend/src/app/ui/layout.ts` (`.drag-handle`, line ~557)
- Modify: `frontend/src/app/ui/magnitude.ts` (`:host` line 25, `.bar` line 30)
- Modify: `frontend/src/app/shell/scan-progress.css` (`.track`, line ~37)
- Modify: `frontend/src/app/ui/chart-tooltip.ts` (`.swatch` inside the one-line `styles:`, line 27)
- Modify: `frontend/src/app/ui/status-cell.ts` (`.track`, line ~132)
- Modify: `frontend/src/app/ui/status-indicator.ts` (`.track`, line ~86)
- Modify: `tests/charts/resolved_tokens.json` (regenerated)

**Interfaces:**
- Consumes: `styleRules(name, source): StyleRule[]` and `StyleRule` from
  `frontend/src/app/ui/testing/style-rules.ts` (V240-6); `allSources()`
  from `frontend/src/app/ui/testing/all-sources.ts`; `resolveToken` from
  `frontend/src/app/ui/testing/resolve-token.ts`.
- Produces: token `--pill-radius: 999px` (bare `:root`, tier 3);
  `--chip-radius: var(--pill-radius)`. `styleRules` now reads past an
  escaped backtick inside a `styles:` literal (V240-9 and V240-10 rely on
  it: `button.ts` is only fully visible after this task).

Why: spec v240 §3 moves the four radius targets to doctena's shapes
(10px panels, 12px controls, pill chips, 6px cells) and adds
`--pill-radius`, because the primitives radius gate bans px literals in
components. "Bars and tracks under 6px tall use `--pill-radius`": a 6px
corner on a 3px bar is clamped to a half-height round end in some engines
and drawn as a lozenge in others, so the token says what is meant. The new
gate (`radius.spec.ts`) finds every rule that reads `--radius-sm` and
declares a px `height` under 6. Today that is six rules, plus magnitude's
`.bar`, which is `height: 100%` of its 3px host and moves with it. V240-6's
parser stops at an escaped backtick (part header, fact 1); the fix lands
here because this is the first gate in this part that scans every file.

The six thin-bar rules (scan at `4bf4df0c`):

| File | Rule | Height |
|---|---|---|
| `app/ui/layout.ts` | `.drag-handle` | 4px |
| `app/ui/magnitude.ts` | `:host` | 3px |
| `app/shell/scan-progress.css` | `.track` | 3px |
| `app/ui/chart-tooltip.ts` | `.swatch` | 2px |
| `app/ui/status-cell.ts` | `.track` | 4px |
| `app/ui/status-indicator.ts` | `.track` | 3px |

- [ ] **Step 1: Write the failing parser tests (escaped backtick)**

In `frontend/src/app/ui/testing/style-rules.spec.ts`, add these two tests
inside `describe('styleRules (v240)', …)`, after the
`"reads a real component: button.ts's :host rule"` test:

```ts
  it('reads past an escaped backtick that a comment quotes inside the literal', () => {
    const ts = 'styles: `\n  /* the \\`icon\\` variant */\n  .a { x: 1; }\n  .b { y: 2; }\n`, x = `.ghost { z: 3; }`';
    expect(styleRules('app/ui/x.ts', ts)).toEqual([
      { selector: '.a', body: 'x: 1;' },
      { selector: '.b', body: 'y: 2;' },
    ]);
  });

  it("reads button.ts's rules after its escaped-backtick comments", () => {
    const source = readFileSync(join(process.cwd(), 'src/app/ui/button.ts'), 'utf8');
    const selectors = styleRules('app/ui/button.ts', source).map((rule) => rule.selector);
    expect(selectors).toContain(':host(.danger-icon)');
    expect(selectors).toContain(':host(.chip)');
    expect(selectors).toContain(':host(.segment)');
    expect(selectors).toContain(':host(.link)');
  });
```

(In the first test the JavaScript string `'\\`'` is a backslash followed by
a backtick, exactly what `button.ts` holds; `x = \`…\`` after the literal
must not be read, because it is not under `styles:`.)

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/testing/style-rules.spec.ts`
Expected: FAIL — the first new test returns `[]` (the literal ends at the
escaped backtick and its text holds no complete rule); the second does not
find `:host(.chip)`.

- [ ] **Step 3: Teach `literalAt` to skip escaped backticks**

In `frontend/src/app/ui/testing/style-rules.ts`, replace `literalAt` with:

```ts
/** The template literal at the first non-separator (space, comma) from `from`, or null. */
function literalAt(source: string, from: number): { text: string; end: number } | null {
  let at = from;
  while (at < source.length && /[\s,]/.test(source[at])) at++;
  if (source[at] !== '`') return null;
  const close = closingBacktick(source, at + 1);
  return close < 0 ? null : { text: source.slice(at + 1, close), end: close + 1 };
}

/** The next unescaped backtick from `from`, or -1. A comment inside a
 *  styles literal may quote code as \`icon\` (button.ts does); that
 *  backtick is escaped and does not end the literal. */
function closingBacktick(source: string, from: number): number {
  let close = source.indexOf('`', from);
  while (close > 0 && source[close - 1] === '\\') close = source.indexOf('`', close + 1);
  return close;
}
```

- [ ] **Step 4: Run the parser spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/testing/style-rules.spec.ts`
Expected: PASS (11 tests).

- [ ] **Step 5: Write the failing token pins**

In `frontend/src/app/ui/tokens.spec.ts`:

1. In `REQUIRED`, directly after `'--chip-radius',` add `'--pill-radius',`.
2. Replace the comment and test `it('defines the four radius targets', …)`
   (~lines 474–483) with:

```ts
  /* v167 §3 supersedes v80 D3's single 2px: four targets, all in tier 3,
   * and the two old tokens are gone so no unclassified corner survives.
   * v240 §3 keeps the four targets and moves them to doctena's shapes:
   * 10px panels, 12px controls, pill chips, 6px cells; --pill-radius is
   * the round end chips and thin bars read. */
  it('defines the four radius targets', () => {
    expect(TIER3).toMatch(/^\s*--panel-radius:\s*10px;/m);
    expect(TIER3).toMatch(/^\s*--control-radius:\s*12px;/m);
    expect(TIER3).toMatch(/^\s*--pill-radius:\s*999px;/m);
    expect(TIER3).toMatch(/^\s*--chip-radius:\s*var\(--pill-radius\);/m);
    expect(TIER3).toMatch(/^\s*--radius-sm:\s*6px;/m);
    expect(CSS).not.toMatch(/^\s*--radius(?:-chip)?:/m);
  });

  it('resolves a chip corner to the pill and a nested panel to 8px (v240 §3)', () => {
    expect(resolveToken('--chip-radius')).toBe('999px');
    expect(resolveToken('--pill-radius')).toBe('999px');
    expect(resolveToken('--panel-inner-radius')).toBe('8px');
  });
```

3. In `VALUES` (describe `v167 §3: the tier-3 component tokens`), set:

```ts
    '--panel-radius': '10px',
    '--control-radius': '12px',
    '--pill-radius': '999px',
    '--chip-radius': 'var(--pill-radius)',
    '--radius-sm': '6px',
```

and `'--panel-inner-radius': '8px',` (replacing `'var(--control-radius)'`).
Keep every other entry.

If `resolveToken` is not yet imported in `tokens.spec.ts` (V240-3 uses it;
check with `grep -n "import { resolveToken" src/app/ui/tokens.spec.ts`), add
`import { resolveToken } from './testing/resolve-token';`.

- [ ] **Step 6: Write the failing thin-bar gate**

Create `frontend/src/app/ui/radius.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { allSources } from './testing/all-sources';
import { StyleRule, styleRules } from './testing/style-rules';

/**
 * Spec v240 §3: --radius-sm is 6px, for swatches and cells. A bar or track
 * under 6px tall takes --pill-radius instead: a 6px corner on a 3px bar is
 * not a shape anyone chose. The gate reads every rule that rounds its
 * corners with --radius-sm and declares a px height; any height under 6px
 * fails. A height in %, rem or a token is not read (a % bar follows its
 * parent, which the gate checks in its own rule).
 */
const THIN_PX = 6;
const RADIUS_SM = /border(?:-[a-z]+)*-radius:\s*var\(--radius-sm\)/;
const PX_HEIGHT = /(?:^|[\s;{])height:\s*(\d+(?:\.\d+)?)px/g;

function thinOnRadiusSm(rule: StyleRule): boolean {
  if (!RADIUS_SM.test(rule.body)) return false;
  return [...rule.body.matchAll(PX_HEIGHT)].some(([, px]) => Number(px) < THIN_PX);
}

function offenders(name: string, source: string): string[] {
  return styleRules(name, source).filter(thinOnRadiusSm).map((rule) => rule.selector);
}

describe('v240 §3: thin bars are pills, not 6px corners', () => {
  it('flags a 3px track on --radius-sm and passes the same track on --pill-radius', () => {
    expect(offenders('a.css', '.t { height: 3px; border-radius: var(--radius-sm); }')).toEqual(['.t']);
    expect(offenders('a.css', '.t { height: 3px; border-radius: var(--pill-radius); }')).toEqual([]);
  });

  it('passes a 6px or taller bar, a min-height and a % height on --radius-sm', () => {
    const css = [
      '.a { height: 6px; border-radius: var(--radius-sm); }',
      '.b { height: 14px; border-radius: var(--radius-sm); }',
      '.c { min-height: 3px; border-radius: var(--radius-sm); }',
      '.d { height: 100%; border-radius: var(--radius-sm); }',
    ].join('\n');
    expect(offenders('a.css', css)).toEqual([]);
  });

  for (const { name, source } of allSources()) {
    it(`${name} rounds no bar under 6px tall with --radius-sm`, () => {
      expect(offenders(name, source)).toEqual([]);
    });
  }

  /* The six rules the gate found when it landed, plus magnitude's .bar,
   * which is height: 100% of its 3px host. */
  const PILLS: [file: string, selector: string][] = [
    ['app/ui/layout.ts', '.drag-handle'],
    ['app/ui/magnitude.ts', ':host'],
    ['app/ui/magnitude.ts', '.bar'],
    ['app/shell/scan-progress.css', '.track'],
    ['app/ui/chart-tooltip.ts', '.swatch'],
    ['app/ui/status-cell.ts', '.track'],
    ['app/ui/status-indicator.ts', '.track'],
  ];

  for (const [file, selector] of PILLS) {
    it(`${file} "${selector}" ends in --pill-radius`, () => {
      const rules = styleRules(file, readFileSync(join(process.cwd(), 'src', file), 'utf8'));
      const rule = rules.find((candidate) => candidate.selector === selector && /radius/.test(candidate.body));
      expect(rule, `${file} ${selector}`).toBeDefined();
      expect(rule!.body).toMatch(/border-radius:\s*var\(--pill-radius\)/);
    });
  }
});
```

In `frontend/src/app/ui/chip.spec.ts`, replace the comment above
`describe('Chip is flat (v195 Phase 2)', …)` with:

```ts
/* v195 Phase 2: a chip is flat. Its corner is the --chip-radius token
 * (V195-3), a pill since v240 §3 (var(--pill-radius)); a quality band is
 * told by its text colour and its label, never by a border mixed from a
 * valence hue. */
```

(The test body still asserts `border-radius: var(--chip-radius);`, which
does not change.)

- [ ] **Step 7: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/radius.spec.ts`
Expected: FAIL — the token pins (values still 6px/4px/4px/2px, no
`--pill-radius`), the six per-file gate rows above, and all seven `PILLS`
rows.

- [ ] **Step 8: Change the tier-3 radius tokens**

In `frontend/src/styles/tokens.css`, replace the four radius lines at the
top of the tier-3 `:root` block (~lines 470–475) with:

```css
  /* The four radius targets (v195 §1.5; v240 §3 values: doctena's shapes).
   * Every border-radius in the app is one of these, --pill-radius, or 50%
   * (status dots), 0 (flush edges) or inherit. */
  --panel-radius: 10px;    /* panels, cards, drawers' inner sections, dialogs */
  --control-radius: 12px;  /* buttons, inputs, selects, segmented controls */
  --pill-radius: 999px;    /* fully round ends: chips, tags, bars and tracks under 6px tall */
  --chip-radius: var(--pill-radius); /* chips and tags are pills (v240 §3) */
  --radius-sm: 6px;        /* cells, swatches, bars and tracks 6px tall or more */
```

In the same block replace `--panel-inner-radius: var(--control-radius);`
with `--panel-inner-radius: 8px;`.

In the radii comment (~lines 320–325), replace

```
   * file (v195 §1.5: --panel-radius 6px, --control-radius 4px, --chip-radius 4px,
   * --radius-sm 2px); --radius and --radius-chip are deleted.
```

with

```
   * file (v240 §3: --panel-radius 10px, --control-radius 12px, --chip-radius
   * the 999px --pill-radius, --radius-sm 6px); --radius and --radius-chip
   * are deleted.
```

- [ ] **Step 9: Put the thin bars on `--pill-radius`**

In each rule of the table above, change `border-radius: var(--radius-sm);`
(`border-radius:var(--radius-sm);` in `chart-tooltip.ts`'s one-line
string) to `border-radius: var(--pill-radius);`
(`border-radius:var(--pill-radius);`). Also change magnitude's `.bar`
(`frontend/src/app/ui/magnitude.ts` line 30), so its two lines read:

```css
    :host { display: block; height: 3px; background: var(--surface-raised); border-radius: var(--pill-radius); }
```

```css
    .bar { display: block; height: 100%; border-radius: var(--pill-radius); background: var(--pos); }
```

and `layout.ts` line ~557 reads:

```css
      .drag-handle { display: block; width: 36px; height: 4px; margin: var(--space-8) auto 0; border-radius: var(--pill-radius); background: var(--border-strong); }
```

Nothing else in these rules changes. `scan-progress.css`'s `.fill` keeps
`border-radius: inherit;`.

- [ ] **Step 10: Regenerate the token fixture**

Run: `python scripts/dev/dump_tokens.py`
Then: `python scripts/dev/dump_tokens.py --check`
Expected: `--check` exits 0. `git diff --stat tests/charts/resolved_tokens.json`
shows the radius entries (`chip-radius` `"999px"`, `control-radius`
`"12px"`, `panel-inner-radius` `"8px"`, `panel-radius` `"10px"`,
`radius-sm` `"6px"`) and a new `pill-radius`, and nothing else.

- [ ] **Step 11: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/tokens.spec.ts --include src/app/ui/radius.spec.ts --include src/app/ui/chip.spec.ts --include src/app/ui/testing/style-rules.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/magnitude.spec.ts --include src/app/ui/status-cell.spec.ts --include src/app/shell/scan-progress.spec.ts --include src/app/ui/chart-tooltip.spec.ts --include src/app/ui/layout.spec.ts`
Expected: PASS. If one of the last five specs pins
`border-radius: var(--radius-sm)` on a rule changed here, update that pin
to `var(--pill-radius)` in this task and stage the spec with the commit.

Run: `python scripts/dev/testrun.py file tests/dev/test_dump_tokens.py`
Expected: PASS (the fixture is current).

- [ ] **Step 12: Commit**

```bash
git add frontend/src/styles/tokens.css frontend/src/app/ui/tokens.spec.ts \
  frontend/src/app/ui/chip.spec.ts frontend/src/app/ui/radius.spec.ts \
  frontend/src/app/ui/testing/style-rules.ts frontend/src/app/ui/testing/style-rules.spec.ts \
  frontend/src/app/ui/layout.ts frontend/src/app/ui/magnitude.ts \
  frontend/src/app/shell/scan-progress.css frontend/src/app/ui/chart-tooltip.ts \
  frontend/src/app/ui/status-cell.ts frontend/src/app/ui/status-indicator.ts \
  tests/charts/resolved_tokens.json
git commit -m "feat(v240): doctena radii -- 10px panels, 12px controls, pill chips, 6px cells; --pill-radius on thin bars, gated; styleRules reads past escaped backticks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V240-8: Uppercase buttons; −0.02em on headings at `--text-title` and above

**Model:** sonnet — two CSS treatments across nine files plus a source gate with a pinned exemption table; mechanical but the gate's table must match the code exactly.

**Files:**
- Modify: `frontend/src/app/ui/button.ts` (`:host` rule lines 51–66; a new reset rule after `:host(.link:not([disabled]):hover)`)
- Modify: `frontend/src/app/ui/button.spec.ts` (new describe at the end)
- Modify: `frontend/src/app/ui/page.ts` (`.title`, line 69)
- Modify: `frontend/src/app/ui/section-head.ts` (`h1`, line 48)
- Modify: `frontend/src/app/ui/section-head.spec.ts` (`sets both heading levels…`, ~lines 86–97)
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts` (`h1`, line 961)
- Modify: `frontend/src/app/workspaces/plans/plan-detail.ts` (`.plan-title`, ~line 295)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (`.trade-title`, ~line 500)
- Modify: `frontend/src/app/workspaces/trades/outcome-strip.ts` (`.tile-value`, line 54)
- Create: `frontend/src/app/ui/headings.spec.ts`

**Interfaces:**
- Consumes: `styleRules`, `StyleRule` from `frontend/src/app/ui/testing/style-rules.ts`
  (V240-6, escaped-backtick fix V240-7 — without it `button.ts`'s reset
  rule is invisible); `allSources()` from `frontend/src/app/ui/testing/all-sources.ts`.
- Produces: nothing later tasks consume.

Why: spec v240 §3 sets `sb-button` text UPPERCASE with +0.04em tracking at
weight 600, as on doctena, and leaves icon buttons alone. Index Decision 6
puts the treatment on `:host` and resets it on the `icon`, `danger-icon`,
`chip`, `segment` and `link` variants (icon controls, filter chips,
segmented tabs and inline links, which doctena does not uppercase). One
combined reset rule does it; `:host(.x)` outranks `:host`, so source order
does not matter. Headings keep weight 600 and gain −0.02em tracking at
`--text-title` and above (Decision 7: the literal `-0.02em`, no new token).

The heading list is the set of rules whose `font-size` is
`var(--text-title)`, found by scanning with `styleRules` at `4bf4df0c`.
The brief listed `ui/layout.ts:541` among them; that rule is the drawer's
`.close` (the `×` glyph at title size), not a heading, so it is exempt and
`layout.ts` is not edited here. `portfolio-value.ts`'s `.figure` already
tracks with `var(--figure-tracking)` (−0.02em) and `login.css`'s `.mark`
already has `letter-spacing: -0.02em`, so both are in the table but need no
edit. `--text-metric` and `--text-hero` set display figures (`figure.ts`,
`stat-tile.ts`, `metric-card.ts`, `gauge.ts`, `risk.ts`,
`runner-endings.ts`, `cancels-summary.ts`), not headings; spec §3 scopes the
tracking to headings, so they are out of this task.

| File | Rule | Today | Change |
|---|---|---|---|
| `app/ui/page.ts` | `.title` | no letter-spacing | add `letter-spacing: -0.02em;` |
| `app/ui/section-head.ts` | `h1` | `letter-spacing: normal;` | `letter-spacing: -0.02em;` |
| `app/workspaces/gallery/gallery.ts` | `h1` | none | add |
| `app/workspaces/plans/plan-detail.ts` | `.plan-title` | none | add |
| `app/workspaces/trades/trade-detail.ts` | `.trade-title` | none | add |
| `app/workspaces/trades/outcome-strip.ts` | `.tile-value` | none | add |
| `app/workspaces/dashboard/panels/portfolio-value.ts` | `.figure` | `var(--figure-tracking)` | none |
| `app/shell/login/login.css` | `.mark` | `-0.02em` | none |

- [ ] **Step 1: Write the failing button pins**

Append to `frontend/src/app/ui/button.spec.ts` (add
`import { styleRules } from './testing/style-rules';` to the imports):

```ts
/* v240 §3 and index Decision 6: a text button reads UPPERCASE with +0.04em
 * tracking at 600, as on doctena. Icon controls, filter chips, segmented
 * tabs and inline links keep sentence case and normal tracking. */
describe('v240: uppercase text buttons', () => {
  const RESET = ':host(.icon), :host(.danger-icon), :host(.chip), :host(.segment), :host(.link)';
  const body = (selector: string) =>
    styleRules('app/ui/button.ts', SOURCE).find((rule) => rule.selector === selector)?.body ?? '';

  it('sets every button in uppercase, +0.04em, weight 600 on :host', () => {
    const host = body(':host');
    expect(host).toContain('text-transform: uppercase;');
    expect(host).toContain('letter-spacing: 0.04em;');
    expect(host).toContain('font-weight: 600;');
  });

  it('resets the icon, danger-icon, chip, segment and link variants in one rule', () => {
    const reset = body(RESET);
    expect(reset).toContain('text-transform: none;');
    expect(reset).toContain('letter-spacing: normal;');
  });

  it('sets text-transform in no other rule, so no variant drifts back to mixed case', () => {
    const setters = styleRules('app/ui/button.ts', SOURCE)
      .filter((rule) => /text-transform:/.test(rule.body))
      .map((rule) => rule.selector);
    expect(setters).toEqual([':host', RESET]);
  });
});
```

- [ ] **Step 2: Write the failing heading gate and update the section-head pin**

Create `frontend/src/app/ui/headings.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { allSources } from './testing/all-sources';
import { styleRules } from './testing/style-rules';

/**
 * Spec v240 §3: headings keep weight 600 and gain −0.02em tracking at
 * --text-title and above (index Decision 7: the literal -0.02em; a display
 * figure's var(--figure-tracking) is the same -0.02em). Every rule set at
 * var(--text-title) is either a heading below, which must track, or a
 * pinned non-heading, so a new title-size rule has to be classified.
 */
const HEADINGS: [file: string, selector: string][] = [
  ['app/shell/login/login.css', '.mark'],
  ['app/ui/page.ts', '.title'],
  ['app/ui/section-head.ts', 'h1'],
  ['app/workspaces/dashboard/panels/portfolio-value.ts', '.figure'],
  ['app/workspaces/gallery/gallery.ts', 'h1'],
  ['app/workspaces/plans/plan-detail.ts', '.plan-title'],
  ['app/workspaces/trades/outcome-strip.ts', '.tile-value'],
  ['app/workspaces/trades/trade-detail.ts', '.trade-title'],
];

/** Title-size rules that are not headings: nothing to tighten. */
const NOT_HEADINGS: [file: string, selector: string, why: string][] = [
  ['app/ui/layout.ts', '.close', "the drawer's close glyph, one character"],
  ['app/ui/figure.ts', '.value', "the @container size step of a display figure; the base .value rule tracks"],
];

const TITLE_SIZE = /(?:^|[\s;{])font-size:\s*var\(--text-title\)/;
const TRACKED = /letter-spacing:\s*(?:-0\.02em|var\(--figure-tracking\))/;
const key = (file: string, selector: string) => `${file} ${selector}`;

const titleRules = allSources().flatMap(({ name, source }) =>
  styleRules(name, source)
    .filter((rule) => TITLE_SIZE.test(rule.body))
    .map((rule) => ({ key: key(name, rule.selector), body: rule.body })));

describe('v240 §3: headings at --text-title track at -0.02em', () => {
  for (const [file, selector] of HEADINGS) {
    it(`${file} "${selector}" tracks at -0.02em`, () => {
      const rule = titleRules.find((candidate) => candidate.key === key(file, selector));
      expect(rule, key(file, selector)).toBeDefined();
      expect(rule!.body).toMatch(TRACKED);
    });
  }

  it('classifies every rule set at --text-title as a heading or a pinned non-heading', () => {
    const known = new Set([...HEADINGS, ...NOT_HEADINGS].map(([file, selector]) => key(file, selector)));
    expect(titleRules.map((rule) => rule.key).filter((found) => !known.has(found))).toEqual([]);
  });

  it('keeps the non-heading list exact: each entry is still a title-size rule', () => {
    for (const [file, selector] of NOT_HEADINGS) {
      expect(titleRules.some((rule) => rule.key === key(file, selector)), key(file, selector)).toBe(true);
    }
  });
});
```

In `frontend/src/app/ui/section-head.spec.ts`, replace the test
`it('sets both heading levels in the UI face at 600, sentence case as given', …)`
with:

```ts
  it('sets both heading levels in the UI face at 600, sentence case as given', () => {
    const h1 = ruleOf(/\sh1 \{[^}]*\}/);
    const h2 = ruleOf(/\sh2 \{[^}]*\}/);
    for (const heading of [h1, h2]) {
      expect(heading).toContain('font-family: var(--font-sans)');
      expect(heading).toContain('font-weight: 600');
      expect(heading).not.toContain('text-transform');
    }
    // v240 §3: -0.02em at --text-title and above; the subhead keeps normal.
    expect(h1).toContain('letter-spacing: -0.02em');
    expect(h2).toContain('letter-spacing: normal');
    expect(h1).toContain('font-size: var(--text-title)');
    expect(h2).toContain('font-size: var(--text-subhead)');
  });
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/button.spec.ts --include src/app/ui/headings.spec.ts --include src/app/ui/section-head.spec.ts`
Expected: FAIL — the three button tests (no `text-transform` anywhere
today), six `HEADINGS` rows (all but `login.css` and `portfolio-value.ts`)
and the section-head `h1` pin. The classification test and the
non-heading test already pass.

- [ ] **Step 4: Uppercase the button and add the reset**

In `frontend/src/app/ui/button.ts`, in the `:host { … }` rule, directly
after `font-weight: 600;` add:

```css
      text-transform: uppercase;
      letter-spacing: 0.04em;
```

Directly after `:host(.link:not([disabled]):hover) { text-decoration: underline; }`
add:

```css

    /* v240 §3 (index Decision 6): doctena uppercases its text buttons only.
       Icon controls, filter chips, segmented tabs and inline links keep the
       label as written. :host(.x) outranks :host, so order is free. */
    :host(.icon), :host(.danger-icon), :host(.chip), :host(.segment), :host(.link) { text-transform: none; letter-spacing: normal; }
```

- [ ] **Step 5: Track the headings**

Apply the table above:

- `frontend/src/app/ui/page.ts` line 69 becomes
  `    .title { margin: 0; color: var(--text); font-size: var(--text-title); font-weight: 600; letter-spacing: -0.02em; line-height: 1.25; }`
- `frontend/src/app/ui/section-head.ts` line 48: in the `h1` rule only,
  `letter-spacing: normal;` becomes `letter-spacing: -0.02em;` (the `h2`
  on line 49 keeps `normal`).
- `frontend/src/app/workspaces/gallery/gallery.ts` line 961 becomes
  `    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; letter-spacing: -0.02em; }`
- `frontend/src/app/workspaces/plans/plan-detail.ts` `.plan-title`
  and `frontend/src/app/workspaces/trades/trade-detail.ts` `.trade-title`:
  directly after `font-weight: 600;` add the line
  `      letter-spacing: -0.02em;`
- `frontend/src/app/workspaces/trades/outcome-strip.ts` line 54 becomes
  `    .tile-value { font-size: var(--text-title); letter-spacing: -0.02em; overflow-wrap: anywhere; }`

- [ ] **Step 6: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/button.spec.ts --include src/app/ui/headings.spec.ts --include src/app/ui/section-head.spec.ts --include src/app/ui/page.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts --include src/app/workspaces/plans/plan-detail.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/trades/outcome-strip.spec.ts --include src/app/ui/text-styles.spec.ts`
Expected: PASS. (`text-styles.spec.ts` scans heading rules for
`text-transform`; none is added to a heading.) If an `--include` names a
spec that does not exist, drop it and re-run.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/button.ts frontend/src/app/ui/button.spec.ts \
  frontend/src/app/ui/page.ts frontend/src/app/ui/section-head.ts \
  frontend/src/app/ui/section-head.spec.ts frontend/src/app/ui/headings.spec.ts \
  frontend/src/app/workspaces/gallery/gallery.ts frontend/src/app/workspaces/plans/plan-detail.ts \
  frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/outcome-strip.ts
git commit -m "feat(v240): uppercase text buttons (+0.04em); -0.02em on headings at --text-title, gated

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


# Phase 5: The type and money-colour gates

### Task V240-9: Type gates: `tabular-nums` on numeric rules, no text in `--text-faint` (with pending lists)

**Model:** sonnet — a table-driven source gate whose two pending lists must match the code exactly, plus a small parser helper; no product code changes.

**Files:**
- Create: `frontend/src/app/ui/type-gates.spec.ts`
- Modify: `frontend/src/app/ui/testing/style-rules.ts` (new export `withChartChrome`)
- Modify: `frontend/src/app/ui/testing/style-rules.spec.ts` (one test)

**Interfaces:**
- Consumes: `styleRules`, `StyleRule` from `frontend/src/app/ui/testing/style-rules.ts`
  (V240-6; escaped-backtick fix V240-7); `allSources()`, `stripComments()`
  from `frontend/src/app/ui/testing/all-sources.ts`; `CHART_CHROME` from
  `frontend/src/app/ui/chart/chart-frame.ts` (exists, line 32).
- Produces:
  - `export function withChartChrome(source: string): string` in
    `frontend/src/app/ui/testing/style-rules.ts` — every
    `${CHART_CHROME.<key>}` replaced by its token name; an unknown key is
    left as written. V240-10 uses it.
  - In `frontend/src/app/ui/type-gates.spec.ts`: `const TABULAR_PENDING:
    ReadonlySet<string>` and `const FAINT_PENDING: ReadonlySet<string>`
    (file names relative to `src/`, as `allSources()` names them), each
    exactly today's offenders. Part 3 (V240-13..V240-15) removes entries
    by area; V240-16 deletes both sets and their "still offends" tests.

Why: Jost is proportional, so a number column only stays aligned through
its `tnum` feature (V240-1 pins it in the font). Every rule that reads
`--font-num`/`--font-mono`, or styles a `.num` cell, therefore carries
`font-variant-numeric: tabular-nums` (index Decision 4: added everywhere,
no exemptions; it changes only digits). `--text-faint` stays a divider
colour under the corrected spec, so no rule may paint text in it: the gate
matches the `color` property exactly (Decision 3), so `border-color`,
`background` and `fill` reads stay legal. Both gates start with a pending
list of today's offenders so this task lands green; the four sweep tasks
empty the lists.

Blind spots, closed here rather than left open:

- **Interpolated styles.** Seven components build style rules with
  `${CHART_CHROME.…}`, which `styleRules` turns into `__expr__`; a token
  read through one is invisible. `withChartChrome` substitutes the real
  token names first (`CHART_CHROME.tickColour` is `--text-muted` today, so
  nothing offends), and a pin fails if any rule still holds `__expr__`
  afterwards, naming the file. `market-value.ts` interpolates only an
  `@media` breakpoint, which is in no rule, so it needs nothing.
- **Inline styles in templates and `.html`.** `styleRules` reads no
  template. A per-file check counts `color: var(--text-faint)` in the whole
  comment-stripped source and requires the count to equal the count inside
  style rules, and forbids a `[style.color]` binding to `--text-faint`.
  None exists today.
- `.html` files hold no style rules (`index.html`'s inline cold-load style
  reads no font or faint token).

Today's offenders (scan with this task's predicates at `4bf4df0c`, after
V240-7's parser fix): `tabular-nums` 66 rules in 39 files, `--text-faint`
as text 97 rules in 46 files. They match the index's snapshot.

- [ ] **Step 1: Write the failing `withChartChrome` test**

In `frontend/src/app/ui/testing/style-rules.spec.ts`, change the import to
`import { styleRules, withChartChrome } from './style-rules';`, add
`import { CHART_CHROME } from '../chart/chart-frame';`, and add inside the
describe:

```ts
  it('withChartChrome puts the CHART_CHROME token names back before parsing', () => {
    const ts = 'styles:`.label{color:var(${CHART_CHROME.tickColour});font-size:var(${CHART_CHROME.tickSize})}`';
    expect(styleRules('app/ui/x.ts', withChartChrome(ts))).toEqual([
      { selector: '.label', body: `color:var(${CHART_CHROME.tickColour});font-size:var(${CHART_CHROME.tickSize})` },
    ]);
    expect(withChartChrome('a ${CHART_CHROME.nope} b')).toBe('a ${CHART_CHROME.nope} b');
    expect(withChartChrome('a ${BREAKPOINTS.sm - 1} b')).toBe('a ${BREAKPOINTS.sm - 1} b');
  });
```

(The `ts` string is single-quoted, so its `${…}` stay literal text; the
expected `body` is a template literal, so it holds the real token names.)

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/testing/style-rules.spec.ts`
Expected: FAIL — `withChartChrome` is not exported.

- [ ] **Step 3: Add `withChartChrome`**

In `frontend/src/app/ui/testing/style-rules.ts`, add below the existing
import:

```ts
import { CHART_CHROME } from '../chart/chart-frame';
```

and append to the file:

```ts
const CHART_CHROME_RE = /\$\{CHART_CHROME\.(\w+)\}/g;

/**
 * The source with every `${CHART_CHROME.<key>}` replaced by the token name
 * it holds (chart-frame.ts), so a gate reads `color:var(--text-muted)`
 * where bar-list.ts and six other charts interpolate it. Any other
 * interpolation, and an unknown key, is left as written (styleRules then
 * turns it into `__expr__`).
 */
export function withChartChrome(source: string): string {
  const chrome: Readonly<Record<string, string>> = CHART_CHROME;
  return source.replace(CHART_CHROME_RE, (whole, key: string) => chrome[key] ?? whole);
}
```

`chart-frame.ts` has no runtime imports of its own (its header says so),
so importing it into a test helper pulls in nothing else.

- [ ] **Step 4: Run the parser spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/testing/style-rules.spec.ts`
Expected: PASS (12 tests).

- [ ] **Step 5: Write the type gates**

Create `frontend/src/app/ui/type-gates.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { allSources, stripComments } from './testing/all-sources';
import { StyleRule, styleRules, withChartChrome } from './testing/style-rules';

/**
 * Spec v240 §2 and §11, two source gates over every style rule in src/
 * (allSources(): .ts styles: literals and .css files; specs and styles/
 * are out):
 *
 * - tabular: Jost is proportional, so a rule that reads --font-num or
 *   --font-mono, or styles a .num cell, sets
 *   `font-variant-numeric: tabular-nums` (index Decision 4: everywhere, no
 *   exemptions; it changes only digits).
 * - faint: --text-faint is a divider colour (the corrected spec §1), so no
 *   rule's `color` reads it; captions and hints use --text-muted (index
 *   Decision 3). border-color, background and fill stay legal.
 *
 * Each gate starts with a pending set of today's offenders. Part 3's sweep
 * tasks remove entries by area and V240-16 deletes both sets. A pending file
 * must still offend, so the sets never hold a fixed file.
 */
const TABULAR_PENDING: ReadonlySet<string> = new Set([
  'app/shell/login/login.css',
  'app/shell/shell.css',
  'app/ui/async.ts',
  'app/ui/chip.ts',
  'app/ui/confidence-cell.ts',
  'app/ui/data-table/data-table.ts',
  'app/ui/hint.ts',
  'app/ui/panel-header.ts',
  'app/ui/plan-cell.ts',
  'app/ui/pnl-cell.ts',
  'app/ui/stat-tile.ts',
  'app/ui/status-cell.ts',
  'app/workspaces/analytics/tabs/tuning.ts',
  'app/workspaces/calendar/calendar.ts',
  'app/workspaces/calendar/day/calendar-day.ts',
  'app/workspaces/calendar/day/day-trade-card.ts',
  'app/workspaces/calendar/day/trade-sparkline.ts',
  'app/workspaces/cancels/cancels-summary.ts',
  'app/workspaces/dashboard/dashboard.ts',
  'app/workspaces/dashboard/panels/market-movers.ts',
  'app/workspaces/dashboard/panels/recent-activity.ts',
  'app/workspaces/dashboard/panels/trading-performance.ts',
  'app/workspaces/dashboard/panels/watchlist-panel.ts',
  'app/workspaces/gallery/gallery.ts',
  'app/workspaces/guide/guide.ts',
  'app/workspaces/plans/plan-detail.ts',
  'app/workspaces/reports/gates-tab.ts',
  'app/workspaces/research/research.ts',
  'app/workspaces/risk/risk.ts',
  'app/workspaces/system/logs-tab.ts',
  'app/workspaces/system/scan-tab.ts',
  'app/workspaces/system/settings-tab.ts',
  'app/workspaces/trades/trade-detail.ts',
  'app/workspaces/trades/trades.ts',
  'app/workspaces/versions/versions.ts',
  'app/workspaces/watchlist/earnings-calendar.ts',
  'app/workspaces/watchlist/ticker-detail.ts',
  'app/workspaces/watchlist/watchlist.ts',
  'styles.css',
]);

const FAINT_PENDING: ReadonlySet<string> = new Set([
  'app/shell/breadcrumb.ts',
  'app/ui/age-hint.ts',
  'app/ui/bar-list.ts',
  'app/ui/button.ts',
  'app/ui/column-picker.ts',
  'app/ui/direction-arrow.ts',
  'app/ui/freshness.ts',
  'app/ui/market-value.ts',
  'app/ui/matrix.ts',
  'app/ui/metric-chip.ts',
  'app/ui/plan-cell.ts',
  'app/ui/pnl-basis.ts',
  'app/ui/share-bar.ts',
  'app/ui/status-cell.ts',
  'app/workspaces/analytics/tabs/benchmark.ts',
  'app/workspaces/analytics/tabs/execution.ts',
  'app/workspaces/analytics/tabs/override-fidelity-panel.ts',
  'app/workspaces/analytics/tabs/overview.ts',
  'app/workspaces/analytics/tabs/partials.ts',
  'app/workspaces/analytics/tabs/pipeline.ts',
  'app/workspaces/analytics/tabs/runner-endings.ts',
  'app/workspaces/analytics/tabs/variance-band-panel.ts',
  'app/workspaces/calendar/calendar.ts',
  'app/workspaces/cancels/cancels-summary.ts',
  'app/workspaces/dashboard/dashboard.ts',
  'app/workspaces/dashboard/panels/equity-candles.ts',
  'app/workspaces/dashboard/panels/exposure-by-horizon.ts',
  'app/workspaces/dashboard/panels/market-movers.ts',
  'app/workspaces/dashboard/panels/recent-activity.ts',
  'app/workspaces/dashboard/panels/watchlist-panel.ts',
  'app/workspaces/guide/guide.ts',
  'app/workspaces/plans/plan-detail.ts',
  'app/workspaces/reports/attribution-tab.ts',
  'app/workspaces/reports/gates-tab.ts',
  'app/workspaces/reports/reports.ts',
  'app/workspaces/research/research.ts',
  'app/workspaces/risk/risk.ts',
  'app/workspaces/system/logs-tab.ts',
  'app/workspaces/system/scan-tab.ts',
  'app/workspaces/system/settings-tab.ts',
  'app/workspaces/trades/trade-detail.ts',
  'app/workspaces/trades/trades.ts',
  'app/workspaces/trades/why/outcome-path.ts',
  'app/workspaces/versions/versions.ts',
  'app/workspaces/watchlist/earnings-calendar.ts',
  'app/workspaces/watchlist/watchlist.ts',
]);

const NUM_FACE = /var\(--font-(?:num|mono)\)/;
const NUM_CELL = /\.num(?![\w-])/;
const TABULAR = /font-variant-numeric:[^;]*tabular-nums/;
const FAINT_TEXT = /(?:^|[\s;{])color\s*:[^;]*var\(--text-faint\)/;

type Gate = {
  id: string;
  rule: string;
  pending: ReadonlySet<string>;
  offends: (rule: StyleRule) => boolean;
};

const GATES: Gate[] = [
  {
    id: 'tabular',
    rule: 'sets tabular-nums on every --font-num, --font-mono and .num rule',
    pending: TABULAR_PENDING,
    offends: (rule) => (NUM_FACE.test(rule.body) || NUM_CELL.test(rule.selector)) && !TABULAR.test(rule.body),
  },
  {
    id: 'faint',
    rule: 'paints no text in --text-faint',
    pending: FAINT_PENDING,
    offends: (rule) => FAINT_TEXT.test(rule.body),
  },
];

/** Every source's style rules, with CHART_CHROME interpolations resolved. */
const SOURCES = allSources().map(({ name, source }) => ({
  name,
  source,
  rules: styleRules(name, withChartChrome(source)),
}));

const offenders = (gate: Gate, rules: StyleRule[]) => rules.filter(gate.offends).map((rule) => rule.selector);

describe('v240 type gates: the predicates', () => {
  const [tabular, faint] = GATES;
  const rules = (css: string) => styleRules('a.css', css);

  it('tabular flags a numeric face or a .num cell without tabular-nums', () => {
    expect(offenders(tabular, rules('.a { font-family: var(--font-num); }'))).toEqual(['.a']);
    expect(offenders(tabular, rules('.b { font-family: var(--font-mono); }'))).toEqual(['.b']);
    expect(offenders(tabular, rules('td.num { text-align: right; }'))).toEqual(['td.num']);
  });

  it('tabular passes the same rules with tabular-nums, and ignores .number and .num-x', () => {
    expect(offenders(tabular, rules('.a { font-family: var(--font-num); font-variant-numeric: tabular-nums; }'))).toEqual([]);
    expect(offenders(tabular, rules('.number { gap: 0; } .num-x { gap: 0; } .c { font-family: var(--font-sans); }'))).toEqual([]);
  });

  it('faint flags color but not border-color, background or fill', () => {
    expect(offenders(faint, rules('.a { color: var(--text-faint); }'))).toEqual(['.a']);
    expect(offenders(faint, rules('.b{gap:0;color:var(--text-faint)}'))).toEqual(['.b']);
    const legal = '.c { border-color: var(--text-faint); background: var(--text-faint); fill: var(--text-faint); }';
    expect(offenders(faint, rules(legal))).toEqual([]);
  });
});

for (const gate of GATES) {
  describe(`v240 type gate: ${gate.id}`, () => {
    for (const { name, rules } of SOURCES) {
      if (gate.pending.has(name)) {
        it(`${name} is pending and still offends (a sweep removes it)`, () => {
          expect(offenders(gate, rules)).not.toEqual([]);
        });
      } else {
        it(`${name} ${gate.rule}`, () => {
          expect(offenders(gate, rules)).toEqual([]);
        });
      }
    }

    it('names only scanned files in its pending set', () => {
      const scanned = new Set(SOURCES.map(({ name }) => name));
      expect([...gate.pending].filter((name) => !scanned.has(name))).toEqual([]);
    });
  });
}

describe('v240 type gates: nothing hides from them', () => {
  /* The seven chart components whose styles interpolate CHART_CHROME. */
  const INTERPOLATED = [
    'app/ui/bar-list.ts',
    'app/ui/chart-tooltip.ts',
    'app/ui/dot-plot.ts',
    'app/ui/histogram.ts',
    'app/ui/line-chart.ts',
    'app/ui/strip-plot.ts',
    'app/ui/waterfall.ts',
  ];
  const holdsExpr = (rules: StyleRule[]) => rules.some((rule) => `${rule.selector} ${rule.body}`.includes('__expr__'));

  it('pins the files whose style rules interpolate, read raw', () => {
    const raw = SOURCES.filter(({ name, source }) => holdsExpr(styleRules(name, source))).map(({ name }) => name);
    expect(raw).toEqual(INTERPOLATED);
  });

  it('leaves no interpolation in any rule once CHART_CHROME is substituted', () => {
    expect(SOURCES.filter(({ rules }) => holdsExpr(rules)).map(({ name }) => name)).toEqual([]);
  });

  const INLINE_FAINT = /(?:^|[\s;{"'])color\s*:\s*var\(--text-faint\)/g;
  const BOUND_FAINT = /\[style\.color\]\s*=\s*"[^"]*--text-faint/;
  const count = (text: string) => (text.match(INLINE_FAINT) ?? []).length;

  for (const { name, source, rules } of SOURCES) {
    it(`${name} paints no template or inline text in --text-faint`, () => {
      const code = stripComments(source);
      const inRules = rules.reduce((n, rule) => n + count(` ${rule.body}`), 0);
      expect(count(code)).toBe(inRules);
      expect(code).not.toMatch(BOUND_FAINT);
    });
  }
});
```

- [ ] **Step 6: Run the gate**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/type-gates.spec.ts`
Expected: PASS. The two pending sets are exactly today's offenders, so
every "still offends" test and every "passes" test is green.

If a test fails, the code moved since `4bf4df0c` (another task, or a
concurrent session): a "passes" failure names a new offender (add it to
the pending set only if it predates this task; otherwise fix the rule in
the same way part 3 does: add `font-variant-numeric: tabular-nums;`, or
`color: var(--text-faint)` → `color: var(--text-muted)`); a "still
offends" failure names a file someone already fixed (remove it from the
set). Never widen a predicate to make a test pass.

- [ ] **Step 7: Prove the gate bites**

Temporarily change `frontend/src/app/ui/age-hint.ts`'s `.age-hint` rule's
`color: var(--text-faint)` to `color: var(--text-muted)` and run Step 6's
command.
Expected: FAIL — `app/ui/age-hint.ts is pending and still offends`.
Revert the change (`git checkout -- frontend/src/app/ui/age-hint.ts`) and
re-run: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/ui/type-gates.spec.ts frontend/src/app/ui/testing/style-rules.ts \
  frontend/src/app/ui/testing/style-rules.spec.ts
git commit -m "test(v240): type gates -- tabular-nums on numeric rules, no text in --text-faint, with pending lists; withChartChrome closes the interpolation blind spot

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V240-10: Money-colour scan: nav, brand, active and focus never read `--pos`/`--neg`

**Model:** sonnet — one table-driven source scan with a single pinned status exemption; the judgement (which rule is status, not focus) is made here and must be pinned exactly.

**Files:**
- Create: `frontend/src/app/ui/money-colour.spec.ts`

**Interfaces:**
- Consumes: `styleRules`, `StyleRule`, `withChartChrome` from
  `frontend/src/app/ui/testing/style-rules.ts` (V240-6, V240-7's
  escaped-backtick fix, V240-9); `allSources()` from
  `frontend/src/app/ui/testing/all-sources.ts`.
- Produces: `const NAV_FILES: readonly string[]` in
  `frontend/src/app/ui/money-colour.spec.ts` (plan 3 appends its tab-bar
  editor file; index Handoff).

Why: the corrected spec §1 keeps `--pos`/`--neg` for money, direction and
good/bad status (errors, danger buttons, the kill-switch, the shock pill,
flashes, the tape) and adds one rule: navigation, the brand, active and
current states and focus rings never read them. In Navy `--pos` is
doctena's mint, the same hue doctena uses for "you are here"; on this
site mint must only ever mean "gain". Index Decision 5 fixes the scan's two
parts:

- (a) any rule anywhere whose selector holds `:focus`, `:focus-visible`,
  `:focus-within`, `[aria-current` or `.active` reads neither token;
- (b) every rule in the nav files reads neither: `app/shell/phone-tab-bar.ts`,
  `app/shell/more-sheet.ts`, `app/shell/section-tabs.ts`,
  `app/shell/breadcrumb.ts`, and the `app/shell/shell.css` rules whose
  selector matches `/rail|brand|wordmark|nav|tab/` (22 rules today, all
  `.rail*`, `.nav`, `.brand*`; `.killswitch-strip` is status and outside
  the filter).

The scan at `4bf4df0c` (after V240-7's parser fix) finds no nav offender
and one rule under (a): `button.ts`'s
`:host(.danger-icon:not([disabled]):hover), :host(.danger-icon:not([disabled]):focus-visible)`,
which turns the quiet delete icon red on hover or keyboard focus. That is
the danger status the spec keeps (index Goal: "danger buttons" stay on
`--neg`), not a focus ring: the ring is `:host(:focus-visible)`'s
`outline: 1px solid var(--accent)`, which this rule does not override.
Swapping it to `--accent` would make a delete control look like a primary
action on focus. So it is the one pinned `STATUS_STATES` entry, held to
two conditions: it still exists and reads `--neg` (the list stays exact),
and it sets no `outline` or `box-shadow` from `--pos`/`--neg` (the ring
stays accent). Nothing else changes; the ledger's "swap any offender to
`--accent`" has no offender to swap.

- [ ] **Step 1: Write the scan**

Create `frontend/src/app/ui/money-colour.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { allSources } from './testing/all-sources';
import { StyleRule, styleRules, withChartChrome } from './testing/style-rules';

/**
 * Spec v240 §1 (corrected): mint never marks navigation. --pos and --neg
 * mean money, direction and good/bad status; navigation, the brand,
 * active and current states and focus rings use --accent. Index
 * Decision 5:
 *  (a) no rule whose selector holds :focus, [aria-current or .active reads
 *      --pos/--neg, anywhere;
 *  (b) no rule in a nav file reads them; in shell.css, the rules whose
 *      selector names the rail, brand, wordmark, nav or a tab.
 */
const NAV_FILES: readonly string[] = [
  'app/shell/breadcrumb.ts',
  'app/shell/more-sheet.ts',
  'app/shell/phone-tab-bar.ts',
  'app/shell/section-tabs.ts',
];

const SHELL_CSS = 'app/shell/shell.css';
const SHELL_NAV_SELECTOR = /rail|brand|wordmark|nav|tab/;
const STATE_SELECTOR = /:focus|\[aria-current|\.active(?![\w-])/;
const MONEY = /var\(--(?:pos|neg)\b/;
const RING_FROM_MONEY = /(?:^|[\s;{])(?:outline(?:-color)?|box-shadow)\s*:[^;]*var\(--(?:pos|neg)\b/;

/** Status that happens to change on focus, never a focus ring: each entry
 *  is a [file, exact selector] the scan lets read --pos/--neg. */
const STATUS_STATES: [file: string, selector: string, why: string][] = [
  [
    'app/ui/button.ts',
    ':host(.danger-icon:not([disabled]):hover), :host(.danger-icon:not([disabled]):focus-visible)',
    'the delete icon turns red on hover or focus: danger status; the ring stays :host(:focus-visible) accent',
  ],
];

const isStatus = (name: string, rule: StyleRule) =>
  STATUS_STATES.some(([file, selector]) => file === name && selector === rule.selector);

function isNavRule(name: string, rule: StyleRule): boolean {
  if (NAV_FILES.includes(name)) return true;
  return name === SHELL_CSS && SHELL_NAV_SELECTOR.test(rule.selector);
}

/** The selectors in one file that break (a) or (b). */
function moneyOffenders(name: string, source: string): string[] {
  return styleRules(name, withChartChrome(source))
    .filter((rule) => MONEY.test(rule.body))
    .filter((rule) => isNavRule(name, rule) || (STATE_SELECTOR.test(rule.selector) && !isStatus(name, rule)))
    .map((rule) => rule.selector);
}

describe('v240: the money-colour scan, on fixtures', () => {
  it('flags a focus ring, an active state and an aria-current link in --pos/--neg anywhere', () => {
    const css = [
      '.x:focus-visible { outline: 1px solid var(--neg); }',
      '.tab.active { color: var(--pos); }',
      'a[aria-current="page"] { border-color: var(--pos-soft); }',
      '.row:focus-within { background: var(--accent-soft); }',
    ].join('\n');
    expect(moneyOffenders('app/ui/x.css', css)).toEqual(['.x:focus-visible', '.tab.active', 'a[aria-current="page"]']);
  });

  it('flags every --pos/--neg rule in a nav file, and only rail/brand/nav/tab rules in shell.css', () => {
    expect(moneyOffenders('app/shell/breadcrumb.ts', 'styles: `.sep { color: var(--neg); }`')).toEqual(['.sep']);
    const shell = '.rail-link { color: var(--pos); }\n.killswitch-strip { color: var(--neg); }';
    expect(moneyOffenders(SHELL_CSS, shell)).toEqual(['.rail-link']);
  });

  it('leaves money and status rules elsewhere alone, and an .active-x class is not .active', () => {
    const css = '.pnl.neg { color: var(--neg); }\n.chip.good { color: var(--pos); }\n.active-row { color: var(--pos); }';
    expect(moneyOffenders('app/ui/x.css', css)).toEqual([]);
  });
});

describe('v240: navigation, brand, active and focus never read --pos/--neg', () => {
  const SOURCES = allSources();

  for (const { name, source } of SOURCES) {
    it(`${name} keeps --pos/--neg off nav, active and focus rules`, () => {
      expect(moneyOffenders(name, source)).toEqual([]);
    });
  }

  it('scans nav files that exist', () => {
    const names = new Set(SOURCES.map(({ name }) => name));
    expect(NAV_FILES.filter((file) => !names.has(file))).toEqual([]);
  });

  it("finds the shell.css nav rules (the selector filter still bites)", () => {
    const shell = SOURCES.find(({ name }) => name === SHELL_CSS)!;
    const navRules = styleRules(SHELL_CSS, shell.source).filter((rule) => SHELL_NAV_SELECTOR.test(rule.selector));
    expect(navRules.map((rule) => rule.selector)).toContain('.rail-link.active');
    expect(navRules.map((rule) => rule.selector)).toContain('.brand .word');
  });

  for (const [file, selector, why] of STATUS_STATES) {
    it(`${file} "${selector}" is still status on --pos/--neg and paints no ring from them (${why})`, () => {
      const source = SOURCES.find(({ name }) => name === file)!.source;
      const rule = styleRules(file, source).find((candidate) => candidate.selector === selector);
      expect(rule, `${file} ${selector}`).toBeDefined();
      expect(rule!.body).toMatch(MONEY);
      expect(rule!.body).not.toMatch(RING_FROM_MONEY);
    });
  }
});
```

(`moneyOffenders` takes any name: a fixture named `….css` is read whole,
a `….ts` one through its `styles:` literal.)

- [ ] **Step 2: Run it**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/money-colour.spec.ts`
Expected: PASS — the fixtures prove the scan flags (a) and (b) and leaves
money and status alone; every source file passes; the one status entry
holds.

If a per-file test fails, a rule reads `--pos`/`--neg` under nav, active
or focus. Change that read to `var(--accent)` (or `var(--accent-soft)` for
a `--pos-soft`/`--neg-soft` fill), update any spec that pins the old
value, and add both files to Step 4's `git add`. Never add a
`STATUS_STATES` entry for a nav file, a focus ring (`outline`,
`box-shadow`) or a current-page marker.

- [ ] **Step 3: Prove the scan bites on real files**

Temporarily add `color: var(--pos);` to the `.rail-link.active` rule in
`frontend/src/app/shell/shell.css`, run
Step 2's command, and expect FAIL on `app/shell/shell.css`. Revert
(`git checkout -- frontend/src/app/shell/shell.css`) and re-run: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/ui/money-colour.spec.ts
git commit -m "test(v240): mint never marks navigation -- nav, brand, active and focus rules never read --pos/--neg (danger-icon focus pinned as status)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

