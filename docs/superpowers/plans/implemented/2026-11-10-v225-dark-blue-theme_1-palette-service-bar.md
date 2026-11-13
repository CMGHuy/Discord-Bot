# v225 — Dark blue theme, part 1: palette, Navy block, service, pre-paint, icon, bar button

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v225 — Dark blue theme](../specs/2026-11-10-v225-dark-blue-theme-design.md)
**Index:** [`_0-index.md`](2026-11-10-v225-dark-blue-theme_0-index.md) — Goal, Architecture, **Global Constraints**, Review Focus, **Parallelisation** and the task ledger live there and bind every task below.

Tasks V225-1..V225-6. Worktree for every task: `.claude/worktrees/2026-11-10-v225-dark-blue-theme` (branch of the same name). Every command below runs from that worktree's root; `ng-test.mjs` takes `frontend` as its project directory. Commit subjects are one line, no body.

# Phase 1 — Tokens

### Task V225-1: Midnight/frost palette, the Navy tier-2 block, fixture regeneration, token pins

**Model:** sonnet — CSS and a test-only helper over an existing resolver, with exact values given; no design judgement left.

**Files:**
- Modify: `frontend/src/styles/palette.css` (bare `:root`, l.37-65)
- Modify: `frontend/src/styles/tokens.css` (header l.1-17 rewritten; new block after the density `@media`, ~l.409)
- Modify: `tests/charts/resolved_tokens.json` (regenerated, never hand-edited)
- Modify: `frontend/src/app/ui/testing/resolve-token.ts` (add `export` to `topLevelBlocks` and `declarations`; nothing else)
- Create: `frontend/src/app/ui/testing/theme-tokens.ts`
- Modify: `frontend/src/app/ui/tokens.spec.ts` (new describe after `v195 §1.1: the Graphite palette`, ~l.358)

**Interfaces:**
- Consumes: `resolve-token.ts` — `STYLE_FILES`, `stripComments`, `parseRoot`, `resolveAll`, `resolveToken`, and (newly exported) `topLevelBlocks(css: string): [string, string][]`, `declarations(body: string): Record<string, string>` (names without `--`).
- Produces (V225-2, V225-3, V225-4 and part 2 rely on these exact names):
  - tier-1 `--midnight-950/900/850/800/750/700/500`, `--midnight-950-a72`, `--frost-100/300/400` in `palette.css`; resolvable through `resolveToken('--midnight-950')` etc. once the fixture is regenerated.
  - selector `:root[data-theme="navy"]` in `tokens.css`.
  - `theme-tokens.ts`: `export type TokenTheme = 'graphite' | 'navy'`; `export const TOKEN_THEMES: readonly TokenTheme[]` (`['graphite', 'navy']`); `export const NAVY_SELECTOR = ':root[data-theme="navy"]'`; `export const GROUND_INK_TOKENS: readonly string[]` (the eleven, `--` prefixed); `export function navyRepoints(css?: string): Record<string, string>` (`'--bg' -> 'var(--midnight-950)'`; default reads `src/styles/tokens.css` from `process.cwd()`; throws unless exactly one Navy block); `export function resolveTokenIn(theme: TokenTheme, name: string): string`.

- [ ] **Step 1: Write the failing token spec**

Add the import and a describe to `frontend/src/app/ui/tokens.spec.ts`, directly after the closing `});` of `describe('v195 §1.1: the Graphite palette'`:

```ts
import { GROUND_INK_TOKENS, NAVY_SELECTOR, navyRepoints, resolveTokenIn } from './testing/theme-tokens';
```

```ts
/**
 * v225: Dark blue (Navy) beside Graphite. One tier-2 block,
 * `:root[data-theme="navy"]`, re-points exactly the ground and ink tokens
 * to the midnight/frost palette; every other colour is shared, so a gain,
 * a loss or a warning reads the same in both themes.
 */
describe('v225: the Navy ground', () => {
  const NAVY: [token: string, palette: string, value: string][] = [
    ['--bg', '--midnight-950', '#070c18'],
    ['--surface', '--midnight-900', '#0c1424'],
    ['--surface-raised', '--midnight-850', '#121c32'],
    ['--surface-overlay', '--midnight-800', '#172440'],
    ['--overlay-dim', '--midnight-950-a72', 'rgba(7, 12, 24, 0.72)'],
    ['--border', '--midnight-750', '#182540'],
    ['--border-strong', '--midnight-700', '#233453'],
    ['--text', '--frost-100', '#e6ecf5'],
    ['--text-secondary', '--frost-300', '#c9d4e3'],
    ['--text-muted', '--frost-400', '#9fb0c8'],
    ['--text-faint', '--midnight-500', '#5f6f8a'],
  ];
  /* Shared by both themes (spec v225 § Palette). --quality-3 is absent on
   * purpose: it is var(--text-secondary), so it follows the ink. */
  const SHARED = [
    '--accent', '--accent-fill', '--accent-fill-hi', '--on-accent',
    '--pos', '--neg', '--warn', '--info',
    '--pos-soft', '--neg-soft', '--warn-soft', '--accent-soft', '--info-soft',
    '--quality-1', '--quality-2', '--quality-4', '--quality-5',
    '--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5', '--chart-6',
    '--scrim-soft', '--shadow-overlay',
  ];
  const NAVY_OPEN = /^:root\[data-theme="navy"\] \{/m;
  const block = CSS.slice(CSS.search(NAVY_OPEN)).match(/\{([^}]*)\}/)?.[1] ?? '';

  it('declares one Navy block, after the tier-2 ground and before the tier-3 banner', () => {
    expect(NAVY_SELECTOR).toBe(':root[data-theme="navy"]');
    expect(stripComments(CSS).match(/:root\[data-theme="navy"\]/g)).toHaveLength(1);
    const at = CSS.search(NAVY_OPEN);
    expect(at).toBeGreaterThan(CSS.search(/^\s*--text-faint:\s*var\(--graphite-500\);/m));
    expect(at).toBeLessThan(CSS.indexOf(TIER3_BANNER));
  });

  it('re-points exactly the ground and ink tokens, and every one of them', () => {
    expect([...GROUND_INK_TOKENS].sort()).toEqual(NAVY.map(([name]) => name).sort());
    expect(Object.keys(navyRepoints()).sort()).toEqual([...GROUND_INK_TOKENS].sort());
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

  it('carries tier-3 tokens built on the ground over to Navy', () => {
    expect(resolveTokenIn('navy', '--panel-bg')).toBe('#0c1424');
  });

  it('keeps the Arctic Navy guard clean of the new palette names', () => {
    const PALETTE = readFileSync(join(process.cwd(), 'src/styles/palette.css'), 'utf8');
    expect(PALETTE).toMatch(/^\s*--midnight-950:\s*#070c18;/m);
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

- [ ] **Step 2: Run it to see it fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/tokens.spec.ts`
Expected: FAIL — the build cannot resolve `./testing/theme-tokens`.

