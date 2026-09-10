import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Flash } from './flash';
import { ABSENT, money, pct } from './format';

/**
 * P&L as one cell holding both figures -- the v80 cell contract.
 *
 * `+4.20% (+9.80 €)`: the percentage says how good the trade was, the amount
 * says how much money that was, and neither answers the other's question.
 * Extracted from the identical templates in `trades.ts` and `dashboard.ts`.
 * Migration moves both here, and Ticker detail gains the amount.
 *
 * Coloured by the sign of the percentage through the global .pos/.neg (the
 * valence law's one green and one red), and flashing when the percentage
 * changes through the same [sbFlash] the templates used.
 *
 * An em dash when there is no percentage to price. An unknown amount is left
 * out, not shown as "(—)": a bracketed dash beside a real percentage reads as
 * a rendering fault, not as "size unknown".
 */
@Component({
  selector: 'sb-pnl-cell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Flash],
  template: `
    @if (pct() !== null) {
      <span class="pnl num" [sbFlash]="pct()" [class]="tone()">
        {{ pctText() }}
        @if (amount() !== null) {
          <span class="amount"> ({{ amountText() }})</span>
        }
      </span>
    } @else {
      <span class="absent">{{ absent }}</span>
    }
  `,
  styles: `
    .pnl { font-family: var(--font-mono); font-size: var(--text-table); white-space: nowrap; }
    /* The amount is the second figure: same colour, one step smaller. */
    .amount { font-size: var(--text-chip); }
    .absent { color: var(--text-muted); }
  `,
})
export class PnlCell {
  readonly pct = input.required<number | null>();
  readonly amount = input<number | null>(null);
  /** From `ConnectionStore.currency()`, never a literal -- see `money()`. */
  readonly currency = input.required<string>();

  protected readonly absent = ABSENT;
  protected readonly pctText = computed(() => pct(this.pct()));
  protected readonly amountText = computed(() => money(this.amount(), this.currency()));

  /** Exactly zero is neither a gain nor a loss. */
  protected readonly tone = computed(() => {
    const value = this.pct();
    if (value === null || value === 0) return '';
    return value > 0 ? 'pos' : 'neg';
  });
}
