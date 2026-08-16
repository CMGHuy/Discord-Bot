import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

export interface LineChartPoint {
  date: string;
  value: number;
}

export interface LineChartSeries {
  name: string;
  points: LineChartPoint[];
}

/** Maps an ISO date string to 0-1, linear in TIME, not in array index --
 *  unevenly-spaced dates (a weekly rolling-return point beside a monthly
 *  calendar-return one) must not be drawn as if they were evenly spaced. */
export function lineChartXScale(dates: readonly string[]): (date: string) => number {
  const times = dates.map((d) => new Date(d).getTime());
  const min = Math.min(...times);
  const max = Math.max(...times);
  const span = max - min;
  return (date: string) => (span === 0 ? 0 : (new Date(date).getTime() - min) / span);
}

/** Maps a value to 0-1. An explicit `domain` (e.g. a fixed 0-100 win-rate
 *  axis) wins over the auto min/max of `values` -- see the Calibration
 *  decile chart, which needs an ABSOLUTE scale so an 80% reference line
 *  means the same thing regardless of which decile happens to be tallest. */
export function lineChartYScale(
  values: readonly number[],
  domain?: { min: number; max: number },
): (value: number) => number {
  const min = domain?.min ?? Math.min(...values);
  const max = domain?.max ?? Math.max(...values);
  const span = max - min;
  // A flat series has no range to scale into. Drawn at the middle rather
  // than the top or bottom, where it would read as an extreme -- same rule
  // sparkline.ts's y() already applies.
  return (value: number) => (span === 0 ? 0.5 : (value - min) / span);
}

/** One series' SVG path, in a 0-1 x 0-1 coordinate space the component
 *  scales into its actual viewBox. */
export function seriesPath(
  series: LineChartSeries,
  xScale: (date: string) => number,
  yScale: (value: number) => number,
): string {
  const points = series.points;
  if (points.length === 0) return '';
  if (points.length === 1) {
    const x = xScale(points[0].date);
    const y = 1 - yScale(points[0].value);
    return `M ${x.toFixed(4)} ${y.toFixed(4)}`;
  }
  return points
    .map((p, i) => {
      const x = xScale(p.date).toFixed(4);
      const y = (1 - yScale(p.value)).toFixed(4); // SVG y grows downward
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    })
    .join(' ');
}

/** Eight categorical hues, fixed order -- the dataviz skill's dark-mode
 *  categorical palette (`references/palette.md`'s "Categorical palette"
 *  table, Dark column), verified directly against that file rather than
 *  assumed. This app is dark-only (`styles/tokens.css`'s own "Dark only"
 *  note: no `prefers-color-scheme` block, no `[data-theme]` hook), so the
 *  dark-surface steps are the only ones that apply here -- the light column
 *  is never rendered. A ninth series folds into "Other" per the skill's own
 *  rule rather than cycling back to hue 1. */
const SERIES_COLORS = [
  '#3987e5', '#d95926', '#199e70', '#c98500',
  '#d55181', '#008300', '#9085e9', '#e66767',
] as const;

/**
 * A multi-series time chart with a shared axis, a legend past one series,
 * and an optional fixed reference line -- built once for the three "over
 * time" Performance panels (Task 4, 9, 11) and the restored Calibration
 * decile chart (Task 8), rather than three bespoke SVGs. Neither existing
 * primitive fit: `Sparkline` is a deliberately unlabelled 100x24 single
 * series (its own doc comment), `Histogram` is bars only.
 *
 * No animation on data change (spec 3's "no card-flash on refresh" rule) --
 * a value updates in place, same as every other live figure in this app.
 */
