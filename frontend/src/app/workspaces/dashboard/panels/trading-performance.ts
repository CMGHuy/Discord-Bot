import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { DashboardScope } from '../../../api/models';
import { Button } from '../../../ui/button';
import { ControlRow, Panel } from '../../../ui/layout';
import { MetricCard } from '../../../ui/metric-card';
import { PortfolioValue } from './portfolio-value';

/** `DashboardScope` also has a third value, 'active', that this toggle never
 *  sets and never renders as pressed -- reusing the store's real type rather
 *  than a narrower local one so `[scope]="store.scope()"` needs no cast. */
export type DashboardScopeMode = DashboardScope;

/**
 * The eight figures — v85 D9.
 *
 * Win rate, expectancy and payoff ratio travel together on purpose: win rate
 * and payoff ratio decompose expectancy, so read as a triple they say why the
 * expectancy is what it is rather than only what it is.
 *
 * The scope control sits in this panel's header (D10) and is page-wide: it
 * also re-scopes the Closed tab below. That was chosen deliberately with the
 * caveat understood — it is not an oversight to "fix" by narrowing it.
 *
 * Portfolio Value merged in as this panel's first section rather than a
 * sibling card: both describe "how am I doing", and two bordered boxes side
 * by side that never disagree in that context read as one idea sliced in two.
 */
@Component({
  selector: 'sb-trading-performance',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, MetricCard, ControlRow, Button, PortfolioValue],
  template: `
    <sb-panel heading="Trading performance">
      <sb-control-row panel-actions role="group" aria-label="Date scope">
        @for (option of scopes; track option.mode) {
          <button
            sb-button
            type="button"
            [attr.data-scope]="option.mode"
            [variant]="scope() === option.mode ? 'secondary' : 'ghost'"
            [attr.aria-pressed]="scope() === option.mode"
            (click)="scopeChange.emit(option.mode)"
          >{{ option.label }}</button>
        }
      </sb-control-row>

      <div class="combined">
        <sb-portfolio-value
          class="portfolio"
          [balance]="balance()"
          [changePct]="changePct()"
          [points]="points()"
          [currency]="currency()"
        />

        <div class="grid">
          <sb-metric-card label="Open P&L" [value]="openPnlPct()" tone="pnl" unit="%" />
          <sb-metric-card label="Win rate" [value]="winRate()" unit="%" [decimals]="1" />
          <sb-metric-card label="Expectancy" [value]="expectancyR()" tone="pnl" unit="R" />
          <sb-metric-card label="Payoff ratio" [value]="payoffRatio()" [decimals]="2" />
          <sb-metric-card [label]="realizedLabel()" [value]="realizedAmount()"
                          tone="pnl" [unit]="currencyUnit()" />
          <sb-metric-card label="Open trades" [value]="openTrades()" [decimals]="0" />
          <sb-metric-card label="Avg confidence" [value]="avgConfidence()" [decimals]="1" />
          <sb-metric-card label="Risk used" [value]="riskUsedPct()" unit="%" [sub]="riskSub()" />
        </div>
      </div>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    /* The metric grid is sized to its own four fixed-ish columns (.grid,
       below) rather than a flexible track, so .combined's "auto" column
       gives it exactly that width and no more; Portfolio Value (1fr) takes
       every pixel left over instead of sitting in a capped column of its
       own. Stacks below 640px -- narrower than that and a shared row
       squeezes the sparkline into an unreadable sliver. */
    .combined {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: var(--space-20);
      align-items: start;
    }
    .portfolio { min-width: 0; }
    @media (max-width: 640px) {
      .combined { grid-template-columns: minmax(0, 1fr); }
    }
    /* A fixed 4 columns, not auto-fit: eight cards read as two even rows of
       four, never an uneven 5+3 or 6+2 split that auto-fit would produce at
       an in-between width. minmax with two lengths (not a bare 1fr) keeps
       this grid's own width computable when the ancestor asks for its
       content size (.combined's "auto" track above, and -- separately --
       any container that ends up shrink-to-fit sized), which a 1fr track
       cannot give under those conditions. */
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 180px));
      gap: var(--space-14);
    }
    @media (max-width: 640px) {
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  `,
})
export class TradingPerformance {
  readonly balance = input<number | null>(null);
  readonly changePct = input<number | null>(null);
  readonly points = input<readonly number[]>([]);
  readonly openPnlPct = input<number | null>(null);
  readonly winRate = input<number | null>(null);
  readonly expectancyR = input<number | null>(null);
  readonly avgConfidence = input<number | null>(null);
  readonly realizedAmount = input<number | null>(null);
  readonly realizedLabel = input('Realised today');
  readonly openTrades = input<number>(0);
  readonly riskUsedPct = input<number | null>(null);
  readonly riskCapPct = input<number | null>(null);
  /** Mean winning R over the magnitude of mean losing R. Null, never 0, when
   *  either side has no outcomes yet — see payoff_ratio_from_rs. */
  readonly payoffRatio = input<number | null>(null);
  readonly currency = input('€');
  readonly scope = input<DashboardScopeMode>('today');
  readonly scopeChange = output<DashboardScopeMode>();

  protected readonly scopes: { mode: DashboardScopeMode; label: string }[] = [
    { mode: 'today', label: 'Today' },
    { mode: 'all', label: 'All days' },
  ];

  protected readonly currencyUnit = computed(() => ` ${this.currency()}`);
  protected readonly riskSub = computed(() => {
    const cap = this.riskCapPct();
    return cap === null ? null : `of ${cap.toFixed(1)}% cap`;
  });
}