- [ ] **Step 3: Export the two parsing helpers from `resolve-token.ts`**

In `frontend/src/app/ui/testing/resolve-token.ts` change `function topLevelBlocks(` to `export function topLevelBlocks(` and `function declarations(` to `export function declarations(`. No other change in this task (V225-2 adds one docblock line).

- [ ] **Step 4: Create `frontend/src/app/ui/testing/theme-tokens.ts`**

Test-only, beside `resolve-token.ts`; files read from `process.cwd()` like it. No colour literal anywhere in it (it is under `src/`, so the colour gate scans it).

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import {
  STYLE_FILES, declarations, parseRoot, resolveAll, resolveToken, stripComments, topLevelBlocks,
} from './resolve-token';

/**
 * Token values under each admin theme (spec v225). Test-only.
 *
 * resolve-token.ts and scripts/dev/dump_tokens.py read bare `:root` blocks
 * only, so they always answer Graphite -- which is what the jsdom fixture
 * and the Discord chart parity need. This helper layers the one
 * `:root[data-theme="navy"]` block of tokens.css over those `:root` blocks
 * and resolves again, for the specs that must measure Navy (contrast,
 * tokens, the cold-load copy). Never fold this into resolve-token.ts: its
 * Python twin would have to learn the theme too, and the Discord PNGs would
 * then be one resolver change away from Navy.
 */
export type TokenTheme = 'graphite' | 'navy';

export const TOKEN_THEMES: readonly TokenTheme[] = ['graphite', 'navy'];

export const NAVY_SELECTOR = ':root[data-theme="navy"]';

/** The ground and ink: the only tokens the Navy block re-points (tokens.css header). */
export const GROUND_INK_TOKENS: readonly string[] = [
  '--bg', '--surface', '--surface-raised', '--surface-overlay', '--overlay-dim',
  '--border', '--border-strong', '--text', '--text-secondary', '--text-muted', '--text-faint',
];

const read = (file: string) => readFileSync(join(process.cwd(), file), 'utf8');
```

Then implement:
- `navyRepoints(css: string = read(STYLE_FILES[1])): Record<string, string>` — `topLevelBlocks(stripComments(css))` filtered to `selector === NAVY_SELECTOR`; throw `expected one ${NAVY_SELECTOR} block, found ${n}` unless exactly one; return its `declarations(body)` with each name re-prefixed by `--`.
- a private memoised `navyTokens(): Record<string, string>` — `parseRoot` of each `STYLE_FILES` entry in order (as `resolvedTokens()` does), then each `navyRepoints()` entry assigned over it (name without `--`), then `resolveAll(...)`.
- `resolveTokenIn(theme: TokenTheme, name: string): string` — `'graphite'` returns `resolveToken(name)`; `'navy'` strips a leading `--`, throws `${name} is not a token` when absent, else returns `navyTokens()[key]`.

- [ ] **Step 5: Add the tier-1 palette entries**

In `frontend/src/styles/palette.css`, inside the bare `:root`, one declaration per line. After `--graphite-500: #6b7280;` add

```css

  /* v225 Dark blue (Navy) ground, darkest first: tokens.css's
     :root[data-theme="navy"] block re-points the ground to these. */
  --midnight-950: #070c18;
  --midnight-900: #0c1424;
  --midnight-850: #121c32;
  --midnight-800: #172440;
  --midnight-750: #182540;
  --midnight-700: #233453;
  /* rules, dividers and disabled glyphs only -- never text */
  --midnight-500: #5f6f8a;
```

after `--white: #ffffff;` add

```css

  /* v225 Navy ink, blue-tinted to sit on the midnight ground */
  --frost-400: #9fb0c8;
  --frost-300: #c9d4e3;
  --frost-100: #e6ecf5;
```

and after `--graphite-950-a72: rgba(13, 15, 18, 0.72);` add `  --midnight-950-a72: rgba(7, 12, 24, 0.72);`.

In the file's header comment, change "index.html / manifest.webmanifest carry copies of --bg for the cold load" to "index.html / manifest.webmanifest carry copies of --bg for the cold load, and index.html one of the Navy --bg (spec v225)".

- [ ] **Step 6: Add the Navy block and rewrite the `tokens.css` header**

Replace the header paragraph l.7-11 ("**Dark only. There is no light theme ...** ... not adding a media query.") with:

```css
 * **Dark only. Two dark grounds, no light theme** (spec v225,
 * docs/superpowers/specs/2026-11-10-v225-dark-blue-theme-design.md): Black
 * (Graphite, the bare :root below) and Dark blue (Navy), selected by
 * <html data-theme="navy"> -- no attribute, or any other value, is
 * Graphite. There is still no light theme and no `prefers-color-scheme`
 * block; `data-theme` exists for the ground only. ui/theme.service.ts
 * writes it from the per-browser localStorage key ui.theme.
 *
 * The ground and ink are a named list: --bg, --surface, --surface-raised,
 * --surface-overlay, --overlay-dim, --border, --border-strong, --text,
 * --text-secondary, --text-muted, --text-faint. Every token on that list
 * has a Navy value in the :root[data-theme="navy"] block; every token off
 * it is shared by both themes. A new ground or ink token joins the list and
 * gets its Navy value in the same commit (tokens.spec.ts checks both ways).
```

Keep the "The bot's Discord chart PNGs share this palette ..." paragraph and add one sentence to its end: "The PNGs are always Graphite: both resolvers read bare :root blocks only, so the Navy block never reaches the fixture (spec v225)."

Directly after the density `@media (min-width: 1024px) and (pointer: fine) { … }` block (before the `/* Breakpoints are 640 / …` comment), add:

```css

/* v225 -- the Dark blue (Navy) ground, a per-browser choice. Re-points the
 * eleven ground and ink tokens named in the header to the midnight/frost
 * palette and nothing else; var() references only, the hues live in
 * palette.css. Outside the bare :root on purpose -- dump_tokens.py and
 * resolve-token.ts read only `:root`, so the fixture and the Discord PNGs
 * stay Graphite. Never write this selector as part of a `:root, ...` list. */
:root[data-theme="navy"] {
  --bg: var(--midnight-950);
  --surface: var(--midnight-900);
  --surface-raised: var(--midnight-850);
  --surface-overlay: var(--midnight-800);
  --overlay-dim: var(--midnight-950-a72);
  --border: var(--midnight-750);
  --border-strong: var(--midnight-700);
  --text: var(--frost-100);
  --text-secondary: var(--frost-300);
  --text-muted: var(--frost-400);
  --text-faint: var(--midnight-500);
}
```

