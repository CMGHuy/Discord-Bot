# v240 — Doctena night, plan 1 of 5: Theme and type — Part 1b: cold load and controls

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V240-6" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) (§1, §11; its `### Corrections from the plan 1 code brief` section wins over the text above it)
**Index:** [2026-11-23-v240-doctena-night-theme-and-type_0-index.md](2026-11-23-v240-doctena-night-theme-and-type_0-index.md) holds the Goal, Global Constraints, the "Decisions this index fixes", `## Parallelisation` and the task ledger. Every task below implicitly includes the index's Global Constraints.

Part 1 overflowed: V240-1..V240-4 fill
[`_1-fonts-and-colours.md`](2026-11-23-v240-doctena-night-theme-and-type_1-fonts-and-colours.md)
to the 1500-line cap, so its last two tasks live here, unchanged in id,
files and contracts. Run them after V240-4: V240-5 (the Navy cold load) and
V240-6 (`styleRules` and `--control-border`).

Conventions for every task in this part:

- Frontend commands run from `frontend/`:
  `cd frontend && npx ng test --watch=false --include <spec> [--include <spec>]`.
  A 60s `Timeout waiting for worker` is machine load: re-run once.
- No task runs the full suite (CI does). Commits are scoped; stage only the
  files the task names.

# Phase 2 (continued): the default theme at cold load

### Task V240-5: Cold load in Navy: pre-boot script with `GRAPHITE_BG`, static meta, inline ground, web manifest

**Model:** sonnet — the pre-paint script and its pinned copies must change together; the script runs before Angular, so its tests execute it directly.

**Files:**
- Modify: `frontend/src/index.html` (theme-color meta and its comment, the pre-paint script and its comment, the inline ground and its comment)
- Modify: `frontend/public/manifest.webmanifest` (`theme_color`, `background_color`)
- Modify: `frontend/src/app/ui/primitives.spec.ts` (`HEX_ALLOWLIST` entry; the `the cold-load copies …` and `the Dark blue cold load (v225)` describes)

**Interfaces:**
- Consumes: Navy `--bg` = `--doctena-950` = `#00131f` (V240-3); `readTheme`'s
  rule, Black only for exactly `'graphite'` (V240-4).
- Produces: the index.html script vars `NAVY_BG = '#00131f'` and
  `GRAPHITE_BG = '#0d0f12'`; the comment phrase
  `manifest.webmanifest takes the Navy ground`. No TypeScript symbol.

Why: spec v240 §1 and its corrections: a default user must never see a
Graphite flash. The static meta, the inline `html, body` ground and the
manifest all take the Navy `--bg`. The pre-boot script always sets
`data-theme` (index Decision 2): `navy` unless storage holds exactly
`'graphite'`, and `navy` when storage throws. So the first paint already
uses the Navy tokens, not just the Navy ground. It sets the meta to
`NAVY_BG` or `GRAPHITE_BG`. It injects a ground `<style>` only for
Graphite, scoped to `html[data-theme="graphite"]` so that switching to Dark
blue later drops it. `HEX_ALLOWLIST`'s `index.html` entry is exact and in
source order, so it gains `GRAPHITE_BG`, and the script now holds two hex
literals.

- [ ] **Step 1: Rewrite the primitives specs (they fail)**

In `frontend/src/app/ui/primitives.spec.ts`:

1. Replace the `HEX_ALLOWLIST` constant with:

```ts
const HEX_ALLOWLIST = new Map<string, string[]>([
  // The four cold-load copies, in file order: the theme-color meta (Navy,
  // the default look since v240), NAVY_BG and GRAPHITE_BG in index.html's
  // pre-paint script, and the inline html/body ground (Navy). They paint
  // before any stylesheet has loaded, so they cannot read var(--bg); the
  // cold-load describes below fail the moment one drifts from palette.css.
  ['index.html', ['#00131f', '#00131f', '#0d0f12', '#00131f']],
]);
```

2. Replace the whole `describe('the cold-load copies equal the resolved --bg (v167 §7)', ...)`
   block (keep the JSDoc above it, appending one sentence: `Since v240 the
   copies hold the Navy --bg, the default look.`) with:

