import { ChangeDetectionStrategy, Component, computed, contentChildren, input } from '@angular/core';
import { ABSENT, num } from './format';
export type FigureTone = 'plain' | 'pnl' | 'caution';
@Component({ selector: 'sb-figure', changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div class="figure"><span class="sb-label">{{ label() }}</span><span class="value num" [class]="toneClass()">{{ display() }}</span>@if (sub(); as text) { <span class="sub num">{{ text }}</span> }</div>`,
  styles: `:host { display: block; min-width: 0; border-left: var(--figure-rule, 0px) solid var(--border); border-top: var(--figure-rule, 0px) solid var(--border); } .figure { display: flex; flex-direction: column; gap: var(--space-6); height: 100%; box-sizing: border-box; padding: var(--space-14) var(--space-20); background: var(--surface); } .value { font-family: var(--font-mono); font-size: var(--register-figure, var(--text-metric)); font-weight: 500; font-variant-numeric: tabular-nums; line-height: 1.1; white-space: nowrap; } .sub { color: var(--text-muted); font-size: var(--register-label, var(--text-table)); } .warn { color: var(--warn); } .absent { color: var(--text-muted); } @container figures (max-width: 639px) { .figure { padding: var(--space-10) var(--space-14); } .value { font-size: var(--text-title); } }`,
})
export class Figure {
  readonly label = input.required<string>(); readonly value = input.required<number | null>(); readonly tone = input<FigureTone>('plain'); readonly unit = input(''); readonly decimals = input(2); readonly sub = input<string | null>(null);
  protected readonly display = computed(() => { const value = this.value(); return value === null ? ABSENT : `${num(value, this.decimals())}${this.unit()}`; });
  protected readonly toneClass = computed(() => { const value = this.value(); if (value === null) return 'absent'; if (this.tone() === 'caution') return 'warn'; if (this.tone() !== 'pnl') return ''; return value > 0 ? 'pos' : value < 0 ? 'neg' : ''; });
}
@Component({ selector: 'sb-figure-strip', changeDetection: ChangeDetectionStrategy.OnPush, host: { '[style.--figure-columns]': 'columns()' }, template: `<div class="strip"><ng-content /></div>`, styles: `:host { display: block; overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius); container: figures / inline-size; } .strip { --figure-rule: 1px; display: grid; grid-template-columns: repeat(var(--figure-columns, 4), minmax(0, 1fr)); margin: -1px 0 0 -1px; } @container figures (max-width: 639px) { .strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } }`, })
export class FigureStrip { private readonly figures = contentChildren(Figure); protected readonly columns = computed(() => Math.min(4, Math.max(1, this.figures().length))); }