No brace may appear inside that block's body (V225-2's Python parity test strips it with `[^}]*`). Keep the existing `--text-faint is a RULE AND DIVIDER colour` comment untouched (`contrast.spec.ts` matches it).

- [ ] **Step 7: Regenerate the fixture**

Run: `python scripts/dev/dump_tokens.py` then `python scripts/dev/dump_tokens.py --check`
Expected: `--check` exits 0. `git diff --stat tests/charts/resolved_tokens.json` shows only added lines: the eleven `midnight-*`/`frost-*` keys; no existing key changes value.

- [ ] **Step 8: Run the narrow tests**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/contrast.spec.ts`
Expected: PASS, 0 failed (resolve-token.spec's "reproduces the committed fixture" included; contrast is still Graphite-only until V225-2).

Run: `python scripts/dev/testrun.py file tests/dev/test_dump_tokens.py` and `python scripts/dev/testrun.py file tests/charts/test_chart_theme.py`
Expected: PASS (`STYLE_VERSION` and `chart_style.THEME` untouched).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/styles/palette.css frontend/src/styles/tokens.css tests/charts/resolved_tokens.json frontend/src/app/ui/testing/resolve-token.ts frontend/src/app/ui/testing/theme-tokens.ts frontend/src/app/ui/tokens.spec.ts
git commit -m "feat(v225): midnight/frost palette and the Navy ground block (V225-1)"
```

### Task V225-2: Contrast gates per theme, resolver pairing notes, Discord parity test

**Model:** sonnet — mechanical loop-wrapping of an existing spec plus two small pytest cases; values and names fixed here.

**Files:**
- Modify: `frontend/src/app/ui/contrast.spec.ts` (the three theme-dependent describes, l.40-107)
- Modify: `frontend/src/app/ui/testing/resolve-token.ts` (docblock l.4-22, +1 line; code unchanged)
- Modify: `scripts/dev/dump_tokens.py` (module docstring l.16-21, +1 line; code unchanged)
- Modify: `tests/dev/test_dump_tokens.py` (two new tests, `import re`)

**Interfaces:**
- Consumes (V225-1): `TOKEN_THEMES`, `resolveTokenIn(theme, name)` from `frontend/src/app/ui/testing/theme-tokens.ts`; the `:root[data-theme="navy"] { … }` block in `tokens.css` with no brace in its body.
- Produces: pytest `test_navy_block_is_invisible_to_the_discord_fixture`, `test_parse_root_skips_the_navy_selector`. Nothing later consumes code from this task.

- [ ] **Step 1: Write the failing Python parity tests**

Append to `tests/dev/test_dump_tokens.py` (add `import re` beside `import sys`):

```python
_NAVY_BLOCK = re.compile(r':root\[data-theme="navy"\]\s*\{[^}]*\}')


def test_parse_root_skips_the_navy_selector():
    css = ':root { --a: 1; }\n:root[data-theme="navy"] { --a: 2; --b: 3; }\n'
    assert dt.parse_root(css) == {"a": "1"}


def test_navy_block_is_invisible_to_the_discord_fixture(tmp_path):
    """Spec v225: the Discord PNGs stay Graphite. Two in-memory runs over the
    real palette.css + tokens.css, with and without the Navy block, must give
    the same tokens -- never compared against the committed file, so a
    regenerated fixture cannot hide a resolver that learned the theme."""
    palette_src, tokens_src = (p.read_text(encoding="utf-8") for p in dt.STYLE_FILES)
    assert len(_NAVY_BLOCK.findall(tokens_src)) == 1, "the Navy block moved, was renamed or holds a brace"
    palette = tmp_path / "palette.css"
    with_navy = tmp_path / "tokens-navy.css"
    without_navy = tmp_path / "tokens-graphite.css"
    palette.write_text(palette_src, encoding="utf-8")
    with_navy.write_text(tokens_src, encoding="utf-8")
    without_navy.write_text(_NAVY_BLOCK.sub("", tokens_src), encoding="utf-8")

    navy = dt.resolve_tokens((palette, with_navy))
    assert navy == dt.resolve_tokens((palette, without_navy))
    assert navy["bg"] == navy["graphite-950"]
    assert navy["text"] == navy["grey-100"]
```

- [ ] **Step 2: Run them**

Run: `python scripts/dev/testrun.py file tests/dev/test_dump_tokens.py`
Expected: PASS on top of V225-1 (they pin existing behaviour: the resolver already ignores the selector). If `test_navy_block_is_invisible_to_the_discord_fixture` fails, the block is not where V225-1 put it — fix the block, never the resolver.

- [ ] **Step 3: Add the pairing line to both resolvers**

In `scripts/dev/dump_tokens.py`'s module docstring, after the "Rules (resolve-token.ts mirrors them): … is an error." paragraph, add the line:

```
The `[data-theme]` blocks are deliberately invisible here; never teach this resolver a theme (v225).
```

In `frontend/src/app/ui/testing/resolve-token.ts`'s docblock, after "(resolve-token.spec.ts here, test_chart_theme.py there).", add the line:

```
 * The `[data-theme]` blocks are deliberately invisible here; never teach this resolver a theme (v225).
```

No code change in either file.

- [ ] **Step 4: Make every theme-dependent contrast gate run once per theme**

In `frontend/src/app/ui/contrast.spec.ts` add the import

```ts
import { TOKEN_THEMES, resolveTokenIn } from './testing/theme-tokens';
```

and drop `resolveToken` from the `./testing/resolve-token` import if nothing else uses it. Then rewrite the three describes `'WCAG AA on every text/surface pair'`, `'accent legibility (v80 D1)'` and `'v181: profit/loss figures read on every surface and on their own tint'` so each sits inside `for (const theme of TOKEN_THEMES) { … }`, every `resolveToken(x)` becomes `resolveTokenIn(theme, x)`, and every describe name ends in ` (${theme})`. The `NON_TEXT` documentation check (reads `CSS`, theme-independent) moves out into its own describe, `'--text-faint is documented as non-text'`, that runs once. `'no faint text in the v186 primitives (source scan)'` stays as it is. The first describe becomes:

