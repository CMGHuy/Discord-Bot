import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { allSources, stripComments } from './testing/all-sources';
import { callSites } from './testing/call-sites';
import { resolveToken } from './testing/resolve-token';
import { resolveTokenIn } from './testing/theme-tokens';
import { THEME_PREF_KEY } from './theme.service';

/**
 * Raw buttons that stay raw, each with the reason.
 *
 * Four entries, all whole-surface hit areas, and it should stay that way. A
 * gate that starts life with a fistful of exceptions teaches everyone that
 * exceptions are normal.
 */
const RAW_BUTTON_ALLOWLIST = new Map<string, string>([
  // The whole toast IS the dismiss control -- a full-bleed surface with its
  // own kind-coloured background, not a button sitting inside a toast. Giving
  // it a variant would mean a variant used exactly once, which is a worse
  // answer than one justified exception.
  ['shell/toast-host.ts', 'class="toast elev-overlay"'],
  // The whole activity row IS the drawer trigger (v179 §6a.4) -- icon, arrow,
  // ticker, detail and time laid out inside one native button, so the row
  // gets keyboard activation and focus for free. sb-button's variants style a
  // labelled control, not a row of mixed content; a row variant would be used
  // exactly once.
  ['workspaces/dashboard/panels/recent-activity.ts', 'class="event-hit"'],
  // The More tab IS a tab-bar cell -- glyph over label, laid out exactly like
  // its sibling <a class="tab"> cells so the five read as one bar. A button
  // variant would style a labelled control, not a bar cell (v195 V195-18).
  ['shell/phone-tab-bar.ts', 'class="tab more"'],
  // The More sheet's search row IS a field-shaped trigger for the palette --
  // glyph and placeholder text across the sheet's full width. It opens the
  // palette rather than taking input, so it is not a text input (v195 V195-18).
  ['shell/more-sheet.ts', 'class="search"'],
  // v203 shell controls: each is a chip, an edge tab or a full-width strip with its own
  // geometry (dot + words, a rotated 40px tab, a state line), not a labelled button. They pad
  // to 44px with .sb-hit and carry their own accessible names.
  ['shell/alarm-chip.ts', 'class="alarm-chip sb-hit"'],
  ['shell/live/live-edge-tab.ts', 'class="edge-tab sb-hit"'],
  ['shell/live/live-strip.ts', 'class="live-strip sb-hit"'],
  // v227: the voice chip is a top-bar chip like the alarm chip -- speaker glyph
  // + state word, padded to 44px by .sb-hit, aria-label naming its action.
  ['shell/voice-chip.ts', 'class="voice-chip sb-hit"'],
]);

describe('no call site hand-rolls a button', () => {
  for (const { name, source } of callSites()) {
    it(`${name} routes every button through sb-button`, () => {
      const allowed = RAW_BUTTON_ALLOWLIST.get(name);
      const raw = [...source.matchAll(/<button\b[^>]*>/gs)]
        .map(([tag]) => tag.replace(/\s+/g, ' '))
        .filter((tag) => !tag.includes('sb-button'))
        .filter((tag) => !(allowed && tag.includes(allowed)));
      expect(raw).toEqual([]);
    });
  }
});

/**
 * Raw form controls that stay raw, each with the reason it cannot be wrapped.
 * Adding a name here is a claim about the control, so it needs a reason.
 */
const RAW_CONTROL_ALLOWLIST = new Map<string, string>([
  // A file input cannot be wrapped: the picker only opens from a real click
  // on the real element, and re-dispatching one loses the user-activation
  // that browsers require.
  ['workspaces/system/settings-tab.ts', 'type="file"'],
  // The command palette's field is an ARIA combobox (v195 §3.1): it carries
  // role="combobox", aria-activedescendant and aria-controls and owns the
  // arrow and Enter keys for the listbox under it. sb-text-input wraps a
  // plain field and exposes none of that; growing it a combobox mode for one
  // call site would be the worse trade.
  ['shell/palette/command-palette.ts', 'role="combobox"'],
  // v227: the voice rate slider. A range input has no primitive (this is the
  // app's only one), and a ui/ wrapper used exactly once is the worse trade;
  // its thumb takes the --hit-min square from voice-settings.ts.
  ['workspaces/system/voice-settings.ts', 'type="range"'],
]);

describe('no call site hand-rolls a form control', () => {
  for (const { name, source } of callSites()) {
    it(`${name} routes every input and select through a primitive`, () => {
      const allowed = RAW_CONTROL_ALLOWLIST.get(name);
      const raw = [...source.matchAll(/<(input|select)\b[^>]*>/gs)]
        .map(([tag]) => tag.replace(/\s+/g, ' '))
        .filter((tag) => !(allowed && tag.includes(allowed)));
      expect(raw).toEqual([]);
    });
  }
});

/**
 * Promoted classes a call site may still define, each with the reason
 * sb-section-head cannot cover it. Adding a name here is a claim about
 * the file, so it needs a reason.
 */
const PROMOTED_ALLOWLIST = new Map<string, string[]>([
  // Trade detail's <h1> is a ticker span plus a live sb-status-indicator --
  // rich content, not a string. sb-section-head's `heading` input is
  // `string` only (Task 5's given design); there is no slot to project a
  // component into in its place.
  ['workspaces/trades/trade-detail.ts', ['head']],
]);

