# v167 Arctic Navy token foundation. Implementation Plan, part 3: colour gate, radius migration, visual pass, full suite (AN11..AN15)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `grep -n "^### Task AN11:" -A 300 docs/superpowers/plans/2026-10-16-v167-arctic-navy-token-foundation_3-gates-radius-verify.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md`](../specs/2026-10-16-v167-arctic-navy-token-foundation-design.md) (§3 radius classification, §5 gates, §7 cold-load colour, Interaction with live plans, Testing and evidence; `## Amendments from the plan brief` 3, 4, 9 and 10 override)
**Index:** [`2026-10-16-v167-arctic-navy-token-foundation_0-index.md`](2026-10-16-v167-arctic-navy-token-foundation_0-index.md). Its `## Global Constraints`, `## Where to work` (`$WT`, `$R`, `GATES`, the no-`cd` rule), `## Parallelisation`, `## Task ledger` and `## Radius classification` bind every task here.

**Scope of this part:** the extended colour gate on a new `allSources()` walker, with the four colour literals it catches migrated in the same commit (AN11); the guarded radius migration, first the `ui/` + `shell/` + `styles.css` sites after the v165/v166 precondition and a merge of `main` (AN12), then the workspace sites, the radius gate and the deletion of `--radius` / `--radius-chip` (AN13); the Playwright visual pass with the partner (AN14); the single full-suite run (AN15).

**What parts 1 and 2 hand this part (from the ledger, not from their files):**
- `frontend/src/app/ui/testing/resolve-token.ts` (AN3): `resolveToken(name: string): string` (accepts `--x` or `x`, reads `src/styles/palette.css` + `src/styles/tokens.css` from `process.cwd()`, follows `var()` to a literal; throws `Error('<name> is not a token')`).
- `scripts/dev/dump_tokens.py` (AN2): no flag rewrites `tests/charts/resolved_tokens.json`; `--check` exits 1 when it is stale. `tests/dev/test_dump_tokens.py` and `tests/charts/test_chart_theme.py::test_resolver_reproduces_the_committed_fixture` hold the fixture to the CSS.
- `frontend/src/styles/palette.css` (AN7): `--navy-950 #070b14`, so the resolved `--bg` is `#070b14`.
- `frontend/src/styles/tokens.css` tier 3 (AN8): `--panel-radius: 8px`, `--control-radius: 6px`, `--chip-radius: 999px`, `--radius-sm: 2px`, `--scrim-soft: rgb(0 0 0 / 0.5)`, `--panel-shadow`, `--shadow-overlay`, in a second `:root` at the end of the file under `/* ===== Tier 3: component tokens (spec v167 §3) ===== */`. `--radius: 2px` and `--radius-chip: 2px` are still declared (AN13 deletes them).
- `frontend/src/app/ui/tokens.spec.ts` (AN8): file-local `CSS` (raw `tokens.css` text) and `TIER3` (the text from the tier-3 banner to the end); the case `tightens both radii to 2px` is still there.
- `frontend/src/app/ui/primitives.spec.ts` (AN9): G3 is `describe('G3: only the two elevation rules cast a shadow', ...)`. This part never edits G3.
- `styles.css:.elev-overlay`, `ui/layout.ts:.panel`, `ui/figure.ts:host`, `ui/chart-container.ts:.frame` are already on `var(--panel-radius)` (AN9). `ui/button.ts` primary rules are on `--btn-fill` (AN10); its `:host` radius (`:52`) and `:host(.chip)` radius (`:137`) are AN12's.

---

# Phase 3: gates, radius, verification

### Task AN11: Colour gate on a new `allSources()` walker; the four literals it catches migrated

**Model:** sonnet — a new walker, one extended gate and four small migrations

**Files:**
- Create: `frontend/src/app/ui/testing/all-sources.ts`
- Create: `frontend/src/app/ui/all-sources.spec.ts`
- Modify: `frontend/src/app/ui/primitives.spec.ts:1-5` (imports), `:94-116` (the hex gate, replaced and extended; G3 below it is AN9's and is not touched)
- Modify: `frontend/src/app/shell/shell.css:33` (`.scrim` background)
- Modify: `frontend/src/app/workspaces/versions/versions.ts:402-428` (`versionTint()` and its doc comment)
- Modify: `frontend/src/index.html:20-42` (`theme-color` meta, the cold-load comment and `<style>`)
- Modify: `frontend/public/manifest.webmanifest:6-7`

**Interfaces:**
- Consumes: AN3's `resolveToken(name: string): string` from `frontend/src/app/ui/testing/resolve-token.ts`; AN8's `--scrim-soft`; AN7's resolved `--bg` = `#070b14`.
- Produces (AN13 imports both into `primitives.spec.ts`):
  - `allSources(): { name: string; source: string }[]` in `frontend/src/app/ui/testing/all-sources.ts`: every `.ts`/`.css`/`.html` under `frontend/src`, names relative to `frontend/src` with `/` (`app/ui/button.ts`, `styles.css`, `index.html`), sorted with `localeCompare`, excluding `*.spec.ts` and the `src/styles/` directory; `source` is the raw file text.
  - `stripComments(source: string): string` in the same file: removes `/* */`, `<!-- -->` and `//` line comments (a `//` only at line start or after whitespace, so `https://` survives).
  - In `primitives.spec.ts`: `COLOUR_RE = /(?<!&)#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/g`; `HEX_ALLOWLIST: Map<string, string[]>` with the single entry `['index.html', ['#070b14', '#070b14']]`; `TOKENS_HEX_ALLOWED` (the seven names); `TIER3_RGB` (`--panel-shadow`, `--shadow-overlay`, `--scrim-soft`).
- `callSites()` in `ui/testing/call-sites.ts` is not touched: the button, control, valence and promoted gates keep its scope (amendment 3).

**Why the old gate could not just be widened:** `callSites()` walks `src/app`, skips every directory named `ui` or `testing` and reads only `.ts`/`.html`. A colour gate over it never looked at a primitive, a `.css` file, `styles.css` or `index.html`. A prototype of the new scan over today's tree finds exactly four literals: `shell/shell.css:33` `rgb(0 0 0 / 0.5)`, `versions.ts:427` `hsl(252, 65%, ...)`, and `index.html:21` / `:42` `#0a0b10`. `button.ts:65-66`'s hex sits in a comment and `versions.ts:151`'s `&#9650;` is a character reference; both stay legal.

- [ ] **Step 1: Write the failing walker spec**

Create `frontend/src/app/ui/all-sources.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { allSources, stripComments } from './testing/all-sources';

/**
 * The colour and radius gates' scope -- spec v167 §5 and amendment 3.
 * callSites() skips ui/ and testing/ and reads no .css, so a gate over it
 * proves nothing about the primitives or the stylesheets. allSources() is
 * the wider walker; these cases pin what it reaches and what it leaves out.
 */
describe("allSources(): the colour and radius gates' scope", () => {
  const names = allSources().map(({ name }) => name);

  for (const included of ['app/ui/button.ts', 'app/shell/shell.css', 'styles.css', 'index.html']) {
    it(`reaches ${included}`, () => {
      expect(names).toContain(included);
    });
  }

  it('leaves out styles/, whose two token files have their own rules', () => {
    expect(names.filter((name) => name.startsWith('styles/'))).toEqual([]);
  });

  it('leaves out every spec', () => {
    expect(names.filter((name) => name.endsWith('.spec.ts'))).toEqual([]);
  });

  it('keeps only .ts, .css and .html', () => {
    expect(names.filter((name) => !/\.(ts|css|html)$/.test(name))).toEqual([]);
  });

  it('names files relative to src/ with forward slashes, in a stable order', () => {
    expect(names.filter((name) => name.includes('\\'))).toEqual([]);
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b)));
  });

  it('returns the raw source, comments included', () => {
    const button = allSources().find(({ name }) => name === 'app/ui/button.ts')!;
    expect(button.source).toContain('/*');
  });
});

describe('stripComments()', () => {
  it('drops a block comment and keeps the code around it', () => {
    expect(stripComments('a { color: red; /* #fff */ }')).toBe('a { color: red;  }');
  });

  it('drops a block comment that spans lines', () => {
    expect(stripComments('a {\n/* one\n   #fff two */\n}')).toBe('a {\n\n}');
  });

  it('drops an HTML comment', () => {
    expect(stripComments('<p><!-- #fff --></p>')).toBe('<p></p>');
  });

  it('drops a // line comment and keeps the line break', () => {
    expect(stripComments('const a = 1; // #fff\nconst b = 2;')).toBe('const a = 1; \nconst b = 2;');
  });

  it('keeps a URL, whose // follows a colon', () => {
    const url = "const u = 'https://bomeo-capital.com/#top';";
    expect(stripComments(url)).toBe(url);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/all-sources.spec.ts
```
Expected: FAIL, the build cannot resolve `./testing/all-sources`.

- [ ] **Step 3: Write the walker**

Create `frontend/src/app/ui/testing/all-sources.ts`:

```ts
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Every .ts, .css and .html under frontend/src: the scope of the colour and
 * radius gates (spec v167 §5, amendment 3). Unlike callSites() it reaches
 * ui/, testing/, every component stylesheet, styles.css and index.html.
 * Left out: *.spec.ts, and the styles/ directory (palette.css and
 * tokens.css, which primitives.spec.ts checks under their own rules).
 *
 * Names are relative to src/ with forward slashes ('app/ui/button.ts',
 * 'index.html') and sorted, so an allow-list Map keys on them on Windows
 * too. cwd is frontend/ under `ng test`, as for every spec in this repo.
 */
const SRC = join(process.cwd(), 'src');
const STYLES = join(SRC, 'styles');

export type Source = { name: string; source: string };

function scanned(entry: string): boolean {
  return /\.(ts|css|html)$/.test(entry) && !entry.endsWith('.spec.ts');
}

function walk(dir: string, out: Source[]): void {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (full !== STYLES) walk(full, out);
      continue;
    }
    if (!scanned(entry)) continue;
    const name = full.slice(SRC.length + 1).replace(/\\/g, '/');
    out.push({ name, source: readFileSync(full, 'utf8') });
  }
}

export function allSources(): Source[] {
  const out: Source[] = [];
  walk(SRC, out);
  return out.sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Removes block comments, HTML comments and line comments, so a hex quoted
 * in prose (button.ts's contrast note) or a radius named in a comment stays
 * legal. A `//` counts as a comment only at the start of a line or after
 * whitespace: the `//` of `https://` follows a colon and is kept.
 */
export function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/(^|\s)\/\/[^\n]*/gm, '$1');
}
```

- [ ] **Step 4: Run it and watch it pass**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/all-sources.spec.ts
```
Expected: `Tests  14 passed`, 0 failed.

