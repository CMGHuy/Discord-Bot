import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { DashboardScope } from '../../../api/models';
import { Panel } from '../../../ui/layout';
import { MetricCard } from '../../../ui/metric-card';
import { ACCOUNT_LABEL } from './equity-candles.model';
import { breakevenPairTone, riskTone as riskToneOf, signTone } from './equity-range.model';
import { PortfolioValue } from './portfolio-value';
import { amount, pct } from '../../../ui/format';
import { SegmentOption, Segmented } from '../../../ui/segmented';

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
  imports: [Panel, MetricCard, Segmented, PortfolioValue],
  template: `
    <sb-panel heading="Trading performance">
      <!-- v179 §3.3: one segmented control on the header line, in place of a
           bordered and a borderless button that stacked on a phone. -->
      <sb-segmented panel-actions label="Date scope" [options]="scopeOptions"
                    [value]="scope()" (valueChange)="pickScope($event)" />

      <div class="combined">
        <sb-portfolio-value
          class="portfolio"
          [balance]="balance()"
          [changePct]="changePct()"
          [points]="points()"
          [currency]="currency()"
        />

        <div class="grid">
          <sb-metric-card label="Open P&L" [value]="openPnlPct()" [tint]="openPnlTone()" unit="%" [sub]="openPnlSub()" [subPnl]="openPnlAmount()" />
          <sb-metric-card label="Win rate" [value]="winRate()" [tint]="winPairTone()" unit="%" [decimals]="1" [sub]="sample(winRateN())" />
          <sb-metric-card label="Expectancy" [value]="expectancyR()" [tint]="expectancyTone()" unit="R" [sub]="sample(expectancyN())" />
          <sb-metric-card label="Payoff ratio" [value]="payoffRatio()" [tint]="payoffTone()" [decimals]="2" [sub]="noCloseHint(payoffRatio())" />
          <sb-metric-card [label]="realizedLabel()" [value]="realizedAmount()" [tint]="realizedTone()"
                          [unit]="currencyUnit()" [sub]="noCloseHint(realizedAmount())" />
          <sb-metric-card label="Open trades" [value]="openTrades()" [decimals]="0" />
          <sb-metric-card label="Avg confidence" [value]="avgConfidence()" [decimals]="1" />
          <sb-metric-card label="Risk used" [value]="riskUsedPct()" [tint]="riskTone()" unit="%" [sub]="riskSub()" />
        </div>
      </div>

      <!-- Phone (v172 section 5, reversing v85's hide-on-phone): the portfolio
           block above (figure, day change, equity candles) now shows, the
           eight-card grid does not. This summary carries the figures the grid
           would; its Portfolio and Today rows repeat the figure above on
           purpose, so the summary reads complete on its own. -->
      <div class="mobile-summary" aria-label="Portfolio summary">
        <div><span>Portfolio</span><strong>{{ fmtAmount(balance()) }}</strong></div>
        <div [attr.data-tone]="tinted(changeTone())"><span>Today</span><strong>{{ fmtPct(changePct()) }}</strong></div>
        <div><span>Open</span><strong>{{ openTrades() }}</strong></div>
        <div [attr.data-tone]="tinted(riskTone())"><span>Risk</span><strong>{{ fmtPct(riskUsedPct()) }}</strong></div>
        <div [attr.data-tone]="tinted(winPairTone())"><span>Win rate</span><strong>{{ fmtFigure(winRate(), '%', 1) }}</strong></div>
        <div [attr.data-tone]="tinted(expectancyTone())"><span>Expectancy</span><strong>{{ fmtFigure(expectancyR(), 'R', 2) }}</strong></div>
        <div [attr.data-tone]="tinted(payoffTone())"><span>Payoff</span><strong>{{ fmtFigure(payoffRatio(), '', 2) }}</strong></div>
        <div [attr.data-tone]="tinted(realizedTone())"><span>{{ realizedLabel() }}</span><strong>{{ fmtFigure(realizedAmount(), currencyUnit(), 2) }}</strong></div>
      </div>
      <p class="account">{{ accountLabel }}</p>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    /* One column at every width (v172): the equity candles need the panel's
       full width, so the portfolio block (figure, day change, candles) is a
       row of its own above the KPI grid instead of a ~240px side column that
       would leave the chart and its readout unreadable. */
    .combined {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: var(--space-14);
      align-items: start;
    }
    .portfolio { min-width: 0; width: 100%; }
    .mobile-summary { display: none; }
    /* v181 §4: every figure here is simulated, before costs and tax. */
    .account { margin: var(--space-10) 0 0; font-size: var(--text-chip); color: var(--text-muted); }
    /* A fixed 4 columns, not auto-fit: eight cards read as two even rows of
       four, never an uneven 5+3 or 6+2 split that auto-fit would produce at
       an in-between width. minmax with two lengths (not a bare 1fr) keeps
       this grid's own width computable when the ancestor asks for its
       content size (.combined's "auto" track above, and -- separately --
       any container that ends up shrink-to-fit sized), which a 1fr track
       cannot give under those conditions. The tracks stretch (1fr max), so the
       cards span the panel and share the chart's left and right edges. */
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 1fr));
      gap: var(--space-14);
    }
    /* The tablet band -- v95 A5.
       Between sm and md the 4-up KPI grid's 560px floor and the portfolio
       block cannot both fit: measured at 768px the portfolio column
       collapsed to ~40px and '997,291.88 EUR' rendered as four fragments.
       Two KPI columns and a full-width portfolio row is the narrowest
       arrangement where both are readable. Above md the original four-up
       returns untouched. Placed after the base rules deliberately -- a media
       query adds no specificity, so a base .grid declared below it would
       win. */
    @media (max-width: 1023px) {
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 639px) {
      .grid { display: none; }
      .combined { margin-bottom: var(--space-10); }
      .mobile-summary {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: var(--space-8);
      }
      .mobile-summary div { display: flex; justify-content: space-between; gap: var(--space-8); padding: var(--space-6); border-bottom: 1px solid var(--border); font-size: var(--text-table); }
      .mobile-summary span { color: var(--text-secondary); }
      .mobile-summary strong { font-family: var(--font-mono); }
      .mobile-summary [data-tone='pos'] { background: var(--pos-soft); }
      .mobile-summary [data-tone='neg'] { background: var(--neg-soft); }
      .mobile-summary [data-tone='pos'] strong { color: var(--pos); }
      .mobile-summary [data-tone='neg'] strong { color: var(--neg); }
      .mobile-summary [data-tone='warn'] strong { color: var(--warn); }
    }
  `,
})
export class TradingPerformance {
  readonly balance = input<number | null>(null);
  readonly changePct = input<number | null>(null);
  readonly points = input<readonly number[]>([]);
  readonly openPnlPct = input<number | null>(null);
  /** Money equivalent of the open P&L %, shown beneath it. */
  readonly openPnlAmount = input<number | null>(null);
  readonly winRate = input<number | null>(null);
  readonly expectancyR = input<number | null>(null);
  readonly winRateN = input<number | null>(null);
  readonly expectancyN = input<number | null>(null);
  protected sample(n: number | null): string | null { return n === null ? null : `N=${n}`; }
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

