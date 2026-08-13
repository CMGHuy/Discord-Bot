import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { num } from './format';

/**
 * Entry, target and stop in one cell — spec v18 Decision 4.
 *
 * Always reads `entry → target / stop`, in that order, for both directions.
 * For a short the target is the LOWER number and the stop the higher one, so
 * the colours carry which is which, not the positions. Anything that inferred
 * role from magnitude would read correctly on every long and invert silently
 * on every short — which is the worst version of the bug, because the cell
 * still looks plausible.
 *
 * Three columns collapse into one here, so the tooltip spells the roles out:
 * the colour pair alone is not readable for everyone, and a bare `178.00 →
 * 195.00 / 170.00` does not say which number is the stop.
 */
@Component({
  selector: 'sb-plan-cell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="plan" [title]="tooltip()">
      <span class="entry">{{ fmt(entry()) }}</span>
      <span class="sep">{{ ' → ' }}</span>
      <span class="target">{{ fmt(target()) }}</span>
      <span class="sep">{{ ' / ' }}</span>
      <span class="stop">{{ fmt(stop()) }}</span>
    </span>
  `,
  styles: `
    .plan { font-family: var(--font-mono); font-size: var(--text-table); white-space: nowrap; }
    .entry  { color: var(--text-secondary); }
    .target { color: var(--pos); }
    .stop   { color: var(--neg); }
    /* Spacing lives in the TEXT, not in a margin. Angular strips whitespace
       between elements, so a margin-only gap renders correctly and leaves
       textContent as '178.00→195.00/170.00' -- which is what a screen reader
       announces and what anything reading the cell as a string gets. In a
       mono font the literal spaces are exactly one cell wide anyway. */
    .sep    { color: var(--text-faint); white-space: pre; }
  `,
})
export class PlanCell {
  readonly entry = input<number | null>(null);
  readonly target = input<number | null>(null);
  readonly stop = input<number | null>(null);

  protected readonly tooltip = computed(
    () =>
      `Entry ${this.fmt(this.entry())} · Target ${this.fmt(this.target())} · ` +
      `Stop ${this.fmt(this.stop())}`,
  );

  protected fmt(v: number | null): string {
    return num(v);
  }
}
