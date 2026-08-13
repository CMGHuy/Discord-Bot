import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

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
 */
@Component({
  selector: 'sb-confidence-cell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (level() !== null) {
      <span class="conf">
        <span class="badge" [class]="band()">Lv{{ level() }}</span>
        @if (score() !== null) {
          <span class="sep">{{ ' · ' }}</span>
          <span class="score">{{ score() }}</span>
        }
      </span>
    } @else {
      <span class="absent">{{ absent }}</span>
    }
  `,
  styles: `
    .conf { font-family: var(--font-mono); font-size: var(--text-table); white-space: nowrap; }
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

  protected readonly absent = ABSENT;

  protected readonly band = computed(() => {
    const lv = this.level();
    return lv !== null && lv >= 1 && lv <= 5 ? `q${lv}` : 'q3';
  });
}
