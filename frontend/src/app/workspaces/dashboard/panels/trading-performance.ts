import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { ViewportService } from '../../../ui/breakpoints';
import { Button } from '../../../ui/button';
import { Select, SelectOption } from '../../../ui/form-controls';
import { ControlRow, Panel } from '../../../ui/layout';
import { MetricCard } from '../../../ui/metric-card';
import { PortfolioValue } from './portfolio-value';
import { amount, pct } from '../../../ui/format';
import { ACCOUNT_LABEL } from './equity-candles.model';
import {
  SCOPE_PRESETS,
  ScopePreset,
  ScopeSelection,
  breakevenPairTone,
  rangeChipLabel,
  riskTone as riskToneOf,
  showsNowLabel,
  signTone,
} from './equity-range.model';

/** The dropdown's value for a hand-picked range: never a preset, never persisted. */
const RANGE_OPTION = 'Range';

/**
 * The eight figures — v85 D9.
 *
 * Win rate, expectancy and payoff ratio travel together on purpose: win rate
 * and payoff ratio decompose expectancy, so read as a triple they say why the
 * expectancy is what it is rather than only what it is.
 *
 * The scope control sits in this panel's header (D10) and is page-wide: it
 * also re-scopes the Closed tab below. v181 §1 widens it from Today / All
 * days to the presets 1D · 5D · 1M · 3M · 6M · YTD · 1Y · All, plus a Range
 * chip that a hand pan or zoom of the chart turns on. Below 640px the same
 * entries are one native dropdown.
 *
 * Portfolio Value merged in as this panel's first section rather than a
 * sibling card: both describe "how am I doing", and two bordered boxes side
 * by side that never disagree in that context read as one idea sliced in two.
 */
