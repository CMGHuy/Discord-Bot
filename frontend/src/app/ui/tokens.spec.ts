import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * The token file is asserted as TEXT, not through a mounted component.
 *
 * The tokens have to exist whether or not anything consumes them yet — SR2
 * lands the palette before the components that read it — and jsdom does not
 * resolve `var()` chains anyway, so a computed-style assertion here would pass
 * on a stylesheet that defines nothing.
 *
 * **Not `import … from '…tokens.css?raw'`.** That was tried first, to avoid a
 * dependency: Vite honours `?raw`, but the Angular compiler claims every
 * `.css` import ahead of it and hands back a processed style object, so the
 * assertions received an object and failed with a type error rather than a
 * useful message. `@types/node` is types-only and vitest already runs in Node,
 * so reading the file directly is both cheaper and more honest.
 *
 * Resolved from `process.cwd()`, not from `import.meta.url`. Under
 * `@angular/build:unit-test` the module's own URL is an `http:` one — the
 * builder serves the bundle rather than loading it off disk — and `readFileSync`
 * rejects it with "The URL must be of scheme file". `ng test` always runs with
 * the frontend project root as its working directory.
 */
const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

const REQUIRED = [
  '--bg',
  '--surface',
  '--surface-raised',
  '--surface-overlay',
  '--border',
  '--border-strong',

  '--text',
  '--text-secondary',
  '--text-muted',
  '--text-faint',

  '--pos',
  '--neg',
  '--warn',
  '--accent',
  '--info',

  '--pos-soft',
  '--neg-soft',
  '--warn-soft',
  '--accent-soft',
  '--info-soft',

  '--quality-1',
  '--quality-2',
  '--quality-3',
  '--quality-4',
  '--quality-5',

  '--dur-instant',
  '--dur-base',
  '--dur-slow',
  '--ease-out',
  '--ease-spring',

  '--control-h',
];

describe('design tokens', () => {
  for (const name of REQUIRED) {
    it(`defines ${name}`, () => {
      expect(CSS).toMatch(new RegExp(`^\\s*${name}:`, 'm'));
    });
  }

  it('sizes controls with a single height token', () => {
    expect(CSS).toMatch(/^\s*--control-h:\s*28px;/m);
  });

  it('honours prefers-reduced-motion', () => {
    expect(CSS).toContain('prefers-reduced-motion: reduce');
  });

  it('has dropped --space-28', () => {
    expect(CSS).not.toMatch(/^\s*--space-28:/m);
  });

  it('has dropped the old greyscale quality tokens', () => {
    for (const dead of ['--quality-high', '--quality-mid', '--quality-low']) {
      expect(CSS).not.toMatch(new RegExp(`^\\s*${dead}:`, 'm'));
    }
  });

  it('keeps --transition as an alias so existing call sites still compile', () => {
    expect(CSS).toMatch(/^\s*--transition:/m);
  });
});
