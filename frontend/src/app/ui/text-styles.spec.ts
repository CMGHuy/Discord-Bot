import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

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
  it('.sb-label is 11px monospace capitals at 0.08em in muted text', () => {
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
