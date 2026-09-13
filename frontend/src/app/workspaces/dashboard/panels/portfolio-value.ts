import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Sparkline } from '../../../ui/sparkline';
import { amount, pct } from '../../../ui/format';

/**
 * The account, in one figure — v85 D8.
 *
 * The bot keeps one honest 30-day series, so it is shown directly rather than
 * pretending a range picker can offer different histories.
 *
 * No panel of its own: it renders as the first section inside
 * `sb-trading-performance`'s single panel (v85 dashboard revision) rather
 * than as a sibling card, so the host binds `display: block` and leaves
 * borders/heading to whichever panel embeds it.
 */
@Component({
  selector: 'sb-portfolio-value',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Sparkline],
  template: `
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
