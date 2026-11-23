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