```ts
for (const theme of TOKEN_THEMES) {
  const tok = (name: string) => resolveTokenIn(theme, name);

  describe(`WCAG AA on every text/surface pair (${theme})`, () => {
    for (const fg of ['--text', '--text-secondary', '--text-muted']) {
      for (const bg of SURFACES) {
        it(`${fg} on ${bg} clears 4.5:1`, () => {
          expect(ratio(tok(fg), tok(bg))).toBeGreaterThanOrEqual(4.5);
        });
      }
    }
  });

  describe(`accent legibility (v80 D1) (${theme})`, () => {
    // the three existing cases, with tok() in place of resolveToken()
  });

  describe(`v181: profit/loss figures read on every surface and on their own tint (${theme})`, () => {
    // the two existing loops, with tok() in place of resolveToken()
  });
}

describe('--text-faint is documented as non-text', () => {
  for (const name of NON_TEXT) {
    it(`${name} is documented as non-text`, () => {
      expect(CSS).toMatch(new RegExp(`${name}[\\s\\S]{0,400}?rule and divider`, 'i'));
    });
  }
});
```

The `over()` helper, `SURFACES`, `NON_TEXT` and every comment stay. Add no gate for `--neg` on `--neg-soft` over `--surface-overlay` (spec § Palette: 4.48:1 in both themes, out of scope), and add one comment line above the v181 soft-tint loop saying so.

- [ ] **Step 5: Run the contrast and resolver specs**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/contrast.spec.ts --include src/app/ui/resolve-token.spec.ts`
Expected: PASS, 0 failed. The contrast test count is the old theme-dependent count doubled (each `it` name now appears once under `(graphite)` and once under `(navy)`); the Navy figures match the spec's table (lowest gated: `--neg` on `--neg-soft` over `--surface-raised`, 4.93).

Run: `python scripts/dev/testrun.py file tests/dev/test_dump_tokens.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/contrast.spec.ts frontend/src/app/ui/testing/resolve-token.ts scripts/dev/dump_tokens.py tests/dev/test_dump_tokens.py
git commit -m "test(v225): contrast gates per theme and the Discord parity pin (V225-2)"
```

# Phase 2 — The preference

### Task V225-3: `ThemeService`: signal, guarded storage, attribute, `theme-color` meta, boot

**Model:** sonnet — a near-copy of `DensityService` with one extra DOM write; the shape is fixed by the ledger.

**Files:**
- Create: `frontend/src/app/ui/theme.service.ts`
- Create: `frontend/src/app/ui/theme.service.spec.ts`
- Modify: `frontend/src/app/app.config.ts` (import beside `DensityService` l.32; initializer after l.121)

**Interfaces:**
- Consumes: `resolveTokenIn` from `ui/testing/theme-tokens.ts` (V225-1) — spec only, to inject the Navy `--bg` without a literal. The service itself has no dependency on V225-1 and may be built beside it; its spec needs V225-1 merged.
- Produces (V225-4, V225-6, V225-7, V225-8, V225-9, V225-10 consume these exact names):
  - `export type Theme = 'graphite' | 'navy'`
  - `export const THEME_PREF_KEY = 'ui.theme'`
  - `export interface ThemeStorage { get(key: string): string | null; set(key: string, value: string): void }`
  - `export const THEME_STORAGE: InjectionToken<ThemeStorage>` (providedIn root, factory = guarded localStorage)
  - `export function readTheme(storage: ThemeStorage): Theme`
  - `@Injectable({ providedIn: 'root' }) export class ThemeService { readonly theme: Signal<Theme>; set(theme: Theme): void; toggle(): void }` — always writes `document.documentElement.dataset['theme']` to the current value (`'graphite'` included), at construction and on every `set`/`toggle`.

- [ ] **Step 1: Write the failing spec `frontend/src/app/ui/theme.service.spec.ts`**

Mirror `density.service.spec.ts` (same imports, `MapStorage`, `refusing`, `serviceWith`). Specific to theme:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { resolveToken } from './testing/resolve-token';
import { resolveTokenIn } from './testing/theme-tokens';
import { THEME_PREF_KEY, THEME_STORAGE, ThemeService, ThemeStorage, readTheme } from './theme.service';

// class MapStorage / const refusing / serviceWith(storage?) exactly as in density.service.spec.ts,
// typed ThemeStorage and providing THEME_STORAGE.

const html = document.documentElement;
const attribute = () => html.dataset['theme'];
let meta: HTMLMetaElement;
let navyStyle: HTMLStyleElement;

beforeEach(() => {
  // jsdom has no theme-color meta and resolves only the flat Graphite fixture:
  // add the meta, and a Navy --bg the way tokens.css would supply it.
  meta = document.createElement('meta');
  meta.name = 'theme-color';
  meta.content = resolveToken('--bg');
  document.head.appendChild(meta);
  navyStyle = document.createElement('style');
  navyStyle.textContent = `:root[data-theme="navy"] { --bg: ${resolveTokenIn('navy', '--bg')}; }`;
  document.head.appendChild(navyStyle);
});

afterEach(() => {
  meta.remove();
  navyStyle.remove();
  delete html.dataset['theme'];
  localStorage.removeItem(THEME_PREF_KEY);
  vi.restoreAllMocks();
});

describe('readTheme (v225)', () => {
  it('defaults to graphite when nothing is stored', () => {
    expect(readTheme(new MapStorage())).toBe('graphite');
  });

  it('restores a stored navy choice', () => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, 'navy');
    expect(readTheme(storage)).toBe('navy');
  });

  it.each(['graphite', 'NAVY', 'navy ', ' navy', '', 'dark', '{"theme":"navy"}'])('reads %j as graphite', (value) => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, value);
    expect(readTheme(storage)).toBe('graphite');
  });

  it('falls back to graphite when the storage throws', () => {
    expect(readTheme(refusing)).toBe('graphite');
  });

  it('stores under the per-browser key ui.theme', () => {
    expect(THEME_PREF_KEY).toBe('ui.theme');
  });
});

describe('ThemeService (v225)', () => {
  it('writes data-theme="graphite" at construction when nothing is stored, and leaves the meta Graphite', () => {
    serviceWith(new MapStorage());
    expect(attribute()).toBe('graphite');
    expect(meta.content).toBe(resolveToken('--bg'));
  });

  it('restores a stored navy choice onto <html> and the theme-color meta', () => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, 'navy');
    const service = serviceWith(storage);
    expect(service.theme()).toBe('navy');
    expect(attribute()).toBe('navy');
    expect(meta.content).toBe(resolveTokenIn('navy', '--bg'));
  });

  it('set() moves the signal, the attribute, the stored key and the meta together', () => {
    const storage = new MapStorage();
    const service = serviceWith(storage);
    service.set('navy');
    expect([service.theme(), attribute(), storage.map.get(THEME_PREF_KEY)]).toEqual(['navy', 'navy', 'navy']);
    expect(meta.content).toBe(resolveTokenIn('navy', '--bg'));
    service.set('graphite');
    expect([service.theme(), attribute(), storage.map.get(THEME_PREF_KEY)]).toEqual(['graphite', 'graphite', 'graphite']);
    expect(meta.content).toBe(resolveToken('--bg'));
  });

  it('toggle() flips between the two themes', () => {
    const service = serviceWith(new MapStorage());
    service.toggle();
    expect(service.theme()).toBe('navy');
    service.toggle();
    expect(service.theme()).toBe('graphite');
  });

  it('does not rewrite a junk stored value until the user chooses', () => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, 'NAVY');
    const service = serviceWith(storage);
    expect(service.theme()).toBe('graphite');
    expect(storage.map.get(THEME_PREF_KEY)).toBe('NAVY');
  });

  it('starts graphite, and still switches for the page life, when storage refuses both calls', () => {
    const service = serviceWith(refusing);
    expect(() => service.set('navy')).not.toThrow();
    expect(service.theme()).toBe('navy');
    expect(attribute()).toBe('navy');
  });

  it('switches without a theme-color meta in the document', () => {
    meta.remove();
    const service = serviceWith(new MapStorage());
    expect(() => service.set('navy')).not.toThrow();
    expect(attribute()).toBe('navy');
  });
});

describe('the default storage is localStorage, guarded', () => {
  it('reads and writes ui.theme through localStorage', () => {
    localStorage.setItem(THEME_PREF_KEY, 'navy');
    const service = serviceWith();
    expect(service.theme()).toBe('navy');
    service.set('graphite');
    expect(localStorage.getItem(THEME_PREF_KEY)).toBe('graphite');
  });

  it('falls back to graphite and keeps working when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('denied', 'SecurityError'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError'); });
    const service = serviceWith();
    expect(service.theme()).toBe('graphite');
    service.set('navy');
    expect(attribute()).toBe('navy');
  });
});

describe('the app boots the theme service', () => {
  it('app.config.ts instantiates ThemeService in an app initializer', () => {
    const config = readFileSync(join(process.cwd(), 'src/app/app.config.ts'), 'utf8');
    expect(config).toContain("import { ThemeService } from './ui/theme.service';");
    expect(config).toContain('provideAppInitializer(() => { inject(ThemeService); })');
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/theme.service.spec.ts`
Expected: FAIL — `./theme.service` does not exist.