- [ ] **Step 5: Extend the colour gate in `primitives.spec.ts`**

Re-read `primitives.spec.ts:1-20` and `:94-136` first (AN9 changed G3 further down; leave it alone).

Replace the import block (`:1-5`) with:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { allSources, stripComments } from './testing/all-sources';
import { callSites } from './testing/call-sites';
import { resolveToken } from './testing/resolve-token';
```

Replace the hex gate (`:94-116`: the `/** Colour literals outside tokens.css.` doc comment, `const HEX_ALLOWLIST = new Map<string, string>([]);` and the whole `describe('no colour is declared outside tokens.css', ...)`) with:

```ts
/**
 * Colour literals outside the token files -- spec v167 §5, which extends
 * the gate this block used to be (hex only, over callSites() only).
 *
 * Scope: allSources() -- every .ts/.css/.html under src/, so ui/, every
 * stylesheet, styles.css and index.html, minus specs and styles/.
 * Pattern: a hex literal, or rgb()/rgba()/hsl()/hsla() in either the comma
 * or the space syntax. (?<!&) keeps an HTML numeric character reference out
 * (&#9650; in versions.ts is a triangle glyph, not a colour). Comments are
 * stripped first, so a hex quoted in prose (button.ts's contrast note)
 * stays legal.
 *
 * An entry here is a copy of a token that cannot read var(). The list of
 * literals a file may hold is exact and in source order, so a third copy
 * fails as surely as a new hue.
 */
const COLOUR_RE = /(?<!&)#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/g;

const HEX_ALLOWLIST = new Map<string, string[]>([
  // The two cold-load copies of --bg: the theme-color meta and the inline
  // html/body background paint before any stylesheet has loaded, so they
  // cannot read var(--bg). 'the cold-load copies equal the resolved --bg'
  // below fails the moment they drift from palette.css.
  ['index.html', ['#070b14', '#070b14']],
]);

describe('no colour is declared outside the token files', () => {
  for (const { name, source } of allSources()) {
    it(`${name} declares no colour literal`, () => {
      const found = [...stripComments(source).matchAll(COLOUR_RE)].map(([literal]) => literal);
      expect(found).toEqual(HEX_ALLOWLIST.get(name) ?? []);
    });
  }
});

/**
 * tokens.css under its own rules (spec v167 §5). palette.css is tier 1, the
 * only file free to hold hued literals. tokens.css keeps hex only on the
 * seven names jsdom and chart-palette.spec read as literals, and
 * rgb()/rgba() only inside the three tier-3 shadow and scrim tokens, black
 * or white at some alpha. A hued glow derives from a tier-2 token with
 * color-mix(), so a palette change reaches it. hsl() is in neither file.
 */
const TOKENS_HEX_ALLOWED = new Set([
  '--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5', '--chart-6', '--quality-4',
]);
const TIER3_RGB = new Set(['--panel-shadow', '--shadow-overlay', '--scrim-soft']);