```ts
describe('the cold-load copies equal the resolved Navy --bg (v167 §7, v240)', () => {
  const bg = resolveTokenIn('navy', '--bg').toLowerCase();
  const read = (file: string) => readFileSync(join(process.cwd(), file), 'utf8');

  it('index.html paints the theme-color meta in the Navy --bg', () => {
    const meta = read('src/index.html').match(/<meta name="theme-color" content="([^"]+)">/);
    expect(meta?.[1].toLowerCase()).toBe(bg);
  });

  it('index.html paints the inline cold-load ground in the Navy --bg', () => {
    const inline = read('src/index.html').match(/<style>html, body \{ background: ([^;]+); \}<\/style>/);
    expect(inline?.[1].toLowerCase()).toBe(bg);
  });

  it("the manifest's theme_color and background_color are the Navy --bg", () => {
    const manifest = JSON.parse(read('public/manifest.webmanifest'));
    expect(manifest.theme_color.toLowerCase()).toBe(bg);
    expect(manifest.background_color.toLowerCase()).toBe(bg);
  });
});
```

3. Replace the whole `the Dark blue cold load (v225)` block, its JSDoc
   included, with:

```ts
/**
 * v225, v240: the chosen look paints from the first frame. index.html's
 * inline script reads ui.theme before the bundle parses and mirrors
 * ui/theme.service.ts readTheme: Black only for exactly 'graphite', Navy
 * otherwise (missing, junk, or a throwing localStorage). It always sets
 * data-theme. For Black it also swaps the theme-color meta and adds a Black
 * ground scoped to html[data-theme="graphite"], so a later switch to Dark
 * blue drops it. The manifest carries the Navy ground, the default.
 */
describe('the pre-paint theme script (v225, v240)', () => {
  const INDEX = readFileSync(join(process.cwd(), 'src/index.html'), 'utf8');
  const script = INDEX.match(/<script>([\s\S]*?)<\/script>/)?.[1] ?? '';
  const html = document.documentElement;
  const NAVY = resolveTokenIn('navy', '--bg').toLowerCase();
  const GRAPHITE = resolveToken('--bg').toLowerCase();
  let meta: HTMLMetaElement;

  const run = () => new Function(script)();
  const injected = () =>
    [...document.head.querySelectorAll('style')].filter((s) => s.textContent!.includes('data-theme="graphite"'));

  beforeEach(() => {
    meta = document.createElement('meta');
    meta.name = 'theme-color';
    meta.content = '';
    document.head.appendChild(meta);
  });

  afterEach(() => {
    meta.remove();
    injected().forEach((s) => s.remove());
    delete html.dataset['theme'];
    localStorage.removeItem(THEME_PREF_KEY);
    vi.restoreAllMocks();
  });

  it('holds each ground once: NAVY_BG is --doctena-950, GRAPHITE_BG is --graphite-950', () => {
    const navy = script.match(/var NAVY_BG = '([^']+)';/)?.[1].toLowerCase();
    const graphite = script.match(/var GRAPHITE_BG = '([^']+)';/)?.[1].toLowerCase();
    expect(navy).toBe(resolveToken('--doctena-950').toLowerCase());
    expect(navy).toBe(NAVY);
    expect(graphite).toBe(resolveToken('--graphite-950').toLowerCase());
    expect(graphite).toBe(GRAPHITE);
    expect(script.match(/#[0-9a-f]{6}/gi)).toHaveLength(2);
  });

  it('sits after the theme-color meta and before the inline ground style', () => {
    const at = INDEX.indexOf('<script>');
    expect(at).toBeGreaterThan(INDEX.indexOf('<meta name="theme-color"'));
    expect(at).toBeLessThan(INDEX.indexOf('<style>html, body {'));
  });

  it(`turns Black only on exactly 'graphite' under ${THEME_PREF_KEY}, reading storage inside try/catch`, () => {
    expect(script).toContain(`localStorage.getItem('${THEME_PREF_KEY}') === 'graphite'`);
    expect(script).toMatch(/try \{[\s\S]*\} catch \(e\) \{/);
  });

  it('paints Black when ui.theme is graphite: attribute, meta and a scoped ground', () => {
    localStorage.setItem(THEME_PREF_KEY, 'graphite');
    run();
    expect(html.dataset['theme']).toBe('graphite');
    expect(meta.content.toLowerCase()).toBe(GRAPHITE);
    const rules = injected();
    expect(rules).toHaveLength(1);
    expect(rules[0].textContent).toBe(
      `html[data-theme="graphite"], html[data-theme="graphite"] body { background: ${resolveToken('--graphite-950')}; }`,
    );
  });

  it.each([null, 'navy', 'GRAPHITE', 'graphite ', '', 'black'])('paints Navy for %j: attribute and meta, no injected ground', (stored) => {
    if (stored !== null) localStorage.setItem(THEME_PREF_KEY, stored);
    run();
    expect(html.dataset['theme']).toBe('navy');
    expect(meta.content.toLowerCase()).toBe(NAVY);
    expect(injected()).toHaveLength(0);
  });

  it('swallows a throwing localStorage and paints Navy, the default', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('denied', 'SecurityError'); });
    expect(run).not.toThrow();
    expect(html.dataset['theme']).toBe('navy');
    expect(meta.content.toLowerCase()).toBe(NAVY);
  });

  it('runs without a theme-color meta in the document', () => {
    meta.remove();
    localStorage.setItem(THEME_PREF_KEY, 'graphite');
    expect(run).not.toThrow();
    expect(html.dataset['theme']).toBe('graphite');
  });

  it('says beside the cold-load copies that the manifest takes the Navy ground', () => {
    expect(INDEX).toMatch(/manifest\.webmanifest takes the Navy ground/);
    expect(INDEX).not.toMatch(/manifest\.webmanifest stays Graphite/);
    const manifest = JSON.parse(readFileSync(join(process.cwd(), 'public/manifest.webmanifest'), 'utf8'));
    expect(manifest.theme_color.toLowerCase()).toBe(NAVY);
  });
});
```

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/primitives.spec.ts`
Expected: FAIL — the colour gate on `index.html` (found
`['#0d0f12', '#00131f', '#0d0f12']`), the three cold-load copies (Graphite
`#0d0f12`), `GRAPHITE_BG` missing, the script still Graphite by default, and
the manifest phrase.