- [ ] **Step 3: Create `frontend/src/app/ui/theme.service.ts`**

Copy `density.service.ts`'s structure: `THEME_PREF_KEY`, `ThemeStorage`, a private guarded `localStorageTheme()` (same try/catch shape), `THEME_STORAGE = new InjectionToken<ThemeStorage>('THEME_STORAGE', { providedIn: 'root', factory: localStorageTheme })`, `readTheme()` returning `'navy'` only for the exact string `navy` (inside try/catch, else `'graphite'`), and `ThemeService` with `storage`, `root = inject(DOCUMENT).documentElement`, `current = signal<Theme>(readTheme(this.storage))`, `readonly theme = this.current.asReadonly()`, constructor `apply()`, `set(theme)` (signal, guarded `storage.set`, `apply()`), `toggle()` = `this.set(this.current() === 'navy' ? 'graphite' : 'navy')`.

`apply()` order is fixed:

```ts
  private apply(): void {
    this.root.dataset['theme'] = this.current();
    // The browser chrome follows --bg. Read back, never a literal: the colour
    // gate (primitives.spec.ts) allows no hex in a .ts file.
    const bg = getComputedStyle(this.root).getPropertyValue('--bg').trim();
    const meta = this.root.ownerDocument.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    if (meta && bg) meta.content = bg;
  }
```

The class doc comment states: Black (Graphite) and Dark blue (Navy), spec v225; a per-BROWSER preference kept in localStorage, not `PreferencesStore`, because the partner chose per browser and because index.html's pre-paint script must read it before the bundle parses (`PreferencesStore` loads over HTTP after the shell boots); the plan v21 rule "shell preferences go through PreferencesStore" is about account-level settings and does not cover this one; anything unreadable is Graphite and a junk value is not rewritten until the user chooses; tokens.css owns what `data-theme="navy"` means. No colour literal anywhere in the file.

- [ ] **Step 4: Boot it in `frontend/src/app/app.config.ts`**

Add `import { ThemeService } from './ui/theme.service';` after the `DensityService` import, and after the density initializer:

```ts
    // v225: writes <html data-theme> and the theme-color meta from the
    // per-browser ui.theme preference. index.html's inline script has
    // usually applied a stored Dark blue already; this keeps the two in step
    // and covers a page whose pre-paint script failed.
    provideAppInitializer(() => { inject(ThemeService); }),
```

- [ ] **Step 5: Run the specs**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/theme.service.spec.ts --include src/app/ui/density.service.spec.ts --include src/app/ui/primitives.spec.ts`
Expected: PASS, 0 failed (primitives.spec's colour gate now scans `theme.service.ts` and finds no literal).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/theme.service.ts frontend/src/app/ui/theme.service.spec.ts frontend/src/app/app.config.ts
git commit -m "feat(v225): ThemeService keeps ui.theme, data-theme and the theme-color meta (V225-3)"
```

### Task V225-4: Pre-paint script in `index.html`, colour-gate allow-list, cold-load pins

**Model:** sonnet — a dozen lines of inline script with its exact shape given, plus spec pins; the one judgement (no flash, no throw) is spelled out.

