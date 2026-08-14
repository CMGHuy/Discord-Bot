import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** One bar: a bin's label and how many observations fell in it. */
export interface HistogramBin {
  label: string;
  count: number;
}

/**
 * A distribution, as horizontal bars.
 *
 * **Horizontal, and bars.** The bin labels are the axis — "-1.0R", "0-2 days" —
 * and a vertical histogram sets them on their side or drops every other one.
 * Bars rather than a line because the bins are discrete buckets, and rather
 * than a pie because a pie cannot show an ordered scale at all: the whole
 * finding in a P&L or R-multiple distribution is its SHAPE, a cluster of small
 * losses with a tail of larger wins, and shape needs an ordered axis.
 *
 * Bars are scaled against the tallest bin, not against the total. Against the
 * total, a bin holding two trades out of ninety is two percent of the track and
 * invisible — which is exactly the tail worth seeing.
 *
 * `negative` marks which bins are losses. It is a predicate rather than a
 * colour so no component has to know the token names, and the labels carry
 * their own sign, so colour is never the only cue.
 */
@Component({
  selector: 'sb-histogram',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ul>
      @for (bin of bins(); track bin.label) {
        <li>
          <span class="label num">{{ bin.label }}</span>
          <span class="track">
            <span
              class="fill"
              [class.negative]="isNegative()(bin)"
              [style.width.%]="width(bin.count)"
            ></span>
          </span>
          <span class="count num">{{ bin.count }}</span>
        </li>
      }
    </ul>
  `,
  styles: `
    ul { display: grid; gap: 2px; list-style: none; }
    li {
      display: grid;
      grid-template-columns: 4rem 1fr 2.5rem;
      align-items: center;
      gap: var(--space-8);
    }
    .label, .count { color: var(--text-secondary); font-size: var(--text-chip); }
    .count { text-align: right; }
    .track {
      height: 10px;
      background: var(--bg);
      border-radius: 2px;
      overflow: hidden;
    }
    .fill {
      display: block;
      height: 100%;
      /* Gains and losses are P&L direction — the one place the green/red pair
         is allowed by the colour rule. */
      background: var(--pos);
      border-radius: 2px;
    }
    .fill.negative { background: var(--neg); }
  `,
})
export class Histogram {
  readonly bins = input.required<readonly HistogramBin[]>();

  /** Defaults to "a label starting with a minus sign", which covers every
   *  signed-scale histogram here. A caller whose bins are not signed passes
   *  its own predicate, or accepts that nothing is marked as a loss. */
  readonly isNegative = input<(bin: HistogramBin) => boolean>((bin) =>
    bin.label.startsWith('-'),
  );

  private readonly tallest = computed(() =>
    Math.max(...this.bins().map((bin) => bin.count), 1),
  );

  protected width(count: number): number {
    return (count / this.tallest()) * 100;
  }
}