- [ ] **Step 3: Rewrite the cold-load block of `index.html`**

In `frontend/src/index.html`, replace everything from the comment above
`<meta name="theme-color" ...>` through the closing `</script>` of the
pre-paint script with:

```html
  <!-- A copy of the Navy --bg (palette.css --doctena-950): the browser reads
       the theme-color before any stylesheet loads, so it cannot be
       var(--bg). Navy is the default look since v240; the pre-paint script
       below swaps it to GRAPHITE_BG when this browser chose Black.
       primitives.spec.ts allow-lists it and asserts it equals the resolved
       Navy --bg (spec v167 §7). -->
  <meta name="theme-color" content="#00131f">
  <!-- v225, v240: paints the chosen look from the first frame. Runs before
       the bundle parses and mirrors ui/theme.service.ts readTheme: Black
       only for exactly ui.theme = 'graphite', Navy otherwise (missing,
       junk, or a blocked localStorage). It always sets data-theme. For
       Black it also swaps the theme-color meta above to GRAPHITE_BG and
       adds a Black ground scoped to html[data-theme="graphite"], so a later
       switch to Dark blue drops it. ThemeService applies the same theme on
       bootstrap. NAVY_BG is a copy of palette.css --doctena-950 and
       GRAPHITE_BG of --graphite-950; primitives.spec.ts pins both. -->
  <script>
    (function () {
      var NAVY_BG = '#00131f';
      var GRAPHITE_BG = '#0d0f12';
      var theme = 'navy';
      try {
        if (localStorage.getItem('ui.theme') === 'graphite') theme = 'graphite';
      } catch (e) {
        /* Blocked storage: Navy, the default. */
      }
      document.documentElement.setAttribute('data-theme', theme);
      var meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute('content', theme === 'graphite' ? GRAPHITE_BG : NAVY_BG);
      if (theme === 'graphite') {
        var ground = document.createElement('style');
        ground.textContent = 'html[data-theme="graphite"], html[data-theme="graphite"] body { background: ' + GRAPHITE_BG + '; }';
        document.head.appendChild(ground);
      }
    })();
  </script>
```

Then replace the comment above `<style>html, body { background: #0d0f12; }</style>`
and that line with:

