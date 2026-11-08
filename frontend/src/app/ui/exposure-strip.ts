import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { lineChartXScale } from './line-chart';

export interface ExposureBar {
  date: string;
  pct: number | null;
  approx: boolean;
}

export interface ExposureRect {
  date: string;
  pct: number;
  approx: boolean;
  x: number;
  width: number;
  height: number;
}

/** Uses the chart's dates so missing observations retain their time position. */
export function exposureBars(dates: readonly string[], bars: readonly ExposureBar[]): ExposureRect[] {
  if (dates.length === 0) return [];
  const scale = lineChartXScale(dates);
  const width = 600 / dates.length * 0.8;
  return bars.flatMap((bar) => {
    if (bar.pct === null || !dates.includes(bar.date)) return [];
    return [{
      date: bar.date, pct: bar.pct, approx: bar.approx, width,
      x: Math.min(Math.max(scale(bar.date) * 600 - width / 2, 0), 600 - width),
      height: Math.min(Math.max(bar.pct, 0), 100) / 100 * 40,
    }];
  });
}

@Component({
  selector: 'sb-exposure-strip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (dates().length) {
      <svg viewBox="0 0 600 40" preserveAspectRatio="none" role="img"
           aria-label="Exposure: share of equity in open trades per session">
        @for (r of rects(); track r.date) {
          <rect class="bar" [class.approx]="r.approx" [attr.x]="r.x" [attr.y]="40 - r.height"
                [attr.width]="r.width" [attr.height]="r.height">
            <title>{{ r.date }}: {{ r.pct.toFixed(1) }}%{{ r.approx ? ' (approx.)' : '' }}</title>
          </rect>
        }
      </svg>
    }
  `,
  styles: `
    :host { display: block; }
    svg { width: 100%; height: 40px; display: block; }
    rect.bar { fill: var(--text-faint); }
    rect.bar.approx { fill-opacity: 0.45; }
  `,
})
export class ExposureStrip {
  readonly dates = input.required<string[]>();
  readonly bars = input.required<ExposureBar[]>();
  protected readonly rects = computed(() => exposureBars(this.dates(), this.bars()));
}
