import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { chartOptions, chartPalette, tokenPx } from './chart-theme';

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
    // v54 D5 (CHART_CHROME): axis and tooltipBorder are deliberately the same
    // token (--border-strong) under two names for two different roles --
    // asserted against tooltipSurface too so a future edit that merges them
    // back into one field would fail here, not silently in the chart.
    expect(palette.axis).toBe(tokenValue('--border-strong'));
    expect(palette.tooltipSurface).toBe(tokenValue('--surface-overlay'));
    expect(palette.tooltipBorder).toBe(tokenValue('--border-strong'));
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

  it('themes the axis border, one step up from the grid', () => {
    const palette = chartPalette();
    const options = chartOptions(palette);

    expect(options.rightPriceScale?.borderColor).toBe(palette.axis);
    expect(options.timeScale?.borderColor).toBe(palette.axis);
    // Not palette.border -- CHART_CHROME.grid, drawn by chartOptions.grid
    // below, is the one place this task's axis/grid split still uses it.
    expect(options.grid?.vertLines?.color).toBe(palette.border);
    expect(options.grid?.horzLines?.color).toBe(palette.border);
  });

  it('sizes scale text through tokenPx, not the old parseFloat(token(...)) bug', () => {
    // jsdom does not implement computed-value resolution for font-size on a
    // detached probe, so under test `var(--text-micro)` never resolves and
    // tokenPx() falls through to ITS OWN fallback argument regardless of
    // whether chartOptions() calls it correctly -- comparing
    // options.layout?.fontSize against a second, independent tokenPx() call
    // (or against the literal 11) would pass identically whether
    // chartOptions() calls tokenPx() or has reverted to the original bug.
    // Mocking what the probe's OWN getComputedStyle call resolves to is the
    // only way to tell those two cases apart under this test environment:
    // only the tokenPx() code path creates a probe element and reads it
    // back through getComputedStyle at all.
    const probeFontSize = '19px';
    const real = window.getComputedStyle.bind(window);
    vi.spyOn(window, 'getComputedStyle').mockImplementation((el, pseudo) => {
      if (el instanceof HTMLElement && el.style.fontSize.startsWith('var(')) {
        return { fontSize: probeFontSize } as CSSStyleDeclaration;
      }
      return real(el, pseudo);
    });

    const options = chartOptions(chartPalette());

    expect(options.layout?.fontSize).toBe(19);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });
});

describe('tokenPx', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reads back a real resolved font-size as a number', () => {
    vi.spyOn(window, 'getComputedStyle').mockReturnValue({
      fontSize: '23px',
    } as CSSStyleDeclaration);

    expect(tokenPx('--whatever', 11)).toBe(23);
  });

  it('falls back when the probe never resolves to a number', () => {
    // What jsdom itself actually returns for `font-size: var(--x)` on a
    // detached element -- the literal unresolved string, not a px value.
    vi.spyOn(window, 'getComputedStyle').mockReturnValue({
      fontSize: 'var(--whatever)',
    } as CSSStyleDeclaration);

    expect(tokenPx('--whatever', 11)).toBe(11);
  });
});
