import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { allSources } from './testing/all-sources';
import { resolveToken } from './testing/resolve-token';

/**
 * v179 §3.4: every interactive control has a 44x44px hit area on phone and
 * tablet. Asserted as source text: jsdom evaluates no media query and lays
 * nothing out (see tokens.spec.ts for why the stylesheet is read from disk).
 */
const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
const TOKENS = read('src/styles/tokens.css');
const GLOBAL = read('src/styles.css');
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
/** The first rule whose selector STARTS a line, so `.nav a` does not match
 *  `.shell.railed:not(.overlay) .nav a`. '' when absent. */
const rule = (source: string, selector: string) =>
  source.match(new RegExp(`^\\s*${esc(selector)}\\s*\\{[^}]*\\}`, 'm'))?.[0] ?? '';

describe('v179: --hit-min and the touch block', () => {
  it('defaults --hit-min to 24px (WCAG 2.2 minimum target)', () => {
    expect(TOKENS).toMatch(/^\s*--hit-min:\s*24px;/m);
    expect(resolveToken('--hit-min')).toBe('24px');
  });

  it('raises --hit-min to 44px on phone and tablet', () => {
    const block = TOKENS.match(/@media \(pointer: coarse\), \(max-width: 1023px\)\s*\{([\s\S]*?)\n\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toMatch(/--hit-min:\s*44px;/);
  });

  it('leaves no phone-only or bare coarse-pointer touch block anywhere', () => {
    const sources = [...allSources(), { name: 'styles/tokens.css', source: TOKENS }];
    const offenders = sources
      .filter(({ source }) => /@media \(pointer: coarse\), \(max-width: 639px\)/.test(source)
        || /@media \(pointer: coarse\)\s*\{/.test(source))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });
});

describe('v179: the .sb-hit utility', () => {
  it('makes the control the containing block', () => {
    expect(rule(GLOBAL, '.sb-hit')).toContain('position: relative');
  });

  it('centres a transparent box of at least --hit-min on the control', () => {
    const after = rule(GLOBAL, '.sb-hit::after');
    for (const declaration of [
      'content: ""', 'position: absolute', 'top: 50%', 'left: 50%',
      'width: max(100%, var(--hit-min))', 'height: max(100%, var(--hit-min))',
      'transform: translate(-50%, -50%)',
    ]) {
      expect(after).toContain(declaration);
    }
  });
});

describe('v179: controls that grow to the hit size', () => {
  const GROWN: [file: string, selector: string, declaration: string][] = [
    ['src/app/shell/shell.css', '.nav a', 'min-height: var(--control-h)'],
    ['src/app/ui/filter-bar.ts', '.chip', 'min-height: var(--control-h)'],
    ['src/app/ui/column-picker.ts', '.trigger', 'min-height: var(--control-h)'],
    ['src/app/ui/column-picker.ts', 'label', 'min-height: var(--hit-min)'],
    ['src/app/ui/column-picker.ts', '.reset', 'min-height: var(--hit-min)'],
    ['src/app/ui/segmented.ts', '.segment', 'min-width: var(--hit-min)'],
    ['src/app/ui/form-controls.ts', '.box', 'min-width: var(--hit-min)'],
  ];

  it.each(GROWN)('%s %s sets %s', (file, selector, declaration) => {
    expect(rule(read(file), selector)).toContain(declaration);
  });
});

describe('v179: controls that keep their look and take .sb-hit', () => {
  const PADDED: [file: string, markup: RegExp][] = [
    ['src/app/ui/row-link.ts', /<a class="row-link sb-hit"/],
    ['src/app/ui/panel-header.ts', /<button type="button" class="table sb-hit"/],
    ['src/app/workspaces/dashboard/positions-table.ts', /<a class="all-link sb-hit"/],
    ['src/app/workspaces/dashboard/panels/recent-activity.ts', /<a panel-actions class="all-link sb-hit"/],
  ];

  it.each(PADDED)('%s pads its control with .sb-hit', (file, markup) => {
    expect(read(file)).toMatch(markup);
  });
});
