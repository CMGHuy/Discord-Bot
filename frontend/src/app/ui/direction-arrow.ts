import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { ABSENT } from './format';
import { Icon, IconName } from './icon';

/**
 * Direction as a single icon — spec v18 Decision 4, drawn by v240 §4: the
 * `long` / `short` trend arrows replaced the ▲ / ▼ text glyphs, whose shape
 * changed with the font and sat off the baseline.
 *
 * **The one recorded exception to the valence rule.** Everywhere else green
 * and red mean money made and money lost; here they mean long and short,
 * which is a direction and not an outcome. It is allowed because the pairing
 * is so strongly conventional in trading UIs that the alternative reads as a
 * bug, and it is written down so nobody "fixes" it later by making both
 * arrows grey.
 *
 * The icon is the entire content of the cell, so the accessible name is
 * load-bearing rather than a nicety: without it the column is silent to a
 * screen reader and the shape carries everything. The icon is aria-hidden
 * with an empty title; the span is `role="img"` so its aria-label is
 * announced although it holds no text.
 */
@Component({
  selector: 'sb-direction-arrow',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (label(); as text) {
      <span class="arrow" [class]="cls()" role="img" [title]="text" [attr.aria-label]="text">
        <sb-icon [name]="icon()" title="" />
      </span>
    } @else {
      <span class="absent" aria-hidden="true">{{ absent }}</span>
    }
  `,
  styles: `
    /* An svg has no text baseline: in a baseline-aligned flex row (Recent
       Activity) the arrow centres on the row as sb-icon does, and inline in
       text (the confidence cell) it centres on the line. */
    :host { display: inline-flex; align-self: center; vertical-align: middle; }
    .arrow { display: inline-flex; line-height: 0; cursor: help; }
    .long  { color: var(--pos); }
    .short { color: var(--neg); }
    .absent { color: var(--text-muted); }
  `,
})
export class DirectionArrow {
  readonly direction = input<string | null>(null);

  protected readonly absent = ABSENT;

  private readonly isLong = computed(() => this.direction() === 'bullish');
  private readonly isShort = computed(() => this.direction() === 'bearish');

  /** Read only when `label()` is set, i.e. for a long or a short. */
  protected readonly icon = computed<IconName>(() => (this.isLong() ? 'long' : 'short'));
  protected readonly cls = computed(() => (this.isLong() ? 'long' : 'short'));

  /** Null for an unknown direction, which is what selects the dash branch. */
  protected readonly label = computed(() =>
    this.isLong() ? 'Long (bullish)' : this.isShort() ? 'Short (bearish)' : null,
  );
}
