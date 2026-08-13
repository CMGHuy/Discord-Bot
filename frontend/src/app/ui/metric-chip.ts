import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { MetricTone } from './metric-card';

/**
 * One number with a label, compact. The Dashboard's secondary tier.
 *
 * The same data as `MetricCard` in a fraction of the space — hierarchy comes
 * from size rather than from culling (design system Decision 2). Three cards
 * carry the daily numbers and six of these carry the rest; nine equal cards is
 * what made the old dashboard unreadable.
 */
@Component({
  selector: 'sb-metric-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="chip">
      <span class="label">{{ label() }}</span>
      <span class="value num" [class]="valueClass()">{{ display() }}</span>
    </div>
  `,
  styles: `
    .chip {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--space-8);
      padding: var(--space-6) var(--space-10);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }
    .label {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      white-space: nowrap;
    }
    .value { font-size: var(--text-subhead); font-weight: 600; }
    .pos { color: var(--pos); }
    .neg { color: var(--neg); }
    .warn { color: var(--warn); }
    .absent { color: var(--text-faint); }
  `,
})
export class MetricChip {
  readonly label = input.required<string>();
  readonly value = input.required<number | null>();
  readonly tone = input<MetricTone>('plain');
  readonly unit = input('');
  readonly decimals = input(2);

  /** An em dash, matching `MetricCard`: a metric with no value yet is not a
   *  metric that is zero. */
  protected readonly display = computed(() => {
    const value = this.value();
    if (value === null) return '—';
    return `${value.toFixed(this.decimals())}${this.unit()}`;
  });

  protected readonly valueClass = computed(() => {
    const value = this.value();
    if (value === null) return 'absent';
    if (this.tone() === 'caution') return 'warn';
    if (this.tone() !== 'pnl') return '';
    // Exactly zero is neither a profit nor a loss.
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  });
}