  /** The two scopes this toggle sets. `active` is never offered, so it
   *  presses no segment (see DashboardScopeMode above). */
  protected readonly scopeOptions: SegmentOption[] = [
    { value: 'today', label: 'Today' },
    { value: 'all', label: 'All days' },
  ];

  protected pickScope(value: string): void {
    this.scopeChange.emit(value as DashboardScopeMode);
  }

  protected readonly currencyUnit = computed(() => ` ${this.currency()}`);
  protected fmtAmount = (value: number | null) => amount(value, this.currency());
  protected fmtPct = pct;
  /** Same rule as MetricCard: no value is an em dash, never a zero. */
  protected fmtFigure(value: number | null, unit: string, decimals: number): string {
    return value === null ? '—' : `${value.toFixed(decimals)}${unit}`;
  }
  /** An em dash alone reads as broken. When the scope is today and the figure
   *  is absent, say why: nothing has closed yet (the "All days" toggle has it). */
  protected noCloseHint(value: number | null): string | null {
    return value === null && this.scope() === 'today' ? 'none closed today' : null;
  }
  protected readonly openPnlSub = computed(() => {
    const value = this.openPnlAmount();
    return value === null ? null : amount(value, this.currency());
  });
  protected readonly riskSub = computed(() => {
    const cap = this.riskCapPct();
    return cap === null ? null : `of ${cap.toFixed(1)}% cap`;
  });
  protected readonly accountLabel = ACCOUNT_LABEL;
  protected readonly changeTone = computed(() => signTone(this.changePct()));
  protected readonly openPnlTone = computed(() => signTone(this.openPnlPct()));
  protected readonly expectancyTone = computed(() => signTone(this.expectancyR()));
  protected readonly realizedTone = computed(() => signTone(this.realizedAmount()));
  /** v181 §5: win rate and payoff are judged as a pair against break-even
   *  (100 / (1 + payoff)), never alone; neutral under 5 closes in scope. */
  protected readonly winPairTone = computed(() =>
    breakevenPairTone(this.winRate(), this.payoffRatio(), this.winRateN()));
  protected readonly payoffTone = computed(() => this.winPairTone());
  protected readonly riskTone = computed(() => riskToneOf(this.riskUsedPct(), this.riskCapPct()));
  /** A summary row carries a tone attribute only when it is judged. */
  protected tinted(tone: string): string | null {
    return tone === 'neutral' ? null : tone;
  }
}
