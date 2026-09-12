import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * The smallest sample a derived metric may be read from without a warning.
 *
 * 30 is not a law of statistics; it is the point below which this book's
 * per-strategy and per-horizon slices have historically flipped sign on one
 * more trade. R11-04 makes it a setting — until then it is a constant, so the
 * primitive can ship in wave 1 ahead of the control that tunes it.
 */
export const MIN_SAMPLE_N = 30;

export type StatTone = 'neutral' | 'pos' | 'neg';

/**
 * One metric, its label, and its sample size — spec v85 D23.
 *
 * The sample size is not decoration and not a tooltip. A win rate of 68% over
 * seven trades and one over four hundred are different claims, and a tile that
 * renders them identically is the correctness bug this component exists to
 * prevent. Below `MIN_SAMPLE_N` the tile de-emphasises itself and says how many
 * more closed trades it needs — the figure is still shown, because hiding it
 * would stop you watching a young strategy develop.
 *
 * `value` is pre-formatted by the caller. This component never formats a
 * number: the pages that use it disagree about units (R, %, currency) and a
 * formatter here would have to learn all of them.
 */
@Component({
  selector: 'sb-stat-tile',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="tile" [class.thin]="thin()" [class]="tone()">
      <div class="label">{{ label() }}</div>
      <div class="value">{{ value() ?? '—' }}</div>
      @if (sample() !== null) {
        <div class="sample" [title]="sampleTitle()">
          N={{ sample() }}@if (thin()) {<span class="flag"> · thin sample</span>}
        </div>
      }
      @if (hint()) {
        <div class="hint">{{ hint() }}</div>
      }
    </div>
  `,
  styles: `
    .tile {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: var(--space-14);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }
    .label {
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-faint);
    }
    .value {
      font-size: var(--text-metric);
      font-variant-numeric: tabular-nums;
      color: var(--text);
    }
    .pos .value { color: var(--pos); }
    .neg .value { color: var(--neg); }
    .sample,
    .hint {
      font-size: var(--text-micro);
      font-variant-numeric: tabular-nums;
      color: var(--text-faint);
    }
    /* The second cue. Opacity alone would be a colour-only signal, which the
       plan forbids; the .flag span puts the same fact in words. */
    .thin .value { opacity: 0.62; }
    .thin .flag { font-style: italic; }
  `,
})
export class StatTile {
  readonly label = input.required<string>();
  readonly value = input.required<string | null>();
  readonly sample = input<number | null>(null);
  readonly tone = input<StatTone>('neutral');
  readonly hint = input<string | undefined>(undefined);

  protected readonly thin = computed(() => {
    const n = this.sample();
    return n !== null && n < MIN_SAMPLE_N;
  });

  protected readonly sampleTitle = computed(() => {
    const n = this.sample();
    if (n === null) return '';
    if (n >= MIN_SAMPLE_N) return `${n} closed trades`;
    return `${n} closed trades — ${MIN_SAMPLE_N - n} more before this figure is worth reading`;
  });
}
