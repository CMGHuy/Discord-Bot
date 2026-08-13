import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { chartOptions, chartPalette } from './chart-theme';

/**
 * These tests exist to prove the fallbacks are not needed.
 *
 * `chart-theme.ts` used to carry eight hex literals as the second argument to
 * its token read, because under jsdom nothing had loaded a stylesheet and every
 * custom property came back empty. They went stale immediately (SR3's audit
 * found them holding the superseded v20 palette) and painting a stale palette
 * is a silent failure. `src/test-setup.ts` now injects the real token file into
 * the test document, so the read resolves — and if that ever stops working,
 * these assertions fail loudly instead of the fallback quietly covering it up.
 *
 * The expected values are parsed out of `tokens.css` rather than written here,
 * for the same reason the fallbacks were removed: a literal in this file is one
 * more copy of the palette to keep in step.
 */
const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

function tokenValue(name: string): string {
  const match = new RegExp(`^\\s*${name}:\\s*([^;]+);`, 'm').exec(CSS);
  if (!match) throw new Error(`tokens.css does not define ${name}`);
  return match[1].trim();
}

describe('chartPalette', () => {
  it('resolves every colour from the token file', () => {
    const palette = chartPalette();

    expect(palette.up).toBe(tokenValue('--pos'));
    expect(palette.down).toBe(tokenValue('--neg'));
    expect(palette.accent).toBe(tokenValue('--accent'));
    expect(palette.warn).toBe(tokenValue('--warn'));
    expect(palette.text).toBe(tokenValue('--text'));
    expect(palette.textMuted).toBe(tokenValue('--text-muted'));
    expect(palette.border).toBe(tokenValue('--border'));
    expect(palette.surface).toBe(tokenValue('--surface'));
    expect(palette.volume).toBe(tokenValue('--text-faint'));
    expect(palette.separator).toBe(tokenValue('--border-strong'));
    expect(palette.separatorHover).toBe(tokenValue('--accent'));
    expect(palette.info).toBe(tokenValue('--info'));
    expect(palette.posSoft).toBe(tokenValue('--pos-soft'));
    expect(palette.negSoft).toBe(tokenValue('--neg-soft'));
    expect(palette.infoSoft).toBe(tokenValue('--info-soft'));
  });

  it('leaves no entry empty', () => {
    // The one thing a missing token produces is an empty string, which
    // lightweight-charts accepts and draws as nothing -- an invisible series
    // rather than an error. Catch it here instead.
    for (const [name, value] of Object.entries(chartPalette())) {
      expect(value, `palette.${name} is empty`).not.toBe('');
    }
  });
});

describe('chartOptions', () => {
  it('themes the pane separators, which the library otherwise draws in its own grey', () => {
    const palette = chartPalette();
    const options = chartOptions(palette);

    expect(options.layout?.panes?.separatorColor).toBe(palette.separator);
    expect(options.layout?.panes?.separatorHoverColor).toBe(palette.separatorHover);
  });
});