**Files:**
- Modify: `frontend/src/index.html` (between the `theme-color` meta l.28 and the cold-load comment l.43; that comment's wording)
- Modify: `frontend/src/app/ui/primitives.spec.ts` (`HEX_ALLOWLIST` l.141-147; new describe after `the cold-load copies equal the resolved --bg (v167 §7)`, ~l.241)

**Interfaces:**
- Consumes: `resolveToken('--midnight-950')` (V225-1, fixture key), `resolveTokenIn('navy', '--bg')` (V225-1), `THEME_PREF_KEY` (V225-3).
- Produces: the literal `var NAVY_BG = '#070c18';` in the inline script; the injected rule scoped to `html[data-theme="navy"]`. `manifest.webmanifest` is not touched.

- [ ] **Step 1: Write the failing spec changes in `primitives.spec.ts`**

Replace the `index.html` entry of `HEX_ALLOWLIST` (keep one `//` comment line per entry, the "every allowlist entry is justified" check counts them):

```ts
  // The three cold-load copies, in file order: the Graphite theme-color
  // meta, the Navy --bg held once in index.html's pre-paint script (v225),
  // and the Graphite inline html/body background. They paint before any
  // stylesheet has loaded, so they cannot read var(--bg); the cold-load
  // describes below fail the moment one drifts from palette.css.
  ['index.html', ['#0d0f12', '#070c18', '#0d0f12']],
```

Add these imports: `import { resolveTokenIn } from './testing/theme-tokens';` and `import { THEME_PREF_KEY } from './theme.service';` (and `afterEach` from vitest). Then, after the closing `});` of `describe('the cold-load copies equal the resolved --bg (v167 §7)'`:

```ts
/**
 * v225: a browser that chose Dark blue paints Navy from the first frame.
 * index.html's inline script reads ui.theme before the bundle parses and,
 * on exactly 'navy', sets data-theme, the theme-color meta and a Navy
 * ground scoped to html[data-theme="navy"] -- so toggling back to Black
 * later drops it. The manifest stays Graphite.
 */
describe('the Dark blue cold load (v225)', () => {
  const INDEX = readFileSync(join(process.cwd(), 'src/index.html'), 'utf8');
  const script = INDEX.match(/<script>([\s\S]*?)<\/script>/)?.[1] ?? '';
  const html = document.documentElement;
  let meta: HTMLMetaElement;

  const run = () => new Function(script)();
  const injected = () =>
    [...document.head.querySelectorAll('style')].filter((s) => s.textContent!.includes('data-theme="navy"'));

  beforeEach(() => {
    meta = document.createElement('meta');
    meta.name = 'theme-color';
    meta.content = resolveToken('--bg');
    document.head.appendChild(meta);
  });

  afterEach(() => {
    meta.remove();
    injected().forEach((s) => s.remove());
    delete html.dataset['theme'];
    localStorage.removeItem(THEME_PREF_KEY);
    vi.restoreAllMocks();
  });

  it('holds the Navy --bg once, equal to the resolved --midnight-950 and Navy --bg', () => {
    const literal = script.match(/var NAVY_BG = '([^']+)';/)?.[1].toLowerCase();
    expect(literal).toBe(resolveToken('--midnight-950').toLowerCase());
    expect(literal).toBe(resolveTokenIn('navy', '--bg').toLowerCase());
    expect(script.match(/#[0-9a-f]{6}/gi)).toHaveLength(1);
  });

  it('sits after the theme-color meta and before the inline Graphite style', () => {
    const at = INDEX.indexOf('<script>');
    expect(at).toBeGreaterThan(INDEX.indexOf('<meta name="theme-color"'));
    expect(at).toBeLessThan(INDEX.indexOf('<style>html, body {'));
  });

  it(`acts only on exactly 'navy' under ${THEME_PREF_KEY}, inside try/catch`, () => {
    expect(script).toContain(`localStorage.getItem('${THEME_PREF_KEY}') === 'navy'`);
    expect(script).toMatch(/try \{[\s\S]*\} catch \(e\) \{/);
  });

  it('paints Navy when ui.theme is navy: attribute, meta and a scoped ground', () => {
    localStorage.setItem(THEME_PREF_KEY, 'navy');
    run();
    expect(html.dataset['theme']).toBe('navy');
    expect(meta.content.toLowerCase()).toBe(resolveToken('--midnight-950').toLowerCase());
    const rules = injected();
    expect(rules).toHaveLength(1);
    expect(rules[0].textContent).toBe(
      `html[data-theme="navy"], html[data-theme="navy"] body { background: ${resolveToken('--midnight-950')}; }`,
    );
  });

  it.each([null, 'graphite', 'NAVY', 'navy ', ''])('leaves the page Graphite for %j', (stored) => {
    if (stored !== null) localStorage.setItem(THEME_PREF_KEY, stored);
    run();
    expect(html.dataset['theme']).toBeUndefined();
    expect(meta.content).toBe(resolveToken('--bg'));
    expect(injected()).toHaveLength(0);
  });

  it('swallows a throwing localStorage and leaves the page Graphite', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('denied', 'SecurityError'); });
    expect(run).not.toThrow();
    expect(html.dataset['theme']).toBeUndefined();
  });

  it('says beside the cold-load copies that the manifest stays Graphite', () => {
    expect(INDEX).toMatch(/manifest\.webmanifest stays Graphite/);
    const manifest = JSON.parse(readFileSync(join(process.cwd(), 'public/manifest.webmanifest'), 'utf8'));
    expect(manifest.theme_color.toLowerCase()).toBe(resolveToken('--bg').toLowerCase());
  });
});
```

(`beforeEach`, `afterEach` and `vi` join the existing `vitest` import.)

- [ ] **Step 2: Run it to see it fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/primitives.spec.ts`
Expected: FAIL — `index.html declares no colour literal` (expected three literals, found two) and every case in `the Dark blue cold load (v225)` (no `<script>` yet).

- [ ] **Step 3: Add the pre-paint script to `frontend/src/index.html`**

Directly after `<meta name="theme-color" content="#0d0f12">` (and before the iOS comment), insert:

```html
  <!-- v225: a browser that chose Dark blue (localStorage ui.theme = navy,
       written by ui/theme.service.ts) paints Navy from the first frame.
       Runs before the bundle parses; on exactly 'navy' it sets
       data-theme, swaps the theme-color meta above and adds a Navy ground
       scoped to html[data-theme="navy"], so a later switch to Black drops
       it. Any failure leaves the page Graphite and ThemeService applies the
       stored theme on bootstrap. NAVY_BG is a copy of palette.css
       --midnight-950; primitives.spec.ts pins it. -->
  <script>
    (function () {
      var NAVY_BG = '#070c18';
      try {
        if (localStorage.getItem('ui.theme') === 'navy') {
          document.documentElement.setAttribute('data-theme', 'navy');
          var meta = document.querySelector('meta[name="theme-color"]');
          if (meta) meta.setAttribute('content', NAVY_BG);
          var ground = document.createElement('style');
          ground.textContent = 'html[data-theme="navy"], html[data-theme="navy"] body { background: ' + NAVY_BG + '; }';
          document.head.appendChild(ground);
        }
      } catch (e) {
        /* Blocked storage: stay Graphite. */
      }
    })();
  </script>
```

The `querySelector` finds the page's only theme-color meta (the one above). No `//` comments inside the script (the colour gate's comment stripper treats `//` as a comment start).

- [ ] **Step 4: Update the cold-load comment above `<style>html, body { … }</style>`**

In the comment at l.43-56, change "This hex is one of the two colour literals the colour gate deliberately leaves in place" to "This hex is one of the three colour literals the colour gate deliberately leaves in place (the theme-color meta, the Navy NAVY_BG above, and this one)", and append before `-->`:

```
       manifest.webmanifest stays Graphite (spec v225): a manifest is
       static and installed once, so it cannot follow a per-browser choice;
       a Dark blue user's home-screen splash is black for an instant,
       accepted. The manifest is JSON and cannot carry this note itself.
```

Leave the meta and the `<style>html, body { background: #0d0f12; }</style>` lines byte-identical (the v167 §7 regexes read them).

- [ ] **Step 5: Run the specs**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/primitives.spec.ts --include src/app/ui/theme.service.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/index.html frontend/src/app/ui/primitives.spec.ts
git commit -m "feat(v225): pre-paint the Dark blue ground before the bundle loads (V225-4)"
```

# Phase 3 — The bar control

### Task V225-5: `theme` icon glyph

**Model:** haiku — one entry in three exhaustive maps and one spec case, path data given.

**Files:**
- Modify: `frontend/src/app/ui/icon.ts` (`ICON_NAMES` l.21-48, `PATHS` l.56-120, `LABELS` l.123-131)
- Modify: `frontend/src/app/ui/icon.spec.ts` (one case before `never draws two names with the same glyph`)

**Interfaces:**
- Consumes: nothing.
- Produces: `IconName` `'theme'` (in `ICON_NAMES`, `PATHS`, `LABELS` = `'Theme'`); V225-6 renders `<sb-icon name="theme" title="" />`.

- [ ] **Step 1: Write the failing spec case**

In `frontend/src/app/ui/icon.spec.ts`, after `carries the search glyph the top bar and the phone bar use (v195 correction 1)`:

```ts
  it('carries the half-filled circle the theme toggle uses (v225)', () => {
    expect(ICON_NAMES).toContain('theme');
    const path = render('theme').querySelector('svg path')!;
    // An outline circle with its right half hatched solid, drawn in strokes
    // like every other glyph (the svg is fill="none"), never an emoji.
    expect(path.getAttribute('d')).toMatch(/^M8 2a6 6 0 1 0 0 12A6 6 0 0 0 8 2z/);
    expect(render('theme').getAttribute('title')).toBe('Theme');
  });
```

- [ ] **Step 2: Run it to see it fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/icon.spec.ts`
Expected: FAIL — `expected [...] to include 'theme'`.

- [ ] **Step 3: Add the glyph**

In `frontend/src/app/ui/icon.ts`: append `'theme',` after `'search',` in `ICON_NAMES`; add to `PATHS` after `search`:

```ts
  // A circle, half filled: the Black / Dark blue theme toggle (v225). The
  // svg is fill="none", so the right half is solid by seven 1.5px strokes
  // 1.5px apart, each stopping short of the outline for the round caps.
  theme: 'M8 2a6 6 0 1 0 0 12A6 6 0 0 0 8 2z M8 3.5h3.4 M8 5h4.6 M8 6.5h5.2 M8 8h5.4 M8 9.5h5.2 M8 11h4.6 M8 12.5h3.4',
```

and `theme: 'Theme',` at the end of `LABELS` (after `search: 'Search',`). Both records are exhaustive, so a missing entry is a compile error.

- [ ] **Step 4: Run the spec**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/icon.spec.ts`
Expected: PASS, 0 failed (`renders an svg for theme` and `never draws two names with the same glyph` included).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/icon.ts frontend/src/app/ui/icon.spec.ts
git commit -m "feat(v225): half-filled circle icon for the theme toggle (V225-5)"
```

### Task V225-6: Top-bar theme button (tablet/desktop) with a visible pressed state

**Model:** sonnet — a template, CSS and spec change in one component following existing bar patterns; the order pin and copy are fixed here.

**Files:**
- Modify: `frontend/src/app/shell/shell.ts` (imports l.1-40; fields beside `density`, l.289-292)
- Modify: `frontend/src/app/shell/shell.html` (after the palette/search `@if/@else`, before `<sb-profile-menu>`, ~l.101)
- Modify: `frontend/src/app/shell/shell.css` (after the `.palette-trigger` rules, ~l.186)
- Modify: `frontend/src/app/shell/shell.spec.ts` (`shellProviders` l.95-105; a file-level `afterEach`; the cluster describe ~l.718-830; the phone bar pin ~l.870; the desktop bar pin ~l.1310-1322)

**Interfaces:**
- Consumes: `ThemeService` (`theme(): Theme`, `toggle()`), `THEME_STORAGE`, `ThemeStorage` from `frontend/src/app/ui/theme.service.ts` (V225-3); icon name `'theme'` (V225-5).
- Produces (V225-7, V225-11, V225-12 rely on these): `Shell.theme = inject(ThemeService)` (protected); bar element `button.theme-toggle` as a direct child of `header.topbar`, between `button.palette-trigger` and `sb-profile-menu`, followed by its anchored `sb-hint`; `aria-label="Dark blue theme"`, `[attr.aria-pressed]` = `'true'` under Navy; `shellProviders()` in `shell.spec.ts` supplies an in-memory `THEME_STORAGE` and the file cleans `data-theme` after every test.

- [ ] **Step 1: Write the failing shell specs**

In `frontend/src/app/shell/shell.spec.ts`:

1. Import `THEME_STORAGE, ThemeStorage` from `'../ui/theme.service'`. Above `shellProviders`, add

```ts
/** An in-memory ui.theme store, so no shell spec writes the real localStorage (v225). */
function memoryThemeStorage(map = new Map<string, string>()): ThemeStorage {
  return { get: (key) => map.get(key) ?? null, set: (key, value) => void map.set(key, value) };
}
```

   add `{ provide: THEME_STORAGE, useValue: memoryThemeStorage() },` to the array `shellProviders()` returns, and a file-level hook right after the `readSource` const:

```ts
afterEach(() => {
  delete document.documentElement.dataset['theme'];
});
```

2. In `describe('shell top-bar cluster (v195 Phase 3)'`, add `{ provide: THEME_STORAGE, useValue: memoryThemeStorage(stored) },` after its `DENSITY_STORAGE` provider (the later provider wins, so `stored` sees `ui.theme`), and these cases after `writes ui.density and data-density from the profile menu`:

```ts
  const themeButton = (el: HTMLElement) => el.querySelector<HTMLButtonElement>('header.topbar > button.theme-toggle')!;

  it('toggles Dark blue from the bar: aria-pressed, data-theme and ui.theme move together', async () => {
    const { fixture, el } = await mount();
    const button = themeButton(el);
    expect(button.getAttribute('aria-label')).toBe('Dark blue theme');
    expect(button.getAttribute('aria-pressed')).toBe('false');
    expect(html.dataset['theme']).toBe('graphite');

    button.click();
    await settle(fixture);
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(html.dataset['theme']).toBe('navy');
    expect(stored.get('ui.theme')).toBe('navy');
    expect(button.getAttribute('aria-label')).toBe('Dark blue theme');

    button.click();
    await settle(fixture);
    expect(button.getAttribute('aria-pressed')).toBe('false');
    expect(html.dataset['theme']).toBe('graphite');
    expect(stored.get('ui.theme')).toBe('graphite');
  });

  it('starts pressed when this browser stored Dark blue', async () => {
    stored.set('ui.theme', 'navy');
    const { el } = await mount();
    expect(themeButton(el).getAttribute('aria-pressed')).toBe('true');
    expect(html.dataset['theme']).toBe('navy');
  });

  it('is a 44px-hit icon button with the theme glyph and an anchored "Dark blue theme" hint', async () => {
    const { el } = await mount();
    const button = themeButton(el);
    expect(button.classList).toContain('sb-hit');
    expect(button.classList).toContain('icon');
    expect(button.querySelector('sb-icon')).not.toBeNull();
    const tip = el.querySelector('header.topbar > sb-hint [role=tooltip]')!;
    expect(tip.textContent!.trim()).toBe('Dark blue theme');
    expect(button.getAttribute('aria-describedby')).toBe(tip.id);
  });

  it('shows the pressed state as the accent glyph on the accent tint', () => {
    const css = readSource('src/app/shell/shell.css');
    const rule = css.match(/\.theme-toggle\[aria-pressed="true"\][^{]*\{[^}]*\}/)?.[0] ?? '';
    expect(rule).toContain('color: var(--accent);');
    expect(rule).toContain('background: var(--accent-soft);');
    expect(css).toMatch(/\.theme-toggle\[aria-pressed="true"\]:not\(\[disabled\]\):hover/);
  });
```

   and in its `afterEach` add `delete html.dataset['theme'];` beside the density line.

3. In the phone test `leads the phone bar with the diamond and the wordmark, then the cluster, the search icon and the avatar` keep `order` unchanged and add `expect(bar.querySelector('button.theme-toggle')).toBeNull();` after the existing `toBeNull()` line.

4. In `describe('shell top bar (v203, spec v202 §3)'`, make `render()` call `f.detectChanges()` twice (the anchored hint renders once the view query has resolved), rename the order test to `'orders the bar: wordmark, divider, breadcrumb, cluster, search, theme, avatar'` and change `order` to:

```ts
    const order = ['a.brand', 'span.topbar-divider', 'sb-breadcrumb.topbar-lead', 'div.status-cluster',
      'button.palette-trigger', 'button.theme-toggle', 'sb-hint', 'sb-profile-menu', 'sb-scan-progress'];
```

- [ ] **Step 2: Run them to see them fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/shell/shell.spec.ts`
Expected: FAIL — the four new cluster cases and the desktop order pin (no `button.theme-toggle`); every other shell case still passes.

- [ ] **Step 3: Wire the service and the anchor query in `shell.ts`**

Add `ElementRef` and `viewChild` to the `@angular/core` import and `import { ThemeService } from '../ui/theme.service';` beside the `DensityService` import. After the `density` field:

```ts
  /** Black or Dark blue for this browser (spec v225): the bar button and the
   *  profile menu's Theme row both write through ThemeService, which owns
   *  `ui.theme`, `data-theme` and the theme-color meta. */
  protected readonly theme = inject(ThemeService);

  /** The bar button's element, for its anchored hint: `#themeToggle` on a
   *  `button[sb-button]` names the Button component, not the element. */
  protected readonly themeToggleRef = viewChild('themeToggle', { read: ElementRef<HTMLElement> });
```

- [ ] **Step 4: Add the button to `shell.html`**

Between the closing `}` of the palette `@if/@else` and `<sb-profile-menu`:

```html
      <!-- v225: Black / Dark blue, tablet and desktop only; a phone switches
           in the profile menu's Theme row. The name stays fixed, the state is
           aria-pressed, shown as the accent glyph on the accent tint. -->
      @if (!isPhone()) {
        <button sb-button variant="icon" type="button" class="theme-toggle sb-hit" #themeToggle
                aria-label="Dark blue theme" [attr.aria-pressed]="theme.theme() === 'navy'"
                (click)="theme.toggle()">
          <sb-icon name="theme" title="" />
        </button>
        @if (themeToggleRef(); as toggle) {
          <sb-hint [anchor]="toggle.nativeElement" text="Dark blue theme" />
        }
      }