describe('the valence law is not forked', () => {
  for (const { name, source } of callSites()) {
    it(`${name} does not redefine .pos, .neg or .muted`, () => {
      const offenders = ['pos', 'neg', 'muted'].filter((cls) =>
        new RegExp(`^\\s*\\.${cls}\\s*[,{]`, 'm').test(source),
      );
      expect(offenders).toEqual([]);
    });
  }
});

describe('no call site redefines a promoted composite', () => {
  const PROMOTED = ['head', 'row-link', 'note', 'chips'];
  for (const { name, source } of callSites()) {
    it(`${name} defines none of the promoted classes`, () => {
      const allowed = new Set(PROMOTED_ALLOWLIST.get(name) ?? []);
      const offenders = PROMOTED.filter((cls) =>
        !allowed.has(cls) && new RegExp(`^\\s*\\.${cls}\\s*[,{]`, 'm').test(source),
      );
      expect(offenders).toEqual([]);
    });
  }
});

/**
 * Colour literals outside the token files -- spec v167 §5, which extends
 * the gate this block used to be (hex only, over callSites() only).
 *
 * Scope: allSources() -- every .ts/.css/.html under src/, so ui/, every
 * stylesheet, styles.css and index.html, minus specs and styles/.
 * Pattern: a hex literal, or rgb()/rgba()/hsl()/hsla() in either the comma
 * or the space syntax. (?<!&) keeps an HTML numeric character reference
 * (a glyph entity such as &#9650;) from reading as a hex colour; since v241
 * none is left in the sources (icon-glyphs.spec.ts keeps the replaced
 * marker glyphs out), but the lookbehind costs nothing. Comments are
 * stripped first, so a hex quoted in prose (button.ts's contrast note)
 * stays legal.
 *
 * An entry here is a copy of a token that cannot read var(). The list of
 * literals a file may hold is exact and in source order, so a third copy
 * fails as surely as a new hue.
 */
const COLOUR_RE = /(?<!&)#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/g;

const HEX_ALLOWLIST = new Map<string, string[]>([
  // The four cold-load copies, in file order: the theme-color meta (Navy,
  // the default look since v240), NAVY_BG and GRAPHITE_BG in index.html's
  // pre-paint script, and the inline html/body ground (Navy). They paint
  // before any stylesheet has loaded, so they cannot read var(--bg); the
  // cold-load describes below fail the moment one drifts from palette.css.
  ['index.html', ['#00131f', '#00131f', '#0d0f12', '#00131f']],
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
 * rgb()/rgba() only inside the four tier-3 shadow and scrim tokens, black
 * or white at some alpha. A hued glow derives from a tier-2 token with
 * color-mix(), so a palette change reaches it. hsl() is in neither file.
 */
const TOKENS_HEX_ALLOWED = new Set([
  '--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5', '--chart-6', '--quality-4',
]);
/* v168 amendment 8 added the hover-lift shadow; v195 §1.2 deleted it. The
 * panel shadow is `none` under v195 and stays allowed, not required. */
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

  it('keeps rgb()/rgba() inside the tier-3 shadow and scrim tokens only', () => {
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

describe('every allowlist entry is justified', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/primitives.spec.ts'), 'utf8');

  // PROMOTED_ALLOWLIST is this file's own addition (v54 Task 5, the
  // trade-detail.ts rich-heading exception) -- the plan's own list here
  // named only the three it introduced, but the principle is general.
  for (const list of [
    'RAW_CONTROL_ALLOWLIST', 'RAW_BUTTON_ALLOWLIST', 'HEX_ALLOWLIST', 'PROMOTED_ALLOWLIST',
  ]) {
    it(`${list} has a comment above every entry`, () => {
      const body = SOURCE.slice(SOURCE.indexOf(`const ${list}`));
      const block = body.slice(0, body.indexOf(']);'));
      const entries = [...block.matchAll(/^\s*\[['"]/gm)];
      const comments = [...block.matchAll(/^\s*\/\//gm)];
      expect(comments.length).toBeGreaterThanOrEqual(entries.length);
    });
  }
});

/**
 * G3 -- a non-inset box-shadow appears in exactly two rules of styles.css,
 * .sb-panel (in flow, --panel-shadow) and .elev-overlay (out of flow,
 * --shadow-overlay), in that order. v168 §3 #5 added a hover lift and a
 * button glow in styles/motion.css; v195 §1.2 deleted both, so motion.css
 * casts none. No component casts one itself.
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

  it('motion.css casts no shadow: no lift, no glow (v195 §1.2)', () => {
    const motion = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '');
    expect(shadows(motion)).toEqual([]);
  });
});

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

/* v195 §1.2 retires v168 §3 #5: no panel or card lifts on hover, so no
 * surface carries the marker class and no source names it. */
describe('v195 §1.2: no surface carries .sb-lift', () => {
  const source = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
  const SURFACES = [
    'src/app/ui/layout.ts',
    'src/app/ui/figure.ts',
    'src/app/ui/chart-container.ts',
    'src/app/ui/stat-tile.ts',
    'src/app/ui/metric-card.ts',
  ];
  for (const path of SURFACES) {
    it(`${path} marks no lift`, () => expect(source(path)).not.toMatch(/\bsb-lift\b/));
  }

  it('no source anywhere names .sb-lift', () => {
    const offenders = allSources()
      .filter(({ source: text }) => /\bsb-lift\b/.test(stripComments(text)))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });
});