```html
  <!-- Painted before the bundle parses, so a slow load shows the app's own
       ground colour rather than a white flash on a UI that is dark by
       definition. It is the Navy ground, the default look since v240; a
       browser that chose Black gets the scoped Black ground the pre-paint
       script adds above, which outranks this rule.

       This hex is one of the four colour literals the colour gate
       deliberately leaves in place (the theme-color meta, NAVY_BG and
       GRAPHITE_BG in the pre-paint script, and this one): it has to be
       inline and it has to work before any stylesheet loads, so it cannot
       read `--bg`. It is therefore a copy, and copies drift -- so
       primitives.spec.ts ('the cold-load copies equal the resolved Navy
       --bg', spec v167 §7, v240) fails when it differs from the Navy --bg
       in styles/palette.css, as does the manifest's pair. The symptom it
       prevents is a one-frame flash of the old colour on a cold load, which
       is easy to miss and easy to explain once seen.

       manifest.webmanifest takes the Navy ground (spec v240): a manifest is
       static and installed once, so it cannot follow a per-browser choice
       and carries the default. A Black user's home-screen splash is dark
       blue for an instant, accepted. The manifest is JSON and cannot carry
       this note itself. -->
  <style>html, body { background: #00131f; }</style>
```

- [ ] **Step 4: Move the manifest to the Navy ground**

In `frontend/public/manifest.webmanifest`, change lines 6–7 to:

```json
  "theme_color": "#00131f",
  "background_color": "#00131f",
```

- [ ] **Step 5: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/theme.service.spec.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/index.html frontend/public/manifest.webmanifest frontend/src/app/ui/primitives.spec.ts
git commit -m "feat(v240): cold load in Navy -- pre-paint script always sets data-theme, GRAPHITE_BG only for an explicit Black; meta, inline ground and manifest take the Navy --bg

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 3: The shared style parser and the control border

### Task V240-6: `styleRules` parser; `--control-border` on inputs, selects and segmented controls

**Model:** sonnet — a small parser that four later gates depend on, with edge cases (interpolations, arrays, `@media`) that must be pinned exactly.

**Files:**
- Create: `frontend/src/app/ui/testing/style-rules.ts`
- Create: `frontend/src/app/ui/testing/style-rules.spec.ts`
- Create: `frontend/src/app/ui/control-border.spec.ts`
- Modify: `frontend/src/app/ui/form-controls.ts` (the `select` rule ~line 56, the `input` rule ~line 115, their comments)
- Modify: `frontend/src/app/ui/form-controls.spec.ts` (`v195 Phase 2: flat fields`, ~lines 85–100)
- Modify: `frontend/src/app/ui/segmented.ts` (the `.track` rule, line 20)
- Modify: `frontend/src/app/ui/date-range.ts` (the `input` rule, ~line 47)
- Modify: `frontend/src/app/ui/pagination.ts` (the `.per-page select, .jump` rule, line 45)
- Modify: `frontend/src/app/ui/data-table/data-table.ts` (the `.phone-sort select` rule, line 459)

**Interfaces:**
- Consumes: `--control-border` (V240-3: bare `var(--border-strong)`, Navy
  `var(--doctena-blue-600)`); `stripComments(source: string): string` from
  `frontend/src/app/ui/testing/all-sources.ts`.
- Produces, in `frontend/src/app/ui/testing/style-rules.ts`:
  - `export type StyleRule = { selector: string; body: string };`
  - `export function styleRules(name: string, source: string): StyleRule[]`.
    `name` is the file name as `allSources()` gives it (relative to `src/`,
    forward slashes). A `.css` file is read whole. A `.ts` file yields every
    template literal under `styles:`, a single literal or an array of them.
    Anything else (`.html`) yields `[]`. Comments are stripped and each
    `${…}` interpolation becomes `__expr__`. The selector is trimmed to its
    last line, with a comma-continued selector list joined onto one line.
    The body is trimmed. Rules inside `@media`/`@container`/`@keyframes`
    come back as their inner rules.
  - V240-7 (thin-bar radius), V240-9 (type gates) and V240-10 (money colour)
    import it.

Why: spec v240 §1 gives inputs, selects and segmented controls a visible
`--control-border` (`#0072b0` in Navy, 3.28:1 on `--surface`, WCAG 1.4.11).
`--border` stays decorative on panels and rules. Today these controls draw
`--border-strong`, about 1.5:1 in Black. Black keeps that value through the
token's bare `var(--border-strong)` (index Decision 1), so Black looks the
same. Four later gates (control border, thin-bar radius, type, money colour)
must read only real style text, so they share one parser (index
Architecture). It reads `.css` whole and `.ts` `styles:` literals only, so
a TypeScript block like `if (x) { y(); }` or a template's `{{ v }}` is never
mistaken for a CSS rule. Some components interpolate a token name into
their styles (`bar-list.ts`: `color:var(${CHART_CHROME.tickColour})`), so
interpolations are neutralised before rule matching. Pagination's page
buttons and the other `--border-strong` uses (spinners, table rules,
dividers) are not controls in the spec's sense and stay as they are.

