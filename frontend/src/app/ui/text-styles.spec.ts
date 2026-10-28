import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { allSources, stripComments } from './testing/all-sources';

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
  it('.sb-label is 12px monospace capitals at 0.08em in muted text', () => {
    const r = rule('sb-label');
    expect(r).toContain('font-family: var(--font-mono)');
    expect(r).toContain('font-size: var(--text-micro)');
    expect(r).toContain('font-weight: 500');
    expect(r).toContain('letter-spacing: 0.08em');
    expect(r).toContain('text-transform: uppercase');
    expect(r).toContain('color: var(--text-muted)');
  });

  it('.sb-help is chip-sized secondary text capped at a readable measure, never past its container', () => {
    const r = rule('sb-help');
    expect(r).toContain('font-size: var(--text-chip)');
    expect(r).toContain('color: var(--text-secondary)');
    // min(65ch, 100%), not a bare 65ch -- a narrow panel is narrower than 65ch
    // in pixels, and a bare ch cap doesn't know that (v80 F26 browser walk).
    expect(r).toContain('max-width: min(65ch, 100%)');
  });
});

describe('v179: numbers in one face', () => {
  it('.num takes the numeric font token, tabular', () => {
    const r = rule('num');
    expect(r).toContain('font-family: var(--font-num)');
    expect(r).toContain('font-variant-numeric: tabular-nums');
  });
});

describe('v195: no literal text size below 12px', () => {
  /* Comments are stripped: chart/chart-width.ts explains the old 11px
   * floor in prose ("font-size: 11px is 11px at every width"), which is
   * documentation, not a declaration. */
  it('sets no px font-size under 12px anywhere in the app', () => {
    const offenders = allSources().flatMap(({ name, source }) =>
      [...stripComments(source).matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)]
        .filter((m) => Number(m[1]) < 12)
        .map((m) => `${name}: ${m[0]}`));
    expect(offenders).toEqual([]);
  });
});

describe('v195 Phase 2: the one quiet-meta style', () => {
  it('.sb-meta is muted micro text with tabular figures, never the faint rule colour', () => {
    const r = rule('sb-meta');
    expect(r).toContain('color: var(--text-muted)');
    expect(r).toContain('font-size: var(--text-micro)');
    expect(r).toContain('font-variant-numeric: tabular-nums');
    expect(r).not.toContain('--text-faint');
  });
});

describe('v195 Phase 2: one panel title, sentence case', () => {
  const read = (path: string) => stripComments(readFileSync(join(process.cwd(), path), 'utf8'));
  const titles = (source: string) => [...source.matchAll(/[\s`]h[12]\s*\{[^}]*\}/g)].map(([m]) => m);
  const TITLE = [
    'font-family: var(--font-sans);',
    'font-weight: 600;',
    'font-size: var(--text-table);',
    'color: var(--text);',
    'letter-spacing: normal;',
  ];

  it('sets sb-panel and sb-panel-header titles identically, at the 13px table step', () => {
    const panel = titles(read('src/app/ui/layout.ts'))[0];
    const header = titles(read('src/app/ui/panel-header.ts'))[0];
    for (const declaration of TITLE) {
      expect(panel, `layout.ts ${declaration}`).toContain(declaration);
      expect(header, `panel-header.ts ${declaration}`).toContain(declaration);
    }
  });

  it('uppercases no title in the panel, panel-header or section-head primitive', () => {
    for (const path of ['src/app/ui/layout.ts', 'src/app/ui/panel-header.ts', 'src/app/ui/section-head.ts']) {
      const found = titles(read(path));
      expect(found.length, path).toBeGreaterThan(0);
      for (const title of found) expect(title, path).not.toContain('text-transform');
    }
  });
});
