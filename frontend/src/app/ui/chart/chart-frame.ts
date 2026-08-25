/**
 * The chart chrome every chart shares: axis, grid, ticks, tooltip.
 *
 * The four chart components had each chosen their own axis colour and tick
 * size, so two charts side by side on Analytics did not look like one system.
 * Chrome is not data — it recedes, which is why every value here is a
 * greyscale token and none is a hue.
 *
 * Bare custom-property NAMES, not `var()` expressions — a first review of
 * this wave found `axis`/`grid` unused: the CSS-styled charts (line, sparkline,
 * histogram) can embed a `var()` expression straight into a stylesheet, but
 * the canvas-drawn trade chart cannot (`lightweight-charts` needs a resolved
 * colour string, not a CSS variable reference — see `token()` below) and so
 * it read the same underlying tokens back out through its own `token()`
 * calls, independently of this object. Two names for one value is exactly
 * the drift risk this file exists to prevent: change `axis`/`grid`/
 * `tooltipSurface`/`tooltipBorder` here and the canvas chart would not move.
 * A bare name lets every consumer resolve it through its own mechanism
 * (`var(${CHART_CHROME.x})` in a stylesheet, `token(CHART_CHROME.x)` on a
 * canvas) while still reading the same object.
 *
 * `tickColour` is the one key still resolved twice rather than fixed by
 * this refactor: the canvas chart's scale-label colour is
 * `chart-theme.ts`'s `palette.textMuted` (`token('--text-muted')`), not
 * `token(CHART_CHROME.tickColour)` -- because `textMuted` is a
 * multi-purpose field there (also the crosshair and legend text), not a
 * single-purpose tick colour, so routing it through this constant would
 * couple those other uses to a name meant for axis ticks. It is the same
 * underlying token today (`--text-muted`), so nothing currently drifts, but
 * changing `tickColour` here would not move the canvas chart's scale
 * labels the way it would move `histogram.ts`'s. */
export const CHART_CHROME = {
  axis: '--border-strong',
  grid: '--border',
  tickSize: '--text-micro',
  tickColour: '--text-muted',
  tooltipSurface: '--surface-overlay',
  tooltipBorder: '--border-strong',
} as const;

/**
 * Resolves a custom property to its live value, read off the document root.
 *
 * Lives here, not in `chart-theme.ts`, because the two CSS-styled charts
 * (`line-chart.ts`, `histogram.ts`) need it too, and this file has no
 * runtime imports of its own — `chart-theme.ts` pulls in `lightweight-charts`
 * for its option types, which those two charts have no other reason to bundle.
 * `chart-theme.ts` re-exports both functions so its own existing importers
 * are unaffected.
 */
export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * Resolves a custom property to an actual pixel number -- `token()` alone
 * cannot do this for `--text-*`/`--space-*`: they are `calc(Npx *
 * var(--text-scale))` expressions (`tokens.css`'s Text-size control), and
 * `getComputedStyle().getPropertyValue()` on a *custom* property returns its
 * raw, unparsed value rather than a resolved one -- `calc()` is never
 * evaluated. `parseFloat` on that raw string is `NaN`, silently. Probed via
 * a detached element's resolved `font-size` instead, which the engine does
 * fully resolve, `--text-scale` included.
 */
export function tokenPx(name: string, fallback: number): number {
  const probe = document.createElement('div');
  probe.style.position = 'absolute';
  probe.style.visibility = 'hidden';
  probe.style.fontSize = `var(${name})`;
  document.body.appendChild(probe);
  const resolved = parseFloat(getComputedStyle(probe).fontSize);
  document.body.removeChild(probe);
  return Number.isFinite(resolved) ? resolved : fallback;
}
