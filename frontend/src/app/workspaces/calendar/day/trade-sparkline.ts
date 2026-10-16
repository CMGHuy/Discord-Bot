import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { SparkSeries } from '../../../api/models';
import { FINAL_STOP_LABEL } from './day-copy';

/* v165 D4/D5 -- one trade's daily closes on the day page: the recorded
 * entry, final stop and targets as ticks, the exit as a dot at the FILL
 * price, and the up-to-3 bars after the exit drawn dimmed (context, not
 * part of the trade). Not `ui/sparkline.ts`: that one is a bare 100x24
 * polyline with nowhere to put a level. */

export type TickKind = 'entry' | 'stop' | 'tp1' | 'tp2';

export interface SparkGeometry {
  /** Bars 0..exit_bar. */
  path: string;
  /** Bars exit_bar..end; '' when the exit bar is the last one. */
  dimmedPath: string;
  ticks: { kind: TickKind; y: number }[];
  exitDot: { x: number; y: number } | null;
}

interface Point {
  x: number;
  y: number;
}

const TICK_KINDS: readonly TickKind[] = ['entry', 'stop', 'tp1', 'tp2'];
const TICK_LABELS: Record<TickKind, string> = {
  entry: 'entry',
  stop: FINAL_STOP_LABEL,
  tp1: 'TP1',
  tp2: 'TP2',
};
/** Keeps the stroke and the dot off the box edge. */
const PAD = 2;
const NO_GEOMETRY: SparkGeometry = { path: '', dimmedPath: '', ticks: [], exitDot: null };

const round2 = (value: number): number => Math.round(value * 100) / 100;

/** One scale for closes and levels together, so every tick lands inside. */
function yScale(values: number[], height: number): (value: number) => number {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const usable = height - PAD * 2;
  return (value) => round2(span === 0 ? height / 2 : height - PAD - ((value - min) / span) * usable);
}

function linePath(points: Point[], width: number): string {
  if (points.length === 1) {
    const y = points[0].y.toFixed(2);
    return `M 0.00 ${y} L ${width.toFixed(2)} ${y}`;
  }
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(' ');
}

function levelsOf(series: SparkSeries): { kind: TickKind; value: number }[] {
  return TICK_KINDS.flatMap((kind) => {
    const value = series[kind];
    return value === null ? [] : [{ kind, value }];
  });
}

/** The exit bar's index, or null when the server's index is unusable. */
function exitIndex(series: SparkSeries, last: number): number | null {
  const bar = series.exit_bar;
  return Number.isInteger(bar) && bar >= 0 && bar <= last ? bar : null;
}

/** Pure, so the drawing is asserted without a DOM. */
export function sparkGeometry(series: SparkSeries, width = 120, height = 32): SparkGeometry {
  const closes = series.closes.map((bar) => bar.close);
  if (closes.length === 0) return NO_GEOMETRY;
  const levels = levelsOf(series);
  const exit = series.exit;
  const y = yScale([...closes, ...levels.map((l) => l.value), ...(exit === null ? [] : [exit])], height);
  const last = closes.length - 1;
  const points = closes.map((close, i) => ({
    x: last === 0 ? width / 2 : round2((i / last) * width),
    y: y(close),
  }));
  const exitBar = exitIndex(series, last);
  const cut = exitBar ?? last;
  return {
    path: linePath(points.slice(0, cut + 1), width),
    dimmedPath: cut < last ? linePath(points.slice(cut), width) : '',
    ticks: levels.map((l) => ({ kind: l.kind, y: y(l.value) })),
    exitDot: exitBar === null || exit === null || series.stale
      ? null
      : { x: points[exitBar].x, y: y(exit) },
  };
}

@Component({
  selector: 'sb-trade-sparkline',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    @if (geometry(); as g) {
      <a class="spark" [routerLink]="['/trades', tradeId()]" [queryParams]="chartTab"
         aria-label="Open this trade's chart">
        <svg [attr.viewBox]="viewBox" [attr.width]="width" [attr.height]="height" aria-hidden="true">
          @for (tick of g.ticks; track tick.kind) {
            <line class="tick" [attr.data-kind]="tick.kind" x1="0" [attr.x2]="width"
                  [attr.y1]="tick.y" [attr.y2]="tick.y"><title>{{ tickLabel(tick.kind) }}</title></line>
          }
          <path class="line" [attr.d]="g.path" />
          @if (g.dimmedPath) {
            <path class="line dimmed" [attr.d]="g.dimmedPath" />
          }
          @if (g.exitDot; as dot) {
            <circle class="exit" r="2.5" [attr.cx]="dot.x" [attr.cy]="dot.y"><title>exit</title></circle>
          }
        </svg>
      </a>
      @if (staleEnd(); as end) {
        <span class="stale-note">cache ends {{ end }}</span>
      }
    } @else {
      <span class="spark-empty" title="No cached daily bars for this row">—</span>
    }
  `,
  styles: `
    :host { display: inline-flex; align-items: center; gap: var(--space-6); max-width: 100%; }
    .spark { display: inline-flex; align-items: center; flex: none; min-height: 44px; line-height: 0; border-radius: 2px; }
    .spark:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    .line { fill: none; stroke: var(--text-secondary); stroke-width: 1.25; }
    .line.dimmed { opacity: 0.35; stroke-dasharray: 2 2; }
    .tick { stroke: var(--text-faint); stroke-width: 1; stroke-dasharray: 3 2; }
    .tick[data-kind='stop'] { stroke: var(--neg); }
    .tick[data-kind='tp1'], .tick[data-kind='tp2'] { stroke: var(--pos); }
    .exit { fill: var(--accent); }
    .stale-note { color: var(--text-faint); font-size: var(--text-chip); white-space: nowrap; }
    .spark-empty { color: var(--text-faint); font-family: var(--font-mono); }
  `,
})
export class TradeSparkline {
  readonly series = input<SparkSeries | null | undefined>();
  /** `plan_id ?? trade_id` -- the id the `/trades/:id` route takes. */
  readonly tradeId = input.required<string>();

  protected readonly width = 120;
  protected readonly height = 32;
  protected readonly viewBox = `0 0 ${this.width} ${this.height}`;
  protected readonly chartTab = { tab: 'chart' };

  protected readonly geometry = computed(() => {
    const series = this.series();
    return series ? sparkGeometry(series, this.width, this.height) : null;
  });

  protected readonly staleEnd = computed(() => {
    const series = this.series();
    return series?.stale ? series.last_bar : null;
  });

  protected tickLabel(kind: TickKind): string {
    return TICK_LABELS[kind];
  }
}