```

`title=""` silences the icon's own "Theme" tooltip so the hint is the only label (as the rail brand does). The hint is anchored, so its host is `display: contents` and takes no room in the bar.

- [ ] **Step 5: Add the pressed look to `shell.css`**

After `.palette-trigger .shortcut { … }`:

```css
/* v225: the theme toggle. Icon buttons have no pressed look of their own,
   so Dark blue on shows the segmented controls' selected look -- the
   accent glyph on the accent tint -- and keeps it under the pointer (the
   :hover selector outranks the icon variant's own hover). */
.theme-toggle { flex: none; }
.theme-toggle[aria-pressed="true"],
.theme-toggle[aria-pressed="true"]:not([disabled]):hover {
  color: var(--accent);
  background: var(--accent-soft);
}
```

- [ ] **Step 6: Run the specs**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/shell/shell.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/hit-area.spec.ts`
Expected: PASS, 0 failed (the colour gate and the raw-button gate accept the new markup).

- [ ] **Step 7: Check the bar at three widths**

With a local admin and `ng serve` running (credentials from `.env`, loaded inside the script, never printed), run `node frontend/scripts/layout-audit.mjs --widths 390,768,1440`.
Expected: exit 0; at 768 and 1440 the button sits between the search trigger and the avatar without wrapping the bar; at 390 it is absent. (V225-12 repeats this in both themes.)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts
git commit -m "feat(v225): Dark blue toggle in the top bar on tablet and desktop (V225-6)"
```
