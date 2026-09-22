import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { ChartTooltip, HoverState, hoverPosition } from './chart-tooltip';

export interface ShareSegment { label: string; count: number; tone?: 'pos' | 'neg' | 'warn' | 'muted' | 'accent'; }

/** Accessible part-to-whole bar: direct values and legend make colour non-essential. */
@Component({ selector: 'sb-share-bar', changeDetection: ChangeDetectionStrategy.OnPush, imports: [ChartTooltip], template: `
  <div class="host" #host><div class="track" role="img" [attr.aria-label]="ariaLabel()">
    @for (s of drawn(); track s.label) { <span class="seg" [attr.data-tone]="s.tone ?? 'accent'" [style.flexGrow]="s.count" tabindex="0" (pointermove)="show($event, s, host)" (focus)="show($event, s, host)" (pointerleave)="hover.set(null)" (blur)="hover.set(null)"></span> }
  </div><ul class="legend">@if (total() === 0) { <li class="none">no observations</li> } @for (s of segments(); track s.label) { <li><span class="key" [attr.data-tone]="s.tone ?? 'accent'"></span><span>{{ s.label }}</span><span class="num">{{ s.count }} · {{ pct(s.count) }}%</span></li> }</ul><sb-chart-tooltip [state]="hover()" [hostWidth]="host.clientWidth" /></div>`, styles: `
  .host { position:relative; } .track { display:flex; gap:2px; height:14px; background:var(--bg); border-radius:4px; overflow:hidden; } .seg { display:block; flex-basis:0; min-width:2px; outline:none; } .seg:hover,.seg:focus-visible { filter:brightness(1.15); } [data-tone='pos'] { background:var(--pos); } [data-tone='neg'] { background:var(--neg); } [data-tone='warn'] { background:var(--warn); } [data-tone='muted'] { background:var(--text-faint); } [data-tone='accent'] { background:var(--accent); } .legend { display:flex; flex-wrap:wrap; gap:var(--space-8) var(--space-14); margin:var(--space-6) 0 0; padding:0; list-style:none; font-size:var(--text-chip); } .legend li { display:inline-flex; align-items:center; gap:var(--space-6); color:var(--text-secondary); } .key { width:10px; height:10px; border-radius:2px; } .num { color:var(--text); font-variant-numeric:tabular-nums; } .none { color:var(--text-faint); font-style:italic; }`, })
export class ShareBar {
  readonly segments = input.required<readonly ShareSegment[]>(); readonly label = input.required<string>();
  protected readonly hover = signal<HoverState | null>(null); protected readonly total = computed(() => this.segments().reduce((n, s) => n + s.count, 0)); protected readonly drawn = computed(() => this.segments().filter((s) => s.count > 0));
  protected readonly ariaLabel = computed(() => `${this.label()}: ${this.segments().map((s) => `${s.label} ${s.count}`).join(', ')}`);
  protected pct(count: number): string { const total = this.total(); return total ? Math.round(count / total * 100).toString() : '0'; }
  protected show(event: PointerEvent | FocusEvent, segment: ShareSegment, host: HTMLElement): void { this.hover.set({ ...hoverPosition(event, host), title: this.label(), rows: [{ label: segment.label, value: `${segment.count} · ${this.pct(segment.count)}%` }] }); }
}
