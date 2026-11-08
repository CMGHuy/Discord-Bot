import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { CHART_CHROME, token } from './chart/chart-frame';

export interface LineChartPoint {
  date: string;
  /** null = no observation, drawn as a gap. */
  value: number | null;
  day?: number | null;
  flag?: string;
}

export interface LineChartSeries {
  name: string;
  points: LineChartPoint[];
  color?: string;
  dashed?: boolean;
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
  const commands: string[] = [];
  let pen = false;
  for (const point of series.points) {
    if (point.value === null) {
      pen = false;
      continue;
    }
    const x = xScale(point.date).toFixed(4);
    const y = (1 - yScale(point.value)).toFixed(4); // SVG y grows downward
    commands.push(`${pen ? 'L' : 'M'} ${x} ${y}`);
    pen = true;
  }
  return commands.join(' ');
}

/**
 * Series colours, read from the token namespace rather than declared here.
 *
 * These were eight raw hexes — the only colours in the app outside
 * tokens.css, and unharmonised with the valence law: nothing stopped one of
 * them drifting into green, on a screen where green means gain.
 *
 * Read through `token()` (`chart-frame.ts`) because an SVG stroke needs a
 * resolved value, not a `var()`. `test-setup.ts` injects tokens.css into the
 * test document, so this resolves under vitest too.
 */
// Six, not eight (v80 D2). A seventh series wraps back to --chart-1 here;
// a chart that genuinely needs more should fold the tail into "Other"
// before it reaches this component.
const SERIES = Array.from({ length: 6 }, (_, i) => `--chart-${i + 1}`);

function seriesColour(index: number): string {
  return token(SERIES[index % SERIES.length]);
}

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
           (pointermove)="onPointerMove($event)" (pointerdown)="onPointerMove($event)" (pointerleave)="onPointerLeave($event)">
        @if (referenceLine(); as ref) {
          <line class="reference" [attr.x1]="0" [attr.x2]="600"
                [attr.y1]="refY(ref)" [attr.y2]="refY(ref)" />
        }
        @if (zeroLine()) {
          <line class="zero" [attr.x1]="0" [attr.x2]="600" [attr.y1]="refY(0)" [attr.y2]="refY(0)" />
        }
        @for (series of series(); track series.name; let i = $index) {
          <path class="series" [attr.d]="pathFor(series)"
                [attr.stroke]="colorOf(series, i)" [attr.stroke-dasharray]="series.dashed ? '6 4' : null" fill="none" />
        }
      </svg>
      @if (tooltipRows().length) {
        <div class="tooltip">
          <strong>{{ tooltipDate() }}</strong>
          @for (row of tooltipRows(); track row.name) {
            <div>{{ row.text }}</div>
          }
        </div>
      }
      @if (series().length > 1) {
        <div class="legend">
          @for (series of series(); track series.name; let i = $index) {
            <span class="entry">
              <i [class.dashed]="!!series.dashed"
                  [style.background]="series.dashed ? null : colorOf(series, i)"
                  [style.border-top-color]="colorOf(series, i)"></i>{{ series.name }}
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
    line.zero { stroke: var(--text-faint); stroke-width: 1; vector-effect: non-scaling-stroke; }
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
    .entry i.dashed { width: 14px; height: 0; border-radius: 0; border-top: 2px dashed; }
    .empty { color: var(--text-muted); font-size: var(--text-table); }
    .tooltip {
      position: absolute;
      padding: var(--space-6) var(--space-8);
      background: var(${CHART_CHROME.tooltipSurface});
      border: 1px solid var(${CHART_CHROME.tooltipBorder});
      border-radius: var(--control-radius);
      font-size: var(--text-chip);
      pointer-events: none;
    }
  `,
})
export class LineChart {
  readonly series = input.required<readonly LineChartSeries[]>();
  readonly yDomain = input<{ min: number; max: number } | null>(null);
  readonly referenceLine = input<number | null>(null);
  /** v208: opt-in 0 baseline, independent of the existing reference line. */
  readonly zeroLine = input(false);
  readonly valueFormat = input<(value: number) => string>((v) => v.toFixed(2));

  readonly hoverDetail = input(false);

  protected readonly hasData = computed(() =>
    this.series().some((s) => s.points.some((p) => p.value !== null)),
  );

  private readonly allDates = computed(() =>
    this.series().flatMap((s) => s.points.map((p) => p.date)),
  );
  private readonly allValues = computed(() =>
    this.series().flatMap((s) => s.points.flatMap((p) => p.value === null ? [] : [p.value])),
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

  protected colorOf(series: LineChartSeries, index: number): string {
    return series.color ? token(series.color) : seriesColour(index);
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

  protected onPointerLeave(event: PointerEvent): void {
    if (event.pointerType !== 'touch') this.hoverIndex.set(null);
  }

  protected readonly tooltipDate = computed(() => {
    const index = this.hoverIndex();
    return index === null ? null : this.nearestDates()[index];
  });

  protected readonly tooltipRows = computed(() => {
    const date = this.tooltipDate();
    if (date === null) return [];
    const detail = this.hoverDetail();
    return this.series().flatMap((series) => {
      const point = series.points.find((p) => p.date === date);
      if (!detail && (point === undefined || point.value === null)) return [];
      let text = `${series.name}: ${point?.value == null ? '—' : this.valueFormat()(point.value)}`;
      if (detail && typeof point?.day === 'number') text += ` (day ${this.valueFormat()(point.day)})`;
      if (detail && point?.flag) text += ` · ${point.flag}`;
      return [{ name: series.name, text }];
    });
  });
}