describe('tokens.css holds no hued literal (v167 §5)', () => {
  const styles = (file: string) =>
    stripComments(readFileSync(join(process.cwd(), 'src/styles', file), 'utf8'));
  const TOKENS = styles('tokens.css');
  const declarations = [...TOKENS.matchAll(/(--[\w-]+):\s*([^;]+);/g)]
    .map(([, name, value]) => ({ name, value }));
  const hexIn = (text: string) => text.match(/(?<!&)#[0-9a-fA-F]{3,8}\b/g) ?? [];
  const rgbIn = (text: string) => text.match(/\brgba?\(/g) ?? [];
  const count = (find: (text: string) => string[]) =>
    declarations.reduce((n, { value }) => n + find(value).length, 0);

  it('keeps hex only on the seven allowed names', () => {
    const offenders = declarations
      .filter(({ name, value }) => hexIn(value).length > 0 && !TOKENS_HEX_ALLOWED.has(name))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });

  it('keeps rgb()/rgba() inside the three tier-3 tokens only', () => {
    const offenders = declarations
      .filter(({ name, value }) => rgbIn(value).length > 0 && !TIER3_RGB.has(name))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });

  it('declares no colour outside a custom property', () => {
    expect(hexIn(TOKENS)).toHaveLength(count(hexIn));
    expect(rgbIn(TOKENS)).toHaveLength(count(rgbIn));
  });

  it('uses only black or white in those rgb()/rgba() calls', () => {
    const channels = [...TOKENS.matchAll(/\brgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/g)]
      .map(([, r, g, b]) => `${r} ${g} ${b}`);
    expect(channels.length).toBeGreaterThan(0);
    expect(channels.filter((rgb) => rgb !== '0 0 0' && rgb !== '255 255 255')).toEqual([]);
  });

  it('uses hsl() in neither token file', () => {
    expect(TOKENS).not.toMatch(/\bhsla?\(/);
    expect(styles('palette.css')).not.toMatch(/\bhsla?\(/);
  });
});

/**
 * The cold-load copies of --bg (spec v167 §7). They cannot read var(), so
 * they are copies, and copies drift: before v167 all four said #0a0b10
 * while --bg said #0c0f16. These cases make a palette change that forgets
 * them fail here instead of flashing the old ground on a cold load and
 * leaving a stale PWA title bar.
 */
describe('the cold-load copies equal the resolved --bg (v167 §7)', () => {
  const bg = resolveToken('--bg').toLowerCase();
  const read = (file: string) => readFileSync(join(process.cwd(), file), 'utf8');

  it('index.html paints the theme-color meta in --bg', () => {
    const meta = read('src/index.html').match(/<meta name="theme-color" content="([^"]+)">/);
    expect(meta?.[1].toLowerCase()).toBe(bg);
  });

  it('index.html paints the inline cold-load ground in --bg', () => {
    const inline = read('src/index.html').match(/<style>html, body \{ background: ([^;]+); \}<\/style>/);
    expect(inline?.[1].toLowerCase()).toBe(bg);
  });

  it("the manifest's theme_color and background_color are --bg", () => {
    const manifest = JSON.parse(read('public/manifest.webmanifest'));
    expect(manifest.theme_color.toLowerCase()).toBe(bg);
    expect(manifest.background_color.toLowerCase()).toBe(bg);
  });
});
```

The `every allowlist entry is justified` block below stays as it is: it already lists `HEX_ALLOWLIST` and slices from `const HEX_ALLOWLIST` to the first `]);`, and the new entry carries a `//` comment above it.

- [ ] **Step 6: Run the gate and watch it fail on exactly the four literals**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/all-sources.spec.ts
```
Expected: FAIL in exactly these six cases:
- `app/shell/shell.css declares no colour literal` (received `['rgb(']`);
- `app/workspaces/versions/versions.ts declares no colour literal` (`['hsl(']`);
- `index.html declares no colour literal` (`['#0a0b10', '#0a0b10']`, expected `['#070b14', '#070b14']`);
- the three `the cold-load copies equal the resolved --bg` cases (`#0a0b10` vs `#070b14`).

Every `tokens.css holds no hued literal` case passes, because AN7 and AN8 already put tokens.css in that shape. If one of them fails, that is an AN7/AN8 defect: stop and report it to the controller; do not loosen a rule here. If another file fails the colour case (a file added since the brief was written), move its literal onto a token by the same reasoning as below and name the file in the commit body.

- [ ] **Step 7: Migrate the four literals**

`frontend/src/app/shell/shell.css:33`, in `.scrim`:

```css
  background: var(--scrim-soft);
```

`frontend/src/app/workspaces/versions/versions.ts`: re-read `:402-428`, then replace the doc comment and `versionTint()` (from `  /**` above `A distinct shade per version` through the method's closing `}`) with:

```ts
  /**
   * A distinct shade per version, so a lane with many past segments reads as
   * a sequence rather than one undifferentiated block -- the complaint this
   * exists to fix was that every non-current segment shared one flat colour
   * with no boundary between them.
   *
   * **One hue, not one per version.** `styles/tokens.css` reserves five hues
   * for meaning (pos/neg/warn/accent/info) and calls a sixth "a review
   * defect" -- this is exactly the design system's own ordinal case (a
   * version's place in a time-ordered sequence, not a nominal identity), so
   * it stays on the accent hue and varies only how much of it shows. Hashed
   * from the version string rather than the segment's position so the same
   * version always reads the same shade if it reappears, and so the shade
   * does not shift under a reader's cursor as the strip re-measures.
   *
   * Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §5):
   * the shade used to be a computed `hsl(252, 65%, 38-62%)` literal, which
   * no palette change could reach. It is now --accent mixed into --surface,
   * so it follows the tokens and the colour gate holds.
   */
  protected versionTint(version: string): string {
    let hash = 0;
    for (let i = 0; i < version.length; i++) {
      hash = (hash * 31 + version.charCodeAt(i)) | 0;
    }
    // 40-75% of --accent over --surface: at the low end still clearly a
    // segment against the lane, and capped 25 points short of pure --accent
    // (which is what the current segment paints) so a hash landing near the
    // top never reads as "current".
    const share = 40 + (Math.abs(hash) % 36);
    return `color-mix(in oklab, var(--accent) ${share}%, var(--surface))`;
  }
```

`frontend/src/index.html`: re-read `:20-42`. Replace line 21 (`<meta name="theme-color" content="#0a0b10">`) with:

```html
  <!-- A copy of --bg (palette.css --navy-950): the browser reads the
       theme-color before any stylesheet loads, so it cannot be var(--bg).
       primitives.spec.ts allow-lists it and asserts it equals the resolved
       --bg (spec v167 §7). -->
  <meta name="theme-color" content="#070b14">
```

and replace `:32-42` (the `<!-- Painted before the bundle parses ...` comment and the `<style>` line) with:

```html
  <!-- Painted before the bundle parses, so a slow load shows the app's own
       ground colour rather than a white flash on a UI that is dark by
       definition.

       This hex is one of the two colour literals the colour gate
       deliberately leaves in place: it has to be inline and it has to work
       before any stylesheet loads, so it cannot read `--bg`. It is therefore
       a copy, and copies drift -- so primitives.spec.ts ('the cold-load
       copies equal the resolved --bg', spec v167 §7) fails when it differs
       from --bg in styles/palette.css, as does the manifest's pair. The
       symptom it prevents is a one-frame flash of the old colour on a cold
       load, which is easy to miss and easy to explain once seen. -->
  <style>html, body { background: #070b14; }</style>
```

`frontend/public/manifest.webmanifest:6-7`:

```json
  "theme_color": "#070b14",
  "background_color": "#070b14",
```

- [ ] **Step 8: Run the narrow runs**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/all-sources.spec.ts --include src/app/workspaces/versions/versions.spec.ts --include src/app/shell
```
Expected: `Tests  N passed`, 0 failed (`versions.spec.ts` and the shell specs prove the tint and scrim edits broke no rendering; jsdom may drop the `color-mix()` inline style, and no versions case asserts on it). Quote the verdict line.

Then confirm the walker's scope by hand once, so the reviewer sees it:
```bash
git -C $WT grep -nE "#[0-9a-fA-F]{6}\b|\b(rgba?|hsla?)\(" -- frontend/src ':!frontend/src/styles' ':!*.spec.ts'
```
Expected: the two `#070b14` lines of `index.html`, and otherwise only lines inside comments (`button.ts`'s contrast note, `versions.ts`'s superseded `hsl(252, ...` in its doc comment, and any other prose mention), which the gate strips. A hit that is code, not comment, means the gate missed it: report it.

- [ ] **Step 9: Commit**

```bash
git -C $WT add frontend/src/app/ui/testing/all-sources.ts frontend/src/app/ui/all-sources.spec.ts frontend/src/app/ui/primitives.spec.ts frontend/src/app/shell/shell.css frontend/src/app/workspaces/versions/versions.ts frontend/src/index.html frontend/public/manifest.webmanifest
git -C $WT commit -m "feat(ui): v167 AN11 -- colour gate over every source; scrim, version tint and cold-load copies on tokens

A new allSources() walker (ui/testing/all-sources.ts) reaches ui/, every
.css, styles.css and index.html, which callSites() never did. The colour
gate now runs over it, catches rgb()/rgba()/hsl() as well as hex, strips
comments first, and holds tokens.css to hex on the seven chart/quality
names and black/white rgba in the three tier-3 tokens. index.html's two
cold-load copies and the manifest pair are asserted equal to the resolved
--bg (#070b14; they were #0a0b10, already off the old --bg).

Migrated: shell.css .scrim -> var(--scrim-soft); versions.ts versionTint()
-> color-mix(in oklab, var(--accent) 40-75%, var(--surface)) instead of a
computed hsl(); index.html and manifest.webmanifest -> #070b14.

<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task AN12: Radius part 1: v165/v166 precondition, merge `main`, the `ui/` + `shell/` + `styles.css` sites

**Model:** sonnet — judgement per site against a fixed table and rule

**Files:**
- Modify: `frontend/src/app/shell/login/login.css:17`
- Modify: `frontend/src/app/shell/scan-progress.css:39`
- Modify: `frontend/src/app/shell/shell.css:201`
- Modify: `frontend/src/app/shell/tape/tape.css:72`
- Modify: `frontend/src/app/ui/async.ts:91`, `:105`, `:115`, `:131`
- Modify: `frontend/src/app/ui/bar-list.ts:11`
- Modify: `frontend/src/app/ui/button.ts:52`, `:137`
- Modify: `frontend/src/app/ui/chart-container.ts:121`
- Modify: `frontend/src/app/ui/chart-tooltip.ts:27`
- Modify: `frontend/src/app/ui/chip.ts:97`
- Modify: `frontend/src/app/ui/column-picker.ts:94`
- Modify: `frontend/src/app/ui/data-table/data-table.ts:379`
- Modify: `frontend/src/app/ui/date-range.ts:48`
- Modify: `frontend/src/app/ui/donut.ts:12`
- Modify: `frontend/src/app/ui/empty-state.ts:30`
- Modify: `frontend/src/app/ui/filter-bar.ts:106`
- Modify: `frontend/src/app/ui/form-controls.ts:55`, `:108`
- Modify: `frontend/src/app/ui/heat-grid.ts:2`
- Modify: `frontend/src/app/ui/histogram.ts:106`, `:115`
- Modify: `frontend/src/app/ui/line-chart.ts:154`
- Modify: `frontend/src/app/ui/magnitude.ts:25-26`
- Modify: `frontend/src/app/ui/metric-card.ts:47`
- Modify: `frontend/src/app/ui/metric-chip.ts:38`
- Modify: `frontend/src/app/ui/pagination.ts:45`, `:51`
- Modify: `frontend/src/app/ui/panel-error.ts:7`
- Modify: `frontend/src/app/ui/segmented.ts:20`
- Modify: `frontend/src/app/ui/share-bar.ts:11`
- Modify: `frontend/src/app/ui/stat-tile.ts:60`
- Modify: `frontend/src/app/ui/status-cell.ts:114`
- Modify: `frontend/src/app/ui/status-indicator.ts:90`
- Modify: `frontend/src/app/ui/status.ts:5`
- Modify: `frontend/src/app/ui/timeline.ts:72`
- Modify: `docs/superpowers/plans/2026-10-16-v167-arctic-navy-token-foundation_0-index.md` (`## Handoff`, only on the stop path of Step 1, in the main tree `$R`)

**Interfaces:**
- Consumes: AN8's four radius targets `--panel-radius` (8px), `--control-radius` (6px), `--chip-radius` (999px), `--radius-sm` (2px); the index's `## Radius classification` (rule and the AN12 table); AN11's colour gate (re-run after the merge).
- Produces: no `var(--radius)`, no `var(--radius-chip)` and no `border-radius: <n>px` left under `frontend/src/app/ui/`, `frontend/src/app/shell/` or in `frontend/src/styles.css`; the branch carrying `main` with v165 and v166 merged, so AN13's inventory sees their components. No gate yet: AN13 adds it once the workspace sites are done too.

**The order is a contract, not a preference.** v165 and v166's plan text uses `var(--radius)`, `var(--radius-chip)` and raw `2px` (index `## Radius classification`, last paragraph). If they land after this migration, AN13's gate fails them; if someone merges around the gate, a deleted token silently resolves to radius 0. So this task runs only once both are on `main`, and never edits another plan's worktree or plan text.

- [ ] **Step 1: Check the v165/v166 precondition**

Run:
```bash
git -C $R cat-file -e main:frontend/src/app/workspaces/calendar/day/calendar-day.ts && echo "v165 on main" || echo "v165 NOT on main"
git -C $R cat-file -e main:frontend/src/app/workspaces/trades/outcome-strip.ts && echo "v166 on main" || echo "v166 NOT on main"
git -C $R worktree list | grep -E "v16[56]-" || echo "no v165/v166 worktree"
```
`calendar-day.ts` is a file v165 creates and `outcome-strip.ts` one v166 creates (their indexes' ledgers). Proceed only when the output is `v165 on main`, `v166 on main` and `no v165/v166 worktree` (a worktree still listed means that plan is mid-flight and may still add sites).

**Stop path.** Otherwise do not touch any file under `frontend/`. Append one bullet to the `## Handoff` section of `$R/docs/superpowers/plans/2026-10-16-v167-arctic-navy-token-foundation_0-index.md`:

```markdown
- **<YYYY-MM-DD>: AN12 stopped at its precondition.** <v165 | v166 | both> not merged to `main` (<the three output lines of Step 1>). AN1-AN11 are committed on the branch; AN12-AN15 stay open. Resume AN12 at Step 1 once both plans are merged and their worktrees removed.
```

Leave the edit uncommitted for the controller (plans are committed on `main` by the controller) and report `BLOCKED: v165/v166 not merged` with the three output lines.

- [ ] **Step 2: Merge `main` into the branch**

Invoke the `worktree-lifecycle` skill first (another session may be working on `main`). Then:

```bash
git -C $WT merge --no-edit main
```

If a conflict appears in a file this plan has changed (`ui/`, `shell/`, `styles.css`, `styles/`, `index.html`, `versions.ts`, `chart_style.py`, `cache.py`, the specs), keep both sides' intent: v167's tokens and gates, the other plan's behaviour. A conflict you cannot resolve that way is a stop: `git -C $WT merge --abort` and report `BLOCKED:` with the conflicting hunks.

Then check the merged tree against everything v167 has gated so far:

```bash
python $WT/scripts/dev/dump_tokens.py --check
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/tokens.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/all-sources.spec.ts
```

Expected: `--check` exits 0 and `Tests  N passed`, 0 failed. Two failures are expected possibilities, and both are fixed here, in one separate commit before the radius work:
- `--check` exits 1 because the merge brought a `tokens.css` edit: run `python $WT/scripts/dev/dump_tokens.py` and stage `tests/charts/resolved_tokens.json`.
- `<file> declares no colour literal` for a v165/v166 file (their plans predate the colour gate): move the literal onto the existing semantic token it stands for (`--text-faint`, `--surface-raised`, ...), never onto a new hue, and never into `HEX_ALLOWLIST`.

```bash
git -C $WT add <the files you changed in this step>
git -C $WT commit -m "fix(ui): v167 AN12 -- merged v165/v166 code onto the v167 gates

<one line per file: the literal and the token it now reads, or 'fixture regenerated'>

<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Skip that commit when both checks are already green.

- [ ] **Step 3: Inventory the sites (the failing check)**

Run:
```bash
git -C $WT grep -nE "var\(--radius(-chip)?\)|border[a-z-]*radius:\s*[0-9.]+px" -- frontend/src/app/ui frontend/src/app/shell frontend/src/styles.css ':!*.spec.ts'
```
Expected: 40 lines (44 on `main` before v167, minus the four AN9 already moved), every one a row of the table in Step 4 (`var(--radius-sm)` does not match: the pattern needs `)` straight after `radius` or `radius-chip`). A line the table does not name (a merged v165/v166 site, or code added since the brief) is classified by the index's rule, in order: (1) under ~12px tall, or a cell, track, swatch or fill -> `--radius-sm`; (2) a tag or pill that reads as a label -> `--chip-radius`; (3) a button, input, select, textarea, segmented track, trigger, small tooltip or dropdown list -> `--control-radius`; (4) a panel, card, tile, frame, empty/error block, overlay, log or form block -> `--panel-radius`. Name each such site in the commit body.

`border-radius: 50%` (dots), `0` (`button.ts:156` `:host(.segment)`, `layout.ts:381` the drawer's flush edge) and `inherit` (`scan-progress.css:47` `.fill`) stay as they are.

- [ ] **Step 4: Move every site onto its target**

Open each file, confirm the element matches its row (a contradiction is re-classified by the rule and named in the commit body), and replace only the radius value. Multi-line rules keep their indentation; one-line `styles:` strings keep their spacing style (`border-radius:var(--x)` stays unspaced where it was unspaced).

| File:line | Selector | Before | After |
|---|---|---|---|
| `shell/login/login.css:17` | `.panel` | `border-radius: var(--radius);` | `border-radius: var(--panel-radius);` |
| `shell/scan-progress.css:39` | `.track` | `border-radius: 2px;` | `border-radius: var(--radius-sm);` |
| `shell/shell.css:201` | `.nav a` | `border-radius: 0 var(--radius) var(--radius) 0;` | `border-radius: 0 var(--control-radius) var(--control-radius) 0;` |
| `shell/tape/tape.css:72` | `.tile` | `border-radius: var(--radius-chip); }` | `border-radius: var(--control-radius); }` |
| `ui/async.ts:91` | `.retry` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/async.ts:105` | `.skeleton-cell` | `border-radius: var(--radius-chip);` | `border-radius: var(--radius-sm);` |
| `ui/async.ts:115` | `.reason` | `border-radius: var(--radius-chip);` | `border-radius: var(--chip-radius);` |
| `ui/async.ts:131` | `.stale-badge` | `border-radius: var(--radius-chip);` | `border-radius: var(--chip-radius);` |
| `ui/bar-list.ts:11` | `.track` | `.track{position:relative;height:10px;background:var(--bg);border-radius:2px}` | `.track{position:relative;height:10px;background:var(--bg);border-radius:var(--radius-sm)}` |
| `ui/bar-list.ts:11` | `.fill` | `.fill{position:absolute;top:0;bottom:0;border-radius:2px}` | `.fill{position:absolute;top:0;bottom:0;border-radius:var(--radius-sm)}` |
| `ui/button.ts:52` | `:host` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/button.ts:137` | `:host(.chip)` | `border-radius: var(--radius-chip);` | `border-radius: var(--chip-radius);` |
| `ui/chart-container.ts:121` | `.retry` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/chart-tooltip.ts:27` | `.tooltip` (first radius on the line) | `border-radius:var(--radius);` | `border-radius:var(--control-radius);` |
| `ui/chart-tooltip.ts:27` | `.swatch` (12x2px) | `border-radius:1px;` | `border-radius:var(--radius-sm);` |
| `ui/chip.ts:97` | `.chip` | `border-radius: var(--radius-chip);` | `border-radius: var(--chip-radius);` |
| `ui/column-picker.ts:94` | `.trigger` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/data-table/data-table.ts:379` | `.phone-sort select` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/date-range.ts:48` | `input` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/donut.ts:12` | `i` (legend swatch, .7rem) | `i{width:.7rem;height:.7rem;border-radius:2px;` | `i{width:.7rem;height:.7rem;border-radius:var(--radius-sm);` |
| `ui/empty-state.ts:30` | `.empty` | `border-radius: var(--radius);` | `border-radius: var(--panel-radius);` |
| `ui/filter-bar.ts:106` | `.chip` | `border-radius: var(--radius-chip);` | `border-radius: var(--chip-radius);` |
| `ui/form-controls.ts:55` | `select` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/form-controls.ts:108` | `input` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/heat-grid.ts:2` | `td` (a cell) | `td{font-size:var(--text-micro);text-align:right;padding:4px 6px;border-radius:2px;` | `td{font-size:var(--text-micro);text-align:right;padding:4px 6px;border-radius:var(--radius-sm);` |
| `ui/histogram.ts:106` | `.track` | `border-radius: 2px;` | `border-radius: var(--radius-sm);` |
| `ui/histogram.ts:115` | `.fill` | `border-radius: 2px;` | `border-radius: var(--radius-sm);` |
| `ui/line-chart.ts:154` | `.tooltip` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/magnitude.ts:25` | `:host` (3px bar) | `border-radius: 2px; }` | `border-radius: var(--radius-sm); }` |
| `ui/magnitude.ts:26` | `.bar` | `border-radius: 2px;` | `border-radius: var(--radius-sm);` |
| `ui/metric-card.ts:47` | `.card` | `border-radius: var(--radius);` | `border-radius: var(--panel-radius);` |
| `ui/metric-chip.ts:38` | `.chip` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/pagination.ts:45` | `.per-page select, .jump` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/pagination.ts:51` | `button` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `ui/panel-error.ts:7` | `.error` (first radius on the line) | `border:1px dashed var(--neg); border-radius:var(--radius);` | `border:1px dashed var(--neg); border-radius:var(--panel-radius);` |
| `ui/panel-error.ts:7` | `button` (second radius on the line) | `border:1px solid var(--border-strong); border-radius:var(--radius);` | `border:1px solid var(--border-strong); border-radius:var(--control-radius);` |
| `ui/segmented.ts:20` | `.track` | `border-radius: var(--radius); }` | `border-radius: var(--control-radius); }` |
| `ui/share-bar.ts:11` | `.track` (14px bar) | `background:var(--bg); border-radius:4px;` | `background:var(--bg); border-radius:var(--radius-sm);` |
| `ui/share-bar.ts:11` | `.key` (10px swatch) | `.key { width:10px; height:10px; border-radius:2px;` | `.key { width:10px; height:10px; border-radius:var(--radius-sm);` |
| `ui/stat-tile.ts:60` | `.tile` | `border-radius: var(--radius);` | `border-radius: var(--panel-radius);` |
| `ui/status-cell.ts:114` | `.track` | `border-radius: 2px;` | `border-radius: var(--radius-sm);` |
| `ui/status-indicator.ts:90` | `.track` | `border-radius: 2px;` | `border-radius: var(--radius-sm);` |
| `ui/status.ts:5` | `.closed .marker` (7px) | `.closed .marker { width: 7px; height: 7px; border-radius: 1px;` | `.closed .marker { width: 7px; height: 7px; border-radius: var(--radius-sm);` |
| `ui/timeline.ts:72` | `.badge` | `border-radius: var(--radius);` | `border-radius: var(--chip-radius);` |

Already done by AN9, no edit: `styles.css:158` `.elev-overlay`, `ui/layout.ts:68` `.panel`, `ui/figure.ts:13` `:host`, `ui/chart-container.ts:90` `.frame`.

Two judgement notes for the reviewer: `share-bar.ts` `.track` goes from 4px to 2px (it is 14px tall but reads as a bar, rule 1); `chart-tooltip.ts` `.swatch` and `status.ts` `.closed .marker` go from 1px to 2px (the smallest target; at 2px tall the swatch looks the same).

- [ ] **Step 5: Re-run the inventory and the narrow runs**

Run the Step 3 grep again. Expected: no output.

Then:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui --include src/app/shell
```
Expected: `Tests  N passed`, 0 failed. `src/app/ui` contains every `GATES` spec plus the primitives' own specs, so this one run covers both. Quote the verdict line.

- [ ] **Step 6: Commit**

```bash
git -C $WT add frontend/src/app/shell frontend/src/app/ui
git -C $WT commit -m "feat(ui): v167 AN12 -- ui/ and shell/ corners on the four radius targets

v165 and v166 are on main and merged into the branch (precondition:
<the three Step 1 output lines>). Every var(--radius), var(--radius-chip)
and raw px radius under ui/ and shell/ now reads one of --panel-radius,
--control-radius, --chip-radius or --radius-sm, per the index's
classification table. 50%, 0 and inherit stay.

Deviations from the table: <none | site -- old row -> new row, reason>.
Sites not in the table: <none | site -- target, rule n>.

<frontend verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task AN13: Radius part 2: workspace sites (incl. v165/v166), the radius gate, `--radius` / `--radius-chip` deleted

**Model:** sonnet — the remaining sites, one new gate block, token deletion

**Files:**
- Modify: `frontend/src/app/ui/primitives.spec.ts` (new `describe('no raw or retired radius (v167 §3)')` block at the end of the file)
- Modify: `frontend/src/app/ui/tokens.spec.ts:291-294` (the `tightens both radii to 2px` case; re-read, AN8 shifted lines)
- Modify: `frontend/src/styles/tokens.css:251-269` (radii comment superseded, `--radius` and `--radius-chip` deleted; re-read, AN7/AN8 shifted lines)
- Modify: `tests/charts/resolved_tokens.json` (regenerated)
- Modify: `frontend/src/app/workspaces/analytics/tabs/execution.ts:22`
- Modify: `frontend/src/app/workspaces/analytics/tabs/partials.ts:196`
- Modify: `frontend/src/app/workspaces/analytics/tabs/tuning.ts:253`, `:300`
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts:307`, `:491`
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts:736`
- Modify: `frontend/src/app/workspaces/plans/plan-detail.ts:252`
- Modify: `frontend/src/app/workspaces/risk/risk.ts:504`, `:521`
- Modify: `frontend/src/app/workspaces/system/logs-tab.ts:221`
- Modify: `frontend/src/app/workspaces/system/scan-tab.ts:185`
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts:517`, `:532`, `:547`, `:563`, `:604`
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts:647`, `:726`
- Modify: `frontend/src/app/workspaces/versions/versions.ts:285`, `:289`, `:292`, `:322`, `:334`
- Modify: `frontend/src/app/workspaces/watchlist/earnings-calendar.ts:133`, `:167`, `:193`
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts:516`, `:548`
- Plus every v165/v166 file the Step 1 inventory finds (they arrive with AN12's merge; their paths are not on `main` while this plan is written, so they are named from the grep, not here).

**Interfaces:**
- Consumes: AN11's `allSources()` and `stripComments()` (already imported in `primitives.spec.ts`); AN8's four radius targets and `tokens.spec.ts`'s file-local `CSS` and `TIER3`; AN12's merged branch with `ui/` and `shell/` already clean; AN2's `dump_tokens.py`.
- Produces: the radius gate in `primitives.spec.ts`: `RADIUS_DECL_RE = /border(?:-[a-z]+)*-radius:\s*([^;}]+)[;}]/g` (a value containing `\d+(\.\d+)?px` fails), `RETIRED_RADIUS_RE = /var\(--radius(?:-chip)?\)/g` (any match fails), and a case that `tokens.css` declares neither `--radius:` nor `--radius-chip:`; `tokens.spec.ts` case `defines the four radius targets`; `tokens.css` without `--radius` / `--radius-chip`; the fixture without the keys `radius` and `radius-chip`.

**One deviation from the ledger's regex, on purpose.** The ledger wrote `RADIUS_DECL_RE` with `([^;]+);`. One-line `styles:` strings end a rule with `}` and no `;` (`bar-list.ts`: `.track{...;border-radius:var(--radius-sm)}.fill{position:absolute;...`), so `[^;]+` runs into the next rule and would read its px (`width:10px`) as this corner's. Stopping at `;` or `}` reads the corner's own value only. Both forms find the same 77 offenders on today's tree; only the stricter one stays quiet after the migration. The pattern is local to this task; no other task consumes it.

- [ ] **Step 1: Inventory what is left**

Run:
```bash
git -C $WT grep -nE "var\(--radius(-chip)?\)|border[a-z-]*radius:\s*[0-9.]+px" -- frontend/src ':!frontend/src/styles' ':!*.spec.ts'
```
Expected: the 29 workspace lines of the Step 4 table (line numbers may have moved where v165/v166 edited a file, notably `trade-detail.ts` and `calendar.ts`), plus the v165/v166 sites, and nothing under `ui/` or `shell/` (AN12). The v165/v166 constructs known from their plan text, to classify by the index's rule:
- v165 `.spark { display: inline-flex; line-height: 0; border-radius: 2px; }` (a sparkline) -> `var(--radius-sm)`;
- v165 day-page `border-radius: var(--radius-chip);` on a tag -> `var(--chip-radius)`;
- v165 drawer `.breakdown .fill { ... height: 8px; border-radius: 2px; ... }` -> `var(--radius-sm)`;
- v166 outcome-strip tile `border-radius: var(--radius);` -> `var(--panel-radius)`.
A site that is gone after the merge (v166 rewrote part of `trade-detail.ts`) is simply not edited; say so in the commit body.

- [ ] **Step 2: Write the failing gate and token cases**

Append to the end of `frontend/src/app/ui/primitives.spec.ts` (after G3):

```ts
/**
 * No raw or retired radius -- spec v167 §3 and §5. Every corner outside
 * styles/ reads one of the four tier-3 targets: --panel-radius,
 * --control-radius, --chip-radius or --radius-sm. A px value is a corner
 * nobody classified. var(--radius) and var(--radius-chip) are retired:
 * tokens.css no longer declares them, so either would resolve to nothing
 * and the browser would silently square the corner. 50%, 0 and inherit
 * carry no px and stay legal.
 *
 * The value stops at `;` or `}`: one-line `styles:` strings end a rule with
 * `}` and no `;`, and running on to the next `;` would read the next
 * rule's px as this corner's.
 */
const RADIUS_DECL_RE = /border(?:-[a-z]+)*-radius:\s*([^;}]+)[;}]/g;
const RETIRED_RADIUS_RE = /var\(--radius(?:-chip)?\)/g;

