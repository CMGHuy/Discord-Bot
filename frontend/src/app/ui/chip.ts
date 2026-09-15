import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * How a chip is coloured: one of the five quality bands, or neutral.
 *
 * `q1`…`q5` rather than `high`/`mid`/`low` because the ramp has five steps
 * now and the names must not imply three. They map to `--quality-1`…`5`
 * positionally, which is what lets a component pick a band by number instead
 * of string-building a token name — `var(--quality-9)` resolves to nothing and
 * renders invisible text.
 *
 * v80 D4 adds `good`, `warn` and `info`: states that are judgements but not
 * quality levels (a gate passed, a stale feed, a note). They tint rather than
 * outline, which is what tells them apart from a quality chip in one row.
 *
 * v86 adds `bad` and `muted` for the cohort verdict chip: `bad` is `good`'s
 * negative mirror (the loss/danger colour, tinted the same way) for a cohort
 * that has been closing poorly; `muted` is dimmer than `neutral` (which
 * still reads as an ordinary category tag, like a horizon) for "no opinion
 * yet" -- COHORT_UNKNOWN must not look like a judgement call in either
 * direction.
 */
export type ChipTone =
  | 'neutral'
  | 'good'
  | 'warn'
  | 'info'
  | 'bad'
  | 'muted'
  | 'q1'
  | 'q2'
  | 'q3'
  | 'q4'
  | 'q5';

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
 *
 * Mono caps by default (v80 D4), so a tag reads as a tag and not as a word in
 * the sentence beside it. `caps` exists for the one chip that must keep its
 * case: a quality level is named `Lv4`, and `LV4` reads as something else.
 */
@Component({
  selector: 'sb-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="chip" [class]="tone()" [class.caps]="caps()">{{ label() }}</span>`,
  styles: `
    .chip {
      display: inline-flex;
      align-items: center;
      padding: 1px var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-chip);
      font-family: var(--font-mono);
      font-size: var(--text-chip);
      font-weight: 500;
      white-space: nowrap;
    }
    /* The .sb-label spacing, for the same reason: capitals need air. */
    .caps { text-transform: uppercase; letter-spacing: 0.08em; }
    .neutral { color: var(--text-secondary); }
    .good { color: var(--pos); background: var(--pos-soft); border-color: transparent; }
    .warn { color: var(--warn); background: var(--warn-soft); border-color: transparent; }
    .info { color: var(--info); background: var(--info-soft); border-color: transparent; }
    /* v86 -- bad is good's mirror image, same tint treatment, the loss
       colour instead of the profit one. */
    .bad { color: var(--neg); background: var(--neg-soft); border-color: transparent; }
    /* Dimmer than .neutral on purpose (--text-muted, not --text-secondary):
       neutral still reads as a plain category tag, and COHORT_UNKNOWN is
       "no opinion yet", not a category. */
    .muted { color: var(--text-muted); }
    .q1 { color: var(--quality-1); border-color: color-mix(in srgb, var(--neg) 35%, transparent); }
    .q2 { color: var(--quality-2); border-color: color-mix(in srgb, var(--warn) 35%, transparent); }
    .q3 { color: var(--quality-3); }
    /* Its own hue, not --info's: info is lavender since v80 D1, and level 4
       is the ramp's yellow-green. */
    .q4 { color: var(--quality-4); border-color: color-mix(in srgb, var(--quality-4) 35%, transparent); }
    .q5 { color: var(--quality-5); border-color: color-mix(in srgb, var(--pos) 35%, transparent); }

    /* v80 D4 -- a chip in a phone row is a tap target when it sits inside a
       button, and a line of text when it does not; 28px serves both. */
    @media (pointer: coarse), (max-width: 639px) {
      .chip { min-height: 28px; }
    }
  `,
})
export class Chip {
  readonly label = input.required<string>();
  readonly tone = input<ChipTone>('neutral');
  readonly caps = input(true);
}

/**
 * Convenience over `Chip` for the two fields that carry a quality judgement,
 * so no call site has to remember to pass the tone.
 */
@Component({
  selector: 'sb-quality-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip],
  template: `<sb-chip [label]="label()" [tone]="tone()" [caps]="false" />`,
})
export class QualityChip {
  /** A confidence level (1–5) or a tier (`A`/`B`/`C`). */
  readonly value = input.required<number | string | null>();
  /** Shown instead of the raw value — `Lv4`, `Tier B`. Defaults to the value. */
  readonly label = input.required<string>();

  protected readonly tone = computed(() => qualityTone(this.value()));
}
