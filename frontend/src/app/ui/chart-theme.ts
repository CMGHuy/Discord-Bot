import { DeepPartial } from 'lightweight-charts';
import type { ChartOptions } from 'lightweight-charts';

/**
 * The chart's colours, read from the design tokens at runtime.
 *
 * Spec v14 Decision 10 says the theme comes from the tokens and never from
 * hardcoded hex. lightweight-charts wants concrete colour strings — it paints
 * to a canvas and cannot resolve `var(--surface)` — so the values are read out
 * of the computed style of the document root instead of being copied into this
 * file. Copying them would create a fourth palette that silently stops
 * matching the moment the tokens change, which is the exact failure NG38 was
 * cleaning up.
 *
 * Read once per chart creation rather than cached at module load, so a chart
 * built after a token change gets the new values.
 */
function token(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  // The fallback is for jsdom, where computed custom properties come back
  // empty. A chart in a test does not need to be the right colour; it needs
  // not to throw.
  return value || fallback;
}

export interface ChartPalette {
  up: string;
  down: string;
  accent: string;
  warn: string;
  text: string;
  textMuted: string;
  border: string;
  surface: string;
}

/* The eight fallbacks below are the only hex literals outside `tokens.css`
 * that SR3's audit permits, and they are permitted on one condition: they must
 * equal the tokens they stand in for. They were the v20 palette until SR2
 * changed it, which is the failure mode worth naming — a stale fallback does
 * not throw and does not look broken; it silently paints the previous design
 * in whatever context the token read fails. If `tokens.css` changes one of
 * these eight values, change it here in the same commit. */
export function chartPalette(): ChartPalette {
  return {
    up: token('--pos', '#17c98e'),
    down: token('--neg', '#ff5470'),
    accent: token('--accent', '#7b5cfa'),
    warn: token('--warn', '#ffb43d'),
    text: token('--text', '#e9ebf5'),
    textMuted: token('--text-muted', '#6d7590'),
    border: token('--border', '#232838'),
    surface: token('--surface', '#10121a'),
  };
}

/** Chart options built from the palette. Grid lines are drawn in `--border`,
 *  the same hairline the tables use, so the chart recedes into the page
 *  rather than sitting on it as a separate visual system. */
export function chartOptions(palette: ChartPalette): DeepPartial<ChartOptions> {
  return {
    autoSize: true,
    layout: {
      background: { color: palette.surface },
      textColor: palette.textMuted,
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: palette.border },
      horzLines: { color: palette.border },
    },
    rightPriceScale: { borderColor: palette.border },
    timeScale: { borderColor: palette.border, timeVisible: false },
    crosshair: {
      vertLine: { color: palette.textMuted, labelBackgroundColor: palette.accent },
      horzLine: { color: palette.textMuted, labelBackgroundColor: palette.accent },
    },
  };
}