@Component({
  selector: 'sb-trading-performance',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, MetricCard, ControlRow, Button, PortfolioValue, Select],
  template: `
    <sb-panel heading="Trading performance">
      <div panel-actions class="scope">
        @if (phone()) {
          <sb-select class="preset-select" ariaLabel="Date scope"
                     [options]="presetOptions()" [value]="selectValue()"
                     (valueChange)="onSelect($event)" />
        } @else {
          <sb-control-row role="group" aria-label="Date scope">
            @for (option of presets; track option) {
              <button
                sb-button
                type="button"
                [attr.data-preset]="option"
                [variant]="activePreset() === option ? 'secondary' : 'ghost'"
                [attr.aria-pressed]="activePreset() === option"
                (click)="presetChange.emit(option)"
              >{{ option }}</button>
            }
            @if (rangeLabel(); as label) {
              <span class="range-chip" aria-current="true"><span class="range-word">Range</span> {{ label }}</span>
            }
          </sb-control-row>
        }
      </div>

      @if (stale()) {
        <p class="stale-hint" role="status">Couldn't refresh for this range · showing the last figures</p>
      }

      <div class="combined">
        <sb-portfolio-value
          class="portfolio"
          [balance]="balance()"
          [changePct]="changePct()"
          [points]="points()"
          [currency]="currency()"
        />

        <div class="grid" [class.stale]="stale()">
          <sb-metric-card label="Open P&L" [value]="openPnlPct()" [tint]="openPnlTone()" unit="%" [sub]="openPnlSub()" [subPnl]="openPnlAmount()" />
          <sb-metric-card label="Win rate" [value]="winRate()" [tint]="winPairTone()" unit="%" [decimals]="1" [sub]="sample(winRateN())" />
          <sb-metric-card label="Expectancy" [value]="expectancyR()" [tint]="expectancyTone()" unit="R" [sub]="sample(expectancyN())" />
          <sb-metric-card label="Payoff ratio" [value]="payoffRatio()" [tint]="payoffTone()" [decimals]="2" [sub]="noCloseHint(payoffRatio())" />
          <sb-metric-card [label]="realizedLabel()" [value]="realizedAmount()" [tint]="realizedTone()"
                          [unit]="currencyUnit()" [sub]="noCloseHint(realizedAmount())" />
          <sb-metric-card label="Open trades" [value]="openTrades()" [decimals]="0" [sub]="openTradesSub()" />
          <sb-metric-card label="Avg confidence" [value]="avgConfidence()" [decimals]="1" />
          <sb-metric-card label="Risk used" [value]="riskUsedPct()" [tint]="riskTone()" unit="%" [sub]="riskSub()" />
        </div>
      </div>

      <!-- Phone (v172 section 5, reversing v85's hide-on-phone): the portfolio
           block above (figure, day change, equity candles) now shows, the
           eight-card grid does not. This summary carries the figures the grid
           would; its Portfolio and Today rows repeat the figure above on
           purpose, so the summary reads complete on its own. -->
      <div class="mobile-summary" [class.stale]="stale()" aria-label="Portfolio summary">
        <div><span>Portfolio</span><strong>{{ fmtAmount(balance()) }}</strong></div>
        <div [attr.data-tone]="tinted(changeTone())"><span>Today</span><strong>{{ fmtPct(changePct()) }}</strong></div>
        <div><span>Open{{ nowSuffix() }}</span><strong>{{ openTrades() }}</strong></div>
        <div [attr.data-tone]="tinted(riskTone())"><span>Risk{{ nowSuffix() }}</span><strong>{{ fmtPct(riskUsedPct()) }}</strong></div>
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
    .scope { min-width: 0; max-width: 100%; }
    /* v181 §1: the phone dropdown is a 44px target; --control-h is 28px on a
       fine pointer and the select's own height reads it. */
    .preset-select { display: block; --control-h: 44px; }
    .range-chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      border: 1px solid var(--border-strong);
      border-radius: var(--control-radius);
      background: var(--surface-raised);
      color: var(--text);
      font-size: var(--text-chip);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .range-word { color: var(--text-secondary); }
    /* v181 §9: a failed range refetch keeps the last figures, dimmed. */
    .grid.stale, .mobile-summary.stale { opacity: 0.55; }
    .stale-hint { margin: 0 0 var(--space-10); font-size: var(--text-chip); color: var(--warn); }
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
  readonly selection = input<ScopeSelection>({ kind: 'preset', preset: '1D' });
  /** v181 §9: the last range refetch failed; the figures are the previous ones. */
  readonly stale = input(false);
  readonly presetChange = output<ScopePreset>();

  /** Below 640px the presets are one native dropdown (v181 §1). */
  protected readonly phone = inject(ViewportService).isPhone;
  protected readonly presets = SCOPE_PRESETS;
  protected readonly activePreset = computed(() => {
    const selection = this.selection();
    return selection.kind === 'preset' ? selection.preset : null;
  });
  protected readonly rangeLabel = computed(() => {
    const selection = this.selection();
    return selection.kind === 'range' ? rangeChipLabel(selection.window) : null;
  });
  protected readonly presetOptions = computed<SelectOption[]>(() => {
    const options = SCOPE_PRESETS.map((value) => ({ value, label: value }));
    const label = this.rangeLabel();
    return label === null ? options : [...options, { value: RANGE_OPTION, label: `Range · ${label}` }];
  });
  protected readonly selectValue = computed(() => this.activePreset() ?? RANGE_OPTION);
  /** Only a preset leaves the dropdown; picking the Range entry changes nothing. */
  protected onSelect(value: string): void {
    const picked = SCOPE_PRESETS.find((option) => option === value);
    if (picked) this.presetChange.emit(picked);
  }

  /** v181 §5: open P&L, open trades and risk used are always "now"; outside
   *  1D a tinted card must not read as that window's exposure. */
  protected readonly nowLabel = computed(() => showsNowLabel(this.selection()));
  protected readonly nowSuffix = computed(() => (this.nowLabel() ? ' · now' : ''));
  protected readonly openTradesSub = computed(() => (this.nowLabel() ? 'now' : null));
  private withNow(text: string | null): string | null {
    if (!this.nowLabel()) return text;
    return text === null ? 'now' : `now · ${text}`;
  }

  protected readonly currencyUnit = computed(() => ` ${this.currency()}`);
  protected fmtAmount = (value: number | null) => amount(value, this.currency());
  protected fmtPct = pct;
  /** Same rule as MetricCard: no value is an em dash, never a zero. */
  protected fmtFigure(value: number | null, unit: string, decimals: number): string {
    return value === null ? '—' : `${value.toFixed(decimals)}${unit}`;
  }
  /** An em dash alone reads as broken: say why, in the scope's own words.
   *  All has no hint: nothing closed at all is its own answer. */
  protected noCloseHint(value: number | null): string | null {
    if (value !== null) return null;
    const active = this.activePreset();
    if (active === '1D') return 'none closed today';
    return active === 'All' ? null : 'none closed in range';
  }
  protected readonly openPnlSub = computed(() => {
    const value = this.openPnlAmount();
    return this.withNow(value === null ? null : amount(value, this.currency()));
  });
  protected readonly riskSub = computed(() => {
    const cap = this.riskCapPct();
    return this.withNow(cap === null ? null : `of ${cap.toFixed(1)}% cap`);
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
