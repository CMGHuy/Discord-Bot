import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { amount, pct } from '../../../ui/format';
import { ChartTarget, TimeWindow, signTone } from './equity-range.model';
import { EquityCandles } from './equity-candles';

/**
 * The account, in one figure and one chart — v85 D8, v172.
 *
 * The figure and the day change stay as they were; v172 replaces the
 * 30-point sparkline under them with `sb-equity-candles` (1H · 4H · 1D · 1W,
 * mark-to-market or closed trades only), which fetches its own candles.
 *
 * No panel of its own: it renders as the first section inside
 * `sb-trading-performance`'s single panel (v85 dashboard revision) rather
 * than as a sibling card, so the host binds `display: block` and leaves
 * borders/heading to whichever panel embeds it.
 */
@Component({
  selector: 'sb-portfolio-value',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [EquityCandles],
  template: `
    @if (balance() !== null) {
      <p class="figure">{{ money() }}</p>
    } @else {
      <p class="figure muted">—</p>
    }

    @if (changePct() !== null) {
      <p class="change" [class.pos]="changeTone() === 'pos'" [class.neg]="changeTone() === 'neg'">
        {{ fmtPct(changePct()) }} today
      </p>
    }

    <sb-equity-candles [currency]="currency()" [target]="chartTarget()"
                       (rangeChange)="chartRangeChange.emit($event)"
                       (viewReset)="viewReset.emit()" />
  `,
  styles: `
    :host { display: block; }
    .figure {
      margin: 0;
      font-size: var(--text-title);
      font-weight: 600;
      color: var(--text);
      font-variant-numeric: tabular-nums;
      line-height: 1.1;
      /* v95 A5: the figure is one number -- wrapped, it reads as several. */
      white-space: nowrap;
    }
    .figure.muted { color: var(--text-faint); }
    .change {
      margin: var(--space-4) 0 var(--space-10);
      font-size: var(--text-body);
      font-variant-numeric: tabular-nums;
    }
    .change.pos { color: var(--pos); }
    .change.neg { color: var(--neg); }
  `,
})
export class PortfolioValue {
  /** DashboardStore owns both ends of the chart scope link. */
  readonly chartTarget = input<ChartTarget | null>(null);
  readonly chartRangeChange = output<TimeWindow>();
  /** The chart's reset button, passed up to the scope owner. */
  readonly viewReset = output<void>();
  readonly balance = input<number | null>(null);
  readonly changePct = input<number | null>(null);
  /** The API's 30-day `equity_30d` series. Still bound by
   *  `sb-trading-performance` and still served (spec v172 § 4 keeps it this
   *  release); no longer drawn here. Retiring it is a separate change. */
  readonly points = input<readonly number[]>([]);
  readonly currency = input('€');

  protected readonly money = computed(() => amount(this.balance(), this.currency()));
  protected readonly changeTone = computed(() => signTone(this.changePct()));
  protected fmtPct = pct;
}
