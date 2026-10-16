import { describe, expect, it } from 'vitest';

import {
  flattenedRootCss,
  parseRoot,
  readFixture,
  resolveAll,
  resolvedTokens,
  resolveToken,
  stripComments,
} from './testing/resolve-token';

/**
 * Spec v167 § 1: one token resolver per language, each held to the committed
 * fixture tests/charts/resolved_tokens.json. scripts/dev/dump_tokens.py writes
 * it and tests/charts/test_chart_theme.py holds the Python resolver to it, so a
 * drift in either resolver, or a palette.css / tokens.css edit without
 * regenerating, fails a test in both languages.
 */
describe('the TypeScript token resolver', () => {
  it('reproduces the committed fixture exactly', () => {
    expect(resolvedTokens()).toEqual(readFixture());
  });

  it('accepts a name with or without the leading dashes', () => {
    expect(resolveToken('--bg')).toBe(resolveToken('bg'));
    expect(resolveToken('--bg')).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it('names a token that does not exist', () => {
    expect(() => resolveToken('--no-such-token')).toThrow('--no-such-token is not a token');
  });

  it('never hands back a nested var()', () => {
    for (const [name, value] of Object.entries(resolvedTokens())) {
      expect(value, name).not.toContain('var(');
    }
  });
});

/** The same cases as tests/dev/test_dump_tokens.py, so the two ports agree on the rules. */
describe('parseRoot and resolveAll follow the dump_tokens.py rules', () => {
  it('strips block comments across lines', () => {
    expect(stripComments('a /* x\n { y } */ b')).toBe('a  b');
  });

  it('reads every :root block, later wins', () => {
    expect(parseRoot(':root { --a: #111; --b: 1px; }\n:root {\n  --a:   #222 ;\n}\n')).toEqual({
      a: '#222',
      b: '1px',
    });
  });

  it('drops @media and @supports blocks', () => {
    const css =
      ':root { --gap: 14px; }\n' +
      '@media (max-width: 639px) { :root { --gap: 10px; } }\n' +
      '@supports (color: color-mix(in srgb, red, blue)) { :root { --x: 1; } }\n';
    expect(parseRoot(css)).toEqual({ gap: '14px' });
  });

  it('ignores comments and non-root rules', () => {
    expect(parseRoot('/* :root { --ghost: 1; } */ body { --local: 2; } :root { --kept: 3; }')).toEqual({
      kept: '3',
    });
  });

  it('collapses whitespace in values', () => {
    expect(parseRoot(':root { --shadow: 0 8px 24px\n      rgba(0, 0, 0, .55); }')).toEqual({
      shadow: '0 8px 24px rgba(0, 0, 0, .55)',
    });
  });

  it('follows var() hops to a literal', () => {
    const declared = {
      navy: '#070b14',
      bg: 'var(--navy)',
      scrim: 'var(--bg)',
      gap: 'calc(2px * var(--scale))',
      scale: '1',
    };
    expect(resolveAll(declared)).toEqual({
      navy: '#070b14',
      bg: '#070b14',
      scrim: '#070b14',
      gap: 'calc(2px * 1)',
      scale: '1',
    });
  });

  it('names an undefined reference', () => {
    expect(() => resolveAll({ bg: 'var(--missing)' })).toThrow('--missing is not defined');
  });

  it('rejects a cycle', () => {
    expect(() => resolveAll({ a: 'var(--b)', b: 'var(--a)' })).toThrow('cycle at --a');
  });

  it('rejects fallback syntax', () => {
    expect(() => resolveAll({ a: '#fff', b: 'var(--a, #000)' })).toThrow('only plain var');
  });
});

describe('the jsdom test document (src/test-setup.ts)', () => {
  it('flattens to one :root block with sorted keys', () => {
    expect(flattenedRootCss({ b: '2px', a: '#fff' })).toBe(':root {\n  --a: #fff;\n  --b: 2px;\n}\n');
  });

  it('sees every token as its resolved literal', () => {
    const root = getComputedStyle(document.documentElement);
    for (const [name, value] of Object.entries(readFixture())) {
      expect(root.getPropertyValue(`--${name}`).trim(), name).toBe(value);
    }
  });
});
