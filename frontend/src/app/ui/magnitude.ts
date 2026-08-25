import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * A bar showing how big a figure is, beside the figure itself.
 *
 * Magnitude is what a column of digits is worst at: reading "+2.10" against
 * "+0.30" takes a comparison, and a bar takes a glance. Decorative by
 * construction — the number is always adjacent, so this is aria-hidden and
 * announcing it would read every figure twice.
 *
 * Colour follows the valence law: --pos for a gain, --neg for a loss. That is
 * the one place a bar may carry a hue, and it reinforces a sign the adjacent
 * `signed()` string has already spelled out.
 */
@Component({
  selector: 'sb-magnitude',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'aria-hidden': 'true' },
  template: `
    @if (width(); as pct) {
      <span class="bar" [class.neg]="isNegative()" [style.width.%]="pct"></span>
    }
  `,
  styles: `
    :host { display: block; height: 3px; background: var(--surface-raised); border-radius: 2px; }
    .bar { display: block; height: 100%; border-radius: 2px; background: var(--pos); }
    .bar.neg { background: var(--neg); margin-left: auto; }
  `,
})
export class Magnitude {
  readonly value = input.required<number | null>();
  readonly max = input(1);

  protected readonly isNegative = computed(() => (this.value() ?? 0) < 0);
  protected readonly width = computed(() => {
    const v = this.value();
    if (typeof v !== 'number' || !Number.isFinite(v)) return null;
    const max = Math.abs(this.max()) || 1;
    return Math.min(100, (Math.abs(v) / max) * 100);
  });
}
