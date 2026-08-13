import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * How a chip is coloured. Note what is missing: there is no `good`/`bad` pair
 * and no way to ask for green or red. Those two colours mean P&L direction and
 * nothing else, and a chip never carries P&L.
 */
export type ChipTone = 'neutral' | 'quality-high' | 'quality-mid' | 'quality-low';

/**
 * Maps a confidence level (1–5) or a tier (`A`/`B`/`C`) onto the greyscale
 * quality ramp — spec 3 Decision 3.
 *
 * This function exists so the mapping is in exactly one place. Confidence and
 * tier chips are currently green/amber/red by value, which the colour rules
 * forbid: they are QUALITY, not money. Leaving them coloured while applying
 * the rules elsewhere would be worse than not applying the rules at all,
 * because green would then mean two different things in adjacent columns of
 * the same row.
 *
 * `Lv5/A` → `--text`, `Lv3/B` → `--text-secondary`, `Lv1/C` → `--warn`, with
 * `Lv4`/`Lv2` folding into the band next to them. Amber is the weakest band
 * rather than red because amber means caution, and a low-confidence setup is a
 * caution rather than a loss.
 */
export function qualityTone(value: number | string | null | undefined): ChipTone {
  if (value === null || value === undefined || value === '') return 'neutral';

  if (typeof value === 'number') {
    if (value >= 4) return 'quality-high';
    if (value === 3) return 'quality-mid';
    return 'quality-low';
  }

  switch (value.trim().toUpperCase()) {
    case 'A':
      return 'quality-high';
    case 'B':
      return 'quality-mid';
    case 'C':
      return 'quality-low';
    default:
      return 'neutral';
  }
}

/**
 * A small labelled tag — tier, horizon, confidence.
 *
 * Deliberately toneless by default: a horizon is not a judgement and does not
 * earn a colour. Use `qualityTone()` for the two that are judgements.
 */
@Component({
  selector: 'sb-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="chip" [class]="tone()">{{ label() }}</span>`,
  styles: `
    .chip {
      display: inline-block;
      padding: 1px var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-chip);
      font-size: var(--text-chip);
      font-weight: 600;
      letter-spacing: 0.04em;
      white-space: nowrap;
    }
    .neutral { color: var(--text-secondary); }
    .quality-high { color: var(--quality-high); border-color: var(--text-faint); }
    .quality-mid { color: var(--quality-mid); }
    .quality-low { color: var(--quality-low); border-color: color-mix(in srgb, var(--warn) 35%, transparent); }
  `,
})
export class Chip {
  readonly label = input.required<string>();
  readonly tone = input<ChipTone>('neutral');
}

/**
 * Convenience over `Chip` for the two fields that carry a quality judgement,
 * so no call site has to remember to pass the tone.
 */
@Component({
  selector: 'sb-quality-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip],
  template: `<sb-chip [label]="label()" [tone]="tone()" />`,
})
export class QualityChip {
  /** A confidence level (1–5) or a tier (`A`/`B`/`C`). */
  readonly value = input.required<number | string | null>();
  /** Shown instead of the raw value — `Lv4`, `Tier B`. Defaults to the value. */
  readonly label = input.required<string>();

  protected readonly tone = computed(() => qualityTone(this.value()));
}
