import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { ABSENT } from './format';

/**
 * Direction as a single glyph — spec v18 Decision 4.
 *
 * **The one recorded exception to the valence rule.** Everywhere else green
 * and red mean money made and money lost; here they mean long and short,
 * which is a direction and not an outcome. It is allowed because the pairing
 * is so strongly conventional in trading UIs that the alternative reads as a
 * bug, and it is written down so nobody "fixes" it later by making both
 * arrows grey.
 *
 * The glyph is the entire content of the cell, so the accessible name is
 * load-bearing rather than a nicety: without it the column is silent to a
 * screen reader and the shape carries everything.
 */
@Component({
  selector: 'sb-direction-arrow',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (label(); as text) {
      <span class="arrow" [class]="cls()" [title]="text" [attr.aria-label]="text">
        {{ glyph() }}
      </span>
    } @else {
      <span class="absent" aria-hidden="true">{{ absent }}</span>
    }
  `,
  styles: `
    .arrow {
      font-weight: 700;
      font-size: var(--text-subhead);
      cursor: help;
      line-height: 1;
    }
    .long  { color: var(--pos); }
    .short { color: var(--neg); }
    .absent { color: var(--text-faint); }
  `,
})
export class DirectionArrow {
  readonly direction = input<string | null>(null);

  protected readonly absent = ABSENT;

  private readonly isLong = computed(() => this.direction() === 'bullish');
  private readonly isShort = computed(() => this.direction() === 'bearish');

  protected readonly glyph = computed(() => (this.isLong() ? '▲' : this.isShort() ? '▼' : ABSENT));
  protected readonly cls = computed(() => (this.isLong() ? 'long' : 'short'));

  /** Null for an unknown direction, which is what selects the dash branch. */
  protected readonly label = computed(() =>
    this.isLong() ? 'Long (bullish)' : this.isShort() ? 'Short (bearish)' : null,
  );
}