- [ ] **Step 1: Write the failing parser spec**

Create `frontend/src/app/ui/testing/style-rules.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { styleRules } from './style-rules';

describe('styleRules (v240)', () => {
  it('reads a .css file whole, including the rules inside @media', () => {
    const css = '.a { color: red; }\n@media (max-width: 639px) {\n  .b { gap: 0; }\n}\n';
    expect(styleRules('app/shell/x.css', css)).toEqual([
      { selector: '.a', body: 'color: red;' },
      { selector: '.b', body: 'gap: 0;' },
    ]);
  });

  it("reads a .ts file's styles: literal and never its code or template", () => {
    const ts = [
      'export class X {',
      '  run() { if (this.ok) { this.go(); } }',
      '}',
      '@Component({ selector: "sb-x", template: `<p class="a">{{ v }}</p>`, styles: `',
      '    :host { display: block; }',
      '    .a { color: var(--text); }',
      '  `})',
    ].join('\n');
    expect(styleRules('app/ui/x.ts', ts)).toEqual([
      { selector: ':host', body: 'display: block;' },
      { selector: '.a', body: 'color: var(--text);' },
    ]);
  });

  it('reads every literal of a styles: array', () => {
    const ts = '@Component({ styles: [`.a { x: 1; }`, `\n  .b { y: 2; }\n`] })';
    expect(styleRules('app/ui/x.ts', ts)).toEqual([
      { selector: '.a', body: 'x: 1;' },
      { selector: '.b', body: 'y: 2;' },
    ]);
  });

  it('returns nothing for a .ts file without styles:', () => {
    expect(styleRules('app/ui/x.ts', 'export const f = () => { return { a: 1 }; };')).toEqual([]);
  });

  it('returns nothing for .html, even when it holds an inline <style>', () => {
    expect(styleRules('index.html', '<style>html, body { background: red; }</style>')).toEqual([]);
  });

  it('strips comments before reading rules', () => {
    const css = '/* .ghost { a: b; } */\n.real { c: d; } // .line { e: f; }\n';
    expect(styleRules('styles.css', css)).toEqual([{ selector: '.real', body: 'c: d;' }]);
  });

  it('neutralises an interpolation so its braces do not split a rule', () => {
    const ts = 'styles:`.label{color:var(${CHART.tick});font-size:12px}.n{gap:0}`';
    expect(styleRules('app/ui/x.ts', ts)).toEqual([
      { selector: '.label', body: 'color:var(__expr__);font-size:12px' },
      { selector: '.n', body: 'gap:0' },
    ]);
  });

  it('joins a selector list broken over lines, and drops a stray line above the selector', () => {
    expect(styleRules('a.css', '.a,\n  .b {\n  c: d;\n}')).toEqual([{ selector: '.a, .b', body: 'c: d;' }]);
    expect(styleRules('a.css', 'stray words\n.a { b: c; }')).toEqual([{ selector: '.a', body: 'b: c;' }]);
  });

  it("reads a real component: button.ts's :host rule", () => {
    const source = readFileSync(join(process.cwd(), 'src/app/ui/button.ts'), 'utf8');
    const host = styleRules('app/ui/button.ts', source).find((rule) => rule.selector === ':host');
    expect(host?.body).toContain('border-radius: var(--control-radius);');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/testing/style-rules.spec.ts`
Expected: FAIL — `Cannot find module './style-rules'` (or "Failed to resolve import").

- [ ] **Step 3: Implement `style-rules.ts`**

Create `frontend/src/app/ui/testing/style-rules.ts`:

```ts
import { stripComments } from './all-sources';

/**
 * One CSS rule as written in a source file: its selector and the text
 * between its braces, both trimmed. Test-only (spec v240 §1, §2, §11).
 */
export type StyleRule = { selector: string; body: string };

/** Innermost `selector { body }` pairs: an @media, @container or @keyframes
 *  wrapper is skipped and the rules inside it are read. */
const RULE_RE = /([^{};]+)\{([^{}]*)\}/g;

/** A template-literal interpolation inside a style (`var(${TOKEN})`). Its
 *  braces would split a rule, and no gate can see through it anyway. */
const INTERPOLATION_RE = /\$\{[^}]*\}/g;

/**
 * Every CSS rule in one source file, in order, read only from real style
 * text, so a gate never mistakes `if (x) { y(); }` or a template's
 * `{{ v }}` for a rule:
 * - a `.css` file: the whole file;
 * - a `.ts` file: every template literal under a component's `styles:`,
 *   one literal or an array of them;
 * - anything else (`.html`): nothing.
 *
 * Comments are stripped and interpolations become `__expr__`. The selector
 * is the rule's last line, so a stray line above it never leaks in; a
 * selector list broken over lines with trailing commas is joined back.
 * `name` is the file name as allSources() gives it ('app/ui/button.ts').
 */
export function styleRules(name: string, source: string): StyleRule[] {
  const texts = name.endsWith('.css') ? [source] : name.endsWith('.ts') ? stylesLiterals(source) : [];
  return texts.flatMap((text) => rulesIn(stripComments(text).replace(INTERPOLATION_RE, '__expr__')));
}

function rulesIn(css: string): StyleRule[] {
  return [...css.matchAll(RULE_RE)].map(([, selector, body]) => ({ selector: lastSelector(selector), body: body.trim() }));
}

/** The selector's last line, extended upwards over lines that end in a comma. */
function lastSelector(raw: string): string {
  const lines = raw.split('\n').map((line) => line.trim()).filter(Boolean);
  let start = lines.length - 1;
  while (start > 0 && lines[start - 1].endsWith(',')) start--;
  return lines.slice(start).join(' ');
}

/** The text of every template literal under `styles:`, single or in an array. */
function stylesLiterals(source: string): string[] {
  const out: string[] = [];
  for (const match of source.matchAll(/\bstyles:\s*(\[)?/g)) {
    let literal = literalAt(source, match.index! + match[0].length);
    while (literal) {
      out.push(literal.text);
      literal = match[1] ? literalAt(source, literal.end) : null;
    }
  }
  return out;
}

/** The template literal at the first non-separator (space, comma) from `from`, or null. */
function literalAt(source: string, from: number): { text: string; end: number } | null {
  let at = from;
  while (at < source.length && /[\s,]/.test(source[at])) at++;
  if (source[at] !== '`') return null;
  const close = source.indexOf('`', at + 1);
  return close < 0 ? null : { text: source.slice(at + 1, close), end: close + 1 };
}
```

- [ ] **Step 4: Run the parser spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/testing/style-rules.spec.ts`
Expected: PASS (9 tests).

- [ ] **Step 5: Write the failing control-border gate and update the form-controls pin**

Create `frontend/src/app/ui/control-border.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { styleRules } from './testing/style-rules';

/**
 * Spec v240 §1: inputs, selects and segmented controls are outlined in
 * --control-border (doctena blue in Navy, 3.28:1 on --surface, WCAG 1.4.11;
 * the strong hairline under Black, index Decision 1). --border stays the
 * decorative panel and rule colour. One row per control rule: the file,
 * relative to src/, and its exact selector (the first rule with it).
 */
const CONTROLS: [file: string, selector: string][] = [
  ['app/ui/form-controls.ts', 'select'],
  ['app/ui/form-controls.ts', 'input'],
  ['app/ui/date-range.ts', 'input'],
  ['app/ui/segmented.ts', '.track'],
  ['app/ui/pagination.ts', '.per-page select, .jump'],
  ['app/ui/data-table/data-table.ts', '.phone-sort select'],
];

const rulesOf = (file: string) => styleRules(file, readFileSync(join(process.cwd(), 'src', file), 'utf8'));

describe('v240: controls are outlined in --control-border', () => {
  for (const [file, selector] of CONTROLS) {
    it(`${file} "${selector}" draws its border in --control-border`, () => {
      const rule = rulesOf(file).find((candidate) => candidate.selector === selector);
      expect(rule, `${file} ${selector}`).toBeDefined();
      expect(rule!.body).toContain('border: 1px solid var(--control-border);');
      expect(rule!.body).not.toContain('--border-strong');
    });
  }

  it('leaves no input or select rule in those files on the strong hairline', () => {
    const files = [...new Set(CONTROLS.map(([file]) => file))];
    const offenders = files.flatMap((file) =>
      rulesOf(file)
        .filter((rule) => /(^|[\s,])(input|select)\b/.test(rule.selector))
        .filter((rule) => /\bborder:[^;]*var\(--border-strong\)/.test(rule.body))
        .map((rule) => `${file} ${rule.selector}`));
    expect(offenders).toEqual([]);
  });
});
```

In `frontend/src/app/ui/form-controls.spec.ts`, replace the comment above
`describe('v195 Phase 2: flat fields', ...)` and its first test with:

```ts
/* v195 Phase 2: since V195-3 a panel is the flat --surface, so a field on
 * --surface had no fill step left against it. Fields sit one step down, on
 * the --bg well, behind the control border (v240: --control-border, 3:1 in
 * Navy); the accent is the focus ring and the checkbox tick only. */
describe('v195 Phase 2: flat fields', () => {
  const field = (tag: 'select' | 'input') => SOURCE.match(new RegExp(`\\n {4}${tag} \\{[^}]*\\}`))?.[0] ?? '';

  it('fills the select and the text input with the --bg well behind the control border', () => {
    for (const tag of ['select', 'input'] as const) {
      const rule = field(tag);
      expect(rule, tag).toContain('background: var(--bg);');
      expect(rule, tag).toContain('border: 1px solid var(--control-border);');
      expect(rule, tag).toContain('border-radius: var(--control-radius);');
      expect(rule, tag).toContain('transition: border-color var(--transition);');
    }
    expect(SOURCE).not.toContain('background: var(--surface);');
  });
```

(The remaining tests in that describe stay as they are.)

- [ ] **Step 6: Run them to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/control-border.spec.ts --include src/app/ui/form-controls.spec.ts`
Expected: FAIL — all six control rules still read `--border-strong`.

- [ ] **Step 7: Point the six control rules at `--control-border`**

In each rule below, change `border: 1px solid var(--border-strong);` to
`border: 1px solid var(--control-border);`. Nothing else in these rules
changes:

| File | Rule |
|---|---|
| `frontend/src/app/ui/form-controls.ts` | `select {` (~line 52) |
| `frontend/src/app/ui/form-controls.ts` | `input {` (~line 110, the text input; not the checkbox's `input { accent-color … }` at ~204) |
| `frontend/src/app/ui/date-range.ts` | `input {` (~line 43) |
| `frontend/src/app/ui/segmented.ts` | `.track { … }` (line 20) |
| `frontend/src/app/ui/pagination.ts` | `.per-page select, .jump { … }` (line 45; the `button { … }` rule on line 51 keeps `--border-strong`) |
| `frontend/src/app/ui/data-table/data-table.ts` | `.phone-sort select { … }` (line 459) |

In `frontend/src/app/ui/form-controls.ts`, also update the comment above
`select {`. Replace `now, so the field sits one step down on the --bg well, behind the`
/ `strong hairline, and its edge brightens on hover. */` with
`now, so the field sits one step down on the --bg well, behind the` /
`control border (v240, 3:1 in Navy), and its edge brightens on hover. */`.

- [ ] **Step 8: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/control-border.spec.ts --include src/app/ui/form-controls.spec.ts --include src/app/ui/testing/style-rules.spec.ts --include src/app/ui/segmented.spec.ts --include src/app/ui/date-range.spec.ts --include src/app/ui/pagination.spec.ts --include src/app/ui/data-table/data-table.spec.ts`
Expected: PASS. If one of the last four specs pins `var(--border-strong)` on
a changed rule, update that pin to `var(--control-border)` in this task and
stage the spec with the commit.

Then confirm nothing else drifted:
`cd frontend && git grep -n "var(--control-border)" -- src ':!*.spec.ts'`
Expected: exactly the six rules above.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/ui/testing/style-rules.ts frontend/src/app/ui/testing/style-rules.spec.ts \
  frontend/src/app/ui/control-border.spec.ts frontend/src/app/ui/form-controls.ts \
  frontend/src/app/ui/form-controls.spec.ts frontend/src/app/ui/segmented.ts \
  frontend/src/app/ui/date-range.ts frontend/src/app/ui/pagination.ts \
  frontend/src/app/ui/data-table/data-table.ts
git commit -m "feat(v240): styleRules parser for style gates; inputs, selects and segmented controls outlined in --control-border

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

