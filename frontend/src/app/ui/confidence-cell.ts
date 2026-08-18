import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { DirectionArrow } from './direction-arrow';
import { ABSENT } from './format';

/**
 * Confidence as `Lv4 · 78` — spec v18 Decision 4.
 *
 * Two columns become one. The score is optional and its separator goes with
 * it: `Lv4 · —` reads as a rendering fault, where plain `Lv4` reads as a
 * level with no score, which is what it is.
 *
 * The band is a CLASS per level, never a token name built by interpolation.
 * `var(--quality-{{level}})` looks tidier and turns a level outside 1–5 into
 * `var(--quality-9)`, which resolves to nothing — the text renders in the
 * inherited colour or none at all, and the cell silently disappears.
 *
 * `direction` is optional and, when given, renders DirectionArrow to the
 * LEFT of the level -- the Dashboard's four lifecycle tables fold their own
 * separate Direction column into this one to save the width, and every
 * other call site (Trades, the detail views) simply never passes it, which
 * leaves them exactly as before.
 *
 * The arrow sits OUTSIDE the level's own @if: a PENDING plan often has a
 * direction (it is one of the plan's defining numbers) before it has ever
 * been scored for confidence (which only exists once a trade is logged), so
 * gating the arrow on `level() !== null` too would silently drop the one
 * piece of direction information the row has left, now that there is no
 * separate Direction column to fall back to.
 */
@Component({
  selector: 'sb-confidence-cell',
  imports: [DirectionArrow],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="conf">
      @if (direction(); as dir) {
        <sb-direction-arrow [direction]="dir" />
      }
      @if (level() !== null) {
        <span class="badge" [class]="band()">Lv{{ level() }}</span>
        @if (score() !== null) {
          <span class="sep">{{ ' · ' }}</span>
          <span class="score">{{ score() }}</span>
        }
      } @else {
        <span class="absent">{{ absent }}</span>
      }
    </span>
  `,
  styles: `
    .conf {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      font-family: var(--font-mono);
      font-size: var(--text-table);
      white-space: nowrap;
    }
    .badge { font-weight: 600; }
    .score { color: var(--text-secondary); }
    /* Spacing in the text, not a margin -- Angular strips whitespace between
       elements, and textContent is what a screen reader reads out. */
    .sep { color: var(--text-faint); white-space: pre; }
    .absent { color: var(--text-faint); }

    .q1 { color: var(--quality-1); }
    .q2 { color: var(--quality-2); }
    .q3 { color: var(--quality-3); }
    .q4 { color: var(--quality-4); }
    .q5 { color: var(--quality-5); }
  `,
})
export class ConfidenceCell {
  readonly level = input<number | null>(null);
  readonly score = input<number | null>(null);
  readonly direction = input<string | null>(null);

  protected readonly absent = ABSENT;

  protected readonly band = computed(() => {
    const lv = this.level();
    return lv !== null && lv >= 1 && lv <= 5 ? `q${lv}` : 'q3';
  });
}
