import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

const VIEW_WIDTH = 100;
const VIEW_HEIGHT = 24;
/** Keeps the stroke from being clipped at the extremes. */
const PADDING = 1.5;

/** Builds the polyline for a series, in the 100×24 view box.
 *
 *  Exported so it can be tested without a DOM: the path is the only thing
 *  here worth asserting, and reading it back out of rendered SVG would be
 *  testing the browser rather than this code. */
export function sparklinePath(points: readonly number[]): string {
  if (points.length === 0) return '';

  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min;
  const usable = VIEW_HEIGHT - PADDING * 2;

  // A flat series has no range to scale into. Drawn down the middle rather
  // than at the top or bottom, where it would read as an extreme.
  const y = (value: number) =>
    span === 0 ? VIEW_HEIGHT / 2 : VIEW_HEIGHT - PADDING - ((value - min) / span) * usable;

  // A single point has no line to draw, so it becomes a short flat one --
  // otherwise one data point renders as nothing at all, which is
  // indistinguishable from having no data.
  if (points.length === 1) {
    return `M 0 ${y(points[0]).toFixed(2)} L ${VIEW_WIDTH} ${y(points[0]).toFixed(2)}`;
  }

  const step = VIEW_WIDTH / (points.length - 1);
  return points
    .map((value, index) => {
      const command = index === 0 ? 'M' : 'L';
      return `${command} ${(index * step).toFixed(2)} ${y(value).toFixed(2)}`;
    })
    .join(' ');
}

/**
 * A tiny trend line — equity over 30 days, a strategy's rolling win rate.
 *
 * No axes, no grid, no labels and no tooltip: at this size they are noise, and
 * the number they would annotate is always sitting next to the sparkline
 * already. It shows shape and direction, and anything more precise belongs on
 * a real chart.
 *
 * Coloured by net direction, first point to last, which is P&L direction and
 * therefore allowed green or red. Intermediate dips do not recolour it — the
 * question a sparkline answers is "up or down over this window".
 */
@Component({
  selector: 'sb-sparkline',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (path(); as d) {
      <svg
        [attr.viewBox]="viewBox"
        preserveAspectRatio="none"
        role="img"
        [attr.aria-label]="ariaLabel()"
      >
        <path [attr.d]="d" [class]="toneClass()" />
      </svg>
    }
  `,
  styles: `
    :host { display: inline-block; width: 100%; height: 24px; }
    svg { display: block; width: 100%; height: 100%; overflow: visible; }
    path {
      fill: none;
      stroke: var(--text-muted);
      stroke-width: 1.25;
      stroke-linejoin: round;
      stroke-linecap: round;
      /* The line is scaled non-uniformly by preserveAspectRatio, which would
         otherwise stretch the stroke with it. */
      vector-effect: non-scaling-stroke;
    }
    .pos { stroke: var(--pos); }
    .neg { stroke: var(--neg); }
  `,
})
export class Sparkline {
  readonly points = input.required<readonly number[]>();
  /** Named for assistive technology — "Equity, last 30 days". */
  readonly label = input('Trend');

  protected readonly viewBox = `0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`;

  protected readonly path = computed(() => sparklinePath(this.points()));

  protected readonly toneClass = computed(() => {
    const points = this.points();
    if (points.length < 2) return '';
    const change = points[points.length - 1] - points[0];
    if (change > 0) return 'pos';
    if (change < 0) return 'neg';
    return '';
  });

  protected readonly ariaLabel = computed(() => {
    const points = this.points();
    if (points.length < 2) return this.label();
    const change = points[points.length - 1] - points[0];
    const direction = change > 0 ? 'up' : change < 0 ? 'down' : 'flat';
    return `${this.label()}: ${direction} over ${points.length} points`;
  });
}
