import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Panel } from '../../../ui/layout';
import { Sparkline } from '../../../ui/sparkline';
import { amount, pct } from '../../../ui/format';

/**
 * The account, in one figure — v85 D8.
 *
 * Deliberately NOT the mockup's interactive intraday chart: the only equity
 * series this bot keeps is `equity_30d`, 30 daily points. A 1D/1W/1M/3M/YTD/
 * 1Y/ALL strip over one series would be six controls that cannot answer.
 */
@Component({
  selector: 'sb-portfolio-value',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Sparkline],
  template: `
    <sb-panel heading="Portfolio value">
      @if (balance() !== null) {
        <p class="figure">{{ money() }}</p>
      } @else {
        <p class="figure muted">—</p>
      }

      @if (changePct() !== null) {
        <p class="change" [class.pos]="changePct()! > 0" [class.neg]="changePct()! < 0">
          {{ fmtPct(changePct()) }} today
        </p>
      }

      @if (points().length) {
        <sb-sparkline [points]="points()" label="30-day equity" />
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .figure {
      margin: 0;
      font-size: var(--text-hero);
      font-weight: 600;
      color: var(--text);
      font-variant-numeric: tabular-nums;
      line-height: 1.1;
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
  readonly balance = input<number | null>(null);
  readonly changePct = input<number | null>(null);
  readonly points = input<readonly number[]>([]);
  readonly currency = input('€');

  protected readonly money = computed(() => amount(this.balance(), this.currency()));
  protected fmtPct = pct;
}