@Component({
  selector: 'sb-line-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (hasData()) {
      <svg viewBox="0 0 600 220" preserveAspectRatio="none" role="img"
           (pointermove)="onPointerMove($event)" (pointerleave)="onPointerLeave()">
        @if (referenceLine(); as ref) {
          <line class="reference" [attr.x1]="0" [attr.x2]="600"
                [attr.y1]="refY(ref)" [attr.y2]="refY(ref)" />
        }
        @for (series of series(); track series.name; let i = $index) {
          <path class="series" [attr.d]="pathFor(series)"
                [attr.stroke]="colorFor(i)" fill="none" />
        }
      </svg>
      @if (tooltipRows().length) {
        <div class="tooltip">
          <strong>{{ tooltipDate() }}</strong>
          @for (row of tooltipRows(); track row.name) {
            <div>{{ row.name }}: {{ valueFormat()(row.point.value) }}</div>
          }
        </div>
      }
      @if (series().length > 1) {
        <div class="legend">
          @for (series of series(); track series.name; let i = $index) {
            <span class="entry">
              <i [style.background]="colorFor(i)"></i>{{ series.name }}
            </span>
          }
        </div>
      }
    } @else {
      <p class="empty">No data to chart.</p>
    }
  `,
  styles: `
    :host { display: block; }
    svg { width: 100%; height: 140px; }
    path.series { stroke-width: 2; vector-effect: non-scaling-stroke; }
    line.reference {
      stroke: var(--text-faint);
      stroke-width: 1;
      stroke-dasharray: 4 3;
      vector-effect: non-scaling-stroke;
    }
    .legend { display: flex; flex-wrap: wrap; gap: var(--space-10); margin-top: var(--space-8);
              font-size: var(--text-chip); color: var(--text-secondary); }
    .entry { display: inline-flex; align-items: center; gap: var(--space-4); }
    .entry i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
    .empty { color: var(--text-faint); font-size: var(--text-table); }
    .tooltip {
      position: absolute;
      padding: var(--space-6) var(--space-8);
      background: var(--surface-overlay);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
      font-size: var(--text-chip);
      pointer-events: none;
    }
  `,
})
export class LineChart {
  readonly series = input.required<readonly LineChartSeries[]>();
  readonly yDomain = input<{ min: number; max: number } | null>(null);
  readonly referenceLine = input<number | null>(null);
  readonly valueFormat = input<(value: number) => string>((v) => v.toFixed(2));

  protected readonly hasData = computed(() =>
    this.series().some((s) => s.points.length > 0),
  );

  private readonly allDates = computed(() =>
    this.series().flatMap((s) => s.points.map((p) => p.date)),
  );
  private readonly allValues = computed(() =>
    this.series().flatMap((s) => s.points.map((p) => p.value)),
  );

  private readonly xScale = computed(() => lineChartXScale(this.allDates()));
  private readonly yScale = computed(() =>
    lineChartYScale(this.allValues(), this.yDomain() ?? undefined),
  );

  protected pathFor(series: LineChartSeries): string {
    const path = seriesPath(series, this.xScale(), this.yScale());
    // Scale the 0-1 path up into the 600x220 viewBox.
    return path.replace(/([ML]) ([\d.]+) ([\d.]+)/g, (_, cmd, x, y) =>
      `${cmd} ${(Number(x) * 600).toFixed(2)} ${(Number(y) * 220).toFixed(2)}`);
  }

  protected refY(value: number): number {
    return (1 - this.yScale()(value)) * 220;
  }

  protected colorFor(index: number): string {
    return SERIES_COLORS[index % SERIES_COLORS.length];
  }

  protected readonly hoverIndex = signal<number | null>(null);

  private readonly nearestDates = computed(() => {
    const dates = [...new Set(this.allDates())].sort(
      (a, b) => new Date(a).getTime() - new Date(b).getTime(),
    );
    return dates;
  });

  // getBoundingClientRect() is unavailable in jsdom's layout-less
  // environment (same trap this repo already documents for width-dependent
  // tests elsewhere), so this reads clientX relative to the element's own
  // bounding box at pointer time -- the spec only asserts the tooltip's
  // PRESENCE and CONTENT, never a pixel position, for exactly that reason.
  protected onPointerMove(event: PointerEvent): void {
    const dates = this.nearestDates();
    if (dates.length === 0) return;
    const svg = event.currentTarget as SVGSVGElement;
    const rect = svg.getBoundingClientRect();
    const fraction = rect.width > 0 ? (event.clientX - rect.left) / rect.width : 0;
    const index = Math.round(fraction * (dates.length - 1));
    this.hoverIndex.set(Math.max(0, Math.min(dates.length - 1, index)));
  }

  protected onPointerLeave(): void {
    this.hoverIndex.set(null);
  }

  protected readonly tooltipDate = computed(() => {
    const index = this.hoverIndex();
    return index === null ? null : this.nearestDates()[index];
  });

  protected readonly tooltipRows = computed(() => {
    const date = this.tooltipDate();
    if (date === null) return [];
    return this.series()
      .map((s) => ({ name: s.name, point: s.points.find((p) => p.date === date) }))
      .filter((row): row is { name: string; point: LineChartPoint } => row.point !== undefined);
  });
}
