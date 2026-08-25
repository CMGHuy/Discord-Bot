import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { CHART_CHROME } from './chart/chart-frame';

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
    <div class="wrap">
      @if (referenceLine(); as ref) {
        <div class="track-col">
          <div class="reference-line" [style.left.%]="referenceLeft()"></div>
        </div>
      }
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
    </div>
  `,
  styles: `
    /* The reference line sits in a grid layer of its own (.wrap), whose
       three columns exactly mirror each .li's own 4rem/1fr/2.5rem grid, so
       an absolutely-positioned line in the middle column lands on the bars
       themselves rather than spanning the label/count columns too. */
    .wrap {
      position: relative;
      display: grid;
      grid-template-columns: 4rem 1fr 2.5rem;
      gap: var(--space-8);
    }
    .wrap > ul { grid-column: 1 / -1; }
    .track-col { grid-column: 2; grid-row: 1; position: relative; align-self: stretch; }
    .reference-line {
      position: absolute;
      top: 0;
      bottom: 0;
      border-left: 1px dashed var(--text-faint);
    }
    ul { display: grid; gap: 2px; list-style: none; }
    li {
      display: grid;
      grid-template-columns: 4rem 1fr 2.5rem;
      align-items: center;
      gap: var(--space-8);
    }
    /* v54 D5: "The bin labels are the axis" (this file's own docstring) --
       so the LABEL takes CHART_CHROME's tick colour/size, the same as every
       other chart's axis text. The count is the observation itself, not the
       axis -- it keeps the body-text pair every other value in this app
       uses, so the number the reader is there to read does not get dimmer
       and smaller than its own label. */
    .label { color: ${CHART_CHROME.tickColour}; font-size: ${CHART_CHROME.tickSize}; }
    .count { color: var(--text-secondary); font-size: var(--text-chip); text-align: right; }
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

  /** A fixed scale ceiling. Wins over the default scale-to-tallest-bin --
   *  needed by the Calibration decile chart, where two deciles at 60% and
   *  85% win rate must scale against an absolute 100, not against each
   *  other (which would understate a genuinely bad decile next to a worse
   *  one). */
  readonly max = input<number | null>(null);

  /** A dashed line drawn across every bar's track, at this value against
   *  the active scale (`max` when given, else the tallest bin). */
  readonly referenceLine = input<number | null>(null);

  private readonly tallest = computed(
    () => this.max() ?? Math.max(...this.bins().map((bin) => bin.count), 1),
  );

  protected width(count: number): number {
    return (count / this.tallest()) * 100;
  }

  protected referenceLeft(): number {
    const ref = this.referenceLine();
    return ref === null ? 0 : (ref / this.tallest()) * 100;
  }
}
