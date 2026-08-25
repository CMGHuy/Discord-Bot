/**
 * The chart chrome every chart shares: axis, grid, ticks, tooltip.
 *
 * The four chart components had each chosen their own axis colour and tick
 * size, so two charts side by side on Analytics did not look like one system.
 * Chrome is not data — it recedes, which is why every value here is a
 * greyscale token and none is a hue.
 */
export const CHART_CHROME = {
  axis: 'var(--border-strong)',
  grid: 'var(--border)',
  tickSize: 'var(--text-micro)',
  tickColour: 'var(--text-muted)',
  tooltipSurface: 'var(--surface-overlay)',
  tooltipBorder: 'var(--border-strong)',
} as const;
