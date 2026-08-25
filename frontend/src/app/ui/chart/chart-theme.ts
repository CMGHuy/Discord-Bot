import { CrosshairMode, DeepPartial } from 'lightweight-charts';
import type { ChartOptions } from 'lightweight-charts';

import { CHART_CHROME, token, tokenPx } from './chart-frame';

// Re-exported so this file's existing importers (legend-primitive.ts,
// chart-theme.spec.ts, and any test fixture that does
// `import { token } from './chart-theme'`) are unaffected by token()/
// tokenPx() now living in chart-frame.ts -- moved there because that file
// has no runtime imports of its own, unlike this one (lightweight-charts,
// for the option types below), and the two CSS-styled charts need these
// functions too without bundling a canvas library they never draw to.
export { token, tokenPx };

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
 * **One theme module for every chart in the app**, which is why it lives in
 * `ui/chart/` next to the components that read it rather than beside the first
 * component that happened to need it (SR35 moved it). A second theme file is a
 * second palette, however carefully it starts out matching.
 *
 * Read once per chart creation rather than cached at module load, so a chart
 * built after a token change gets the new values.
 */

/* There are no hex fallbacks here any more, and that is the point.
 *
 * There used to be eight — SR3's audit classified them as the one permitted
 * exemption to "no hex outside `tokens.css`" — and they existed only for
 * jsdom, where nothing had ever loaded the stylesheet so every custom property
 * read back empty. They were already stale when the audit found them: they
 * still held the v20 palette that SR2 had replaced. A stale fallback does not
 * throw and does not look broken; it silently paints the previous design
 * wherever the token read fails.
 *
 * `src/test-setup.ts` now injects the real `tokens.css` into the test document
 * (read off disk, so the values are the file's own — see that file for why
 * `?raw` does not work here), and jsdom resolves custom properties from an
 * injected `<style>`. So the fallback's only caller
 * is gone, and the values cannot go stale because there is no second copy of
 * them anywhere.
 *
 * An empty read is still tolerated rather than thrown on: a chart mounted
 * before the stylesheet lands should be the wrong colour for a frame, not a
 * crash that takes the workspace with it. lightweight-charts ignores an empty
 * colour string. */

export interface ChartPalette {
  up: string;
  down: string;
  accent: string;
  warn: string;
  text: string;
  textMuted: string;
  border: string;
  surface: string;
  /** Volume bars. Greyscale on purpose: under the tokens' valence rule a hue
   *  means a MEANING, and volume has no valence — a big red bar would read as
   *  a loss. It also has to sit behind the candles without competing with
   *  them, which is the other half of the same choice. */
  volume: string;
  /** The draggable rule between panes. `--border-strong`, not `--border`: it
   *  separates two coordinate systems rather than two rows, and it is a
   *  control the user can grab. */
  separator: string;
  /** Hover state of that rule — `--accent`, the interactive token, so it
   *  announces itself as draggable rather than merely brightening. */
  separatorHover: string;
  /** The neutral hue, for overlays that carry no valence — the Keltner
   *  envelope is neither good nor bad news, it is a measure of calm. */
  info: string;
  /** 12% tints, for the risk and reward bands SR36 fills between the plan
   *  lines, and for SR38's envelope lines. Soft enough to sit under candles
   *  without hiding a wick. */
  posSoft: string;
  negSoft: string;
  infoSoft: string;
  /** v54 D5: the right price scale's and time scale's own border —
   *  `chart-frame.ts`'s `CHART_CHROME.axis`. `--border-strong`, not
   *  `--border`: an axis is a boundary a reader orients against, not a
   *  hairline between rows the way the grid is. lightweight-charts paints to
   *  a canvas, so this reads `CHART_CHROME.axis`'s bare custom-property name
   *  through `token()` for a resolved colour, rather than the `var()`-wrapped
   *  form the three CSS-styled charts embed straight into a stylesheet. */
  axis: string;
  /** The on-canvas legend's box background — `CHART_CHROME.tooltipSurface` —
   *  so `LegendPrimitive`'s corner box (this chart's nearest equivalent to
   *  the other three charts' `.tooltip`) reads as the same surface. */
  tooltipSurface: string;
  /** The legend box's border — `CHART_CHROME.tooltipBorder`. Same token as
   *  `axis` (both `--border-strong`); named separately because the two serve
   *  different roles, matching `CHART_CHROME`'s own two separate keys. */
  tooltipBorder: string;
}

export function chartPalette(): ChartPalette {
  return {
    up: token('--pos'),
    down: token('--neg'),
    accent: token('--accent'),
    warn: token('--warn'),
    text: token('--text'),
    textMuted: token('--text-muted'),
    // CHART_CHROME.grid -- this palette's only consumer is chartOptions()'s
    // grid.vertLines/horzLines below, so it reads the shared constant like
    // axis/tooltipSurface/tooltipBorder do, not a second literal of --border.
    border: token(CHART_CHROME.grid),
    surface: token('--surface'),
    volume: token('--text-faint'),
    separator: token('--border-strong'),
    separatorHover: token('--accent'),
    info: token('--info'),
    posSoft: token('--pos-soft'),
    negSoft: token('--neg-soft'),
    infoSoft: token('--info-soft'),
    axis: token(CHART_CHROME.axis),
    tooltipSurface: token(CHART_CHROME.tooltipSurface),
    tooltipBorder: token(CHART_CHROME.tooltipBorder),
  };
}

/** Chart chrome shared with the other three charts (v54 D5,
 *  `chart-frame.ts`'s `CHART_CHROME`): grid lines in `CHART_CHROME.grid`, the
 *  same hairline the tables use, so the chart recedes into the page rather
 *  than sitting on it as a separate visual system; the axis border one step
 *  up, at `CHART_CHROME.axis`; scale-label text sized from
 *  `CHART_CHROME.tickSize`, the same size every chart's axis/tick text now
 *  shares. `CHART_CHROME` holds bare custom-property NAMES so both this
 *  canvas chart (via `token()`/`tokenPx()`, a resolved colour/number) and the
 *  CSS-styled charts (via `var()` in a stylesheet) read the very same
 *  constant rather than two copies of it. Read inside the function, not
 *  cached at module load, for the same reason `chartPalette()` is: a chart
 *  built after a token change must get the new value. */
export function chartOptions(palette: ChartPalette): DeepPartial<ChartOptions> {
  return {
    autoSize: true,
    layout: {
      background: { color: palette.surface },
      textColor: palette.textMuted,
      fontSize: tokenPx(CHART_CHROME.tickSize, 11),
      attributionLogo: false,
      // v5 draws the pane separators itself; left at the library's defaults
      // they are a mid-grey from its own theme, which is the one part of the
      // chart that would visibly not belong to this palette.
      panes: {
        enableResize: true,
        separatorColor: palette.separator,
        separatorHoverColor: palette.separatorHover,
      },
    },
    grid: {
      vertLines: { color: palette.border },
      horzLines: { color: palette.border },
    },
    rightPriceScale: { borderColor: palette.axis },
    timeScale: { borderColor: palette.axis, timeVisible: false },
    crosshair: {
      mode: CrosshairMode.Magnet,
      vertLine: { color: palette.textMuted, labelBackgroundColor: palette.accent },
      horzLine: { color: palette.textMuted, labelBackgroundColor: palette.accent },
    },
  };
}
