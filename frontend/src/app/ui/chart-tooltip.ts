import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { CHART_CHROME } from './chart/chart-frame';

export interface TooltipRow { label: string; value: string; swatch?: string; }
export interface HoverState { x: number; y: number; title: string; rows: TooltipRow[]; }

/** Pointer or focus-target position relative to a chart host. */
export function hoverPosition(event: PointerEvent | FocusEvent, host: HTMLElement): { x: number; y: number } {
  const box = host.getBoundingClientRect();
  if ('clientX' in event) return { x: event.clientX - box.left, y: event.clientY - box.top };
  const target = (event.target as HTMLElement | null)?.getBoundingClientRect();
  return target ? { x: target.left - box.left + target.width / 2, y: target.top - box.top } : { x: 0, y: 0 };
}

/** One accessible, text-bound readout for every analytics chart (v94 D11). */
@Component({
  selector: 'sb-chart-tooltip', changeDetection: ChangeDetectionStrategy.OnPush,
  template: `@if (state(); as s) { <div class="tooltip" role="status" aria-live="polite"
    [style.left.px]="s.x" [style.top.px]="s.y" [class.flip]="flip()">
    <div class="title">{{ s.title }}</div>
    @for (row of s.rows; track row.label) { <div class="row">
      @if (row.swatch) { <span class="swatch" [style.background]="row.swatch"></span> }
      <span class="value num">{{ row.value }}</span><span class="label">{{ row.label }}</span>
    </div> }
  </div> }`,
  styles: `:host { display: contents; } .tooltip { position:absolute; z-index:3; pointer-events:none; transform:translate(12px,-50%); min-width:9rem; padding:var(--space-6) var(--space-8); background:var(${CHART_CHROME.tooltipSurface}); border:1px solid var(${CHART_CHROME.tooltipBorder}); border-radius:var(--radius); box-shadow:var(--shadow-overlay); font-size:var(--text-chip); } .tooltip.flip { transform:translate(calc(-100% - 12px),-50%); } .title { color:var(--text-muted); font-size:var(--text-micro); margin-bottom:2px; } .row { display:grid; grid-template-columns:auto auto 1fr; align-items:center; gap:var(--space-6); } .swatch { display:inline-block; width:12px; height:2px; border-radius:1px; } .value { color:var(--text); font-weight:600; font-variant-numeric:tabular-nums; } .label { color:var(--text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }`,
})
export class ChartTooltip {
  readonly state = input.required<HoverState | null>();
  readonly hostWidth = input<number | null>(null);
  protected readonly flip = computed(() => {
    const state = this.state(), width = this.hostWidth();
    return !!state && width !== null && state.x > width * .7;
  });
}
