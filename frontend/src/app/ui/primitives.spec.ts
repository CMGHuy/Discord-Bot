import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { allSources, stripComments } from './testing/all-sources';
import { callSites } from './testing/call-sites';
import { resolveToken } from './testing/resolve-token';

/**
 * Raw buttons that stay raw, each with the reason.
 *
 * One entry, and it should stay that way. A gate that starts life with a
 * fistful of exceptions teaches everyone that exceptions are normal.
 */
const RAW_BUTTON_ALLOWLIST = new Map<string, string>([
  // The whole toast IS the dismiss control -- a full-bleed surface with its
  // own kind-coloured background, not a button sitting inside a toast. Giving
  // it a variant would mean a variant used exactly once, which is a worse
  // answer than one justified exception.
  ['shell/toast-host.ts', 'class="toast elev-overlay"'],
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
