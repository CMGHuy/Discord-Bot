import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * How a chip is coloured: one of the five quality bands, or neutral.
 *
 * `q1`…`q5` rather than `high`/`mid`/`low` because the ramp has five steps
 * now and the names must not imply three. They map to `--quality-1`…`5`
 * positionally, which is what lets a component pick a band by number instead
 * of string-building a token name — `var(--quality-9)` resolves to nothing and
 * renders invisible text.
 */
export type ChipTone = 'neutral' | 'q1' | 'q2' | 'q3' | 'q4' | 'q5';

/**
 * Maps a confidence level (1–5) or a tier (`A`/`B`/`C`) onto the quality ramp
 * — spec v18 Decision 2.
 *
 * This function exists so the mapping is in exactly one place.
 *
 * **These chips used to be greyscale on purpose** (spec v20 Decision 3): the
 * old rule was that green means money and nothing else, so quality could not
 * be coloured without green meaning two things in adjacent columns. v18
 * replaces that with *one colour, one valence* — green means good in every
 * domain — which is what makes the ramp legitimate here. It is also the whole
 * reason the confidence column was asked for back: a greyscale ramp is not
 * scannable down a column, which is the only way this field is ever read.
 *
 * Confidence maps straight through, `Lv1`→`q1` … `Lv5`→`q5`. Tier is a
 * three-step scale onto the same five-step ramp: `A`→`q5` (good), `B`→`q3`
 * (neutral), `C`→`q2` (caution). `C` is amber rather than red because a weak
 * tier is a caution, not a loss — that much of the old reasoning survives.
 */
export function qualityTone(value: number | string | null | undefined): ChipTone {
  if (value === null || value === undefined || value === '') return 'neutral';

  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 'neutral';
    const band = Math.round(value);
    if (band < 1 || band > 5) return 'neutral';
    return `q${band}` as ChipTone;
  }

  switch (value.trim().toUpperCase()) {
    case 'A':
      return 'q5';
    case 'B':
      return 'q3';
    case 'C':
      return 'q2';
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
    .q1 { color: var(--quality-1); border-color: color-mix(in srgb, var(--neg) 35%, transparent); }
    .q2 { color: var(--quality-2); border-color: color-mix(in srgb, var(--warn) 35%, transparent); }
    .q3 { color: var(--quality-3); }
    .q4 { color: var(--quality-4); border-color: color-mix(in srgb, var(--info) 35%, transparent); }
    .q5 { color: var(--quality-5); border-color: color-mix(in srgb, var(--pos) 35%, transparent); }
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
