import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { createChart, LineSeries } from 'lightweight-charts';
import type { ChartOptions, DeepPartial, IChartApi } from 'lightweight-charts';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { resolveToken } from '../testing/resolve-token';
import { resolveTokenIn } from '../testing/theme-tokens';
import { CHART_CHROME } from './chart-frame';
import {
  SVG_CHART_TOKENS, TICK_FALLBACK_PX, applyChartTheme, chartOptions, chartPalette, pctFormat, priceFormat,
  rFormat, themedToken, tokenPx,
} from './chart-theme';

// The real-chart tests below create a lightweight-charts instance; fancy-canvas needs matchMedia.
installMatchMediaPolyfill();

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
 * The expected values come from `resolveToken()` rather than being written
 * here, for the same reason the fallbacks were removed: a literal in this file
 * is one more copy of the palette to keep in step. Not the raw tokens.css text
 * either: since spec v167 tier 2 reads `--pos: var(--mint-400)`, and the
 * palette must equal the literal the resolver reaches (test-setup.ts injects
 * exactly those literals).
 */

describe('chartPalette', () => {
  it('resolves every colour from the token file', () => {
    const palette = chartPalette();

    expect(palette.up).toBe(resolveToken('--pos'));
    expect(palette.down).toBe(resolveToken('--neg'));
    expect(palette.accent).toBe(resolveToken('--accent'));
    expect(palette.warn).toBe(resolveToken('--warn'));
    expect(palette.text).toBe(resolveToken('--text'));
    expect(palette.textMuted).toBe(resolveToken('--text-muted'));
    expect(palette.border).toBe(resolveToken('--border'));
    expect(palette.surface).toBe(resolveToken('--surface'));
    expect(palette.volume).toBe(resolveToken('--text-faint'));
    expect(palette.separator).toBe(resolveToken('--border-strong'));
    expect(palette.separatorHover).toBe(resolveToken('--accent'));
    expect(palette.info).toBe(resolveToken('--info'));
    expect(palette.posSoft).toBe(resolveToken('--pos-soft'));
    expect(palette.negSoft).toBe(resolveToken('--neg-soft'));
    expect(palette.infoSoft).toBe(resolveToken('--info-soft'));
    // v54 D5 (CHART_CHROME): axis and tooltipBorder are deliberately the same
    // token (--border-strong) under two names for two different roles --
    // asserted against tooltipSurface too so a future edit that merges them
    // back into one field would fail here, not silently in the chart.
    expect(palette.axis).toBe(resolveToken('--border-strong'));
    expect(palette.tooltipSurface).toBe(resolveToken('--surface-overlay'));
    expect(palette.tooltipBorder).toBe(resolveToken('--border-strong'));
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

/* -- v195 Phase 6 -- the canvas chart on the Graphite tokens ----------------- */

describe('chart theme on the Graphite tokens (v195 Phase 6)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('draws the entry in the accent, a hue no chart series uses', () => {
    // The Discord image's ENTRY_COLOR reads THEME["accent"] since V195-1, so
    // the entry line is one colour in the app and in an alert. --chart-1 was
    // the old Discord entry colour; the two must not converge again.
    const palette = chartPalette();
    expect(palette.accent).toBe(resolveToken('--accent'));
    expect(palette.accent).not.toBe(resolveToken('--chart-1'));
    expect(new Set([palette.up, palette.down, palette.accent]).size).toBe(3);
  });

  it('keeps the chrome neutral: no valence or accent hue on grid, axis, ground, ticks or volume', () => {
    const palette = chartPalette();
    const hued = new Set([palette.up, palette.down, palette.accent, palette.warn, palette.info]);
    for (const [name, value] of Object.entries({
      border: palette.border, axis: palette.axis, surface: palette.surface,
      textMuted: palette.textMuted, volume: palette.volume, separator: palette.separator,
    })) {
      expect(hued.has(value), `palette.${name} is ${value}`).toBe(false);
    }
  });

  it('falls back to the 12px micro floor when the tick size cannot be resolved', () => {
    const palette = chartPalette();
    const real = window.getComputedStyle.bind(window);
    vi.spyOn(window, 'getComputedStyle').mockImplementation((el, pseudo) => {
      if (el instanceof HTMLElement && el.style.fontSize.startsWith('var(')) {
        return { fontSize: 'var(--text-micro)' } as CSSStyleDeclaration;
      }
      return real(el, pseudo);
    });

    expect(TICK_FALLBACK_PX).toBe(12);
    expect(chartOptions(palette).layout?.fontSize).toBe(TICK_FALLBACK_PX);
  });
});

/* -- v246 §A3 -- formats, applyChartTheme, SVG tokens, Navy fallback -------- */

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/chart/chart-theme.ts'), 'utf8');

/** Layers Navy values for `names` the way tokens.css does and switches the root to Navy; returns the undo. */
function navyFor(names: readonly string[]): () => void {
  const root = document.documentElement;
  const previous = root.getAttribute('data-theme');
  const style = document.createElement('style');
  style.textContent = `:root[data-theme="navy"]{${names.map((n) => `${n}:${resolveTokenIn('navy', n)}`).join(';')}}`;
  document.head.appendChild(style);
  root.setAttribute('data-theme', 'navy');
  return () => {
    style.remove();
    if (previous === null) root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', previous);
  };
}

function recordingChart(): { chart: IChartApi; applied: DeepPartial<ChartOptions>[] } {
  const applied: DeepPartial<ChartOptions>[] = [];
  const chart = { applyOptions: (options: DeepPartial<ChartOptions>) => applied.push(options) } as unknown as IChartApi;
  return { chart, applied };
}

describe('value formats (v246 §A3)', () => {
  it('prices group thousands and sign a loss with the true minus', () => {
    expect(priceFormat.type).toBe('custom');
    expect(priceFormat.minMove).toBe(0.01);
    expect(priceFormat.formatter(997800)).toBe('997,800.00');
    expect(priceFormat.formatter(-1234.5)).toBe('−1,234.50');
    expect(priceFormat.formatter(-1234.5)).not.toContain('-');
    expect(priceFormat.formatter(-0.001)).toBe('0.00');
  });

  it('signs an R and suffixes it', () => {
    expect(rFormat.formatter(1.5)).toBe('+1.50R');
    expect(rFormat.formatter(-1)).toBe('−1.00R');
    expect(rFormat.formatter(0)).toBe('0.00R');
  });

  it('signs a percentage', () => {
    expect(pctFormat.formatter(3)).toBe('+3.00%');
    expect(pctFormat.formatter(-2.5)).toBe('−2.50%');
  });

  it('is what a real series prints on its price scale', () => {
    const element = document.createElement('div');
    document.body.appendChild(element);
    const chart = createChart(element, { width: 300, height: 200 });
    try {
      const series = chart.addSeries(LineSeries, { priceFormat });
      expect(series.priceFormatter().format(997800)).toBe('997,800.00');
      series.applyOptions({ priceFormat: rFormat });
      expect(series.priceFormatter().format(-1)).toBe('−1.00R');
    } finally {
      chart.remove();
      element.remove();
    }
  });
});

describe('applyChartTheme (v246 §A3)', () => {
  it('applies the chart chrome with the axis text in --text-secondary', () => {
    const { chart, applied } = recordingChart();
    const palette = chartPalette();
    applyChartTheme(chart);

    expect(applied).toHaveLength(1);
    const options = applied[0];
    expect(options.layout?.background).toEqual({ color: palette.surface });
    expect(options.layout?.textColor).toBe(resolveToken('--text-secondary'));
    expect(options.grid?.vertLines?.color).toBe(palette.border);
    expect(options.grid?.horzLines?.color).toBe(palette.border);
    expect(options.rightPriceScale?.borderColor).toBe(palette.axis);
    expect(options.timeScale?.borderColor).toBe(palette.axis);
    expect(options.timeScale?.timeVisible).toBe(false);
    expect(options.crosshair?.vertLine?.color).toBe(resolveToken('--text-muted'));
    expect(options.crosshair?.horzLine?.color).toBe(resolveToken('--text-muted'));
  });

  it('never touches sizing: autoSize is not part of the theme', () => {
    const { chart, applied } = recordingChart();
    applyChartTheme(chart);
    expect(Object.hasOwn(applied[0], 'autoSize')).toBe(false);
    expect(chartOptions(chartPalette()).autoSize).toBe(true);
  });

  it('uses the palette it is given', () => {
    const { chart, applied } = recordingChart();
    applyChartTheme(chart, { ...chartPalette(), surface: 'given-surface' });
    expect(applied[0].layout?.background).toEqual({ color: 'given-surface' });
  });

  it('is accepted by a real chart and leaves it fixed-size', () => {
    const element = document.createElement('div');
    document.body.appendChild(element);
    const chart = createChart(element, { width: 300, height: 200 });
    try {
      applyChartTheme(chart);
      expect(chart.options().autoSize).toBe(false);
      expect(chart.options().layout.textColor).toBe(resolveToken('--text-secondary'));
    } finally {
      chart.remove();
      element.remove();
    }
  });

  it('follows a theme switch: the next call reads the Navy inks', () => {
    const graphite = { surface: resolveToken('--surface'), text: resolveToken('--text-secondary') };
    const undo = navyFor(['--surface', '--text-secondary']);
    try {
      const { chart, applied } = recordingChart();
      applyChartTheme(chart);
      expect(applied[0].layout?.background).toEqual({ color: resolveTokenIn('navy', '--surface') });
      expect(applied[0].layout?.textColor).toBe(resolveTokenIn('navy', '--text-secondary'));
      expect(resolveTokenIn('navy', '--surface')).not.toBe(graphite.surface);
      expect(resolveTokenIn('navy', '--text-secondary')).not.toBe(graphite.text);
    } finally {
      undo();
    }
  });
});

describe('SVG_CHART_TOKENS (v246 §A3)', () => {
  it('names real tokens, mapped from the spec (Handoff 3)', () => {
    expect(SVG_CHART_TOKENS.line).toBe('--accent');
    expect(SVG_CHART_TOKENS.pos).toBe('--pos');
    expect(SVG_CHART_TOKENS.neg).toBe('--neg');
    expect(SVG_CHART_TOKENS.grid).toBe(CHART_CHROME.grid);
    expect(SVG_CHART_TOKENS.axisText).toBe('--text-secondary');
    expect(SVG_CHART_TOKENS.crosshair).toBe('--text-muted');
    expect(SVG_CHART_TOKENS.barRadius).toBe('--radius-sm');
    expect(SVG_CHART_TOKENS.labelSize).toBe(CHART_CHROME.tickSize);
    for (const name of [SVG_CHART_TOKENS.line, SVG_CHART_TOKENS.pos, SVG_CHART_TOKENS.neg, SVG_CHART_TOKENS.grid,
      SVG_CHART_TOKENS.axisText, SVG_CHART_TOKENS.crosshair, SVG_CHART_TOKENS.barRadius, SVG_CHART_TOKENS.labelSize]) {
      expect(() => resolveToken(name), name).not.toThrow();
    }
  });

  it('carries the stroke widths and the bar gap the SVG charts draw today, in px', () => {
    expect(SVG_CHART_TOKENS.strokeWidth).toBe(2);
    expect(SVG_CHART_TOKENS.strokeWidthThin).toBe(1);
    expect(SVG_CHART_TOKENS.barGap).toBe(2);
  });
});

describe('themedToken: the Navy fallback (v246 edge states)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns a resolving token as is, without a warning', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(themedToken('--accent')).toBe(resolveToken('--accent'));
    expect(warn).not.toHaveBeenCalled();
  });

  it('falls back to the Navy value for a token the current theme lacks, and warns once', () => {
    const root = document.documentElement;
    const previous = root.getAttribute('data-theme');
    const navy = resolveTokenIn('navy', '--surface');
    const style = document.createElement('style');
    style.textContent = `:root[data-theme="navy"]{--v246-navy-only:${navy}}`;
    document.head.appendChild(style);
    root.setAttribute('data-theme', 'graphite');
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      expect(themedToken('--v246-navy-only')).toBe(navy);
      expect(themedToken('--v246-navy-only')).toBe(navy);
      expect(warn).toHaveBeenCalledTimes(1);
      expect(String(warn.mock.calls[0][0])).toContain('--v246-navy-only');
      expect(root.getAttribute('data-theme')).toBe('graphite');
    } finally {
      style.remove();
      if (previous === null) root.removeAttribute('data-theme');
      else root.setAttribute('data-theme', previous);
    }
  });

  it('returns empty for a token missing under Navy too, restores the root, and warns once', () => {
    const root = document.documentElement;
    const previous = root.getAttribute('data-theme');
    root.removeAttribute('data-theme');
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      expect(themedToken('--v246-nowhere')).toBe('');
      expect(themedToken('--v246-nowhere')).toBe('');
      expect(warn).toHaveBeenCalledTimes(1);
      expect(root.hasAttribute('data-theme')).toBe(false);
    } finally {
      if (previous !== null) root.setAttribute('data-theme', previous);
    }
  });

  it('reads every palette entry through it', () => {
    const body = SOURCE.slice(SOURCE.indexOf('export function chartPalette'), SOURCE.indexOf('export const TICK_FALLBACK_PX'));
    expect(body.match(/\btoken\(/g)).toBeNull();
    expect(body.match(/\bthemedToken\(/g)).toHaveLength(Object.keys(chartPalette()).length);
  });
});