describe('no raw or retired radius (v167 §3)', () => {
  for (const { name, source } of allSources()) {
    it(`${name} rounds every corner with a radius token`, () => {
      const code = stripComments(source);
      const raw = [...code.matchAll(RADIUS_DECL_RE)]
        .map(([, value]) => value.trim())
        .filter((value) => /\d+(\.\d+)?px/.test(value));
      expect(raw).toEqual([]);
      expect(code.match(RETIRED_RADIUS_RE) ?? []).toEqual([]);
    });
  }

  it('tokens.css declares neither --radius nor --radius-chip', () => {
    const tokens = stripComments(readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8'));
    expect(tokens).not.toMatch(/--radius:/);
    expect(tokens).not.toMatch(/--radius-chip:/);
  });
});
```

(`/--radius:/` cannot match `--panel-radius:` or `--panel-inner-radius:`: those have a single `-` before `radius`.)

In `frontend/src/app/ui/tokens.spec.ts`, re-read around the case `tightens both radii to 2px` and replace it with:

```ts
  /* v167 §3 supersedes v80 D3's single 2px: four targets, all in tier 3,
   * and the two old tokens are gone so no unclassified corner survives. */
  it('defines the four radius targets', () => {
    expect(TIER3).toMatch(/^\s*--panel-radius:\s*8px;/m);
    expect(TIER3).toMatch(/^\s*--control-radius:\s*6px;/m);
    expect(TIER3).toMatch(/^\s*--chip-radius:\s*999px;/m);
    expect(TIER3).toMatch(/^\s*--radius-sm:\s*2px;/m);
    expect(CSS).not.toMatch(/^\s*--radius(?:-chip)?:/m);
  });
```

- [ ] **Step 3: Run them and watch them fail**

Run:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/tokens.spec.ts
```
Expected: FAIL in `<file> rounds every corner with a radius token` for every workspace and v165/v166 file of Step 1 (and for none under `ui/`, `shell/` or `styles.css`), in `tokens.css declares neither --radius nor --radius-chip`, and in `defines the four radius targets` (the `not.toMatch` line).

- [ ] **Step 4: Move every workspace site onto its target**

Open each file, confirm the element matches its row (a contradiction is re-classified by the index's rule and named in the commit body), and replace only the radius value. Paths are under `frontend/src/app/workspaces/`.

| File:line | Selector | Before | After |
|---|---|---|---|
| `analytics/tabs/execution.ts:22` | `.verdict div` (a verdict card) | `.verdict div{padding:var(--space-10);border:1px solid var(--border);border-radius:var(--radius)}` | `.verdict div{padding:var(--space-10);border:1px solid var(--border);border-radius:var(--panel-radius)}` |
| `analytics/tabs/partials.ts:196` | `.tile.hero` | `.tile.hero{outline:1px solid var(--accent);border-radius:var(--radius)}` | `.tile.hero{outline:1px solid var(--accent);border-radius:var(--panel-radius)}` |
| `analytics/tabs/tuning.ts:253` | `.alert` | `border-radius: var(--radius);` | `border-radius: var(--panel-radius);` |
| `analytics/tabs/tuning.ts:300` | `.proposal` | `border-radius: var(--radius);` | `border-radius: var(--panel-radius);` |
| `calendar/calendar.ts:307` | `.metric` | `.metric { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius); }` | `.metric { display: inline-flex; border: 1px solid var(--border); border-radius: var(--control-radius); }` |
| `calendar/calendar.ts:491` | `.tag` | `border-radius: var(--radius);` | `border-radius: var(--chip-radius);` |
| `gallery/gallery.ts:736` | `.elev-step` | `border-radius: var(--radius);` | `border-radius: var(--panel-radius);` |
| `plans/plan-detail.ts:252` | `.tag` | `border-radius: var(--radius-chip);` | `border-radius: var(--chip-radius);` |
| `risk/risk.ts:504` | `.track` (6px bar) | `border-radius: 3px;` | `border-radius: var(--radius-sm);` |
| `risk/risk.ts:521` | `.state` (eyebrow tag) | `border-radius: var(--radius);` | `border-radius: var(--chip-radius);` |
| `system/logs-tab.ts:221` | `.log` | `border-radius: var(--radius);` | `border-radius: var(--panel-radius);` |
| `system/scan-tab.ts:185` | `.state` | `border-radius: var(--radius);` | `border-radius: var(--chip-radius);` |
| `system/settings-tab.ts:517` | `.restart` | `border-radius: var(--radius-chip);` | `border-radius: var(--chip-radius);` |
| `system/settings-tab.ts:532` | `.reset` | `border-radius: var(--radius-chip);` | `border-radius: var(--control-radius);` |
| `system/settings-tab.ts:547` | `.bar` | `border-radius: var(--radius);` | `border-radius: var(--panel-radius);` |
| `system/settings-tab.ts:563` | `.stale-form` | `border-radius: var(--radius);` | `border-radius: var(--panel-radius);` |
| `system/settings-tab.ts:604` | `.import-text` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `trades/trade-detail.ts:647` | `.tag` | `border-radius: var(--radius-chip);` | `border-radius: var(--chip-radius);` |
| `trades/trade-detail.ts:726` | `.note-field` | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `versions/versions.ts:285` | `.segment` | `border-radius: 2px;` | `border-radius: var(--radius-sm);` |
| `versions/versions.ts:289` | `.absent` | `border: 1px dashed var(--border-strong); border-radius: 2px; }` | `border: 1px dashed var(--border-strong); border-radius: var(--radius-sm); }` |
| `versions/versions.ts:292` | `.bracket` (12px row) | `border-radius: 3px; background: var(--surface-raised); }` | `border-radius: var(--radius-sm); background: var(--surface-raised); }` |
| `versions/versions.ts:322` | `.tooltip` | `border-radius: var(--radius); font-size: var(--text-micro); color: var(--text);` | `border-radius: var(--control-radius); font-size: var(--text-micro); color: var(--text);` |
| `versions/versions.ts:334` | `.sw` (swatch) | `.sw { display: inline-block; width: .8rem; height: .5rem; border-radius: 2px; }` | `.sw { display: inline-block; width: .8rem; height: .5rem; border-radius: var(--radius-sm); }` |
| `watchlist/earnings-calendar.ts:133` | `.grid` | `border-radius: var(--radius);` | `border-radius: var(--panel-radius);` |
| `watchlist/earnings-calendar.ts:167` | `.entry` (a cell entry) | `border-radius: var(--radius);` | `border-radius: var(--radius-sm);` |
| `watchlist/earnings-calendar.ts:193` | `.cell:has(.entry)` | `border-radius: var(--radius);` | `border-radius: var(--radius-sm);` |
| `watchlist/watchlist.ts:516` | `.suggestions` (dropdown list) | `border-radius: var(--radius);` | `border-radius: var(--control-radius);` |
| `watchlist/watchlist.ts:548` | `.source-badge` | `padding: 0 var(--space-6); border: 1px solid var(--warn); border-radius: var(--radius-chip);` | `padding: 0 var(--space-6); border: 1px solid var(--warn); border-radius: var(--chip-radius);` |

**One re-classification against the index table, already decided:** `calendar.ts:307 .metric` is listed under `--panel-radius`, but the element is `<div class="metric" role="group" aria-label="Metric">` wrapping the metric toggle's `sb-button`s, i.e. a segmented track (rule 3), so it takes `--control-radius` like `ui/segmented.ts`'s `.track`. Name it in the commit body.

Then the v165/v166 sites from Step 1, each by the rule (the four known constructs listed there).

- [ ] **Step 5: Delete the two old tokens and supersede the radii comments**

In `frontend/src/styles/tokens.css`, re-read the `-- radii, motion --` comment and the `--radius` lines (`:251-269` before AN7/AN8; find them by text). Replace the first two lines of that comment

```css
  /* -- radii, motion ---------------------------------------------------
   * Tight radii: terminal, not consumer app.
```

with

```css
  /* -- radii, motion ---------------------------------------------------
   * Tight radii: terminal, not consumer app.
   * Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §3):
   * the corners are the four targets in the tier-3 block at the end of this
   * file (--panel-radius 8px, --control-radius 6px, --chip-radius 999px,
   * --radius-sm 2px); --radius and --radius-chip are deleted.
```

and replace

```css
  /* v80 D3: 2px, was 4px / 3px -- a pro terminal's corners, not a card's. */
  --radius: 2px;
  --radius-chip: 2px;
```

with

```css
  /* v80 D3: 2px, was 4px / 3px -- a pro terminal's corners, not a card's.
     Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §3):
     --radius and --radius-chip are deleted. Every corner is classified onto
     one of the four tier-3 radius targets, and primitives.spec.ts fails a
     raw px radius or either old name anywhere outside styles/. */
```

Leave the motion part of the comment and every `--dur-*` / `--ease-*` declaration untouched (out of scope).

- [ ] **Step 6: Regenerate the fixture and check it**

Run:
```bash
python $WT/scripts/dev/dump_tokens.py
python $WT/scripts/dev/dump_tokens.py --check
git -C $WT diff --stat -- tests/charts/resolved_tokens.json
```
Expected: `--check` exits 0; the fixture diff is exactly two removed lines (the `"radius"` and `"radius-chip"` keys).

- [ ] **Step 7: Run the narrow runs**

Run the inventory once more:
```bash
git -C $WT grep -nE "var\(--radius(-chip)?\)|border[a-z-]*radius:\s*[0-9.]+px" -- frontend/src ':!*.spec.ts'
```
Expected: no output (this time `styles/` is included: `tokens.css` holds only the tier-3 targets, whose values are not matched).

Then:
```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui --include src/app/workspaces
python $WT/scripts/dev/testrun.py file tests/charts/test_chart_theme.py
python $WT/scripts/dev/testrun.py file tests/dev/test_dump_tokens.py
```
Expected: the frontend run `Tests  N passed`, 0 failed (`src/app/ui` carries every `GATES` spec, `src/app/workspaces` every workspace spec, v165/v166's included); both Python runs `N passed`, 0 failed (`test_resolver_reproduces_the_committed_fixture` proves the regenerated fixture). Quote all three verdict lines.

- [ ] **Step 8: Commit**

```bash
git -C $WT add frontend/src/app/workspaces frontend/src/app/ui/primitives.spec.ts frontend/src/app/ui/tokens.spec.ts frontend/src/styles/tokens.css tests/charts/resolved_tokens.json
git -C $WT commit -m "feat(ui): v167 AN13 -- workspace corners classified; radius gate; --radius and --radius-chip deleted

Every remaining var(--radius), var(--radius-chip) and raw px radius in
workspaces/ (v165/v166 components included) reads one of the four tier-3
targets. primitives.spec.ts gains 'no raw or retired radius' over
allSources(); tokens.spec.ts asserts the four targets; tokens.css drops
the two old tokens and marks the v80 D3 radii comments superseded; the
fixture is regenerated.

calendar.ts .metric: --control-radius, not the table's --panel-radius --
it is the metric toggle's segmented track (rule 3).
Other deviations: <none | site -- old row -> new row, reason>.
v165/v166 sites: <file:line selector -> target, one per line>.
Gone after the merge: <none | site>.

<frontend verdict line>
<test_chart_theme verdict line>
<test_dump_tokens verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task AN14: Visual pass: Playwright shots at 390 / 768 / 1440, before and after, signed off by the partner

**Model:** sonnet — runs two local stacks and judges shots against the pass criterion

**Files:**
- Modify: `frontend/scripts/browse.mjs:11-12` (usage), `:27-40` (`parseArgs`), `:66-100` (`shots`)
- Create: `docs/superpowers/results/v167/before/` (PNG + txt per path and width)
- Create: `docs/superpowers/results/v167/after/` (PNG + txt per path and width)
- Modify: `docs/superpowers/plans/2026-10-16-v167-arctic-navy-token-foundation_0-index.md` (`## Progress`, `## Handoff`; the branch copy in `$WT`)

**Interfaces:**
- Consumes: the finished look (AN7-AN13 committed on the branch); `main` in the main tree `$R` as the "before".
- Produces: `browse.mjs shots ... --click <css selector>`: after a path has loaded and settled, clicks the first match and waits 800 ms before measuring and shooting; a selector that matches nothing is reported on stderr and the shot is still taken. `--click` may repeat; the clicks run in the order given (the ledger's single-click form is the one-flag case). Every `<slug>@<width>.txt` now starts with a line `page-scroll-x: <n>` (document scroll width minus client width at the 900px-tall viewport, before the full-height grow), so "no horizontal page scroll" is read from a file, not judged by eye. The 18 shots under `docs/superpowers/results/v167/{before,after}/`.

**Needs the partner.** They type the local admin login into the headed Playwright window once (`browse.mjs` never fills, asks for or stores a credential; never read `.env` for one). The cookie is per host, not per port, so one sign-in on `localhost` serves both dev servers. The sign-off at the end is theirs too: the implementer prepares it, the controller asks.

**Pass criterion (spec, Testing and evidence), at each of 390 / 768 / 1440:** no horizontal page scroll (`page-scroll-x: 0` in every after txt); no text clipped by a new radius (pills on `--chip-radius` and controls on `--control-radius` are where it would show); every panel shows the gradient ground (`--panel-bg`) and the hairline (`--panel-border`); and the partner signs the set off in chat. The shots are evidence the partner reviews, not an automated diff.

**Known, recorded, not a failure:** `sb-figure-strip` carries `.sb-panel` and paints `--panel-bg` (AN9), but each Figure cell inside it still paints `background: var(--surface)`, so the strip's gradient is hidden behind its cells. That is the nested-panel case v169 owns (`--panel-inner-bg`, added by AN8). Note where it shows; do not fix it here.

- [ ] **Step 1: Add `--click` and the scroll measurement to `browse.mjs`**

In `frontend/scripts/browse.mjs`, replace the two usage lines `:11-12` with:

```js
 *   node scripts/browse.mjs shots --out <dir> --path "/trades/ID?tab=live" [--path ...]
 *                                 [--widths 1440,1024,768,390] [--base URL] [--click <css selector>]
```

and add, after the paragraph `Every \`shots\` capture is a full-page PNG ...` (`:16-17`), before the closing ` */`:

```js
 *
 * --click opens something before the shot (a drawer, a menu): after the
 * page settles it clicks the FIRST match and waits 800 ms. It may repeat;
 * the clicks run in the order given. Each .txt starts
 * with `page-scroll-x: <n>`, the document's horizontal overflow in px at
 * the 900px-tall viewport -- 0 means no horizontal page scroll.
```

In `parseArgs`, add `clicks: []` to the defaults object and one branch before the `else throw`:

```js
  const opts = { cmd: argv[0] ?? 'login', paths: [], widths: [1440, 1024, 768, 390], base: 'https://bomeo-capital.com', out: null, clicks: [] };
```

```js
    else if (flag === '--click') opts.clicks.push(value);
```

Add two helpers after `slug()`:

```js
/** --click: the first match only. A miss is reported, not fatal, so one
 *  empty page does not cost the rest of the set. */
async function clickFirst(page, selector, path) {
  const target = page.locator(selector).first();
  if ((await target.count()) === 0) {
    console.error(`--click matched nothing on ${path}: ${selector}`);
    return;
  }
  await target.click();
  await page.waitForTimeout(800);
}

/** Horizontal overflow of the page itself, in px: 0 means no sideways scroll. */
function pageScrollX(page) {
  return page.evaluate(() => {
    const doc = document.documentElement;
    return Math.max(doc.scrollWidth - doc.clientWidth, document.body.scrollWidth - document.body.clientWidth);
  });
}
```

In `shots`, right after `await page.waitForTimeout(1500);` insert:

```js
      for (const selector of opts.clicks) await clickFirst(page, selector, path);
      const scrollX = await pageScrollX(page);
```

and change the `writeFileSync` line to:

```js
      writeFileSync(`${name}.txt`, `page-scroll-x: ${scrollX}\n${await page.evaluate(() => document.body.innerText)}`);
```

Check the syntax:
```bash
node --check $WT/frontend/scripts/browse.mjs
```
Expected: no output, exit 0.

- [ ] **Step 2: Start the local stacks**

Each of these is a long-running process: start it with the Bash tool's `run_in_background`, never with `&`, and watch its output for the ready line.

```bash
test -d $WT/frontend/node_modules || npm --prefix $WT/frontend ci
python $R/admin_ui.py
npm --prefix $R/frontend exec -- ng serve --port 4123
npm --prefix $WT/frontend exec -- ng serve --port 4124
```

- `admin_ui.py` is the one API both dev servers proxy to (`frontend/proxy.conf.json` -> `http://localhost:1234`); run it from `$R`, the backend is the same in both trees. If it exits (no database reachable from this machine, a missing setting), stop here and report `BLOCKED:` with its last log lines; do not point the proxy anywhere else.
- `:4123` is this repo's `ng serve` port (`docs/claude/skills-tools.md`); the main tree serves the before look there. The worktree needs a second port at the same time; `:4124` is the after look.
- Ready when each `ng serve` prints `Local: http://localhost:412x/`.

- [ ] **Step 3: Sign in once**

```bash
node $WT/frontend/scripts/browse.mjs login --base http://localhost:4123
```
Tell the controller the window is waiting; the partner types the local admin login. `Signed in.` on stderr ends the step.

- [ ] **Step 4: Take the before and after sets**

```bash
node $WT/frontend/scripts/browse.mjs shots --base http://localhost:4123 --out $WT/docs/superpowers/results/v167/before --widths 390,768,1440 --path dashboard --path trades
node $WT/frontend/scripts/browse.mjs shots --base http://localhost:4123 --out $WT/docs/superpowers/results/v167/before --widths 390,768,1440 --path calendar --click "button.value"
node $WT/frontend/scripts/browse.mjs shots --base http://localhost:4124 --out $WT/docs/superpowers/results/v167/after --widths 390,768,1440 --path dashboard --path trades
node $WT/frontend/scripts/browse.mjs shots --base http://localhost:4124 --out $WT/docs/superpowers/results/v167/after --widths 390,768,1440 --path calendar --click "button.value"
```
`button.value` is a calendar day's value button (`calendar.ts:163` before v165), which opens the day drawer. v165 (calendar day page, merged in AN12) reworks that drawer; re-read `calendar.ts` after the merge and, if the selector or the drawer changed, use the selector that now opens it (and name it in the commit body). The spec asks for an open drawer, so the shot must show one. Expected: 9 PNG + 9 txt in each directory (`dashboard@390.png` ... `calendar@1440.png`). If stderr says `--click matched nothing on /calendar: button.value`, the current month has no closed trades locally: re-run that calendar line in both sets with `--click 'button[aria-label="Previous month"]'` before `--click "button.value"` (repeat the previous-month click until the trades shot's dates are reached), so both sets open the same day.

- [ ] **Step 5: Judge the after set against the pass criterion**

```bash
grep -H "^page-scroll-x:" $WT/docs/superpowers/results/v167/after/*.txt $WT/docs/superpowers/results/v167/before/*.txt
```
Expected: `page-scroll-x: 0` on every after file. A non-zero after value where the before value is 0 is a v167 regression: find the element (usually a pill or control that grew with its radius) and fix it in the file that owns it, with its own `fix(ui): v167 AN14 -- ...` commit and the narrow run of that file's spec, then re-shoot that path.

Then open every after PNG with the Read tool, beside its before twin, and write down per shot: clipped text (yes/no, where), panels with gradient ground and hairline (yes/no, which not), and anything else that changed shape. The `sb-figure-strip` gradient hidden behind its cells is the known v169 item above: list it, do not count it.

- [ ] **Step 6: Get the partner's sign-off**

Report to the controller, in one message: the 18 PNG paths (absolute, `$WT/docs/superpowers/results/v167/...`), the `page-scroll-x` lines, the per-shot notes from Step 5 and the known v169 item. The controller asks the partner (`AskUserQuestion`, recommended option first: "Signed off") and passes back the answer. Without "signed off", the task is not done: fix what the partner names, re-shoot, ask again.

- [ ] **Step 7: Record the result and stop the stacks**

In `$WT/docs/superpowers/plans/2026-10-16-v167-arctic-navy-token-foundation_0-index.md`, replace the `## Progress` body (`Not started. ...`) with:

```markdown
- **Phases 1-3 (AN1-AN13):** done on branch `2026-10-16-v167-arctic-navy-token-foundation`.
- **Visual pass (AN14), <YYYY-MM-DD>:** 18 shots in `docs/superpowers/results/v167/{before,after}/` at 390 / 768 / 1440 (dashboard, trades, calendar with the day drawer open). `page-scroll-x: 0` on every after shot; <no clipped text | what was fixed>; panels show the gradient ground and hairline. Signed off by the partner in chat on <YYYY-MM-DD>.
- **Next:** AN15, the full suite.
```

and append to `## Handoff`:

```markdown
- **For v169 (from AN14):** `sb-figure-strip` carries `.sb-panel` and paints `--panel-bg`, but each Figure cell paints `background: var(--surface)` over it, so the strip's gradient does not show. Nested-panel case: the cells should read `--panel-inner-bg` (or go transparent). Seen in <which shots>.
```

Stop the three background processes (`admin_ui.py`, both `ng serve`).

- [ ] **Step 8: Commit**

```bash
git -C $WT add frontend/scripts/browse.mjs docs/superpowers/results/v167 docs/superpowers/plans/2026-10-16-v167-arctic-navy-token-foundation_0-index.md
git -C $WT commit -m "test(ui): v167 AN14 -- visual pass, before and after at 390/768/1440

browse.mjs gains --click (open a drawer before the shot) and writes
page-scroll-x at the top of every .txt. 18 shots of dashboard, trades and
the calendar day drawer, before (main) and after (this branch). Every
after shot has page-scroll-x: 0; the partner signed the set off on
<YYYY-MM-DD>. The figure-strip gradient hidden by its cells is handed to
v169 in the index.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task AN15: Full Python suite, whole frontend spec run, radon and fixture checks

**Model:** haiku — runs commands, no code

**Files:** none. This task changes nothing unless a check fails (see Step 5).

**Interfaces:**
- Consumes: every commit AN1-AN14 on the branch.
- Produces: the verdict lines `/close-out` needs: full Python suite, whole frontend run, `dump_tokens.py --check`, radon.

This is the plan's single full-suite run (`docs/claude/document-conventions.md`, "Naming specs and plans" in `CLAUDE.md`). Nothing after it re-runs the suite: not the merge back to `main`, not `/close-out`.

- [ ] **Step 1: Confirm the branch is clean**

```bash
git -C $WT status --short
```
Expected: no output. Anything listed belongs to an earlier task: stop and report it rather than committing it here.

- [ ] **Step 2: Full Python suite**

Dispatch the `test-runner` subagent (so the output stays out of the controller's context) with:
```bash
python $WT/scripts/dev/testrun.py full
```
Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). Quote the verdict line.

- [ ] **Step 3: Whole frontend spec run**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false
```
Expected: `Tests  N passed`, 0 failed. A 60 s `Timeout waiting for worker ... no tests` before anything ran is machine load: re-run once. Quote the verdict line.

- [ ] **Step 4: Fixture, syntax and complexity**

```bash
python $WT/scripts/dev/dump_tokens.py --check
python -m py_compile $WT/scripts/dev/dump_tokens.py $WT/scripts/dev/select_tests.py $WT/swingbot/core/charts/chart_style.py $WT/swingbot/core/charts/cache.py
python -m radon cc -s -n C $WT/scripts/dev/dump_tokens.py $WT/swingbot/core/charts/cache.py
python -m radon cc -s -n C $WT/scripts/dev/select_tests.py $WT/swingbot/core/charts/chart_style.py
```
Expected: `--check` exits 0; `py_compile` prints nothing; the first radon line prints nothing (every function in the two files v167 created or changed is under rank C, i.e. complexity < 11, well inside the < 15 rule). The second radon line may list legacy functions; none of them may be one v167 touched (v167 changed only the `ESCALATE_PREFIXES` tuple in `select_tests.py` and module-level constants in `chart_style.py`, no function body). Quote the outputs.

- [ ] **Step 5: On a failure**

A failed test is fixed and re-run alone, never by re-running the suite: find the task whose files own the failure, fix it in those files with a `fix(...): v167 AN15 -- <what>` commit on the branch, then run only that test (`python $WT/scripts/dev/testrun.py file <test>` or `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>`) and quote its verdict line. Do not loosen a gate, a threshold or a contrast figure to get green; a contrast or ΔE failure reopens the spec's table (index, Global Constraints).

- [ ] **Step 6: Report**

No commit when Steps 2-4 were green on the first run. Report to the controller: the four verdicts (Python full, frontend whole, `--check`, radon) and any Step 5 fix commits with their single-test verdicts. The controller then runs `/close-out` (the `**Bump:**` is `ui minor; bot patch`; no task edits `VERSION.json`).

