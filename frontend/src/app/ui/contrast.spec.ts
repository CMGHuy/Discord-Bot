import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

function token(name: string): string {
  return CSS.match(new RegExp(`^\\s*${name}:\\s*(#[0-9a-fA-F]{6});`, 'm'))![1];
}

/** WCAG 2.1 relative luminance. */
function luminance(hex: string): number {
  const ch = (i: number) => {
    const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * ch(0) + 0.7152 * ch(1) + 0.0722 * ch(2);
}

function ratio(fg: string, bg: string): number {
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

const SURFACES = ['--bg', '--surface', '--surface-raised', '--surface-overlay'];

/**
 * Tokens that are NOT text and are exempt.
 *
 * `--text-faint` measures ~2.3:1 on --surface. It is a RULE AND DIVIDER
 * colour, never text that must be read — that is decision D6's binding rule,
 * and `no-text-uses-text-faint` below is what enforces it.
 */
const NON_TEXT = new Set(['--text-faint']);

describe('WCAG AA on every text/surface pair', () => {
  for (const fg of ['--text', '--text-secondary', '--text-muted']) {
    for (const bg of SURFACES) {
      it(`${fg} on ${bg} clears 4.5:1`, () => {
        expect(ratio(token(fg), token(bg))).toBeGreaterThanOrEqual(4.5);
      });
    }
  }

  for (const name of NON_TEXT) {
    it(`${name} is documented as non-text`, () => {
      expect(CSS).toMatch(new RegExp(`${name}[\\s\\S]{0,400}?rule and divider`, 'i'));
    });
  }
});

/**
 * v80 D1. The accent is two tokens: --accent is interactive TEXT and state
 * (links, active tab, sort arrow) and must read on every surface;
 * --accent-fill is what a filled button paints, carrying --on-accent.
 */
describe('accent legibility (v80 D1)', () => {
  for (const bg of SURFACES) {
    it(`--accent as text on ${bg} clears 4.5:1`, () => {
      expect(ratio(token('--accent'), token(bg))).toBeGreaterThanOrEqual(4.5);
    });
  }

  it('--on-accent on --accent-fill clears 4.5:1', () => {
    expect(ratio(token('--on-accent'), token('--accent-fill'))).toBeGreaterThanOrEqual(4.5);
  });
});
