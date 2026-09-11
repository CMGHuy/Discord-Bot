import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { DashboardScope } from '../../../api/models';
import { Button } from '../../../ui/button';
import { ControlRow, Panel } from '../../../ui/layout';
import { MetricCard } from '../../../ui/metric-card';

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
 */
@Component({
  selector: 'sb-trading-performance',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, MetricCard, ControlRow, Button],
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
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    /* auto-fit rather than a fixed count: eight cards should reflow to 4×2,
       2×4 or 1×8 by available width, not by a breakpoint list. */
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: var(--space-14);
    }
  `,
})
export class TradingPerformance {
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
